"""Phase D3 Paper Lifecycle Demo — prove WAIT->BUY->ADD->HOLD->TRIM->SELL->WAIT
emerges purely from the deterministic engine as mandate/portfolio inputs change.
No manual patching of engine output. Run: python /app/phase_d3_lifecycle_demo.py"""
import sys
sys.path.insert(0, '/app/backend')
import requests, config
B = 'http://localhost:8001'
PID = 'u_D3_LIFECYCLE'
P = F = 0
def ck(name, cond, got=''):
    global P, F
    if cond: P += 1; print('  PASS', name)
    else: F += 1; print('  FAIL', name, ':: got', got)
def setm(m): requests.post(B+'/api/v1/albert/mandate', json={'pid': PID, 'mandate': m})
def setp(usdc, pos): requests.post(B+'/api/v1/portfolio', json={'pid': PID, 'usdc': usdc, 'positions': pos})
def btc():
    d = requests.get(B+'/api/v1/albert/decisions', params={'pid': PID}).json()
    b = next((x for x in d['decisions'] if x['symbol'] == 'BTC'), None)
    return b, d
def spot():
    return requests.get(B+'/api/v1/albert/portfolio-summary', params={'pid': PID}).json()

# clean slate
for c in (config.mandate_col, config.portfolio_col):
    c.delete_one({'_id': PID})
config.decision_current_col.delete_many({'pid': PID}); config.decision_snapshots_col.delete_many({'pid': PID}); config.decision_history_col.delete_many({'pid': PID})

# get BTC spot to size positions with controlled gain
px = None
try:
    px = requests.get(B+'/api/v1/ticker').json()
except Exception: pass

print('=== S1 WAIT (BTC not in approved universe) ===')
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['ETH'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
setp(50000, [])
b, _ = btc()
ck('S1 BTC WAIT + ineligible', b['action'] == 'WAIT' and b['eligible'] is False and b['ineligibilityReason'] == 'NOT_IN_APPROVED_UNIVERSE', (b['action'], b['eligible'], b['ineligibilityReason']))
S1_id = b['decisionId']

print('=== S2 BUY (approve BTC) ===')
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
setp(50000, [])
b, _ = btc()
ck('S2 BTC BUY', b['action'] == 'BUY' and b['recommendedDeployNowUsd'] > 0, (b['action'], b['recommendedDeployNowUsd']))
S2_id = b['decisionId']
cp = b['currentPrice']  # real BTC spot; use as entry so gain ~0 (no profit-take)

print('=== S3 ADD (own some BTC at ~breakeven, still BUY) ===')
setp(50000, [{'asset': 'BTC', 'size': 0.02, 'avg_entry': cp}])
b, _ = btc()
ck('S3 BTC still BUY (ADD while held)', b['action'] == 'BUY' and b['positionBefore']['valueUsd'] > 0, (b['action'], b['positionBefore']['valueUsd']))

print('=== S4 HOLD (in-cap, ~0 headroom, ~breakeven) ===')
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 3}, 'max_trade_risk_pct': 2})
setp(50000, [{'asset': 'BTC', 'size': 0.02, 'avg_entry': cp}])
b, _ = btc()
ck('S4 BTC HOLD', b['action'] == 'HOLD', (b['action'], b.get('currentAllocationPct')))
S4_id = b['decisionId']

print('=== S5 TRIM (profit-take, in-cap) ===')
# big gain (avg_entry very low), cap 100 + large usdc so allocation small & within cap,
# tight risk -> PROFIT_TAKE outranks any BUY.
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 100}, 'max_trade_risk_pct': 2})
setp(200000, [{'asset': 'BTC', 'size': 0.02, 'avg_entry': 500}])  # ~ +massive%, small position
b, _ = btc()
ck('S5 BTC SELL / PROFIT_TAKE (TRIM)', b['action'] == 'SELL' and b['reasonCode'] == 'PROFIT_TAKE' and b['sellPlan']['action'].startswith('TRIM'), (b['action'], b['reasonCode'], b.get('sellPlan', {}).get('action')))
ck('S5 sell plan has exact usd/qty + before>after', b['sellPlan']['sellUsd'] > 0 and b['positionAfter']['valueUsd'] < b['positionBefore']['valueUsd'], (b['sellPlan']['sellUsd'],))

print('=== S6 SELL full (emergency: exclude BTC) ===')
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['ETH'], 'excluded_coins': ['BTC'], 'max_alloc_pct': {'BTC': 100}, 'max_trade_risk_pct': 2})
setp(200000, [{'asset': 'BTC', 'size': 0.02, 'avg_entry': 500}])
b, _ = btc()
ck('S6 BTC SELL / EMERGENCY_EXIT / EXIT_100', b['action'] == 'SELL' and b['reasonCode'] == 'EMERGENCY_EXIT' and b['sellPlan']['action'] == 'EXIT_100' and b['sellPlan']['fraction'] == 1.0, (b['reasonCode'], b.get('sellPlan', {}).get('action')))

print('=== S7 WAIT (position closed) ===')
setm({'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['ETH'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
setp(50000, [])  # BTC no longer held, not approved
b, _ = btc()
ck('S7 BTC WAIT (flat again)', b['action'] == 'WAIT', b['action'])

print('=== Audit trail (history recorded the transitions) ===')
hist = requests.get(B+'/api/v1/albert/decision-history', params={'pid': PID, 'asset': 'BTC', 'limit': 50}).json()
types = [e['changeType'] for e in hist['events']]
print('   changeTypes (newest first):', types)
ck('history recorded WAIT->BUY', any('WAIT->BUY' in t for t in types), types)
ck('history recorded a ->HOLD transition', any('->HOLD' in t for t in types), types)
ck('history recorded a PROFIT_TAKE / TRIM transition', any('PROFIT_TAKE' in t or 'TRIM' in t for t in types), types)
ck('history recorded EMERGENCY_EXIT', any('EMERGENCY_EXIT' in t for t in types), types)
ck('history recorded a ->WAIT (exit to flat)', any('->WAIT' in t for t in types), types)
# chain integrity: every event's previous links to an earlier new id
ids_ok = True
evs = list(reversed(hist['events']))  # oldest first
for i in range(1, len(evs)):
    if evs[i]['previousDecisionId'] != evs[i-1]['newDecisionId']:
        ids_ok = False
ck('audit chain links across all transitions', ids_ok)

# cleanup
for c in (config.mandate_col, config.portfolio_col):
    c.delete_one({'_id': PID})
config.decision_current_col.delete_many({'pid': PID}); config.decision_snapshots_col.delete_many({'pid': PID}); config.decision_history_col.delete_many({'pid': PID})
print()
print('LIFECYCLE RESULT: %d passed, %d failed' % (P, F))
sys.exit(1 if F else 0)
