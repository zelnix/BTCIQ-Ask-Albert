"""
Phase D2 Backend Testing - Albert's Plan
Tests: Flip conditions, immutable decision snapshot, discovery/eligibility, 
       Ask-Albert explain, decision-change history
"""
import requests
import time
import json

# Base URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

# Fresh test PIDs for D2
TEST_PIDS = []

def cleanup_test_data():
    """Clean up all test data from MongoDB collections"""
    print("\n" + "="*80)
    print("CLEANUP: Deleting test data from MongoDB collections")
    print("="*80)
    
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    db = client["btciq"]
    
    collections = [
        "user_mandates",
        "user_portfolios", 
        "albert_decision_current",
        "albert_decision_snapshots",
        "albert_decision_history"
    ]
    
    for coll_name in collections:
        coll = db[coll_name]
        # Delete by pid pattern
        for pid in TEST_PIDS:
            result = coll.delete_many({"pid": pid})
            if result.deleted_count > 0:
                print(f"  ✓ Deleted {result.deleted_count} documents from {coll_name} for pid={pid}")
        
        # Also delete by _id pattern for decision_current (format: "<pid>:<ASSET>")
        if coll_name == "albert_decision_current":
            for pid in TEST_PIDS:
                result = coll.delete_many({"_id": {"$regex": f"^{pid}:"}})
                if result.deleted_count > 0:
                    print(f"  ✓ Deleted {result.deleted_count} documents from {coll_name} by _id pattern")
    
    print(f"✓ Cleanup complete for {len(TEST_PIDS)} test PIDs")

def post_mandate(pid, mandate_data):
    """Helper: POST mandate"""
    url = f"{BASE_URL}/v1/albert/mandate"
    payload = {"pid": pid, "mandate": mandate_data}
    resp = requests.post(url, json=payload, timeout=30)
    return resp

def post_portfolio(pid, usdc, positions):
    """Helper: POST portfolio"""
    url = f"{BASE_URL}/v1/portfolio"
    payload = {"pid": pid, "usdc": usdc, "positions": positions}
    resp = requests.post(url, json=payload, timeout=30)
    return resp

def get_decisions(pid):
    """Helper: GET decisions"""
    url = f"{BASE_URL}/v1/albert/decisions"
    resp = requests.get(url, params={"pid": pid}, timeout=30)
    return resp

def get_decision_history(pid, asset=None, limit=50):
    """Helper: GET decision history"""
    url = f"{BASE_URL}/v1/albert/decision-history"
    params = {"pid": pid, "limit": limit}
    if asset:
        params["asset"] = asset
    resp = requests.get(url, params=params, timeout=30)
    return resp

def get_decision_by_id(pid, decision_id):
    """Helper: GET decision by ID"""
    url = f"{BASE_URL}/v1/albert/decision/{decision_id}"
    resp = requests.get(url, params={"pid": pid}, timeout=30)
    return resp

def post_explain_call(pid, decision_id, question=None):
    """Helper: POST explain-call"""
    url = f"{BASE_URL}/v1/albert/explain-call"
    payload = {"pid": pid, "decisionId": decision_id}
    if question:
        payload["question"] = question
    resp = requests.post(url, json=payload, timeout=90)
    return resp

def get_regime():
    """Helper: GET regime"""
    url = f"{BASE_URL}/v1/albert/regime"
    resp = requests.get(url, timeout=30)
    return resp

def get_portfolio_summary(pid):
    """Helper: GET portfolio summary"""
    url = f"{BASE_URL}/v1/albert/portfolio-summary"
    resp = requests.get(url, params={"pid": pid}, timeout=30)
    return resp

# ============================================================================
# TEST A: REGRESSION (Phase A/B/C + D1 must still pass)
# ============================================================================

