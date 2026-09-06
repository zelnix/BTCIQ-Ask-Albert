"""Phase D2 acceptance tests. Run: python /app/phase_d2_test.py"""
import sys, json, time
sys.path.insert(0, '/app/backend')
import requests
from albert.engine import hashing

B = 'http://localhost:8001'
P = 0
F = 0
def ck(name, cond, extra=''):
    global P, F
    if cond: P += 1; print('  PASS', name)
    else: F += 1; print('  FAIL', name, '::', extra)

def mandate(pid, m): return requests.post(B+'/api/v1/albert/mandate', json={'pid': pid, 'mandate': m}).json()
def portfolio(pid, usdc, pos): return requests.post(B+'/api/v1/portfolio', json={'pid': pid, 'usdc': usdc, 'positions': pos}).json()
def decisions(pid): return requests.get(B+'/api/v1/albert/decisions', params={'pid': pid}).json()
def find(d, s): return next((x for x in d['decisions'] if x['symbol'] == s), None)

print('=== GATE 1/2/3: canonical hash determinism ===')
kw = dict(engine_version='albert-decide-v1', symbol='BTC', regime='BULL', buy_threshold=72, score=81.3,
          confidence=96, eligible=True, ineligibility_reason=None,
          mandate_checks={'excluded': False, 'inApprovedUniverse': True, 'withinCap': True, 'withinRiskBudget': True, 'mandateComplete': True},
          current_allocation_pct=13.7, cap_pct=40.0, unrealized_pct=76.8, current_price=79828.4,
          invalidation=63182.27, position_value=7954.86, deployable_usdc=37500.0, total_value=57954.86,
          regime_deploy_ceiling=22500.0)
h1 = hashing.hash_inputs(hashing.canonical_inputs(**kw))
h2 = hashing.hash_inputs(hashing.canonical_inputs(**kw))
ck('same inputs -> same hash', h1 == h2, (h1, h2))
kw2 = dict(kw); kw2['score'] = 82.4
ck('material input (score) change -> hash changes', hashing.hash_inputs(hashing.canonical_inputs(**kw2)) != h1)
kw3 = dict(kw); kw3['engine_version'] = 'albert-decide-v2'
ck('engine version change -> hash changes', hashing.hash_inputs(hashing.canonical_inputs(**kw3)) != h1)
ci = hashing.canonical_inputs(**kw)
ck('canonical inputs exclude ids/timestamps/text',
   all(k not in ci for k in ('decisionId', 'snapshotId', 'evaluatedAt', 'marketDataTimestamp', 'reasons', 'flipConditions')))

