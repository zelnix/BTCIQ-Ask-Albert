"""Comparable-historical-window scenario provider (N-B).

WHAT THIS IS. Given an asset's closed daily candles, it describes today's market
conditions with a small set of strictly trailing features, finds the historical days that
most resembled today, and reads the distribution of what actually happened next. The
bullish and bearish paths are the 80th and 20th percentiles of those realised forward
returns, anchored to today's observed close.

WHAT THIS IS NOT. It is not a prediction, not a probability and not a target. The output
is deliberately labelled a *conditional historical scenario* until forward validation
justifies stronger language. Two paths are not the set of possible outcomes: sideways
outcomes and moves beyond either path remain possible, and the response says so.

DESIGN DECISIONS THAT PROTECT HONESTY
  * Point-in-time features only. Every feature at index i uses candles up to i and
    nothing after it.
  * No data-derived scaling. Features are divided by FIXED declared constants rather than
    z-scored against the whole series, because a full-series z-score quietly leaks the
    future into the past.
  * Purged matching. Days within +/- the horizon of the query are excluded, so an
    overlapping window cannot be matched to itself.
  * Known outcomes only. A day is a candidate only if its full forward horizon already
    happened.
  * Minimum sample enforced. Below it the provider returns unavailable rather than a
    confident-looking path built from five observations.
  * The season/phase lens is NOT a model input in v1 and says so, because claiming a
    driver moved a path requires that driver to be part of the numeric method.
"""
import math
import statistics

MODEL_VERSION = 'historical-analog-scenario-v1'
WARMUP = 90                 # candles needed before the first usable feature vector
MIN_SAMPLE = 40             # matched days below which no path is returned
TOP_FRACTION = 0.10         # take the most similar 10% of candidates, floored at MIN_SAMPLE
BULL_PCTL, MID_PCTL, BEAR_PCTL = 80, 50, 20

# Fixed feature scales. These are part of the model version: changing one changes the
# model. They are rough typical magnitudes for daily crypto, chosen once and frozen -
# never fitted to the series being queried.
FEATURES = (
    ('mom20', 0.20, 1.0),      # 20-day return
    ('mom60', 0.35, 1.0),      # 60-day return
    ('vol20', 0.03, 1.0),      # stdev of daily log returns, 20-day
    ('dd90', 0.25, 1.0),       # drawdown from the trailing 90-day high
    ('maDist50', 0.15, 1.0),   # distance from the 50-day average
    ('rsi14', 30.0, 0.5),      # Wilder RSI, trailing only
)
MIN_FEATURES_PRESENT = 5


def _sma(closes, i, n):
    if i + 1 < n:
        return None
    return sum(closes[i - n + 1:i + 1]) / float(n)


