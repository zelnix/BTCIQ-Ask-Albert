"""Phase G — Portfolio-Level Risk & Drawdown Protection state (stateful, persisted).

Maintains an up-only high-water mark (HWM) derived from the reconciled paper
portfolio value, and a STATEFUL protection mode with hysteresis so the circuit
breaker cannot flap around the mandate threshold and cannot be cleared by a
backend restart.

State machine (per pid):
    NORMAL --(drawdown >= maxDrawdown)--> PROTECTION_ACTIVE
    PROTECTION_ACTIVE stays active while drawdown > recoveryThreshold
    PROTECTION_ACTIVE --(drawdown <= recoveryThreshold)--> NORMAL
where recoveryThreshold = maxDrawdown * PORTFOLIO_DRAWDOWN_RECOVERY_RATIO.

HWM is architected as flow-adjustable from the start: an externalFlowAdjustmentUsd
field is stored and subtracted so a future paper deposit/withdrawal cannot create
an artificial gain or a fake investment drawdown. There is no deposit/withdrawal
mechanism today, so it defaults to 0 (behaviour: HWM ratchets up only).
"""
import datetime

from config import portfolio_risk_col
from albert.engine.constants import PORTFOLIO_DRAWDOWN_RECOVERY_RATIO


def _now():
    return datetime.datetime.utcnow().isoformat()


def load(pid):
    return portfolio_risk_col.find_one({'_id': pid})


def reset(pid):
    """Clear all drawdown-protection state (called on paper-reset)."""
    portfolio_risk_col.delete_one({'_id': pid})


def evaluate(pid, current_value, max_drawdown_pct):
    """Deterministically ratchet the HWM, compute current drawdown, and advance the
    stateful protection machine with hysteresis. Persists the new state and returns
    a portfolioRisk dict (audit-ready).

    current_value  : reconciled paper-portfolio total value (holdings + usdc)
    max_drawdown_pct: mandate limit (None/0 => enforcement disabled)
    """
    state = portfolio_risk_col.find_one({'_id': pid}) or {}
    prev_hwm = float(state.get('highWaterMarkUsd') or 0.0)
    ext_flow = float(state.get('externalFlowAdjustmentUsd') or 0.0)  # reserved; 0 today
    protection = bool(state.get('protectionMode') or False)
    activated_at = state.get('protectionActivatedAt')
    breach_hwm = state.get('breachHwmUsd')

    cv = float(current_value or 0.0)
    # Flow-adjusted value: subtract net external inflows so deposits don't mint a
    # fake HWM and withdrawals don't look like investment losses.
    effective_cv = cv - ext_flow
    hwm = prev_hwm if prev_hwm > 0 else effective_cv
    if effective_cv > hwm:            # up-only ratchet
        hwm = effective_cv
    drawdown_pct = round(max(0.0, ((hwm - effective_cv) / hwm * 100.0) if hwm > 0 else 0.0), 4)

    try:
        max_dd = float(max_drawdown_pct) if max_drawdown_pct is not None else None
    except Exception:  # noqa
        max_dd = None
    enforceable = max_dd is not None and max_dd > 0
    recovery_threshold = round(max_dd * PORTFOLIO_DRAWDOWN_RECOVERY_RATIO, 4) if enforceable else None

    breached_now = bool(enforceable and drawdown_pct >= max_dd)
    if enforceable:
        if not protection:
            if breached_now:
                protection = True
                activated_at = _now()
                breach_hwm = round(hwm, 2)
        else:
            # Remain protected until drawdown recovers to/under the recovery threshold.
            if drawdown_pct <= recovery_threshold:
                protection = False
                activated_at = None
                breach_hwm = None
    else:
        protection = False
        activated_at = None
        breach_hwm = None

    doc = {'_id': pid, 'pid': pid,
           'highWaterMarkUsd': round(hwm, 2),
           'externalFlowAdjustmentUsd': ext_flow,
           'protectionMode': protection,
           'protectionActivatedAt': activated_at,
           'breachHwmUsd': breach_hwm,
           'recoveryThresholdPct': recovery_threshold,
           'maxDrawdownPct': max_dd,
           'updatedAt': _now()}
    portfolio_risk_col.update_one({'_id': pid}, {'$set': doc}, upsert=True)

    return {
        'highWaterMarkUsd': round(hwm, 2),
        'currentPortfolioValueUsd': round(cv, 2),
        'externalFlowAdjustmentUsd': ext_flow,
        'drawdownPct': drawdown_pct,
        'maxDrawdownPct': max_dd,
        'recoveryThresholdPct': recovery_threshold,
        'enforceable': bool(enforceable),
        'breached': breached_now,
        'protectionMode': bool(protection),
        'protectionActivatedAt': activated_at,
        'breachHwmUsd': breach_hwm,
    }
