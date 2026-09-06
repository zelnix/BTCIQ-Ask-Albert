"""Phase G local sanity test — deterministic portfolio drawdown protection.
Runs against the local FastAPI (localhost:8001) + direct Mongo for HWM seeding.
"""
import json, requests, time
from config import mandate_col, portfolio_col, portfolio_risk_col, decision_current_col, decision_snapshots_col, decision_history_col, paper_portfolio_col, order_ledger_col

BASE = 'http://localhost:8001/api'
PID = 'u_TEST_PHASE_G'


def cleanup():
    for col in (mandate_col, portfolio_col, portfolio_risk_col, decision_current_col,
                decision_snapshots_col, decision_history_col, paper_portfolio_col):
        try:
            col.delete_many({'$or': [{'_id': PID}, {'pid': PID}, {'_id': {'$regex': '^' + PID}}]})
        except Exception:
            col.delete_many({'pid': PID})
    order_ledger_col.delete_many({'pid': PID})


def setup():
    mandate_col.update_one({'_id': PID}, {'$set': {'_id': PID, 'risk_tolerance': 'moderate',
        'reserve_pct': 25, 'max_drawdown_pct': 20, 'approved_coins': ['BTC', 'ETH', 'SOL'],
        'excluded_coins': [], 'max_alloc_pct': {'BTC': 40, 'ETH': 40, 'SOL': 30},
        'max_trade_risk_pct': 2.0, 'leverage_enabled': False}}, upsert=True)
    portfolio_col.update_one({'_id': PID}, {'$set': {'_id': PID, 'usdc': 20000.0, 'positions': [
        {'asset': 'BTC', 'size': 0.3, 'avg_entry': 40000.0},
        {'asset': 'ETH', 'size': 10.0, 'avg_entry': 2000.0},
        {'asset': 'SOL', 'size': 200.0, 'avg_entry': 90.0}]}}, upsert=True)


def decisions():
    return requests.get(BASE + '/v1/albert/decisions', params={'pid': PID}, timeout=90).json()


def prisk():
    return requests.get(BASE + '/v1/albert/portfolio-risk', params={'pid': PID}, timeout=30).json()['portfolioRisk']


def seed_hwm(hwm, protection=False):
    portfolio_risk_col.update_one({'_id': PID}, {'$set': {'_id': PID, 'pid': PID,
        'highWaterMarkUsd': hwm, 'externalFlowAdjustmentUsd': 0.0, 'protectionMode': protection,
        'protectionActivatedAt': None, 'breachHwmUsd': None, 'recoveryThresholdPct': 16.0,
        'maxDrawdownPct': 20}}, upsert=True)


results = []
def check(name, ok, detail=''):
    results.append((name, ok, detail))
    print(('PASS' if ok else 'FAIL'), '-', name, ('| ' + detail) if detail else '')


cleanup(); setup()

# 1. First pass: HWM initializes to current, no drawdown, normal BUY/SELL behaviour.
pr0 = prisk()
V = pr0['currentPortfolioValueUsd']
check('1 init HWM == current value', abs(pr0['highWaterMarkUsd'] - V) < 1.0, 'HWM=%s V=%s' % (pr0['highWaterMarkUsd'], V))
check('1 no drawdown initially', pr0['drawdownPct'] == 0.0 and not pr0['protectionMode'])
check('1 enforceable (max_dd=20)', pr0['enforceable'] and pr0['maxDrawdownPct'] == 20 and pr0['recoveryThresholdPct'] == 16.0)

snap_normal = decisions()
prec = snap_normal['precedenceOrder']
check('2 precedence has PORTFOLIO_DRAWDOWN_RISK=2', prec.get('PORTFOLIO_DRAWDOWN_RISK') == 2 and prec.get('EMERGENCY_EXIT') == 1 and prec.get('RISK_REDUCTION') == 4, str(prec))
check('2 engine version v2', snap_normal['engineVersion'] == 'albert-decide-v2')
normal_buys = [d['symbol'] for d in snap_normal['decisions'] if d['action'] == 'BUY']
print('   normal-mode BUYs:', normal_buys)

# 3. Force a 25% drawdown by seeding HWM = V / 0.75 (current is 25% below HWM). Breach > 20%.
seed_hwm(round(V / 0.75, 2), protection=False)
snap = decisions()
pr = snap['portfolioRisk']
check('3 drawdown ~25%', 24.0 <= pr['drawdownPct'] <= 26.0, 'dd=%s' % pr['drawdownPct'])
check('3 breached + protectionMode active', pr['breached'] and pr['protectionMode'])
check('3 protectionActivatedAt set', bool(pr['protectionActivatedAt']) and bool(pr['triggeredAt']))
check('3 severity>0 + targetFraction>=0.25', pr['severity'] > 0 and pr['targetRiskReductionFraction'] >= 0.25, 'sev=%s tgt=%s' % (pr['severity'], pr['targetRiskReductionFraction']))
check('3 riskReductionRequiredUsd>0', pr['riskReductionRequiredUsd'] > 0, 'req=%s exposure=%s' % (pr['riskReductionRequiredUsd'], pr['totalRiskExposureUsd']))

