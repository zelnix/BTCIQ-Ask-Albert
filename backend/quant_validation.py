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