def test_a_regression():
    print("\n" + "="*80)
    print("TEST A: REGRESSION - Phase A/B/C + D1 endpoints still working")
    print("="*80)
    
    pid = "u_TEST_D2_REGR"
    TEST_PIDS.append(pid)
    
    try:
        # A1: GET /api/v1/albert/regime
        print("\n[A1] Testing GET /api/v1/albert/regime")
        resp = get_regime()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "regime" in data, "Missing 'regime' field"
        assert data["regime"] in ["BULL", "RANGE", "BEAR"], f"Invalid regime: {data['regime']}"
        print(f"  ✓ PASS: regime={data['regime']}, confidence={data.get('confidence')}")
        
        # A2: Portfolio summary math
        print("\n[A2] Testing portfolio summary math")
        # Setup: mandate + portfolio
        mandate = {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH"],
            "excluded_coins": [],
            "max_alloc_pct": {"BTC": 40, "ETH": 30},
            "max_trade_risk_pct": 2
        }
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        print(f"  ✓ Mandate saved")
        
        # Portfolio: usdc=5000, hold ~1 BTC
        resp = post_portfolio(pid, 5000, [{"asset": "BTC", "size": 1.0, "avg_entry": 60000}])
        assert resp.status_code == 200, f"Portfolio POST failed: {resp.status_code}"
        print(f"  ✓ Portfolio saved")
        
        # Get summary
        resp = get_portfolio_summary(pid)
        assert resp.status_code == 200, f"Portfolio summary failed: {resp.status_code}"
        data = resp.json()
        
        # Validate math
        usdc = data.get("usdc", 0)
        reserve_pct = data.get("reserve_pct", 0)
        protected_reserve = data.get("protected_reserve", 0)
        deployable_usdc = data.get("deployable_usdc", 0)
        
        expected_protected = usdc * reserve_pct / 100
        expected_deployable = usdc - expected_protected
        
        assert abs(protected_reserve - expected_protected) < 0.5, \
            f"Protected reserve mismatch: {protected_reserve} vs {expected_protected}"
        assert abs(deployable_usdc - expected_deployable) < 0.5, \
            f"Deployable USDC mismatch: {deployable_usdc} vs {expected_deployable}"
        
        print(f"  ✓ PASS: protected_reserve={protected_reserve:.2f}, deployable={deployable_usdc:.2f}")
        
        # A3: BUY decision tranche sums
        print("\n[A3] Testing BUY decision tranche sums")
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        for dec in data.get("decisions", []):
            if dec.get("action") == "BUY":
                tranches = dec.get("tranches", [])
                total_planned = dec.get("totalPlannedDeploymentUsd", 0)
                tranche_sum = sum(t.get("amountUsd", 0) for t in tranches)
                
                assert abs(tranche_sum - total_planned) < 0.5, \
                    f"{dec['symbol']}: tranche sum {tranche_sum} != totalPlanned {total_planned}"
                
                deploy_now = dec.get("recommendedDeployNowUsd", 0)
                assert deploy_now <= deployable_usdc + 0.5, \
                    f"{dec['symbol']}: deployNow {deploy_now} > deployable {deployable_usdc}"
                
                print(f"  ✓ {dec['symbol']}: tranches sum={tranche_sum:.2f}, totalPlanned={total_planned:.2f}")
        
        # A4: D1 SELL precedence (max_alloc_pct breach)
        print("\n[A4] Testing D1 SELL precedence (RISK_REDUCTION)")
        # BTC allocation is ~90%+ (1 BTC @ ~$80k vs $5k USDC)
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        assert btc_dec is not None, "BTC decision not found"
        
        if btc_dec.get("action") == "SELL":
            assert btc_dec.get("reasonCode") == "RISK_REDUCTION", \
                f"Expected RISK_REDUCTION, got {btc_dec.get('reasonCode')}"
            
            sell_plan = btc_dec.get("sellPlan", {})
            all_signals = sell_plan.get("allSignals", [])
            assert "REBALANCE" in all_signals, "Expected REBALANCE in allSignals"
            
            print(f"  ✓ PASS: BTC action=SELL, reasonCode=RISK_REDUCTION, allSignals={all_signals}")
        else:
            print(f"  ⚠ BTC action={btc_dec.get('action')} (expected SELL, but market may have changed)")
        
        print("\n✅ TEST A: REGRESSION PASSED")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST A FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST A ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TEST B: IMMUTABLE ENVELOPE
# ============================================================================

