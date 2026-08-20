"""Dynamic Regime-Switching Signal Weights (Gaussian HMM).

Replaces the previous *static* composite weights (Technicals 45% / Macro 20% /
Chart Structure 20% / News 15%) with **regime-conditioned dynamic weights**.

The market state at time t is modelled as a latent variable S_t in {1..K} across
K = 4 regimes:

    consolidation      -> Low-Vol Consolidation  (range / mean-reversion)
    bull_momentum      -> Bull Momentum          (trending up)
    bear_distribution  -> Bear Distribution       (trending down / risk-off)
    high_vol_squeeze   -> High-Vol Squeeze        (liquidation / event driven)

A Gaussian HMM is fit on a feature matrix of daily observations
[log_return_1d, log_return_5d, realized_vol_14d, parkinson_vol_14d].
Forward-backward inference yields smoothed posterior state probabilities
gamma_{k,t}. The regime-conditioned weight matrix W (K x M) is combined with the
state posterior to produce the dynamic weight vector:

    w_m = sum_k gamma_{k,t} * W_{k,m}    (then L1-normalised)

Stack adaptation vs. the reference blueprint (kept faithful to the maths, mapped
to our live infra): hmmlearn for the HMM, MongoDB (regime_col) for the state /
model cache, APScheduler (the existing daily compute() job) for the walk-forward
re-fit. No Redis / Celery / MLflow.
"""
import base64
import datetime
import pickle
import traceback

import numpy as np

try:
    from hmmlearn.hmm import GaussianHMM
    _HAS_HMM = True
except Exception:  # noqa
    _HAS_HMM = False

# Canonical regime order (indices are arbitrary until we label states by behaviour)
REGIME_NAMES = ["consolidation", "bull_momentum", "bear_distribution", "high_vol_squeeze"]
REGIME_LABELS = {
    "consolidation": "Low-Vol Consolidation",
    "bull_momentum": "Bull Momentum",
    "bear_distribution": "Bear Distribution",
    "high_vol_squeeze": "High-Vol Squeeze",
}
REGIME_DESCRIPTIONS = {
    "consolidation": "Range-bound, low realised volatility. Technicals and chart structure lead; macro/news carry little weight.",
    "bull_momentum": "Trending higher with constructive structure. Technicals and chart momentum dominate the signal.",
    "bear_distribution": "Risk-off distribution. Macro/policy and news flow carry the most weight; technicals fade.",
    "high_vol_squeeze": "Elevated volatility / event-driven squeeze. News and macro dominate; technicals least reliable.",
}

# The composite signals actually available to the decision engine.
SIGNALS = ["technicals", "macro_policy", "chart_structure", "news_flow"]

# Regime-conditioned prior weight matrix W (each row sums to 1.0).
REGIME_WEIGHT_MATRIX = {
    "consolidation":     {"technicals": 0.50, "chart_structure": 0.25, "macro_policy": 0.15, "news_flow": 0.10},
    "bull_momentum":     {"technicals": 0.40, "chart_structure": 0.30, "macro_policy": 0.20, "news_flow": 0.10},
    "bear_distribution": {"technicals": 0.20, "chart_structure": 0.20, "macro_policy": 0.35, "news_flow": 0.25},
    "high_vol_squeeze":  {"technicals": 0.15, "chart_structure": 0.20, "macro_policy": 0.30, "news_flow": 0.35},
}

# Static fallback (the legacy weights) — used only if the HMM is unavailable / errors.
STATIC_WEIGHTS = {"technicals": 0.45, "macro_policy": 0.20, "chart_structure": 0.20, "news_flow": 0.15}

_FEATURE_NAMES = ["log_return_1d", "log_return_5d", "realized_vol_14d", "parkinson_vol_14d"]


def extract_features(df):
    """Build the HMM observation matrix from the daily OHLC dataframe.

    Returns an (N, 4) float array of [ret_1d, ret_5d, realized_vol_14d, parkinson_vol_14d]
    with the initial NaN warm-up rows dropped.
    """
    close = np.asarray(df["close"], dtype=float)
    high = np.asarray(df["high"], dtype=float)
    low = np.asarray(df["low"], dtype=float)
    n = len(close)
    if n < 60:
        raise ValueError("not enough history for regime detection")

    logc = np.log(np.clip(close, 1e-9, None))
    ret1 = np.diff(logc, prepend=logc[0])
    # 5-day momentum (rolling sum of 1d log returns)
    ret5 = np.zeros(n)
    for i in range(n):
        ret5[i] = logc[i] - logc[max(0, i - 5)]
    # 14-day realised volatility (rolling std of 1d log returns)
    rv = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - 13)
        rv[i] = np.std(ret1[lo:i + 1]) if i >= 1 else 0.0
    # Parkinson volatility from the high/low range, 14d rolling mean
    hl = np.log(np.clip(high, 1e-9, None) / np.clip(low, 1e-9, None))
    park_inst = np.sqrt(np.clip(hl * hl / (4.0 * np.log(2.0)), 0, None))
    park = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - 13)
        park[i] = np.mean(park_inst[lo:i + 1])

    feats = np.column_stack([ret1, ret5, rv, park])
    feats = feats[14:]  # drop warm-up
    feats = np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)
    return feats


