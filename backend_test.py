#!/usr/bin/env python3
"""Phase G Backend Testing — Portfolio-Level Risk & Drawdown Protection

Tests the deterministic drawdown circuit breaker with HWM, stateful protection,
hysteresis recovery, precedence, and BUY suppression.

Scenarios A-F as specified in test_result.md.
"""
import requests
import time
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv('/app/.env')

# External API base
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

# MongoDB connection for direct HWM seeding
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'btciq')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# Collections
mandate_col = db['user_mandates']
portfolio_col = db['user_portfolios']
portfolio_risk_col = db['albert_portfolio_risk']
decision_current_col = db['albert_decision_current']
decision_snapshots_col = db['albert_decision_snapshots']
decision_history_col = db['albert_decision_history']
paper_portfolio_col = db['albert_paper_portfolio']
paper_ledger_col = db['albert_paper_ledger']

# Test PIDs
TEST_PIDS = []

def cleanup_test_data():
    """Clean up all test data from MongoDB collections."""
    print("\n" + "="*80)
    print("CLEANUP: Deleting test data from MongoDB collections...")
    print("="*80)
    
    if not TEST_PIDS:
        print("No test PIDs to clean up.")
        return
    
    total_deleted = 0
    for col_name, col in [
        ('user_mandates', mandate_col),
        ('user_portfolios', portfolio_col),
        ('albert_portfolio_risk', portfolio_risk_col),
        ('albert_decision_current', decision_current_col),
        ('albert_decision_snapshots', decision_snapshots_col),
        ('albert_decision_history', decision_history_col),
        ('albert_paper_portfolio', paper_portfolio_col),
        ('albert_paper_ledger', paper_ledger_col),
    ]:
        result = col.delete_many({'pid': {'$in': TEST_PIDS}})
        deleted = result.deleted_count
        total_deleted += deleted
        if deleted > 0:
            print(f"  • {col_name}: deleted {deleted} documents")
    
    print(f"\n✅ CLEANUP COMPLETE: Deleted {total_deleted} total documents for {len(TEST_PIDS)} test PIDs")
    print("="*80)


def create_mandate(pid, max_drawdown_pct=None, approved_coins=None, excluded_coins=None):
    """Create a mandate for testing."""
    if approved_coins is None:
        approved_coins = ['BTC', 'ETH', 'SOL']
    
    mandate = {
        'pid': pid,
        'risk_tolerance': 'moderate',
        'reserve_pct': 25,
        'approved_coins': approved_coins,
        'excluded_coins': excluded_coins or [],
        'max_alloc_pct': {'BTC': 40, 'ETH': 30, 'SOL': 30},
        'max_trade_risk_pct': 2,
        'leverage_enabled': False,
    }
    
    if max_drawdown_pct is not None:
        mandate['max_drawdown_pct'] = max_drawdown_pct
    
    resp = requests.post(f"{BASE_URL}/v1/albert/mandate", json=mandate, timeout=30)
    return resp


def create_portfolio(pid, usdc=20000, positions=None):
    """Create a portfolio for testing."""
    if positions is None:
        # Default: hold some BTC, ETH, SOL
        positions = [
            {'asset': 'BTC', 'size': 0.1, 'avg_entry': 80000},
            {'asset': 'ETH', 'size': 2.0, 'avg_entry': 2500},
            {'asset': 'SOL', 'size': 50, 'avg_entry': 100},
        ]
    
    portfolio = {
        'pid': pid,
        'usdc': usdc,
        'positions': positions,
    }
    
    resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio, timeout=30)
    return resp


def get_portfolio_risk(pid):
    """Get portfolio risk state (also evaluates and persists)."""
    resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", params={'pid': pid}, timeout=30)
    if resp.status_code == 200:
        # Extract portfolioRisk from nested response
        data = resp.json()
        if 'portfolioRisk' in data:
            # Create a mock response object with the portfolioRisk data
            class MockResp:
                def __init__(self, status_code, data):
                    self.status_code = status_code
                    self._data = data
                def json(self):
                    return self._data
            return MockResp(200, data['portfolioRisk'])
    return resp


def get_decisions(pid):
    """Get Albert's decisions."""
    resp = requests.get(f"{BASE_URL}/v1/albert/decisions", params={'pid': pid}, timeout=60)
    return resp


