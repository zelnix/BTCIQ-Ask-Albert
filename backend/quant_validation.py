"""Quant-grade validation engine.

Purged & Embargoed walk-forward cross-validation (removes look-ahead leakage from the
forward-looking Triple-Barrier labels) + statistical significance metrics that correct for
data-snooping: Probabilistic Sharpe Ratio (PSR), Deflated Sharpe Ratio (DSR), annualised
Sharpe, max drawdown, and a rolling Brier-score decay monitor.

Adapted to our daily-bar pipeline (positional PurgedKFold, ATR-scaled triple-barrier labels
with realised path returns). Runs inside the daily compute() job; result cached and served
via GET /api/v1/validation.
"""
import traceback

import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss

ANNUALIZE = np.sqrt(365.0)  # one label per daily bar


def _atr_frac(df, period=14):
    high, low, close = df['high'].astype(float), df['low'].astype(float), df['close'].astype(float)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    return (atr / close)


def _triple_barrier(df, h, pt_mult=1.5, sl_mult=1.0):
    """Returns (labels 0/1, realised path returns) for an h-bar horizon."""
    c = df['close'].to_numpy(float)
    hi = df['high'].to_numpy(float)
    lo = df['low'].to_numpy(float)
    a = _atr_frac(df).to_numpy(float)
    n = len(c)
    lab = np.full(n, np.nan)
    ret = np.full(n, np.nan)
    for i in range(n):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = c[i]
        up_b, dn_b = entry * (1 + pt_mult * a[i]), entry * (1 - sl_mult * a[i])
        end = min(i + h, n - 1)
        L, ex = None, c[end]
        for j in range(i + 1, end + 1):
            uh, lh = hi[j] >= up_b, lo[j] <= dn_b
            if uh and lh:
                L, ex = 0, dn_b
                break
            if uh:
                L, ex = 1, up_b
                break
            if lh:
                L, ex = 0, dn_b
                break
        if L is None:
            L = 1 if c[end] > entry else 0
            ex = c[end]
        lab[i] = L
        ret[i] = (ex - entry) / entry
    return pd.Series(lab, index=df.index), pd.Series(ret, index=df.index)


class PurgedKFold:
    """Positional purged & embargoed K-Fold for horizon-h forward labels."""

    def __init__(self, n_splits=5, horizon=5, pct_embargo=0.01):
        self.n_splits = n_splits
        self.horizon = horizon
        self.pct_embargo = pct_embargo

    def split(self, n):
        idx = np.arange(n)
        embargo = int(n * self.pct_embargo)
        folds = np.array_split(idx, self.n_splits)
        for fold in folds:
            test_idx = fold
            t0, t1 = test_idx[0], test_idx[-1]
            # purge: drop training bars whose [i, i+h] label window overlaps the test block,
            # plus an embargo band after the test block.
            lo = t0 - self.horizon
            hi = t1 + embargo
            train_idx = idx[(idx + self.horizon < lo) | (idx > hi)]
            if len(train_idx) > 20 and len(test_idx) > 5:
                yield train_idx, test_idx


def _psr(returns, benchmark_sr=0.0):
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 10 or r.std() == 0:
        return None
    sr = (r.mean() / r.std()) * ANNUALIZE
    sk = float(skew(r))
    kt = float(kurtosis(r, fisher=True))
    denom = (1 + (0.5 * sr ** 2) - (sk * sr) + ((kt / 4.0) * sr ** 2))
    if denom <= 0:
        return None
    sr_std = np.sqrt(denom / (len(r) - 1))
    if sr_std == 0:
        return None
    return float(norm.cdf((sr - benchmark_sr) / sr_std))


def _dsr(returns, num_trials=30, var_trials=0.5):
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 10 or r.std() == 0:
        return None
    e_max = np.sqrt(var_trials) * (
        (1 - 0.5772156649) * norm.ppf(1 - 1.0 / num_trials)
        + 0.5772156649 * norm.ppf(1 - 1.0 / (num_trials * np.e)))
    return _psr(r, benchmark_sr=e_max)


