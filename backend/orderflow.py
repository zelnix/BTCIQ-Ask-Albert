"""Pillar 1 — Real-time WebSocket ingestion + 1-second rolling order-flow aggregator.

Architecture:
  Exchange WS consumers (Coinbase spot trades, Bybit perp trades + liquidations)
    -> Redis Streams ingestion buffer (XADD, MAXLEN ~100k)  [+ in-memory rolling window]
    -> 1-second aggregator worker computes CVD / OFI / VPIN / liquidation-cascade
    -> snapshot cached in Redis (of:latest) AND process memory for sub-ms endpoints.

Binance is geo-blocked (451) from this host, so we use Coinbase + Bybit which are
reachable. Everything degrades gracefully: if a venue drops we reconnect with
backoff; if Redis is down we keep the in-memory window; the endpoint always
returns a status.
"""

import asyncio
import json
import os
import threading
import time
from collections import deque

import websockets

try:
    import redis as _redis
except Exception:  # noqa
    _redis = None

REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
WINDOW_SEC = 60          # rolling analytics window
STREAM_MAXLEN = 100000   # circular Redis stream buffer

_lock = threading.Lock()
_book_lock = threading.Lock()
_trades = deque()        # (ts, price, size_btc, aggressor 'buy'/'sell', venue)
_liqs = deque()          # (ts, price, notional_usd, side 'long'/'short', venue)
_hist = deque(maxlen=180)  # per-second rolling samples for the sparkline
_book = {'bids': {}, 'asks': {}, 'ts': 0}  # live Bybit L2 order book (price->size)
_walls_state = {}          # 'bid'/'ask' -> tracked significant wall near price
_wall_events = deque(maxlen=20)
WALL_MIN_USD = 3_000_000   # a resting wall this large near price is noteworthy
WALL_NEAR_PCT = 0.5        # within ±0.5% of mid
WALL_PERSIST_S = 5         # must persist this long to count (filters flicker/spoof noise)
_state = {
    'started': False,
    'venues': {'coinbase': 'connecting', 'bybit': 'connecting', 'bybit_liq': 'connecting', 'bybit_book': 'connecting'},
    'last_price': None,
    'session_cvd_btc': 0.0,
    'snapshot': None,
    'started_at': None,
    'redis': False,
}
_r = None


def _get_redis():
    global _r
    if _redis is None:
        return None
    if _r is None:
        try:
            _r = _redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1.0)
            _r.ping()
            _state['redis'] = True
        except Exception:  # noqa
            _r = None
            _state['redis'] = False
    return _r


def _xadd(stream, fields):
    r = _get_redis()
    if not r:
        return
    try:
        r.xadd(stream, fields, maxlen=STREAM_MAXLEN, approximate=True)
    except Exception:  # noqa
        _state['redis'] = False


def _record_trade(ts, price, size, aggressor, venue):
    with _lock:
        _trades.append((ts, price, size, aggressor, venue))
        _state['last_price'] = price
        _state['session_cvd_btc'] += size if aggressor == 'buy' else -size
        cutoff = ts - WINDOW_SEC * 2
        while _trades and _trades[0][0] < cutoff:
            _trades.popleft()
    _xadd('of:trades', {'ts': f'{ts:.3f}', 'p': f'{price:.2f}', 'sz': f'{size:.6f}',
                        'side': aggressor, 'v': venue})


def _record_liq(ts, price, notional, side, venue):
    with _lock:
        _liqs.append((ts, price, notional, side, venue))
        cutoff = ts - WINDOW_SEC * 3
        while _liqs and _liqs[0][0] < cutoff:
            _liqs.popleft()
    _xadd('of:liq', {'ts': f'{ts:.3f}', 'p': f'{price:.2f}', 'usd': f'{notional:.0f}',
                     'side': side, 'v': venue})


