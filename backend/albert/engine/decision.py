"""Full deterministic decision snapshot: regime + per-asset DecisionResult +
deployment plan + SELL engine + precedence (Phase C + D1).

The engine emits a single canonical call per asset: BUY / HOLD / SELL / WAIT.
Precedence guarantees a high opportunity score can never overpower a risk exit
(see albert.engine.precedence / constants.PRECEDENCE_ORDER). The LLM only ever
explains this output — it cannot alter an action, amount, score, or reason.
"""
import datetime
import uuid

from albert import deps
from albert.engine import regime as regime_mod
from albert.engine import scoring as scoring_mod
from albert.engine import sell as sell_mod
from albert.engine.constants import (
    ALBERT_ENGINE_VERSION, REGIME_BUY_THRESHOLD, REGIME_DEPLOY_CEILING,
    ALBERT_UNIVERSE, STABLES, PRECEDENCE_ORDER,
)

# reasonCode for non-SELL calls
_REASON_BUY = 'OPPORTUNITY_ENTRY'
_REASON_HOLD = 'THESIS_INTACT'
_REASON_WAIT_BELOW = 'BELOW_ENTRY_LINE'
_REASON_WAIT_GATED = 'GATED_BY_MANDATE'
_REASON_WAIT_STALE = 'STALE_DATA'
_REASON_WAIT_NOROOM = 'NO_HEADROOM'


def _apply_sell(base, ctx):
    """Evaluate the SELL engine for a held asset and, if a SELL fires, override
    the decision (SELL always outranks BUY/HOLD/WAIT). Returns True if a SELL
    was applied."""
    res = sell_mod.evaluate_sell(ctx)
    if not res:
        return False
    plan = res['best']
    base['action'] = 'SELL'
    base['reasonCode'] = plan['reasonCode']
    base['sellReason'] = plan['reasonCode']
    base['sellPlan'] = plan
    base['precedenceRuleApplied'] = plan['reasonCode']
    base['recommendedDeployNowUsd'] = 0.0
    base['totalPlannedDeploymentUsd'] = 0.0
    base['tranches'] = []
    base['reasons'].insert(0, plan['note'])
    if len(res['signals']) > 1:
        others = [s for s in res['signals'] if s != plan['reasonCode']]
        base['reasons'].append('Other conditions also present (lower precedence): ' + ', '.join(others) + '.')
    return True


