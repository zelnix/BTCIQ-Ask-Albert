"""Canonical decision-input hashing (Phase D2).

The decisionInputsHash proves reproducibility: the SAME canonical inputs + the
SAME engine version always yield the SAME hash (and therefore the same
decision). Presentation fields (ids, timestamps, generated explanation text,
human-readable reason strings) are deliberately EXCLUDED so they cannot corrupt
the hash.
"""
import hashlib
import json


def _r(x, n=2):
    try:
        if x is None:
            return None
        return round(float(x), n)
    except Exception:  # noqa
        return None


def canonical_inputs(*, engine_version, symbol, regime, buy_threshold, score, confidence,
                     eligible, ineligibility_reason, mandate_checks, current_allocation_pct,
                     cap_pct, unrealized_pct, current_price, invalidation, position_value,
                     deployable_usdc, total_value, regime_deploy_ceiling):
    """Return the canonicalised, deterministic input dict used for hashing.

    Everything here is a *decision input* (or a discretised form of one). No ids,
    timestamps, or explanation text.
    """
    mc = mandate_checks or {}
    return {
        'engineVersion': engine_version,
        'symbol': symbol,
        'regime': regime,
        'buyThreshold': buy_threshold,
        'score': _r(score, 1),
        'confidence': int(confidence) if confidence is not None else None,
        'eligible': bool(eligible),
        'ineligibilityReason': ineligibility_reason,
        'mandateChecks': {
            'excluded': bool(mc.get('excluded')),
            'inApprovedUniverse': bool(mc.get('inApprovedUniverse')),
            'withinCap': bool(mc.get('withinCap')),
            'withinRiskBudget': bool(mc.get('withinRiskBudget')),
            'mandateComplete': bool(mc.get('mandateComplete')),
        },
        'currentAllocationPct': _r(current_allocation_pct, 2),
        'capPct': _r(cap_pct, 2),
        'unrealizedPct': _r(unrealized_pct, 2),
        'currentPrice': _r(current_price, 6),
        'invalidation': _r(invalidation, 6),
        'positionValue': _r(position_value, 2),
        'deployableUsdc': _r(deployable_usdc, 2),
        'totalValue': _r(total_value, 2),
        'regimeDeployCeiling': _r(regime_deploy_ceiling, 2),
    }


def hash_inputs(inputs):
    """Deterministic sha256 (first 16 hex chars) of a canonical input dict."""
    blob = json.dumps(inputs, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]


def short_hash(obj):
    """Stable short hash of any JSON-able object (used for mandate/portfolio/regime versions)."""
    blob = json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:12]