class DynamicRegimeEngine:
    """Fits a 4-state Gaussian HMM and maps latent states -> named regimes."""

    def __init__(self):
        self.model = None
        self.state_map = None      # hmm state index -> regime name
        self.fitted_at = None

    # ---- persistence (MongoDB via base64 pickle) ----
    def to_blob(self):
        return base64.b64encode(pickle.dumps({
            "model": self.model, "state_map": self.state_map,
            "fitted_at": self.fitted_at,
        })).decode("ascii")

    def load_blob(self, blob):
        try:
            d = pickle.loads(base64.b64decode(blob))
            self.model = d.get("model")
            self.state_map = d.get("state_map")
            self.fitted_at = d.get("fitted_at")
            return self.model is not None and self.state_map is not None
        except Exception:  # noqa
            traceback.print_exc()
            return False

    # ---- training ----
    def fit(self, feats):
        if not _HAS_HMM:
            raise RuntimeError("hmmlearn unavailable")
        model = GaussianHMM(n_components=4, covariance_type="diag",
                            n_iter=200, random_state=42, tol=1e-3)
        model.fit(feats)
        states = model.predict(feats)

        # Characterise each latent state by mean return (feat 0) and mean vol (feat 2).
        stats = {}
        for s in range(4):
            mask = states == s
            if mask.sum() == 0:
                stats[s] = {"ret": 0.0, "vol": 0.0}
            else:
                stats[s] = {"ret": float(feats[mask, 0].mean()),
                            "vol": float(feats[mask, 2].mean())}

        # Label by behaviour: the highest-vol state is the squeeze; of the rest the
        # highest mean-return is the bull, the lowest is the bear, the middle is
        # consolidation.
        by_vol = sorted(stats, key=lambda s: stats[s]["vol"], reverse=True)
        squeeze = by_vol[0]
        rest = [s for s in stats if s != squeeze]
        rest_by_ret = sorted(rest, key=lambda s: stats[s]["ret"], reverse=True)
        bull = rest_by_ret[0]
        bear = rest_by_ret[-1]
        consolidation = [s for s in rest if s not in (bull, bear)][0]

        self.model = model
        self.state_map = {
            squeeze: "high_vol_squeeze",
            bull: "bull_momentum",
            bear: "bear_distribution",
            consolidation: "consolidation",
        }
        self.fitted_at = datetime.datetime.utcnow()
        return self

    # ---- inference ----
    def posterior(self, feats):
        """Smoothed posterior over regimes for the most recent observation."""
        raw = self.model.predict_proba(feats)[-1]  # posterior over hmm states
        probs = {name: 0.0 for name in REGIME_NAMES}
        for state_idx, name in self.state_map.items():
            probs[name] += float(raw[state_idx])
        # normalise (defensive)
        tot = sum(probs.values()) or 1.0
        return {k: v / tot for k, v in probs.items()}

    def dynamic_weights(self, regime_probs):
        w = {s: 0.0 for s in SIGNALS}
        for regime, p in regime_probs.items():
            for sig, base in REGIME_WEIGHT_MATRIX[regime].items():
                w[sig] += p * base
        tot = sum(w.values()) or 1.0
        return {k: round(v / tot, 4) for k, v in w.items()}


def _confidence_bands(regime, composite_score, realized_vol):
    """Regime-scaled 24h confidence cone around the expected drift.

    Uses the most-recent realised daily vol as the base sigma and a regime
    multiplier (squeeze widens, consolidation tightens).
    """
    mult = {"high_vol_squeeze": 1.8, "bear_distribution": 1.25,
            "bull_momentum": 1.1, "consolidation": 0.8}.get(regime, 1.0)
    sigma = max(0.005, float(realized_vol)) * mult   # daily sigma (fraction)
    drift = (composite_score - 50.0) / 100.0 * sigma * 4.0   # small directional tilt
    z = 1.2816  # ~80% band
    return {
        "lower_pct": round((drift - z * sigma) * 100, 2),
        "expected_pct": round(drift * 100, 2),
        "upper_pct": round((drift + z * sigma) * 100, 2),
        "sigma_daily_pct": round(sigma * 100, 2),
        "vol_multiplier": mult,
    }


