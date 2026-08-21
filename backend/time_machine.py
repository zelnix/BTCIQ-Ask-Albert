"""Pillar 3 — "Time Machine" analog engine (FAISS nearest-neighbour pattern match).

Indexes every historical day as a standardized multidimensional feature vector
(momentum / trend / volatility / volume) into a FAISS cosine-similarity index.
Given today's vector it answers "when did this happen before?" — returning the
top-K most similar historical days and their subsequent 7-day / 30-day forward
return paths, plus an aggregate "what happened next" summary.
"""

import numpy as np

try:
    import faiss
    _HAS_FAISS = True
except Exception:  # noqa
    _HAS_FAISS = False


def _analog_context(df, j):
    """Human-readable market backdrop for a historical analog day, derived from
    price/volume/indicators (a true news archive isn't stored for past dates)."""
    try:
        closes = df['close'].values
        n = len(closes)

        def ret(a, b):
            return round((closes[a] - closes[b]) / closes[b] * 100, 1) if 0 <= b < n and closes[b] else None
        prior7 = ret(j, j - 7)
        prior30 = ret(j, j - 30)
        vr = None
        if 'volume' in df.columns and j >= 20:
            base = float(df['volume'].values[max(0, j - 20):j].mean() or 0)
            vr = round(float(df['volume'].values[j]) / base, 2) if base else None
        rsi_raw = float(df['RSI'].iloc[j]) if 'RSI' in df.columns else None
        rsi = round(rsi_raw * 100) if (rsi_raw is not None and rsi_raw <= 1.5) else (round(rsi_raw) if rsi_raw is not None else None)
        ema = float(df['EMA_Ratio'].iloc[j]) if 'EMA_Ratio' in df.columns else 0.0
        atr = float(df['ATR_Pct'].iloc[j]) if 'ATR_Pct' in df.columns else None
        trend = 'up-trend' if ema > 0.002 else 'down-trend' if ema < -0.002 else 'flat'
        mom = 'overbought' if (rsi is not None and rsi >= 70) else 'oversold' if (rsi is not None and rsi <= 30) else 'neutral momentum'
        vol_desc = ('elevated volatility' if (atr is not None and atr > 0.04)
                    else 'calm volatility' if (atr is not None and atr < 0.02) else 'normal volatility')
        vol_flow = ('above-average volume' if (vr and vr > 1.2) else 'below-average volume' if (vr and vr < 0.8) else 'average volume')
        bits = []
        if prior30 is not None:
            bits.append(f"price had moved {prior30:+.1f}% over the prior month ({prior7:+.1f}% in the prior week)")
        bits.append(f"in a {trend} with {mom}")
        bits.append(f"{vol_desc} and {vol_flow}")
        summary = 'On this day, ' + ', '.join(bits) + '.'
        return {
            'prior_7d_pct': prior7, 'prior_30d_pct': prior30,
            'rsi': rsi, 'trend': trend, 'momentum': mom,
            'atr_pct': round(atr * 100, 2) if atr is not None else None,
            'volume_ratio': vr, 'summary': summary,
            'note': 'News archive not available for past dates — context derived from price, volume and indicators.',
        }
    except Exception:  # noqa
        return None


def find_analogs(df, feature_cols, k=3, forward=30, exclude_recent=7, min_gap=15):
    """df: OHLCV+features DataFrame (must include feature_cols, 'close', 'timestamp')."""
    cols = [c for c in feature_cols if c in df.columns]
    n = len(df)
    if n < 120 or not cols:
        return {'status': 'insufficient_data'}

    X = df[cols].values.astype('float32')
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-9
    Z = (X - mu) / sd
    norm = np.linalg.norm(Z, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    Zn = (Z / norm).astype('float32')

    query = Zn[-1:].copy()
    closes = df['close'].values
    dates = df['timestamp']

    # Rank candidates by cosine similarity (FAISS inner-product on L2-normalised vectors).
    if _HAS_FAISS:
        index = faiss.IndexFlatIP(Zn.shape[1])
        index.add(Zn)
        _, idxs = index.search(query, min(n, 80))
        order = list(idxs[0])
        sims_full = None
    else:  # numpy fallback
        sims_full = (Zn @ query[0])
        order = list(np.argsort(-sims_full))[:80]

    def sim_of(j):
        return float((Zn[j] @ query[0]))

    results = []
    used = []
    for j in order:
        j = int(j)
        if j >= n - exclude_recent:      # skip the query itself + very recent days
            continue
        if j + forward >= n:             # need a full forward window
            continue
        if any(abs(j - u) < min_gap for u in used):  # dedupe adjacent clusters
            continue
        used.append(j)
        c0 = float(closes[j])
        c7 = float(closes[j + 7]) if j + 7 < n else c0
        c30 = float(closes[j + forward])
        path = [{'d': o, 'close': round(float(closes[j + o]), 2)} for o in range(0, forward + 1)]
        results.append({
            'date': dates.iloc[j].strftime('%Y-%m-%d'),
            'similarity': round(sim_of(j), 4),
            'price_then': round(c0, 2),
            'ret_7d_pct': round((c7 - c0) / c0 * 100, 2),
            'ret_30d_pct': round((c30 - c0) / c0 * 100, 2),
            'path_30d': path,
            'context': _analog_context(df, j),
        })
        if len(results) >= k:
            break

    summary = None
    if results:
        summary = {
            'avg_ret_7d_pct': round(sum(r['ret_7d_pct'] for r in results) / len(results), 2),
            'avg_ret_30d_pct': round(sum(r['ret_30d_pct'] for r in results) / len(results), 2),
            'pct_higher_7d': round(100 * sum(1 for r in results if r['ret_7d_pct'] > 0) / len(results)),
            'pct_higher_30d': round(100 * sum(1 for r in results if r['ret_30d_pct'] > 0) / len(results)),
        }

    return {
        'status': 'ready',
        'engine': 'faiss' if _HAS_FAISS else 'numpy',
        'as_of': dates.iloc[-1].strftime('%Y-%m-%d'),
        'current_price': round(float(closes[-1]), 2),
        'k': len(results),
        'features_used': cols,
        'analogs': results,
        'summary': summary,
        'method': 'FAISS cosine similarity over standardized momentum/trend/volatility/volume feature vectors.',
    }