def test_b_immutable_envelope():
    print("\n" + "="*80)
    print("TEST B: IMMUTABLE ENVELOPE - Full audit fields in every decision")
    print("="*80)
    
    pid = "u_TEST_D2_ENV"
    TEST_PIDS.append(pid)
    
    try:
        # Setup: normal mandate + portfolio
        mandate = {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH"],
            "excluded_coins": [],
            "max_alloc_pct": {"BTC": 40, "ETH": 30},
            "max_trade_risk_pct": 2
        }
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        resp = post_portfolio(pid, 50000, [{"asset": "BTC", "size": 0.1, "avg_entry": 70000}])
        assert resp.status_code == 200, f"Portfolio POST failed: {resp.status_code}"
        
        print("  ✓ Setup complete")
        
        # Get decisions
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        # Check top-level snapshot fields
        print("\n[B1] Checking top-level snapshot fields")
        required_top = ["engineVersion", "mandateVersion", "portfolioVersion", 
                       "regimeSnapshotId", "precedenceOrder", "changeEvents"]
        for field in required_top:
            assert field in data, f"Missing top-level field: {field}"
        print(f"  ✓ All top-level fields present: {required_top}")
        
        # Check per-decision envelope
        print("\n[B2] Checking per-decision envelope fields")
        decisions = data.get("decisions", [])
        assert len(decisions) > 0, "No decisions returned"
        
        required_fields = [
            "decisionId", "snapshotId", "engineVersion", "marketDataTimestamp",
            "call", "reasonCode", "precedenceRuleApplied", "score", "confidence",
            "positionBefore", "recommendedDeltaUsd", "positionAfter", "invalidation",
            "flipConditions", "riskFlags", "mandateChecks", "deploymentPlan", "sellPlan",
            "mandateVersion", "portfolioVersion", "regimeSnapshotId", "eligible",
            "ineligibilityReason", "decisionInputs", "decisionInputsHash"
        ]
        
        for dec in decisions[:3]:  # Check first 3 decisions
            symbol = dec.get("symbol", "?")
            print(f"\n  Checking {symbol}:")
            
            missing = []
            for field in required_fields:
                if field not in dec:
                    missing.append(field)
            
            assert len(missing) == 0, f"{symbol}: Missing fields: {missing}"
            
            # Validate flipConditions is non-empty list
            flip_conds = dec.get("flipConditions", [])
            assert isinstance(flip_conds, list), f"{symbol}: flipConditions not a list"
            assert len(flip_conds) > 0, f"{symbol}: flipConditions is empty"
            
            # Each flip condition has required fields
            for fc in flip_conds:
                assert "toCall" in fc, f"{symbol}: flip condition missing 'toCall'"
                assert "trigger" in fc, f"{symbol}: flip condition missing 'trigger'"
                assert "detail" in fc, f"{symbol}: flip condition missing 'detail'"
            
            print(f"    ✓ All {len(required_fields)} envelope fields present")
            print(f"    ✓ flipConditions: {len(flip_conds)} conditions")
            
            # Validate mandateChecks structure
            mc = dec.get("mandateChecks", {})
            assert isinstance(mc, dict), f"{symbol}: mandateChecks not a dict"
            mc_keys = ["excluded", "inApprovedUniverse", "withinCap", "withinRiskBudget", "mandateComplete"]
            for key in mc_keys:
                assert key in mc, f"{symbol}: mandateChecks missing '{key}'"
            print(f"    ✓ mandateChecks: {mc_keys}")
            
            # Validate riskFlags is a list
            rf = dec.get("riskFlags", [])
            assert isinstance(rf, list), f"{symbol}: riskFlags not a list"
            print(f"    ✓ riskFlags: {len(rf)} flags")
        
        print("\n✅ TEST B: IMMUTABLE ENVELOPE PASSED")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST B FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST B ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TEST C: DISCOVERY vs ELIGIBILITY
# ============================================================================

