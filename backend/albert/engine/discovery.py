"""Phase I - Top-100 Discovery (provider-agnostic universe layer).

Hard architectural rule: DISCOVERY IS NOT PERMISSION TO BUY. This module ranks a
live market-cap universe, applies liquidity + data-quality filters, and (only for
assets tradable on the configured venues) runs Albert's opportunity score. Mandate
eligibility and the final call are layered on top per-pid. An asset can look highly
interesting (high score) and still be WAIT because it is not eligible.

Pipeline:  Live universe -> Top-100 by mcap -> liquidity + data-quality ->
           opportunity score (tradable only) -> eligibility -> BUY/HOLD/SELL/WAIT

The market-data provider is injected as pre-fetched `rows` (see server), so no
vendor is baked into the engine.
"""
import uuid
import datetime

from albert.engine.constants import REGIME_BUY_THRESHOLD, STABLES

# Versioned discovery config (bump ALBERT_ENGINE_VERSION alongside material changes).
DISCOVERY_TTL_SEC = 600            # cache the (pid-independent) core snapshot ~10 min
LIQUIDITY_MIN_USD = 10_000_000     # 24h volume floor for liquidity PASS


def _data_quality(row, is_stable, tradable):
    if is_stable:
        return 'STABLE'
    if not (row.get('priceUsd') and row.get('marketCapUsd')):
        return 'INCOMPLETE'
    if not tradable:
        return 'NO_MARKET'
    return 'GOOD'


def assemble_core(*, rows, regime, tradable_set, score_fn, engine_version, source, source_ts):
    """pid-INDEPENDENT core: rank + market cap + liquidity + data-quality + opportunity
    score (tradable & liquid & good-data only). Never scores stablecoins or
    non-tradable assets. Returns a snapshot dict; eligibility/call applied later."""
    buy_threshold = REGIME_BUY_THRESHOLD.get(regime, 78)
    assets = []
    for row in rows:
        sym = row['symbol']
        is_stable = sym in STABLES
        tradable = sym in tradable_set
        vol = float(row.get('volume24hUsd') or 0)
        liquidity = 'PASS' if vol >= LIQUIDITY_MIN_USD else 'FAIL'
        dq = _data_quality(row, is_stable, tradable)
        score = confidence = invalidation = None
        if dq == 'GOOD' and liquidity == 'PASS':
            sc = score_fn(sym, regime) or {}
            if sc.get('ok'):
                score = sc.get('score')
                confidence = sc.get('confidence')
                invalidation = sc.get('invalidation')
            else:
                dq = 'STALE_DATA'   # tradable but no usable OHLCV right now
        assets.append({
            'symbol': sym, 'name': row.get('name'), 'rank': row.get('rank'),
            'marketCapUsd': row.get('marketCapUsd'), 'priceUsd': row.get('priceUsd'),
            'volume24hUsd': vol, 'liquidity': liquidity, 'dataQuality': dq, 'tradable': tradable,
            'opportunityScore': score, 'confidence': confidence, 'invalidation': invalidation,
            'buyThreshold': buy_threshold, 'scorable': bool(tradable and not is_stable),
        })
    return {
        'universeSnapshotId': str(uuid.uuid4()),
        'source': source, 'sourceTimestamp': source_ts,
        'generatedAt': datetime.datetime.utcnow().isoformat(),
        'engineVersion': engine_version, 'regime': regime, 'buyThreshold': buy_threshold,
        'liquidityMinUsd': LIQUIDITY_MIN_USD, 'count': len(assets), 'assets': assets,
    }


def apply_eligibility(core, *, held, excluded, approved, mandate_complete):
    """pid-SPECIFIC: add mandate eligibility + a lightweight, HONEST discovery call.
    An ineligible / unscored / illiquid asset can NEVER show BUY here — the real
    sizing/decision stays in the Command Centre. Discovery only answers 'interesting?'."""
    from albert.engine import universe as universe_mod
    held = set(held or set())
    out = dict(core)
    out['pidApplied'] = True
    result = []
    for a0 in core.get('assets', []):
        a = dict(a0)
        sym = a['symbol']
        data_ok = a['dataQuality'] == 'GOOD'
        elig, reason = universe_mod.eligibility(
            sym, data_ok=data_ok, excluded=excluded, approved=approved, mandate_complete=mandate_complete)
        held_now = sym in held
        score = a.get('opportunityScore')
        if not elig or score is None:
            call = 'HOLD' if held_now else 'WAIT'
        elif held_now:
            call = 'HOLD'
        elif score >= a.get('buyThreshold', 78):
            call = 'BUY'
        else:
            call = 'WAIT'
        a['eligible'] = bool(elig)
        a['ineligibilityReason'] = reason
        a['held'] = held_now
        a['albertCall'] = call
        result.append(a)
    out['assets'] = result
    return out
