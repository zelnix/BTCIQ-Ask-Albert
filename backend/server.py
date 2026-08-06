"""
Bitcoin Predictive AI - FastAPI ML Microservice
----------------------------------------------
Real BTC/USD daily data (ccxt: Kraken primary, Coinbase fallback)
 -> price-agnostic stationary features (RSI, StochRSI, MACD hist, EMA ratio,
    ATR%, Bollinger width%, Volume Z-score, Volume ratio)
 -> RandomForest classifier (predict if tomorrow's close > today's close)
 -> TimeSeriesSplit cross-validation + walk-forward backtest (accuracy over time)
 -> persisted to MongoDB, refreshed daily via APScheduler.

Exposed under /api/v1/* and proxied by the Next.js /api layer.
"""
import os
import re
import uuid
import math
import json
import asyncio
import threading
import datetime
import traceback
import urllib.request

import ccxt
import numpy as np
import pandas as pd
try:
    import shap  # SHAP factor contributions
    _HAS_SHAP = True
except Exception:  # noqa
    _HAS_SHAP = False
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv('/app/.env')

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'your_database_name')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
runs_col = db['btc_runs']
signals_col = db['live_signals']
dominance_col = db['dominance_hist']
news_col = db['news']
chat_col = db['ask_quant_chat']
predictions_col = db['predictions']
bitmark_col = db['bitmark_snapshots']
smart_alerts_col = db['smart_alerts']
audit_col = db['forecast_audit']
insights_col = db['albert_insights']  # cache for AI-generated section insights
compare_col = db['compare_coins']  # cache for per-coin comparison summaries
coin_dash_col = db['coin_dashboards']  # cache for per-coin full dashboards (altcoins)
coin_news_col = db['coin_news']  # cache for per-coin news (altcoins)
coin_dom_col = db['coin_dominance_hist']  # per-coin market-cap dominance history
# Admin passcode gate for manual forecast runs (Stage-1: passcode instead of full auth)
ADMIN_PASSCODE = os.environ.get('ADMIN_PASSCODE', 'btciq-admin')
# BitMarkAI forecast trigger state (set by manual/event triggers, read by compute)
_forecast_trigger = {'reason': None}
_bitmark_last_manual = {'ts': 0.0}

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
GEMINI_MODEL = 'gemini-2.5-flash'
# Ask Quant conversational model (Gemini 3 Flash via Emergent gateway, verified available)
CHAT_MODEL = os.environ.get('CHAT_MODEL', 'gemini-3-flash-preview')
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import feedparser
    _HAS_LLM = True
except Exception:  # noqa
    _HAS_LLM = False

# in-memory ticker cache (avoid hammering the exchange on every poll)
_ticker_cache = {}  # symbol -> {'data':..., 'ts':...}
# USD->AUD fx rate cache (refreshed ~30 min)
_fx_cache = {'rate': None, 'ts': 0.0}


def grade_pending(df):
    """Resolve pending forward signals whose target candle close is now known."""
    close_by_date = {
        row['timestamp'].strftime('%Y-%m-%d'): float(row['close'])
        for _, row in df.iterrows()
    }
    for s in signals_col.find({'resolved': False}):
        tgt = s.get('predict_for_date')
        base = s.get('close_at_signal')
        if tgt in close_by_date and base:
            nc = close_by_date[tgt]
            actual = 'UP' if nc > base else 'DOWN'
            signals_col.update_one(
                {'_id': s['_id']},
                {'$set': {'resolved': True, 'next_close': round(nc, 2),
                          'actual': actual, 'correct': bool(actual == s['signal'])}},
            )