# ---------------------------------------------------------------- consumers
async def _coinbase():
    url = 'wss://ws-feed.exchange.coinbase.com'
    sub = {'type': 'subscribe', 'product_ids': ['BTC-USD'], 'channels': ['matches']}
    while True:
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                _state['venues']['coinbase'] = 'live'
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get('type') in ('match', 'last_match'):
                        try:
                            price = float(m['price']); size = float(m['size'])
                        except Exception:  # noqa
                            continue
                        # Coinbase 'side' is the MAKER side; taker aggressor is the opposite.
                        aggressor = 'buy' if m.get('side') == 'sell' else 'sell'
                        _record_trade(time.time(), price, size, aggressor, 'coinbase')
        except Exception:  # noqa
            _state['venues']['coinbase'] = 'reconnecting'
            await asyncio.sleep(3)


async def _bybit():
    url = 'wss://stream.bybit.com/v5/public/linear'
    sub = {'op': 'subscribe', 'args': ['publicTrade.BTCUSDT']}
    while True:
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                _state['venues']['bybit'] = 'live'
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get('topic', '').startswith('publicTrade'):
                        for t in m.get('data', []):
                            try:
                                price = float(t['p']); size = float(t['v'])
                            except Exception:  # noqa
                                continue
                            aggressor = 'buy' if str(t.get('S')).lower() == 'buy' else 'sell'
                            _record_trade(time.time(), price, size, aggressor, 'bybit')
        except Exception:  # noqa
            _state['venues']['bybit'] = 'reconnecting'
            await asyncio.sleep(3)


async def _bybit_liq():
    url = 'wss://stream.bybit.com/v5/public/linear'
    sub = {'op': 'subscribe', 'args': ['allLiquidation.BTCUSDT']}
    while True:
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                _state['venues']['bybit_liq'] = 'live'
                async for raw in ws:
                    m = json.loads(raw)
                    if 'iquidation' in m.get('topic', ''):
                        for t in m.get('data', []):
                            try:
                                price = float(t['p']); size = float(t['v'])
                            except Exception:  # noqa
                                continue
                            # Bybit S = side of the filled order that liquidated a position.
                            # S='Sell' => a long was force-sold; S='Buy' => a short was covered.
                            side = 'long' if str(t.get('S')).lower() == 'sell' else 'short'
                            _record_liq(time.time(), price, price * size, side, 'bybit')
        except Exception:  # noqa
            _state['venues']['bybit_liq'] = 'reconnecting'
            await asyncio.sleep(3)


async def _bybit_book():
    """Maintain a live L2 order book from Bybit (orderbook.50) for the liquidity
    heatmap: snapshot resets, deltas patch (size '0' removes a level)."""
    url = 'wss://stream.bybit.com/v5/public/linear'
    sub = {'op': 'subscribe', 'args': ['orderbook.50.BTCUSDT']}
    while True:
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                _state['venues']['bybit_book'] = 'live'
                async for raw in ws:
                    m = json.loads(raw)
                    if not m.get('topic', '').startswith('orderbook'):
                        continue
                    data = m.get('data') or {}
                    typ = m.get('type')
                    with _book_lock:
                        if typ == 'snapshot':
                            _book['bids'] = {float(p): float(s) for p, s in data.get('b', [])}
                            _book['asks'] = {float(p): float(s) for p, s in data.get('a', [])}
                        else:  # delta
                            for p, s in data.get('b', []):
                                p = float(p); s = float(s)
                                if s == 0:
                                    _book['bids'].pop(p, None)
                                else:
                                    _book['bids'][p] = s
                            for p, s in data.get('a', []):
                                p = float(p); s = float(s)
                                if s == 0:
                                    _book['asks'].pop(p, None)
                                else:
                                    _book['asks'][p] = s
                        _book['ts'] = time.time()
        except Exception:  # noqa
            _state['venues']['bybit_book'] = 'reconnecting'
            await asyncio.sleep(3)


