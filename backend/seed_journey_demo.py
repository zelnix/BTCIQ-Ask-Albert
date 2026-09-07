"""Seed a full crafted WAIT->BUY->ADD->HOLD->TRIM->SELL->WAIT journey for asset JRNY on
the demo pid so the frontend testing agent can validate every Phase H node type
(mixed engineVersion, expired-vs-filled orders, exposure-from-fills-only)."""
from config import (decision_snapshots_col, decision_history_col, order_intents_col,
                    order_ledger_col)

PID = 'u_7693422a-e2c0-4242-8211-e6f1d0eaa320'
ASSET = 'JRNY'


def clean():
    for col in (decision_snapshots_col, decision_history_col, order_intents_col, order_ledger_col):
        col.delete_many({'pid': PID, 'asset': ASSET})


def snap(did, ts, env, ver):
    env = dict(env); env.update({'decisionId': did, 'snapshotId': 'S_' + did, 'engineVersion': ver, 'decisionInputsHash': 'HJ' + did})
    decision_snapshots_col.insert_one({'_id': PID + '_' + did, 'decisionId': did, 'snapshotId': 'S_' + did,
        'pid': PID, 'asset': ASSET, 'decisionInputsHash': 'HJ' + did, 'identity': [env.get('call')],
        'envelope': env, 'createdAt': ts})


def hist(prev, new, ts, reasons, ctype):
    decision_history_col.insert_one({'_id': PID + '_evj_' + new, 'pid': PID, 'asset': ASSET,
        'previousDecisionId': prev, 'newDecisionId': new, 'previousSnapshotId': 'S_' + prev,
        'newSnapshotId': 'S_' + new, 'changedAt': ts, 'changeType': ctype, 'changeReason': reasons})


def order(oid, did, side, state, amount, qty, ts, fills):
    order_intents_col.insert_one({'_id': PID + '_' + oid, 'orderIntentId': oid, 'pid': PID, 'asset': ASSET,
        'decisionId': did, 'snapshotId': 'S_' + did, 'decisionInputsHash': 'HJ' + did,
        'idempotencyScope': 'jscope_' + oid, 'idempotencyKey': 'jkey_' + oid, 'engineVersion': 'albert-decide-v1',
        'side': side, 'state': state, 'amountUsd': amount, 'quantity': qty,
        'filledQuantity': sum(f['quantity'] for f in fills),
        'remainingQuantity': qty - sum(f['quantity'] for f in fills), 'fills': fills, 'createdAt': ts})


def fill(oid, side, q, price, ts):
    order_ledger_col.insert_one({'_id': PID + '_LJ_' + oid + '_' + ts, 'pid': PID, 'accountId': 'paper',
        'orderIntentId': oid, 'asset': ASSET, 'side': side, 'quantity': q, 'price': price,
        'usd': round(q * price, 2), 'ts': ts})


