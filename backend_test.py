"""
Backend testing for Discovery Watchlist and Recovery Timeline features.
Tests via external API base URL.
"""
import requests
import time
import uuid
from typing import Dict, Any

BASE_URL = "https://quant-features.preview.emergentagent.com/api"
SEEDED_PID = "u_7693422a-e2c0-4242-8211-e6f1d0eaa320"

# Track test PIDs for cleanup
test_pids = []

def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test results."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  {details}")

def create_test_pid(prefix: str) -> str:
    """Create a unique test PID."""
    pid = f"u_{prefix}_{uuid.uuid4().hex[:8]}"
    test_pids.append(pid)
    return pid

def cleanup_test_data():
    """Clean up all test data from MongoDB."""
    print("\n" + "="*80)
    print("CLEANUP: Removing test data...")
    print("="*80)
    
    # Import MongoDB collections
    import sys
    sys.path.insert(0, '/app/backend')
    from config import (
        mandate_col, portfolio_col, portfolio_risk_col, 
        discovery_watchlist_col
    )
    
    deleted_counts = {}
    for pid in test_pids:
        deleted_counts[pid] = {
            'mandates': mandate_col.delete_many({'pid': pid}).deleted_count,
            'portfolios': portfolio_col.delete_many({'pid': pid}).deleted_count,
            'portfolio_risk': portfolio_risk_col.delete_many({'_id': pid}).deleted_count,
            'watchlist': discovery_watchlist_col.delete_many({'pid': pid}).deleted_count,
        }
    
    total_deleted = sum(sum(counts.values()) for counts in deleted_counts.values())
    print(f"✅ Deleted {total_deleted} documents across {len(test_pids)} test PIDs")
    for pid, counts in deleted_counts.items():
        print(f"  {pid}: {counts}")

# ============================================================================
# FEATURE 1: DISCOVERY WATCHLIST TESTS
# ============================================================================