def _build_heatmap(mid_hint=None, band=0.012, nb=20):
    """Bucket live resting liquidity into price bins around mid for the heatmap."""
    with _book_lock:
        bids = dict(_book['bids'])
        asks = dict(_book['asks'])
    if not bids or not asks:
        return None
    best_bid = max(bids)
    best_ask = min(asks)
    mid = (best_bid + best_ask) / 2.0
    lo = mid * (1 - band)
    hi = mid * (1 + band)
    step = (hi - lo) / nb
    if step <= 0:
        return None
    bins = [{'lo': lo + i * step, 'hi': lo + (i + 1) * step, 'bid_usd': 0.0, 'ask_usd': 0.0} for i in range(nb)]
    for p, s in bids.items():
        if lo <= p <= mid:
            bins[min(nb - 1, int((p - lo) / step))]['bid_usd'] += p * s
    for p, s in asks.items():
        if mid < p <= hi:
            bins[min(nb - 1, int((p - lo) / step))]['ask_usd'] += p * s
    out = []
    max_bid = {'usd': 0.0, 'price': None}
    max_ask = {'usd': 0.0, 'price': None}
    bid_total = 0.0
    ask_total = 0.0
    for b in bins:
        bmid = (b['lo'] + b['hi']) / 2.0
        bu = round(b['bid_usd'], 0)
        au = round(b['ask_usd'], 0)
        bid_total += bu
        ask_total += au
        out.append({'price': round(bmid, 1), 'pct': round((bmid - mid) / mid * 100, 3),
                    'bid_usd': bu, 'ask_usd': au})
        if bu > max_bid['usd']:
            max_bid = {'usd': bu, 'price': round(bmid, 1)}
        if au > max_ask['usd']:
            max_ask = {'usd': au, 'price': round(bmid, 1)}
    tot = bid_total + ask_total
    depth_imbalance = {
        'bid_usd_total': round(bid_total, 0),
        'ask_usd_total': round(ask_total, 0),
        'bid_pct': round(100 * bid_total / tot, 1) if tot > 0 else 50.0,
        'state': ('Bids stacked' if tot > 0 and bid_total / tot > 0.58 else
                  'Asks stacked' if tot > 0 and bid_total / tot < 0.42 else 'Balanced'),
    }
    return {'mid': round(mid, 1), 'band_pct': band * 100, 'bins': out,
            'max_bid_wall': max_bid, 'max_ask_wall': max_ask, 'levels': len(bids) + len(asks),
            'depth_imbalance': depth_imbalance}


def _track_walls(ob, now):
    """Detect large resting walls that APPEAR (persisted) or get PULLED near price
    (a spoofing / support-resistance tell). Emits debounced events."""
    if not ob or not ob.get('mid'):
        return
    mid = ob['mid']
    for side in ('bid', 'ask'):
        wall = ob['max_bid_wall'] if side == 'bid' else ob['max_ask_wall']
        usd = (wall or {}).get('usd') or 0
        price = (wall or {}).get('price')
        pct = abs((price - mid) / mid * 100) if price and mid else 999
        significant = usd >= WALL_MIN_USD and pct <= WALL_NEAR_PCT
        st = _walls_state.get(side)
        if significant:
            if not st or (price and st.get('price') and abs(st['price'] - price) / price > 0.003):
                st = {'price': price, 'usd': usd, 'since': now, 'active': False}
                _walls_state[side] = st
            st['usd'] = usd
            st['last_seen'] = now
            if not st['active'] and now - st['since'] >= WALL_PERSIST_S:
                st['active'] = True
                _wall_events.append({'t': now, 'side': side, 'event': 'appeared',
                                     'price': price, 'usd': usd,
                                     'pct': round((price - mid) / mid * 100, 3)})
        else:
            if st and st.get('active'):
                _wall_events.append({'t': now, 'side': side, 'event': 'pulled',
                                     'price': st.get('price'), 'usd': st.get('usd')})
            if st:
                _walls_state.pop(side, None)


# ---------------------------------------------------------------- aggregator
def _round(v, n=2):
    try:
        return round(float(v), n)
    except Exception:  # noqa
        return None


