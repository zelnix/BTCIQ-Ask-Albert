"""Phase H — Lifecycle Replay & Decision Journey (read-only assembly).

Assembles a single per-asset timeline from EXISTING frozen records:
  * decision_snapshots_col  — immutable decision states (the journey nodes)
  * decision_history_col     — transition events (changeReason)
  * order_intents_col        — paper orders linked to a decision by decisionId
  * order_ledger_col         — immutable paper fills (the actual exposure track)

INTEGRITY RULES (hard):
  - Never recompute a historical decision with today's engine. Each node shows the
    original frozen envelope + its original engineVersion + snapshotId.
  - Keep Decision (what Albert recommended) / Execution (what happened to the paper
    order) / Portfolio effect (resulting paper exposure) visually separable — an
    expired/unexecuted recommendation must not look like a fill.
  - Degrade gracefully: missing orders/fills/history yield empty structures, never
    invented events.
"""
from config import (
    decision_snapshots_col, decision_history_col, order_intents_col,
    order_ledger_col, portfolio_col,
)
from albert.engine.constants import ALBERT_ENGINE_VERSION

_EPS = 1e-9
_DRAWDOWN_CODES = ('PORTFOLIO_DRAWDOWN_RISK', 'GATED_BY_DRAWDOWN')


def _stage(env):
    """Deterministic user-facing stage. ADD/TRIM are PRESENTATION over the frozen
    BUY/SELL contract (they never change the underlying engine call)."""
    action = env.get('call') or env.get('action')
    if action == 'BUY':
        pb = (env.get('positionBefore') or {})
        existed = (pb.get('valueUsd') or 0) > _EPS or (pb.get('size') or 0) > _EPS
        return 'ADD' if existed else 'BUY'
    if action == 'SELL':
        sp = env.get('sellPlan') or {}
        return 'SELL' if (sp.get('action') == 'EXIT_100') else 'TRIM'
    if action == 'HOLD':
        return 'HOLD'
    return 'WAIT'


def _label(env, stage):
    if stage in ('BUY', 'ADD'):
        d = env.get('recommendedDeltaUsd') or env.get('recommendedDeployNowUsd') or 0
        return '%s $%s' % (stage, format(round(d), ',')) if d else stage
    if stage == 'TRIM':
        sp = env.get('sellPlan') or {}
        act = sp.get('action') or ''
        pct = act.split('_')[1] if act.startswith('TRIM_') else ''
        return ('Trim %s%%' % pct) if pct else 'Trim'
    if stage == 'SELL':
        return 'Exit 100%'
    return stage.title()


def _order_view(o):
    return {
        'orderIntentId': o.get('orderIntentId'),
        'side': o.get('side'),
        'state': o.get('state'),
        'amountUsd': o.get('amountUsd'),
        'quantity': o.get('quantity'),
        'filledQuantity': o.get('filledQuantity', 0.0),
        'remainingQuantity': o.get('remainingQuantity'),
        'engineVersion': o.get('engineVersion'),
        'decisionInputsHash': o.get('decisionInputsHash'),
        'createdAt': o.get('createdAt'),
        'fills': [{'quantity': f.get('quantity'), 'price': f.get('price'),
                   'usd': f.get('usd'), 'ts': f.get('ts')} for f in (o.get('fills') or [])],
    }


