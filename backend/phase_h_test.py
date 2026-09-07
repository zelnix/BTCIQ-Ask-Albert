"""Phase H lifecycle assembler test — seeds a full frozen journey and verifies the
read-only replay (stages, previousCall, engine-version preservation, ADD detection,
exposure-from-fills-only, order linkage, drawdown intervention, precedence override,
graceful degradation)."""
import requests
from config import (decision_snapshots_col, decision_history_col, order_intents_col,
                    order_ledger_col, portfolio_col)

BASE = 'http://localhost:8001/api'
PID = 'u_TEST_PHASE_H'
ASSET = 'TESTX'

results = []
def check(name, ok, detail=''):
    results.append(ok); print(('PASS' if ok else 'FAIL'), '-', name, ('| ' + detail) if detail else '')


def cleanup():
    for col in (decision_snapshots_col, decision_history_col, order_intents_col, order_ledger_col):
        col.delete_many({'pid': PID})
    portfolio_col.delete_many({'_id': PID})


def snap(did, ts, env, ver):
    env = dict(env)
    env.update({'decisionId': did, 'snapshotId': 'S_' + did, 'engineVersion': ver,
                'decisionInputsHash': 'H_' + did})
    decision_snapshots_col.insert_one({'_id': did, 'decisionId': did, 'snapshotId': 'S_' + did,
        'pid': PID, 'asset': ASSET, 'decisionInputsHash': 'H_' + did, 'identity': [env.get('call')],
        'envelope': env, 'createdAt': ts})


def hist(prev, new, ts, reasons, ctype):
    decision_history_col.insert_one({'_id': 'ev_' + new, 'pid': PID, 'asset': ASSET,
        'previousDecisionId': prev, 'newDecisionId': new, 'previousSnapshotId': 'S_' + prev,
        'newSnapshotId': 'S_' + new, 'changedAt': ts, 'changeType': ctype, 'changeReason': reasons})


def order(oid, did, side, state, amount, qty, ts, fills):
    order_intents_col.insert_one({'_id': oid, 'orderIntentId': oid, 'pid': PID, 'asset': ASSET,
        'decisionId': did, 'snapshotId': 'S_' + did, 'decisionInputsHash': 'H_' + did,
        'idempotencyScope': 'scope_' + oid, 'idempotencyKey': 'key_' + oid,
        'engineVersion': 'albert-decide-v1', 'side': side, 'state': state, 'amountUsd': amount,
        'quantity': qty, 'filledQuantity': sum(f['quantity'] for f in fills),
        'remainingQuantity': qty - sum(f['quantity'] for f in fills), 'fills': fills, 'createdAt': ts})


def fill(oid, side, q, price, ts):
    order_ledger_col.insert_one({'_id': 'L_' + oid + '_' + ts, 'pid': PID, 'accountId': 'paper',
        'orderIntentId': oid, 'asset': ASSET, 'side': side, 'quantity': q, 'price': price,
        'usd': round(q * price, 2), 'ts': ts})


cleanup()
portfolio_col.insert_one({'_id': PID, 'usdc': 50000.0, 'positions': []})  # baseline size 0