async def _aggregator():
    while True:
        await asyncio.sleep(1.0)
        try:
            now = time.time()
            with _lock:
                trades = list(_trades)
                liqs = list(_liqs)
                last_price = _state['last_price']
                session_cvd = _state['session_cvd_btc']
            w = [t for t in trades if t[0] >= now - WINDOW_SEC]
            buy_btc = sum(t[2] for t in w if t[3] == 'buy')
            sell_btc = sum(t[2] for t in w if t[3] == 'sell')
            tot_btc = buy_btc + sell_btc
            cvd_win = buy_btc - sell_btc
            imbalance = (buy_btc / tot_btc) if tot_btc > 0 else 0.5
            # OFI proxy: net signed BTC volume per second over the window.
            ofi = cvd_win / max(1, WINDOW_SEC)
            # VPIN proxy: mean order-flow toxicity across 1-second buckets.
            buckets = {}
            for ts, _p, sz, side, _v in w:
                b = int(ts)
                d = buckets.setdefault(b, [0.0, 0.0])
                d[0 if side == 'buy' else 1] += sz
            vpin_vals = [abs(bd[0] - bd[1]) / (bd[0] + bd[1]) for bd in buckets.values() if (bd[0] + bd[1]) > 0]
            vpin = sum(vpin_vals) / len(vpin_vals) if vpin_vals else 0.0
            # Liquidations over the window + a short 10s cascade probe.
            lw = [x for x in liqs if x[0] >= now - WINDOW_SEC]
            long_liq = sum(x[2] for x in lw if x[3] == 'long')
            short_liq = sum(x[2] for x in lw if x[3] == 'short')
            recent_liq = sum(x[2] for x in liqs if x[0] >= now - 10)
            cascade = recent_liq >= 1_000_000  # >$1M liquidated in 10s

            venues_live = sum(1 for s in _state['venues'].values() if s == 'live')
            status = 'live' if venues_live > 0 else 'connecting'
            snap = {
                'status': status,
                'as_of': now,
                'venues': dict(_state['venues']),
                'redis': _state['redis'],
                'last_price': _round(last_price),
                'window_sec': WINDOW_SEC,
                'trades_window': len(w),
                'trades_per_sec': _round(len(w) / max(1, WINDOW_SEC), 2),
                'buy_btc': _round(buy_btc, 4),
                'sell_btc': _round(sell_btc, 4),
                'cvd_window_btc': _round(cvd_win, 4),
                'session_cvd_btc': _round(session_cvd, 4),
                'buy_ratio_pct': _round(imbalance * 100, 1),
                'ofi_btc_per_s': _round(ofi, 4),
                'vpin': _round(vpin, 3),
                'flow_state': ('Aggressive buying' if imbalance > 0.58 else
                               'Aggressive selling' if imbalance < 0.42 else 'Balanced'),
                'liquidations': {
                    'long_usd_1m': _round(long_liq, 0),
                    'short_usd_1m': _round(short_liq, 0),
                    'net_usd_1m': _round(short_liq - long_liq, 0),
                    'cascade_10s_usd': _round(recent_liq, 0),
                    'cascade_risk': bool(cascade),
                    'count_1m': len(lw),
                },
            }
            _hist.append({'t': int(now), 'cvd': _round(session_cvd, 3),
                          'liq_net': _round(short_liq - long_liq, 0)})
            snap['history'] = list(_hist)[-90:]
            try:
                ob = _build_heatmap()
                snap['orderbook'] = ob
                _track_walls(ob, now)
                snap['walls'] = {'bid': _walls_state.get('bid'), 'ask': _walls_state.get('ask'),
                                 'recent_events': list(_wall_events)[-5:]}
            except Exception:  # noqa
                snap['orderbook'] = None
            _state['snapshot'] = snap
            r = _get_redis()
            if r:
                try:
                    r.set('of:latest', json.dumps(snap), ex=30)
                except Exception:  # noqa
                    pass
        except Exception:  # noqa
            import traceback
            traceback.print_exc()


def _run_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.gather(
        _coinbase(), _bybit(), _bybit_liq(), _bybit_book(), _aggregator(),
    ))


def start():
    """Start the WS consumers + aggregator in a dedicated background thread. Idempotent."""
    with _lock:
        if _state['started']:
            return
        _state['started'] = True
        _state['started_at'] = time.time()
    _get_redis()
    threading.Thread(target=_run_loop, daemon=True, name='orderflow').start()


def get_latest():
    snap = _state.get('snapshot')
    if snap:
        return {'status': snap.get('status', 'live'), **snap}
    # not warmed up yet — try Redis, else report connecting
    r = _get_redis()
    if r:
        try:
            raw = r.get('of:latest')
            if raw:
                s = json.loads(raw)
                return {'status': s.get('status', 'live'), **s}
        except Exception:  # noqa
            pass
    return {'status': 'connecting', 'venues': dict(_state['venues']),
            'redis': _state['redis'], 'message': 'Order-flow pipeline warming up…'}
