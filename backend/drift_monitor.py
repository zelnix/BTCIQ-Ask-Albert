"""Pillar 2 — Feature Drift Monitoring & Model-Failover Circuit Breaker.

Pure-Python (numpy/scipy) drift detection used by the daily ML pipeline in
server.py. Compares the RECENT feature window against the TRAINING baseline
using the Population Stability Index (PSI) and a two-sample Kolmogorov-Smirnov
(KS) test. If the market has drifted outside the training distribution — or if
the live data feeds are incomplete — the caller trips a circuit breaker that:

  * downgrades the displayed model confidence to "Low", and
  * falls back from dynamic ML weighting to a conservative rule-based
    trend-following signal.

No external services, no new infrastructure.
"""

import numpy as np

try:  # scipy is already a dependency (scikit-learn); KS via scipy when available
    from scipy.stats import ks_2samp
    _HAS_SCIPY = True
except Exception:  # noqa
    _HAS_SCIPY = False

# ---- thresholds (industry-standard PSI bands) ----
PSI_WATCH = 0.10        # minor shift — worth watching
PSI_BREAK = 0.25        # significant shift — trip the circuit breaker
COMPLETENESS_MIN = 95.0  # % of core feeds that must be healthy


def calculate_psi(expected, actual, num_buckets=10):
    """Population Stability Index between a baseline (expected) and a recent
    (actual) sample of a single feature. Bins are quantile-cut on the baseline."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < num_buckets or len(actual) == 0:
        return 0.0
    percentiles = np.linspace(0, 100, num_buckets + 1)
    bins = np.percentile(expected, percentiles)
    bins = np.unique(bins)
    if len(bins) < 3:  # near-constant feature — no meaningful distribution
        return 0.0
    bins[0], bins[-1] = -np.inf, np.inf

    expected_pct = np.histogram(expected, bins=bins)[0] / len(expected)
    actual_pct = np.histogram(actual, bins=bins)[0] / len(actual)

    # avoid zero-division / log(0)
    expected_pct = np.where(expected_pct == 0, 1e-4, expected_pct)
    actual_pct = np.where(actual_pct == 0, 1e-4, actual_pct)

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(round(psi, 4))


def calculate_ks(expected, actual):
    """Two-sample KS statistic + significance flag (alpha=0.05).

    Returns (ks_stat, p_value, significant). Falls back to a manual ECDF-based
    statistic (with the asymptotic 1.36 critical value) if scipy is missing."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    n, m = len(expected), len(actual)
    if n < 5 or m < 5:
        return 0.0, 1.0, False
    if _HAS_SCIPY:
        try:
            res = ks_2samp(expected, actual)
            stat = float(res.statistic)
            pval = float(res.pvalue)
            return round(stat, 4), round(pval, 4), bool(pval < 0.05)
        except Exception:  # noqa
            pass
    # manual ECDF KS statistic
    grid = np.sort(np.concatenate([expected, actual]))
    cdf_e = np.searchsorted(np.sort(expected), grid, side='right') / n
    cdf_a = np.searchsorted(np.sort(actual), grid, side='right') / m
    stat = float(np.max(np.abs(cdf_e - cdf_a)))
    crit = 1.36 * np.sqrt((n + m) / (n * m))  # alpha ~ 0.05
    return round(stat, 4), None, bool(stat > crit)


def _feed_completeness(data_health):
    """Percentage of CORE data feeds that are healthy (live or degraded, i.e.
    not stale/down). Returns (completeness_pct, missing_labels)."""
    if not data_health:
        return 100.0, []
    feeds = [f for f in (data_health.get('feeds') or []) if f.get('core')]
    if not feeds:
        # fall back to the health score if per-feed detail is absent
        return float(data_health.get('score', 100)), []
    healthy = [f for f in feeds if f.get('status') in ('live', 'degraded')]
    missing = [f.get('label') for f in feeds if f.get('status') in ('stale', 'down')]
    pct = round(100.0 * len(healthy) / len(feeds), 1)
    return pct, missing


def _rule_based_signal(live_feats):
    """Conservative trend-following fallback (no ML). Uses the EMA 9/21 spread as
    the primary trend direction with the MACD histogram as confirmation."""
    ema = float(live_feats.get('EMA_Ratio', 0.0) or 0.0)
    macd = float(live_feats.get('MACD_Hist_Norm', 0.0) or 0.0)
    rsi = float(live_feats.get('RSI', 0.5) or 0.5)  # normalised 0-1 in this engine
    if ema > 0 and macd >= 0:
        direction = 'UP'
    elif ema < 0 and macd <= 0:
        direction = 'DOWN'
    else:
        direction = 'NEUTRAL'
    # conviction from how far RSI sits from the 0.5 midpoint, capped low & humble
    conviction = int(round(min(60.0, 50.0 + abs(rsi - 0.5) * 40.0)))
    return {'signal': direction, 'confidence': conviction,
            'basis': 'EMA 9/21 trend + MACD confirmation (conservative rule-based)'}