# --- journey nodes (frozen) ---
snap('d1', '2026-01-01T00:00:01', {'call': 'WAIT', 'action': 'WAIT', 'reasonCode': 'BELOW_ENTRY_LINE',
     'score': 45, 'confidence': 30, 'regime': 'BULL', 'eligible': True,
     'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v1')
snap('d2', '2026-01-01T00:00:02', {'call': 'BUY', 'action': 'BUY', 'reasonCode': 'OPPORTUNITY_ENTRY',
     'score': 78, 'confidence': 72, 'regime': 'BULL', 'eligible': True,
     'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 4000,
     'flipConditions': [{'toState': 'WAIT', 'condition': 'x'}]}, 'albert-decide-v1')
snap('d3', '2026-01-01T00:00:03', {'call': 'BUY', 'action': 'BUY', 'reasonCode': 'OPPORTUNITY_ENTRY',
     'score': 81, 'confidence': 75, 'regime': 'BULL', 'eligible': True,
     'positionBefore': {'valueUsd': 4000, 'pct': 5, 'size': 10}, 'recommendedDeltaUsd': 1500, 'flipConditions': []}, 'albert-decide-v1')
snap('d4', '2026-01-01T00:00:04', {'call': 'HOLD', 'action': 'HOLD', 'reasonCode': 'THESIS_INTACT',
     'score': 70, 'confidence': 66, 'regime': 'BULL', 'eligible': True,
     'positionBefore': {'valueUsd': 6300, 'pct': 7, 'size': 15}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v1')
snap('d5', '2026-01-01T00:00:05', {'call': 'SELL', 'action': 'SELL', 'reasonCode': 'PORTFOLIO_DRAWDOWN_RISK',
     'score': 55, 'confidence': 60, 'regime': 'BEAR', 'eligible': True,
     'positionBefore': {'valueUsd': 6750, 'pct': 8, 'size': 15}, 'recommendedDeltaUsd': -1687.5,
     'sellPlan': {'action': 'TRIM_25', 'fraction': 0.25, 'amountUsd': 1687.5,
                  'positionAfter': {'valueUsd': 5062.5, 'pct': 6, 'size': 11.25},
                  'allSignals': ['PORTFOLIO_DRAWDOWN_RISK', 'RISK_REDUCTION']}, 'flipConditions': []}, 'albert-decide-v1')
snap('d6', '2026-01-01T00:00:06', {'call': 'SELL', 'action': 'SELL', 'reasonCode': 'EMERGENCY_EXIT',
     'score': 30, 'confidence': 80, 'regime': 'BEAR', 'eligible': True,
     'positionBefore': {'valueUsd': 5175, 'pct': 6, 'size': 11.25}, 'recommendedDeltaUsd': -5175,
     'sellPlan': {'action': 'EXIT_100', 'fraction': 1.0, 'amountUsd': 5175,
                  'positionAfter': {'valueUsd': 0, 'pct': 0, 'size': 0},
                  'allSignals': ['EMERGENCY_EXIT', 'PORTFOLIO_DRAWDOWN_RISK']}, 'flipConditions': []}, 'albert-decide-v2')
snap('d7', '2026-01-01T00:00:07', {'call': 'WAIT', 'action': 'WAIT', 'reasonCode': 'BELOW_ENTRY_LINE',
     'score': 20, 'confidence': 40, 'regime': 'BEAR', 'eligible': True,
     'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v2')

hist('d1', 'd2', '2026-01-01T00:00:02', ['Call WAIT -> BUY'], 'WAIT->BUY')
hist('d2', 'd3', '2026-01-01T00:00:03', ['Deployment DEPLOY -> DEPLOY', 'Score 78 -> 81'], 'CHANGED')
hist('d3', 'd4', '2026-01-01T00:00:04', ['Call BUY -> HOLD'], 'BUY->HOLD')
hist('d4', 'd5', '2026-01-01T00:00:05', ['Call HOLD -> SELL'], 'HOLD->SELL')
hist('d5', 'd6', '2026-01-01T00:00:06', ['Sell action TRIM_25 -> EXIT_100'], 'TRIM_25->EXIT_100')
hist('d6', 'd7', '2026-01-01T00:00:07', ['Call SELL -> WAIT'], 'SELL->WAIT')

# orders: BUY has an EXPIRED (no fill) AND a FILLED order; ADD/TRIM/EXIT filled.
order('o_exp', 'd2', 'BUY', 'EXPIRED', 4000, 10, '2026-01-01T00:00:02', [])
order('o_buy', 'd2', 'BUY', 'FILLED', 4000, 10, '2026-01-01T00:00:02', [{'quantity': 10, 'price': 400, 'usd': 4000, 'ts': '2026-01-01T00:00:02'}])
order('o_add', 'd3', 'BUY', 'FILLED', 1500, 5, '2026-01-01T00:00:03', [{'quantity': 5, 'price': 420, 'usd': 2100, 'ts': '2026-01-01T00:00:03'}])
order('o_trim', 'd5', 'SELL', 'FILLED', 1687.5, 3.75, '2026-01-01T00:00:05', [{'quantity': 3.75, 'price': 450, 'usd': 1687.5, 'ts': '2026-01-01T00:00:05'}])
order('o_exit', 'd6', 'SELL', 'FILLED', 5175, 11.25, '2026-01-01T00:00:06', [{'quantity': 11.25, 'price': 460, 'usd': 5175, 'ts': '2026-01-01T00:00:06'}])

fill('o_buy', 'BUY', 10, 400, '2026-01-01T00:00:02')
fill('o_add', 'BUY', 5, 420, '2026-01-01T00:00:03')
fill('o_trim', 'SELL', 3.75, 450, '2026-01-01T00:00:05')
fill('o_exit', 'SELL', 11.25, 460, '2026-01-01T00:00:06')

lc = requests.get(BASE + '/v1/albert/lifecycle/' + ASSET, params={'pid': PID}, timeout=30).json()
evs = lc['events']
stages = [e['stage'] for e in evs]
calls = [e['call'] for e in evs]
prev = [e['previousCall'] for e in evs]

check('status ready + 7 events', lc['status'] == 'ready' and len(evs) == 7, 'n=%d' % len(evs))
check('stage order WAIT,BUY,ADD,HOLD,TRIM,SELL,WAIT', stages == ['WAIT', 'BUY', 'ADD', 'HOLD', 'TRIM', 'SELL', 'WAIT'], str(stages))
check('ADD preserves underlying BUY call', evs[2]['stage'] == 'ADD' and evs[2]['call'] == 'BUY')
check('TRIM preserves SELL call + TRIM_25', evs[4]['stage'] == 'TRIM' and evs[4]['call'] == 'SELL' and evs[4]['sellPlan']['action'] == 'TRIM_25')
check('SELL is full exit EXIT_100', evs[5]['stage'] == 'SELL' and evs[5]['sellPlan']['action'] == 'EXIT_100')
check('previousCall chain', prev == [None, 'WAIT', 'BUY', 'BUY', 'HOLD', 'SELL', 'SELL'], str(prev))
check('engineVersion preserved per event (no rewrite)', [e['engineVersion'] for e in evs] == ['albert-decide-v1'] * 5 + ['albert-decide-v2'] * 2)
check('currentEngineVersion is v2 (replay across upgrade)', lc['currentEngineVersion'] == 'albert-decide-v2')
check('snapshotId + hash present all events', all(e['snapshotId'] and e['decisionInputsHash'] for e in evs))
check('changeReason carried from history', evs[1]['changeReason'] == ['Call WAIT -> BUY'] and evs[3]['changeReason'] == ['Call BUY -> HOLD'] and evs[4]['changeReason'] == ['Call HOLD -> SELL'])

# drawdown intervention + precedence override
check('TRIM drawdown intervention (driven by PDR)', evs[4]['portfolioRiskIntervention'] and 'drove' in (evs[4]['portfolioRiskNote'] or ''))
check('EXIT shows precedence override (EMERGENCY over PDR)', evs[5]['portfolioRiskIntervention'] and 'took precedence' in (evs[5]['portfolioRiskNote'] or ''), evs[5]['portfolioRiskNote'])

# execution linkage + unexecuted must not look like a fill
buy_ev = evs[1]
oids = {o['orderIntentId']: o for o in buy_ev['orders']}
check('BUY event links BOTH orders (expired + filled)', set(oids) == {'o_exp', 'o_buy'}, str(list(oids)))
check('expired order shows no fills', oids['o_exp']['state'] == 'EXPIRED' and oids['o_exp']['fills'] == [])
check('filled order shows the fill', oids['o_buy']['state'] == 'FILLED' and len(oids['o_buy']['fills']) == 1)
check('BUY hasExecution true (some order filled)', buy_ev['hasExecution'] is True)

# exposure track = fills only; recommendations never bump it
track_sizes = [round(p['size'], 4) for p in lc['positionTrack']]
check('exposure track from fills only 0->10->15->11.25->0', track_sizes == [0.0, 10.0, 15.0, 11.25, 0.0], str(track_sizes))
check('current paper exposure is 0 (completed round trip, shown not hidden)', lc['currentPaperPositionSize'] == 0.0)
check('paperPositionSizeAtDecision at TRIM = 11.25', evs[4]['paperPositionSizeAtDecision'] == 11.25, str(evs[4]['paperPositionSizeAtDecision']))
check('WAIT node (unexecuted) has no orders / no execution', evs[0]['orders'] == [] and evs[0]['hasExecution'] is False)

# lifecycle-assets discovery
la = requests.get(BASE + '/v1/albert/lifecycle-assets', params={'pid': PID}, timeout=30).json()
check('lifecycle-assets includes TESTX', ASSET in la['assets'])

# graceful degradation
empty = requests.get(BASE + '/v1/albert/lifecycle/ZZZZ', params={'pid': PID}, timeout=30).json()
check('unknown asset degrades to empty (no invented events)', empty['status'] == 'empty' and empty['events'] == [] and empty['positionTrack'] == [{'ts': None, 'size': 0.0, 'kind': 'BASELINE'}])

cleanup()
print('\n=== %d/%d PASSED ===' % (sum(results), len(results)))