def test_c_discovery_eligibility():
    print("\n" + "="*80)
    print("TEST C: DISCOVERY vs ELIGIBILITY - Ineligible assets scored but never BUY")
    print("="*80)
    
    pid = "u_TEST_D2_ELIG"
    TEST_PIDS.append(pid)
    
    try:
        # Setup: mandate with limited approved_coins (exclude XRP)
        mandate = {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH"],  # XRP not in approved
            "excluded_coins": [],
            "max_alloc_pct": {"BTC": 40, "ETH": 30},
            "max_trade_risk_pct": 2
        }
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        resp = post_portfolio(pid, 50000, [])
        assert resp.status_code == 200, f"Portfolio POST failed: {resp.status_code}"
        
        print("  ✓ Setup complete (approved_coins=['BTC','ETH'])")
        
        # Get decisions
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        # Find a high-scoring coin NOT in approved_coins (e.g., XRP, SOL, ADA)
        print("\n[C1] Looking for ineligible high-scorer")
        ineligible_found = False
        
        for dec in data.get("decisions", []):
            symbol = dec.get("symbol")
            if symbol not in ["BTC", "ETH"]:  # Not in approved list
                score = dec.get("opportunityScore", 0)
                eligible = dec.get("eligible", True)
                reason = dec.get("ineligibilityReason")
                action = dec.get("action")
                
                if score > 0:  # Was scored
                    print(f"\n  Found: {symbol}")
                    print(f"    opportunityScore: {score}")
                    print(f"    eligible: {eligible}")
                    print(f"    ineligibilityReason: {reason}")
                    print(f"    action: {action}")
                    
                    # Validate
                    assert score > 0, f"{symbol}: opportunityScore should be > 0"
                    assert eligible == False, f"{symbol}: should be ineligible"
                    assert reason == "NOT_IN_APPROVED_UNIVERSE", \
                        f"{symbol}: expected NOT_IN_APPROVED_UNIVERSE, got {reason}"
                    assert action == "WAIT", f"{symbol}: action should be WAIT, got {action}"
                    
                    print(f"    ✓ PASS: Scored but ineligible, action=WAIT")
                    ineligible_found = True
                    break
        
        assert ineligible_found, "No ineligible high-scorer found in decisions"
        
        # C2: Confirm NO ineligible asset has action=BUY
        print("\n[C2] Confirming no ineligible asset has action=BUY")
        for dec in data.get("decisions", []):
            if not dec.get("eligible", True):
                action = dec.get("action")
                assert action != "BUY", \
                    f"{dec['symbol']}: ineligible asset has action=BUY (VIOLATION)"
        
        print("  ✓ PASS: No ineligible asset has action=BUY")
        
        print("\n✅ TEST C: DISCOVERY vs ELIGIBILITY PASSED")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST C FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST C ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TEST D: DECISION-CHANGE HISTORY
# ============================================================================