def analyze(df, regime_col=None, force_refit=False, max_age_hours=20):
    """Top-level entry: ensure a fresh model, run inference, persist, and return a
    JSON-serialisable regime analysis dict.

    Called from compute() each daily run (the walk-forward re-fit) and read back by
    the /forecast/regime + /forecast/reconcile-signals endpoints.
    """
    result = {
        "available": False,
        "current_regime": None,
        "regime_label": None,
        "regime_description": None,
        "regime_probabilities": None,
        "active_weights": None,
        "static_weights": {k: round(v, 4) for k, v in STATIC_WEIGHTS.items()},
        "weight_matrix": REGIME_WEIGHT_MATRIX,
        "confidence_24h": None,
        "fitted_at": None,
        "feature_names": _FEATURE_NAMES,
    }
    if not _HAS_HMM:
        result["note"] = "hmmlearn unavailable — using static weights"
        result["active_weights"] = result["static_weights"]
        return result

    try:
        feats = extract_features(df)
    except Exception as e:  # noqa
        result["note"] = f"feature extraction failed: {e}"
        result["active_weights"] = result["static_weights"]
        return result

    engine = DynamicRegimeEngine()
    loaded = False
    if regime_col is not None and not force_refit:
        try:
            doc = regime_col.find_one({"_id": "btc"})
            if doc and doc.get("model_blob"):
                loaded = engine.load_blob(doc["model_blob"])
                if loaded and engine.fitted_at:
                    age = (datetime.datetime.utcnow() - engine.fitted_at).total_seconds() / 3600.0
                    if age > max_age_hours:
                        loaded = False  # stale -> refit
        except Exception:  # noqa
            traceback.print_exc()
            loaded = False

    if not loaded:
        try:
            engine.fit(feats)
        except Exception as e:  # noqa
            traceback.print_exc()
            result["note"] = f"HMM fit failed: {e}"
            result["active_weights"] = result["static_weights"]
            return result
        if regime_col is not None:
            try:
                regime_col.update_one(
                    {"_id": "btc"},
                    {"$set": {"model_blob": engine.to_blob(),
                              "fitted_at": engine.fitted_at.isoformat()}},
                    upsert=True,
                )
            except Exception:  # noqa
                traceback.print_exc()

    try:
        regime_probs = engine.posterior(feats)
        active_weights = engine.dynamic_weights(regime_probs)
        dominant = max(regime_probs, key=regime_probs.get)
        realized_vol = float(feats[-1, 2])
        # composite score preview is filled by the decision engine; use 50 (neutral)
        bands = _confidence_bands(dominant, 50.0, realized_vol)

        result.update({
            "available": True,
            "current_regime": dominant,
            "regime_label": REGIME_LABELS[dominant],
            "regime_description": REGIME_DESCRIPTIONS[dominant],
            "regime_probabilities": {k: round(v, 4) for k, v in regime_probs.items()},
            "active_weights": active_weights,
            "confidence_24h": bands,
            "fitted_at": engine.fitted_at.isoformat() if engine.fitted_at else None,
            "realized_vol_daily_pct": round(realized_vol * 100, 2),
        })

        # Persist the latest analysis for the reconcile/regime endpoints.
        if regime_col is not None:
            try:
                snap = {k: v for k, v in result.items() if k != "weight_matrix"}
                snap["updated_at"] = datetime.datetime.utcnow().isoformat()
                regime_col.update_one({"_id": "btc"}, {"$set": {"latest": snap}}, upsert=True)
            except Exception:  # noqa
                traceback.print_exc()
    except Exception as e:  # noqa
        traceback.print_exc()
        result["note"] = f"inference failed: {e}"
        result["active_weights"] = result["static_weights"]

    return result


def recompute_confidence(regime, composite_score, realized_vol_pct):
    """Public helper so the decision engine can refresh the 24h cone once it knows
    the real composite score (analyze() seeds it at neutral 50)."""
    try:
        return _confidence_bands(regime, float(composite_score), float(realized_vol_pct) / 100.0)
    except Exception:  # noqa
        return None