def build_lifecycle(pid, asset, account_id='paper'):
    asset = str(asset or '').upper()[:8]
    if not pid or not asset:
        return {'status': 'error', 'error': 'pid and asset required'}

    snaps = list(decision_snapshots_col.find({'pid': pid, 'asset': asset}).sort('createdAt', 1))
    hist = {}
    for h in decision_history_col.find({'pid': pid, 'asset': asset}):
        if h.get('newDecisionId'):
            hist[h['newDecisionId']] = h

    orders_by_did = {}
    for o in order_intents_col.find({'pid': pid, 'asset': asset}).sort('createdAt', 1):
        orders_by_did.setdefault(o.get('decisionId'), []).append(o)

    # --- exposure track (actual paper fills only) ---
    base = portfolio_col.find_one({'_id': pid}) or {}
    baseline_size = 0.0
    for p in (base.get('positions') or []):
        if str(p.get('asset', '')).upper()[:8] == asset:
            baseline_size = float(p.get('size') or 0)
    fills = list(order_ledger_col.find({'pid': pid, 'accountId': account_id, 'asset': asset}).sort('ts', 1))
    position_track = [{'ts': None, 'size': round(baseline_size, 10), 'kind': 'BASELINE'}]
    running = baseline_size
    for f in fills:
        q = float(f.get('quantity') or 0)
        running = running + q if f.get('side') == 'BUY' else max(0.0, running - q)
        position_track.append({'ts': f.get('ts'), 'size': round(running, 10), 'kind': f.get('side'),
                               'quantity': q, 'price': f.get('price'), 'usd': f.get('usd'),
                               'orderIntentId': f.get('orderIntentId')})
    current_size = round(running, 10)

    def _paper_size_at(ts):
        sz = baseline_size
        for f in fills:
            if (f.get('ts') or '') <= (ts or ''):
                q = float(f.get('quantity') or 0)
                sz = sz + q if f.get('side') == 'BUY' else max(0.0, sz - q)
        return round(sz, 10)

    events = []
    prev_call = None
    for s in snaps:
        env = s.get('envelope') or {}
        ts = s.get('createdAt')
        stage = _stage(env)
        did = s.get('decisionId') or env.get('decisionId')
        sp = env.get('sellPlan') or {}
        all_signals = sp.get('allSignals') or []
        reason = env.get('reasonCode')
        # portfolio-drawdown intervention + precedence-override visibility
        intervention = reason in _DRAWDOWN_CODES or ('PORTFOLIO_DRAWDOWN_RISK' in all_signals)
        note = None
        if reason in _DRAWDOWN_CODES:
            note = 'Portfolio drawdown protection drove this call.'
        elif 'PORTFOLIO_DRAWDOWN_RISK' in all_signals and reason:
            note = 'Portfolio drawdown risk was active, but %s took precedence.' % reason

        orders = [_order_view(o) for o in orders_by_did.get(did, [])]
        h = hist.get(did)

        events.append({
            'eventId': did,
            'timestamp': ts,
            'decisionId': did,
            'snapshotId': s.get('snapshotId') or env.get('snapshotId'),
            'decisionInputsHash': env.get('decisionInputsHash') or s.get('decisionInputsHash'),
            'engineVersion': env.get('engineVersion'),
            'stage': stage,
            'label': _label(env, stage),
            'call': env.get('call') or env.get('action'),
            'previousCall': prev_call,
            'reasonCode': reason,
            'precedenceRuleApplied': env.get('precedenceRuleApplied'),
            'score': env.get('score') if env.get('score') is not None else env.get('opportunityScore'),
            'confidence': env.get('confidence'),
            'regime': env.get('regime'),
            'eligible': env.get('eligible'),
            'ineligibilityReason': env.get('ineligibilityReason'),
            # DECISION (recommended)
            'recommendedDeltaUsd': env.get('recommendedDeltaUsd'),
            'positionBefore': env.get('positionBefore'),
            'positionAfter': env.get('positionAfter'),
            'sellPlan': sp or None,
            'sellAllSignals': all_signals or None,
            'flipConditions': env.get('flipConditions') or [],
            # EXECUTION (paper orders)
            'orders': orders,
            'hasExecution': any(o['fills'] for o in orders),
            # PORTFOLIO EFFECT (actual paper exposure at the time of this decision)
            'paperPositionSizeAtDecision': _paper_size_at(ts),
            # PORTFOLIO RISK
            'portfolioRiskIntervention': bool(intervention),
            'portfolioRiskNote': note,
            # audit
            'changeReason': (h or {}).get('changeReason') or [],
            'changeType': (h or {}).get('changeType'),
        })
        prev_call = env.get('call') or env.get('action')

    status = 'ready' if (events or fills) else 'empty'
    return {
        'status': status,
        'pid': pid,
        'asset': asset,
        'currentEngineVersion': ALBERT_ENGINE_VERSION,
        'eventCount': len(events),
        'baselineSize': round(baseline_size, 10),
        'currentPaperPositionSize': current_size,
        'positionTrack': position_track,
        'events': events,
    }