def _rsi(closes, i, n=14):
    if i < n:
        return None
    gains = losses = 0.0
    for k in range(i - n + 1, i + 1):
        ch = closes[k] - closes[k - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - (100.0 / (1.0 + rs))


def features_at(closes, i):
    """Strictly trailing condition fingerprint for day i. None for anything not yet
    computable - never zero-filled, because zero is a value and absence is not."""
    if i < WARMUP:
        return None
    f = {}
    f['mom20'] = (closes[i] / closes[i - 20] - 1.0) if closes[i - 20] else None
    f['mom60'] = (closes[i] / closes[i - 60] - 1.0) if closes[i - 60] else None
    rets = []
    for k in range(i - 19, i + 1):
        if closes[k - 1] > 0 and closes[k] > 0:
            rets.append(math.log(closes[k] / closes[k - 1]))
    f['vol20'] = statistics.pstdev(rets) if len(rets) >= 15 else None
    hi = max(closes[max(0, i - 89):i + 1])
    f['dd90'] = (closes[i] / hi - 1.0) if hi else None
    ma = _sma(closes, i, 50)
    f['maDist50'] = (closes[i] / ma - 1.0) if ma else None
    f['rsi14'] = _rsi(closes, i)
    if f['rsi14'] is not None:
        f['rsi14'] = f['rsi14'] - 50.0      # centre so "neutral" is zero
    return f


def _distance(a, b):
    """Weighted Euclidean distance over the features BOTH days have. Returns None when
    too few are shared for the comparison to mean anything."""
    tot = wsum = 0.0
    used = 0
    for name, scale, weight in FEATURES:
        x, y = a.get(name), b.get(name)
        if x is None or y is None:
            continue
        d = (x - y) / scale
        tot += weight * d * d
        wsum += weight
        used += 1
    if used < MIN_FEATURES_PRESENT or wsum == 0:
        return None
    return math.sqrt(tot / wsum)


def _pctl(sorted_vals, p):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _candidates(closes, query_i, horizon, *, cutoff=None):
    """Usable historical days: warmed up, forward outcome already known, and purged of
    anything overlapping the query window."""
    last = (cutoff if cutoff is not None else len(closes) - 1)
    out = []
    for i in range(WARMUP, last - horizon + 1):
        if abs(i - query_i) <= horizon:
            continue
        out.append(i)
    return out


def _match(closes, query_i, horizon, *, cutoff=None):
    q = features_at(closes, query_i)
    if not q:
        return None, 'INSUFFICIENT_HISTORY'
    scored = []
    for i in _candidates(closes, query_i, horizon, cutoff=cutoff):
        fi = features_at(closes, i)
        if not fi:
            continue
        d = _distance(q, fi)
        if d is None:
            continue
        scored.append((d, i))
    if len(scored) < MIN_SAMPLE:
        return None, 'INSUFFICIENT_COMPARABLE_SAMPLE'
    scored.sort()
    k = max(MIN_SAMPLE, int(len(scored) * TOP_FRACTION))
    return scored[:k], None


def _forward_paths(closes, matches, horizon):
    """Realised cumulative-return path for each matched day, day 1..horizon."""
    paths = []
    for _d, i in matches:
        base = closes[i]
        if base <= 0:
            continue
        row = []
        ok = True
        for h in range(1, horizon + 1):
            j = i + h
            if j >= len(closes):
                ok = False
                break
            row.append(closes[j] / base - 1.0)
        if ok:
            paths.append(row)
    return paths


def build(*, closes, dates, horizon, anchor_price=None, cutoff=None):
    """Produce the scenario distribution for the most recent (or `cutoff`) day.

    Returns either {'ok': False, 'reason': ...} or a dict with the bullish/median/bearish
    return paths, the matched-sample description and the similarity spread.
    """
    if not closes or len(closes) < WARMUP + horizon + MIN_SAMPLE:
        return {'ok': False, 'reason': 'INSUFFICIENT_HISTORY',
                'detail': 'Need at least %d daily candles; %d available.'
                          % (WARMUP + horizon + MIN_SAMPLE, len(closes or []))}
    qi = cutoff if cutoff is not None else len(closes) - 1
    matches, err = _match(closes, qi, horizon, cutoff=cutoff)
    if err:
        return {'ok': False, 'reason': err,
                'detail': ('Fewer than %d comparable historical days with a known %d-day '
                           'outcome could be found.' % (MIN_SAMPLE, horizon))}
    paths = _forward_paths(closes, matches, horizon)
    if len(paths) < MIN_SAMPLE:
        return {'ok': False, 'reason': 'INSUFFICIENT_COMPARABLE_SAMPLE',
                'detail': 'Only %d matched days had a complete forward window.' % len(paths)}
    anchor = float(anchor_price if anchor_price is not None else closes[qi])
    bull, mid, bear = [], [], []
    for h in range(horizon):
        col = sorted(p[h] for p in paths)
        bull.append(_pctl(col, BULL_PCTL))
        mid.append(_pctl(col, MID_PCTL))
        bear.append(_pctl(col, BEAR_PCTL))
    sims = [1.0 / (1.0 + d) for d, _i in matches]
    # Matched days OVERLAP: two adjacent calendar days share almost all of their forward
    # window, so 40 matches is not 40 independent observations. Count the distinct
    # episodes (runs separated by more than one horizon) and report that instead of
    # letting the raw count imply more evidence than exists.
    idxs = sorted(i for _d, i in matches)
    episodes = 1 if idxs else 0
    for a, b in zip(idxs, idxs[1:]):
        if b - a > horizon:
            episodes += 1
    lims = []
    if episodes < 10:
        lims.append('The %d matched days collapse into only %d distinct historical episodes, '
                    'so the effective sample is much smaller than the day count suggests.'
                    % (len(paths), episodes))
    pool = len(_candidates(closes, qi, horizon, cutoff=cutoff))
    if pool < 300:
        lims.append('Only %d historical days with a known %d-day outcome are available for '
                    'this asset, which is a short record to generalise from.'
                    % (pool, horizon))
    return {
        'ok': True, 'modelVersion': MODEL_VERSION, 'horizonDays': horizon,
        'anchorPrice': anchor, 'anchorDate': dates[qi] if dates and qi < len(dates) else None,
        'sampleSize': len(paths), 'independentEpisodes': episodes,
        'candidatePool': pool,
        'sampleLimitations': lims,
        'similarity': {'best': round(max(sims), 4), 'worstUsed': round(min(sims), 4),
                       'median': round(statistics.median(sims), 4)},
        'matchedDates': [dates[i] for _d, i in matches[:8] if dates and i < len(dates)],
        'returnPaths': {'bullish': bull, 'median': mid, 'bearish': bear},
        'endpoints': {'bullishPct': round(bull[-1] * 100, 2),
                      'medianPct': round(mid[-1] * 100, 2),
                      'bearishPct': round(bear[-1] * 100, 2)},
        'percentiles': {'bullish': BULL_PCTL, 'median': MID_PCTL, 'bearish': BEAR_PCTL},
        'features': [n for n, _s, _w in FEATURES],
    }


def evaluate(*, closes, dates, horizon, eval_days=180, stride=3):
    """Chronological walk-forward evaluation. No look-ahead: at each evaluation day the
    match set is rebuilt from days strictly before it, purged of the overlapping window.

    Reported against a no-change baseline, because an interval that is merely wide is not
    skill and a median path that merely says "flat" must be shown to beat saying nothing.
    """
    last_usable = len(closes) - horizon - 1
    start = max(WARMUP + MIN_SAMPLE + horizon, last_usable - eval_days)
    if last_usable <= start:
        return {'ok': False, 'reason': 'INSUFFICIENT_HISTORY_FOR_EVALUATION'}
    covered = total = 0
    errs, base_errs, widths = [], [], []
    regimes = {'up': 0, 'down': 0, 'flat': 0}
    for qi in range(start, last_usable + 1, stride):
        res = build(closes=closes, dates=dates, horizon=horizon, cutoff=qi)
        if not res.get('ok'):
            continue
        realised = closes[qi + horizon] / closes[qi] - 1.0
        bull = res['returnPaths']['bullish'][-1]
        bear = res['returnPaths']['bearish'][-1]
        mid = res['returnPaths']['median'][-1]
        total += 1
        if bear <= realised <= bull:
            covered += 1
        errs.append(abs(mid - realised))
        base_errs.append(abs(realised))          # no-change baseline predicts 0%
        widths.append(bull - bear)
        m20 = closes[qi] / closes[qi - 20] - 1.0 if closes[qi - 20] else 0.0
        regimes['up' if m20 > 0.05 else ('down' if m20 < -0.05 else 'flat')] += 1
    if total < 20:
        return {'ok': False, 'reason': 'INSUFFICIENT_EVALUATION_POINTS', 'points': total}
    mae = statistics.median(errs)
    base_mae = statistics.median(base_errs)
    return {
        'ok': True, 'modelVersion': MODEL_VERSION, 'horizonDays': horizon,
        'method': ('Chronological walk-forward. At each evaluation day the comparable set '
                   'is rebuilt using only prior days, purged of the overlapping window.'),
        'evaluationPoints': total, 'stride': stride,
        'firstEvaluatedAt': dates[start] if dates else None,
        'lastEvaluatedAt': dates[last_usable] if dates else None,
        'intervalCoverageRate': round(covered / float(total), 4),
        'intervalCoverageTarget': round((BULL_PCTL - BEAR_PCTL) / 100.0, 2),
        'medianIntervalWidthPct': round(statistics.median(widths) * 100, 2),
        'medianAbsErrorPct': round(mae * 100, 3),
        'baselineMedianAbsErrorPct': round(base_mae * 100, 3),
        'skillVsNoChange': round(1.0 - (mae / base_mae), 4) if base_mae > 0 else None,
        'regimeCoverage': regimes,
        'interpretation': ('Coverage near the target means the band described the realised '
                           'outcome about as often as its percentiles claim. A skill score '
                           'at or below zero means the median path did not beat assuming no '
                           'change, and the paths must be read as descriptive history only.'),
    }