try:
    from scipy.stats import chi2 as _chi2
    _HAS_CHI2 = True
except Exception:  # noqa
    _HAS_CHI2 = False

# Multivariate out-of-distribution thresholds
OOD_Z = 5.0            # per-feature robust |z| that counts as an extreme feature
OOD_Z_COUNT = 2        # how many extreme features constitute an OOD live point
OOD_MAHA_Q = 0.9995    # chi-square quantile for the Mahalanobis OOD gate


def _ood_live(X, feature_cols, live_feats):
    """Is the CURRENT live feature vector outside the model's TRAINING
    distribution? The model retrains daily on the full history, so the right
    'drift' question for this architecture is whether TODAY's inputs are a
    genuine anomaly vs everything the model has seen — not whether the market
    slowly evolved (which is normal and does not break the model).

    Uses robust per-feature z-scores (median / MAD) plus a multivariate
    Mahalanobis-distance gate. Returns (is_ood, detail_dict)."""
    detail = {'robust_z': {}, 'extreme_features': [], 'mahalanobis': None,
              'maha_threshold': None}
    try:
        cols = [c for c in feature_cols if c in X.columns and c in live_feats]
        if not cols or len(X) < 60:
            return False, detail
        base = X[cols].astype(float)
        med = base.median()
        mad = (base - med).abs().median() * 1.4826
        mad = mad.replace(0, np.nan)
        extreme = []
        for c in cols:
            m = mad.get(c)
            if m is None or not np.isfinite(m) or m == 0:
                z = 0.0
            else:
                z = float((live_feats[c] - med[c]) / m)
            detail['robust_z'][c] = round(z, 2)
            if abs(z) >= OOD_Z:
                extreme.append(c)
        detail['extreme_features'] = extreme

        # Multivariate Mahalanobis distance of the live vector vs training.
        maha_ood = False
        try:
            mu = base.mean().values
            cov = np.cov(base.values, rowvar=False)
            cov = cov + np.eye(cov.shape[0]) * 1e-6  # regularise
            inv = np.linalg.pinv(cov)
            x = np.array([live_feats[c] for c in cols], dtype=float)
            diff = x - mu
            maha2 = float(diff.T @ inv @ diff)
            detail['mahalanobis'] = round(maha2, 2)
            if _HAS_CHI2:
                thr = float(_chi2.ppf(OOD_MAHA_Q, df=len(cols)))
            else:
                thr = len(cols) + 6.0 * np.sqrt(2 * len(cols))  # ~99.9% approx
            detail['maha_threshold'] = round(thr, 2)
            maha_ood = maha2 > thr
        except Exception:  # noqa
            pass

        is_ood = (len(extreme) >= OOD_Z_COUNT) or maha_ood
        return bool(is_ood), detail
    except Exception:  # noqa
        import traceback
        traceback.print_exc()
        return False, detail