def seed_hwm_for_drawdown(pid, target_drawdown_pct):
    """Directly seed HWM in MongoDB to create a specific drawdown.
    
    target_drawdown_pct: e.g., 25 for 25% drawdown
    
    Formula: HWM = currentValue / (1 - targetDrawdown)
    E.g., for 25% drawdown: HWM = currentValue / 0.75
    """
    # First get current value
    resp = get_portfolio_risk(pid)
    if resp.status_code != 200:
        print(f"❌ Failed to get current portfolio risk: {resp.status_code}")
        return None
    
    data = resp.json()
    current_value = data.get('currentPortfolioValueUsd', 0)
    
    # Calculate HWM for target drawdown
    target_dd_fraction = target_drawdown_pct / 100.0
    new_hwm = current_value / (1 - target_dd_fraction)
    
    # Update MongoDB directly
    portfolio_risk_col.update_one(
        {'_id': pid},
        {'$set': {'highWaterMarkUsd': round(new_hwm, 2), 'protectionMode': False}},
        upsert=True
    )
    
    print(f"  • Seeded HWM: currentValue=${current_value:.2f}, targetDrawdown={target_drawdown_pct}%, newHWM=${new_hwm:.2f}")
    return new_hwm


def test_scenario_a_normal():
    """Scenario A: NORMAL state with no breach."""
    print("\n" + "="*80)
    print("TEST A: NORMAL STATE (no breach)")
    print("="*80)
    
    pid = 'u_TEST_G_A'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate with max_drawdown_pct=20
        print("\n1. Creating mandate with max_drawdown_pct=20...")
        resp = create_mandate(pid, max_drawdown_pct=20)
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created")
        
        # Create portfolio
        print("\n2. Creating portfolio...")
        resp = create_portfolio(pid)
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # Get portfolio risk (this sets initial HWM)
        print("\n3. Getting portfolio risk (sets initial HWM)...")
        resp = get_portfolio_risk(pid)
        assert resp.status_code == 200, f"Failed to get portfolio risk: {resp.status_code}"
        data = resp.json()
        
        print(f"\n  Portfolio Risk State:")
        print(f"    • highWaterMarkUsd: ${data.get('highWaterMarkUsd', 0):.2f}")
        print(f"    • currentPortfolioValueUsd: ${data.get('currentPortfolioValueUsd', 0):.2f}")
        print(f"    • drawdownPct: {data.get('drawdownPct', 0):.2f}%")
        print(f"    • maxDrawdownPct: {data.get('maxDrawdownPct')}%")
        print(f"    • recoveryThresholdPct: {data.get('recoveryThresholdPct')}%")
        print(f"    • enforceable: {data.get('enforceable')}")
        print(f"    • breached: {data.get('breached')}")
        print(f"    • protectionMode: {data.get('protectionMode')}")
        
        # Assertions
        hwm = data.get('highWaterMarkUsd', 0)
        current_value = data.get('currentPortfolioValueUsd', 0)
        assert abs(hwm - current_value) < 1.0, f"HWM should equal currentValue initially (HWM={hwm}, current={current_value})"
        assert data.get('drawdownPct', 100) == 0, f"drawdownPct should be 0 (got {data.get('drawdownPct')})"
        assert data.get('enforceable') == True, "enforceable should be True"
        assert data.get('protectionMode') == False, "protectionMode should be False"
        assert data.get('recoveryThresholdPct') == 16.0, f"recoveryThresholdPct should be 16.0 (20*0.80) (got {data.get('recoveryThresholdPct')})"
        print("\n  ✅ All portfolio risk assertions passed")
        
        # Get decisions
        print("\n4. Getting decisions...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        print(f"\n  Decisions Snapshot:")
        print(f"    • engineVersion: {data.get('engineVersion')}")
        print(f"    • precedenceOrder: {data.get('precedenceOrder')}")
        
        # Check top-level portfolioRisk
        portfolio_risk = data.get('portfolioRisk', {})
        print(f"    • portfolioRisk.protectionMode: {portfolio_risk.get('protectionMode')}")
        
        # Assertions
        assert data.get('engineVersion') == 'albert-decide-v2', f"engineVersion should be 'albert-decide-v2' (got {data.get('engineVersion')})"
        
        precedence = data.get('precedenceOrder', {})
        assert precedence.get('EMERGENCY_EXIT') == 1, "EMERGENCY_EXIT should be rank 1"
        assert precedence.get('PORTFOLIO_DRAWDOWN_RISK') == 2, "PORTFOLIO_DRAWDOWN_RISK should be rank 2"
        assert precedence.get('THESIS_INVALIDATION') == 3, "THESIS_INVALIDATION should be rank 3"
        assert precedence.get('RISK_REDUCTION') == 4, "RISK_REDUCTION should be rank 4"
        print("  ✅ Precedence order correct")
        
        assert portfolio_risk.get('protectionMode') == False, "portfolioRisk.protectionMode should be False"
        print("  ✅ portfolioRisk.protectionMode is False")
        
        print("\n✅ TEST A PASSED: NORMAL state verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST A FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST A ERROR: {e}")
        return False


def test_scenario_b_breach():
    """Scenario B: BREACH (~25% drawdown) - protection activates, BUYs suppressed, SELLs with PORTFOLIO_DRAWDOWN_RISK."""
    print("\n" + "="*80)
    print("TEST B: BREACH (~25% drawdown)")
    print("="*80)
    
    pid = 'u_TEST_G_B'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate with max_drawdown_pct=20, include more coins in approved list
        # so we have non-held BUY candidates that will be suppressed
        print("\n1. Creating mandate with max_drawdown_pct=20...")
        resp = create_mandate(pid, max_drawdown_pct=20, approved_coins=['BTC', 'ETH', 'SOL', 'XRP', 'LINK', 'ADA'])
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created")
        
        # Create portfolio with holdings
        print("\n2. Creating portfolio with BTC/ETH/SOL holdings...")
        resp = create_portfolio(pid, usdc=20000)
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # Seed HWM for ~25% drawdown
        print("\n3. Seeding HWM for ~25% drawdown...")
        seed_hwm_for_drawdown(pid, 25)
        
        # Get decisions (this triggers the state machine)
        print("\n4. Getting decisions (triggers state machine)...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        # Check portfolioRisk
        portfolio_risk = data.get('portfolioRisk', {})
        print(f"\n  Portfolio Risk State:")
        print(f"    • drawdownPct: {portfolio_risk.get('drawdownPct', 0):.2f}%")
        print(f"    • breached: {portfolio_risk.get('breached')}")
        print(f"    • protectionMode: {portfolio_risk.get('protectionMode')}")
        print(f"    • protectionActivatedAt: {portfolio_risk.get('protectionActivatedAt')}")
        print(f"    • severity: {portfolio_risk.get('severity', 0):.4f}")
        print(f"    • targetRiskReductionFraction: {portfolio_risk.get('targetRiskReductionFraction', 0):.4f}")
        print(f"    • totalRiskExposureUsd: ${portfolio_risk.get('totalRiskExposureUsd', 0):.2f}")
        print(f"    • riskReductionRequiredUsd: ${portfolio_risk.get('riskReductionRequiredUsd', 0):.2f}")
        
        # Assertions on portfolioRisk
        dd_pct = portfolio_risk.get('drawdownPct', 0)
        assert 24 <= dd_pct <= 26, f"drawdownPct should be ~25% (got {dd_pct}%)"
        assert portfolio_risk.get('breached') == True, "breached should be True"
        assert portfolio_risk.get('protectionMode') == True, "protectionMode should be True"
        assert portfolio_risk.get('protectionActivatedAt') is not None, "protectionActivatedAt should be set"
        assert portfolio_risk.get('severity', 0) > 0, "severity should be > 0"
        assert portfolio_risk.get('targetRiskReductionFraction', 0) >= 0.25, "targetRiskReductionFraction should be >= 0.25"
        assert portfolio_risk.get('riskReductionRequiredUsd', 0) > 0, "riskReductionRequiredUsd should be > 0"
        assert portfolio_risk.get('totalRiskExposureUsd', 0) > 0, "totalRiskExposureUsd should be > 0"
        print("  ✅ Portfolio risk state assertions passed")
        
        # Check reductions
        reductions = portfolio_risk.get('reductions', {})
        print(f"\n  Per-Asset Reductions:")
        for asset, red in reductions.items():
            print(f"    • {asset}: fraction={red.get('fraction')}, targetReductionUsd=${red.get('targetReductionUsd', 0):.2f}, "
                  f"reductionBasis={red.get('reductionBasis')}, riskContribution=${red.get('riskContribution', 0):.2f}")
        
        # Check that reductions have correct structure
        for asset, red in reductions.items():
            assert 'fraction' in red, f"{asset} reduction missing 'fraction'"
            assert 'targetReductionUsd' in red, f"{asset} reduction missing 'targetReductionUsd'"
            assert 'reductionBasis' in red, f"{asset} reduction missing 'reductionBasis'"
            assert red['reductionBasis'] in ['RISK_CONTRIBUTION', 'PORTFOLIO_WEIGHT_FALLBACK'], \
                f"{asset} reductionBasis should be RISK_CONTRIBUTION or PORTFOLIO_WEIGHT_FALLBACK (got {red['reductionBasis']})"
            assert 'riskContribution' in red, f"{asset} reduction missing 'riskContribution'"
        print("  ✅ Per-asset reductions structure correct")
        
        # Check BUY suppression
        print("\n5. Checking BUY suppression...")
        decisions = data.get('decisions', [])
        buy_decisions = [d for d in decisions if d.get('action') == 'BUY']
        total_deploy_now = data.get('totalDeployNowUsd', 0)
        
        print(f"    • Total decisions: {len(decisions)}")
        print(f"    • BUY decisions: {len(buy_decisions)}")
        print(f"    • totalDeployNowUsd: ${total_deploy_now:.2f}")
        
        assert len(buy_decisions) == 0, f"ALL BUYs should be suppressed (found {len(buy_decisions)} BUY decisions)"
        assert total_deploy_now == 0, f"totalDeployNowUsd should be 0 (got ${total_deploy_now})"
        print("  ✅ All BUYs suppressed")
        
        # Check for GATED_BY_DRAWDOWN reason code
        gated_decisions = [d for d in decisions if d.get('reasonCode') == 'GATED_BY_DRAWDOWN']
        print(f"    • Decisions with GATED_BY_DRAWDOWN: {len(gated_decisions)}")
        assert len(gated_decisions) > 0, "Should have decisions with reasonCode GATED_BY_DRAWDOWN"
        print("  ✅ Found GATED_BY_DRAWDOWN decisions")
        
        # Check SELL decisions for held risk assets
        print("\n6. Checking SELL decisions for held risk assets...")
        sell_decisions = [d for d in decisions if d.get('action') == 'SELL']
        pdr_sells = [d for d in sell_decisions if d.get('reasonCode') == 'PORTFOLIO_DRAWDOWN_RISK']
        
        print(f"    • Total SELL decisions: {len(sell_decisions)}")
        print(f"    • PORTFOLIO_DRAWDOWN_RISK SELLs: {len(pdr_sells)}")
        
        for d in pdr_sells:
            symbol = d.get('symbol')
            sell_plan = d.get('sellPlan', {})
            action = sell_plan.get('action')
            fraction = sell_plan.get('fraction')
            print(f"    • {symbol}: action={action}, fraction={fraction}, reasonCode={d.get('reasonCode')}")
            
            # Assertions
            assert d.get('reasonCode') == 'PORTFOLIO_DRAWDOWN_RISK', f"{symbol} reasonCode should be PORTFOLIO_DRAWDOWN_RISK"
            assert action in ['TRIM_10', 'TRIM_25', 'TRIM_50', 'EXIT_100'], \
                f"{symbol} sellPlan.action should be in {{TRIM_10,TRIM_25,TRIM_50,EXIT_100}} (got {action})"
            assert fraction in [0.10, 0.25, 0.50, 1.00], \
                f"{symbol} sellPlan.fraction should be in {{0.10,0.25,0.50,1.00}} (got {fraction})"
        
        assert len(pdr_sells) > 0, "Should have at least one PORTFOLIO_DRAWDOWN_RISK SELL"
        print("  ✅ PORTFOLIO_DRAWDOWN_RISK SELLs verified")
        
        print("\n✅ TEST B PASSED: BREACH scenario verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST B FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST B ERROR: {e}")
        return False


def test_scenario_c_emergency_outranks():
    """Scenario C: EMERGENCY_EXIT outranks PORTFOLIO_DRAWDOWN_RISK."""
    print("\n" + "="*80)
    print("TEST C: EMERGENCY_EXIT OUTRANKS PORTFOLIO_DRAWDOWN_RISK")
    print("="*80)
    
    pid = 'u_TEST_G_C'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate with max_drawdown_pct=20, initially no exclusions
        print("\n1. Creating mandate with max_drawdown_pct=20...")
        resp = create_mandate(pid, max_drawdown_pct=20, approved_coins=['BTC', 'ETH', 'SOL'])
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created")
        
        # Create portfolio with SOL holding
        print("\n2. Creating portfolio with SOL holding...")
        resp = create_portfolio(pid, usdc=20000, positions=[
            {'asset': 'BTC', 'size': 0.1, 'avg_entry': 80000},
            {'asset': 'ETH', 'size': 2.0, 'avg_entry': 2500},
            {'asset': 'SOL', 'size': 50, 'avg_entry': 100},
        ])
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # Seed HWM for ~25% drawdown and set protectionMode=True
        print("\n3. Seeding HWM for ~25% drawdown...")
        seed_hwm_for_drawdown(pid, 25)
        portfolio_risk_col.update_one({'_id': pid}, {'$set': {'protectionMode': True}})
        print("  ✅ HWM seeded and protectionMode set to True")
        
        # Update mandate to exclude SOL
        print("\n4. Updating mandate to exclude SOL...")
        resp = create_mandate(pid, max_drawdown_pct=20, approved_coins=['BTC', 'ETH', 'SOL'], excluded_coins=['SOL'])
        assert resp.status_code == 200, f"Failed to update mandate: {resp.status_code}"
        print("  ✅ Mandate updated (SOL excluded)")
        
        # Get decisions
        print("\n5. Getting decisions...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        # Find SOL decision
        decisions = data.get('decisions', [])
        sol_decision = next((d for d in decisions if d.get('symbol') == 'SOL'), None)
        
        assert sol_decision is not None, "SOL decision not found"
        
        print(f"\n  SOL Decision:")
        print(f"    • action: {sol_decision.get('action')}")
        print(f"    • reasonCode: {sol_decision.get('reasonCode')}")
        
        sell_plan = sol_decision.get('sellPlan', {})
        all_signals = sell_plan.get('allSignals', [])
        print(f"    • sellPlan.allSignals: {all_signals}")
        
        # Assertions
        assert sol_decision.get('action') == 'SELL', "SOL action should be SELL"
        assert sol_decision.get('reasonCode') == 'EMERGENCY_EXIT', \
            f"SOL reasonCode should be EMERGENCY_EXIT (got {sol_decision.get('reasonCode')})"
        assert 'PORTFOLIO_DRAWDOWN_RISK' in all_signals, \
            "SOL sellPlan.allSignals should include PORTFOLIO_DRAWDOWN_RISK"
        print("  ✅ EMERGENCY_EXIT outranks PORTFOLIO_DRAWDOWN_RISK")
        
        # Remove exclusion for cleanup
        print("\n6. Removing SOL from excluded_coins...")
        resp = create_mandate(pid, max_drawdown_pct=20, approved_coins=['BTC', 'ETH', 'SOL'], excluded_coins=[])
        assert resp.status_code == 200, f"Failed to update mandate: {resp.status_code}"
        print("  ✅ Exclusion removed")
        
        print("\n✅ TEST C PASSED: EMERGENCY_EXIT precedence verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST C FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST C ERROR: {e}")
        return False


def test_scenario_d_hysteresis():
    """Scenario D: HYSTERESIS - protection stays active between recovery and max, clears at recovery."""
    print("\n" + "="*80)
    print("TEST D: HYSTERESIS (recovery threshold)")
    print("="*80)
    
    pid = 'u_TEST_G_D'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate with max_drawdown_pct=20
        print("\n1. Creating mandate with max_drawdown_pct=20...")
        resp = create_mandate(pid, max_drawdown_pct=20)
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created")
        
        # Create portfolio
        print("\n2. Creating portfolio...")
        resp = create_portfolio(pid, usdc=20000)
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # First, establish initial HWM
        print("\n3. Establishing initial HWM...")
        resp = get_portfolio_risk(pid)
        assert resp.status_code == 200, f"Failed to get portfolio risk: {resp.status_code}"
        
        # Seed HWM for ~18% drawdown (between 16% recovery and 20% max) with protectionMode=True
        print("\n4. Seeding HWM for ~18% drawdown (between recovery 16% and max 20%)...")
        seed_hwm_for_drawdown(pid, 18)
        portfolio_risk_col.update_one({'_id': pid}, {'$set': {'protectionMode': True}})
        print("  ✅ HWM seeded for 18% drawdown, protectionMode=True")
        
        # Get decisions
        print("\n5. Getting decisions (should stay protected)...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        portfolio_risk = data.get('portfolioRisk', {})
        dd_pct = portfolio_risk.get('drawdownPct', 0)
        protection_mode = portfolio_risk.get('protectionMode')
        
        print(f"\n  Portfolio Risk State (18% drawdown):")
        print(f"    • drawdownPct: {dd_pct:.2f}%")
        print(f"    • protectionMode: {protection_mode}")
        
        # Assertions - should stay protected
        assert 16 < dd_pct < 20, f"drawdownPct should be between 16% and 20% (got {dd_pct}%)"
        assert protection_mode == True, f"protectionMode should stay True (got {protection_mode})"
        print("  ✅ Protection stays active between recovery and max")
        
        # Now seed HWM for ~12% drawdown (below 16% recovery threshold)
        print("\n6. Seeding HWM for ~12% drawdown (below recovery 16%)...")
        seed_hwm_for_drawdown(pid, 12)
        portfolio_risk_col.update_one({'_id': pid}, {'$set': {'protectionMode': True}})
        print("  ✅ HWM seeded for 12% drawdown, protectionMode=True")
        
        # Get decisions
        print("\n7. Getting decisions (should clear protection)...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        portfolio_risk = data.get('portfolioRisk', {})
        dd_pct = portfolio_risk.get('drawdownPct', 0)
        protection_mode = portfolio_risk.get('protectionMode')
        
        print(f"\n  Portfolio Risk State (12% drawdown):")
        print(f"    • drawdownPct: {dd_pct:.2f}%")
        print(f"    • protectionMode: {protection_mode}")
        
        # Assertions - should clear protection
        assert dd_pct <= 16, f"drawdownPct should be <= 16% (got {dd_pct}%)"
        assert protection_mode == False, f"protectionMode should become False (got {protection_mode})"
        print("  ✅ Protection cleared at recovery threshold")
        
        # Check that PORTFOLIO_DRAWDOWN_RISK SELLs are gone
        decisions = data.get('decisions', [])
        pdr_sells = [d for d in decisions if d.get('reasonCode') == 'PORTFOLIO_DRAWDOWN_RISK']
        print(f"\n    • PORTFOLIO_DRAWDOWN_RISK SELLs: {len(pdr_sells)}")
        assert len(pdr_sells) == 0, "Should have no PORTFOLIO_DRAWDOWN_RISK SELLs when protection cleared"
        print("  ✅ No PORTFOLIO_DRAWDOWN_RISK SELLs")
        
        # Check that BUYs are no longer suppressed
        buy_decisions = [d for d in decisions if d.get('action') == 'BUY']
        gated_decisions = [d for d in decisions if d.get('reasonCode') == 'GATED_BY_DRAWDOWN']
        print(f"    • BUY decisions: {len(buy_decisions)}")
        print(f"    • GATED_BY_DRAWDOWN decisions: {len(gated_decisions)}")
        # Note: BUYs may still be 0 if no opportunities, but GATED_BY_DRAWDOWN should be 0
        assert len(gated_decisions) == 0, "Should have no GATED_BY_DRAWDOWN decisions when protection cleared"
        print("  ✅ BUYs no longer force-suppressed by drawdown")
        
        print("\n✅ TEST D PASSED: HYSTERESIS verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST D FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST D ERROR: {e}")
        return False


def test_scenario_e_non_enforceable():
    """Scenario E: NON-ENFORCEABLE - no max_drawdown_pct means never protects."""
    print("\n" + "="*80)
    print("TEST E: NON-ENFORCEABLE (no max_drawdown_pct)")
    print("="*80)
    
    pid = 'u_TEST_G_E'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate WITHOUT max_drawdown_pct
        print("\n1. Creating mandate WITHOUT max_drawdown_pct...")
        resp = create_mandate(pid, max_drawdown_pct=None)
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created (no max_drawdown_pct)")
        
        # Create portfolio
        print("\n2. Creating portfolio...")
        resp = create_portfolio(pid, usdc=20000)
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # Establish initial HWM
        print("\n3. Establishing initial HWM...")
        resp = get_portfolio_risk(pid)
        assert resp.status_code == 200, f"Failed to get portfolio risk: {resp.status_code}"
        
        # Seed a huge HWM (50% drawdown)
        print("\n4. Seeding huge HWM for ~50% drawdown...")
        seed_hwm_for_drawdown(pid, 50)
        
        # Get decisions
        print("\n5. Getting decisions...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        portfolio_risk = data.get('portfolioRisk', {})
        print(f"\n  Portfolio Risk State:")
        print(f"    • enforceable: {portfolio_risk.get('enforceable')}")
        print(f"    • protectionMode: {portfolio_risk.get('protectionMode')}")
        print(f"    • drawdownPct: {portfolio_risk.get('drawdownPct', 0):.2f}%")
        
        # Assertions
        assert portfolio_risk.get('enforceable') == False, "enforceable should be False"
        assert portfolio_risk.get('protectionMode') == False, "protectionMode should be False"
        print("  ✅ Non-enforceable: never protects even with huge drawdown")
        
        print("\n✅ TEST E PASSED: NON-ENFORCEABLE verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST E FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST E ERROR: {e}")
        return False


def test_scenario_f_regression():
    """Scenario F: REGRESSION - non-breached pid behaves normally, paper-order endpoints work."""
    print("\n" + "="*80)
    print("TEST F: REGRESSION (non-breached pid + paper-order endpoints)")
    print("="*80)
    
    pid = 'u_TEST_G_F'
    TEST_PIDS.append(pid)
    
    try:
        # Create mandate with max_drawdown_pct=20
        print("\n1. Creating mandate with max_drawdown_pct=20...")
        resp = create_mandate(pid, max_drawdown_pct=20)
        assert resp.status_code == 200, f"Failed to create mandate: {resp.status_code}"
        print("  ✅ Mandate created")
        
        # Create portfolio
        print("\n2. Creating portfolio...")
        resp = create_portfolio(pid, usdc=50000, positions=[
            {'asset': 'BTC', 'size': 0.1, 'avg_entry': 60000},
        ])
        assert resp.status_code == 200, f"Failed to create portfolio: {resp.status_code}"
        print("  ✅ Portfolio created")
        
        # Get decisions (non-breached)
        print("\n3. Getting decisions (non-breached)...")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Failed to get decisions: {resp.status_code}"
        data = resp.json()
        
        # Check that it behaves normally
        portfolio_risk = data.get('portfolioRisk', {})
        print(f"\n  Portfolio Risk State:")
        print(f"    • protectionMode: {portfolio_risk.get('protectionMode')}")
        print(f"    • drawdownPct: {portfolio_risk.get('drawdownPct', 0):.2f}%")
        
        assert portfolio_risk.get('protectionMode') == False, "protectionMode should be False"
        print("  ✅ Non-breached: protectionMode is False")
        
        # Check decisions structure
        decisions = data.get('decisions', [])
        print(f"\n  Decisions:")
        print(f"    • Total decisions: {len(decisions)}")
        
        # Check for normal BUY/HOLD/SELL/WAIT decisions
        actions = [d.get('action') for d in decisions]
        print(f"    • Actions: {set(actions)}")
        
        # Check tranche sums for BUY decisions
        buy_decisions = [d for d in decisions if d.get('action') == 'BUY']
        print(f"    • BUY decisions: {len(buy_decisions)}")
        
        for d in buy_decisions:
            symbol = d.get('symbol')
            # Use top-level fields, not deploymentPlan
            total_planned = d.get('totalPlannedDeploymentUsd', 0)
            tranches = d.get('tranches', [])
            tranche_sum = sum(t.get('amountUsd', 0) for t in tranches)
            print(f"      • {symbol}: totalPlanned=${total_planned:.2f}, tranche_sum=${tranche_sum:.2f}")
            assert abs(tranche_sum - total_planned) < 0.5, \
                f"{symbol} tranche sum should match totalPlanned (sum={tranche_sum}, planned={total_planned})"
        print("  ✅ Tranche sums match totalPlanned")
        
        # Check deployNow <= deployable
        total_deploy_now = data.get('totalDeployNowUsd', 0)
        deployable = data.get('deployableUsdc', 0)
        print(f"    • totalDeployNowUsd: ${total_deploy_now:.2f}")
        print(f"    • deployableUsdc: ${deployable:.2f}")
        assert total_deploy_now <= deployable + 0.01, \
            f"totalDeployNowUsd should be <= deployableUsdc (deployNow={total_deploy_now}, deployable={deployable})"
        print("  ✅ deployNow <= deployable")
        
        # Check D1 SELL precedence (position RISK_REDUCTION is now rank 4)
        sell_decisions = [d for d in decisions if d.get('action') == 'SELL']
        print(f"    • SELL decisions: {len(sell_decisions)}")
        
        for d in sell_decisions:
            symbol = d.get('symbol')
            reason = d.get('reasonCode')
            precedence_rank = data.get('precedenceOrder', {}).get(reason, 999)
            print(f"      • {symbol}: reasonCode={reason}, precedence={precedence_rank}")
        
        # Check precedence order
        precedence = data.get('precedenceOrder', {})
        assert precedence.get('RISK_REDUCTION') == 4, "RISK_REDUCTION should be rank 4"
        assert precedence.get('REBALANCE') == 5, "REBALANCE should be rank 5"
        print("  ✅ D1 SELL precedence intact (RISK_REDUCTION=4, REBALANCE=5)")
        
        # Test paper-order create/confirm/execute
        print("\n4. Testing paper-order create/confirm/execute...")
        
        # Find a BUY decision to create an order
        if buy_decisions:
            buy_dec = buy_decisions[0]
            symbol = buy_dec.get('symbol')
            decision_id = buy_dec.get('decisionId')
            amount_usd = 1000
            
            print(f"    • Creating paper order for {symbol} (decisionId={decision_id})...")
            
            # Create order intent
            create_payload = {
                'pid': pid,
                'portfolioId': 'default',
                'accountId': 'paper',
                'decisionId': decision_id,
                'side': 'BUY',
                'asset': symbol,
                'amountUsd': amount_usd,
                'idempotencyKey': f'test_f_{symbol}_1',
            }
            
            resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
            assert resp.status_code == 200, f"Failed to create order: {resp.status_code}"
            order_data = resp.json()
            # Extract intent from nested response
            intent = order_data.get('intent', order_data)
            order_id = intent.get('orderIntentId')
            print(f"      ✅ Order created: {order_id}")
            
            # Confirm order
            print(f"    • Confirming order {order_id}...")
            resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", json={'pid': pid}, timeout=30)
            assert resp.status_code == 200, f"Failed to confirm order: {resp.status_code}"
            print(f"      ✅ Order confirmed")
            
            # Execute order
            print(f"    • Executing order {order_id}...")
            resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={'pid': pid}, timeout=30)
            assert resp.status_code == 200, f"Failed to execute order: {resp.status_code}"
            exec_data = resp.json()
            # Extract intent from nested response
            exec_intent = exec_data.get('intent', exec_data)
            state = exec_intent.get('state')
            status = exec_data.get('status')
            print(f"      ✅ Order executed: state={state}, status={status}")
            # Accept either FILLED or REJECTED (staleness is expected in fast-changing markets)
            assert state in ['FILLED', 'REJECTED'], f"Order should reach FILLED or REJECTED state (got {state})"
            if state == 'REJECTED':
                print(f"      ⚠️  Order rejected (likely due to staleness - acceptable for Phase E)")
            
            print("  ✅ Paper-order create/confirm/execute works")
        else:
            print("    ⚠️  No BUY decisions available, skipping paper-order test")
        
        # Test paper-reset
        print("\n5. Testing paper-reset...")
        resp = requests.post(f"{BASE_URL}/v1/albert/paper-reset", json={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Failed to reset paper portfolio: {resp.status_code}"
        print("  ✅ Paper-reset successful")
        
        # Verify portfolio_risk_col is cleared
        risk_doc = portfolio_risk_col.find_one({'_id': pid})
        print(f"    • portfolio_risk_col doc after reset: {risk_doc}")
        assert risk_doc is None, "portfolio_risk_col should be cleared after paper-reset"
        print("  ✅ portfolio_risk_col cleared by paper-reset")
        
        print("\n✅ TEST F PASSED: REGRESSION verified")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST F FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST F ERROR: {e}")
        return False


def main():
    """Run all Phase G tests."""
    print("\n" + "="*80)
    print("PHASE G BACKEND TESTING — Portfolio-Level Risk & Drawdown Protection")
    print("="*80)
    print(f"API Base: {BASE_URL}")
    print(f"MongoDB: {MONGO_URL}/{DB_NAME}")
    print("="*80)
    
    results = {}
    
    try:
        # Run all scenarios
        results['A_NORMAL'] = test_scenario_a_normal()
        results['B_BREACH'] = test_scenario_b_breach()
        results['C_EMERGENCY_OUTRANKS'] = test_scenario_c_emergency_outranks()
        results['D_HYSTERESIS'] = test_scenario_d_hysteresis()
        results['E_NON_ENFORCEABLE'] = test_scenario_e_non_enforceable()
        results['F_REGRESSION'] = test_scenario_f_regression()
        
    finally:
        # Always clean up
        cleanup_test_data()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*80)
    
    return passed == total


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
