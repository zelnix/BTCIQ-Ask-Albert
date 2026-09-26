"""Bitcoin versus altcoin SPOT TURNOVER SHARE - 24h, 7d and 30d.

The contract is deliberately narrow:

    btcShare = eligible BTC spot turnover / total eligible spot turnover
    altShare = eligible non-BTC spot turnover / total eligible spot turnover

over the documented universe (see universe.py). ETH is an altcoin here. Stablecoins are
not a bucket. Derivatives turnover and market-cap dominance are different measures and
are not mixed in.

A WORD ON THE 7d AND 30d WINDOWS. The upstream aggregator only publishes a rolling 24h
turnover figure, so a true 7d or 30d turnover total is not obtainable from it. Rather
than fabricate one, this module persists one daily snapshot of the 24h figure and reports
the multi-day windows as the mean of the snapshots it actually holds - labelled PARTIAL,
with the number of days covered, until the window is complete. It is a daily sample of a
rolling measure, not the true window total, and it says so.

Higher turnover is not bullish and a rising altcoin share is not proof that money rotated
out of Bitcoin. Nothing here asserts either.
"""
from decimal import Decimal

from albert.market import meta as M

VOLUME_RULE_VERSION = 'spot-turnover-share-v1'
WINDOWS = {'24h': 1, '7d': 7, '30d': 30}
MIN_ALTS_FOR_SHARE = 10


def _shares(btc_usd, alt_usd):
    total = btc_usd + alt_usd
    if total <= 0:
        return None, None, total
    return (btc_usd / total), (alt_usd / total), total


def live_totals(uni):
    """Today's eligible turnover, split into the two buckets. Returns None when the
    universe itself is unavailable - the denominator must never be guessed."""
    if not uni or uni.get('status') == M.MISSING or not uni.get('btc'):
        return None
    btc_v = uni['btc'].get('volume24hUsd')
    if btc_v is None:
        return None
    alts = [a for a in (uni.get('alts') or []) if a.get('volume24hUsd') is not None]
    if len(alts) < MIN_ALTS_FOR_SHARE:
        return None
    return {'btcUsd': Decimal(str(btc_v)),
            'altUsd': sum((Decimal(str(a['volume24hUsd'])) for a in alts), Decimal('0')),
            'altCount': len(alts)}


def daily_snapshot_row(uni, day):
    """The write-once daily row. Keyed by UTC date so a restart or a second call in the
    same day cannot double-count."""
    tot = live_totals(uni)
    if not tot:
        return None
    return {'_id': 'turnover:%s:%s' % (uni.get('universeVersion'), day),
            'date': day, 'btcUsd': str(tot['btcUsd']), 'altUsd': str(tot['altUsd']),
            'altCount': tot['altCount'], 'universeVersion': uni.get('universeVersion'),
            'snapshotId': uni.get('snapshotId'), 'source': uni.get('source'),
            'sourceTimestamp': uni.get('sourceTimestamp'),
            'recordedAt': M.now_iso()}


def _window_result(window, btc_usd, alt_usd, days_covered, days_required, *,
                   as_of, source, extra_limitations):
    btc_share, alt_share, total = _shares(btc_usd, alt_usd)
    if btc_share is None:
        return {'window': window, 'status': M.MISSING, 'reasonCode': 'ZERO_DENOMINATOR',
                'btcShare': None, 'altShare': None, 'totalTurnoverUsd': None,
                'daysCovered': days_covered, 'daysRequired': days_required,
                'limitations': ['No eligible turnover was measurable for this window, '
                                'so a share cannot be expressed.'] + extra_limitations}
    complete = days_covered >= days_required
    lim = list(extra_limitations)
    if not complete:
        lim.insert(0, 'Only %d of the %d days in this window have been sampled so far, '
                      'so this is an incomplete average rather than the full window.'
                   % (days_covered, days_required))
    if days_required > 1:
        lim.insert(0, 'Multi-day windows are the mean of one daily sample of the rolling '
                      '24h turnover figure, not a true summed window total.')
    return {'window': window,
            'status': M.FRESH if complete else M.PARTIAL,
            'reasonCode': None if complete else 'INCOMPLETE_WINDOW_COVERAGE',
            'btcShare': M.dec_str(btc_share), 'altShare': M.dec_str(alt_share),
            'totalTurnoverUsd': str(total.quantize(Decimal('1'))),
            'btcTurnoverUsd': str(btc_usd.quantize(Decimal('1'))),
            'altTurnoverUsd': str(alt_usd.quantize(Decimal('1'))),
            'daysCovered': days_covered, 'daysRequired': days_required,
            'asOf': as_of, 'source': source, 'limitations': lim}


def shares(uni, history_rows):
    """All three windows at once. `history_rows` are the persisted daily rows, newest
    first; the 24h window uses the live snapshot rather than a stored row so it is as
    fresh as the feed allows."""
    base_lims = ['Spot turnover only - derivatives turnover is excluded and is a '
                 'separate measure.',
                 'Turnover share is not a directional signal: a higher altcoin share '
                 'does not prove capital rotated out of Bitcoin.']
    if uni:
        base_lims = list(uni.get('limitations') or []) + base_lims

    tot = live_totals(uni)
    out = {}
    if not tot:
        out['24h'] = {'window': '24h', 'status': M.MISSING,
                      'reasonCode': (uni or {}).get('reasonCode') or 'NO_UNIVERSE_SNAPSHOT',
                      'btcShare': None, 'altShare': None, 'totalTurnoverUsd': None,
                      'daysCovered': 0, 'daysRequired': 1,
                      'limitations': ['The eligible turnover universe is not available, '
                                      'so no share can be calculated.'] + base_lims}
    else:
        out['24h'] = _window_result('24h', tot['btcUsd'], tot['altUsd'], 1, 1,
                                    as_of=(uni or {}).get('sourceTimestamp'),
                                    source=(uni or {}).get('source'),
                                    extra_limitations=base_lims)

    for name, days in (('7d', 7), ('30d', 30)):
        rows = (history_rows or [])[:days]
        if not rows:
            out[name] = {'window': name, 'status': M.MISSING,
                         'reasonCode': 'NO_DAILY_HISTORY',
                         'btcShare': None, 'altShare': None, 'totalTurnoverUsd': None,
                         'daysCovered': 0, 'daysRequired': days,
                         'limitations': ['No daily turnover snapshots have been recorded '
                                         'yet, so this window cannot be measured.'] + base_lims}
            continue
        btc_sum = sum((Decimal(str(r.get('btcUsd') or 0)) for r in rows), Decimal('0'))
        alt_sum = sum((Decimal(str(r.get('altUsd') or 0)) for r in rows), Decimal('0'))
        n = Decimal(len(rows))
        out[name] = _window_result(name, btc_sum / n, alt_sum / n, len(rows), days,
                                   as_of=rows[0].get('sourceTimestamp') or rows[0].get('recordedAt'),
                                   source=rows[0].get('source'),
                                   extra_limitations=base_lims)

    worst = M.FRESH
    for w in out.values():
        if w['status'] == M.MISSING:
            worst = M.MISSING
            break
        if w['status'] == M.PARTIAL:
            worst = M.PARTIAL
    return {'ruleVersion': VOLUME_RULE_VERSION,
            'measure': 'USD-equivalent spot turnover share',
            'buckets': 'BTC vs eligible non-BTC crypto (ETH counted as an altcoin)',
            'universeVersion': (uni or {}).get('universeVersion'),
            'universeSnapshotId': (uni or {}).get('snapshotId'),
            'status': worst, 'windows': out}
