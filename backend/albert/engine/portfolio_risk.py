"""Phase G — deterministic portfolio-wide risk-reduction sizing.

Given an active drawdown breach, decide the MINIMUM defensible reduction of risk
exposure (not a panic liquidation) and allocate it across held risk assets by
risk-contribution (with a portfolio-weight fallback), then snap each per-asset
requirement UP into the permitted D1 SELL actions (TRIM_10/25/50 / EXIT_100).

Selling crypto -> cash does not restore drawdown value; this layer instead sheds
risk EXPOSURE so a deeper drawdown is less likely, consistent with the position-
level philosophy: reduce enough to comply, not liquidate in panic.
"""
from albert.engine.constants import (
    STABLES, PORTFOLIO_RISK_SEVERITY_FLOOR, PORTFOLIO_RISK_DEFAULT_STOP_DIST,
)
from albert.engine import sizing


def target_reduction_fraction(severity):
    """Continuous, versioned severity -> target risk-reduction fraction curve.
    See constants for the exact shape. Deterministic and monotonic."""
    if severity <= 0:
        return 0.0
    if severity <= PORTFOLIO_RISK_SEVERITY_FLOOR:
        return PORTFOLIO_RISK_SEVERITY_FLOOR
    return min(1.0, severity)


def compute_reductions(*, holdings, scored, max_drawdown_pct, drawdown_pct):
    """Compute the portfolio-wide risk-reduction plan.

    holdings : list of summary holdings dicts {asset,value,size,portfolio_pct,unrealized_pct}
    scored   : dict asset -> {'currentPrice': float|None, 'invalidation': float|None}

    Returns:
      {
        'severity', 'targetRiskReductionFraction', 'totalRiskExposureUsd',
        'riskReductionRequiredUsd',
        'perAsset': { SYMBOL: {'fraction'(snapped), 'targetReductionUsd',
                               'reductionBasis', 'riskContribution'} }
      }
    """
    try:
        max_dd = float(max_drawdown_pct)
    except Exception:  # noqa
        max_dd = 0.0
    excess = (drawdown_pct - max_dd)
    severity = (excess / max_dd) if max_dd > 0 else 0.0
    target = target_reduction_fraction(severity)

    risk_assets = []
    for h in (holdings or []):
        asset = str(h.get('asset', '')).upper()
        val = float(h.get('value') or 0.0)
        if not asset or asset in STABLES or val <= 0:
            continue
        risk_assets.append(h)

    total_exposure = round(sum(float(h.get('value') or 0.0) for h in risk_assets), 2)

    contributions = {}
    basis = {}
    for h in risk_assets:
        asset = str(h['asset']).upper()
        val = float(h.get('value') or 0.0)
        sc = scored.get(asset) or {}
        price = sc.get('currentPrice')
        inv = sc.get('invalidation')
        if price and inv and price > 0:
            risk_pct = abs(float(price) - float(inv)) / float(price)
            if risk_pct <= 0:
                risk_pct = PORTFOLIO_RISK_DEFAULT_STOP_DIST
                basis[asset] = 'PORTFOLIO_WEIGHT_FALLBACK'
            else:
                basis[asset] = 'RISK_CONTRIBUTION'
        else:
            risk_pct = PORTFOLIO_RISK_DEFAULT_STOP_DIST
            basis[asset] = 'PORTFOLIO_WEIGHT_FALLBACK'
        contributions[asset] = val * risk_pct

    total_contribution = sum(contributions.values()) or 0.0
    target_reduction_usd = round(target * total_exposure, 2)

    per_asset = {}
    if target > 0 and total_exposure > 0 and total_contribution > 0:
        for h in risk_assets:
            asset = str(h['asset']).upper()
            val = float(h.get('value') or 0.0)
            weight = contributions[asset] / total_contribution
            red_usd = target_reduction_usd * weight
            raw_frac = min(1.0, (red_usd / val)) if val > 0 else 0.0
            snapped = sizing.round_up_fraction(raw_frac) if raw_frac > 0 else 0.0
            if snapped <= 0:
                continue
            per_asset[asset] = {
                'fraction': round(float(snapped), 4),
                'targetReductionUsd': round(red_usd, 2),
                'reductionBasis': basis[asset],
                'riskContribution': round(contributions[asset], 2),
            }

    return {
        'severity': round(severity, 4),
        'targetRiskReductionFraction': round(target, 4),
        'totalRiskExposureUsd': total_exposure,
        'riskReductionRequiredUsd': target_reduction_usd,
        'perAsset': per_asset,
    }
