"""Phase D1 pure-unit tests: SELL engine, precedence, sizing.
Run: python /app/phase_d1_unit_test.py"""
import sys
sys.path.insert(0, '/app/backend')

from albert.engine import sell, precedence, sizing
from albert.engine.constants import PROFIT_LADDER, EMERGENCY_LOSS_PCT

passed = failed = 0


def check(name, cond, extra=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS', name)
    else:
        failed += 1
        print('  FAIL', name, extra)


def base_ctx(**kw):
    c = {'symbol': 'BTC', 'positionValue': 10000.0, 'positionSize': 0.2, 'unrealizedPct': 5.0,
         'currentPrice': 50000.0, 'invalidationPrice': 42000.0, 'currentAllocationPct': 20.0,
         'capPct': 40.0, 'totalValue': 50000.0, 'excluded': set(), 'tradeRiskPct': 2.0, 'dataOk': True}
    c.update(kw)
    return c


print('--- sizing.round_up_fraction ---')
check('8% overshoot -> 10% trim (not 50%)', sizing.round_up_fraction(0.08) == 0.10, sizing.round_up_fraction(0.08))
check('0.24 -> 0.25', sizing.round_up_fraction(0.24) == 0.25)
check('0.30 -> 0.50', sizing.round_up_fraction(0.30) == 0.50)
check('0.60 -> 1.00', sizing.round_up_fraction(0.60) == 1.0)
check('action_label 1.0 -> EXIT_100', sizing.action_label(1.0) == 'EXIT_100')
check('action_label 0.25 -> TRIM_25', sizing.action_label(0.25) == 'TRIM_25')

print('--- precedence.resolve ordering ---')
sigs = [{'reasonCode': 'PROFIT_TAKE'}, {'reasonCode': 'EMERGENCY_EXIT'}, {'reasonCode': 'REBALANCE'}]
check('emergency wins over all', precedence.resolve(sigs)['reasonCode'] == 'EMERGENCY_EXIT')
check('risk beats rebalance', precedence.resolve([{'reasonCode': 'REBALANCE'}, {'reasonCode': 'RISK_REDUCTION'}])['reasonCode'] == 'RISK_REDUCTION')

print('--- SELL collision matrix ---')
# 1. EMERGENCY (excluded held) + strong everything -> EMERGENCY_EXIT 100%
r = sell.evaluate_sell(base_ctx(excluded={'BTC'}, unrealizedPct=120.0, currentAllocationPct=90.0))
check('excluded held -> EMERGENCY_EXIT', r and r['best']['reasonCode'] == 'EMERGENCY_EXIT', r)
check('  emergency -> EXIT_100 (fraction 1.0)', r['best']['fraction'] == 1.0 and r['best']['action'] == 'EXIT_100')

# 1b. Emergency by big loss
r = sell.evaluate_sell(base_ctx(unrealizedPct=-(EMERGENCY_LOSS_PCT + 5)))
check('big loss -> EMERGENCY_EXIT 100%', r and r['best']['reasonCode'] == 'EMERGENCY_EXIT' and r['best']['fraction'] == 1.0, r)

# 2. THESIS invalidation (price <= invalidation) + high profit + over-alloc -> THESIS wins
r = sell.evaluate_sell(base_ctx(currentPrice=41000.0, invalidationPrice=42000.0, unrealizedPct=120.0, currentAllocationPct=90.0))
check('price below invalidation -> THESIS_INVALIDATION', r and r['best']['reasonCode'] == 'THESIS_INVALIDATION', r)
check('  thesis -> EXIT_100', r['best']['fraction'] == 1.0)

# 3. OVER_ALLOCATION (no thesis break, modest profit) -> REBALANCE
r = sell.evaluate_sell(base_ctx(currentAllocationPct=50.0, capPct=40.0, unrealizedPct=10.0,
                                currentPrice=50000.0, invalidationPrice=48000.0))
check('over-alloc -> REBALANCE', r and r['best']['reasonCode'] == 'REBALANCE', r)
# overshoot = (50-40)/50 = 0.2 -> round up 0.25
check('  rebalance sizing 0.2 -> 0.25 trim', r['best']['fraction'] == 0.25, r['best']['fraction'])

# 3b. tiny 8% -> should not fire below tol (cur 40.5 vs cap 40 -> 0.5pp < 2pp tol)
r = sell.evaluate_sell(base_ctx(currentAllocationPct=40.5, capPct=40.0, unrealizedPct=10.0,
                                currentPrice=50000.0, invalidationPrice=48000.0))
check('tiny overshoot within tol -> no rebalance', (r is None) or (r['best']['reasonCode'] != 'REBALANCE'), r)

# 4. PROFIT_TAKE + BUY-ish (in cap, up 120%, tight stop so no risk breach, no thesis break) -> PROFIT_TAKE
r = sell.evaluate_sell(base_ctx(unrealizedPct=120.0, currentAllocationPct=20.0, capPct=40.0,
                                currentPrice=50000.0, invalidationPrice=49000.0))
check('up 120% -> PROFIT_TAKE', r and r['best']['reasonCode'] == 'PROFIT_TAKE', r)
check('  profit ladder 120% -> 25% trim', r['best']['fraction'] == 0.25, r['best']['fraction'])

# 4b. profit ladder tiers
r = sell.evaluate_sell(base_ctx(unrealizedPct=55.0, invalidationPrice=49000.0, currentAllocationPct=20.0))
check('up 55% -> PROFIT_TAKE 10%', r and r['best']['reasonCode'] == 'PROFIT_TAKE' and r['best']['fraction'] == 0.10, r)
r = sell.evaluate_sell(base_ctx(unrealizedPct=250.0, invalidationPrice=49000.0, currentAllocationPct=20.0))
check('up 250% -> PROFIT_TAKE 50%', r and r['best']['reasonCode'] == 'PROFIT_TAKE' and r['best']['fraction'] == 0.50, r)

# 5. No SELL qualifies (small gain, in cap, tight stop) -> None
r = sell.evaluate_sell(base_ctx(unrealizedPct=10.0, currentAllocationPct=20.0, capPct=40.0,
                                currentPrice=50000.0, invalidationPrice=49000.0))
check('no sell condition -> None (BUY/HOLD path)', r is None, r)

# 6. RISK_REDUCTION: wide stop makes risk-at-stop breach budget -> RISK_REDUCTION beats REBALANCE if both
# position 10k, stop 30% away -> risk 3000; budget 2%*50k=1000; 1.5x=1500 -> breach. need=1-1000/3000=0.667 -> 1.0
r = sell.evaluate_sell(base_ctx(positionValue=10000.0, totalValue=50000.0, tradeRiskPct=2.0,
                                currentPrice=50000.0, invalidationPrice=35000.0,  # 30% stop
                                unrealizedPct=5.0, currentAllocationPct=50.0, capPct=40.0))
check('risk breach + over-alloc -> RISK_REDUCTION (beats REBALANCE)', r and r['best']['reasonCode'] == 'RISK_REDUCTION', r)

print('--- unowned / zero position ---')
check('zero position -> None', sell.evaluate_sell(base_ctx(positionValue=0.0)) is None)

print()
print('SELL RANK sanity: falling score alone never appears here (no score input to sell engine)')
print()
print('RESULT: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