def assess(X, feature_cols, feature_meta=None, data_health=None, live_feats=None,
           ml_signal=None, ml_confidence=None, recent=21, reference=189):
    """Full drift assessment + circuit-breaker decision for one pipeline run.

    X: training feature DataFrame (rows = daily bars, cols include feature_cols).
    Returns a JSON-serialisable dict attached to the dashboard run doc.

    Design: a circuit breaker must catch ABRUPT structural shocks (de-pegs,
    crashes, exchange outages, regulatory shocks) — NOT the slow, natural
    evolution of the market. So we compare a SHORT recent window (~3 weeks)
    against the window IMMEDIATELY PRECEDING it (~6 months) — a rolling
    "now vs recent-normal" test — rather than against ancient history (which
    would always look 'drifted'). PSI is noisy on small samples, so we use
    5 quantile buckets and require BOTH PSI > 0.25 AND a significant two-sample
    KS test before a feature counts as genuinely drifted. This keeps the daily
    false-positive rate low."""
    feature_meta = feature_meta or {}
    live_feats = live_feats or {}
    num_buckets = 5
    per_feature = []
    max_psi = 0.0
    drifted = []          # confirmed drift (PSI + KS)
    watch_only = []       # PSI elevated but not KS-confirmed
    rec = int(recent)
    ref_len = None
    try:
        n = len(X)
        rec = min(recent, max(10, n // 6))
        if n >= (rec + 40):
            ref = min(reference, n - rec)
            baseline = X.iloc[-(rec + ref):-rec]   # window preceding the recent one
            actual = X.iloc[-rec:]                  # most-recent window ("now")
        else:  # not enough history — compare last-third vs the rest
            cut = max(5, n // 3)
            baseline = X.iloc[:-cut]
            actual = X.iloc[-cut:]
        ref_len = int(len(baseline))
        for c in feature_cols:
            if c not in X.columns:
                continue
            psi = calculate_psi(baseline[c].values, actual[c].values, num_buckets)
            ks_stat, ks_p, ks_sig = calculate_ks(baseline[c].values, actual[c].values)
            confirmed = (psi > PSI_BREAK and ks_sig)
            if confirmed:
                status = 'drift'
                drifted.append(c)
            elif psi > PSI_WATCH:
                status = 'watch'
                watch_only.append(c)
            else:
                status = 'stable'
            max_psi = max(max_psi, psi)
            per_feature.append({
                'feature': c,
                'label': (feature_meta.get(c) or {}).get('label', c),
                'category': (feature_meta.get(c) or {}).get('category'),
                'psi': psi,
                'ks_stat': ks_stat,
                'ks_p': ks_p,
                'ks_significant': ks_sig,
                'status': status,
            })
        per_feature.sort(key=lambda z: -z['psi'])
    except Exception:  # noqa
        import traceback
        traceback.print_exc()

    completeness, missing_feeds = _feed_completeness(data_health)
    fallback = _rule_based_signal(live_feats)

    # --- Breaker driver: is TODAY's live vector out-of-distribution vs training? ---
    # (PSI/KS above are reported as descriptive "what shifted" diagnostics; the
    #  actual trip is driven by a robust OOD test on the live point, which does
    #  not fire on normal slow market evolution.)
    is_ood, ood = _ood_live(X, feature_cols, live_feats)

    distribution_shift = len(drifted) >= 1        # KS-confirmed window shift (diagnostic)
    feed_breach = completeness < COMPLETENESS_MIN
    ood_breach = bool(is_ood)
    breaker = bool(ood_breach or feed_breach)

    reasons = []
    if ood_breach:
        ex = ood.get('extreme_features') or []
        if ex:
            zt = ', '.join(f"{(feature_meta.get(c) or {}).get('label', c)} (z {ood['robust_z'].get(c)})" for c in ex)
            reasons.append(f"Live inputs outside training distribution — extreme feature(s): {zt}.")
        if ood.get('mahalanobis') is not None and ood.get('maha_threshold') is not None \
                and ood['mahalanobis'] > ood['maha_threshold']:
            reasons.append(f"Multivariate anomaly: Mahalanobis {ood['mahalanobis']} > {ood['maha_threshold']} gate.")
    if feed_breach:
        miss = (', '.join(missing_feeds) if missing_feeds else 'one or more core feeds')
        reasons.append(f"Data completeness {completeness}% < {COMPLETENESS_MIN}% (unhealthy: {miss}).")

    if breaker:
        overall_status = 'breaker'
        confidence_level = 'Low'
    elif distribution_shift or watch_only or completeness < 100.0:
        overall_status = 'watch'
        confidence_level = 'Guarded'
    else:
        overall_status = 'stable'
        confidence_level = 'Normal'

    if breaker:
        model_mode = 'rule_based'
        effective_signal = fallback['signal']
        effective_confidence = fallback['confidence']
    else:
        model_mode = 'ml'
        effective_signal = ml_signal
        effective_confidence = ml_confidence

    headline = {
        'stable': 'Inputs in-distribution and feeds healthy — full ML model in use.',
        'watch': 'Some feature drift detected — ML model live but monitored closely.',
        'breaker': 'Circuit breaker TRIPPED — inputs out-of-distribution / feeds degraded; reverted to conservative rule-based trend model.',
    }[overall_status]

    return {
        'status': overall_status,
        'circuit_breaker': breaker,
        'confidence_level': confidence_level,
        'max_psi': round(max_psi, 4),
        'psi_watch_threshold': PSI_WATCH,
        'psi_break_threshold': PSI_BREAK,
        'drifted_features': drifted,
        'watch_features': watch_only,
        'ood': ood,
        'ood_breach': ood_breach,
        'data_completeness_pct': completeness,
        'completeness_min': COMPLETENESS_MIN,
        'missing_feeds': missing_feeds,
        'per_feature': per_feature,
        'model_mode': model_mode,
        'ml_signal': ml_signal,
        'ml_confidence': ml_confidence,
        'fallback_signal': fallback,
        'effective_signal': effective_signal,
        'effective_confidence': effective_confidence,
        'reasons': reasons,
        'headline': headline,
        'recent_window': int(rec),
        'reference_window': ref_len,
    }
