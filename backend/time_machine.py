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