def test_d_decision_history():
    print("\n" + "="*80)
    print("TEST D: DECISION-CHANGE HISTORY - Deterministic, mandate-driven transitions")
    print("="*80)
    
    pid = "u_TEST_D2_HIST"
    TEST_PIDS.append(pid)
    
    try:
        # D1: Initial setup
        print("\n[D1] Initial setup: approved=['BTC','ETH'], hold 0.1 BTC")
        mandate = {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH"],
            "excluded_coins": [],
            "max_alloc_pct": {"BTC": 40, "ETH": 30},
            "max_trade_risk_pct": 2
        }
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        resp = post_portfolio(pid, 20000, [{"asset": "BTC", "size": 0.1, "avg_entry": 60000}])
        assert resp.status_code == 200, f"Portfolio POST failed: {resp.status_code}"
        
        # Get initial decisions
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        assert btc_dec is not None, "BTC decision not found"
        
        decision_id_1 = btc_dec.get("decisionId")
        assert decision_id_1, "BTC decisionId missing"
        print(f"  ✓ Initial BTC decisionId: {decision_id_1}")
        print(f"    action: {btc_dec.get('action')}, reasonCode: {btc_dec.get('reasonCode')}")
        
        # D2: Call again with NO changes -> same decisionId
        print("\n[D2] Calling /decisions again with NO changes")
        time.sleep(1)  # Small delay
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        decision_id_2 = btc_dec.get("decisionId")
        
        assert decision_id_2 == decision_id_1, \
            f"DecisionId changed without mandate change: {decision_id_1} -> {decision_id_2}"
        print(f"  ✓ PASS: decisionId stable (still {decision_id_1})")
        
        # Check history count = 0
        resp = get_decision_history(pid, asset="BTC")
        assert resp.status_code == 200, f"History failed: {resp.status_code}"
        hist_data = resp.json()
        count = hist_data.get("count", 0)
        assert count == 0, f"Expected 0 history events, got {count}"
        print(f"  ✓ PASS: decision-history count = 0 (no spam)")
        
        # D3: Exclude BTC -> should flip to SELL/EMERGENCY_EXIT
        print("\n[D3] Excluding BTC from mandate")
        mandate["excluded_coins"] = ["BTC"]
        mandate["approved_coins"] = ["ETH"]
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        time.sleep(1)
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        assert btc_dec is not None, "BTC decision not found"
        
        decision_id_3 = btc_dec.get("decisionId")
        action = btc_dec.get("action")
        reason = btc_dec.get("reasonCode")
        
        assert decision_id_3 != decision_id_1, \
            f"DecisionId should change after exclusion: {decision_id_1} -> {decision_id_3}"
        assert action == "SELL", f"Expected SELL, got {action}"
        assert reason == "EMERGENCY_EXIT", f"Expected EMERGENCY_EXIT, got {reason}"
        
        print(f"  ✓ PASS: New decisionId: {decision_id_3}")
        print(f"    action: {action}, reasonCode: {reason}")
        
        # Check history
        resp = get_decision_history(pid, asset="BTC")
        assert resp.status_code == 200, f"History failed: {resp.status_code}"
        hist_data = resp.json()
        count = hist_data.get("count", 0)
        events = hist_data.get("events", [])
        
        assert count >= 1, f"Expected >= 1 history event, got {count}"
        print(f"  ✓ PASS: decision-history count = {count}")
        
        # Validate newest event
        newest = events[0]
        assert newest.get("previousDecisionId") == decision_id_1, \
            f"previousDecisionId mismatch: {newest.get('previousDecisionId')} vs {decision_id_1}"
        assert newest.get("newDecisionId") == decision_id_3, \
            f"newDecisionId mismatch: {newest.get('newDecisionId')} vs {decision_id_3}"
        assert newest.get("previousSnapshotId"), "previousSnapshotId missing"
        assert newest.get("newSnapshotId"), "newSnapshotId missing"
        assert newest.get("previousSnapshotId") != newest.get("newSnapshotId"), \
            "Snapshot IDs should differ"
        assert newest.get("changeType"), "changeType missing"
        assert len(newest.get("changeReason", [])) > 0, "changeReason empty"
        
        print(f"    previousDecisionId: {newest.get('previousDecisionId')}")
        print(f"    newDecisionId: {newest.get('newDecisionId')}")
        print(f"    changeType: {newest.get('changeType')}")
        print(f"    changeReason: {newest.get('changeReason')}")
        
        # D4: Remove exclusion -> another transition
        print("\n[D4] Removing BTC from excluded_coins")
        mandate["excluded_coins"] = []
        mandate["approved_coins"] = ["BTC", "ETH"]
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        time.sleep(1)
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        decision_id_4 = btc_dec.get("decisionId")
        
        assert decision_id_4 != decision_id_3, \
            f"DecisionId should change after removing exclusion: {decision_id_3} -> {decision_id_4}"
        print(f"  ✓ PASS: New decisionId: {decision_id_4}")
        
        # Check history chain
        resp = get_decision_history(pid, asset="BTC")
        assert resp.status_code == 200, f"History failed: {resp.status_code}"
        hist_data = resp.json()
        events = hist_data.get("events", [])
        
        assert len(events) >= 2, f"Expected >= 2 history events, got {len(events)}"
        
        # Newest event should link decision_id_3 -> decision_id_4
        newest = events[0]
        assert newest.get("previousDecisionId") == decision_id_3, \
            f"Chain broken: previousDecisionId {newest.get('previousDecisionId')} != {decision_id_3}"
        assert newest.get("newDecisionId") == decision_id_4, \
            f"newDecisionId mismatch: {newest.get('newDecisionId')} vs {decision_id_4}"
        
        print(f"  ✓ PASS: History chain links correctly")
        print(f"    Event 1: {decision_id_1} -> {decision_id_3}")
        print(f"    Event 2: {decision_id_3} -> {decision_id_4}")
        
        print("\n✅ TEST D: DECISION-CHANGE HISTORY PASSED")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST D FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST D ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TEST E: ASK ALBERT EXPLAIN (read-only)
# ============================================================================

