"""Deterministic SELL engine (Phase D1).

Emits SELL signals for an OWNED asset from five explicit, deterministic reason
classes. Hard rules:
  * SELL applies only to positions actually held.
  * A falling opportunity score alone NEVER triggers a SELL — every SELL must
    originate from one of the five reason classes below.
  * Severity (not the reason code) chooses the trim fraction, which is then
    rounded into the permitted action framework (10 / 25 / 50 / 100).

Precedence (highest first): EMERGENCY_EXIT > THESIS_INVALIDATION >
RISK_REDUCTION > REBALANCE > PROFIT_TAKE.
"""
from albert.engine import precedence, sizing
from albert.engine.constants import (
    EMERGENCY_LOSS_PCT, RISK_BREACH_MULT, REBALANCE_TOL_PCT, PROFIT_LADDER,
)


def _sig(reason_code, fraction, note):
    return {'reasonCode': reason_code, 'fraction': float(fraction), 'note': note}


def evaluate_sell(ctx):
    """Evaluate every SELL class for one held asset.

    ctx keys:
      symbol, positionValue, positionSize, unrealizedPct (float|None),
      currentPrice (float|None), invalidationPrice (float|None),
      currentAllocationPct, capPct, totalValue, excluded (set),
      tradeRiskPct (float), dataOk (bool)

    Returns None when nothing fires, else a dict:
      {'best': <sell_plan>, 'signals': [reasonCode,...]}
    """
    sym = ctx['symbol']
    pos_val = ctx.get('positionValue') or 0.0
    pos_size = ctx.get('positionSize') or 0.0
    upnl = ctx.get('unrealizedPct')
    price = ctx.get('currentPrice')
    invalidation = ctx.get('invalidationPrice')
    cur_pct = ctx.get('currentAllocationPct') or 0.0
    cap_pct = ctx.get('capPct')
    total = ctx.get('totalValue') or 0.0
    excluded = ctx.get('excluded') or set()
    trade_risk_pct = ctx.get('tradeRiskPct') or 2.0
    data_ok = bool(ctx.get('dataOk'))
    pdr_fraction = ctx.get('portfolioDrawdownFraction')  # Phase G: portfolio-level cut for this asset

    if pos_val <= 0:
        return None

    signals = []

    # 1. EMERGENCY_EXIT ------------------------------------------------------
    if sym in excluded:
        signals.append(_sig('EMERGENCY_EXIT', 1.0,
                            'Held asset is on your excluded-coins list \u2014 flatten the position immediately.'))
    if upnl is not None and upnl <= -EMERGENCY_LOSS_PCT:
        signals.append(_sig('EMERGENCY_EXIT', 1.0,
                            'Position is down %.0f%%, beyond the %.0f%% emergency stop \u2014 exit fully to protect capital.'
                            % (upnl, EMERGENCY_LOSS_PCT)))

    # 1b. PORTFOLIO_DRAWDOWN_RISK (Phase G) -----------------------------------
    # Portfolio-wide risk circuit breaker. Ranks just under EMERGENCY_EXIT, so an
    # individual emergency still wins, but this outranks every position-level trigger.
    if pdr_fraction and pdr_fraction > 0:
        signals.append(_sig('PORTFOLIO_DRAWDOWN_RISK', pdr_fraction,
                            'Portfolio drawdown has breached your mandate limit \u2014 reducing this position to shed portfolio risk.'))

    # 2. THESIS_INVALIDATION -------------------------------------------------
    if data_ok and price and invalidation and price <= invalidation:
        signals.append(_sig('THESIS_INVALIDATION', 1.0,
                            'Price $%s has broken below the invalidation level $%s \u2014 the entry thesis is void.'
                            % (format(price, ',.2f'), format(invalidation, ',.2f'))))

    # 3. RISK_REDUCTION (per-position risk budget) ---------------------------
    if data_ok and price and invalidation and pos_val and total:
        stop_dist = abs(price - invalidation) / price if price else 0.0
        if stop_dist > 0:
            risk_at_stop = pos_val * stop_dist
            budget = total * (trade_risk_pct / 100.0)
            if budget > 0 and risk_at_stop > budget * RISK_BREACH_MULT:
                # minimum fraction to bring risk-at-stop back to the exact budget
                need = 1.0 - (budget / risk_at_stop)
                frac = sizing.round_up_fraction(max(0.0, min(1.0, need)))
                signals.append(_sig('RISK_REDUCTION', frac,
                                    'Position risk-at-stop is %.1fx your %.1f%% per-trade budget \u2014 trim to restore compliance.'
                                    % (risk_at_stop / budget, trade_risk_pct)))

    # 4. REBALANCE (over the allocation cap) ---------------------------------
    if cap_pct is not None and cur_pct > (cap_pct + REBALANCE_TOL_PCT):
        overshoot_frac = (cur_pct - cap_pct) / cur_pct if cur_pct else 0.0
        frac = sizing.round_up_fraction(max(0.0, min(1.0, overshoot_frac)))
        signals.append(_sig('REBALANCE', frac,
                            'Allocation %.0f%% exceeds your %.0f%% cap \u2014 trim back toward target.'
                            % (cur_pct, cap_pct)))

    # 5. PROFIT_TAKE (staged ladder) -----------------------------------------
    if upnl is not None and upnl > 0:
        for thr, frac in PROFIT_LADDER:
            if upnl >= thr:
                signals.append(_sig('PROFIT_TAKE', frac,
                                    'Up %.0f%% \u2014 bank a %.0f%% tranche per the profit-taking ladder.'
                                    % (upnl, frac * 100)))
                break

    if not signals:
        return None

    best = precedence.resolve(signals)
    plan = sizing.build_sell_plan(
        best['reasonCode'], best['fraction'], pos_val, pos_size, cur_pct,
        current_price=price, note=best['note'],
        all_signals=[s['reasonCode'] for s in signals],
    )
    return {'best': plan, 'signals': [s['reasonCode'] for s in signals]}
