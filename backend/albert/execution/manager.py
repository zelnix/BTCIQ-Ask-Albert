"""Paper Order Manager (Phase E) — the deterministic execution firewall.

Only a frozen DecisionSnapshot + execution-safety rules can create or change an
OrderIntent. The LLM is never an input here.
"""
import datetime
import uuid

from config import order_intents_col, order_audit_col, ORDER_TTL_SECONDS, DEFAULT_SLIPPAGE_BPS
from albert import deps
from albert.engine import decision as _dec
from albert.repositories import decision_history as _hist
from albert.execution import state_machine as sm
from albert.execution import ledger

_EPS = 1e-9


def _now():
    return datetime.datetime.utcnow()


def _iso(dt):
    return dt.isoformat()


def _clean(doc):
    if not doc:
        return None
    d = dict(doc)
    d.pop('_id', None)
    return d


def _audit(intent, state_before, state_after, action, facts=None):
    order_audit_col.insert_one({
        '_id': str(uuid.uuid4()), 'orderIntentId': intent['orderIntentId'], 'pid': intent['pid'],
        'asset': intent['asset'], 'action': action, 'stateBefore': state_before, 'stateAfter': state_after,
        'facts': facts or {}, 'ts': _iso(_now())})


def _set_state(intent, new_state, action, facts=None):
    sm.assert_transition(intent['state'], new_state)
    before = intent['state']
    intent['state'] = new_state
    order_intents_col.update_one({'_id': intent['orderIntentId']}, {'$set': {
        'state': new_state, 'updatedAt': _iso(_now()),
        'filledQuantity': intent.get('filledQuantity', 0.0),
        'remainingQuantity': intent.get('remainingQuantity', intent['quantity']),
        'fills': intent.get('fills', [])}})
    _audit(intent, before, new_state, action, facts)


def resolve_current_decision(pid, asset):
    """Re-run the deterministic engine (with stable ids via reconcile) and return
    the current decision for the asset. This is the ONLY source of truth for an
    intent's parameters and for staleness checks."""
    snap = _dec.build_decisions(pid)
    _hist.reconcile(pid, snap)
    return next((d for d in snap['decisions'] if d['symbol'] == asset), None)


def _is_expired(intent):
    try:
        return _now() > datetime.datetime.fromisoformat(intent['expiresAt'])
    except Exception:  # noqa
        return False


def _expire(intent, action):
    if not sm.is_terminal(intent['state']):
        _set_state(intent, sm.EXPIRED, action, {'rejectionReason': 'EXPIRED'})
    return {'status': 'expired', 'reason': 'EXPIRED', 'intent': _clean(order_intents_col.find_one({'_id': intent['orderIntentId']}))}


def _stale(intent, fresh):
    """True if the frozen decision no longer matches the current engine output."""
    if fresh is None:
        return True
    return (fresh.get('decisionInputsHash') != intent['decisionInputsHash']
            or fresh.get('engineVersion') != intent['engineVersion'])


def _reject(intent, reason, action, extra=None):
    facts = {'rejectionReason': reason}
    if extra:
        facts.update(extra)
    _set_state(intent, sm.REJECTED, action, facts)
    return {'status': 'rejected', 'reason': reason, 'intent': _clean(order_intents_col.find_one({'_id': intent['orderIntentId']}))}


