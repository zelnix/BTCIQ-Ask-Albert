"""Market phase assessment - BTC-led, altcoin-led, mixed or unknown.

Two things are kept rigorously apart everywhere in this product:

  * the ASSESSED phase, produced here from evidence by a versioned rule, and
  * the user's WHAT-IF season lens, which is an assumption they choose to explore.

This module only produces the former. It never reads a user assumption, and a user
assumption can never overwrite its output.

The rule uses relative performance and BREADTH over the documented universe - not a
single index and not turnover. Turnover is available to the caller as context only:
volume alone must not be able to declare an altcoin season.

The thresholds below are a documented product rule, not a validated market law. They are
versioned so a change is visible, and MIXED and UNKNOWN are first-class answers rather
than failures.
"""
from albert.market import meta as M

PHASE_RULE_VERSION = 'market-phase-v1'

MIN_ALTS_WITH_RETURNS = 20      # below this the breadth measure is not meaningful
BREADTH_HIGH = 0.60             # share of eligible alts beating BTC
BREADTH_LOW = 0.40
SPREAD_PCT = 3.0                # median alt return minus BTC return, percentage points
WINDOW_FIELD = {'7d': 'change7dPct', '30d': 'change30dPct'}


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def assess(uni, window='7d'):
    """Classify the phase over `window`. Returns the result plus every input used, so the
    classification can be audited rather than believed."""
    field = WINDOW_FIELD.get(window, 'change7dPct')
    base = {'ruleVersion': PHASE_RULE_VERSION, 'window': window,
            'universeVersion': (uni or {}).get('universeVersion'),
            'universeSnapshotId': (uni or {}).get('snapshotId'),
            'assessedAt': M.now_iso(),
            'asOf': (uni or {}).get('sourceTimestamp'),
            'thresholds': {'breadthHigh': BREADTH_HIGH, 'breadthLow': BREADTH_LOW,
                           'spreadPct': SPREAD_PCT,
                           'minAltsWithReturns': MIN_ALTS_WITH_RETURNS},
            'evidenceRefs': [r for r in [(uni or {}).get('evidenceRef')] if r]}

    btc = (uni or {}).get('btc') or {}
    btc_ret = btc.get(field)
    rets = [(a['symbol'], a.get(field)) for a in ((uni or {}).get('alts') or [])]
    rets = [(s, v) for s, v in rets if v is not None]

    if btc_ret is None or len(rets) < MIN_ALTS_WITH_RETURNS:
        return {**base, 'phase': M.UNKNOWN, 'status': M.MISSING,
                'reasonCode': 'INSUFFICIENT_RETURN_COVERAGE',
                'inputs': {'btcReturnPct': btc_ret, 'altsWithReturns': len(rets)},
                'limitations': [
                    'A phase cannot be assessed: %s return coverage is available for only '
                    '%d eligible altcoins (minimum %d) or the Bitcoin return itself is '
                    'missing.' % (window, len(rets), MIN_ALTS_WITH_RETURNS),
                    'Unknown is a real result here, not a placeholder for a guess.']}

    beating = [s for s, v in rets if v > btc_ret]
    breadth = len(beating) / float(len(rets))
    med = _median([v for _s, v in rets])
    spread = med - btc_ret

    if breadth >= BREADTH_HIGH and spread >= SPREAD_PCT:
        phase, why = M.ALTCOIN_LED, (
            '%d of %d eligible altcoins (%.0f%%) outperformed Bitcoin over %s and the '
            'median altcoin return was %.1f points ahead of it.'
            % (len(beating), len(rets), breadth * 100, window, spread))
    elif breadth <= BREADTH_LOW and spread <= -SPREAD_PCT:
        phase, why = M.BTC_LED, (
            'Only %d of %d eligible altcoins (%.0f%%) outperformed Bitcoin over %s and the '
            'median altcoin return was %.1f points behind it.'
            % (len(beating), len(rets), breadth * 100, window, abs(spread)))
    else:
        phase, why = M.MIXED, (
            '%.0f%% of eligible altcoins outperformed Bitcoin over %s and the median '
            'altcoin return was %.1f points from it - neither side is clearly leading.'
            % (breadth * 100, window, spread))

    return {**base, 'phase': phase, 'status': M.FRESH, 'reasonCode': None,
            'finding': why,
            'inputs': {'btcReturnPct': round(btc_ret, 2),
                       'medianAltReturnPct': round(med, 2),
                       'spreadPct': round(spread, 2),
                       'breadth': M.dec_str(breadth, 4),
                       'altsBeatingBtc': len(beating),
                       'altsWithReturns': len(rets)},
            'invalidation': ('This assessment changes if breadth crosses %.0f%%/%.0f%% or '
                             'the median altcoin-versus-Bitcoin spread crosses %s%.1f '
                             'points.' % (BREADTH_LOW * 100, BREADTH_HIGH * 100,
                                          chr(177), SPREAD_PCT)),
            'limitations': list((uni or {}).get('limitations') or []) + [
                'Thresholds are a documented product rule (%s), not a validated market '
                'law.' % PHASE_RULE_VERSION,
                'Percentage changes come from the market-cap aggregator and are not '
                'recomputed from candles here.',
                'Turnover share is deliberately excluded from this classification; it is '
                'context only.']}