# 4. All BUYs suppressed while protection active.
buys = [d for d in snap['decisions'] if d['action'] == 'BUY']
gated = [d['symbol'] for d in snap['decisions'] if d.get('reasonCode') == 'GATED_BY_DRAWDOWN']
check('4 zero BUYs during protection', len(buys) == 0, 'buys=%s gated=%s' % ([d['symbol'] for d in buys], gated))
check('4 totalDeployNow == 0', snap['totalDeployNowUsd'] == 0.0)

# 5. Held risk assets receive PORTFOLIO_DRAWDOWN_RISK sells + reductions recorded.
pdr_sells = [d for d in snap['decisions'] if d.get('reasonCode') == 'PORTFOLIO_DRAWDOWN_RISK']
check('5 at least one PORTFOLIO_DRAWDOWN_RISK sell', len(pdr_sells) >= 1, 'assets=%s' % [d['symbol'] for d in pdr_sells])
for d in pdr_sells:
    sp = d['sellPlan']
    ok = sp['reasonCode'] == 'PORTFOLIO_DRAWDOWN_RISK' and sp['action'] in ('TRIM_10', 'TRIM_25', 'TRIM_50', 'EXIT_100') and sp['fraction'] in (0.10, 0.25, 0.50, 1.00)
    check('5 %s sell snapped to permitted action %s frac=%s' % (d['symbol'], sp['action'], sp['fraction']), ok)
red = pr['reductions']
check('5 reductions map populated w/ basis', all('reductionBasis' in v and v['reductionBasis'] in ('RISK_CONTRIBUTION', 'PORTFOLIO_WEIGHT_FALLBACK') for v in red.values()) and len(red) >= 1, str({k: (v['reductionBasis'], v['fraction']) for k, v in red.items()}))

# 6. EMERGENCY_EXIT still outranks PORTFOLIO_DRAWDOWN_RISK (exclude a held coin).
mandate_col.update_one({'_id': PID}, {'$set': {'excluded_coins': ['SOL']}})
seed_hwm(round(V / 0.75, 2), protection=True)  # keep protection active
snap2 = decisions()
sol = next((d for d in snap2['decisions'] if d['symbol'] == 'SOL'), None)
check('6 excluded held SOL -> EMERGENCY_EXIT (outranks drawdown)', sol and sol['reasonCode'] == 'EMERGENCY_EXIT', 'SOL reason=%s' % (sol and sol.get('reasonCode')))
check('6 EMERGENCY allSignals includes PORTFOLIO_DRAWDOWN_RISK', sol and 'PORTFOLIO_DRAWDOWN_RISK' in (sol['sellPlan'].get('allSignals') or []), str(sol and sol['sellPlan'].get('allSignals')))
mandate_col.update_one({'_id': PID}, {'$set': {'excluded_coins': []}})

# 7. Recovery hysteresis: dd between 16 and 20 -> STAYS protected (was active).
seed_hwm(round(V / 0.82, 2), protection=True)  # dd ~ 18% (>16, <20)
pr7 = decisions()['portfolioRisk']
check('7 dd ~18% stays protected (hysteresis)', 16.0 < pr7['drawdownPct'] < 20.0 and pr7['protectionMode'], 'dd=%s prot=%s' % (pr7['drawdownPct'], pr7['protectionMode']))

# 8. Recovery: dd <= 16% -> protection clears, BUYs allowed again.
seed_hwm(round(V / 0.88, 2), protection=True)  # dd ~ 13.6% (<=16)
snap8 = decisions()
pr8 = snap8['portfolioRisk']
check('8 dd <=16% clears protection', pr8['drawdownPct'] <= 16.0 and not pr8['protectionMode'], 'dd=%s prot=%s' % (pr8['drawdownPct'], pr8['protectionMode']))
buys8 = [d['symbol'] for d in snap8['decisions'] if d['action'] == 'BUY']
check('8 no PORTFOLIO_DRAWDOWN_RISK sells after recovery', not any(d.get('reasonCode') == 'PORTFOLIO_DRAWDOWN_RISK' for d in snap8['decisions']))
print('   post-recovery BUYs:', buys8)

# 9. Non-enforceable mandate (no max_drawdown) -> never protected even with seeded HWM.
mandate_col.update_one({'_id': PID}, {'$unset': {'max_drawdown_pct': ''}})
seed_hwm(round(V / 0.5, 2), protection=False)
pr9 = decisions()['portfolioRisk']
check('9 no maxDrawdown -> not enforceable / never protected', not pr9['enforceable'] and not pr9['protectionMode'])

cleanup()
npass = sum(1 for _, ok, _ in results if ok)
print('\n=== %d/%d PASSED ===' % (npass, len(results)))