# --------------------------------------------------------------------------- #
def create_intent(pid, asset, idempotency_key, slippage_bps=None, portfolio_id='default', account_id='paper'):
    asset = str(asset).upper()[:8]
    slippage_bps = int(slippage_bps if slippage_bps is not None else DEFAULT_SLIPPAGE_BPS)
    scope = '%s|%s|%s|%s' % (pid, portfolio_id, account_id, idempotency_key)
    existing = order_intents_col.find_one({'idempotencyScope': scope})
    if existing:
        return {'status': 'exists', 'intent': _clean(existing)}

    d = resolve_current_decision(pid, asset)
    if not d:
        return {'status': 'error', 'error': 'ASSET_NOT_IN_UNIVERSE'}
    action = d['action']
    if action == 'BUY':
        side = 'BUY'; ref = d.get('currentPrice'); amount = d.get('recommendedDeployNowUsd') or 0.0
        quantity = (amount / ref) if ref else 0.0; reason = d.get('reasonCode')
    elif action == 'SELL' and d.get('sellPlan'):
        side = 'SELL'; ref = d.get('currentPrice'); amount = d['sellPlan'].get('sellUsd') or 0.0
        quantity = d['sellPlan'].get('sellQty') or 0.0; reason = d.get('reasonCode')
    else:
        return {'status': 'error', 'error': 'NO_ACTIONABLE_ORDER', 'call': action}
    if not amount or amount <= 0 or not quantity or quantity <= 0 or not ref:
        return {'status': 'error', 'error': 'NO_ACTIONABLE_ORDER', 'call': action}

    created = _now()
    oid = str(uuid.uuid4())
    max_buy = round(ref * (1 + slippage_bps / 10000.0), 8)
    min_sell = round(ref * (1 - slippage_bps / 10000.0), 8)
    intent = {
        '_id': oid, 'orderIntentId': oid, 'pid': pid, 'portfolioId': portfolio_id, 'accountId': account_id,
        'decisionId': d.get('decisionId'), 'snapshotId': d.get('snapshotId'),
        'decisionInputsHash': d.get('decisionInputsHash'), 'engineVersion': d.get('engineVersion'),
        'asset': asset, 'side': side, 'quantity': round(quantity, 10), 'amountUsd': round(amount, 2),
        'reasonCode': reason, 'referencePrice': ref, 'slippageToleranceBps': slippage_bps,
        'maxBuyPrice': max_buy, 'minSellPrice': min_sell,
        'createdAt': _iso(created), 'expiresAt': _iso(created + datetime.timedelta(seconds=ORDER_TTL_SECONDS)),
        'idempotencyKey': idempotency_key, 'idempotencyScope': scope, 'state': sm.DRAFT,
        'filledQuantity': 0.0, 'remainingQuantity': round(quantity, 10), 'fills': [],
        'updatedAt': _iso(created),
    }
    order_intents_col.insert_one(dict(intent))
    _audit(intent, None, sm.DRAFT, 'CREATE')
    _set_state(intent, sm.PENDING_CONFIRMATION, 'SUBMIT_FOR_CONFIRMATION')
    return {'status': 'created', 'intent': _clean(order_intents_col.find_one({'_id': oid}))}


def _load(order_id):
    return order_intents_col.find_one({'_id': order_id})


def confirm(order_id):
    intent = _load(order_id)
    if not intent:
        return {'status': 'error', 'error': 'NOT_FOUND'}
    if sm.is_terminal(intent['state']):
        return {'status': 'error', 'error': 'TERMINAL_STATE', 'state': intent['state']}
    if intent['state'] != sm.PENDING_CONFIRMATION:
        return {'status': 'error', 'error': 'ILLEGAL_STATE', 'state': intent['state']}
    if _is_expired(intent):
        return _expire(intent, 'CONFIRM')
    fresh = resolve_current_decision(intent['pid'], intent['asset'])
    if _stale(intent, fresh):
        return _reject(intent, 'STALE_DECISION', 'CONFIRM',
                       {'frozenHash': intent['decisionInputsHash'], 'currentHash': (fresh or {}).get('decisionInputsHash')})
    _set_state(intent, sm.CONFIRMED, 'CONFIRM')
    return {'status': 'confirmed', 'intent': _clean(_load(order_id))}