def build_decisions(pid):
    """Full deterministic snapshot: regime + per-asset DecisionResult + deployment plan."""
    reg = regime_mod.compute_regime()
    regime = reg['regime']
    summary = deps.portfolio_summary(pid)
    mandate = deps.get_mandate(pid)
    total = summary['total_value'] or 0.0
    deployable = summary['deployable_usdc'] or 0.0
    approved = set(mandate.get('approved_coins') or [])
    excluded = set(mandate.get('excluded_coins') or [])
    max_alloc = mandate.get('max_alloc_pct') or {}
    trade_risk_pct = mandate.get('max_trade_risk_pct') or 2.0
    held = {h['asset']: h for h in summary['holdings']}
    complete = summary['mandate_complete']
    buy_thresh = REGIME_BUY_THRESHOLD[regime]
    regime_pool = round(deployable * REGIME_DEPLOY_CEILING[regime], 2)

    universe = list(dict.fromkeys(list(ALBERT_UNIVERSE) + list(held.keys())))
    decisions = []
    for sym in universe:
        if sym in STABLES:
            continue
        sc = scoring_mod.score_asset(sym, regime)
        held_h = held.get(sym)
        cur_val = (held_h or {}).get('value', 0.0)
        cur_pct = (held_h or {}).get('portfolio_pct', 0.0)
        pos_size = (held_h or {}).get('size')
        upnl = (held_h or {}).get('unrealized_pct')
        cap_pct = max_alloc.get(sym, 100.0)
        target_pct = cap_pct
        base = {'symbol': sym, 'regime': regime, 'currentPrice': (sc or {}).get('currentPrice'),
                'currentAllocationPct': cur_pct, 'targetAllocationPct': target_pct,
                'recommendedDeployNowUsd': 0.0, 'totalPlannedDeploymentUsd': 0.0,
                'tranches': [], 'warnings': [], 'reasons': [], 'engineVersion': ALBERT_ENGINE_VERSION,
                'reasonCode': None, 'sellReason': None, 'sellPlan': None, 'precedenceRuleApplied': None,
                'evaluatedAt': datetime.datetime.utcnow().isoformat()}

        if not sc.get('ok'):
            base.update({'action': 'WAIT', 'opportunityScore': 0, 'confidence': 20,
                         'scoreComponents': {}, 'invalidationPrice': None,
                         'reasonCode': _REASON_WAIT_STALE,
                         'reasons': ['Market data is stale or insufficient \u2014 Albert waits rather than guesses.']})
            base['precedenceRuleApplied'] = 'WAIT'
            # Even with stale OHLCV, an owned asset can still trigger an EMERGENCY exit
            # (excluded-coin breach, or a portfolio-priced blow-through) — those don't need OHLCV.
            if held_h is not None:
                _apply_sell(base, {
                    'symbol': sym, 'positionValue': cur_val, 'positionSize': pos_size,
                    'unrealizedPct': upnl, 'currentPrice': (sc or {}).get('currentPrice'),
                    'invalidationPrice': None, 'currentAllocationPct': cur_pct, 'capPct': cap_pct,
                    'totalValue': total, 'excluded': excluded, 'tradeRiskPct': trade_risk_pct,
                    'dataOk': False,
                })
            decisions.append(base)
            continue

        # portfolioFit: penalise if already near the cap
        headroom_pct = max(0.0, cap_pct - cur_pct)
        comps = dict(sc['components'])
        comps['portfolioFit'] = round(min(10.0, headroom_pct / max(1.0, cap_pct) * 10.0), 1)
        score = round(sum(comps.values()), 1)
        base.update({'opportunityScore': score, 'confidence': sc['confidence'], 'scoreComponents': comps,
                     'invalidationPrice': sc['invalidation'], 'reasons': list(sc['reasons'])})
        # Mandate hard gates for BUY eligibility
        gate_block = None
        if excluded and sym in excluded:
            gate_block = 'Excluded by your Trading Mandate'
        elif approved and sym not in approved:
            gate_block = 'Not in your approved-coins whitelist'
        elif not complete:
            gate_block = 'Set your mandate to unlock BUY recommendations'
        base['_eligible'] = gate_block is None
        base['_score'] = score
        base['_cur_val'] = cur_val
        base['_cap_val'] = total * cap_pct / 100.0
        base['_owned'] = held_h is not None
        if gate_block:
            base['warnings'].append(gate_block)
        # Default action pre-sizing (BUY amount decided in the allocation pass)
        if score >= buy_thresh and gate_block is None:
            base['action'] = 'BUY'
            base['reasonCode'] = _REASON_BUY
        elif held_h is not None:
            base['action'] = 'HOLD'
            base['reasonCode'] = _REASON_HOLD
            base['reasons'].insert(0, 'You own this and its thesis still holds \u2014 keep it, no add right now.')
        else:
            base['action'] = 'WAIT'
            if gate_block is not None:
                base['reasonCode'] = _REASON_WAIT_GATED
            elif score < buy_thresh:
                base['reasonCode'] = _REASON_WAIT_BELOW
                base['reasons'].insert(0, 'Score %.0f is below the %s BUY line (%s).' % (score, regime, buy_thresh))
            else:
                base['reasonCode'] = _REASON_WAIT_BELOW
        base['precedenceRuleApplied'] = base['action']

        # SELL engine overrides BUY/HOLD when a higher-precedence risk condition fires.
        if held_h is not None:
            _apply_sell(base, {
                'symbol': sym, 'positionValue': cur_val, 'positionSize': pos_size,
                'unrealizedPct': upnl, 'currentPrice': sc.get('currentPrice'),
                'invalidationPrice': sc.get('invalidation'), 'currentAllocationPct': cur_pct,
                'capPct': cap_pct, 'totalValue': total, 'excluded': excluded,
                'tradeRiskPct': trade_risk_pct, 'dataOk': True,
            })
        decisions.append(base)

    # Allocation pass across BUY candidates (score-weighted), respecting all ceilings.
    # SELL decisions are already excluded (action != 'BUY').
    buys = [d for d in decisions if d.get('action') == 'BUY']
    remaining = regime_pool
    if buys and remaining > 0:
        weights = []
        for d in buys:
            excess = max(0.0, d['_score'] - buy_thresh)
            weights.append((excess ** 2) * (d['confidence'] / 100.0))
        wsum = sum(weights) or 1.0
        for d, w in zip(buys, weights):
            opp_alloc = remaining * (w / wsum)
            alloc_headroom = max(0.0, d['_cap_val'] - d['_cur_val'])
            price = d['currentPrice'] or 0.0
            inv = d.get('invalidationPrice') or 0.0
            stop_dist = abs(price - inv) / price if price else 0.15
            risk_sized = (total * trade_risk_pct / 100.0) / stop_dist if stop_dist > 0 else opp_alloc
            planned = max(0.0, min(opp_alloc, alloc_headroom, risk_sized, remaining))
            planned = round(planned, 2)
            if planned < 50:  # too small to matter -> HOLD/WAIT instead
                d['action'] = 'HOLD' if d['_owned'] else 'WAIT'
                d['reasonCode'] = _REASON_WAIT_NOROOM if not d['_owned'] else _REASON_HOLD
                d['precedenceRuleApplied'] = d['action']
                d['reasons'].insert(0, 'Qualifies, but allocation/risk ceilings leave no meaningful room to add now.')
                continue
            deploy_now = round(planned * 0.40, 2)
            d['totalPlannedDeploymentUsd'] = planned
            d['recommendedDeployNowUsd'] = deploy_now
            d['tranches'] = [
                {'number': 1, 'pct': 40, 'amountUsd': deploy_now, 'trigger': 'ENTRY_CONDITIONS_VALID'},
                {'number': 2, 'pct': 35, 'amountUsd': round(planned * 0.35, 2), 'trigger': 'CONTROLLED_PULLBACK'},
                {'number': 3, 'pct': 25, 'amountUsd': round(planned - deploy_now - round(planned * 0.35, 2), 2), 'trigger': 'TREND_RECONFIRMATION'},
            ]
            if alloc_headroom < opp_alloc:
                d['reasons'].insert(0, 'Your %.0f%% cap limits this to $%s.' % (d['targetAllocationPct'], format(planned, ',.0f')))
            remaining = round(remaining - deploy_now, 2)

    total_deploy_now = round(sum(d['recommendedDeployNowUsd'] for d in decisions), 2)
    for d in decisions:
        for k in ('_eligible', '_score', '_cur_val', '_cap_val', '_owned'):
            d.pop(k, None)
    decisions.sort(key=lambda d: d.get('opportunityScore', 0), reverse=True)
    qualifying = sum(1 for d in decisions if d['action'] == 'BUY')

    sell_decisions = [d for d in decisions if d['action'] == 'SELL']
    urgent_sells = [d for d in sell_decisions if d['reasonCode'] in ('EMERGENCY_EXIT', 'THESIS_INVALIDATION')]

    if not complete:
        albert_call = 'Set your Trading Mandate to unlock personalised recommendations.'
    elif urgent_sells:
        parts = ['%s %s (%s)' % (d['symbol'], d['sellPlan']['action'], d['reasonCode']) for d in urgent_sells]
        albert_call = 'REDUCE RISK NOW \u2014 ' + '; '.join(parts) + '.'
    elif total_deploy_now > 0:
        albert_call = ('DEPLOY $%s \u2014 %s opportunit%s qualify; retaining $%s of deployable USDC as dry powder.'
                       % (format(total_deploy_now, ',.0f'), qualifying, ('y' if qualifying == 1 else 'ies'),
                          format(deployable - total_deploy_now, ',.0f')))
        if sell_decisions:
            albert_call += ' Also managing %d position%s: %s.' % (
                len(sell_decisions), '' if len(sell_decisions) == 1 else 's',
                ', '.join('%s %s' % (d['symbol'], d['sellPlan']['action']) for d in sell_decisions))
    elif sell_decisions:
        parts = ['%s %s' % (d['symbol'], d['sellPlan']['action']) for d in sell_decisions]
        albert_call = 'MANAGE POSITIONS \u2014 ' + '; '.join(parts) + '.'
    else:
        albert_call = 'WAIT \u2014 no high-quality entry justifies deploying capital in a %s market right now.' % regime

    return {'snapshotId': str(uuid.uuid4()), 'marketDataTimestamp': datetime.datetime.utcnow().isoformat(),
            'engineVersion': ALBERT_ENGINE_VERSION, 'regime': reg, 'summary': summary,
            'mandate_complete': complete, 'buyThreshold': buy_thresh, 'regimeDeployCeiling': regime_pool,
            'deployableUsdc': deployable, 'totalDeployNowUsd': total_deploy_now, 'albertCall': albert_call,
            'qualifying': qualifying, 'sellCount': len(sell_decisions), 'precedenceOrder': dict(PRECEDENCE_ORDER),
            'decisions': decisions}