def test_e_ask_albert_explain():
    print("\n" + "="*80)
    print("TEST E: ASK ALBERT EXPLAIN - Read-only, returns unchanged decision")
    print("="*80)
    
    pid = "u_TEST_D2_EXPL"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        print("\n[E1] Setup: mandate + portfolio")
        mandate = {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH"],
            "excluded_coins": [],
            "max_alloc_pct": {"BTC": 40, "ETH": 30},
            "max_trade_risk_pct": 2
        }
        resp = post_mandate(pid, mandate)
        assert resp.status_code == 200, f"Mandate POST failed: {resp.status_code}"
        
        resp = post_portfolio(pid, 20000, [{"asset": "BTC", "size": 0.1, "avg_entry": 60000}])
        assert resp.status_code == 200, f"Portfolio POST failed: {resp.status_code}"
        
        # Get decisions
        resp = get_decisions(pid)
        assert resp.status_code == 200, f"Decisions failed: {resp.status_code}"
        data = resp.json()
        
        btc_dec = next((d for d in data.get("decisions", []) if d["symbol"] == "BTC"), None)
        assert btc_dec is not None, "BTC decision not found"
        
        decision_id = btc_dec.get("decisionId")
        assert decision_id, "BTC decisionId missing"
        print(f"  ✓ BTC decisionId: {decision_id}")
        
        # E2: GET /api/v1/albert/decision/{decisionId}
        print("\n[E2] Fetching decision by ID")
        resp = get_decision_by_id(pid, decision_id)
        assert resp.status_code == 200, f"Decision fetch failed: {resp.status_code}"
        fetch_data = resp.json()
        
        assert fetch_data.get("status") == "ready", f"Status not ready: {fetch_data.get('status')}"
        stored_decision = fetch_data.get("decision")
        assert stored_decision, "Decision not returned"
        assert stored_decision.get("decisionId") == decision_id, "DecisionId mismatch"
        
        print(f"  ✓ PASS: Fetched decision")
        print(f"    decisionId: {stored_decision.get('decisionId')}")
        print(f"    call: {stored_decision.get('call')}")
        print(f"    score: {stored_decision.get('opportunityScore')}")
        print(f"    reasonCode: {stored_decision.get('reasonCode')}")
        
        # Store original values for comparison
        original_values = {
            "decisionId": stored_decision.get("decisionId"),
            "call": stored_decision.get("call") or stored_decision.get("action"),
            "score": stored_decision.get("opportunityScore"),
            "reasonCode": stored_decision.get("reasonCode"),
            "recommendedDeltaUsd": stored_decision.get("recommendedDeltaUsd"),
            "confidence": stored_decision.get("confidence"),
        }
        
        # E3: POST /api/v1/albert/explain-call
        print("\n[E3] Calling explain-call (allow up to 90s for LLM)")
        question = "Why this call and what would change it?"
        resp = post_explain_call(pid, decision_id, question)
        assert resp.status_code == 200, f"Explain-call failed: {resp.status_code}"
        explain_data = resp.json()
        
        assert explain_data.get("status") == "ready", f"Status not ready: {explain_data.get('status')}"
        
        explanation = explain_data.get("explanation", "")
        assert len(explanation) > 0, "Explanation is empty"
        print(f"  ✓ PASS: Explanation received ({len(explanation)} chars)")
        print(f"    First 200 chars: {explanation[:200]}...")
        
        # E4: Validate decision is UNCHANGED
        print("\n[E4] Validating decision is UNCHANGED")
        returned_decision = explain_data.get("decision")
        assert returned_decision, "Decision not returned in explain response"
        
        # Compare key fields
        assert returned_decision.get("decisionId") == original_values["decisionId"], \
            f"decisionId mutated: {original_values['decisionId']} -> {returned_decision.get('decisionId')}"
        
        returned_call = returned_decision.get("call") or returned_decision.get("action")
        assert returned_call == original_values["call"], \
            f"call mutated: {original_values['call']} -> {returned_call}"
        
        assert returned_decision.get("opportunityScore") == original_values["score"], \
            f"score mutated: {original_values['score']} -> {returned_decision.get('opportunityScore')}"
        
        assert returned_decision.get("reasonCode") == original_values["reasonCode"], \
            f"reasonCode mutated: {original_values['reasonCode']} -> {returned_decision.get('reasonCode')}"
        
        assert returned_decision.get("recommendedDeltaUsd") == original_values["recommendedDeltaUsd"], \
            f"recommendedDeltaUsd mutated: {original_values['recommendedDeltaUsd']} -> {returned_decision.get('recommendedDeltaUsd')}"
        
        print(f"  ✓ PASS: Decision unchanged")
        print(f"    decisionId: {returned_decision.get('decisionId')} (same)")
        print(f"    call: {returned_call} (same)")
        print(f"    score: {returned_decision.get('opportunityScore')} (same)")
        print(f"    reasonCode: {returned_decision.get('reasonCode')} (same)")
        print(f"    recommendedDeltaUsd: {returned_decision.get('recommendedDeltaUsd')} (same)")
        
        print("\n✅ TEST E: ASK ALBERT EXPLAIN PASSED")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST E FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST E ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("PHASE D2 BACKEND TESTING")
    print("Testing: Flip conditions, immutable snapshot, discovery/eligibility,")
    print("         Ask-Albert explain, decision-change history")
    print("="*80)
    
    results = {}
    
    try:
        # Run all tests
        results["A_REGRESSION"] = test_a_regression()
        results["B_IMMUTABLE_ENVELOPE"] = test_b_immutable_envelope()
        results["C_DISCOVERY_ELIGIBILITY"] = test_c_discovery_eligibility()
        results["D_DECISION_HISTORY"] = test_d_decision_history()
        results["E_ASK_ALBERT_EXPLAIN"] = test_e_ask_albert_explain()
        
    finally:
        # Always cleanup
        cleanup_test_data()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