def execute(order_id, simulate_fill_qty=None):
    """Execute (CONFIRMED->WORKING with staleness re-check) or continue filling a
    WORKING/PARTIALLY_FILLED order. Partial fills come ONLY from an explicit
    simulate_fill_qty (deterministic; no probabilistic liquidity model)."""
    intent = _load(order_id)
    if not intent:
        return {'status': 'error', 'error': 'NOT_FOUND'}
    if sm.is_terminal(intent['state']):
        return {'status': 'error', 'error': 'TERMINAL_STATE', 'state': intent['state']}

    if intent['state'] == sm.CONFIRMED:
        if _is_expired(intent):
            return _expire(intent, 'EXECUTE')
        fresh = resolve_current_decision(intent['pid'], intent['asset'])
        if _stale(intent, fresh):
            return _reject(intent, 'STALE_DECISION', 'EXECUTE',
                           {'frozenHash': intent['decisionInputsHash'], 'currentHash': (fresh or {}).get('decisionInputsHash')})
        _set_state(intent, sm.WORKING, 'EXECUTE')
        intent = _load(order_id)
    elif intent['state'] in (sm.WORKING, sm.PARTIALLY_FILLED):
        pass  # continuation fill of an already-working order (venue event, no re-staleness)
    else:
        return {'status': 'error', 'error': 'ILLEGAL_STATE', 'state': intent['state']}

    # --- slippage gate (direction-aware) ---
    spot = deps.spot_price(intent['asset'])
    if not spot:
        return _reject(intent, 'NO_MARKET_PRICE', 'FILL')
    ref = intent['referencePrice']
    actual_bps = round((spot - ref) / ref * 10000.0, 2) if ref else 0.0
    if intent['side'] == 'BUY' and spot > intent['maxBuyPrice']:
        return _reject(intent, 'SLIPPAGE_EXCEEDED', 'FILL',
                       {'decisionPrice': ref, 'executionSpot': spot, 'allowedMaximumPrice': intent['maxBuyPrice'],
                        'slippageToleranceBps': intent['slippageToleranceBps'], 'actualSlippageBps': actual_bps})
    if intent['side'] == 'SELL' and spot < intent['minSellPrice']:
        return _reject(intent, 'SLIPPAGE_EXCEEDED', 'FILL',
                       {'decisionPrice': ref, 'executionSpot': spot, 'allowedMinimumPrice': intent['minSellPrice'],
                        'slippageToleranceBps': intent['slippageToleranceBps'], 'actualSlippageBps': actual_bps})

    remaining = intent['remainingQuantity']
    fill_qty = remaining if simulate_fill_qty is None else min(float(simulate_fill_qty), remaining)
    if fill_qty <= _EPS:
        return {'status': 'error', 'error': 'ZERO_FILL_QTY'}

    entry = ledger.append_fill(intent['pid'], intent['accountId'], intent['orderIntentId'],
                               intent['asset'], intent['side'], fill_qty, spot)
    ledger.materialize(intent['pid'], intent['accountId'])  # fills feed Albert's next portfolio view

    filled = round(intent.get('filledQuantity', 0.0) + fill_qty, 10)
    remaining = round(intent['quantity'] - filled, 10)
    intent['filledQuantity'] = filled
    intent['remainingQuantity'] = max(0.0, remaining)
    intent['fills'] = (intent.get('fills') or []) + [{'fillId': entry['_id'], 'quantity': fill_qty,
                       'price': spot, 'usd': entry['usd'], 'ts': entry['ts']}]
    facts = {'decisionPrice': ref, 'executionSpot': spot, 'slippageToleranceBps': intent['slippageToleranceBps'],
             'actualSlippageBps': actual_bps, 'allowedMaximumPrice': intent['maxBuyPrice'],
             'allowedMinimumPrice': intent['minSellPrice'], 'fillQuantity': round(fill_qty, 10),
             'fillUsd': entry['usd'], 'remainingQuantity': intent['remainingQuantity']}
    new_state = sm.FILLED if intent['remainingQuantity'] <= _EPS else sm.PARTIALLY_FILLED
    _set_state(intent, new_state, 'FILL', facts)
    return {'status': 'filled' if new_state == sm.FILLED else 'partially_filled',
            'fill': facts, 'intent': _clean(_load(order_id))}


def cancel(order_id):
    intent = _load(order_id)
    if not intent:
        return {'status': 'error', 'error': 'NOT_FOUND'}
    if sm.is_terminal(intent['state']):
        return {'status': 'error', 'error': 'TERMINAL_STATE', 'state': intent['state']}
    if not sm.can_transition(intent['state'], sm.CANCELLED):
        return {'status': 'error', 'error': 'ILLEGAL_STATE', 'state': intent['state']}
    _set_state(intent, sm.CANCELLED, 'CANCEL')
    return {'status': 'cancelled', 'intent': _clean(_load(order_id))}


def sweep_expired(pid):
    """Best-effort cleanup; correctness never depends on it (confirm/execute enforce TTL)."""
    n = 0
    for intent in order_intents_col.find({'pid': pid, 'state': {'$nin': list(sm.TERMINAL)}}):
        if _is_expired(intent):
            _expire(intent, 'SWEEP'); n += 1
    return n


def get_intent(order_id):
    return _clean(_load(order_id))


def list_intents(pid, limit=50):
    return [_clean(d) for d in order_intents_col.find({'pid': pid}).sort('createdAt', -1).limit(int(limit))]


def get_audit(order_id):
    return [{k: v for k, v in a.items() if k != '_id'}
            for a in order_audit_col.find({'orderIntentId': order_id}).sort('ts', 1)]