def _coverage_history(df, feature_cols, horizon=5, alpha=0.10, bucket=7):
    """Walk the CQR corridor over history and report the corridor's REAL hit-rate bucketed
    into ~weekly windows, so users can see whether the 90% band holds up week over week."""
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        data = df.dropna(subset=feature_cols).reset_index(drop=True)
        close = data['close'].astype(float)
        n = len(data)
        y = (close.shift(-horizon) / close - 1.0)
        X = data[feature_cols]
        valid = y.notna()
        X, y = X[valid].reset_index(drop=True), y[valid].reset_index(drop=True)
        m = len(X)
        if m < 200:
            return []
        cut = int(m * 0.6)
        q_lo, q_hi = alpha / 2.0, 1.0 - alpha / 2.0
        gl = GradientBoostingRegressor(loss='quantile', alpha=q_lo, n_estimators=60, max_depth=3,
                                       learning_rate=0.05, random_state=42).fit(X.iloc[:cut], y.iloc[:cut])
        gh = GradientBoostingRegressor(loss='quantile', alpha=q_hi, n_estimators=60, max_depth=3,
                                       learning_rate=0.05, random_state=42).fit(X.iloc[:cut], y.iloc[:cut])
        # conformal q_hat on the first half of the holdout, evaluate coverage on the rest
        cal_end = cut + int((m - cut) * 0.4)
        lo_c = gl.predict(X.iloc[cut:cal_end]); hi_c = gh.predict(X.iloc[cut:cal_end])
        yc = y.iloc[cut:cal_end].to_numpy()
        scores = np.maximum(lo_c - yc, yc - hi_c)
        k = min(max(int(np.ceil((len(scores) + 1) * (1 - alpha))), 1), len(scores))
        q_hat = float(np.sort(scores)[k - 1])
        Xev, yev = X.iloc[cal_end:], y.iloc[cal_end:].to_numpy()
        lo_e = gl.predict(Xev) - q_hat; hi_e = gh.predict(Xev) + q_hat
        hit = ((yev >= lo_e) & (yev <= hi_e)).astype(int)
        out = []
        for i in range(0, len(hit), bucket):
            chunk = hit[i:i + bucket]
            if len(chunk) >= 3:
                out.append({'week': len(out) + 1, 'coverage': round(float(chunk.mean()) * 100, 1),
                            'n': int(len(chunk))})
        return out[-16:]  # last ~16 weeks
    except Exception:  # noqa
        traceback.print_exc()
        return []


def run_validation(df, feature_cols, horizon=5, n_splits=5):
    """Purged walk-forward OOF validation + significance metrics on triple-barrier trades."""
    try:
        data = df.dropna(subset=feature_cols).reset_index(drop=True)
        y, ret = _triple_barrier(data, horizon)
        mask = y.notna() & ret.notna()
        # keep only bars with a fully-formed forward window
        mask.iloc[len(data) - horizon:] = False
        data, y, ret = data[mask].reset_index(drop=True), y[mask].reset_index(drop=True), ret[mask].reset_index(drop=True)
        X = data[feature_cols]
        n = len(X)
        if n < 200 or y.nunique() < 2:
            return None

        oof_prob = np.full(n, np.nan)
        oof_pred = np.full(n, np.nan)
        cv = PurgedKFold(n_splits=n_splits, horizon=horizon)
        for tr, te in cv.split(n):
            ytr = y.iloc[tr]
            if ytr.nunique() < 2:
                continue
            model = HistGradientBoostingClassifier(max_iter=100, learning_rate=0.05, random_state=42)
            model.fit(X.iloc[tr], ytr)
            oof_prob[te] = model.predict_proba(X.iloc[te])[:, 1]
            oof_pred[te] = model.predict(X.iloc[te])

        vm = np.isfinite(oof_prob)
        if vm.sum() < 50:
            return None
        y_true = y.to_numpy()[vm].astype(int)
        y_prob = oof_prob[vm]
        y_pred = oof_pred[vm]
        r = ret.to_numpy()[vm]
        strat = np.where(y_pred == 1, 1.0, -1.0) * r

        brier = float(brier_score_loss(y_true, y_prob))
        psr = _psr(strat)
        dsr = _dsr(strat, num_trials=30)
        sr = float((strat.mean() / strat.std()) * ANNUALIZE) if strat.std() else 0.0
        cum = np.cumsum(strat)
        mdd = float((cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0

        # rolling 60-trade Brier decay
        se = pd.Series((y_true - y_prob) ** 2)
        roll = se.rolling(60, min_periods=20).mean().dropna()
        roll_hist = [round(float(v), 4) for v in roll.iloc[-60:].tolist()]
        slope = 0.0
        if len(roll) >= 20:
            xx = np.arange(len(roll))
            slope = float(np.polyfit(xx, roll.to_numpy(), 1)[0])

        def _pf(v):
            return None if v is None else round(v, 4)

        return {
            'n_trades': int(vm.sum()),
            'horizon_bars': horizon,
            'brier_score': round(brier, 4),
            'probabilistic_sharpe_ratio': _pf(psr),
            'deflated_sharpe_ratio': _pf(dsr),
            'annualized_sharpe': round(sr, 2),
            'max_drawdown_pct': round(mdd * 100, 2),
            'rolling_brier_slope': round(slope, 6),
            'rolling_brier_history': roll_hist,
            'coverage_history': _coverage_history(df, feature_cols, horizon=horizon, alpha=0.10),
            'coverage_history_by_horizon': {
                lbl: _coverage_history(df, feature_cols, horizon=hb, alpha=0.10)
                for lbl, hb in [('24H', 1), ('7D', 7), ('30D', 30)]
            },
            'coverage_target': int(round((1 - 0.10) * 100)),
            'benchmarks': {
                'brier_pass': brier < 0.20,
                'psr_pass': (psr is not None and psr > 0.95),
                'dsr_pass': (dsr is not None and dsr > 0.90),
                'brier_decay_pass': slope <= 0,
            },
            'thresholds': {'brier': 0.20, 'psr': 0.95, 'dsr': 0.90, 'brier_decay_slope': 0.0},
        }
    except Exception:  # noqa
        traceback.print_exc()
        return None