clean()
snap('j1', '2026-02-01T09:00:00', {'call': 'WAIT', 'reasonCode': 'BELOW_ENTRY_LINE', 'score': 45, 'confidence': 30,
     'regime': 'BULL', 'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v1')
snap('j2', '2026-02-02T09:00:00', {'call': 'BUY', 'reasonCode': 'OPPORTUNITY_ENTRY', 'score': 78, 'confidence': 72,
     'regime': 'BULL', 'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 4000,
     'positionAfter': {'valueUsd': 4000, 'pct': 4, 'size': 10}, 'flipConditions': [{'toState': 'WAIT', 'condition': 'Loses entry line', 'metric': 'price'}]}, 'albert-decide-v1')
snap('j3', '2026-02-03T09:00:00', {'call': 'BUY', 'reasonCode': 'OPPORTUNITY_ENTRY', 'score': 82, 'confidence': 75,
     'regime': 'BULL', 'positionBefore': {'valueUsd': 4000, 'pct': 4, 'size': 10}, 'recommendedDeltaUsd': 2100,
     'positionAfter': {'valueUsd': 6300, 'pct': 6, 'size': 15}, 'flipConditions': []}, 'albert-decide-v1')
snap('j4', '2026-02-04T09:00:00', {'call': 'HOLD', 'reasonCode': 'THESIS_INTACT', 'score': 70, 'confidence': 66,
     'regime': 'BULL', 'positionBefore': {'valueUsd': 6750, 'pct': 7, 'size': 15}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v1')
snap('j5', '2026-02-05T09:00:00', {'call': 'SELL', 'reasonCode': 'PORTFOLIO_DRAWDOWN_RISK', 'score': 55, 'confidence': 60,
     'regime': 'BEAR', 'positionBefore': {'valueUsd': 6750, 'pct': 8, 'size': 15}, 'recommendedDeltaUsd': -1687.5,
     'positionAfter': {'valueUsd': 5062.5, 'pct': 6, 'size': 11.25},
     'sellPlan': {'action': 'TRIM_25', 'fraction': 0.25, 'amountUsd': 1687.5,
                  'positionAfter': {'valueUsd': 5062.5, 'pct': 6, 'size': 11.25},
                  'allSignals': ['PORTFOLIO_DRAWDOWN_RISK', 'RISK_REDUCTION']}, 'flipConditions': []}, 'albert-decide-v1')
snap('j6', '2026-02-06T09:00:00', {'call': 'SELL', 'reasonCode': 'EMERGENCY_EXIT', 'score': 25, 'confidence': 82,
     'regime': 'BEAR', 'positionBefore': {'valueUsd': 5175, 'pct': 6, 'size': 11.25}, 'recommendedDeltaUsd': -5175,
     'positionAfter': {'valueUsd': 0, 'pct': 0, 'size': 0},
     'sellPlan': {'action': 'EXIT_100', 'fraction': 1.0, 'amountUsd': 5175,
                  'positionAfter': {'valueUsd': 0, 'pct': 0, 'size': 0},
                  'allSignals': ['EMERGENCY_EXIT', 'PORTFOLIO_DRAWDOWN_RISK']}, 'flipConditions': []}, 'albert-decide-v2')
snap('j7', '2026-02-07T09:00:00', {'call': 'WAIT', 'reasonCode': 'BELOW_ENTRY_LINE', 'score': 18, 'confidence': 40,
     'regime': 'BEAR', 'positionBefore': {'valueUsd': 0, 'pct': 0, 'size': 0}, 'recommendedDeltaUsd': 0, 'flipConditions': []}, 'albert-decide-v2')

hist('j1', 'j2', '2026-02-02T09:00:00', ['Call WAIT -> BUY'], 'WAIT->BUY')
hist('j2', 'j3', '2026-02-03T09:00:00', ['Score 78 -> 82', 'Added to position'], 'CHANGED')
hist('j3', 'j4', '2026-02-04T09:00:00', ['Call BUY -> HOLD'], 'BUY->HOLD')
hist('j4', 'j5', '2026-02-05T09:00:00', ['Call HOLD -> SELL', 'Portfolio drawdown breached'], 'HOLD->SELL')
hist('j5', 'j6', '2026-02-06T09:00:00', ['Sell action TRIM_25 -> EXIT_100', 'Emergency exit triggered'], 'ESCALATED')
hist('j6', 'j7', '2026-02-07T09:00:00', ['Call SELL -> WAIT'], 'SELL->WAIT')

order('oj_exp', 'j2', 'BUY', 'EXPIRED', 4000, 10, '2026-02-02T09:00:00', [])
order('oj_buy', 'j2', 'BUY', 'FILLED', 4000, 10, '2026-02-02T09:05:00', [{'quantity': 10, 'price': 400, 'usd': 4000, 'ts': '2026-02-02T09:05:00'}])
order('oj_add', 'j3', 'BUY', 'FILLED', 2100, 5, '2026-02-03T09:05:00', [{'quantity': 5, 'price': 420, 'usd': 2100, 'ts': '2026-02-03T09:05:00'}])
order('oj_trim', 'j5', 'SELL', 'FILLED', 1687.5, 3.75, '2026-02-05T09:05:00', [{'quantity': 3.75, 'price': 450, 'usd': 1687.5, 'ts': '2026-02-05T09:05:00'}])
order('oj_exit', 'j6', 'SELL', 'FILLED', 5175, 11.25, '2026-02-06T09:05:00', [{'quantity': 11.25, 'price': 460, 'usd': 5175, 'ts': '2026-02-06T09:05:00'}])

fill('oj_buy', 'BUY', 10, 400, '2026-02-02T09:05:00')
fill('oj_add', 'BUY', 5, 420, '2026-02-03T09:05:00')
fill('oj_trim', 'SELL', 3.75, 450, '2026-02-05T09:05:00')
fill('oj_exit', 'SELL', 11.25, 460, '2026-02-06T09:05:00')

print('Seeded JRNY journey for', PID)