def test_watchlist_idempotent_pin():
    """
    Test 1: IDEMPOTENT PIN
    For a FRESH test pid, create mandate approving only BTC & ETH.
    Pin BTC and XRP. Verify 2 symbols. Pin XRP again -> still 2 symbols (no duplicate).
    """
    print("\n" + "="*80)
    print("FEATURE 1 - TEST 1: IDEMPOTENT PIN")
    print("="*80)
    
    pid = create_test_pid("WL_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # Create mandate approving only BTC & ETH
        mandate_data = {
            'pid': pid,
            'risk_tolerance': 'moderate',
            'reserve_pct': 25,
            'approved_coins': ['BTC', 'ETH'],
            'excluded_coins': [],
            'max_drawdown_pct': 20
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/mandate", json=mandate_data, timeout=30)
        assert resp.status_code == 200, f"Mandate creation failed: {resp.status_code}"
        log_test("1.1 - Create mandate", True, f"Approved coins: BTC, ETH")
        
        # Pin BTC
        resp = requests.post(f"{BASE_URL}/v1/albert/watchlist", 
                           json={'pid': pid, 'symbol': 'BTC'}, timeout=30)
        assert resp.status_code == 200, f"Pin BTC failed: {resp.status_code}"
        data = resp.json()
        assert data.get('status') == 'ready', "Status not ready"
        assert data.get('pinned') == True, "Pinned not True"
        assert 'BTC' in data.get('symbols', []), "BTC not in symbols"
        log_test("1.2 - Pin BTC", True, f"Symbols: {data.get('symbols')}")
        
        # Pin XRP (not in approved list)
        resp = requests.post(f"{BASE_URL}/v1/albert/watchlist", 
                           json={'pid': pid, 'symbol': 'XRP'}, timeout=30)
        assert resp.status_code == 200, f"Pin XRP failed: {resp.status_code}"
        data = resp.json()
        symbols = data.get('symbols', [])
        assert len(symbols) == 2, f"Expected 2 symbols, got {len(symbols)}"
        assert 'BTC' in symbols and 'XRP' in symbols, "BTC or XRP missing"
        log_test("1.3 - Pin XRP", True, f"Symbols: {symbols} (2 entries)")
        
        # Pin XRP AGAIN (idempotency test)
        resp = requests.post(f"{BASE_URL}/v1/albert/watchlist", 
                           json={'pid': pid, 'symbol': 'XRP'}, timeout=30)
        assert resp.status_code == 200, f"Pin XRP again failed: {resp.status_code}"
        data = resp.json()
        symbols = data.get('symbols', [])
        assert len(symbols) == 2, f"Expected 2 symbols (no duplicate), got {len(symbols)}"
        assert symbols.count('XRP') == 1, "XRP duplicated!"
        log_test("1.4 - Pin XRP AGAIN (idempotency)", True, 
                f"Symbols: {symbols} (still 2, no duplicate)")
        
        return True
        
    except AssertionError as e:
        log_test("Test 1 - IDEMPOTENT PIN", False, str(e))
        return False
    except Exception as e:
        log_test("Test 1 - IDEMPOTENT PIN", False, f"Exception: {e}")
        return False

def test_watchlist_pin_not_buy():
    """
    Test 2: CRITICAL INVARIANT (pin != buy)
    GET watchlist for the pid from test 1. Find XRP asset.
    It MUST have eligible=false and albertCall='WAIT' (NEVER 'BUY').
    Verify NO watchlist asset with eligible=false has albertCall='BUY'.
    """
    print("\n" + "="*80)
    print("FEATURE 1 - TEST 2: CRITICAL INVARIANT (pin != buy)")
    print("="*80)
    
    # Use the same PID from test 1
    pid = test_pids[-1] if test_pids else create_test_pid("WL_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # First, ensure discovery cache is warm
        print("Warming discovery cache...")
        resp = requests.get(f"{BASE_URL}/v1/albert/discovery", 
                          params={'pid': pid}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status')
            print(f"Discovery status: {status}")
            
            # Poll if building
            if status == 'building':
                print("Discovery building, polling...")
                for i in range(9):  # Poll up to 90s
                    time.sleep(10)
                    resp = requests.get(f"{BASE_URL}/v1/albert/discovery", 
                                      params={'pid': pid}, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('status') == 'ready':
                            print("Discovery ready!")
                            break
        
        # GET watchlist
        resp = requests.get(f"{BASE_URL}/v1/albert/watchlist", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"GET watchlist failed: {resp.status_code}"
        data = resp.json()
        assert data.get('status') == 'ready', "Status not ready"
        
        assets = data.get('assets', [])
        symbols = data.get('symbols', [])
        print(f"Watchlist symbols: {symbols}")
        print(f"Assets count: {len(assets)}")
        
        # Find XRP
        xrp_asset = None
        for asset in assets:
            if asset.get('symbol') == 'XRP':
                xrp_asset = asset
                break
        
        assert xrp_asset is not None, "XRP not found in watchlist assets"
        
        # CRITICAL CHECK: XRP must be eligible=false, albertCall='WAIT'
        eligible = xrp_asset.get('eligible')
        albert_call = xrp_asset.get('albertCall')
        ineligibility_reason = xrp_asset.get('ineligibilityReason')
        
        print(f"XRP: eligible={eligible}, albertCall={albert_call}, reason={ineligibility_reason}")
        
        assert eligible == False, f"XRP should be ineligible, got eligible={eligible}"
        assert albert_call == 'WAIT', f"XRP albertCall should be WAIT, got {albert_call}"
        assert ineligibility_reason == 'NOT_IN_APPROVED_UNIVERSE', \
            f"Expected NOT_IN_APPROVED_UNIVERSE, got {ineligibility_reason}"
        
        log_test("2.1 - XRP ineligible with WAIT call", True, 
                f"eligible=False, albertCall=WAIT, reason={ineligibility_reason}")
        
        # Check BTC (should be eligible)
        btc_asset = None
        for asset in assets:
            if asset.get('symbol') == 'BTC':
                btc_asset = asset
                break
        
        if btc_asset:
            btc_eligible = btc_asset.get('eligible')
            btc_call = btc_asset.get('albertCall')
            print(f"BTC: eligible={btc_eligible}, albertCall={btc_call}")
            log_test("2.2 - BTC eligible status", True, 
                    f"eligible={btc_eligible}, albertCall={btc_call}")
        
        # CRITICAL: Verify NO ineligible asset has albertCall='BUY'
        ineligible_buys = [a for a in assets 
                          if a.get('eligible') == False and a.get('albertCall') == 'BUY']
        
        assert len(ineligible_buys) == 0, \
            f"Found {len(ineligible_buys)} ineligible assets with BUY call: {ineligible_buys}"
        
        log_test("2.3 - NO ineligible asset has BUY call", True, 
                "Invariant preserved: pin != permission to buy")
        
        return True
        
    except AssertionError as e:
        log_test("Test 2 - CRITICAL INVARIANT", False, str(e))
        return False
    except Exception as e:
        log_test("Test 2 - CRITICAL INVARIANT", False, f"Exception: {e}")
        return False

def test_watchlist_delete():
    """
    Test 3: DELETE
    DELETE XRP from watchlist. Verify symbols no longer contains XRP (1 symbol left, BTC).
    """
    print("\n" + "="*80)
    print("FEATURE 1 - TEST 3: DELETE")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else create_test_pid("WL_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # DELETE XRP
        resp = requests.delete(f"{BASE_URL}/v1/albert/watchlist/XRP", 
                             params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"DELETE XRP failed: {resp.status_code}"
        data = resp.json()
        assert data.get('status') == 'ready', "Status not ready"
        assert data.get('pinned') == False, "Pinned should be False after delete"
        
        symbols = data.get('symbols', [])
        assert 'XRP' not in symbols, "XRP still in symbols after delete"
        assert len(symbols) == 1, f"Expected 1 symbol, got {len(symbols)}"
        assert 'BTC' in symbols, "BTC should remain"
        
        log_test("3.1 - DELETE XRP", True, 
                f"Symbols after delete: {symbols} (XRP removed, BTC remains)")
        
        return True
        
    except AssertionError as e:
        log_test("Test 3 - DELETE", False, str(e))
        return False
    except Exception as e:
        log_test("Test 3 - DELETE", False, f"Exception: {e}")
        return False

def test_watchlist_errors():
    """
    Test 4: ERRORS
    POST watchlist with missing symbol (or missing pid) -> response has 'error' field.
    GET watchlist with no pid -> 'error' field.
    """
    print("\n" + "="*80)
    print("FEATURE 1 - TEST 4: ERRORS")
    print("="*80)
    
    try:
        # POST with missing symbol
        resp = requests.post(f"{BASE_URL}/v1/albert/watchlist", 
                           json={'pid': 'test_pid'}, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert 'error' in data, "Expected 'error' field for missing symbol"
        log_test("4.1 - POST with missing symbol", True, f"Error: {data.get('error')}")
        
        # POST with missing pid
        resp = requests.post(f"{BASE_URL}/v1/albert/watchlist", 
                           json={'symbol': 'BTC'}, timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert 'error' in data, "Expected 'error' field for missing pid"
        log_test("4.2 - POST with missing pid", True, f"Error: {data.get('error')}")
        
        # GET with no pid
        resp = requests.get(f"{BASE_URL}/v1/albert/watchlist", timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert 'error' in data, "Expected 'error' field for missing pid"
        log_test("4.3 - GET with no pid", True, f"Error: {data.get('error')}")
        
        return True
        
    except AssertionError as e:
        log_test("Test 4 - ERRORS", False, str(e))
        return False
    except Exception as e:
        log_test("Test 4 - ERRORS", False, f"Exception: {e}")
        return False

def test_watchlist_regression():
    """
    Test 5: REGRESSION
    GET /api/v1/albert/discovery still returns HTTP 200 with status 'ready' or 'building'
    and is unaffected by watchlist operations.
    """
    print("\n" + "="*80)
    print("FEATURE 1 - TEST 5: REGRESSION")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else SEEDED_PID
    print(f"Test PID: {pid}")
    
    try:
        resp = requests.get(f"{BASE_URL}/v1/albert/discovery", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Discovery endpoint failed: {resp.status_code}"
        data = resp.json()
        status = data.get('status')
        assert status in ['ready', 'building'], f"Unexpected status: {status}"
        
        log_test("5.1 - Discovery endpoint regression", True, 
                f"Status: {status}, unaffected by watchlist ops")
        
        return True
        
    except AssertionError as e:
        log_test("Test 5 - REGRESSION", False, str(e))
        return False
    except Exception as e:
        log_test("Test 5 - REGRESSION", False, f"Exception: {e}")
        return False

# ============================================================================
# FEATURE 2: RECOVERY TIMELINE TESTS
# ============================================================================

def test_recovery_timeline_seed_hwm():
    """
    Test 1: SEED HWM
    POST portfolio to set high value (usdc=100000, no positions).
    GET portfolio-risk -> highWaterMarkUsd ~100000, protectionMode=false, 
    recoveryTimeline=[] (empty).
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 1: SEED HWM")
    print("="*80)
    
    pid = create_test_pid("RT_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # Create mandate with max_drawdown_pct=20
        mandate_data = {
            'pid': pid,
            'risk_tolerance': 'moderate',
            'reserve_pct': 0,  # Keep math simple
            'approved_coins': ['BTC', 'ETH'],
            'excluded_coins': [],
            'max_drawdown_pct': 20
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/mandate", json=mandate_data, timeout=30)
        assert resp.status_code == 200, f"Mandate creation failed: {resp.status_code}"
        log_test("1.1 - Create mandate", True, "max_drawdown_pct=20, reserve_pct=0")
        
        # Set high portfolio value
        portfolio_data = {
            'pid': pid,
            'usdc': 100000,
            'positions': []
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_data, timeout=30)
        assert resp.status_code == 200, f"Portfolio creation failed: {resp.status_code}"
        log_test("1.2 - Set portfolio", True, "usdc=100000, no positions")
        
        # GET portfolio-risk
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        hwm = pr.get('highWaterMarkUsd')
        protection_mode = pr.get('protectionMode')
        recovery_timeline = pr.get('recoveryTimeline', [])
        
        print(f"HWM: {hwm}, protectionMode: {protection_mode}, timeline length: {len(recovery_timeline)}")
        
        assert hwm is not None and abs(hwm - 100000) < 100, \
            f"Expected HWM ~100000, got {hwm}"
        assert protection_mode == False, f"Expected protectionMode=False, got {protection_mode}"
        assert len(recovery_timeline) == 0, \
            f"Expected empty timeline, got {len(recovery_timeline)} entries"
        
        log_test("1.3 - Initial state", True, 
                f"HWM={hwm}, protectionMode=False, recoveryTimeline=[] (empty)")
        
        return True
        
    except AssertionError as e:
        log_test("Test 1 - SEED HWM", False, str(e))
        return False
    except Exception as e:
        log_test("Test 1 - SEED HWM", False, f"Exception: {e}")
        return False

def test_recovery_timeline_breach():
    """
    Test 2: BREACH
    POST portfolio to drop value >= 20% below HWM (usdc=75000 => 25% drawdown).
    GET portfolio-risk -> protectionMode=true, breached=true, drawdownPct ~25.
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 2: BREACH")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else create_test_pid("RT_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # Drop portfolio value to 75000 (25% drawdown from 100000)
        portfolio_data = {
            'pid': pid,
            'usdc': 75000,
            'positions': []
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_data, timeout=30)
        assert resp.status_code == 200, f"Portfolio update failed: {resp.status_code}"
        log_test("2.1 - Drop portfolio value", True, "usdc=75000 (25% drawdown)")
        
        # GET portfolio-risk
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        protection_mode = pr.get('protectionMode')
        breached = pr.get('breached')
        drawdown_pct = pr.get('drawdownPct')
        
        print(f"protectionMode: {protection_mode}, breached: {breached}, drawdownPct: {drawdown_pct}")
        
        assert protection_mode == True, f"Expected protectionMode=True, got {protection_mode}"
        assert breached == True, f"Expected breached=True, got {breached}"
        assert drawdown_pct is not None and drawdown_pct >= 20, \
            f"Expected drawdownPct >= 20, got {drawdown_pct}"
        
        log_test("2.2 - Breach detected", True, 
                f"protectionMode=True, breached=True, drawdownPct={drawdown_pct}")
        
        return True
        
    except AssertionError as e:
        log_test("Test 2 - BREACH", False, str(e))
        return False
    except Exception as e:
        log_test("Test 2 - BREACH", False, f"Exception: {e}")
        return False

def test_recovery_timeline_recover():
    """
    Test 3: RECOVER
    POST portfolio to raise value so drawdown <= 16% (recovery threshold).
    (usdc=85000 => 15% drawdown, still below 100000 HWM).
    GET portfolio-risk -> protectionMode=false AND recoveryTimeline has EXACTLY 1 episode
    whose breachDrawdownPct >= 20 and liftedDrawdownPct <= 16.
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 3: RECOVER")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else create_test_pid("RT_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # Raise portfolio value to 85000 (15% drawdown, below recovery threshold of 16%)
        portfolio_data = {
            'pid': pid,
            'usdc': 85000,
            'positions': []
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_data, timeout=30)
        assert resp.status_code == 200, f"Portfolio update failed: {resp.status_code}"
        log_test("3.1 - Raise portfolio value", True, "usdc=85000 (15% drawdown)")
        
        # GET portfolio-risk
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        protection_mode = pr.get('protectionMode')
        recovery_timeline = pr.get('recoveryTimeline', [])
        
        print(f"protectionMode: {protection_mode}, timeline length: {len(recovery_timeline)}")
        
        assert protection_mode == False, \
            f"Expected protectionMode=False after recovery, got {protection_mode}"
        assert len(recovery_timeline) == 1, \
            f"Expected exactly 1 episode in timeline, got {len(recovery_timeline)}"
        
        # Validate the episode
        episode = recovery_timeline[0]
        breach_dd = episode.get('breachDrawdownPct')
        lifted_dd = episode.get('liftedDrawdownPct')
        activated_at = episode.get('activatedAt')
        lifted_at = episode.get('liftedAt')
        
        print(f"Episode: breachDrawdownPct={breach_dd}, liftedDrawdownPct={lifted_dd}")
        print(f"  activatedAt={activated_at}, liftedAt={lifted_at}")
        
        assert breach_dd is not None and breach_dd >= 20, \
            f"Expected breachDrawdownPct >= 20, got {breach_dd}"
        assert lifted_dd is not None and lifted_dd <= 16, \
            f"Expected liftedDrawdownPct <= 16, got {lifted_dd}"
        assert activated_at is not None, "activatedAt missing"
        assert lifted_at is not None, "liftedAt missing"
        
        log_test("3.2 - Recovery captured", True, 
                f"protectionMode=False, 1 episode: breach={breach_dd}%, lifted={lifted_dd}%")
        
        return True
        
    except AssertionError as e:
        log_test("Test 3 - RECOVER", False, str(e))
        return False
    except Exception as e:
        log_test("Test 3 - RECOVER", False, f"Exception: {e}")
        return False

def test_recovery_timeline_second_cycle():
    """
    Test 4: SECOND CYCLE
    Breach again (usdc=75000) then recover again (usdc=85000).
    GET portfolio-risk after each.
    recoveryTimeline length should become 2, ordered most-recent-first 
    (newest lifted episode is index 0).
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 4: SECOND CYCLE")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else create_test_pid("RT_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # Breach again
        portfolio_data = {
            'pid': pid,
            'usdc': 75000,
            'positions': []
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_data, timeout=30)
        assert resp.status_code == 200, f"Portfolio update failed: {resp.status_code}"
        
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        protection_mode = pr.get('protectionMode')
        assert protection_mode == True, f"Expected protectionMode=True after 2nd breach"
        log_test("4.1 - Second breach", True, "protectionMode=True")
        
        # Recover again
        portfolio_data = {
            'pid': pid,
            'usdc': 85000,
            'positions': []
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_data, timeout=30)
        assert resp.status_code == 200, f"Portfolio update failed: {resp.status_code}"
        
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        protection_mode = pr.get('protectionMode')
        recovery_timeline = pr.get('recoveryTimeline', [])
        
        print(f"protectionMode: {protection_mode}, timeline length: {len(recovery_timeline)}")
        
        assert protection_mode == False, \
            f"Expected protectionMode=False after 2nd recovery, got {protection_mode}"
        assert len(recovery_timeline) == 2, \
            f"Expected 2 episodes in timeline, got {len(recovery_timeline)}"
        
        # Verify most-recent-first ordering
        # The newest episode should be at index 0
        first_episode = recovery_timeline[0]
        second_episode = recovery_timeline[1]
        
        first_lifted = first_episode.get('liftedAt')
        second_lifted = second_episode.get('liftedAt')
        
        print(f"Episode 0 (newest): liftedAt={first_lifted}")
        print(f"Episode 1 (older): liftedAt={second_lifted}")
        
        # The first episode should have a later timestamp than the second
        assert first_lifted > second_lifted, \
            f"Timeline not ordered most-recent-first: {first_lifted} vs {second_lifted}"
        
        log_test("4.2 - Second recovery captured", True, 
                f"2 episodes, most-recent-first ordering verified")
        
        return True
        
    except AssertionError as e:
        log_test("Test 4 - SECOND CYCLE", False, str(e))
        return False
    except Exception as e:
        log_test("Test 4 - SECOND CYCLE", False, f"Exception: {e}")
        return False

def test_recovery_timeline_persistence():
    """
    Test 5: PERSISTENCE
    Call GET portfolio-risk once more without changing the portfolio.
    recoveryTimeline still returns the 2 episodes (persisted, not recomputed/lost).
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 5: PERSISTENCE")
    print("="*80)
    
    pid = test_pids[-1] if test_pids else create_test_pid("RT_TEST")
    print(f"Test PID: {pid}")
    
    try:
        # GET portfolio-risk without changing portfolio
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-risk", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Portfolio-risk failed: {resp.status_code}"
        data = resp.json()
        pr = data.get('portfolioRisk', {})
        
        recovery_timeline = pr.get('recoveryTimeline', [])
        
        print(f"Timeline length: {len(recovery_timeline)}")
        
        assert len(recovery_timeline) == 2, \
            f"Expected 2 persisted episodes, got {len(recovery_timeline)}"
        
        # Verify both episodes still have all required fields
        for i, episode in enumerate(recovery_timeline):
            required_fields = ['highWaterMarkUsd', 'breachValueUsd', 'breachDrawdownPct',
                             'activatedAt', 'liftedAt', 'liftedDrawdownPct']
            for field in required_fields:
                assert field in episode, f"Episode {i} missing field: {field}"
        
        log_test("5.1 - Timeline persistence", True, 
                "2 episodes persisted across calls (not recomputed/lost)")
        
        return True
        
    except AssertionError as e:
        log_test("Test 5 - PERSISTENCE", False, str(e))
        return False
    except Exception as e:
        log_test("Test 5 - PERSISTENCE", False, f"Exception: {e}")
        return False

def test_recovery_timeline_regression():
    """
    Test 6: REGRESSION
    GET /api/v1/albert/decisions and GET /api/v1/albert/discovery still return HTTP 200.
    """
    print("\n" + "="*80)
    print("FEATURE 2 - TEST 6: REGRESSION")
    print("="*80)
    
    pid = SEEDED_PID
    print(f"Test PID: {pid}")
    
    try:
        # Test decisions endpoint
        resp = requests.get(f"{BASE_URL}/v1/albert/decisions", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Decisions endpoint failed: {resp.status_code}"
        log_test("6.1 - Decisions endpoint regression", True, "HTTP 200")
        
        # Test discovery endpoint
        resp = requests.get(f"{BASE_URL}/v1/albert/discovery", 
                          params={'pid': pid}, timeout=30)
        assert resp.status_code == 200, f"Discovery endpoint failed: {resp.status_code}"
        log_test("6.2 - Discovery endpoint regression", True, "HTTP 200")
        
        return True
        
    except AssertionError as e:
        log_test("Test 6 - REGRESSION", False, str(e))
        return False
    except Exception as e:
        log_test("Test 6 - REGRESSION", False, f"Exception: {e}")
        return False

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    print("\n" + "="*80)
    print("BACKEND TESTING: Discovery Watchlist + Recovery Timeline")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Seeded PID: {SEEDED_PID}")
    
    results = {}
    
    # FEATURE 1: DISCOVERY WATCHLIST
    print("\n" + "="*80)
    print("FEATURE 1: DISCOVERY WATCHLIST")
    print("="*80)
    
    results['F1-T1-Idempotent-Pin'] = test_watchlist_idempotent_pin()
    results['F1-T2-Pin-Not-Buy'] = test_watchlist_pin_not_buy()
    results['F1-T3-Delete'] = test_watchlist_delete()
    results['F1-T4-Errors'] = test_watchlist_errors()
    results['F1-T5-Regression'] = test_watchlist_regression()
    
    # FEATURE 2: RECOVERY TIMELINE
    print("\n" + "="*80)
    print("FEATURE 2: RECOVERY TIMELINE")
    print("="*80)
    
    results['F2-T1-Seed-HWM'] = test_recovery_timeline_seed_hwm()
    results['F2-T2-Breach'] = test_recovery_timeline_breach()
    results['F2-T3-Recover'] = test_recovery_timeline_recover()
    results['F2-T4-Second-Cycle'] = test_recovery_timeline_second_cycle()
    results['F2-T5-Persistence'] = test_recovery_timeline_persistence()
    results['F2-T6-Regression'] = test_recovery_timeline_regression()
    
    # Cleanup
    cleanup_test_data()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("\nDetailed Results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