print('=== GATE 6: ineligible asset scored but never BUY ===')
pid = 'u_D2_ELIG'
mandate(pid, {'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 40, 'ETH': 30}, 'max_trade_risk_pct': 2})
portfolio(pid, 50000, [{'asset': 'BTC', 'size': 0.05, 'avg_entry': 60000}])
d = decisions(pid)
xrp = find(d, 'XRP')
ck('XRP scored (>0)', xrp and xrp['opportunityScore'] > 0, xrp and xrp['opportunityScore'])
ck('XRP eligible=False, reason NOT_IN_APPROVED_UNIVERSE', xrp and xrp['eligible'] is False and xrp['ineligibilityReason'] == 'NOT_IN_APPROVED_UNIVERSE', xrp and (xrp['eligible'], xrp['ineligibilityReason']))
ck('XRP action WAIT (never BUY)', xrp and xrp['action'] == 'WAIT', xrp and xrp['action'])

print('=== GATE 4: every call has flip conditions ===')
allflip = all(isinstance(x.get('flipConditions'), list) and len(x['flipConditions']) > 0 for x in d['decisions'])
ck('all decisions have >=1 flip condition', allflip)
sample = d['decisions'][0]['flipConditions'][0]
ck('flip condition shape (toCall/trigger/detail)', all(k in sample for k in ('toCall', 'trigger', 'detail')), sample)

print('=== GATE 5: hysteresis present in BUY/HOLD flips ===')
buy = next((x for x in d['decisions'] if x['action'] == 'BUY'), None) or next((x for x in d['decisions'] if x['action'] == 'HOLD'), None)
if buy:
    triggers = [f['trigger'] for f in buy['flipConditions']]
    ck('hysteresis trigger present (REMAIN / ENTER band)', any('REMAIN' in t or 'ENTER' in t or 'RECLAIMS' in t for t in triggers), triggers)
else:
    ck('hysteresis (no BUY/HOLD to check - skipped)', True)

print('=== Envelope completeness ===')
req = ['decisionId', 'snapshotId', 'engineVersion', 'marketDataTimestamp', 'call', 'reasonCode',
       'precedenceRuleApplied', 'score', 'confidence', 'positionBefore', 'recommendedDeltaUsd', 'positionAfter',
       'invalidation', 'flipConditions', 'riskFlags', 'mandateChecks', 'deploymentPlan', 'sellPlan',
       'mandateVersion', 'portfolioVersion', 'regimeSnapshotId', 'eligible', 'ineligibilityReason', 'decisionInputsHash']
miss = [k for k in req if k not in xrp]
ck('immutable envelope has all fields', not miss, miss)

print('=== GATE 9/10/11: history transitions, no spam, audit chain ===')
pid = 'u_D2_HIST'
mandate(pid, {'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
portfolio(pid, 20000, [{'asset': 'BTC', 'size': 0.1, 'avg_entry': 60000}])
d1 = decisions(pid)
btc1 = find(d1, 'BTC')
did1 = btc1['decisionId']
# call again, no change -> stable id, no new event
d2 = decisions(pid)
btc2 = find(d2, 'BTC')
ck('GATE10: identity unchanged -> stable decisionId', btc2['decisionId'] == did1, (did1, btc2['decisionId']))
hist_after_stable = requests.get(B+'/api/v1/albert/decision-history', params={'pid': pid, 'asset': 'BTC'}).json()
n_stable = hist_after_stable['count']
ck('GATE10: no history spam on identical refresh', n_stable == 0, n_stable)
# force transition: exclude BTC -> EMERGENCY_EXIT
mandate(pid, {'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['ETH'], 'excluded_coins': ['BTC'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
d3 = decisions(pid)
btc3 = find(d3, 'BTC')
did3 = btc3['decisionId']
ck('GATE9: transition -> BTC now SELL/EMERGENCY_EXIT', btc3['action'] == 'SELL' and btc3['reasonCode'] == 'EMERGENCY_EXIT', (btc3['action'], btc3['reasonCode']))
ck('GATE9: transition mints new decisionId', did3 != did1, (did1, did3))
hist = requests.get(B+'/api/v1/albert/decision-history', params={'pid': pid, 'asset': 'BTC'}).json()
ck('GATE9: history event recorded', hist['count'] >= 1, hist['count'])
ev = hist['events'][0]
ck('GATE11: event references prev/new decisionId (chain)', ev['previousDecisionId'] == did1 and ev['newDecisionId'] == did3, (ev.get('previousDecisionId'), ev.get('newDecisionId'), did1, did3))
ck('GATE11: event references prev/new snapshotId', bool(ev['previousSnapshotId']) and bool(ev['newSnapshotId']) and ev['previousSnapshotId'] != ev['newSnapshotId'])
ck('event has changeType + changeReason[]', bool(ev.get('changeType')) and isinstance(ev.get('changeReason'), list) and len(ev['changeReason']) > 0, ev.get('changeType'))
# second transition: remove exclusion -> chain continues
mandate(pid, {'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
d4 = decisions(pid)
btc4 = find(d4, 'BTC')
did4 = btc4['decisionId']
hist2 = requests.get(B+'/api/v1/albert/decision-history', params={'pid': pid, 'asset': 'BTC'}).json()
ck('GATE11: chain links (newest.previous == prior.new)', hist2['events'][0]['previousDecisionId'] == did3 and hist2['events'][0]['newDecisionId'] == did4, (hist2['events'][0].get('previousDecisionId'), did3))

print('=== GATE 8: explain endpoint read-only ===')
# fetch immutable snapshot by decisionId then explain
fetched = requests.get(B+f'/api/v1/albert/decision/{did4}', params={'pid': pid}).json()
ck('decision fetch by id works', fetched.get('status') == 'ready' and fetched['decision']['decisionId'] == did4, fetched.get('status'))
ex = requests.post(B+'/api/v1/albert/explain-call', json={'pid': pid, 'decisionId': did4, 'question': 'Why this call and what would change it?'}, timeout=90).json()
ck('explain returns decision UNCHANGED', ex.get('decision', {}).get('decisionId') == did4 and ex['decision']['call'] == btc4['call'] and ex['decision'].get('recommendedDeltaUsd') == btc4.get('recommendedDeltaUsd'), ex.get('status'))
ck('explain does not alter score/reason', ex['decision'].get('score') == btc4.get('score') and ex['decision'].get('reasonCode') == btc4.get('reasonCode'))
print('   explanation sample:', (ex.get('explanation') or '')[:160].replace(chr(10), ' '))

print('=== GATE 7 + regression: D1 SELL precedence + A/B/C ===')
# reuse D2_HIST excluded scenario already proved EMERGENCY. quick precedence collision:
pid = 'u_D2_PREC'
mandate(pid, {'risk_tolerance': 'moderate', 'reserve_pct': 20, 'approved_coins': ['BTC'], 'max_alloc_pct': {'BTC': 10}, 'max_trade_risk_pct': 2})
portfolio(pid, 5000, [{'asset': 'BTC', 'size': 1.0, 'avg_entry': 40000}])
dp = decisions(pid)
bp = find(dp, 'BTC')
ck('GATE7: precedence RISK_REDUCTION beats co-firing REBALANCE/PROFIT_TAKE', bp['action'] == 'SELL' and bp['reasonCode'] == 'RISK_REDUCTION' and 'REBALANCE' in bp['sellPlan']['allSignals'], (bp['reasonCode'], bp['sellPlan']['allSignals']))
# A/B/C math
s = requests.get(B+'/api/v1/albert/portfolio-summary', params={'pid': 'u_D2_ELIG'}).json()
ck('regression: portfolio math', abs(s['protected_reserve'] - s['usdc']*s['reserve_pct']/100) < 0.5 and abs(s['deployable_usdc'] - (s['usdc']-s['protected_reserve'])) < 0.5)

# cleanup
import config
for pid in ['u_D2_ELIG', 'u_D2_HIST', 'u_D2_PREC']:
    config.mandate_col.delete_one({'_id': pid}); config.portfolio_col.delete_one({'_id': pid})
    config.decision_current_col.delete_many({'pid': pid})
    config.decision_snapshots_col.delete_many({'pid': pid})
    config.decision_history_col.delete_many({'pid': pid})
print()
print('RESULT: %d passed, %d failed' % (P, F))
sys.exit(1 if F else 0)