def record_live_signal(as_of, predict_for, signal, confidence, close):
    """Store today's forward signal as pending (one per as_of date)."""
    signals_col.update_one(
        {'as_of': as_of},
        {'$setOnInsert': {
            '_id': str(uuid.uuid4()), 'as_of': as_of,
            'predict_for_date': predict_for, 'signal': signal,
            'confidence': confidence, 'close_at_signal': close,
            'resolved': False, 'created_at': datetime.datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


def compute_live_record():
    resolved = list(signals_col.find({'resolved': True}, {'_id': 0}))
    tracked = signals_col.count_documents({})
    r = len(resolved)
    correct = sum(1 for s in resolved if s.get('correct'))
    return {
        'tracked': int(tracked), 'resolved': int(r), 'correct': int(correct),
        'winRate': round(correct / r * 100, 1) if r else None,
    }

app = FastAPI(title='BTC Predictive AI Engine')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

_state = {'status': 'idle', 'error': None, 'started_at': None}
_lock = threading.Lock()

FEATURE_COLS = [
    'RSI', 'StochRSI', 'MACD_Hist_Norm', 'EMA_Ratio',
    'ATR_Pct', 'BB_Width_Pct', 'Volume_Z', 'Volume_Ratio',
]

FEATURE_META = {
    'RSI': {'label': 'RSI (14)', 'category': 'Momentum'},
    'StochRSI': {'label': 'Stochastic RSI', 'category': 'Momentum'},
    'MACD_Hist_Norm': {'label': 'MACD Histogram', 'category': 'Trend'},
    'EMA_Ratio': {'label': 'EMA 9/21 Ratio', 'category': 'Trend'},
    'ATR_Pct': {'label': 'ATR %', 'category': 'Volatility'},
    'BB_Width_Pct': {'label': 'Bollinger Width %', 'category': 'Volatility'},
    'Volume_Z': {'label': 'Volume Z-Score', 'category': 'Volume'},
    'Volume_Ratio': {'label': 'Volume Ratio', 'category': 'Volume'},
}


# =====================================================================
# STEP 1: FETCH RAW BITCOIN OHLCV DATA (real data, no API key needed)
# =====================================================================
def fetch_ohlcv():
    errors = []
    for name, sym in [('kraken', 'BTC/USD'), ('coinbase', 'BTC/USD')]:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            bars = ex.fetch_ohlcv(sym, timeframe='1d', limit=720)
            if bars and len(bars) > 250:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.sort_values('timestamp').reset_index(drop=True)
                return df, name
        except Exception as e:  # noqa
            errors.append(f'{name}: {e}')
    raise RuntimeError('All data sources failed: ' + ' | '.join(errors))


# =====================================================================
# STEP 2: PRICE-AGNOSTIC STATIONARY FEATURES (manual, numpy/pandas)
# =====================================================================
def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def _atr(high, low, close, length=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def build_features(df):
    df = df.copy()
    close = df['close']

    # Momentum
    rsi_raw = _rsi(close, 14)
    df['RSI'] = rsi_raw / 100.0
    min_r = rsi_raw.rolling(14).min()
    max_r = rsi_raw.rolling(14).max()
    df['StochRSI'] = ((rsi_raw - min_r) / (max_r - min_r).replace(0, np.nan)).clip(0, 1)

    # Trend
    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    df['MACD_Hist_Norm'] = (macd - signal) / close
    df['EMA_Ratio'] = (_ema(close, 9) / _ema(close, 21)) - 1.0

    # Volatility
    df['ATR_Pct'] = _atr(df['high'], df['low'], close, 14) / close
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    df['BB_Width_Pct'] = ((mid + 2 * std) - (mid - 2 * std)) / mid

    # Volume
    vol_ma = df['volume'].rolling(20).mean()
    vol_std = df['volume'].rolling(20).std()
    df['Volume_Z'] = (df['volume'] - vol_ma) / vol_std.replace(0, np.nan)
    df['Volume_Ratio'] = df['volume'] / vol_ma

    return df


# =====================================================================
# INSTITUTIONAL-GRADE ENGINES (no-key: block data, CoinGecko, chart TA)
# =====================================================================
def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'BitcoinQuant/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _http_text(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'BitcoinQuant/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8').strip()


HALVINGS = [
    (0, '2009-01-03', 50.0),
    (210000, '2012-11-28', 25.0),
    (420000, '2016-07-09', 12.5),
    (630000, '2020-05-11', 6.25),
    (840000, '2024-04-20', 3.125),
]
HALVING_REF_PRICE = {1: 12.0, 2: 650.0, 3: 8600.0, 4: 63900.0}  # approx BTC price on halving day
CYCLE_DAYS = 1460  # ~4 years


def fetch_block_height():
    for url in ['https://mempool.space/api/blocks/tip/height', 'https://blockchain.info/q/getblockcount']:
        try:
            return int(_http_text(url))
        except Exception:  # noqa
            continue
    return None


def compute_cycle_context(price, regime_name):
    height = fetch_block_height()
    if not height:
        return None
    interval = 210000
    epoch = min(height // interval, 4)
    reward = 50.0 / (2 ** epoch)
    last_block, last_date, _ = HALVINGS[epoch]
    next_block = (epoch + 1) * interval
    blocks_to_next = max(0, next_block - height)
    est_days_to_next = round(blocks_to_next * 10 / 1440, 1)
    last_dt = datetime.datetime.strptime(last_date, '%Y-%m-%d')
    days_since = (datetime.datetime.utcnow() - last_dt).days
    ref = HALVING_REF_PRICE.get(epoch)
    cycle_perf = round((price / ref - 1) * 100, 1) if ref else None
    progress = round(min(1.0, days_since / CYCLE_DAYS) * 100, 1)

    frac = days_since / CYCLE_DAYS
    if blocks_to_next < 21000:
        phase = 'Pre-Halving Transition'
    elif frac < 0.10:
        phase = 'Post-Halving Repricing'
    elif frac < 0.35:
        phase = 'Expansion'
    elif frac < 0.50:
        phase = 'Price Discovery'
    elif frac < 0.62:
        phase = 'Distribution Risk'
    elif frac < 0.85:
        phase = 'Contraction'
    else:
        phase = 'Accumulation'
    # blend with live regime (calendar is only context, not destiny)
    if 'Bearish' in regime_name and phase in ('Price Discovery', 'Distribution Risk'):
        phase = 'Contraction'
    return {
        'block_height': height, 'epoch': epoch, 'halving_number': epoch,
        'reward': reward, 'last_halving_date': last_date, 'days_since_halving': days_since,
        'next_halving_block': next_block, 'blocks_to_next': blocks_to_next,
        'est_days_to_next': est_days_to_next, 'cycle_perf_pct': cycle_perf,
        'cycle_progress_pct': progress, 'phase': phase,
    }


def fetch_dominance(price_change_24h):
    try:
        g = _http_json('https://api.coingecko.com/api/v3/global')['data']
    except Exception:  # noqa
        return None
    dom = round(float(g['market_cap_percentage']['btc']), 2)
    total = float(g['total_market_cap']['usd'])
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    dominance_col.update_one({'date': today},
                             {'$set': {'dominance': dom, 'total_mcap': total}}, upsert=True)
    # derive change from stored history if present
    hist = list(dominance_col.find({}, {'_id': 0}).sort('date', -1).limit(40))

    def change_over(days):
        if len(hist) <= days:
            return None
        return round(dom - hist[days]['dominance'], 2)

    d7 = change_over(7)
    d30 = change_over(30)
    dom_dir = 'Neutral'
    ref = d7 if d7 is not None else None
    if ref is not None:
        dom_dir = 'Rising' if ref > 0.15 else ('Falling' if ref < -0.15 else 'Neutral')
    # 2D interpretation (price vs dominance)
    p_up = price_change_24h >= 0
    if dom_dir == 'Neutral':
        interp = 'Dominance is flat — no strong rotation signal yet (history is still building).'
    elif p_up and dom_dir == 'Rising':
        interp = 'Price up + dominance up: capital is concentrating into Bitcoin.'
    elif p_up and dom_dir == 'Falling':
        interp = 'Price up + dominance down: broad crypto risk-on expansion.'
    elif (not p_up) and dom_dir == 'Rising':
        interp = 'Price down + dominance up: defensive rotation out of altcoins into Bitcoin.'
    else:
        interp = 'Price down + dominance down: broad crypto-market weakness.'
    return {'dominance': dom, 'total_mcap_t': round(total / 1e12, 3),
            'change_7d': d7, 'change_30d': d30, 'direction': dom_dir,
            'interpretation': interp, 'history_points': len(hist)}


COINGECKO_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'XRP': 'ripple',
    'ADA': 'cardano', 'DOGE': 'dogecoin', 'AVAX': 'avalanche-2', 'LINK': 'chainlink',
    'DOT': 'polkadot', 'LTC': 'litecoin', 'MATIC': 'matic-network', 'ATOM': 'cosmos',
}


def compute_coin_dominance(symbol, price_change_24h):
    """Real market-cap dominance (share of total crypto market cap) for any coin,
    keyless via CoinGecko. Shaped like the BTC dominance object so the UI can reuse it."""
    try:
        g = _http_json('https://api.coingecko.com/api/v3/global')['data']
    except Exception:  # noqa
        return None
    total = float(g['total_market_cap']['usd'])
    pct = g.get('market_cap_percentage', {}) or {}
    key = symbol.lower()
    dom = None
    mcap = None
    if key in pct:
        dom = round(float(pct[key]), 3)
        mcap = total * dom / 100.0
    else:
        cid = COINGECKO_IDS.get(symbol)
        if cid:
            try:
                arr = _http_json(f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={cid}')
                if arr and arr[0].get('market_cap'):
                    mcap = float(arr[0]['market_cap'])
                    dom = round(mcap / total * 100.0, 4)
            except Exception:  # noqa
                pass
    if dom is None:
        return None
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    coin_dom_col.update_one({'symbol': symbol, 'date': today},
                            {'$set': {'symbol': symbol, 'date': today, 'dominance': dom, 'total_mcap': total}},
                            upsert=True)
    hist = list(coin_dom_col.find({'symbol': symbol}, {'_id': 0}).sort('date', -1).limit(40))

    def change_over(days):
        if len(hist) <= days:
            return None
        return round(dom - hist[days]['dominance'], 3)

    d7 = change_over(7)
    d30 = change_over(30)
    dom_dir = 'Neutral'
    if d7 is not None:
        thr = max(0.02, dom * 0.03)
        dom_dir = 'Rising' if d7 > thr else ('Falling' if d7 < -thr else 'Neutral')
    p_up = price_change_24h >= 0
    name = COMPARE_COINS.get(symbol, {}).get('name', symbol) if 'COMPARE_COINS' in globals() else symbol
    if dom_dir == 'Neutral':
        interp = f'{name}\u2019s market share is holding steady (history is still building).'
    elif p_up and dom_dir == 'Rising':
        interp = f'Price up + share rising: capital is rotating into {name}.'
    elif p_up and dom_dir == 'Falling':
        interp = f'Price up but share slipping: the broader market is rising even faster than {name}.'
    elif (not p_up) and dom_dir == 'Rising':
        interp = f'Price down but share rising: {name} is holding up better than the market.'
    else:
        interp = f'Price down + share falling: {name} is underperforming the broader market.'
    return {'dominance': dom, 'total_mcap_t': round(total / 1e12, 3),
            'mcap_usd': round(mcap) if mcap else None,
            'change_7d': d7, 'change_30d': d30, 'direction': dom_dir,
            'interpretation': interp, 'history_points': len(hist)}


def _swings(series, order=4):
    vals = series.values
    highs, lows = [], []
    for i in range(order, len(vals) - order):
        w = vals[i - order:i + order + 1]
        if vals[i] == w.max():
            highs.append((i, float(vals[i])))
        if vals[i] == w.min():
            lows.append((i, float(vals[i])))
    return highs, lows


def _cluster_levels(points, price, tol=0.015):
    levels = []
    for _, p in sorted(points, key=lambda z: z[1]):
        placed = False
        for lv in levels:
            if abs(p - lv['price']) / price < tol:
                lv['price'] = (lv['price'] * lv['strength'] + p) / (lv['strength'] + 1)
                lv['strength'] += 1
                placed = True
                break
        if not placed:
            levels.append({'price': p, 'strength': 1})
    return levels


def compute_chart_intelligence(df):
    d = df.tail(260).reset_index(drop=True)
    close = d['close']; high = d['high']; low = d['low']; vol = d['volume']
    price = float(close.iloc[-1])
    ema20 = _ema(close, 20).iloc[-1]; ema50 = _ema(close, 50).iloc[-1]
    ema200 = _ema(close, 200).iloc[-1] if len(close) >= 200 else _ema(close, 100).iloc[-1]

    if price > ema20 > ema50 and price > ema200:
        structure = 'Uptrend'; struct_bias = 'Bullish'
    elif price < ema20 < ema50 and price < ema200:
        structure = 'Downtrend'; struct_bias = 'Bearish'
    else:
        structure = 'Range / Transition'; struct_bias = 'Neutral'

    highs, lows = _swings(close, order=4)
    res = [lv for lv in _cluster_levels(highs, price) if lv['price'] > price * 1.001]
    sup = [lv for lv in _cluster_levels(lows, price) if lv['price'] < price * 0.999]
    res = sorted(res, key=lambda z: (-z['strength'], z['price']))[:3]
    sup = sorted(sup, key=lambda z: (-z['strength'], -z['price']))[:3]
    sr_levels = ([{'price': round(l['price'], 0), 'type': 'resistance', 'strength': int(l['strength'])} for l in res]
                 + [{'price': round(l['price'], 0), 'type': 'support', 'strength': int(l['strength'])} for l in sup])

    signals = []
    signals.append({'type': 'Moving-Average Structure', 'bias': struct_bias,
                    'detail': f'Price {"above" if price>ema50 else "below"} EMA50 and EMA200 — {structure.lower()} structure.'})

    hi20 = float(high.iloc[-21:-1].max()); lo20 = float(low.iloc[-21:-1].min())
    volz = float((vol.iloc[-1] - vol.tail(20).mean()) / (vol.tail(20).std() or 1))
    if price > hi20:
        signals.append({'type': 'Breakout', 'bias': 'Bullish',
                        'detail': f'Close broke above the 20-day high (${hi20:,.0f}){" with volume confirmation" if volz>0.5 else " but volume is light"}.'})
    elif price < lo20:
        signals.append({'type': 'Breakdown', 'bias': 'Bearish',
                        'detail': f'Close broke below the 20-day low (${lo20:,.0f}){" with volume confirmation" if volz>0.5 else " but volume is light"}.'})

    bbw = ((close.rolling(20).mean() + 2 * close.rolling(20).std()) - (close.rolling(20).mean() - 2 * close.rolling(20).std())) / close.rolling(20).mean()
    bbw_pct = float((bbw.tail(180) < bbw.iloc[-1]).mean())
    if bbw_pct < 0.2:
        signals.append({'type': 'Volatility Compression', 'bias': 'Neutral',
                        'detail': f'Bollinger Band width is in the {round(bbw_pct*100)}th percentile — a squeeze that often precedes a large move.'})

    rsi_s = _rsi(close, 14)
    if len(lows) >= 2 and len(highs) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p2 < p1 and rsi_s.iloc[i2] > rsi_s.iloc[i1]:
            signals.append({'type': 'Bullish Momentum Divergence', 'bias': 'Bullish',
                            'detail': 'Price made a lower low while RSI made a higher low — waning downside momentum.'})
        (j1, q1), (j2, q2) = highs[-2], highs[-1]
        if q2 > q1 and rsi_s.iloc[j2] < rsi_s.iloc[j1]:
            signals.append({'type': 'Bearish Momentum Divergence', 'bias': 'Bearish',
                            'detail': 'Price made a higher high while RSI made a lower high — waning upside momentum.'})

    # last-candle pattern
    o1, c1, h1, l1 = float(d['open'].iloc[-1]), price, float(high.iloc[-1]), float(low.iloc[-1])
    o0, c0 = float(d['open'].iloc[-2]), float(close.iloc[-2])
    body = abs(c1 - o1); rng = max(h1 - l1, 1e-9); upper = h1 - max(c1, o1); lower = min(c1, o1) - l1
    pattern = None
    if c1 > o1 and c0 < o0 and c1 >= o0 and o1 <= c0:
        pattern = ('Bullish Engulfing', 'Bullish')
    elif c1 < o1 and c0 > o0 and o1 >= c0 and c1 <= o0:
        pattern = ('Bearish Engulfing', 'Bearish')
    elif lower > body * 2 and upper < body:
        pattern = ('Hammer', 'Bullish')
    elif upper > body * 2 and lower < body:
        pattern = ('Shooting Star', 'Bearish')
    elif body < rng * 0.1:
        pattern = ('Doji', 'Neutral')
    if pattern:
        signals.append({'type': f'Candlestick: {pattern[0]}', 'bias': pattern[1],
                        'detail': f'The latest daily candle printed a {pattern[0].lower()} pattern.'})

    # Predictive chart model: historical base rates over full df
    cf = df['close']
    up_break = cf > cf.rolling(20).max().shift(1)
    dn_break = cf < cf.rolling(20).min().shift(1)
    fwd5_up = cf.shift(-5) > cf
    bo_up = float(fwd5_up[up_break].mean()) if up_break.sum() > 5 else 0.5
    bo_dn = float((~fwd5_up)[dn_break].mean()) if dn_break.sum() > 5 else 0.5
    breakout_up = round(bo_up * 100, 1)
    breakdown = round(bo_dn * 100, 1)
    consolidation = round(max(0.0, 100 - breakout_up - breakdown), 1)
    near_res = res[0]['price'] if res else None
    near_sup = sup[0]['price'] if sup else None
    if price > hi20:
        primary = f'Fresh breakout above ${hi20:,.0f}. Historically {breakout_up}% of 20-day-high breakouts saw a higher close within 5 days.'
    elif near_res and (near_res - price) / price < 0.03:
        primary = f'Price is testing resistance near ${near_res:,.0f}. A 4h/daily close above it with volume would favour continuation.'
    elif near_sup and (price - near_sup) / price < 0.03:
        primary = f'Price is leaning on support near ${near_sup:,.0f}. Holding it keeps the structure intact.'
    else:
        primary = f'Price is mid-range between support (${near_sup:,.0f})' if near_sup else 'Price is in open air'
        primary += f' and resistance (${near_res:,.0f}).' if near_res else '.'

    ohlc = [{'t': r['timestamp'].strftime('%m/%d'),
             'o': round(float(r['open']), 0), 'h': round(float(r['high']), 0),
             'l': round(float(r['low']), 0), 'c': round(float(r['close']), 0)}
            for _, r in df.tail(90).iterrows()]

    return {
        'structure': structure, 'structure_bias': struct_bias,
        'signals': signals, 'sr_levels': sr_levels,
        'predictive': {'breakout_up': breakout_up, 'breakdown': breakdown,
                       'consolidation': consolidation, 'primary_setup': primary},
        'ohlc': ohlc,
        'range20': {'high': round(hi20, 0), 'low': round(lo20, 0)},
    }


def build_market_intel(quant, forecasts, cycle, dominance, chart):
    f24 = next((f for f in forecasts if f['horizon'] == '24H'), None)
    f7 = next((f for f in forecasts if f['horizon'] == '7D'), None)
    dom_txt = f"{dominance['direction']} ({dominance['dominance']}%)" if dominance else 'n/a'
    return {
        'quant_score': quant['quant_score'], 'quant_label': quant['quant_label'],
        'regime': quant['regime']['regime'],
        'higher_24h': f24['higher'] if f24 else None,
        'higher_7d': f7['higher'] if f7 else None,
        'confidence': f7['confidence'] if f7 else (f24['confidence'] if f24 else 'n/a'),
        'technical_structure': chart['structure'] if chart else 'n/a',
        'pressure_map': 'Awaiting data source (Glassnode)',
        'smart_money': 'Awaiting data source (Glassnode)',
        'exchange_supply': 'Awaiting data source (Glassnode)',
        'derivatives_risk': 'Awaiting data source (CoinGlass/CME)',
        'crowd': 'Awaiting data source (LunarCrush)',
        'hype_risk': 'Awaiting data source (LunarCrush)',
        'dominance': dom_txt,
        'cycle_phase': cycle['phase'] if cycle else 'n/a',
        'top_positive': quant['factors']['bullish'][0],
        'top_risk': quant['factors']['risk'][0],
    }


# =====================================================================
# CROSS-MARKET + POLICY & LIQUIDITY + ALERTS (keyless: Yahoo + curated)
# =====================================================================
def fetch_yahoo_series(symbol, rng='6mo'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={rng}'
    d = _http_json(url)['chart']['result'][0]
    ts = d['timestamp']; cl = d['indicators']['quote'][0]['close']
    s = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        s[datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')] = float(c)
    return pd.Series(s).sort_index()


CROSS_ASSETS = [('Nasdaq 100', '%5ENDX'), ('S&P 500', '%5EGSPC'), ('US Dollar (DXY)', 'DX-Y.NYB'),
                ('10Y Yield', '%5ETNX'), ('VIX', '%5EVIX'), ('Gold', 'GC=F')]


def compute_crossmarket():
    btc = fetch_yahoo_series('BTC-USD')
    btc_ret = np.log(btc / btc.shift(1))
    raw = {}; out = []
    for name, sym in CROSS_ASSETS:
        try:
            s = fetch_yahoo_series(sym); raw[name] = s
            r = np.log(s / s.shift(1))
            j = pd.concat([btc_ret, r], axis=1, keys=['b', 'a']).dropna()

            def corr(n):
                x = j.tail(n)
                return round(float(x['b'].corr(x['a'])), 2) if len(x) > 3 else None
            c30 = corr(30)
            beta = None
            x = j.tail(30)
            if len(x) > 3 and x['a'].var() > 0:
                beta = round(float(x['b'].cov(x['a']) / x['a'].var()), 2)
            ar = abs(c30 or 0)
            lab = ('Strong' if ar > 0.6 else 'Moderate' if ar > 0.3 else 'Weak') + (' Positive' if (c30 or 0) >= 0 else ' Negative')
            out.append({'asset': name, 'price': round(float(s.iloc[-1]), 2),
                        'corr_7d': corr(7), 'corr_30d': c30, 'corr_90d': corr(90),
                        'beta_30d': beta, 'label': lab})
        except Exception:  # noqa
            traceback.print_exc()
    return out, raw


CENTRAL_BANKS = [
    ('US Federal Reserve', '3.50–3.75%', 'Hold', '2026-07-29'),
    ('European Central Bank', '2.15%', 'Cut', '2026-06'),
    ('Bank of England', '3.75%', 'Cut', '2026-06'),
    ('Bank of Japan', '0.75%', 'Hold', '2026-07'),
    ('Reserve Bank of Australia', '3.35%', 'Cut', '2026-07'),
    ('Bank of Canada', '2.25%', 'Hold', '2026-06'),
    ("People's Bank of China", '2.90% (1Y LPR)', 'Hold', '2026-07'),
]
REG_EVENTS = [
    {'title': 'US spot Bitcoin ETFs', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Strong access-positive', 'note': 'Institutional access channel live and growing.'},
    {'title': 'EU MiCA framework', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'EU', 'impact': 'Certainty-positive', 'note': 'Fully applicable since 2024-12-30. Commission review during 2026 may amend.'},
    {'title': 'SEC SAB 122 (rescinds SAB 121)', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Access-positive', 'note': 'Removed the SEC accounting rule deterring bank custody (2025-01-30). Not a blanket authorisation — prudential/AML rules still apply.'},
    {'title': 'US CLARITY Act (market structure)', 'stage': 'Passed one chamber; Senate cmte reported', 'stage_num': 6, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Positive but UNCONFIRMED', 'note': 'Passed House Jul 2025; Senate Banking advanced May 2026; reported Jun 1 2026. PROPOSED legislation — not yet law.'},
]
POLICY_CALENDAR = [
    {'event': 'US CPI', 'date': '2026-08-12', 'importance': 'Very High', 'btc_sensitivity': 'High'},
    {'event': 'US PCE', 'date': '2026-08-28', 'importance': 'High', 'btc_sensitivity': 'Moderate'},
    {'event': 'US Nonfarm Payrolls', 'date': '2026-09-04', 'importance': 'High', 'btc_sensitivity': 'Moderate'},
    {'event': 'FOMC Rate Decision', 'date': '2026-09-16', 'importance': 'Very High', 'btc_sensitivity': 'High'},
]


def _zscore(series):
    s = series.dropna()
    if len(s) < 20:
        return 0.0
    return float((s.iloc[-1] - s.tail(90).mean()) / (s.tail(90).std() or 1))


def compute_policy(raw):
    dxy = raw.get('US Dollar (DXY)'); y10 = raw.get('10Y Yield'); vix = raw.get('VIX')
    dxy_z = _zscore(dxy) if dxy is not None else 0.0
    y10_z = _zscore(y10) if y10 is not None else 0.0
    vix_z = _zscore(vix) if vix is not None else 0.0
    impulse_z = float(np.mean([-dxy_z, -y10_z, -vix_z]))
    liq = round(max(0, min(100, 50 + impulse_z * 18)))
    liq_state = ('Strong Liquidity Expansion' if liq >= 80 else 'Moderate Expansion' if liq >= 65
                 else 'Neutral / Transitioning' if liq >= 45 else 'Moderate Contraction' if liq >= 30
                 else 'Strong Liquidity Contraction')
    monetary_path = 60          # Fed on hold, market pricing gradual cuts (curated)
    real_dollar = round(max(0, min(100, 50 - (dxy_z + y10_z) * 15)))
    banking_access = 68         # SAB122 + spot ETFs live (curated)
    reg_direction = 64          # net enacted-positive (MiCA, ETFs) vs proposed CLARITY (curated)
    legislative_certainty = 45  # CLARITY still proposed
    event_risk = 55
    score = round(liq * 0.25 + monetary_path * 0.20 + real_dollar * 0.15 + banking_access * 0.15
                  + reg_direction * 0.15 + legislative_certainty * 0.05 + event_risk * 0.05)
    label = ('Strongly Supportive' if score >= 80 else 'Moderately Supportive' if score >= 65
             else 'Mixed / Neutral' if score >= 45 else 'Moderately Restrictive' if score >= 30
             else 'Strongly Restrictive')
    return {
        'score': score, 'label': label,
        'liquidity_impulse': liq, 'liquidity_state': liq_state,
        'components': {'dxy_z': round(dxy_z, 2), 'y10_z': round(y10_z, 2), 'vix_z': round(vix_z, 2)},
        'dxy': round(float(dxy.iloc[-1]), 2) if dxy is not None else None,
        'y10': round(float(y10.iloc[-1]), 2) if y10 is not None else None,
        'vix': round(float(vix.iloc[-1]), 2) if vix is not None else None,
        'central_banks': [{'bank': b, 'rate': r, 'last': d2, 'date': dt} for b, r, d2, dt in CENTRAL_BANKS],
        'regulation': REG_EVENTS, 'calendar': POLICY_CALENDAR,
        'tailwind': 'Global liquidity is stabilising and institutional access (spot ETFs, post-SAB122 custody) is expanding.',
        'risk': 'Real yields and the dollar remain firm, and major US market-structure law (CLARITY Act) is still only proposed.',
        'interpretation': 'Policy conditions are constructive but not yet fully confirmed by capital flows.',
    }


def compute_alerts(quant, cycle, policy, chart, cm):
    a = []
    now = datetime.datetime.utcnow()
    ts = now.strftime('%Y-%m-%d %H:%M UTC')

    def add(level, typ, msg):
        a.append({'level': level, 'type': typ, 'message': msg, 'ts': ts})

    add('info', 'Regime', f"Market regime: {quant['regime']['regime']}. {quant['regime']['behavior']}")
    if policy:
        add('info', 'Liquidity', f"Global Liquidity Impulse {policy['liquidity_impulse']}/100 — {policy['liquidity_state']}. Policy & Liquidity Score {policy['score']} ({policy['label']}).")
        for e in policy['calendar']:
            try:
                days = (datetime.datetime.strptime(e['date'], '%Y-%m-%d').date() - now.date()).days
                if 0 <= days <= 10:
                    add('warning', 'Event Risk', f"{e['event']} in {days}d — {e['importance']} importance, BTC sensitivity {e['btc_sensitivity']}.")
            except Exception:  # noqa
                pass
    if chart:
        for s in chart['signals']:
            if s['type'].startswith('Breakout') or s['type'].startswith('Breakdown') or 'Divergence' in s['type']:
                add('danger' if s['bias'] == 'Bearish' else 'success', 'Chart', f"{s['type']}: {s['detail']}")
    if cm:
        nd = next((x for x in cm if x['asset'] == 'Nasdaq 100'), None)
        if nd and nd['corr_30d'] is not None and abs(nd['corr_30d']) > 0.6:
            add('info', 'Cross-Market', f"BTC–Nasdaq 30d correlation {nd['corr_30d']} ({nd['label']}) — equities currently carry more weight in the 24h/7d models.")
    return a


# =====================================================================
# BTC NEWS INTELLIGENCE (keyless RSS + Gemini 2.5 Flash summaries)
# =====================================================================
NEWS_SOURCES = [
    ('CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 72),
    ('Cointelegraph', 'https://cointelegraph.com/rss', 68),
    ('Bitcoin Magazine', 'https://bitcoinmagazine.com/feed', 68),
    ('Decrypt', 'https://decrypt.co/feed', 68),
    ('Federal Reserve', 'https://www.federalreserve.gov/feeds/press_all.xml', 95),
]
BTC_KEYWORDS = ['bitcoin', 'btc', 'crypto', 'ether', 'ethereum', 'sec', 'etf', 'federal reserve',
                'interest rate', 'rate cut', 'rate hike', 'inflation', 'cpi', 'stablecoin', 'coinbase',
                'binance', 'microstrategy', 'halving', 'mining', 'blackrock', 'custody', 'fomc',
                'monetary', 'open market', 'payroll', 'employment', 'treasury']

NEWS_SYSTEM = (
    "You are a Bitcoin market news analyst. Given a headline and article text, return ONLY one JSON "
    "object (no markdown, no prose) with EXACTLY these keys: "
    '{"summary": "2-sentence factual summary", "why_it_matters": "1-2 sentences on why it matters for Bitcoin", '
    '"direction": "bullish|bearish|mixed|neutral", "bullish_pct": int, "bearish_pct": int, "neutral_pct": int, '
    '"impact_score": int 0-100, "confidence": float 0-1, '
    '"time_horizons": {"immediate":"bullish|bearish|mixed|neutral","seven_day":"...","long_term":"..."}, '
    '"categories": ["one or more of: central_banks, inflation_employment, regulation, etf, institutional_adoption, '
    'corporate_holdings, exchange_custody, security_breach, mining_network, stablecoins, whale_onchain, derivatives, '
    'geopolitics, technology_protocol, social_sentiment, rumor"]}. '
    "Rules: bullish_pct+bearish_pct+neutral_pct MUST sum to 100. Only use the provided material; never invent facts "
    "or quotes. If the story is not Bitcoin-relevant, set direction neutral and a low impact_score. "
    "Keep 'summary' under 40 words and 'why_it_matters' under 35 words. Output compact valid JSON only."
)


def generate_news_summary(headline, text):
    chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f'news-{abs(hash(headline)) % 99999}',
                    system_message=NEWS_SYSTEM)
            .with_model('gemini', GEMINI_MODEL)
            .with_params(temperature=0.0, max_tokens=1200))
    reply = asyncio.run(chat.send_message(UserMessage(text=f'Headline: {headline}\n\nArticle:\n{text[:4000]}')))
    raw = (getattr(reply, 'text', None) or str(reply)).strip()
    if '```' in raw:
        raw = re.sub(r'```(?:json)?', '', raw).strip()
    s, e = raw.find('{'), raw.rfind('}')
    obj = json.loads(raw[s:e + 1])
    return obj


def _norm_title(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())[:45]


def fetch_news():
    entries = []
    for name, url, cred in NEWS_SOURCES:
        try:
            fp = feedparser.parse(url)
            for e in fp.entries[:12]:
                title = e.get('title', '')
                summ = re.sub('<[^>]+>', '', e.get('summary', e.get('description', '')))[:1400]
                blob = (title + ' ' + summ).lower()
                if name != 'Federal Reserve' and not any(k in blob for k in BTC_KEYWORDS):
                    continue
                entries.append({'source': name, 'credibility': cred, 'title': title,
                                'summary': summ.strip(), 'link': e.get('link', ''),
                                'published': e.get('published', e.get('updated', ''))})
        except Exception:  # noqa
            traceback.print_exc()

    # --- Cluster near-duplicate stories across sources into one story each ---
    def _toks(t):
        stop = {'the', 'a', 'an', 'to', 'of', 'in', 'on', 'for', 'and', 'is', 'as', 'at',
                'by', 'it', 'be', 'with', 'from', 'that', 'this', 'its', 'are', 'will', 'has'}
        return set(w for w in re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower()).split()
                   if len(w) > 2 and w not in stop)

    clusters = []
    for e in entries:
        et = _toks(e['title'])
        if not et:
            continue
        placed = False
        for cl in clusters:
            inter = len(et & cl['tokens'])
            union = len(et | cl['tokens']) or 1
            if inter / union >= 0.34 or (inter >= 3 and inter >= 0.6 * min(len(et), len(cl['tokens']))):
                cl['members'].append(e)
                cl['tokens'] |= et
                placed = True
                break
        if not placed:
            clusters.append({'tokens': set(et), 'members': [e]})

    clusters.sort(key=lambda cl: (-len(set(m['source'] for m in cl['members'])),
                                  -max(m['credibility'] for m in cl['members'])))
    clusters = clusters[:8]

    SPEC_WORDS = ('rumor', 'rumour', 'reportedly', 'could ', 'may ', 'might', 'proposal',
                  'proposed', 'unconfirmed', 'alleged', 'speculat', 'plans to', 'considering',
                  'reports', 'said to', 'expected to')

    cards = []
    for cl in clusters:
        members = cl['members']
        rep = max(members, key=lambda m: m['credibility'])
        sources = [{'source': m['source'], 'link': m['link'], 'credibility': m['credibility'],
                    'published': m['published'], 'title': m['title']} for m in members]
        n_src = len(set(m['source'] for m in members))
        ai = None
        if EMERGENT_LLM_KEY and _HAS_LLM:
            try:
                ai = generate_news_summary(rep['title'], rep['summary'] or rep['title'])
            except Exception:  # noqa
                traceback.print_exc()
        if not ai:
            ai = {'summary': (rep['summary'] or rep['title'])[:220], 'why_it_matters': '',
                  'direction': 'neutral', 'bullish_pct': 40, 'bearish_pct': 30, 'neutral_pct': 30,
                  'impact_score': 40, 'confidence': 0.4,
                  'time_horizons': {'immediate': 'neutral', 'seven_day': 'neutral', 'long_term': 'neutral'},
                  'categories': ['general']}
        try:
            imp = int(round(float(ai.get('impact_score', 40)) * (0.55 + 0.45 * rep['credibility'] / 100)))
        except Exception:  # noqa
            imp = 40
        imp = max(0, min(100, imp))
        imp_label = ('Market Moving' if imp >= 85 else 'High Impact' if imp >= 70 else 'Important'
                     if imp >= 50 else 'Monitor' if imp >= 30 else 'Low Significance')
        # Confirmed vs unconfirmed
        blob = (rep['title'] + ' ' + (rep['summary'] or '')).lower()
        speculative = any(w in blob for w in SPEC_WORDS)
        max_cred = max(m['credibility'] for m in members)
        if n_src >= 2 and max_cred >= 65 and not speculative:
            verification = 'Confirmed'
        elif speculative or max_cred < 55:
            verification = 'Unconfirmed'
        else:
            verification = 'Single-source'
        # Per-story forecast impact (model interpretation, honest & bounded)
        dirn = ai.get('direction', 'neutral')
        sign = 1 if dirn == 'bullish' else -1 if dirn == 'bearish' else 0
        nudge = round(sign * imp / 100 * 3.0, 1)
        forecast_impact = {
            'direction': dirn, 'nudge_pts': nudge,
            'horizons': ['24H', '7D'] if imp >= 50 else ['24H'],
            'note': (f'Nudges near-term higher-odds by {"+" if nudge > 0 else ""}{nudge} pts'
                     if nudge else 'No material push to the near-term odds') + ' (model interpretation).',
        }
        cards.append({**rep, 'ai': ai, 'impact': imp, 'impact_label': imp_label,
                      'sources': sources, 'n_sources': n_src,
                      'verification': verification, 'forecast_impact': forecast_impact})
    cards.sort(key=lambda c: -c['impact'])

    bull = sum(1 for c in cards if c['ai'].get('direction') == 'bullish')
    bear = sum(1 for c in cards if c['ai'].get('direction') == 'bearish')
    bias = 'Moderately Bullish' if bull > bear else 'Moderately Bearish' if bear > bull else 'Mixed / Neutral'
    tail = next((c for c in cards if c['ai'].get('direction') == 'bullish'), None)
    risk = next((c for c in cards if c['ai'].get('direction') == 'bearish'), None)
    briefing = {
        'bias': bias, 'total': len(cards),
        'major_stories': sum(1 for c in cards if c['impact'] >= 70),
        'market_moving': sum(1 for c in cards if c['impact'] >= 85),
        'top_tailwind': (tail['ai'].get('why_it_matters') or tail['title']) if tail else 'No clear bullish catalyst in the current feed.',
        'top_risk': (risk['ai'].get('why_it_matters') or risk['title']) if risk else 'No clear bearish catalyst in the current feed.',
        'next_event': POLICY_CALENDAR[0] if POLICY_CALENDAR else None,
    }
    doc = {'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
           'cards': cards, 'briefing': briefing,
           'model': (GEMINI_MODEL if (EMERGENT_LLM_KEY and _HAS_LLM) else 'rule-based')}
    try:
        fire_news_alerts(cards)
    except Exception:  # noqa
        traceback.print_exc()
    news_col.delete_many({})
    news_col.insert_one({**doc, '_id': doc['id']})
    return doc


def fire_news_alerts(cards):
    """Turn each Confirmed, high-impact story into a Smart Alert (once ever, per story)."""
    as_of = datetime.date.today().isoformat()
    now_iso = datetime.datetime.utcnow().isoformat()
    for c in cards:
        # Fire for corroborated OR single-source stories (skip clearly speculative/unconfirmed),
        # with a slightly looser impact bar so meaningful news reliably surfaces as an alert.
        if c.get('verification') == 'Unconfirmed' or int(c.get('impact', 0) or 0) < 60:
            continue
        key = 'news_' + _norm_title(c.get('title', ''))
        if not key or key == 'news_':
            continue
        fi = c.get('forecast_impact') or {}
        why = (c.get('ai') or {}).get('why_it_matters') or (c.get('ai') or {}).get('summary') or ''
        sev = 'high' if int(c.get('impact', 0)) >= 85 else 'warning'
        msg = f"{why} Effect on BitMarkAI forecast: {fi.get('note', 'neutral')}".strip()
        try:
            smart_alerts_col.update_one(
                {'_id': key},
                {'$setOnInsert': {
                    '_id': key, 'id': key, 'ts': now_iso, 'as_of': as_of,
                    'category': 'News', 'severity': sev,
                    'title': c.get('title', 'High-impact story')[:120],
                    'message': msg[:400], 'seen': False,
                    'link': c.get('link'), 'impact': int(c.get('impact', 0)),
                    'forecast_nudge': fi.get('nudge_pts'),
                }}, upsert=True)
        except Exception:  # noqa
            traceback.print_exc()


_news_state = {'status': 'idle', 'error': None}


def run_news_bg():
    if _news_state['status'] == 'running':
        return
    _news_state['status'] = 'running'
    _news_state['error'] = None
    try:
        fetch_news()
        _news_state['status'] = 'done'
    except Exception as ex:  # noqa
        _news_state['status'] = 'error'
        _news_state['error'] = str(ex)
        traceback.print_exc()


# =====================================================================
# STEP 3-5: TARGET, CV, WALK-FORWARD BACKTEST, LIVE SIGNAL
# =====================================================================
def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _quant_score_label(s):
    if s >= 80: return 'Strongly Bullish'
    if s >= 60: return 'Moderately Bullish'
    if s >= 55: return 'Weakly Bullish'
    if s > 45:  return 'Neutral'
    if s > 40:  return 'Weakly Bearish'
    if s > 20:  return 'Bearish'
    return 'Strongly Bearish'


def _sig_word(s):
    if s >= 58: return 'Bullish'
    if s <= 42: return 'Bearish'
    return 'Neutral'


def _horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts, light=False):
    """Train a horizon-specific RandomForest and project bull/base/bear ranges.
    light=True skips SHAP contributions (used for long-horizon outlooks to save compute)."""
    n = len(Xfull)
    y_h = (close.shift(-h) > close).astype(int)
    Xv = Xfull.iloc[:n - h]
    yv = y_h.iloc[:n - h]
    # backtest accuracy via time-series split
    accs = []
    try:
        tscv = TimeSeriesSplit(n_splits=3)
        for tr, te in tscv.split(Xv):
            m = RandomForestClassifier(n_estimators=120, max_depth=5, random_state=42, n_jobs=-1)
            m.fit(Xv.iloc[tr], yv.iloc[tr])
            accs.append(accuracy_score(yv.iloc[te], m.predict(Xv.iloc[te])))
    except Exception:  # noqa
        accs = [0.5]
    acc = float(np.mean(accs)) if accs else 0.5
    # final model -> live probability
    fm = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
    fm.fit(Xv, yv)
    cl = list(fm.classes_)
    pr = fm.predict_proba(live_X)[0]
    p_up = float(pr[cl.index(1)]) if 1 in cl else 0.0

    # SHAP factor contributions for the live prediction (probability space, class = up)
    contributions = []
    if _HAS_SHAP and not light:
        try:
            expl = shap.TreeExplainer(fm)
            sv = expl.shap_values(live_X)
            arr = None
            if isinstance(sv, list):
                arr = np.array(sv[1][0]) if len(sv) > 1 else np.array(sv[0][0])
            else:
                a = np.array(sv)
                arr = a[0, :, 1] if (a.ndim == 3 and a.shape[2] > 1) else (a[0, :, 0] if a.ndim == 3 else a[0])
            for f, val in zip(FEATURE_COLS, arr):
                contributions.append({'feature': f, 'label': FEATURE_META[f]['label'],
                                      'category': FEATURE_META[f]['category'],
                                      'contribution': round(float(val) * 100, 2)})
            contributions.sort(key=lambda z: -abs(z['contribution']))
        except Exception:  # noqa
            contributions = []
    higher = round(p_up * 100, 1)
    lower = round(100 - higher, 1)
    if light:
        # Long-horizon directional models are close to a coin-flip; shrink the displayed
        # probability toward 50% by the realised backtest edge so it is not over-confident.
        edge = max(0.0, (acc - 0.5)) * 2          # 0..1
        weight = min(1.0, 0.25 + edge)            # never fully trusted; floor 0.25
        p_disp = 0.5 + (p_up - 0.5) * weight
        higher = round(p_disp * 100, 1)
        lower = round(100 - higher, 1)
    # scenario ranges from drift + volatility scaled by sqrt(horizon)
    drift = mu * h
    vol = sigma * math.sqrt(h)
    base = price * math.exp(drift)
    bull = price * math.exp(drift + vol)
    bear = price * math.exp(drift - vol)
    exp_low = price * math.exp(drift - 0.5 * vol)
    exp_high = price * math.exp(drift + 0.5 * vol)
    # confidence from probability margin + realised backtest edge
    margin = abs(p_up - 0.5) * 2
    conf_val = margin * 0.6 + max(0.0, (acc - 0.5)) * 2 * 0.4
    conf_label = 'High' if conf_val > 0.45 else ('Moderate' if conf_val > 0.2 else 'Low')
    bullish_lean = higher >= lower
    invalidation = bear if bullish_lean else bull
    label = {1: '24H', 7: '7D', 30: '30D', 90: '3M', 180: '6M', 365: '1Y'}.get(h, f'{h}D')
    return {
        'horizon': label, 'days': h,
        'higher': higher, 'lower': lower,
        'expected_low': round(exp_low, 0), 'expected_high': round(exp_high, 0),
        'bull': round(bull, 0), 'base': round(base, 0), 'bear': round(bear, 0),
        'confidence': conf_label, 'confidence_pct': round(conf_val * 100, 0),
        'accuracy': round(acc * 100, 1),
        'invalidation': round(invalidation, 0),
        'invalidation_dir': 'below' if bullish_lean else 'above',
        'lean': 'UP' if bullish_lean else 'DOWN',
        'expiry': (as_of_ts + pd.Timedelta(days=h)).strftime('%Y-%m-%d'),
        'contributions': contributions,
    }


def compute_quant_analysis(df, feats, price, as_of_ts):
    close = df['close']
    logret = np.log(close / close.shift(1)).dropna()
    recent = logret.tail(90)
    mu = float(recent.mean()) if len(recent) else 0.0
    sigma = float(recent.std()) if len(recent) else 0.02

    # --- Category sub-scores (0-100, higher = more constructive) ---
    ema_ratio = float(feats['EMA_Ratio'])
    macd = float(feats['MACD_Hist_Norm'])
    rsi = float(feats['RSI']) * 100
    stoch = float(feats['StochRSI']) * 100
    vz = float(feats['Volume_Z'])
    vr = float(feats['Volume_Ratio'])
    atr_now = float(feats['ATR_Pct'])
    atr_series = df['ATR_Pct'].tail(365)
    atr_pct = float((atr_series < atr_now).mean()) if len(atr_series) else 0.5

    trend_score = _clamp(50 + 50 * math.tanh((ema_ratio / 0.02) * 0.6 + (macd / 0.004) * 0.4))
    momentum_score = _clamp(0.6 * rsi + 0.4 * stoch)
    volume_score = _clamp(50 + 50 * math.tanh(vz / 1.5))
    volatility_score = _clamp(100 * (1 - atr_pct))

    weights = {'Trend': 0.35, 'Momentum': 0.30, 'Volume': 0.20, 'Volatility': 0.15}
    scores = {'Trend': trend_score, 'Momentum': momentum_score,
              'Volume': volume_score, 'Volatility': volatility_score}
    quant = round(sum(scores[k] * weights[k] for k in weights))

    breakdown = [
        {'name': 'Trend', 'score': round(trend_score), 'weight': int(weights['Trend'] * 100),
         'signal': _sig_word(trend_score), 'active': True,
         'note': f"EMA 9/21 spread {round(ema_ratio*100,2)}%, MACD histogram {round(macd*100,3)}%"},
        {'name': 'Momentum', 'score': round(momentum_score), 'weight': int(weights['Momentum'] * 100),
         'signal': _sig_word(momentum_score), 'active': True,
         'note': f"RSI {round(rsi,1)}, Stochastic RSI {round(stoch,1)}"},
        {'name': 'Volume', 'score': round(volume_score), 'weight': int(weights['Volume'] * 100),
         'signal': _sig_word(volume_score), 'active': True,
         'note': f"Volume {round(vr,2)}x the 20-day norm (z {round(vz,2)})"},
        {'name': 'Volatility', 'score': round(volatility_score), 'weight': int(weights['Volatility'] * 100),
         'signal': 'Calm' if volatility_score >= 55 else ('Elevated' if volatility_score <= 40 else 'Normal'),
         'active': True,
         'note': f"ATR {round(atr_now*100,2)}% ({round(atr_pct*100)}th percentile of the last year)"},
        {'name': 'Derivatives', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires a derivatives data source (funding, OI, basis)'},
        {'name': 'Liquidity', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires order-book / exchange liquidity data'},
        {'name': 'On-chain', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires an on-chain provider (Glassnode / CryptoQuant)'},
        {'name': 'Sentiment', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires a social / news sentiment feed'},
        {'name': 'Macro', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires macro data (DXY, rates, risk assets)'},
    ]

    # --- Market Regime Engine ---
    ema9 = _ema(close, 9); ema21 = _ema(close, 21); ema50 = _ema(close, 50)
    slope50 = float(ema50.iloc[-1] / ema50.iloc[-11] - 1) if len(ema50) > 11 else 0.0
    slope30 = float(close.iloc[-1] / close.iloc[-31] - 1) if len(close) > 31 else 0.0
    slope60 = float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else 0.0
    up_align = ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]
    down_align = ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]
    rng20 = float((close.tail(20).max() - close.tail(20).min()) / close.iloc[-1])
    vol_shock = atr_pct > 0.92

    if vol_shock:
        regime = 'Volatility Shock'
        regime_desc = 'Volatility is in the top decile of the past year — expect wide, erratic swings.'
        behavior = 'The engine widens risk bounds and lowers position conviction until volatility normalises.'
    elif up_align and slope30 > 0.08 and slope50 > 0.03:
        regime = 'Strong Bullish Trend'
        regime_desc = 'Price is above rising short/medium-term averages with strong upward slope.'
        behavior = 'The model favours trend-continuation and treats dips as higher-probability longs.'
    elif up_align or (slope30 > 0.02 and ema9.iloc[-1] > ema21.iloc[-1]):
        regime = 'Weak Bullish Trend'
        regime_desc = 'A mild uptrend with modest momentum and shallow slope.'
        behavior = 'The model leans bullish but keeps conviction moderate.'
    elif down_align and slope30 < -0.08 and slope50 < -0.03:
        regime = 'Strong Bearish Trend'
        regime_desc = 'Price is below falling averages with a steep downward slope.'
        behavior = 'The model avoids longs and treats rallies as lower-probability.'
    elif down_align or (slope30 < -0.02 and ema9.iloc[-1] < ema21.iloc[-1]):
        regime = 'Weak Bearish Trend'
        regime_desc = 'A mild downtrend with soft momentum.'
        behavior = 'The model leans bearish with moderate conviction.'
    elif rng20 < 0.08 and slope60 < -0.05:
        regime = 'Accumulation'
        regime_desc = 'Price is basing in a tight range after a decline, with stabilising volume.'
        behavior = 'The model watches for a breakout and treats the base as support.'
    elif rng20 < 0.08 and slope60 > 0.05:
        regime = 'Distribution'
        regime_desc = 'Price is stalling in a tight range after a rally — momentum is fading.'
        behavior = 'The model turns cautious and flags reversal risk.'
    else:
        regime = 'Consolidation'
        regime_desc = 'Range-bound price with flat moving averages and no dominant trend.'
        behavior = 'The model reduces directional conviction and waits for a break.'

    regime_obj = {'regime': regime, 'description': regime_desc, 'behavior': behavior,
                  'trend30d_pct': round(slope30 * 100, 1), 'vol_percentile': round(atr_pct * 100)}

    # --- Multi-horizon probability forecasts ---
    Xfull = df[FEATURE_COLS]
    live_X = Xfull.iloc[[-1]]
    forecasts = []
    for h in [1, 7, 30]:
        try:
            forecasts.append(_horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts))
        except Exception:  # noqa
            traceback.print_exc()
    # --- Long-horizon outlooks (1M/3M/6M/1Y) — lighter (no SHAP) for the Decision Engine ---
    long_outlook = []
    for h in [90, 180, 365]:
        try:
            long_outlook.append(_horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts, light=True))
        except Exception:  # noqa
            traceback.print_exc()

    # --- Explainable factors: top bullish + top risk ---
    bulls, risks = [], []
    if trend_score >= 58:
        bulls.append((trend_score - 50, f"Price is trading above its short/medium-term trend (EMA 9 > 21) with a {'positive' if macd>=0 else 'improving'} MACD histogram."))
    elif trend_score <= 42:
        risks.append((50 - trend_score, "Trend is bearish — price sits below key moving averages with a negative MACD histogram."))
    if 55 <= rsi < 72:
        bulls.append((rsi - 50, f"Momentum is constructive with RSI at {round(rsi,1)} and no overbought stress yet."))
    elif rsi >= 72:
        risks.append((rsi - 50, f"RSI is overbought at {round(rsi,1)} — elevated risk of a near-term pullback."))
    elif rsi < 45:
        risks.append((50 - rsi, f"Momentum is weak with RSI at {round(rsi,1)}, below the neutral line."))
    if vz >= 0.5:
        bulls.append((vz * 20, f"Volume is running {round(vr,2)}x its 20-day average, confirming participation behind the move."))
    elif vz <= -0.5:
        risks.append((abs(vz) * 20, f"Volume is below normal ({round(vr,2)}x) — the current move lacks conviction."))
    if atr_pct >= 0.8:
        risks.append((atr_pct * 30, f"Volatility is elevated (ATR at the {round(atr_pct*100)}th percentile), widening the risk bounds."))
    elif atr_pct <= 0.3:
        bulls.append((30 * (0.3 - atr_pct) + 5, "Volatility is subdued, a historically constructive backdrop for steady moves."))
    if stoch >= 80:
        risks.append((stoch - 60, "Stochastic RSI is stretched near the top of its band — short-term exhaustion risk."))
    elif stoch <= 20:
        bulls.append((30, "Stochastic RSI is oversold, a common spot for local reversals higher."))

    bulls = [b[1] for b in sorted(bulls, key=lambda z: -z[0])][:3]
    risks = [r[1] for r in sorted(risks, key=lambda z: -z[0])][:3]
    if not bulls:
        bulls = ["No strong bullish factors right now — signals are mixed to neutral."]
    if not risks:
        risks = ["No major risk factors flagged — conditions look relatively balanced."]

    return {
        'quant_score': int(quant),
        'quant_label': _quant_score_label(quant),
        'quant_breakdown': breakdown,
        'regime': regime_obj,
        'forecasts': forecasts,
        'long_outlook': long_outlook,
        'factors': {'bullish': bulls, 'risk': risks},
    }


# =====================================================================
# NEWS → FORECAST LINK + UNIFIED DECISION ENGINE + ASK-QUANT CONTEXT
# =====================================================================
def compute_news_signal(news_doc):
    """Turn the latest BTC news cards into an impact-weighted directional signal in [-1, 1]."""
    if not news_doc:
        return None
    cards = news_doc.get('cards', []) or []
    if not cards:
        return None
    num = den = 0.0
    drivers = []
    for c in cards:
        d = (c.get('ai') or {}).get('direction')
        imp = float(c.get('impact', 0) or 0)
        val = 1 if d == 'bullish' else (-1 if d == 'bearish' else 0)
        w = imp / 100.0
        num += val * w
        den += w
        if imp >= 55 and val != 0:
            drivers.append((imp, val, c.get('title', '')))
    signal = round((num / den), 3) if den else 0.0
    drivers.sort(key=lambda z: -z[0])
    top = drivers[0] if drivers else None
    bias = 'Bullish' if signal > 0.12 else ('Bearish' if signal < -0.12 else 'Neutral')
    return {
        'signal': signal, 'bias': bias,
        'n_high_impact': sum(1 for c in cards if float(c.get('impact', 0) or 0) >= 70),
        'n_stories': len(cards),
        'top_driver': (top[2] if top else None),
        'top_driver_dir': ('bullish' if top and top[1] > 0 else ('bearish' if top else None)),
        'model_bias': news_doc.get('briefing', {}).get('bias'),
    }


def apply_news_link(forecasts, news_sig):
    """Nudge the 24H/7D probabilities with the news signal and attach before/after data."""
    if not news_sig:
        return None
    K = {'24H': 7.0, '7D': 4.5}  # news matters more on shorter horizons
    applied = []
    for f in forecasts:
        k = K.get(f['horizon'])
        if not k:
            continue
        base = float(f['higher'])
        raw_adj = news_sig['signal'] * k
        adj = round(max(-8.0, min(8.0, raw_adj)), 1)
        newh = round(max(2.0, min(98.0, base + adj)), 1)
        f['news_link'] = {
            'applied': True, 'higher_base': round(base, 1), 'higher_adj': newh,
            'lower_base': round(100 - base, 1), 'lower_adj': round(100 - newh, 1),
            'delta': round(newh - base, 1), 'bias': news_sig['bias'],
            'signal': news_sig['signal'], 'top_driver': news_sig['top_driver'],
        }
        f['higher_adj'] = newh
        f['lower_adj'] = round(100 - newh, 1)
        applied.append({'horizon': f['horizon'], 'base': round(base, 1),
                        'adj': newh, 'delta': round(newh - base, 1)})
    return {
        'signal': news_sig['signal'], 'bias': news_sig['bias'],
        'n_high_impact': news_sig['n_high_impact'], 'n_stories': news_sig['n_stories'],
        'top_driver': news_sig['top_driver'], 'top_driver_dir': news_sig['top_driver_dir'],
        'model_bias': news_sig['model_bias'], 'applied': applied,
    }


OUTLOOK_LABELS = {'24H': 'Next 24 Hours', '7D': 'Next 7 Days', '30D': 'Next Month',
                  '3M': 'Next 3 Months', '6M': 'Next 6 Months', '1Y': 'Next Year'}


def compute_decision_engine(quant, all_outlook, policy, news_sig, chart, cycle, dominance):
    """Reconcile technicals, macro/policy, news and chart into one Bitcoin Market State."""
    tech = int(quant['quant_score'])
    pol = int(policy['score']) if policy else 50
    news_score = int(round(50 + (news_sig['signal'] * 30))) if news_sig else 50
    news_score = max(0, min(100, news_score))
    chart_bias = chart['structure_bias'] if chart else 'Neutral'
    chart_score = 70 if chart_bias == 'Bullish' else (30 if chart_bias == 'Bearish' else 50)

    overall = int(round(tech * 0.45 + pol * 0.20 + news_score * 0.15 + chart_score * 0.20))
    overall = max(0, min(100, overall))
    label = _quant_score_label(overall)

    comps = [
        {'name': 'Technicals', 'score': tech, 'weight': 45},
        {'name': 'Macro / Policy', 'score': pol, 'weight': 20},
        {'name': 'Chart Structure', 'score': chart_score, 'weight': 20},
        {'name': 'News Flow', 'score': news_score, 'weight': 15},
    ]
    bull = sum(1 for c in comps if c['score'] >= 55)
    bear = sum(1 for c in comps if c['score'] <= 45)
    if bull >= 3:
        alignment = 'Strong Agreement · Bullish'
    elif bear >= 3:
        alignment = 'Strong Agreement · Bearish'
    elif bull and bear:
        alignment = 'Conflicting Signals'
    else:
        alignment = 'Mixed / Neutral'

    # --- Risk level (distinct from directional score) ---
    vol_pct = float(quant['regime'].get('vol_percentile', 50) or 50)
    event_risk = 0
    now = datetime.datetime.utcnow().date()
    if policy:
        for e in policy.get('calendar', []):
            try:
                days = (datetime.datetime.strptime(e['date'], '%Y-%m-%d').date() - now).days
                if 0 <= days <= 3 and e.get('importance') == 'Very High':
                    event_risk = max(event_risk, 28)
                elif 0 <= days <= 7:
                    event_risk = max(event_risk, 16)
            except Exception:  # noqa
                pass
    news_risk = 0
    if news_sig and news_sig['bias'] == 'Bearish' and news_sig['n_high_impact'] >= 1:
        news_risk = 12
    risk_score = int(round(min(100, vol_pct * 0.6 + event_risk + news_risk)))
    risk_level = ('Extreme' if risk_score >= 80 else 'High' if risk_score >= 60
                  else 'Elevated' if risk_score >= 45 else 'Moderate' if risk_score >= 30 else 'Low')

    # --- Outlook table across every horizon (24H → 1Y) ---
    outlook = []
    for f in all_outlook:
        h = float(f.get('higher_adj', f['higher']))
        outlook.append({
            'horizon': f['horizon'], 'label': OUTLOOK_LABELS.get(f['horizon'], f['horizon']),
            'higher': round(h, 1), 'lower': round(100 - h, 1),
            'lean': 'UP' if h >= 50 else 'DOWN',
            'confidence': f.get('confidence', 'Low'), 'accuracy': f.get('accuracy'),
            'base': f.get('base'), 'bull': f.get('bull'), 'bear': f.get('bear'),
            'expiry': f.get('expiry'), 'news_adjusted': 'news_link' in f,
        })

    def _out(h):
        return next((o for o in outlook if o['horizon'] == h), None)
    o24, o7, o1m, o1y = _out('24H'), _out('7D'), _out('30D'), _out('1Y')

    def lean_txt(o):
        if not o:
            return 'unclear'
        return f"{'higher' if o['lean'] == 'UP' else 'lower'} ({max(o['higher'], o['lower'])}%)"

    regime = quant['regime']['regime']
    dom_txt = f"BTC dominance is {dominance['dominance']}% ({dominance['direction'].lower()}). " if dominance else ''
    cyc_txt = f"The halving cycle is ~{cycle['cycle_progress_pct']}% complete ({cycle['phase']}). " if cycle else ''
    news_txt = ''
    if news_sig:
        news_txt = f"News flow is {news_sig['bias'].lower()}"
        if news_sig.get('top_driver'):
            news_txt += f" (biggest driver: \"{news_sig['top_driver']}\")"
        news_txt += '. '
    summary = (
        f"Bitcoin's unified market state is {label} with an overall conviction score of {overall}/100. "
        f"The market is in a '{regime}' regime. {quant['regime']['description']} "
        f"Technicals ({tech}/100), macro & policy ({pol}/100), chart structure ({chart_bias.lower()}) and news flow "
        f"({news_score}/100) are showing {alignment.lower()}. {news_txt}{dom_txt}{cyc_txt}"
        f"Near term, the engine leans {lean_txt(o24)} over 24h and {lean_txt(o7)} over 7 days; "
        f"the longer-term view leans {lean_txt(o1m)} over the next month and {lean_txt(o1y)} over the next year. "
        f"Overall risk is currently {risk_level}. Treat every figure as probabilities, not certainties — not financial advice."
    )

    return {
        'overall_score': overall, 'label': label, 'regime': regime,
        'regime_description': quant['regime']['description'],
        'alignment': alignment, 'components': comps,
        'risk_level': risk_level, 'risk_score': risk_score,
        'risk_drivers': {'volatility_percentile': round(vol_pct), 'event_risk': event_risk,
                         'news_risk': news_risk},
        'outlook': outlook, 'summary': summary,
        'news_signal': (news_sig['signal'] if news_sig else None),
        'news_bias': (news_sig['bias'] if news_sig else None),
    }


# ---------------------------- Risk Engine ----------------------------
def _risk_state(score):
    return ('Extreme' if score >= 80 else 'High' if score >= 60
            else 'Elevated' if score >= 45 else 'Normal' if score >= 25 else 'Low')


def compute_risk_engine(quant, chart, decision, data_health, event_calendar, last_close, feats):
    """Dedicated risk view — direction-agnostic. Real where we have data; illustrative
    DEMO values (clearly flagged) for feeds that need paid keys (IV, leverage, order book)."""
    import math as _m
    atr_now = float(feats.get('ATR_Pct', 0.03) or 0.03)          # daily realised range fraction
    vol_pct = float(quant['regime'].get('vol_percentile', 50) or 50)
    level = (decision or {}).get('risk_level', _risk_state(round(vol_pct)))
    score = int((decision or {}).get('risk_score', round(vol_pct)))

    # Expected move (real, from ATR scaled by sqrt(time))
    def _band(days):
        mv = atr_now * _m.sqrt(days)
        return {'pct': round(mv * 100, 1),
                'low': round(last_close * (1 - mv), 0), 'high': round(last_close * (1 + mv), 0)}
    expected_move = {'24H': _band(1), '7D': _band(7), '30D': _band(30)}

    # Support / resistance zones (real, from chart intelligence)
    sr = (chart or {}).get('sr_levels', []) or []
    sup = sorted([l for l in sr if l['type'] == 'support' and l['price'] < last_close],
                 key=lambda z: last_close - z['price'])
    res = sorted([l for l in sr if l['type'] == 'resistance' and l['price'] > last_close],
                 key=lambda z: z['price'] - last_close)
    downside_zone = ({'price': sup[0]['price'], 'distance_pct': round((last_close - sup[0]['price']) / last_close * 100, 1),
                      'label': 'Primary support'} if sup else None)
    upside_zone = ({'price': res[0]['price'], 'distance_pct': round((res[0]['price'] - last_close) / last_close * 100, 1),
                    'label': 'Primary resistance'} if res else None)

    # Macro-event risk (real, from event calendar)
    nhi = (event_calendar or {}).get('next_high_impact')
    macro_event_risk = 'Low'
    macro_note = 'No high-impact events in the near window.'
    if nhi and nhi.get('days_until') is not None:
        du = nhi['days_until']
        macro_event_risk = 'High' if du <= 2 else 'Elevated' if du <= 7 else 'Normal'
        macro_note = f"{nhi.get('title')} in {du}d ({nhi.get('importance')} importance)."

    # Data uncertainty (real, from data health)
    dh_level = (data_health or {}).get('level', 'High')
    dh_score = (data_health or {}).get('score', 95)
    data_uncertainty = 'Low' if dh_score >= 90 else 'Normal' if dh_score >= 75 else 'Elevated' if dh_score >= 55 else 'High'

    # Realised vol (real percentile) -> annualised estimate
    realised_vol_annual = round(atr_now * _m.sqrt(365) * 100, 0)

    # ----- DEMO metrics (need paid feeds; clearly flagged) -----
    seed = int(last_close) % 100
    demo = {
        'implied_vol': {'value': round(realised_vol_annual + 8 + seed % 12, 0), 'unit': '% annualised',
                        'state': 'Elevated', 'demo': True, 'source': 'Deribit/CME (needs key)'},
        'leverage_risk': {'state': ['Normal', 'Elevated', 'High'][seed % 3], 'funding_bps': round((seed % 20) - 5, 1),
                          'demo': True, 'source': 'CoinGlass (needs key)'},
        'liquidation_risk': {'state': ['Normal', 'Elevated', 'High'][(seed + 1) % 3],
                             'nearest_cluster_pct': round(2 + seed % 4, 1), 'demo': True, 'source': 'CoinGlass (needs key)'},
        'orderbook_liquidity': {'state': ['Deep', 'Normal', 'Thin'][seed % 3], 'depth_2pct_musd': round(120 + seed, 0),
                                'demo': True, 'source': 'Exchange L2 (needs key)'},
    }

    drivers = [
        {'name': 'Realised volatility', 'state': _risk_state(round(vol_pct)), 'value': f'{round(vol_pct)}th pct', 'demo': False},
        {'name': 'Macro-event risk', 'state': macro_event_risk, 'value': macro_note, 'demo': False},
        {'name': 'Data uncertainty', 'state': data_uncertainty, 'value': f'{dh_level} ({dh_score}/100)', 'demo': False},
        {'name': 'Implied volatility', 'state': demo['implied_vol']['state'], 'value': f"{demo['implied_vol']['value']}%", 'demo': True},
        {'name': 'Leverage / funding', 'state': demo['leverage_risk']['state'], 'value': f"{demo['leverage_risk']['funding_bps']} bps", 'demo': True},
        {'name': 'Liquidation risk', 'state': demo['liquidation_risk']['state'], 'value': f"cluster ~{demo['liquidation_risk']['nearest_cluster_pct']}% away", 'demo': True},
        {'name': 'Order-book liquidity', 'state': demo['orderbook_liquidity']['state'], 'value': f"${demo['orderbook_liquidity']['depth_2pct_musd']}M @2%", 'demo': True},
    ]

    return {
        'level': level, 'score': score, 'state_scale': ['Low', 'Normal', 'Elevated', 'High', 'Extreme'],
        'expected_move': expected_move,
        'realised_vol_annual': realised_vol_annual,
        'vol_percentile': round(vol_pct),
        'downside_zone': downside_zone, 'upside_zone': upside_zone,
        'macro_event_risk': macro_event_risk, 'macro_note': macro_note,
        'data_uncertainty': data_uncertainty,
        'drivers': drivers, 'demo': demo,
        'note': 'Risk is measured separately from direction — a constructive outlook can still carry high risk.',
    }


# ---------------------------- Smart Money & Institutional (DEMO) ----------------------------
def compute_smart_money_demo(last_close, regime):
    """DEMO on-chain / smart-money view. Illustrative only — real values need a Glassnode key."""
    seed = int(last_close) % 100
    trend = 'accumulation' if seed % 2 == 0 else 'distribution'
    return {
        'demo': True, 'source': 'Glassnode / on-chain (needs key)',
        'headline': f'Whales in mild {trend}',
        'metrics': [
            {'name': 'Exchange reserves (30d)', 'value': f'{"-" if trend=="accumulation" else "+"}{round(1.2 + seed%3,1)}%', 'signal': 'Bullish' if trend == 'accumulation' else 'Bearish'},
            {'name': 'Whale wallets ≥1k BTC', 'value': f'{"+" if trend=="accumulation" else "-"}{round(0.3 + seed%2*0.4,1)}%', 'signal': 'Bullish' if trend == 'accumulation' else 'Bearish'},
            {'name': 'Long-term holder supply', 'value': f'+{round(0.5 + seed%3*0.3,1)}%', 'signal': 'Bullish'},
            {'name': 'Realised profit/loss ratio', 'value': f'{round(0.8 + (seed%40)/100,2)}', 'signal': 'Neutral'},
            {'name': 'Dormant supply movement', 'value': 'Quiet', 'signal': 'Neutral'},
        ],
    }


def compute_institutional_demo(last_close):
    """DEMO institutional / ETF flow view. Illustrative only — needs a paid ETF/CME feed."""
    seed = int(last_close) % 100
    net = round((seed % 60) - 20, 0)
    return {
        'demo': True, 'source': 'ETF issuers / CME (needs key)',
        'headline': f'Spot ETF net flow ~${net}M (illustrative)',
        'metrics': [
            {'name': 'Spot ETF net flow (1d)', 'value': f'${net}M', 'signal': 'Bullish' if net > 0 else 'Bearish'},
            {'name': 'Spot ETF net flow (7d)', 'value': f'${round(net*5,0)}M', 'signal': 'Bullish' if net > 0 else 'Bearish'},
            {'name': 'CME open interest', 'value': f'{round(28 + seed%8,1)}k BTC', 'signal': 'Neutral'},
            {'name': 'CME basis (annualised)', 'value': f'{round(6 + seed%6,1)}%', 'signal': 'Bullish'},
            {'name': 'Grayscale/HODL trend', 'value': 'Stabilising', 'signal': 'Neutral'},
        ],
    }



CHAT_SYSTEM = (
    "You are 'Albert', the friendly HuCentAI Quant analyst built into the BTCIQ Bitcoin dashboard "
    "(powered by BitCentAI, a Bitcoin-Centred Intelligence Engine). You have a warm, witty, "
    "professor-like personality — think a sharp, approachable Einstein of Bitcoin markets — but you "
    "stay rigorous and never over-promise. If someone asks who you are, say you are Albert, the BTCIQ "
    "HuCentAI Quant. Answer the user's question using ONLY the LIVE DASHBOARD DATA provided below. If the "
    "data does not contain the answer, say you don't have that data rather than guessing — never invent "
    "numbers, prices or events. Speak in clear, plain English and be concise (usually under 130 words). "
    "Always frame predictions as probabilities/odds, not certainties, and never give definitive buy/sell "
    "financial advice. You may explain what the numbers mean and why the engine leans a certain way.\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)


def build_chat_context(symbol='BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cd = coin_dash_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
        run = (cd or {}).get('data')
        cn = coin_news_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
        news = (cn or {}).get('doc')
        label = (run or {}).get('coin_name', symbol)
        sym = symbol
    else:
        run = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
        news = news_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
        label = 'Bitcoin'
        sym = 'BTC'
    if not run:
        return 'No dashboard data is available yet.'
    dec = run.get('decision') or {}
    L = []
    if sym != 'BTC':
        L.append(f"IMPORTANT: The asset in focus is {label} ({sym}/USD), an altcoin — NOT Bitcoin. Talk about {label} throughout and ignore Bitcoin-only concepts (halving cycle, BTC dominance) which do not apply here.")
    L.append(f"As of {run.get('as_of')}: {sym}/USD last close ${run.get('last_close')} ({run.get('day_change_pct')}% on the day), data source {run.get('data_source')}.")
    L.append(f"{label} Quant Score {run.get('quant_score')}/100 ({run.get('quant_label')}). Next-day model signal: {run.get('signal')} at {run.get('confidence')}% confidence.")
    L.append(f"Market regime: {run['regime']['regime']} — {run['regime']['description']} (30d trend {run['regime'].get('trend30d_pct')}%, volatility {run['regime'].get('vol_percentile')}th percentile).")
    if dec:
        L.append(f"Unified Decision Engine: overall {dec.get('overall_score')}/100 ({dec.get('label')}), risk level {dec.get('risk_level')}, signal alignment: {dec.get('alignment')}.")
        L.append("Decision summary: " + dec.get('summary', ''))
    for f in run.get('forecasts', []):
        h = f.get('higher_adj', f['higher'])
        nl = f.get('news_link')
        extra = f" (news-adjusted from {nl['higher_base']}%)" if nl else ''
        L.append(f"{f['horizon']} forecast: {h}% higher / {round(100 - h, 1)}% lower{extra}, confidence {f['confidence']}, backtest accuracy {f['accuracy']}%. Scenarios — Bull ${f['bull']} / Base ${f['base']} / Bear ${f['bear']}. Invalidated {f['invalidation_dir']} ${f['invalidation']}.")
    for o in run.get('long_outlook', []):
        L.append(f"{o['horizon']} outlook: {o['higher']}% higher, base ${o['base']} (bull ${o['bull']} / bear ${o['bear']}).")
    L.append("Top bullish factors: " + " | ".join(run['factors']['bullish']))
    L.append("Top risk factors: " + " | ".join(run['factors']['risk']))
    if run.get('policy'):
        p = run['policy']
        L.append(f"Policy & Liquidity Score {p['score']}/100 ({p['label']}); Global Liquidity Impulse {p['liquidity_impulse']}/100 ({p['liquidity_state']}). DXY {p['dxy']}, 10Y yield {p['y10']}%, VIX {p['vix']}.")
    if run.get('dominance'):
        dm = run['dominance']
        L.append(f"BTC dominance {dm['dominance']}% ({dm['direction']}), total crypto market cap ${dm['total_mcap_t']}T. {dm['interpretation']}")
    if run.get('cycle'):
        cy = run['cycle']
        L.append(f"Halving cycle: {cy['cycle_progress_pct']}% through, phase '{cy['phase']}', {cy['days_since_halving']} days since the {cy['last_halving_date']} halving, block reward {cy['reward']} BTC.")
    if run.get('chart'):
        ch = run['chart']
        L.append(f"Chart structure: {ch['structure']} ({ch['structure_bias']}). {ch['predictive']['primary_setup']}")
    if run.get('scoreboard'):
        sb = run['scoreboard']
        L.append(f"Backtest scoreboard: {sb['winRate']}% win rate over {sb['total']} graded predictions ({sb['wins']} wins / {sb['losses']} losses).")
    if news:
        b = news.get('briefing', {})
        L.append(f"News briefing: bias {b.get('bias')}, {b.get('total')} stories, {b.get('major_stories')} high-impact. Top tailwind: {b.get('top_tailwind')}. Top risk: {b.get('top_risk')}.")
        for c in sorted(news.get('cards', []), key=lambda z: -z.get('impact', 0))[:3]:
            L.append(f"News [impact {c.get('impact')}]: {c.get('title')} — {(c.get('ai') or {}).get('direction')}.")
    return "\n".join(L)


# =====================================================================
# DATA TRUST LAYER  +  PREDICTION LEDGER  +  EVENT CALENDAR
# =====================================================================
def _age_min(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace('Z', ''))
        return max(0.0, (datetime.datetime.utcnow() - t).total_seconds() / 60.0)
    except Exception:  # noqa
        return None


def compute_data_health(source, crossmarket, policy, dominance, news_doc):
    now_iso = datetime.datetime.utcnow().isoformat()
    feeds = []

    def add(fid, label, provider, ok, updated_iso, fresh_min, methodology):
        age = _age_min(updated_iso) if updated_iso else None
        if not ok:
            status, conf = 'down', 10
        elif age is None:
            status, conf = 'live', 95
        elif age <= fresh_min:
            status, conf = 'live', 97
        elif age <= fresh_min * 3:
            status, conf = 'degraded', 72
        else:
            status, conf = 'stale', 42
        feeds.append({'id': fid, 'label': label, 'provider': provider, 'status': status,
                      'updated': updated_iso, 'age_min': round(age) if age is not None else None,
                      'confidence': conf, 'methodology': methodology})

    add('price', 'Spot & OHLCV Price', (source or 'kraken').title(), True, now_iso, 180,
        'Daily OHLCV via ccxt; live spot via exchange ticker (polled every ~10s).')
    add('dominance', 'BTC Dominance & Market Cap', 'CoinGecko', dominance is not None, now_iso, 180,
        'Global market-cap share and total market cap from the CoinGecko public API.')
    add('crossmarket', 'Cross-Market (DXY, Yields, VIX, Gold, S&P)', 'Yahoo Finance',
        crossmarket is not None, now_iso, 360, 'Daily closes for macro assets; rolling correlations vs BTC.')
    add('policy', 'Macro & Policy', 'Curated + Yahoo Finance', policy is not None, now_iso, 360,
        'Rate/liquidity proxies plus a curated policy & regulation calendar.')
    add('news', 'Bitcoin News & AI Impact', 'RSS + Gemini',
        news_doc is not None, (news_doc or {}).get('created_at'), 120,
        'Keyless RSS feeds clustered and scored for impact/direction by Gemini.')
    add('fx', 'USD → AUD FX', 'Yahoo Finance', True, now_iso, 1800,
        'AUD=X spot rate used to convert USD prices into AUD.')

    conf_vals = [f['confidence'] for f in feeds]
    score = int(round(sum(conf_vals) / len(conf_vals)))
    live = sum(1 for f in feeds if f['status'] == 'live')
    degraded = sum(1 for f in feeds if f['status'] == 'degraded')
    stale = sum(1 for f in feeds if f['status'] in ('stale', 'down'))
    level = 'High' if score >= 90 else 'Good' if score >= 75 else 'Degraded' if score >= 55 else 'Low'
    faded = stale > 0 or score < 70
    if stale == 0 and degraded == 0:
        note = 'All data feeds are live and fresh — full model confidence.'
    elif faded:
        note = f'{stale} feed(s) stale/down, {degraded} degraded — odds are faded and confidence reduced.'
    else:
        note = f'{degraded} feed(s) slightly delayed — minor confidence reduction.'
    return {'feeds': feeds, 'score': score, 'level': level, 'live': live, 'degraded': degraded,
            'stale': stale, 'faded': faded, 'note': note, 'checked_at': now_iso}


def apply_data_fade(decision, health):
    """When a live feed goes stale, fade the directional odds toward 50% and flag it."""
    if not decision or not health:
        return
    faded = health['faded']
    tf = max(0.35, health['score'] / 100.0)
    decision['data_trust'] = {'score': health['score'], 'level': health['level'], 'faded': faded}
    decision['odds_faded'] = faded
    if not faded:
        return
    for o in decision.get('outlook', []):
        h = o['higher']
        nh = round(50 + (h - 50) * tf, 1)
        o['higher'], o['lower'] = nh, round(100 - nh, 1)
        o['lean'] = 'UP' if nh >= 50 else 'DOWN'
        o['faded'] = True


# ---------------------------- Prediction Ledger ----------------------------
HZ_DAYS = {'24H': 1, '7D': 7, '30D': 30, '3M': 90, '6M': 180, '1Y': 365}


def _vol_label(f):
    try:
        spread = abs(f['bull'] - f['bear']) / max(1e-9, f['base'])
    except Exception:  # noqa
        return 'Elevated'
    return 'Very High' if spread > 0.6 else 'High' if spread > 0.3 else 'Elevated' if spread > 0.12 else 'Low'


def record_predictions(as_of, price_now, all_outlook, regime, source, model_version='rf-quant-v1', trigger='scheduled'):
    """Immutably log every horizon forecast BEFORE the outcome is known (idempotent per as_of+horizon)."""
    for f in all_outlook:
        hz = f['horizon']
        days = HZ_DAYS.get(hz)
        if not days:
            continue
        higher = float(f.get('higher_adj', f['higher']))
        key = f"{as_of}_{hz}"
        doc = {
            '_id': key, 'model_version': model_version, 'trigger': trigger,
            'as_of': as_of, 'issued_at': datetime.datetime.utcnow().isoformat(),
            'horizon': hz, 'horizon_days': days, 'target_date': f.get('expiry'),
            'price_at_issue': round(float(price_now), 2), 'data_source': source,
            'direction': 'UP' if higher >= 50 else 'DOWN',
            'prob_higher': round(higher, 1), 'prob_lower': round(100 - higher, 1),
            'base': f.get('base'), 'bull': f.get('bull'), 'bear': f.get('bear'),
            'confidence': f.get('confidence'), 'confidence_pct': f.get('confidence_pct'), 'regime': regime,
            'expected_volatility': _vol_label(f),
            'resolved': False, 'actual_close': None, 'actual_direction': None,
            'correct': None, 'brier': None, 'abs_pct_error': None, 'range_hit': None,
        }
        try:
            predictions_col.update_one({'_id': key}, {'$setOnInsert': doc}, upsert=True)
        except Exception:  # noqa
            traceback.print_exc()


def seed_ledger_from_backtest(trades):
    """Bootstrap the 24H ledger from the real walk-forward backtest (trigger='backtest')."""
    try:
        existing = {d['_id'] for d in predictions_col.find({'trigger': 'backtest'}, {'_id': 1})}
        new_docs = []
        for t in trades:
            key = f"bt_{t['date']}_24H"
            if key in existing:
                continue
            prob = t['confidence'] if t['signal'] == 'UP' else (100 - t['confidence'])
            actual_up = 1 if t['actual'] == 'UP' else 0
            new_docs.append({
                '_id': key, 'model_version': 'rf-quant-v1', 'trigger': 'backtest',
                'as_of': t['date'], 'issued_at': t['date'], 'horizon': '24H', 'horizon_days': 1,
                'target_date': None, 'price_at_issue': t['close'], 'data_source': 'backtest',
                'direction': t['signal'], 'prob_higher': round(prob, 1), 'prob_lower': round(100 - prob, 1),
                'base': t['nextClose'], 'bull': None, 'bear': None, 'confidence': None, 'regime': None,
                'expected_volatility': None, 'resolved': True,
                'resolved_at': t['date'], 'actual_close': t['nextClose'], 'actual_direction': t['actual'],
                'correct': bool(t['correct']), 'brier': round((prob / 100 - actual_up) ** 2, 4),
                'abs_pct_error': None, 'range_hit': None,
            })
        if new_docs:
            predictions_col.insert_many(new_docs, ordered=False)
    except Exception:  # noqa
        traceback.print_exc()


def resolve_predictions(close_by_date, latest_date):
    """Grade any matured forward predictions against the actual close."""
    try:
        latest = datetime.datetime.strptime(latest_date, '%Y-%m-%d').date()
    except Exception:  # noqa
        return
    dates_sorted = sorted(close_by_date.keys())
    for p in list(predictions_col.find({'resolved': False})):
        td = p.get('target_date')
        if not td:
            continue
        try:
            tdd = datetime.datetime.strptime(td, '%Y-%m-%d').date()
        except Exception:  # noqa
            continue
        if tdd > latest:
            continue
        ac = close_by_date.get(td)
        if ac is None:
            fwd = [d for d in dates_sorted if d >= td]
            ac = close_by_date[fwd[0]] if fwd else close_by_date[dates_sorted[-1]]
        pi = p['price_at_issue']
        actual_dir = 'UP' if ac > pi else 'DOWN'
        prob = p['prob_higher'] / 100.0
        actual_up = 1 if ac > pi else 0
        base = p.get('base') or pi
        rng_hit = None
        if p.get('bear') and p.get('bull'):
            rng_hit = bool(p['bear'] <= ac <= p['bull'])
        predictions_col.update_one({'_id': p['_id']}, {'$set': {
            'resolved': True, 'resolved_at': datetime.datetime.utcnow().isoformat(),
            'actual_close': round(ac, 2), 'actual_direction': actual_dir,
            'correct': (p['direction'] == actual_dir),
            'brier': round((prob - actual_up) ** 2, 4),
            'abs_pct_error': round(abs(base - ac) / ac * 100, 2) if ac else None,
            'range_hit': rng_hit,
        }})


def compute_scorecard():
    resolved = list(predictions_col.find({'resolved': True}, {'_id': 0}))

    def agg(items):
        n = len(items)
        if not n:
            return None
        acc = round(sum(1 for x in items if x.get('correct')) / n * 100, 1)
        briers = [x['brier'] for x in items if x.get('brier') is not None]
        maes = [x['abs_pct_error'] for x in items if x.get('abs_pct_error') is not None]
        rngs = [x['range_hit'] for x in items if x.get('range_hit') is not None]
        return {
            'n': n, 'accuracy': acc,
            'brier': round(sum(briers) / len(briers), 4) if briers else None,
            'mae_pct': round(sum(maes) / len(maes), 2) if maes else None,
            'range_hit_pct': round(sum(1 for r in rngs if r) / len(rngs) * 100, 1) if rngs else None,
        }

    overall = agg(resolved) or {'n': 0, 'accuracy': None, 'brier': None, 'mae_pct': None, 'range_hit_pct': None}
    by_h = {}
    for hz in ['24H', '7D', '30D', '3M', '6M', '1Y']:
        a = agg([x for x in resolved if x.get('horizon') == hz])
        if a:
            by_h[hz] = a
    # probability calibration (predicted higher% vs realised up-rate)
    calib = []
    for lo, hi in [(0, 40), (40, 50), (50, 60), (60, 100)]:
        bucket = [x for x in resolved if lo <= x.get('prob_higher', 0) < hi]
        if bucket:
            realised = round(sum(1 for x in bucket if x.get('actual_direction') == 'UP') / len(bucket) * 100, 1)
            calib.append({'bucket': f'{lo}-{hi}%', 'n': len(bucket),
                          'avg_pred': round(sum(x['prob_higher'] for x in bucket) / len(bucket), 1),
                          'realised_up': realised})
    pending = list(predictions_col.find(
        {'resolved': False, 'trigger': {'$ne': 'backtest'}}, {'_id': 0}).sort('target_date', 1))

    # Ensure every open forecast has a directional-confidence label + percentage so the
    # UI can render a badge + number even for docs logged before confidence_pct existed.
    def _conf_from_prob(prob_higher):
        margin = abs(float(prob_higher) - 50.0) / 50.0        # 0..1
        pct = round(min(100.0, margin * 100.0))
        label = 'High' if margin > 0.45 else ('Moderate' if margin > 0.2 else 'Low')
        return label, pct

    for p in pending:
        cp = p.get('confidence_pct')
        cl = p.get('confidence')
        if cp is None:
            # Legacy doc logged before confidence_pct existed — derive both from the
            # directional probability so the badge and percentage always agree.
            fb_label, fb_pct = _conf_from_prob(p.get('prob_higher', 50))
            p['confidence_pct'] = fb_pct
            p['confidence'] = fb_label
        elif cl is None:
            fb_label, _ = _conf_from_prob(p.get('prob_higher', 50))
            p['confidence'] = fb_label

    recent = sorted([x for x in resolved if x.get('trigger') != 'backtest'],
                    key=lambda z: z.get('resolved_at', ''), reverse=True)[:15]

    # Performance grouped by market regime (real resolved forecasts that carry a regime)
    by_regime = {}
    regimes = set(x.get('regime') for x in resolved if x.get('regime'))
    for rg in regimes:
        a = agg([x for x in resolved if x.get('regime') == rg])
        if a:
            by_regime[rg] = a

    # Filterable ledger: every open forecast + resolved live + a capped slice of backtested,
    # each normalised with the fields the UI filters on. Nothing is deleted or hidden.
    def _norm(x):
        return {
            'issued_date': x.get('as_of'), 'horizon': x.get('horizon'),
            'price_at_issue': x.get('price_at_issue'),
            'base': x.get('base'), 'bull': x.get('bull'), 'bear': x.get('bear'),
            'prob_higher': x.get('prob_higher'), 'prob_lower': x.get('prob_lower'),
            'direction': x.get('direction'),
            'confidence': x.get('confidence'), 'confidence_pct': x.get('confidence_pct'),
            'model_version': x.get('model_version'), 'trigger': x.get('trigger'),
            'regime': x.get('regime'), 'target_date': x.get('target_date'),
            'actual_close': x.get('actual_close'), 'actual_direction': x.get('actual_direction'),
            'correct': x.get('correct'), 'abs_pct_error': x.get('abs_pct_error'),
            'range_hit': x.get('range_hit'), 'resolved': x.get('resolved'),
        }
    resolved_live = sorted([x for x in resolved if x.get('trigger') != 'backtest'],
                           key=lambda z: z.get('resolved_at', ''), reverse=True)
    resolved_bt = sorted([x for x in resolved if x.get('trigger') == 'backtest'],
                         key=lambda z: z.get('as_of', ''), reverse=True)[:150]
    ledger = [_norm(p) for p in pending] + [_norm(x) for x in resolved_live] + [_norm(x) for x in resolved_bt]

    return {
        'overall': overall, 'by_horizon': by_h, 'by_regime': by_regime, 'calibration': calib,
        'pending': pending[:24], 'recent': recent, 'ledger': ledger,
        'total_logged': predictions_col.count_documents({}),
        'live_logged': predictions_col.count_documents({'trigger': {'$ne': 'backtest'}}),
        'backtested': predictions_col.count_documents({'trigger': 'backtest'}),
        'model_version': 'rf-quant-v1',
    }


# ---------------------------- Event Calendar ----------------------------
FOMC_DATES = ['2026-01-28', '2026-03-18', '2026-04-29', '2026-06-17', '2026-07-29',
              '2026-09-16', '2026-10-28', '2026-12-09',
              '2027-01-27', '2027-03-17', '2027-04-28', '2027-06-16']


def compute_event_calendar(cycle, policy, window=120):
    import calendar as _cal
    today = datetime.datetime.utcnow().date()
    end = today + datetime.timedelta(days=window)
    ev = []

    def add(d, cat, title, desc, imp, vol):
        dd = datetime.datetime.strptime(d, '%Y-%m-%d').date() if isinstance(d, str) else d
        ev.append({'date': dd.strftime('%Y-%m-%d'), 'days_until': (dd - today).days,
                   'category': cat, 'title': title, 'description': desc,
                   'importance': imp, 'expected_volatility': vol})

    y, m = today.year, today.month
    for _ in range(6):
        d1 = datetime.date(y, m, 1)
        first_fri = d1 + datetime.timedelta(days=(4 - d1.weekday()) % 7)
        add(first_fri, 'Macro', 'US Nonfarm Payrolls',
            'Monthly US jobs report; moves rate expectations and risk appetite.', 'High', 'Elevated')
        try:
            add(datetime.date(y, m, 12), 'Macro', 'US CPI Inflation (approx.)',
                'Monthly inflation print — a strong driver of rate expectations and BTC.', 'Very High', 'High')
        except Exception:  # noqa
            pass
        last_day = _cal.monthrange(y, m)[1]
        dl = datetime.date(y, m, last_day)
        last_fri = dl - datetime.timedelta(days=(dl.weekday() - 4) % 7)
        if m in (3, 6, 9, 12):
            add(last_fri, 'Derivatives', 'Quarterly Futures & Options Expiry',
                'Large CME/Deribit quarterly expiry; elevated pinning and volatility.', 'High', 'High')
        else:
            add(last_fri, 'Derivatives', 'Monthly Options & Futures Expiry',
                'Monthly BTC options/futures expiry; short-term volatility.', 'Medium', 'Elevated')
        m += 1
        if m > 12:
            m = 1
            y += 1

    for f in FOMC_DATES:
        fd = datetime.datetime.strptime(f, '%Y-%m-%d').date()
        if today <= fd <= end:
            add(f, 'Macro', 'FOMC Rate Decision',
                'US Federal Reserve interest-rate decision & guidance — top-tier macro catalyst.',
                'Very High', 'Very High')

    anchor = datetime.date(2026, 1, 7)
    k = 0
    while k < 400:
        dd = anchor + datetime.timedelta(days=14 * k)
        k += 1
        if dd > end:
            break
        if dd < today:
            continue
        add(dd, 'On-Chain', 'Bitcoin Difficulty Adjustment',
            'Network retargets mining difficulty (~every 2 weeks); minor direct impact.', 'Low', 'Low')

    ev = [e for e in ev if 0 <= e['days_until'] <= window]
    ev.sort(key=lambda z: z['date'])
    nxt = next((e for e in ev if e['importance'] in ('Very High', 'High')), None)
    counts = {}
    for e in ev:
        counts[e['category']] = counts.get(e['category'], 0) + 1
    return {'events': ev, 'window_days': window, 'next_high_impact': nxt,
            'counts': counts, 'generated': today.strftime('%Y-%m-%d')}


# ---------------------------- BitMarkAI Engine ----------------------------
BM_WEIGHTS = {
    '1W': [('Price & Technicals', 30), ('Momentum & Trend', 25), ('Volatility', 15), ('News & Sentiment', 13), ('Market Regime', 10), ('Macro & Policy', 5), ('Halving Cycle', 2)],
    '1M': [('Price & Technicals', 22), ('Momentum & Trend', 20), ('News & Sentiment', 13), ('Market Regime', 12), ('Macro & Policy', 12), ('Volatility', 10), ('Halving Cycle', 7), ('Dominance & Flows', 4)],
    '3M': [('Halving Cycle', 20), ('Macro & Policy', 18), ('Momentum & Trend', 15), ('Price & Technicals', 13), ('Market Regime', 12), ('Volatility', 8), ('News & Sentiment', 8), ('Dominance & Flows', 6)],
    '6M': [('Halving Cycle', 28), ('Macro & Policy', 22), ('Momentum & Trend', 10), ('Market Regime', 10), ('Price & Technicals', 10), ('Dominance & Flows', 8), ('Volatility', 7), ('News & Sentiment', 5)],
    '1Y': [('Halving Cycle', 38), ('Macro & Policy', 22), ('Dominance & Flows', 10), ('Volatility', 8), ('Price & Technicals', 6), ('Momentum & Trend', 6), ('Market Regime', 6), ('News & Sentiment', 4)],
    '2Y': [('Halving Cycle', 45), ('Macro & Policy', 25), ('Adoption & Liquidity', 20), ('Dominance & Flows', 10)],
    '5Y': [('Adoption & Liquidity', 45), ('Halving Cycle', 25), ('Macro & Policy', 20), ('Dominance & Flows', 10)],
}
BM_LABEL = {'1W': 'Next Week', '1M': 'Next Month', '3M': 'Next 3 Months', '6M': 'Next 6 Months',
            '1Y': 'Next Year', '2Y': 'Next 2 Years', '5Y': 'Next 5 Years'}


def _bm_model_horizon(code, f, price, tp, tr, issued, next_upd):
    higher = float(f.get('higher_adj', f['higher']))
    base, bull, bear = f['base'], f['bull'], f['bear']
    spread = max(1.0, bull - bear)
    base_low, base_high = round(base - 0.15 * spread), round(base + 0.15 * spread)
    return {'horizon': code, 'label': BM_LABEL[code], 'type': 'model', 'current_price': round(price, 2),
            'prob_above': round(higher, 1), 'prob_below': round(100 - higher, 1),
            'base_low': base_low, 'base_high': base_high,
            'bull_low': base_high, 'bull_high': round(bull),
            'bear_low': round(bear), 'bear_high': base_low,
            'expected_volatility': _vol_label(f), 'model_confidence': f.get('confidence', 'Low'),
            'accuracy': f.get('accuracy'), 'top_positive': tp, 'top_risk': tr,
            'weighting': [{'category': c, 'weight': w} for c, w in BM_WEIGHTS[code]],
            'issued': issued, 'next_update': next_upd}


def _bm_scenario_horizon(code, price, years, issued, next_upd):
    scen = [
        ('Adoption Expansion', {2: (1.6, 2.6), 5: (3.0, 9.0)}, 30, 'Accelerating institutional & sovereign adoption plus easing global liquidity.'),
        ('Base Adoption', {2: (1.25, 1.7), 5: (1.8, 3.5)}, 40, 'Steady adoption growth roughly tracking prior post-halving cycles.'),
        ('Restrictive Policy', {2: (0.75, 1.05), 5: (0.9, 1.6)}, 20, 'Tight liquidity, higher-for-longer rates and heavier regulation.'),
        ('Severe Disruption', {2: (0.35, 0.65), 5: (0.5, 1.1)}, 10, 'A major shock — regulatory ban, systemic failure or a liquidity crisis.'),
    ]
    scenarios = []
    for name, mult, prob, note in scen:
        lo, hi = mult[years]
        scenarios.append({'name': name, 'prob': prob, 'low': round(price * lo), 'high': round(price * hi), 'note': note})
    prob_above = sum(s['prob'] for s in scenarios if s['low'] >= price) + \
        sum(s['prob'] * 0.5 for s in scenarios if s['low'] < price <= s['high'])
    prob_above = round(min(95, max(5, prob_above)))
    return {'horizon': code, 'label': BM_LABEL[code], 'type': 'scenario', 'current_price': round(price, 2),
            'prob_above': prob_above, 'prob_below': 100 - prob_above,
            'expected_volatility': 'Very High', 'model_confidence': 'Low' if years == 2 else 'Very Low',
            'scenarios': scenarios,
            'top_positive': 'Post-halving supply squeeze meeting sustained adoption demand.',
            'top_risk': 'Long-range regulatory and macro-liquidity uncertainty widens the range.',
            'weighting': [{'category': c, 'weight': w} for c, w in BM_WEIGHTS[code]],
            'issued': issued, 'next_update': next_upd}


def compute_bitmark(quant, cycle, price, trigger='scheduled'):
    now = datetime.datetime.utcnow()
    issued = now.strftime('%Y-%m-%d')
    next_upd = (now + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    idx = {f['horizon']: f for f in (quant['forecasts'] + quant.get('long_outlook', []))}
    bulls, risks = quant['factors']['bullish'], quant['factors']['risk']
    tp = bulls[0] if bulls else 'Constructive technical structure.'
    tr = risks[0] if risks else 'Elevated near-term volatility.'
    horizons = []
    for code, src in [('1W', '7D'), ('1M', '30D'), ('3M', '3M'), ('6M', '6M'), ('1Y', '1Y')]:
        f = idx.get(src)
        if f:
            horizons.append(_bm_model_horizon(code, f, price, tp, tr, issued, next_upd))
    horizons.append(_bm_scenario_horizon('2Y', price, 2, issued, next_upd))
    horizons.append(_bm_scenario_horizon('5Y', price, 5, issued, next_upd))

    prev = bitmark_col.find_one(sort=[('created_at', -1)])
    changes, change_text = None, None
    if prev:
        pmap = {h['horizon']: h for h in prev.get('horizons', [])}
        chlist = []
        for h in horizons:
            ph = pmap.get(h['horizon'])
            if not ph:
                continue
            d = round(h['prob_above'] - ph.get('prob_above', h['prob_above']), 1)
            if abs(d) >= 0.5:
                chlist.append({'horizon': h['horizon'], 'prob_delta': d,
                               'from': ph.get('prob_above'), 'to': h['prob_above']})
        changes = chlist
        if chlist:
            big = max(chlist, key=lambda z: abs(z['prob_delta']))
            dirw = 'increased' if big['prob_delta'] > 0 else 'decreased'
            change_text = (f"The {big['horizon']} bullish probability {dirw} from {big['from']}% to "
                           f"{big['to']}%. {tp} Key offsetting risk: {tr}")
        else:
            change_text = 'No material change since the previous forecast — probabilities and ranges are broadly stable.'
    else:
        change_text = 'First BitMarkAI forecast recorded to the ledger.'

    snap = {'_id': str(uuid.uuid4()), 'created_at': now.isoformat(), 'trigger': trigger,
            'price': round(price, 2),
            'horizons': [{'horizon': h['horizon'], 'prob_above': h['prob_above'],
                          'confidence': h.get('model_confidence')} for h in horizons]}
    try:
        bitmark_col.insert_one(snap)
    except Exception:  # noqa
        traceback.print_exc()

    return {'model_version': 'bitmark-v1', 'trigger': trigger, 'issued': issued,
            'next_scheduled_update': next_upd, 'current_price': round(price, 2),
            'regime': quant['regime']['regime'], 'horizons': horizons,
            'changes': changes, 'change_explanation': change_text, 'generated_at': now.isoformat()}


# ---------------------------- Smart Alerts (state-change detection) ----------------------------
# Non-price, event-driven alerts triggered when the market STATE changes between runs
# (regime flips, decision-label changes, data-trust degradation, high-impact events entering
# the near window, big daily moves). Persisted + de-duplicated so users see a running feed.
_TRUST_RANK = {'High': 3, 'Good': 2, 'Degraded': 1, 'Low': 0}


def _score_band(s):
    if s is None:
        return None
    if s >= 65:
        return 'Bullish'
    if s >= 55:
        return 'Mildly Bullish'
    if s > 45:
        return 'Neutral'
    if s > 35:
        return 'Mildly Bearish'
    return 'Bearish'


def compute_smart_alerts(doc, prev_doc):
    """Compare the new run against the previous run and log meaningful state changes."""
    as_of = doc.get('as_of')
    now_iso = datetime.datetime.utcnow().isoformat()
    fired = []

    def fire(category, severity, title, message, sig):
        key = f"{as_of}_{category}_{sig}"
        try:
            res = smart_alerts_col.update_one(
                {'_id': key},
                {'$setOnInsert': {
                    '_id': key, 'id': key, 'ts': now_iso, 'as_of': as_of,
                    'category': category, 'severity': severity,
                    'title': title, 'message': message, 'seen': False,
                }}, upsert=True)
            if res.upserted_id is not None:
                fired.append(key)
        except Exception:  # noqa
            traceback.print_exc()

    prev = prev_doc or {}

    # 1) Regime change
    cur_regime = (doc.get('regime') or {}).get('regime')
    prev_regime = (prev.get('regime') or {}).get('regime')
    if cur_regime and prev_regime and cur_regime != prev_regime:
        fire('Regime', 'high', f'Regime shift → {cur_regime}',
             f'Market regime changed from "{prev_regime}" to "{cur_regime}". '
             f'{(doc.get("regime") or {}).get("behavior", "")}', cur_regime)

    # 2) Decision label change (overall market state)
    cur_dl = (doc.get('decision') or {}).get('label')
    prev_dl = (prev.get('decision') or {}).get('label')
    if cur_dl and prev_dl and cur_dl != prev_dl:
        sev = 'high' if ('Bear' in cur_dl or 'Bull' in cur_dl) else 'warning'
        fire('Market State', sev, f'Market state → {cur_dl}',
             f'Unified decision changed from "{prev_dl}" to "{cur_dl}" '
             f'(score {(doc.get("decision") or {}).get("overall_score")}/100).', cur_dl)

    # 3) Quant-score band crossing
    cur_band = _score_band(doc.get('quant_score'))
    prev_band = _score_band(prev.get('quant_score'))
    if cur_band and prev_band and cur_band != prev_band:
        fire('Quant Score', 'info', f'Quant Score band → {cur_band}',
             f'Quant Score moved from {prev.get("quant_score")} ({prev_band}) to '
             f'{doc.get("quant_score")} ({cur_band}).', cur_band)

    # 4) Data-trust degradation / recovery
    cur_tr = (doc.get('data_health') or {}).get('level')
    prev_tr = (prev.get('data_health') or {}).get('level')
    if cur_tr and prev_tr and cur_tr != prev_tr:
        worse = _TRUST_RANK.get(cur_tr, 3) < _TRUST_RANK.get(prev_tr, 3)
        fire('Data Trust', 'warning' if worse else 'success',
             f'Data trust {"degraded" if worse else "recovered"} → {cur_tr}',
             f'Feed health changed from "{prev_tr}" to "{cur_tr}". '
             f'{"Odds are being faded toward 50%." if (doc.get("data_health") or {}).get("faded") else "Full model confidence restored."}',
             cur_tr)

    # 5) High-impact event entering the near-term (<=3 days) window
    nhi = (doc.get('event_calendar') or {}).get('next_high_impact')
    if nhi and nhi.get('days_until') is not None and 0 <= nhi['days_until'] <= 3:
        fire('Event Risk', 'warning', f'{nhi.get("title")} in {nhi["days_until"]}d',
             f'{nhi.get("importance")}-importance {nhi.get("category")} event approaching '
             f'({nhi.get("expected_volatility")} expected volatility). {nhi.get("description", "")}',
             f"{nhi.get('title')}_{nhi.get('date')}")

    # 6) Large daily move
    dc = doc.get('day_change_pct')
    if dc is not None and abs(dc) >= 5.0:
        fire('Volatility', 'high' if abs(dc) >= 8 else 'warning',
             f'Large move: {"+" if dc > 0 else ""}{dc}% in 24h',
             f'Bitcoin moved {"+" if dc > 0 else ""}{dc}% over the last daily candle to '
             f'{fmt_usd_srv(doc.get("last_close"))} — elevated volatility.', f'move_{round(dc)}')

    return {'fired': fired, 'n_fired': len(fired)}


def fmt_usd_srv(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:  # noqa
        return str(v)


def get_smart_alerts(limit=50):
    items = list(smart_alerts_col.find({}, {'_id': 0}).sort('ts', -1).limit(limit))
    unseen = smart_alerts_col.count_documents({'seen': False})
    return {'alerts': items, 'unseen': unseen, 'total': smart_alerts_col.count_documents({})}


# ---------------------------- Time Machine (historical replay) ----------------------------
def build_replay_payload(trades, price_series):
    """Bundle the full walk-forward predictions + price path so the frontend Time Machine
    can replay any historical day (model call vs actual outcome)."""
    return {
        'series': price_series,          # [{date, close}] full history
        'trades': trades,                # [{date, signal, confidence, close, nextClose, actual, correct}]
        'min_date': trades[0]['date'] if trades else None,
        'max_date': trades[-1]['date'] if trades else None,
        'n': len(trades),
    }


def replay_for_date(target_date, window=30):
    """Return the model's as-of prediction for target_date + actual outcome + price window."""
    run = runs_col.find_one(sort=[('created_at', -1)])
    if not run or not run.get('replay'):
        return {'status': 'unavailable', 'message': 'No replay data yet — run a compute first.'}
    rp = run['replay']
    trades = rp.get('trades', [])
    series = rp.get('series', [])
    if not trades:
        return {'status': 'unavailable', 'message': 'No historical predictions available.'}
    # nearest trade at/just-before target_date
    pick = None
    for t in trades:
        if t['date'] <= target_date:
            pick = t
        else:
            break
    if pick is None:
        pick = trades[0]
    # price window around the pick date
    idx = next((i for i, s in enumerate(series) if s['date'] == pick['date']), None)
    if idx is None:
        idx = next((i for i, s in enumerate(series) if s['date'] >= pick['date']), len(series) - 1)
    lo = max(0, idx - window)
    hi = min(len(series), idx + window + 1)
    win = [{**s, 'is_pick': s['date'] == pick['date']} for s in series[lo:hi]]
    # rolling accuracy over the surrounding 30 trades
    tidx = next((i for i, t in enumerate(trades) if t['date'] == pick['date']), None)
    roll = None
    if tidx is not None:
        seg = trades[max(0, tidx - 15):tidx + 15]
        if seg:
            roll = round(sum(1 for x in seg if x['correct']) / len(seg) * 100, 1)
    move_pct = round((pick['nextClose'] - pick['close']) / pick['close'] * 100, 2) if pick['close'] else 0
    return {
        'status': 'ready',
        'pick_date': pick['date'],
        'signal': pick['signal'],
        'confidence': pick['confidence'],
        'close': pick['close'],
        'next_close': pick['nextClose'],
        'actual': pick['actual'],
        'move_pct': move_pct,
        'correct': pick['correct'],
        'window': win,
        'rolling_accuracy': roll,
        'min_date': rp.get('min_date'),
        'max_date': rp.get('max_date'),
        'n': rp.get('n'),
    }


# ---------------------------- Bitcoin Time Machine: curated scenarios ----------------------------
CURATED_SCENARIOS = [
    {'id': 'covid', 'title': 'COVID Liquidity Shock', 'date': '2020-03-12', 'category': 'Macro shock',
     'description': 'Global markets crashed as COVID-19 lockdowns began. Bitcoin fell ~50% in a day ("Black Thursday") before a historic liquidity-driven recovery.'},
    {'id': 'halving2020', 'title': '3rd Bitcoin Halving', 'date': '2020-05-11', 'category': 'Halving',
     'description': 'The block reward was cut from 12.5 to 6.25 BTC. New supply issuance halved — historically a precursor to major bull phases.'},
    {'id': 'top2021', 'title': '2021 Cycle Top', 'date': '2021-11-09', 'category': 'Cycle top',
     'description': 'Bitcoin printed its ~$69k all-time high amid euphoric leverage, just before a prolonged bear market.'},
    {'id': 'chinaban', 'title': 'China Mining Ban', 'date': '2021-05-21', 'category': 'Regulation',
     'description': 'China intensified its crackdown on mining and trading, triggering a sharp sell-off and a global hashrate migration.'},
    {'id': 'ftx', 'title': 'FTX Collapse', 'date': '2022-11-08', 'category': 'Exchange failure',
     'description': 'The FTX exchange imploded, cascading liquidations and a crisis of confidence across crypto.'},
    {'id': 'capitulation', 'title': 'Bear-Market Capitulation', 'date': '2022-11-21', 'category': 'Capitulation',
     'description': 'Post-FTX capitulation drove Bitcoin toward its cycle low near $15.5k — a moment of maximum fear.'},
    {'id': 'etf', 'title': 'US Spot ETF Approval', 'date': '2024-01-10', 'category': 'Institutional',
     'description': 'The SEC approved the first US spot Bitcoin ETFs, opening a regulated institutional access channel.'},
    {'id': 'halving2024', 'title': '4th Bitcoin Halving', 'date': '2024-04-19', 'category': 'Halving',
     'description': 'The block reward was cut from 6.25 to 3.125 BTC — the fourth halving in Bitcoin history.'},
]
_scenario_cache = {}


def fetch_yahoo_daily_range(symbol, start_unix, end_unix):
    """True daily closes for an arbitrary historical window via Yahoo period1/period2."""
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?interval=1d&period1={int(start_unix)}&period2={int(end_unix)}')
    d = _http_json(url)['chart']['result'][0]
    ts = d['timestamp']
    cl = d['indicators']['quote'][0]['close']
    series = []
    for t, c in zip(ts, cl):
        if c is None:
            continue
        series.append({'date': datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d'),
                       'close': round(float(c), 2)})
    return series


def _fwd(series, idx, days):
    j = min(len(series) - 1, idx + days)
    if j <= idx:
        return None
    base = series[idx]['close']
    return round((series[j]['close'] - base) / base * 100, 1) if base else None


def build_scenario(scn, window=60):
    if scn['id'] in _scenario_cache:
        return _scenario_cache[scn['id']]
    try:
        d0 = datetime.datetime.strptime(scn['date'], '%Y-%m-%d')
        start = (d0 - datetime.timedelta(days=window + 10)).timestamp()
        end = (d0 + datetime.timedelta(days=420)).timestamp()
        series = fetch_yahoo_daily_range('BTC-USD', start, end)
    except Exception:  # noqa
        traceback.print_exc()
        series = None
    if not series:
        doc = runs_col.database['scenario_cache'].find_one({'_id': scn['id']})
        if doc:
            return doc['payload']
        return {**scn, 'status': 'unavailable'}
    idx = 0
    for i, s in enumerate(series):
        if s['date'] <= scn['date']:
            idx = i
        else:
            break
    price = series[idx]['close']
    lo = max(0, idx - window)
    hi = min(len(series), idx + window + 1)
    win = [{'date': s['date'], 'close': s['close'], 'is_pick': s['date'] == series[idx]['date']}
           for s in series[lo:hi]]
    outcomes = {'30d': _fwd(series, idx, 30), '90d': _fwd(series, idx, 90), '365d': _fwd(series, idx, 365)}
    model = None
    try:
        rep = replay_for_date(scn['date'], window=15)
        if rep.get('status') == 'ready' and rep.get('pick_date'):
            pd0 = datetime.datetime.strptime(rep['pick_date'], '%Y-%m-%d')
            if abs((pd0 - d0).days) <= 20:      # replay pick genuinely near the event
                model = {'available': True, 'pick_date': rep['pick_date'], 'signal': rep['signal'],
                         'confidence': rep['confidence'], 'actual': rep['actual'],
                         'correct': rep['correct'], 'move_pct': rep['move_pct']}
    except Exception:  # noqa
        model = None
    if model is None:
        model = {'available': False,
                 'note': 'This event pre-dates BitMarkAI’s live data window, so no point-in-time model call exists — shown as historical context only.'}
    payload = {**scn, 'status': 'ready', 'price_at_event': price, 'window': win,
               'outcomes': outcomes, 'model': model}
    _scenario_cache[scn['id']] = payload
    try:
        runs_col.database['scenario_cache'].update_one(
            {'_id': scn['id']}, {'$set': {'_id': scn['id'], 'payload': payload}}, upsert=True)
    except Exception:  # noqa
        pass
    return payload


def get_scenarios():
    out = []
    for scn in CURATED_SCENARIOS:
        try:
            out.append(build_scenario(scn))
        except Exception:  # noqa
            traceback.print_exc()
            out.append({**scn, 'status': 'error'})
    return {'status': 'ready', 'scenarios': out}




def compute():
    df, source = fetch_ohlcv()
    df = build_features(df)
    df = df.dropna().reset_index(drop=True)

    # Target: will tomorrow's close be higher than today's? (1 = up)
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)

    live_row = df.iloc[[-1]].copy()      # target unknown -> live prediction
    train_df = df.iloc[:-1].copy()       # valid targets

    X = train_df[FEATURE_COLS]
    y = train_df['Target']

    # --- TimeSeriesSplit cross validation (no future leakage) ---
    tscv = TimeSeriesSplit(n_splits=5)
    cv_folds = []
    for i, (tr, te) in enumerate(tscv.split(X)):
        m = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr], y.iloc[tr])
        acc = accuracy_score(y.iloc[te], m.predict(X.iloc[te]))
        cv_folds.append({'fold': i + 1, 'accuracy': round(float(acc) * 100, 2), 'testSize': int(len(te))})

    # --- Walk-forward backtest -> accuracy over time + trade log ---
    start = 200 if len(X) > 260 else max(30, int(len(X) * 0.4))
    retrain_every = 10
    model = None
    rows = []
    trades = []
    closes_full = df['close'].reset_index(drop=True)  # includes live row at end
    for i in range(start, len(X)):
        if model is None or (i - start) % retrain_every == 0:
            model = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
            model.fit(X.iloc[:i], y.iloc[:i])
        classes = list(model.classes_)
        proba = model.predict_proba(X.iloc[[i]])[0]
        pred = int(model.predict(X.iloc[[i]])[0])
        conf = float(proba[classes.index(pred)]) * 100 if pred in classes else 50.0
        actual = int(y.iloc[i])
        cur_close = float(closes_full.iloc[i])
        nxt_close = float(closes_full.iloc[i + 1])
        d = train_df['timestamp'].iloc[i]
        rows.append({'date': d, 'correct': 1 if pred == actual else 0, 'close': cur_close})
        trades.append({
            'date': d.strftime('%Y-%m-%d'),
            'signal': 'UP' if pred == 1 else 'DOWN',
            'confidence': round(conf, 1),
            'close': round(cur_close, 2),
            'nextClose': round(nxt_close, 2),
            'actual': 'UP' if actual == 1 else 'DOWN',
            'correct': bool(pred == actual),
        })

    # --- Scoreboard from real out-of-sample trades ---
    total = len(trades)
    wins = sum(1 for t in trades if t['correct'])
    losses = total - wins
    win_rate = round(wins / total * 100, 1) if total else 0.0
    best = cur = 0
    for t in trades:
        if t['correct']:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    sign = None
    streak_len = 0
    for t in reversed(trades):
        if sign is None:
            sign = t['correct']
            streak_len = 1
        elif t['correct'] == sign:
            streak_len += 1
        else:
            break
    scoreboard = {
        'total': total, 'wins': wins, 'losses': losses, 'winRate': win_rate,
        'bestWinStreak': best, 'currentStreak': (streak_len if sign else -streak_len),
    }
    recent_trades = list(reversed(trades))[:25]

    pser = pd.DataFrame(rows)
    pser['rolling_acc'] = pser['correct'].rolling(30, min_periods=10).mean() * 100
    overall_acc = round(float(pser['correct'].mean()) * 100, 2)

    performance = []
    for _, r in pser.iterrows():
        if pd.isna(r['rolling_acc']):
            continue
        d = r['date']
        performance.append({
            'date': d.strftime('%m/%d'),
            'iso': d.strftime('%Y-%m-%d'),
            'btcPrice': round(float(r['close']), 2),
            'aiAccuracy': round(float(r['rolling_acc']), 2),
        })

    # --- Final model on all training data -> live next-day signal ---
    final = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1)
    final.fit(X, y)
    live_X = live_row[FEATURE_COLS]
    pred = int(final.predict(live_X)[0])
    proba = final.predict_proba(live_X)[0]
    # guard for single-class edge case
    classes = list(final.classes_)
    p_up = float(proba[classes.index(1)]) if 1 in classes else 0.0
    p_down = float(proba[classes.index(0)]) if 0 in classes else 0.0
    confidence = round((p_up if pred == 1 else p_down) * 100, 2)

    importances = sorted(
        [{'feature': f, 'label': FEATURE_META[f]['label'], 'category': FEATURE_META[f]['category'],
          'importance': round(float(imp) * 100, 2)} for f, imp in zip(FEATURE_COLS, final.feature_importances_)],
        key=lambda z: -z['importance'],
    )

    feats = live_row.iloc[0]
    feature_snapshot = [
        {'feature': 'RSI', 'label': 'RSI (14)', 'category': 'Momentum',
         'value': round(float(feats['RSI']) * 100, 1), 'unit': ''},
        {'feature': 'StochRSI', 'label': 'Stochastic RSI', 'category': 'Momentum',
         'value': round(float(feats['StochRSI']) * 100, 1), 'unit': ''},
        {'feature': 'MACD_Hist_Norm', 'label': 'MACD Histogram', 'category': 'Trend',
         'value': round(float(feats['MACD_Hist_Norm']) * 100, 3), 'unit': '%'},
        {'feature': 'EMA_Ratio', 'label': 'EMA 9/21 Spread', 'category': 'Trend',
         'value': round(float(feats['EMA_Ratio']) * 100, 2), 'unit': '%'},
        {'feature': 'ATR_Pct', 'label': 'ATR %', 'category': 'Volatility',
         'value': round(float(feats['ATR_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'BB_Width_Pct', 'label': 'Bollinger Width', 'category': 'Volatility',
         'value': round(float(feats['BB_Width_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'Volume_Z', 'label': 'Volume Z-Score', 'category': 'Volume',
         'value': round(float(feats['Volume_Z']), 2), 'unit': 'σ'},
        {'feature': 'Volume_Ratio', 'label': 'Volume Ratio', 'category': 'Volume',
         'value': round(float(feats['Volume_Ratio']), 2), 'unit': 'x'},
    ]

    prev_close = float(train_df['close'].iloc[-1])
    last_close = float(live_row['close'].iloc[0])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)

    # --- Forward live signal history: grade prior pendings, record today's ---
    as_of = live_row['timestamp'].iloc[0].strftime('%Y-%m-%d')
    predict_for = (live_row['timestamp'].iloc[0] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        grade_pending(df)
        record_live_signal(as_of, predict_for, 'UP' if pred == 1 else 'DOWN',
                           confidence, round(last_close, 2))
    except Exception:  # noqa
        traceback.print_exc()
    live_record = compute_live_record()

    # --- Quant Score, Market Regime, multi-horizon forecasts, explainable factors ---
    quant = compute_quant_analysis(df, feats, last_close, live_row['timestamp'].iloc[0])

    # --- Institutional-grade no-key engines ---
    cycle = dominance = chart = market_intel = None
    try:
        cycle = compute_cycle_context(last_close, quant['regime']['regime'])
    except Exception:  # noqa
        traceback.print_exc()
    try:
        dominance = fetch_dominance(day_change)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        chart = compute_chart_intelligence(df)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        market_intel = build_market_intel(quant, quant['forecasts'], cycle, dominance, chart)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Cross-market correlations, Policy & Liquidity, Alerts (keyless) ---
    crossmarket = policy = alerts = None
    try:
        crossmarket, _raw = compute_crossmarket()
        policy = compute_policy(_raw)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        alerts = compute_alerts(quant, cycle, policy, chart, crossmarket)
    except Exception:  # noqa
        traceback.print_exc()

    # --- News → Forecast Link + Unified Bitcoin Decision Engine ---
    news_sig = news_forecast_link = decision = None
    try:
        news_doc = news_col.find_one(sort=[('created_at', -1)])
        news_sig = compute_news_signal(news_doc)
        news_forecast_link = apply_news_link(quant['forecasts'], news_sig)  # mutates 24H/7D
    except Exception:  # noqa
        traceback.print_exc()
    all_outlook = list(quant['forecasts']) + list(quant.get('long_outlook', []))
    try:
        decision = compute_decision_engine(quant, all_outlook, policy, news_sig, chart, cycle, dominance)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Data Trust Layer (source/freshness/confidence + fade odds when stale) ---
    data_health = None
    try:
        data_health = compute_data_health(source, crossmarket, policy, dominance, news_doc)
        apply_data_fade(decision, data_health)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Event Intelligence Calendar ---
    event_calendar = None
    try:
        event_calendar = compute_event_calendar(cycle, policy)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Risk Engine + Smart Money / Institutional (DEMO) ---
    risk = smart_money = institutional = None
    try:
        risk = compute_risk_engine(quant, chart, decision, data_health, event_calendar, last_close, feats)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        smart_money = compute_smart_money_demo(last_close, quant['regime']['regime'])
        institutional = compute_institutional_demo(last_close)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Prediction Ledger + public scorecard ---
    prediction_ledger = None
    try:
        close_by_date = {ts.strftime('%Y-%m-%d'): float(c)
                         for ts, c in zip(df['timestamp'], df['close'])}
        seed_ledger_from_backtest(trades)
        record_predictions(as_of, last_close, all_outlook, quant['regime']['regime'], source)
        resolve_predictions(close_by_date, as_of)
        prediction_ledger = compute_scorecard()
    except Exception:  # noqa
        traceback.print_exc()

    # --- BitMarkAI prediction core (1W–5Y, per-horizon weighting, triggers) ---
    bitmark = None
    try:
        trig = _forecast_trigger.get('reason')
        if not trig:
            hi_news = bool(news_sig and news_sig.get('n_high_impact', 0) >= 2)
            trig = 'event' if (abs(day_change) >= 5.0 or hi_news) else 'scheduled'
        bitmark = compute_bitmark(quant, cycle, last_close, trigger=trig)
        _forecast_trigger['reason'] = None
    except Exception:  # noqa
        traceback.print_exc()

    doc = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.datetime.utcnow().isoformat(),
        'as_of': live_row['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'data_source': source,
        'pair': 'BTC/USD',
        'last_close': round(last_close, 2),
        'day_change_pct': day_change,
        'signal': 'UP' if pred == 1 else 'DOWN',
        'confidence': confidence,
        'prob_up': round(p_up * 100, 2),
        'prob_down': round(p_down * 100, 2),
        'overall_accuracy': overall_acc,
        'cv_folds': cv_folds,
        'cv_mean': round(float(np.mean([f['accuracy'] for f in cv_folds])), 2),
        'importances': importances,
        'performance': performance,
        'features': feature_snapshot,
        'n_samples': int(len(X)),
        'history_days': int((train_df['timestamp'].iloc[-1] - train_df['timestamp'].iloc[0]).days),
        'first_date': train_df['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'predict_for_date': predict_for,
        'scoreboard': scoreboard,
        'trades': recent_trades,
        'live_record': live_record,
        'quant_score': quant['quant_score'],
        'quant_label': quant['quant_label'],
        'quant_breakdown': quant['quant_breakdown'],
        'regime': quant['regime'],
        'forecasts': quant['forecasts'],
        'long_outlook': quant.get('long_outlook', []),
        'factors': quant['factors'],
        'decision': decision,        'news_forecast_link': news_forecast_link,
        'data_health': data_health,
        'event_calendar': event_calendar,
        'risk': risk,
        'smart_money': smart_money,
        'institutional': institutional,
        'prediction_ledger': prediction_ledger,
        'bitmark': bitmark,
        'cycle': cycle,
        'dominance': dominance,
        'chart': chart,
        'market_intel': market_intel,
        'crossmarket': crossmarket,
        'policy': policy,
        'alerts': alerts,
    }

    # --- Smart Alerts: detect state changes vs the previous run ---
    smart_alerts = None
    try:
        prev_doc = runs_col.find_one(sort=[('created_at', -1)])
        smart_alerts = compute_smart_alerts(doc, prev_doc)
    except Exception:  # noqa
        traceback.print_exc()
    doc['smart_alerts'] = get_smart_alerts()

    # --- Time Machine replay payload (stored only, not sent in dashboard) ---
    try:
        price_series = [{'date': ts.strftime('%Y-%m-%d'), 'close': round(float(c), 2)}
                        for ts, c in zip(df['timestamp'], df['close'])]
        replay = build_replay_payload(trades, price_series)
    except Exception:  # noqa
        traceback.print_exc()
        replay = None

    to_store = dict(doc)
    to_store['_id'] = doc['id']
    to_store['replay'] = replay
    # keep the full smart-alert feed out of the heavy run doc snapshot
    to_store.pop('smart_alerts', None)
    runs_col.insert_one(to_store)
    return doc


def run_compute_bg():
    with _lock:
        if _state['status'] == 'running':
            return
        _state['status'] = 'running'
        _state['error'] = None
        _state['started_at'] = datetime.datetime.utcnow().isoformat()
    try:
        compute()
        _state['status'] = 'done'
    except Exception as e:  # noqa
        _state['status'] = 'error'
        _state['error'] = str(e)
        traceback.print_exc()


@app.on_event('startup')
def _startup():
    try:
        scheduler = BackgroundScheduler(timezone='UTC')
        scheduler.add_job(run_compute_bg, 'cron', hour=0, minute=5, id='daily_refresh')
        scheduler.add_job(run_news_bg, 'interval', hours=1, id='news_refresh')
        scheduler.start()
    except Exception:  # noqa
        traceback.print_exc()
    if runs_col.count_documents({}) == 0:
        threading.Thread(target=run_compute_bg, daemon=True).start()
    if news_col.count_documents({}) == 0:
        threading.Thread(target=run_news_bg, daemon=True).start()


@app.get('/api/v1/health')
def health():
    return {'status': 'ok', 'compute_status': _state['status'], 'error': _state['error'],
            'runs': runs_col.count_documents({})}


@app.get('/api/v1/ticker')
def ticker(symbol: str = 'BTC'):
    import time
    symbol = (symbol or 'BTC').strip().upper()[:6]
    pair = 'BTC/USD' if symbol == 'BTC' else f'{symbol}/USD'
    now = time.time()
    cache = _ticker_cache.get(symbol)
    if cache and cache.get('data') and (now - cache['ts']) < 8:
        return cache['data']

    def usd_aud():
        if _fx_cache['rate'] and (now - _fx_cache['ts']) < 1800:
            return _fx_cache['rate']
        try:
            s = fetch_yahoo_series('AUD=X', '5d')
            rate = float(s.iloc[-1])
            if rate > 0:
                _fx_cache['rate'] = rate
                _fx_cache['ts'] = now
        except Exception:  # noqa
            traceback.print_exc()
        return _fx_cache['rate']

    for name in ['kraken', 'coinbase']:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            t = ex.fetch_ticker(pair)
            last = float(t['last'])
            pct = t.get('percentage')
            if pct is None and t.get('open'):
                pct = (last - float(t['open'])) / float(t['open']) * 100
            rate = usd_aud()
            data = {
                'symbol': symbol,
                'price': round(last, 2),
                'price_aud': round(last * rate, 2) if rate else None,
                'aud_rate': round(rate, 4) if rate else None,
                'change24h': round(float(pct), 2) if pct is not None else 0.0,
                'high': round(float(t.get('high') or last), 2),
                'low': round(float(t.get('low') or last), 2),
                'source': name,
                'ts': datetime.datetime.utcnow().isoformat(),
            }
            _ticker_cache[symbol] = {'data': data, 'ts': now}
            return data
        except Exception:  # noqa
            continue
    return {'price': None, 'error': 'ticker unavailable'}


@app.get('/api/v1/dashboard')
def dashboard(symbol: str = 'BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        if symbol not in COMPARE_COINS:
            return {'status': 'error', 'error': 'unsupported_symbol'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        cached = coin_dash_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('data'):
            return {'status': 'ready', 'compute_status': 'done', **cached['data']}
        st = _coin_dash_state.get(symbol)
        if st != 'running':
            threading.Thread(target=run_coin_dash_bg, args=(symbol,), daemon=True).start()
        if st == 'error':
            return {'status': 'error', 'error': 'compute_failed'}
        return {'status': 'computing'}
    doc = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
    if not doc:
        st = _state['status']
        return {'status': 'error' if st == 'error' else 'computing', 'error': _state['error']}
    # Add smart_alerts to the response (not stored in the run doc to save space)
    doc['smart_alerts'] = get_smart_alerts()
    return {'status': 'ready', 'compute_status': _state['status'], **doc}


@app.post('/api/v1/refresh')
def refresh():
    threading.Thread(target=run_compute_bg, daemon=True).start()
    return {'status': 'started'}


@app.get('/api/v1/news')
def news(symbol: str = 'BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        if symbol not in COMPARE_COINS:
            return {'status': 'error', 'error': 'unsupported_symbol'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        cached = coin_news_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('doc'):
            return {'status': 'ready', 'news_status': 'done', **cached['doc']}
        st = _coin_news_state.get(symbol)
        if st != 'running':
            threading.Thread(target=run_coin_news_bg, args=(symbol,), daemon=True).start()
        if st == 'error':
            return {'status': 'error', 'error': 'news_failed'}
        return {'status': 'computing'}
    doc = news_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
    if not doc:
        if _news_state['status'] not in ('running',):
            threading.Thread(target=run_news_bg, daemon=True).start()
        return {'status': 'error' if _news_state['status'] == 'error' else 'computing', 'error': _news_state['error']}
    return {'status': 'ready', 'news_status': _news_state['status'], **doc}


@app.post('/api/v1/news/refresh')
def news_refresh():
    threading.Thread(target=run_news_bg, daemon=True).start()
    return {'status': 'started'}


@app.get('/api/v1/chat/history')
def chat_history(session_id: str):
    msgs = list(chat_col.find({'session_id': session_id}, {'_id': 0}).sort('created_at', 1))
    return {'session_id': session_id, 'messages': msgs}


@app.get('/api/v1/scorecard')
def scorecard():
    try:
        return {'status': 'ready', **compute_scorecard()}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/alerts')
def alerts_feed(limit: int = 50):
    try:
        return {'status': 'ready', **get_smart_alerts(limit)}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'alerts': [], 'unseen': 0}


@app.post('/api/v1/alerts/ack')
def alerts_ack(payload: dict = Body(default={})):
    ids = (payload or {}).get('ids')
    try:
        if ids:
            smart_alerts_col.update_many({'id': {'$in': ids}}, {'$set': {'seen': True}})
        else:
            smart_alerts_col.update_many({'seen': False}, {'$set': {'seen': True}})
        return {'status': 'ok', 'unseen': smart_alerts_col.count_documents({'seen': False})}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/replay')
def replay(date: str = None, window: int = 30):
    try:
        run = runs_col.find_one(sort=[('created_at', -1)])
        rp = (run or {}).get('replay') or {}
        if not date:
            # default to the most recent replayable date
            date = rp.get('max_date')
        if not date:
            return {'status': 'unavailable', 'message': 'No replay data yet.'}
        return replay_for_date(date, window=window)
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/scenarios')
def scenarios():
    try:
        return get_scenarios()
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'scenarios': []}


@app.post('/api/v1/bitmark/run')
def bitmark_run(payload: dict = Body(default={})):
    import time
    passcode = (payload or {}).get('passcode', '')
    if passcode != ADMIN_PASSCODE:
        audit_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                              'action': 'manual_forecast_run', 'result': 'denied', 'reason': 'bad_passcode'})
        return {'status': 'unauthorized',
                'message': 'A valid admin passcode is required to trigger a manual forecast run. Enter it in Settings.'}
    now = time.time()
    cooldown = 300  # rate limit: one manual forecast every 5 minutes
    elapsed = now - _bitmark_last_manual['ts']
    if elapsed < cooldown:
        wait = int(cooldown - elapsed)
        return {'status': 'rate_limited', 'retry_in': wait,
                'message': f'A manual forecast can only be run once every {cooldown // 60} minutes — please wait {wait}s. This stops re-running until you get an answer you like.'}
    if _state['status'] == 'running':
        return {'status': 'busy', 'message': 'A forecast is already running — please wait for it to finish.'}
    _bitmark_last_manual['ts'] = now
    _forecast_trigger['reason'] = 'manual'
    audit_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                          'action': 'manual_forecast_run', 'result': 'started', 'trigger': 'manual'})
    threading.Thread(target=run_compute_bg, daemon=True).start()
    return {'status': 'started',
            'message': 'Running a fresh BitMarkAI forecast against the latest data (~30s). The updated ranges and a "what changed" summary will appear when it completes.'}


@app.get('/api/v1/audit')
def audit_log(limit: int = 20):
    items = list(audit_col.find({}, {'_id': 0}).sort('ts', -1).limit(limit))
    return {'status': 'ready', 'entries': items}


@app.post('/api/v1/chat')
def chat_endpoint(payload: dict = Body(...)):
    session_id = (str(payload.get('session_id') or uuid.uuid4()))[:80]
    message = (payload.get('message') or '').strip()[:2000]
    if not message:
        return {'error': 'empty message', 'text': 'Please type a question.'}
    if not (EMERGENT_LLM_KEY and _HAS_LLM):
        return {'error': 'llm_unconfigured',
                'text': 'The Ask Quant chat model is not configured on this server.'}
    try:
        ctx = build_chat_context((payload.get('symbol') or 'BTC'))
        hist = list(chat_col.find({'session_id': session_id}, {'_id': 0}).sort('created_at', 1))
        hist_txt = ''
        for h in hist[-5:]:
            hist_txt += f"User: {h.get('user')}\nQuant: {h.get('assistant')}\n"
        user_text = (f"Recent conversation:\n{hist_txt}\n" if hist_txt else '') + f"Question: {message}"
        chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f'askquant-{session_id}',
                        system_message=CHAT_SYSTEM.format(ctx=ctx))
                .with_model('gemini', CHAT_MODEL)
                .with_params(temperature=0.2, max_tokens=700))
        reply = asyncio.run(chat.send_message(UserMessage(text=user_text)))
        text = (getattr(reply, 'text', None) or str(reply)).strip()
        chat_col.insert_one({'_id': str(uuid.uuid4()), 'session_id': session_id,
                             'user': message, 'assistant': text, 'model': CHAT_MODEL,
                             'created_at': datetime.datetime.utcnow().isoformat()})
        return {'session_id': session_id, 'text': text, 'model': CHAT_MODEL}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'error': 'chat_failed',
                'text': 'Sorry — I could not answer that just now. Please try again in a moment.'}


# =====================================================================
# ALBERT SECTION INSIGHTS  (AI-generated, cached per compute-run)
# =====================================================================
ALBERT_INSIGHT_SYSTEM = (
    "You are 'Albert', the friendly HuCentAI Quant analyst in the BTCIQ Bitcoin dashboard. You are explaining "
    "this section to a curious NON-TRADER who does not know market jargon. Your goal is to be genuinely "
    "INSIGHTFUL — do NOT simply restate the numbers already on screen. Instead:\n"
    "1) Explain in plain English WHAT is actually driving Bitcoin right now / WHY it is where it is (lean on "
    "the news drivers, factors, macro and regime).\n"
    "2) Explain what that could mean going forward.\n"
    "3) Give ONE or TWO concrete 'if this happens, then this is the likely outcome' scenarios using the real "
    "price levels, invalidation points and odds in the data (e.g. 'if BTC holds $X, the model's Y% up case "
    "strengthens; if it loses $X, expect ...').\n"
    "Rules: use ONLY the live dashboard data below — never invent numbers, prices or events. Any term a "
    "beginner might not know, explain in 3-4 words. Always frame the future as probabilities/odds, never "
    "certainties, and never give direct buy/sell financial advice. Warm, clear, professor-like. "
    "Do NOT open with a greeting or salutation (no 'Hello', 'Hi', 'Hey', 'Hello there', and do not address "
    "the reader) — start immediately with the substance. "
    "Write 80-130 words, at most two short paragraphs. Do not use markdown headers or bullet symbols.\n\n"
    "THIS SECTION'S FOCUS: {focus}\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)

ALBERT_TECH_SYSTEM = (
    "You are 'Albert', the HuCentAI Quant analyst in the BTCIQ Bitcoin dashboard, now giving a MORE TECHNICAL "
    "briefing for a reader who understands markets. Be precise and quantitative:\n"
    "1) Reference the concrete numbers — scores, probabilities, confidence, backtest hit-rates, key price levels, "
    "invalidation points, regime/volatility read, and any relevant macro/liquidity or on-chain style signals.\n"
    "2) Explain the mechanism / what is driving the read, and how the signal groups reconcile (agreement vs conflict).\n"
    "3) State the actionable levels and the specific 'if BTC does X vs level Y, then Z' conditions the model watches.\n"
    "Rules: use ONLY the live dashboard data below — never invent numbers, prices or events. You may use standard "
    "trading terms without dumbing them down, but stay rigorous. Always frame outcomes as probabilities, never "
    "certainties, and never give direct buy/sell financial advice. Do NOT open with a greeting or salutation "
    "(no 'Hello', 'Hi', 'Hey') — start immediately with the analysis. Write 90-150 words, tight and information-dense, "
    "no markdown headers or bullet symbols.\n\n"
    "THIS SECTION'S FOCUS: {focus}\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)


SECTION_FOCUS = {
    'overview': "The big-picture read on Bitcoin: what is pushing the price now and what it likely means over the next day to week.",
    'forecasts': "The short and medium-term forecasts: what the odds imply, and what price action would confirm or break each call.",
    'analysis': "The Quant Score breakdown: which forces (trend, momentum, macro, etc.) are pushing Bitcoin and what their balance means.",
    'performance': "The model's real track record: how much a beginner should trust the current calls, and why.",
    'chart': "The chart structure and key support/resistance levels: what a break above or below them would likely lead to.",
    'cycle': "The 4-year halving cycle and BTC dominance: what this stage has historically meant for the months ahead.",
    'policy': "Macro and liquidity: how interest rates, the US dollar and global liquidity are pushing or pulling Bitcoin.",
    'news': "The day's Bitcoin news: which stories actually matter for price and why.",
    'risk': "The current risk level: how big the swings could be and what could trigger a sharp move either way.",
}


def _latest_run_version():
    run = runs_col.find_one(sort=[('created_at', -1)], projection={'created_at': 1, 'as_of': 1})
    if not run:
        return None
    return str(run.get('created_at') or run.get('as_of') or '')


@app.get('/api/v1/albert/insight')
async def albert_insight(section: str = 'overview', mode: str = 'plain', refresh: int = 0, symbol: str = 'BTC'):
    section = (section or 'overview').strip().lower()[:40]
    mode = 'technical' if str(mode).lower().startswith('tech') else 'plain'
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cd = coin_dash_col.find_one({'_id': f'{symbol}:{today}'}, {'created_at': 1})
        version = str((cd or {}).get('created_at') or today) if cd else None
    else:
        version = _latest_run_version()
    if not version:
        return {'status': 'fallback', 'reason': 'no_data'}
    cache_id = f"{symbol}:{section}:{mode}:{version}"
    if not refresh:
        cached = insights_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('text'):
            return {'status': 'ready', 'section': section, 'mode': mode, 'text': cached['text'], 'model': cached.get('model'), 'generated_at': cached.get('created_at'), 'cached': True}
    if not (EMERGENT_LLM_KEY and _HAS_LLM):
        return {'status': 'fallback', 'reason': 'llm_unconfigured'}
    try:
        ctx = build_chat_context(symbol)
        focus = SECTION_FOCUS.get(section, "Explain what this section means for the asset's price and outlook in plain English.")
        sys_tmpl = ALBERT_TECH_SYSTEM if mode == 'technical' else ALBERT_INSIGHT_SYSTEM
        kind = 'technical briefing' if mode == 'technical' else 'insight'
        umsg = f"Write Albert's {kind} for the '{section}' section now, following all the rules."

        def _complete(t):
            return len(t.split()) >= 50 and t.rstrip()[-1:] in '.!?"\u201d)'

        # emergentintegrations streaming can occasionally return a truncated partial response,
        # so retry a few times and keep the first complete-looking (or longest) answer.
        best = ''
        for _ in range(3):
            chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f'insight-{section}-{mode}-{uuid.uuid4().hex[:10]}',
                            system_message=sys_tmpl.format(focus=focus, ctx=ctx))
                    .with_model('gemini', CHAT_MODEL)
                    .with_params(temperature=0.4, max_tokens=8000))
            reply = await chat.send_message(UserMessage(text=umsg))
            text = (getattr(reply, 'text', None) or str(reply)).strip()
            text = re.sub(r'^\s*(hello|hi|hey|greetings|good (?:morning|afternoon|evening))\b[^.!?\n]*[.!?,]?\s+', '', text, flags=re.I).lstrip()
            if len(text) > len(best):
                best = text
            if _complete(text):
                best = text
                break
        text = best
        if not text:
            return {'status': 'fallback', 'reason': 'empty'}
        # Only cache complete responses so an occasional partial regenerates on the next load.
        now_iso = datetime.datetime.utcnow().isoformat()
        if _complete(text):
            insights_col.update_one(
                {'_id': cache_id},
                {'$set': {'_id': cache_id, 'section': section, 'mode': mode, 'version': version, 'text': text,
                          'model': CHAT_MODEL, 'created_at': now_iso}},
                upsert=True)
        return {'status': 'ready', 'section': section, 'mode': mode, 'text': text, 'model': CHAT_MODEL, 'generated_at': now_iso, 'cached': False}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'status': 'fallback', 'reason': 'error'}



# =====================================================================
# COMPARE COINS  (per-coin quant summary via the same pipeline, cached)
# =====================================================================
COMPARE_COINS = {
    'BTC': {'name': 'Bitcoin', 'pairs': [('kraken', 'BTC/USD'), ('coinbase', 'BTC/USD')]},
    'ETH': {'name': 'Ethereum', 'pairs': [('kraken', 'ETH/USD'), ('coinbase', 'ETH/USD')]},
    'SOL': {'name': 'Solana', 'pairs': [('kraken', 'SOL/USD'), ('coinbase', 'SOL/USD')]},
    'XRP': {'name': 'XRP', 'pairs': [('kraken', 'XRP/USD'), ('coinbase', 'XRP/USD')]},
    'ADA': {'name': 'Cardano', 'pairs': [('kraken', 'ADA/USD'), ('coinbase', 'ADA/USD')]},
    'DOGE': {'name': 'Dogecoin', 'pairs': [('kraken', 'DOGE/USD'), ('coinbase', 'DOGE/USD')]},
    'AVAX': {'name': 'Avalanche', 'pairs': [('kraken', 'AVAX/USD'), ('coinbase', 'AVAX/USD')]},
    'LINK': {'name': 'Chainlink', 'pairs': [('kraken', 'LINK/USD'), ('coinbase', 'LINK/USD')]},
    'DOT': {'name': 'Polkadot', 'pairs': [('kraken', 'DOT/USD'), ('coinbase', 'DOT/USD')]},
    'LTC': {'name': 'Litecoin', 'pairs': [('kraken', 'LTC/USD'), ('coinbase', 'LTC/USD')]},
    'MATIC': {'name': 'Polygon', 'pairs': [('kraken', 'MATIC/USD'), ('coinbase', 'MATIC/USD')]},
    'ATOM': {'name': 'Cosmos', 'pairs': [('kraken', 'ATOM/USD'), ('coinbase', 'ATOM/USD')]},
}


def _fetch_ohlcv_pairs(pairs):
    errors = []
    for name, sym in pairs:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            bars = ex.fetch_ohlcv(sym, timeframe='1d', limit=720)
            if bars and len(bars) > 250:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df.sort_values('timestamp').reset_index(drop=True), name
        except Exception as e:  # noqa
            errors.append(f'{name}: {e}')
    raise RuntimeError('All sources failed: ' + ' | '.join(errors))


def compute_coin_summary(symbol):
    cfg = COMPARE_COINS[symbol]
    df, source = _fetch_ohlcv_pairs(cfg['pairs'])
    df = build_features(df).dropna().reset_index(drop=True)
    feats = df.iloc[-1]
    last_close = float(df['close'].iloc[-1])
    prev_close = float(df['close'].iloc[-2])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)
    ts = df['timestamp'].iloc[-1]
    quant = compute_quant_analysis(df, feats, last_close, ts)
    fc = quant.get('forecasts', []) or []

    def _find(h):
        for f in fc:
            if f.get('horizon') == h:
                return f
        return {}
    f24 = _find('24H') or (fc[0] if fc else {})
    f7 = _find('7D')
    regime = quant.get('regime') or {}
    regime_name = regime.get('regime') if isinstance(regime, dict) else str(regime)
    support = resistance = None
    try:
        chart = compute_chart_intelligence(df)
        for lv in (chart.get('sr_levels') or []):
            if lv['type'] == 'support' and (support is None or lv['price'] > support):
                support = lv['price']  # nearest support below is highest support under price
            if lv['type'] == 'resistance' and (resistance is None or lv['price'] < resistance):
                resistance = lv['price']
    except Exception:  # noqa
        pass
    spark = [round(float(c), 4) for c in df['close'].tail(60).tolist()]
    return {
        'symbol': symbol, 'name': cfg['name'], 'source': source, 'as_of': ts.strftime('%Y-%m-%d'),
        'price': round(last_close, 2), 'day_change_pct': day_change,
        'quant_score': quant['quant_score'], 'quant_label': quant['quant_label'],
        'regime': regime_name,
        'forecast_24h': {'higher': f24.get('higher'), 'confidence': f24.get('confidence'), 'confidence_pct': f24.get('confidence_pct')},
        'forecast_7d': {'higher': f7.get('higher'), 'confidence': f7.get('confidence'), 'confidence_pct': f7.get('confidence_pct')},
        'bullish': (quant['factors']['bullish'] or [])[:2],
        'risk': (quant['factors']['risk'] or [])[:2],
        'support': support, 'resistance': resistance, 'spark': spark,
    }


@app.get('/api/v1/compare/coins')
def compare_coins_list():
    return {'coins': [{'symbol': k, 'name': v['name']} for k, v in COMPARE_COINS.items()]}


@app.get('/api/v1/compare/coin')
def compare_coin(symbol: str = 'BTC', refresh: int = 0):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol not in COMPARE_COINS:
        return {'status': 'error', 'reason': 'unsupported_symbol'}
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    cache_id = f"{symbol}:{today}"
    if not refresh:
        cached = compare_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('data'):
            return {'status': 'ready', 'cached': True, 'data': cached['data']}
    try:
        data = compute_coin_summary(symbol)
        compare_col.update_one({'_id': cache_id},
                               {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today, 'data': data,
                                         'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        return {'status': 'ready', 'cached': False, 'data': data}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'reason': str(ex)[:200]}



# =====================================================================
# GLOBAL COIN SWITCH — full per-coin dashboard (altcoins), isolated from
# the Bitcoin pipeline (no persistence, no BTC ledger writes).
# =====================================================================
_coin_dash_state = {}          # symbol -> 'running' | 'done' | 'error'
_coin_dash_lock = threading.Lock()


def compute_coin_dashboard(symbol):
    """Build a full dashboard payload for any supported coin using the same
    price-agnostic quant engine as Bitcoin. BTC-specific engines (halving cycle,
    dominance, policy, news, events, ETF/institutional) are left None because
    those views are hidden for altcoins in the UI."""
    cfg = COMPARE_COINS[symbol]
    df, source = _fetch_ohlcv_pairs(cfg['pairs'])
    df = build_features(df)
    df = df.dropna().reset_index(drop=True)
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)

    live_row = df.iloc[[-1]].copy()
    train_df = df.iloc[:-1].copy()
    X = train_df[FEATURE_COLS]
    y = train_df['Target']

    # TimeSeriesSplit cross validation
    tscv = TimeSeriesSplit(n_splits=5)
    cv_folds = []
    for i, (tr, te) in enumerate(tscv.split(X)):
        m = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr], y.iloc[tr])
        acc = accuracy_score(y.iloc[te], m.predict(X.iloc[te]))
        cv_folds.append({'fold': i + 1, 'accuracy': round(float(acc) * 100, 2), 'testSize': int(len(te))})

    # Walk-forward backtest -> accuracy over time + trade log
    start = 200 if len(X) > 260 else max(30, int(len(X) * 0.4))
    retrain_every = 10
    model = None
    rows = []
    trades = []
    closes_full = df['close'].reset_index(drop=True)
    for i in range(start, len(X)):
        if model is None or (i - start) % retrain_every == 0:
            model = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
            model.fit(X.iloc[:i], y.iloc[:i])
        classes = list(model.classes_)
        pred = int(model.predict(X.iloc[[i]])[0])
        proba = model.predict_proba(X.iloc[[i]])[0]
        conf = float(proba[classes.index(pred)]) * 100 if pred in classes else 50.0
        actual = int(y.iloc[i])
        cur_close = float(closes_full.iloc[i])
        nxt_close = float(closes_full.iloc[i + 1])
        d = train_df['timestamp'].iloc[i]
        rows.append({'date': d, 'correct': 1 if pred == actual else 0, 'close': cur_close})
        trades.append({
            'date': d.strftime('%Y-%m-%d'),
            'signal': 'UP' if pred == 1 else 'DOWN',
            'confidence': round(conf, 1),
            'close': round(cur_close, 2),
            'nextClose': round(nxt_close, 2),
            'actual': 'UP' if actual == 1 else 'DOWN',
            'correct': bool(pred == actual),
        })

    total = len(trades)
    wins = sum(1 for t in trades if t['correct'])
    losses = total - wins
    win_rate = round(wins / total * 100, 1) if total else 0.0
    best = cur = 0
    for t in trades:
        if t['correct']:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    sign = None
    streak_len = 0
    for t in reversed(trades):
        if sign is None:
            sign = t['correct']
            streak_len = 1
        elif t['correct'] == sign:
            streak_len += 1
        else:
            break
    scoreboard = {
        'total': total, 'wins': wins, 'losses': losses, 'winRate': win_rate,
        'bestWinStreak': best, 'currentStreak': (streak_len if sign else -streak_len),
    }
    recent_trades = list(reversed(trades))[:25]

    pser = pd.DataFrame(rows)
    pser['rolling_acc'] = pser['correct'].rolling(30, min_periods=10).mean() * 100
    overall_acc = round(float(pser['correct'].mean()) * 100, 2)
    performance = []
    for _, r in pser.iterrows():
        if pd.isna(r['rolling_acc']):
            continue
        d = r['date']
        performance.append({
            'date': d.strftime('%m/%d'),
            'iso': d.strftime('%Y-%m-%d'),
            'btcPrice': round(float(r['close']), 2),
            'aiAccuracy': round(float(r['rolling_acc']), 2),
        })

    final = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1)
    final.fit(X, y)
    live_X = live_row[FEATURE_COLS]
    pred = int(final.predict(live_X)[0])
    proba = final.predict_proba(live_X)[0]
    classes = list(final.classes_)
    p_up = float(proba[classes.index(1)]) if 1 in classes else 0.0
    p_down = float(proba[classes.index(0)]) if 0 in classes else 0.0
    confidence = round((p_up if pred == 1 else p_down) * 100, 2)

    importances = sorted(
        [{'feature': f, 'label': FEATURE_META[f]['label'], 'category': FEATURE_META[f]['category'],
          'importance': round(float(imp) * 100, 2)} for f, imp in zip(FEATURE_COLS, final.feature_importances_)],
        key=lambda z: -z['importance'],
    )

    feats = live_row.iloc[0]
    feature_snapshot = [
        {'feature': 'RSI', 'label': 'RSI (14)', 'category': 'Momentum', 'value': round(float(feats['RSI']) * 100, 1), 'unit': ''},
        {'feature': 'StochRSI', 'label': 'Stochastic RSI', 'category': 'Momentum', 'value': round(float(feats['StochRSI']) * 100, 1), 'unit': ''},
        {'feature': 'MACD_Hist_Norm', 'label': 'MACD Histogram', 'category': 'Trend', 'value': round(float(feats['MACD_Hist_Norm']) * 100, 3), 'unit': '%'},
        {'feature': 'EMA_Ratio', 'label': 'EMA 9/21 Spread', 'category': 'Trend', 'value': round(float(feats['EMA_Ratio']) * 100, 2), 'unit': '%'},
        {'feature': 'ATR_Pct', 'label': 'ATR %', 'category': 'Volatility', 'value': round(float(feats['ATR_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'BB_Width_Pct', 'label': 'Bollinger Width', 'category': 'Volatility', 'value': round(float(feats['BB_Width_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'Volume_Z', 'label': 'Volume Z-Score', 'category': 'Volume', 'value': round(float(feats['Volume_Z']), 2), 'unit': 'σ'},
        {'feature': 'Volume_Ratio', 'label': 'Volume Ratio', 'category': 'Volume', 'value': round(float(feats['Volume_Ratio']), 2), 'unit': 'x'},
    ]

    prev_close = float(train_df['close'].iloc[-1])
    last_close = float(live_row['close'].iloc[0])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)
    as_of = live_row['timestamp'].iloc[0].strftime('%Y-%m-%d')
    predict_for = (live_row['timestamp'].iloc[0] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

    quant = compute_quant_analysis(df, feats, last_close, live_row['timestamp'].iloc[0])

    chart = market_intel = decision = risk = alerts = None
    try:
        chart = compute_chart_intelligence(df)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        market_intel = build_market_intel(quant, quant['forecasts'], None, None, chart)
    except Exception:  # noqa
        traceback.print_exc()
    all_outlook = list(quant['forecasts']) + list(quant.get('long_outlook', []))
    try:
        decision = compute_decision_engine(quant, all_outlook, None, None, chart, None, None)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        risk = compute_risk_engine(quant, chart, decision, None, None, last_close, feats)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        alerts = compute_alerts(quant, None, None, chart, None)
    except Exception:  # noqa
        traceback.print_exc()
    dominance = None
    try:
        dominance = compute_coin_dominance(symbol, day_change)
    except Exception:  # noqa
        traceback.print_exc()

    doc = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.datetime.utcnow().isoformat(),
        'as_of': as_of,
        'symbol': symbol,
        'coin_name': cfg['name'],
        'data_source': source,
        'pair': f'{symbol}/USD',
        'last_close': round(last_close, 2),
        'day_change_pct': day_change,
        'signal': 'UP' if pred == 1 else 'DOWN',
        'confidence': confidence,
        'prob_up': round(p_up * 100, 2),
        'prob_down': round(p_down * 100, 2),
        'overall_accuracy': overall_acc,
        'cv_folds': cv_folds,
        'cv_mean': round(float(np.mean([f['accuracy'] for f in cv_folds])), 2),
        'importances': importances,
        'performance': performance,
        'features': feature_snapshot,
        'n_samples': int(len(X)),
        'history_days': int((train_df['timestamp'].iloc[-1] - train_df['timestamp'].iloc[0]).days),
        'first_date': train_df['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'predict_for_date': predict_for,
        'scoreboard': scoreboard,
        'trades': recent_trades,
        'quant_score': quant['quant_score'],
        'quant_label': quant['quant_label'],
        'quant_breakdown': quant['quant_breakdown'],
        'regime': quant['regime'],
        'forecasts': quant['forecasts'],
        'long_outlook': quant.get('long_outlook', []),
        'factors': quant['factors'],
        'decision': decision,
        'risk': risk,
        'chart': chart,
        'market_intel': market_intel,
        'alerts': alerts,
        # BTC-only engines (hidden for altcoins in UI)
        'live_record': None, 'news_forecast_link': None, 'data_health': None,
        'event_calendar': None, 'smart_money': None, 'institutional': None,
        'prediction_ledger': None, 'bitmark': None, 'cycle': None, 'dominance': dominance,
        'crossmarket': None, 'policy': None, 'smart_alerts': [],
    }
    return doc


def run_coin_dash_bg(symbol):
    with _coin_dash_lock:
        if _coin_dash_state.get(symbol) == 'running':
            return
        _coin_dash_state[symbol] = 'running'
    try:
        data = compute_coin_dashboard(symbol)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        coin_dash_col.update_one({'_id': cache_id},
                                 {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today, 'data': data,
                                           'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        _coin_dash_state[symbol] = 'done'
    except Exception:  # noqa
        _coin_dash_state[symbol] = 'error'
        traceback.print_exc()


# =====================================================================
# PER-COIN NEWS (altcoins) — same RSS + clustering + Gemini pipeline,
# coin-keyword filtered, cached per coin/day, isolated from BTC news.
# =====================================================================
COIN_NEWS_TERMS = {
    'ETH': ['ethereum', 'ether', 'vitalik', 'layer 2', 'staking', 'erc-20'],
    'SOL': ['solana'],
    'XRP': ['xrp', 'ripple'],
    'ADA': ['cardano'],
    'DOGE': ['dogecoin', 'doge'],
    'AVAX': ['avalanche', 'avax'],
    'LINK': ['chainlink'],
    'DOT': ['polkadot'],
    'LTC': ['litecoin'],
    'MATIC': ['polygon', 'matic'],
    'ATOM': ['cosmos'],
}
COIN_NEWS_SHARED = ['sec', 'etf', 'regulation', 'federal reserve', 'interest rate',
                    'rate cut', 'rate hike', 'inflation', 'cpi', 'stablecoin', 'coinbase',
                    'binance', 'blackrock', 'custody', 'fomc']

_coin_news_state = {}          # symbol -> 'running' | 'done' | 'error'
_coin_news_lock = threading.Lock()


def generate_coin_news_summary(name, headline, text):
    sysmsg = NEWS_SYSTEM.replace('Bitcoin', name)
    chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f'coinnews-{abs(hash(headline)) % 99999}',
                    system_message=sysmsg)
            .with_model('gemini', GEMINI_MODEL)
            .with_params(temperature=0.0, max_tokens=1200))
    reply = asyncio.run(chat.send_message(UserMessage(text=f'Headline: {headline}\n\nArticle:\n{text[:4000]}')))
    raw = (getattr(reply, 'text', None) or str(reply)).strip()
    if '```' in raw:
        raw = re.sub(r'```(?:json)?', '', raw).strip()
    s, e = raw.find('{'), raw.rfind('}')
    obj = json.loads(raw[s:e + 1])
    return obj


def build_coin_news(symbol):
    cfg = COMPARE_COINS[symbol]
    name = cfg['name']
    terms = [name.lower(), symbol.lower()] + COIN_NEWS_TERMS.get(symbol, [])
    match_terms = list(dict.fromkeys(terms + COIN_NEWS_SHARED))

    entries = []
    for sname, url, cred in NEWS_SOURCES:
        try:
            fp = feedparser.parse(url)
            for e in fp.entries[:14]:
                title = e.get('title', '')
                summ = re.sub('<[^>]+>', '', e.get('summary', e.get('description', '')))[:1400]
                blob = (title + ' ' + summ).lower()
                # keep coin-specific stories, plus macro stories from the Fed feed
                if not any(k in blob for k in terms) and not (sname == 'Federal Reserve'):
                    if not any(k in blob for k in match_terms):
                        continue
                entries.append({'source': sname, 'credibility': cred, 'title': title,
                                'summary': summ.strip(), 'link': e.get('link', ''),
                                'published': e.get('published', e.get('updated', ''))})
        except Exception:  # noqa
            traceback.print_exc()

    def _toks(t):
        stop = {'the', 'a', 'an', 'to', 'of', 'in', 'on', 'for', 'and', 'is', 'as', 'at',
                'by', 'it', 'be', 'with', 'from', 'that', 'this', 'its', 'are', 'will', 'has'}
        return set(w for w in re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower()).split()
                   if len(w) > 2 and w not in stop)

    clusters = []
    for e in entries:
        et = _toks(e['title'])
        if not et:
            continue
        placed = False
        for cl in clusters:
            inter = len(et & cl['tokens'])
            union = len(et | cl['tokens']) or 1
            if inter / union >= 0.34 or (inter >= 3 and inter >= 0.6 * min(len(et), len(cl['tokens']))):
                cl['members'].append(e)
                cl['tokens'] |= et
                placed = True
                break
        if not placed:
            clusters.append({'tokens': set(et), 'members': [e]})
    clusters.sort(key=lambda cl: (-len(set(m['source'] for m in cl['members'])),
                                  -max(m['credibility'] for m in cl['members'])))
    clusters = clusters[:6]

    SPEC_WORDS = ('rumor', 'rumour', 'reportedly', 'could ', 'may ', 'might', 'proposal',
                  'proposed', 'unconfirmed', 'alleged', 'speculat', 'plans to', 'considering',
                  'reports', 'said to', 'expected to')
    cards = []
    for cl in clusters:
        members = cl['members']
        rep = max(members, key=lambda m: m['credibility'])
        sources = [{'source': m['source'], 'link': m['link'], 'credibility': m['credibility'],
                    'published': m['published'], 'title': m['title']} for m in members]
        n_src = len(set(m['source'] for m in members))
        ai = None
        if EMERGENT_LLM_KEY and _HAS_LLM:
            try:
                ai = generate_coin_news_summary(name, rep['title'], rep['summary'] or rep['title'])
            except Exception:  # noqa
                traceback.print_exc()
        if not ai:
            ai = {'summary': (rep['summary'] or rep['title'])[:220], 'why_it_matters': '',
                  'direction': 'neutral', 'bullish_pct': 40, 'bearish_pct': 30, 'neutral_pct': 30,
                  'impact_score': 40, 'confidence': 0.4,
                  'time_horizons': {'immediate': 'neutral', 'seven_day': 'neutral', 'long_term': 'neutral'},
                  'categories': ['general']}
        try:
            imp = int(round(float(ai.get('impact_score', 40)) * (0.55 + 0.45 * rep['credibility'] / 100)))
        except Exception:  # noqa
            imp = 40
        imp = max(0, min(100, imp))
        imp_label = ('Market Moving' if imp >= 85 else 'High Impact' if imp >= 70 else 'Important'
                     if imp >= 50 else 'Monitor' if imp >= 30 else 'Low Significance')
        blob = (rep['title'] + ' ' + (rep['summary'] or '')).lower()
        speculative = any(w in blob for w in SPEC_WORDS)
        max_cred = max(m['credibility'] for m in members)
        if n_src >= 2 and max_cred >= 65 and not speculative:
            verification = 'Confirmed'
        elif speculative or max_cred < 55:
            verification = 'Unconfirmed'
        else:
            verification = 'Single-source'
        dirn = ai.get('direction', 'neutral')
        sign = 1 if dirn == 'bullish' else -1 if dirn == 'bearish' else 0
        nudge = round(sign * imp / 100 * 3.0, 1)
        forecast_impact = {
            'direction': dirn, 'nudge_pts': nudge,
            'horizons': ['24H', '7D'] if imp >= 50 else ['24H'],
            'note': (f'Nudges near-term higher-odds by {"+" if nudge > 0 else ""}{nudge} pts'
                     if nudge else 'No material push to the near-term odds') + ' (model interpretation).',
        }
        cards.append({**rep, 'ai': ai, 'impact': imp, 'impact_label': imp_label,
                      'sources': sources, 'n_sources': n_src,
                      'verification': verification, 'forecast_impact': forecast_impact})
    cards.sort(key=lambda c: -c['impact'])

    bull = sum(1 for c in cards if c['ai'].get('direction') == 'bullish')
    bear = sum(1 for c in cards if c['ai'].get('direction') == 'bearish')
    bias = 'Moderately Bullish' if bull > bear else 'Moderately Bearish' if bear > bull else 'Mixed / Neutral'
    tail = next((c for c in cards if c['ai'].get('direction') == 'bullish'), None)
    risk = next((c for c in cards if c['ai'].get('direction') == 'bearish'), None)
    briefing = {
        'bias': bias, 'total': len(cards),
        'major_stories': sum(1 for c in cards if c['impact'] >= 70),
        'market_moving': sum(1 for c in cards if c['impact'] >= 85),
        'top_tailwind': (tail['ai'].get('why_it_matters') or tail['title']) if tail else f'No clear {name} tailwind in the current feed.',
        'top_risk': (risk['ai'].get('why_it_matters') or risk['title']) if risk else f'No clear {name} risk in the current feed.',
        'next_event': None,
    }
    doc = {'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
           'symbol': symbol, 'coin_name': name, 'cards': cards, 'briefing': briefing,
           'model': (GEMINI_MODEL if (EMERGENT_LLM_KEY and _HAS_LLM) else 'rule-based')}
    return doc


def run_coin_news_bg(symbol):
    with _coin_news_lock:
        if _coin_news_state.get(symbol) == 'running':
            return
        _coin_news_state[symbol] = 'running'
    try:
        doc = build_coin_news(symbol)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        coin_news_col.update_one({'_id': cache_id},
                                 {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today,
                                           'doc': doc, 'created_at': datetime.datetime.utcnow().isoformat()}},
                                 upsert=True)
        _coin_news_state[symbol] = 'done'
    except Exception:  # noqa
        _coin_news_state[symbol] = 'error'
        traceback.print_exc()

