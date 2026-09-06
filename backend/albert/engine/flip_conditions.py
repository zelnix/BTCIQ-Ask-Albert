"""Deterministic 'What Would Change This' flip conditions (Phase D2).

Every BUY / SELL / HOLD / WAIT call returns explicit, engine-generated flip
conditions. They are derived purely from engine state + versioned thresholds
(NEVER from the LLM), include hysteresis so small score wobble does not flap the
call, and SELL flips respect the D1 precedence hierarchy.
"""
from albert.engine.constants import (
    REGIME_BUY_ENTER, REGIME_BUY_REMAIN, CONFIDENCE_MIN, EMERGENCY_LOSS_PCT,
    PROFIT_LADDER,
)


def _c(to_call, trigger, detail, threshold=None):
    d = {'toCall': to_call, 'trigger': trigger, 'detail': detail}
    if threshold is not None:
        d['threshold'] = threshold
    return d


def _next_profit_tier(upnl):
    """Lowest ladder threshold strictly above the current gain (the next tranche)."""
    tiers = sorted(t for t, _f in PROFIT_LADDER)
    for t in tiers:
        if upnl is None or upnl < t:
            return t
    return None


def build_flip_conditions(*, action, reason_code, regime, score, confidence, owned,
                          current_price, invalidation, unrealized_pct, cap_pct,
                          current_allocation_pct, eligible, ineligibility_reason):
    enter = REGIME_BUY_ENTER[regime]
    remain = REGIME_BUY_REMAIN[regime]
    out = []

    if action == 'BUY':
        # Hysteresis: stays a BUY down to the remain band; below enter but above
        # remain -> stop adding (HOLD if owned); below remain -> WAIT.
        out.append(_c('HOLD' if owned else 'WAIT', 'SCORE_BELOW_ENTER_ABOVE_REMAIN',
                      'Opportunity score slips below the %s BUY line (%d) but holds above %d \u2014 stop adding.' % (regime, enter, remain),
                      threshold=enter))
        out.append(_c('WAIT', 'SCORE_BELOW_REMAIN',
                      'Opportunity score falls below the %d hysteresis floor \u2014 the entry no longer qualifies.' % remain,
                      threshold=remain))
        out.append(_c('WAIT', 'CONFIDENCE_INSUFFICIENT',
                      'Data confidence drops below %d \u2014 Albert waits rather than guesses.' % CONFIDENCE_MIN,
                      threshold=CONFIDENCE_MIN))
        if invalidation:
            out.append(_c('SELL:THESIS_INVALIDATION', 'PRICE_BELOW_INVALIDATION',
                          'Price closes at or below the invalidation level $%s \u2014 thesis void, exit.' % format(invalidation, ',.2f'),
                          threshold=invalidation))

    elif action == 'HOLD':
        out.append(_c('BUY', 'SCORE_RECLAIMS_ENTER_WITH_HEADROOM',
                      'BUY if the score reaches %d while %s conditions remain valid, with allocation headroom and deployable USDC.' % (enter, regime),
                      threshold=enter))
        tier = _next_profit_tier(unrealized_pct)
        if tier is not None:
            out.append(_c('SELL:PROFIT_TAKE', 'GAIN_REACHES_LADDER',
                          'Unrealized gain reaches +%d%% \u2014 bank a profit-taking tranche.' % int(tier),
                          threshold=tier))
        if invalidation:
            out.append(_c('SELL:THESIS_INVALIDATION', 'PRICE_BELOW_INVALIDATION',
                          'Price closes at or below $%s \u2014 thesis void, exit.' % format(invalidation, ',.2f'),
                          threshold=invalidation))
        if cap_pct is not None:
            out.append(_c('SELL:REBALANCE', 'ALLOCATION_ABOVE_CAP',
                          'Allocation rises above your %.0f%% cap \u2014 trim back toward target.' % cap_pct,
                          threshold=cap_pct))
        out.append(_c('SELL:RISK_REDUCTION', 'RISK_EXCEEDS_BUDGET',
                      'Position risk-at-stop exceeds 1.5x your per-trade risk budget \u2014 trim to comply.'))
        out.append(_c('SELL:EMERGENCY_EXIT', 'LOSS_BELOW_EMERGENCY',
                      'Position falls to -%.0f%% \u2014 emergency full exit.' % EMERGENCY_LOSS_PCT,
                      threshold=-EMERGENCY_LOSS_PCT))

    elif action == 'WAIT':
        if not eligible and ineligibility_reason == 'NOT_IN_APPROVED_UNIVERSE':
            out.append(_c('BUY', 'BECOMES_ELIGIBLE',
                          'Add this asset to your approved-coins whitelist \u2014 then at score >= %d (with headroom + deployable USDC) it can BUY.' % enter,
                          threshold=enter))
        elif not eligible and ineligibility_reason == 'EXCLUDED_BY_MANDATE':
            out.append(_c('BUY', 'REMOVE_FROM_EXCLUDED',
                          'Remove this asset from your excluded list \u2014 only then can it be considered.'))
        elif not eligible and ineligibility_reason == 'MANDATE_INCOMPLETE':
            out.append(_c('BUY', 'COMPLETE_MANDATE',
                          'Complete your Trading Mandate (risk tolerance + reserve) to unlock BUY \u2014 then at score >= %d it can qualify.' % enter,
                          threshold=enter))
        elif not eligible and ineligibility_reason == 'STALE_DATA':
            out.append(_c('RE_EVALUATE', 'DATA_REFRESHED',
                          'Fresh market data restores a confident read \u2014 Albert re-evaluates.'))
        else:
            out.append(_c('BUY', 'ALL_GATES_PASS',
                          'BUY if the score reaches %d (confidence >= %d) while %s conditions hold and mandate + allocation headroom + deployable USDC all clear.' % (enter, CONFIDENCE_MIN, regime),
                          threshold=enter))

    elif action == 'SELL':
        # A SELL can revert to HOLD if the triggering condition clears BEFORE
        # execution. Higher-precedence triggers can still override a lower one.
        out.append(_c('HOLD', 'RISK_CONDITION_CLEARS',
                      'If the %s condition clears before execution (price reclaims invalidation / allocation back under cap / risk back within budget), revert to HOLD.' % reason_code))
        # Precedence-aware escalation note.
        if reason_code == 'PROFIT_TAKE':
            out.append(_c('SELL:RISK_REDUCTION', 'HIGHER_PRECEDENCE_FIRES',
                          'A higher-precedence risk trigger (emergency / thesis / risk / rebalance) would override this profit-take.'))
        elif reason_code in ('REBALANCE', 'RISK_REDUCTION'):
            out.append(_c('SELL:THESIS_INVALIDATION', 'HIGHER_PRECEDENCE_FIRES',
                          'An emergency or thesis-invalidation trigger would override this %s and force a full exit.' % reason_code))
        elif reason_code == 'THESIS_INVALIDATION':
            out.append(_c('SELL:EMERGENCY_EXIT', 'HIGHER_PRECEDENCE_FIRES',
                          'An emergency condition (excluded-coin breach or -%.0f%% blow-through) would escalate this to an immediate full exit.' % EMERGENCY_LOSS_PCT))

    return out
