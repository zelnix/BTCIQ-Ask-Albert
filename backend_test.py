"""
Phase E Backend Testing — Paper Order Manager (Execution Safety Layer)
Tests all scenarios from the review request using external /api base URL.
"""
import requests
import time
import json
from pymongo import MongoClient

# Configuration
BASE_URL = "https://quant-features.preview.emergentagent.com/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "btciq"

# Test PIDs (FRESH for each test)
TEST_PIDS = []

# MongoDB collections to clean up
COLLECTIONS_TO_CLEAN = [
    'user_mandates',
    'user_portfolios',
    'albert_decision_current',
    'albert_decision_snapshots',
    'albert_decision_history',
    'albert_order_intents',
    'albert_paper_ledger',
    'albert_order_audit',
    'albert_paper_portfolio'
]

def log(msg):
    print(f"[TEST] {msg}")

def setup_mandate_and_portfolio(pid, usdc=50000):
    """Setup mandate and portfolio for a test PID"""
    log(f"Setting up mandate and portfolio for {pid}")
    
    # Create mandate
    mandate_payload = {
        "pid": pid,
        "mandate": {
            "risk_tolerance": "moderate",
            "reserve_pct": 25,
            "approved_coins": ["BTC", "ETH", "SOL"],
            "max_alloc_pct": {
                "BTC": 40,
                "ETH": 30,
                "SOL": 20
            },
            "max_trade_risk_pct": 2
        }
    }
    resp = requests.post(f"{BASE_URL}/v1/albert/mandate", json=mandate_payload, timeout=30)
    if resp.status_code != 200:
        log(f"ERROR: Failed to create mandate: {resp.status_code} {resp.text}")
        return False
    log(f"✓ Mandate created")
    
    # Create portfolio
    portfolio_payload = {
        "pid": pid,
        "usdc": usdc,
        "positions": []
    }
    resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_payload, timeout=30)
    if resp.status_code != 200:
        log(f"ERROR: Failed to create portfolio: {resp.status_code} {resp.text}")
        return False
    log(f"✓ Portfolio created with USDC={usdc}")
    
    return True

def get_buy_symbol(pid):
    """Get a symbol with BUY action from decisions"""
    log(f"Getting BUY symbol for {pid}")
    resp = requests.get(f"{BASE_URL}/v1/albert/decisions", params={"pid": pid}, timeout=60)
    if resp.status_code != 200:
        log(f"ERROR: Failed to get decisions: {resp.status_code}")
        return None
    
    data = resp.json()
    decisions = data.get('decisions', [])
    for d in decisions:
        if d.get('action') == 'BUY':
            sym = d.get('symbol')
            log(f"✓ Found BUY symbol: {sym}")
            return sym
    
    log("WARNING: No BUY symbol found")
    return None

def cleanup_test_data():
    """Clean up all test data from MongoDB"""
    log("Cleaning up test data from MongoDB...")
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        
        total_deleted = 0
        for coll_name in COLLECTIONS_TO_CLEAN:
            coll = db[coll_name]
            # Delete by pid for most collections
            if coll_name == 'albert_paper_portfolio':
                # paper_portfolio uses _id == pid
                result = coll.delete_many({'_id': {'$in': TEST_PIDS}})
            else:
                result = coll.delete_many({'pid': {'$in': TEST_PIDS}})
            if result.deleted_count > 0:
                log(f"  Deleted {result.deleted_count} docs from {coll_name}")
                total_deleted += result.deleted_count
        
        log(f"✓ Cleanup complete: {total_deleted} total documents deleted")
        client.close()
        return True
    except Exception as e:
        log(f"ERROR during cleanup: {e}")
        return False

def test_a_happy_full_fill():
    """TEST A: HAPPY FULL FILL - create->confirm->execute a BUY reaches FILLED"""
    log("\n" + "="*80)
    log("TEST A: HAPPY FULL FILL")
    log("="*80)
    
    pid = "u_TEST_E_A"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST A FAILED: Setup failed")
            return False
        
        # Get a BUY symbol
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST A FAILED: No BUY symbol available")
            return False
        
        # 1. Create intent
        log(f"\n1. Creating order intent for {sym}...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k1"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Create failed: {resp.status_code} {resp.text}")
            return False
        
        data = resp.json()
        if data.get('status') != 'created':
            log(f"❌ TEST A FAILED: Expected status 'created', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        order_id = intent.get('orderIntentId')
        if not order_id:
            log(f"❌ TEST A FAILED: No orderIntentId returned")
            return False
        
        # Verify intent state and fields
        if intent.get('state') != 'PENDING_CONFIRMATION':
            log(f"❌ TEST A FAILED: Expected state PENDING_CONFIRMATION, got {intent.get('state')}")
            return False
        
        required_fields = ['decisionInputsHash', 'engineVersion', 'referencePrice', 'maxBuyPrice', 'expiresAt']
        for field in required_fields:
            if field not in intent:
                log(f"❌ TEST A FAILED: Missing required field: {field}")
                return False
        
        log(f"✓ Intent created: {order_id}, state={intent.get('state')}")
        log(f"  decisionInputsHash: {intent.get('decisionInputsHash')}")
        log(f"  engineVersion: {intent.get('engineVersion')}")
        log(f"  referencePrice: {intent.get('referencePrice')}")
        log(f"  maxBuyPrice: {intent.get('maxBuyPrice')}")
        log(f"  expiresAt: {intent.get('expiresAt')}")
        
        # 2. Try execute BEFORE confirm (should fail)
        log(f"\n2. Trying execute BEFORE confirm (should fail)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Execute endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'error' or data.get('error') != 'ILLEGAL_STATE':
            log(f"❌ TEST A FAILED: Expected error ILLEGAL_STATE, got {data}")
            return False
        
        log(f"✓ Execute before confirm correctly rejected: {data.get('error')}")
        
        # 3. Confirm
        log(f"\n3. Confirming order...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Confirm failed: {resp.status_code} {resp.text}")
            return False
        
        data = resp.json()
        if data.get('status') != 'confirmed':
            log(f"❌ TEST A FAILED: Expected status 'confirmed', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'CONFIRMED':
            log(f"❌ TEST A FAILED: Expected state CONFIRMED, got {intent.get('state')}")
            return False
        
        log(f"✓ Order confirmed, state={intent.get('state')}")
        
        # 4. Execute (full fill)
        log(f"\n4. Executing order (full fill)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Execute failed: {resp.status_code} {resp.text}")
            return False
        
        data = resp.json()
        if data.get('status') != 'filled':
            log(f"❌ TEST A FAILED: Expected status 'filled', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'FILLED':
            log(f"❌ TEST A FAILED: Expected state FILLED, got {intent.get('state')}")
            return False
        
        fill = data.get('fill', {})
        required_fill_fields = ['decisionPrice', 'executionSpot', 'actualSlippageBps', 'fillQuantity', 'fillUsd', 'remainingQuantity']
        for field in required_fill_fields:
            if field not in fill:
                log(f"❌ TEST A FAILED: Missing fill field: {field}")
                return False
        
        log(f"✓ Order executed and FILLED")
        log(f"  decisionPrice: {fill.get('decisionPrice')}")
        log(f"  executionSpot: {fill.get('executionSpot')}")
        log(f"  actualSlippageBps: {fill.get('actualSlippageBps')}")
        log(f"  fillQuantity: {fill.get('fillQuantity')}")
        log(f"  fillUsd: {fill.get('fillUsd')}")
        log(f"  remainingQuantity: {fill.get('remainingQuantity')}")
        
        # 5. Check paper portfolio
        log(f"\n5. Checking paper portfolio...")
        resp = requests.get(f"{BASE_URL}/v1/albert/paper-portfolio", params={"pid": pid}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Paper portfolio failed: {resp.status_code}")
            return False
        
        data = resp.json()
        paper = data.get('paperPortfolio', {})
        recon = data.get('reconciliation', {})
        
        positions = paper.get('positions', [])
        sym_found = any(p.get('asset') == sym for p in positions)
        if not sym_found:
            log(f"❌ TEST A FAILED: {sym} not found in paper portfolio positions")
            return False
        
        if not recon.get('ok'):
            log(f"❌ TEST A FAILED: Reconciliation not ok: {recon}")
            return False
        
        log(f"✓ Paper portfolio contains {sym}, reconciliation.ok=True")
        
        # 6. Check portfolio summary (fills feed the engine)
        log(f"\n6. Checking portfolio summary...")
        resp = requests.get(f"{BASE_URL}/v1/albert/portfolio-summary", params={"pid": pid}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Portfolio summary failed: {resp.status_code}")
            return False
        
        data = resp.json()
        holdings = data.get('holdings', [])
        sym_in_holdings = any(h.get('asset') == sym for h in holdings)
        if not sym_in_holdings:
            log(f"❌ TEST A FAILED: {sym} not found in portfolio summary holdings")
            return False
        
        log(f"✓ Portfolio summary now includes {sym}")
        
        # 7. FILLED is terminal - try confirm, cancel, execute (all should fail)
        log(f"\n7. Testing FILLED is terminal...")
        
        # Try confirm
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        data = resp.json()
        if data.get('error') != 'TERMINAL_STATE':
            log(f"❌ TEST A FAILED: Confirm after FILLED should return TERMINAL_STATE, got {data}")
            return False
        log(f"✓ Confirm after FILLED correctly rejected: TERMINAL_STATE")
        
        # Try cancel
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/cancel", timeout=30)
        data = resp.json()
        if data.get('error') != 'TERMINAL_STATE':
            log(f"❌ TEST A FAILED: Cancel after FILLED should return TERMINAL_STATE, got {data}")
            return False
        log(f"✓ Cancel after FILLED correctly rejected: TERMINAL_STATE")
        
        # Try execute
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        data = resp.json()
        if data.get('error') != 'TERMINAL_STATE':
            log(f"❌ TEST A FAILED: Execute after FILLED should return TERMINAL_STATE, got {data}")
            return False
        log(f"✓ Execute after FILLED correctly rejected: TERMINAL_STATE")
        
        # 8. Check ledger has exactly ONE fill
        log(f"\n8. Checking ledger has exactly ONE fill...")
        resp = requests.get(f"{BASE_URL}/v1/albert/orders", params={"pid": pid}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST A FAILED: Orders list failed: {resp.status_code}")
            return False
        
        data = resp.json()
        orders = data.get('orders', [])
        our_order = next((o for o in orders if o.get('orderIntentId') == order_id), None)
        if not our_order:
            log(f"❌ TEST A FAILED: Order not found in orders list")
            return False
        
        fills = our_order.get('fills', [])
        if len(fills) != 1:
            log(f"❌ TEST A FAILED: Expected exactly 1 fill, got {len(fills)}")
            return False
        
        log(f"✓ Ledger has exactly ONE fill (no double-fill)")
        
        log("\n✅ TEST A PASSED: HAPPY FULL FILL")
        return True
        
    except Exception as e:
        log(f"❌ TEST A FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_b_idempotency():
    """TEST B: IDEMPOTENCY - same idempotencyKey returns same orderIntentId"""
    log("\n" + "="*80)
    log("TEST B: IDEMPOTENCY")
    log("="*80)
    
    pid = "u_TEST_E_B"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST B FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST B FAILED: No BUY symbol available")
            return False
        
        # 1. Create first intent
        log(f"\n1. Creating first order intent...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_idem"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST B FAILED: First create failed: {resp.status_code}")
            return False
        
        data1 = resp.json()
        if data1.get('status') != 'created':
            log(f"❌ TEST B FAILED: Expected status 'created', got {data1.get('status')}")
            return False
        
        order_id_1 = data1.get('intent', {}).get('orderIntentId')
        log(f"✓ First intent created: {order_id_1}")
        
        # 2. Create second intent with SAME idempotencyKey
        log(f"\n2. Creating second order intent with SAME idempotencyKey...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST B FAILED: Second create failed: {resp.status_code}")
            return False
        
        data2 = resp.json()
        if data2.get('status') != 'exists':
            log(f"❌ TEST B FAILED: Expected status 'exists', got {data2.get('status')}")
            return False
        
        order_id_2 = data2.get('intent', {}).get('orderIntentId')
        log(f"✓ Second create returned status 'exists' with orderIntentId: {order_id_2}")
        
        # 3. Verify same orderIntentId
        if order_id_1 != order_id_2:
            log(f"❌ TEST B FAILED: Different orderIntentIds: {order_id_1} vs {order_id_2}")
            return False
        
        log(f"✓ Same orderIntentId returned: {order_id_1}")
        
        # 4. Verify only one intent exists
        resp = requests.get(f"{BASE_URL}/v1/albert/orders", params={"pid": pid}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST B FAILED: Orders list failed: {resp.status_code}")
            return False
        
        data = resp.json()
        orders = data.get('orders', [])
        if len(orders) != 1:
            log(f"❌ TEST B FAILED: Expected exactly 1 order, got {len(orders)}")
            return False
        
        log(f"✓ Only ONE intent exists for pid+idempotencyKey")
        
        log("\n✅ TEST B PASSED: IDEMPOTENCY")
        return True
        
    except Exception as e:
        log(f"❌ TEST B FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_c_staleness_at_confirm():
    """TEST C: STALENESS AT CONFIRM - change portfolio after create, then confirm"""
    log("\n" + "="*80)
    log("TEST C: STALENESS AT CONFIRM")
    log("="*80)
    
    pid = "u_TEST_E_C"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST C FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST C FAILED: No BUY symbol available")
            return False
        
        # 1. Create intent
        log(f"\n1. Creating order intent...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_stale_c"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST C FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        order_id = data.get('intent', {}).get('orderIntentId')
        log(f"✓ Intent created: {order_id}")
        
        # 2. Change the portfolio (make it stale)
        log(f"\n2. Changing portfolio to make decision stale...")
        portfolio_payload = {
            "pid": pid,
            "usdc": 60000,  # Different USDC
            "positions": [{"asset": "BTC", "size": 0.1, "avg_entry": 50000}]  # Add a position
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST C FAILED: Portfolio update failed: {resp.status_code}")
            return False
        log(f"✓ Portfolio changed")
        
        # 3. Try to confirm (should be rejected as STALE_DECISION)
        log(f"\n3. Confirming order (should be rejected as STALE_DECISION)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST C FAILED: Confirm endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'rejected':
            log(f"❌ TEST C FAILED: Expected status 'rejected', got {data.get('status')}")
            return False
        
        if data.get('reason') != 'STALE_DECISION':
            log(f"❌ TEST C FAILED: Expected reason STALE_DECISION, got {data.get('reason')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'REJECTED':
            log(f"❌ TEST C FAILED: Expected state REJECTED, got {intent.get('state')}")
            return False
        
        log(f"✓ Confirm correctly rejected: status={data.get('status')}, reason={data.get('reason')}, state={intent.get('state')}")
        
        log("\n✅ TEST C PASSED: STALENESS AT CONFIRM")
        return True
        
    except Exception as e:
        log(f"❌ TEST C FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_d_staleness_at_execute():
    """TEST D: STALENESS AT EXECUTE - confirm OK, then change portfolio, then execute"""
    log("\n" + "="*80)
    log("TEST D: STALENESS AT EXECUTE")
    log("="*80)
    
    pid = "u_TEST_E_D"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST D FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST D FAILED: No BUY symbol available")
            return False
        
        # 1. Create intent
        log(f"\n1. Creating order intent...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_stale_d"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST D FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        order_id = data.get('intent', {}).get('orderIntentId')
        log(f"✓ Intent created: {order_id}")
        
        # 2. Confirm (should succeed)
        log(f"\n2. Confirming order...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST D FAILED: Confirm failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'confirmed':
            log(f"❌ TEST D FAILED: Expected status 'confirmed', got {data.get('status')}")
            return False
        log(f"✓ Order confirmed")
        
        # 3. Change the portfolio (make it stale)
        log(f"\n3. Changing portfolio to make decision stale...")
        portfolio_payload = {
            "pid": pid,
            "usdc": 70000,  # Different USDC
            "positions": [{"asset": "ETH", "size": 10, "avg_entry": 2000}]  # Add a position
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST D FAILED: Portfolio update failed: {resp.status_code}")
            return False
        log(f"✓ Portfolio changed")
        
        # 4. Try to execute (should be rejected as STALE_DECISION)
        log(f"\n4. Executing order (should be rejected as STALE_DECISION)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST D FAILED: Execute endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'rejected':
            log(f"❌ TEST D FAILED: Expected status 'rejected', got {data.get('status')}")
            return False
        
        if data.get('reason') != 'STALE_DECISION':
            log(f"❌ TEST D FAILED: Expected reason STALE_DECISION, got {data.get('reason')}")
            return False
        
        log(f"✓ Execute correctly rejected: status={data.get('status')}, reason={data.get('reason')}")
        
        log("\n✅ TEST D PASSED: STALENESS AT EXECUTE")
        return True
        
    except Exception as e:
        log(f"❌ TEST D FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_e_expiry():
    """TEST E: EXPIRY - verify TTL semantics (expiresAt ~= createdAt + 5 minutes)"""
    log("\n" + "="*80)
    log("TEST E: EXPIRY")
    log("="*80)
    
    pid = "u_TEST_E_E"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST E FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST E FAILED: No BUY symbol available")
            return False
        
        # 1. Create intent
        log(f"\n1. Creating order intent...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_expiry"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST E FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        intent = data.get('intent', {})
        order_id = intent.get('orderIntentId')
        created_at = intent.get('createdAt')
        expires_at = intent.get('expiresAt')
        
        log(f"✓ Intent created: {order_id}")
        log(f"  createdAt: {created_at}")
        log(f"  expiresAt: {expires_at}")
        
        # 2. Verify TTL is ~300 seconds (5 minutes)
        from datetime import datetime
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        expires = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        ttl_seconds = (expires - created).total_seconds()
        
        if not (290 <= ttl_seconds <= 310):
            log(f"❌ TEST E FAILED: TTL should be ~300s, got {ttl_seconds}s")
            return False
        
        log(f"✓ TTL verified: {ttl_seconds}s (~300s expected)")
        
        # 3. Confirm
        log(f"\n2. Confirming order...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST E FAILED: Confirm failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'confirmed':
            log(f"❌ TEST E FAILED: Expected status 'confirmed', got {data.get('status')}")
            return False
        log(f"✓ Order confirmed")
        
        # 4. Patch Mongo to set expiresAt to the past
        log(f"\n3. Patching MongoDB to set expiresAt to the past...")
        try:
            client = MongoClient(MONGO_URL)
            db = client[DB_NAME]
            coll = db['albert_order_intents']
            
            past_time = datetime.utcnow().replace(year=2020).isoformat()
            result = coll.update_one(
                {'_id': order_id},
                {'$set': {'expiresAt': past_time}}
            )
            
            if result.modified_count != 1:
                log(f"❌ TEST E FAILED: Failed to patch expiresAt in MongoDB")
                client.close()
                return False
            
            log(f"✓ expiresAt patched to past: {past_time}")
            client.close()
        except Exception as e:
            log(f"❌ TEST E FAILED: MongoDB patch error: {e}")
            return False
        
        # 5. Try to execute (should be EXPIRED)
        log(f"\n4. Executing order (should be EXPIRED)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST E FAILED: Execute endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'expired':
            log(f"❌ TEST E FAILED: Expected status 'expired', got {data.get('status')}")
            return False
        
        if data.get('reason') != 'EXPIRED':
            log(f"❌ TEST E FAILED: Expected reason EXPIRED, got {data.get('reason')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'EXPIRED':
            log(f"❌ TEST E FAILED: Expected state EXPIRED, got {intent.get('state')}")
            return False
        
        log(f"✓ Execute correctly returned: status={data.get('status')}, reason={data.get('reason')}, state={intent.get('state')}")
        
        # 6. Try to confirm after EXPIRED (should be TERMINAL_STATE)
        log(f"\n5. Confirming after EXPIRED (should be TERMINAL_STATE)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST E FAILED: Confirm endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('error') != 'TERMINAL_STATE':
            log(f"❌ TEST E FAILED: Expected error TERMINAL_STATE, got {data}")
            return False
        
        log(f"✓ Confirm after EXPIRED correctly rejected: TERMINAL_STATE")
        
        log("\n✅ TEST E PASSED: EXPIRY")
        return True
        
    except Exception as e:
        log(f"❌ TEST E FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_f_directional_slippage():
    """TEST F: DIRECTIONAL SLIPPAGE - BUY and SELL slippage checks"""
    log("\n" + "="*80)
    log("TEST F: DIRECTIONAL SLIPPAGE")
    log("="*80)
    
    pid = "u_TEST_E_F"
    TEST_PIDS.append(pid)
    
    try:
        # Part 1: BUY slippage
        log("\n--- Part 1: BUY Slippage ---")
        
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST F FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST F FAILED: No BUY symbol available")
            return False
        
        # 1. Create BUY intent
        log(f"\n1. Creating BUY order intent for {sym}...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_slip_buy"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        intent = data.get('intent', {})
        order_id = intent.get('orderIntentId')
        side = intent.get('side')
        
        if side != 'BUY':
            log(f"❌ TEST F FAILED: Expected side BUY, got {side}")
            return False
        
        log(f"✓ BUY intent created: {order_id}, side={side}")
        log(f"  referencePrice: {intent.get('referencePrice')}")
        log(f"  maxBuyPrice: {intent.get('maxBuyPrice')}")
        
        # Verify maxBuyPrice is approximately referencePrice * (1 + slippageBps/10000)
        ref_price = intent.get('referencePrice')
        max_buy = intent.get('maxBuyPrice')
        slippage_bps = intent.get('slippageToleranceBps', 50)
        expected_max = ref_price * (1 + slippage_bps / 10000.0)
        
        if abs(max_buy - expected_max) > 0.01:
            log(f"❌ TEST F FAILED: maxBuyPrice {max_buy} doesn't match expected {expected_max}")
            return False
        
        log(f"✓ maxBuyPrice verified: {max_buy} ≈ {expected_max}")
        
        # 2. Confirm
        log(f"\n2. Confirming BUY order...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Confirm failed: {resp.status_code}")
            return False
        log(f"✓ BUY order confirmed")
        
        # 3. Patch Mongo to set maxBuyPrice very low (force slippage rejection)
        log(f"\n3. Patching MongoDB to set maxBuyPrice=1.0 (force slippage)...")
        try:
            client = MongoClient(MONGO_URL)
            db = client[DB_NAME]
            coll = db['albert_order_intents']
            
            result = coll.update_one(
                {'_id': order_id},
                {'$set': {'maxBuyPrice': 1.0}}
            )
            
            if result.modified_count != 1:
                log(f"❌ TEST F FAILED: Failed to patch maxBuyPrice in MongoDB")
                client.close()
                return False
            
            log(f"✓ maxBuyPrice patched to 1.0")
            client.close()
        except Exception as e:
            log(f"❌ TEST F FAILED: MongoDB patch error: {e}")
            return False
        
        # 4. Try to execute (should be rejected SLIPPAGE_EXCEEDED)
        log(f"\n4. Executing BUY order (should be rejected SLIPPAGE_EXCEEDED)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Execute endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'rejected':
            log(f"❌ TEST F FAILED: Expected status 'rejected', got {data.get('status')}")
            return False
        
        if data.get('reason') != 'SLIPPAGE_EXCEEDED':
            log(f"❌ TEST F FAILED: Expected reason SLIPPAGE_EXCEEDED, got {data.get('reason')}")
            return False
        
        log(f"✓ BUY order correctly rejected: status={data.get('status')}, reason={data.get('reason')}")
        
        # Part 2: SELL slippage
        log("\n--- Part 2: SELL Slippage ---")
        
        # Setup for SELL: need to hold a coin that's excluded
        log(f"\n5. Setting up for SELL test (excluded coin)...")
        
        # Update mandate to exclude DOGE
        mandate_payload = {
            "pid": pid,
            "mandate": {
                "risk_tolerance": "moderate",
                "reserve_pct": 25,
                "approved_coins": ["BTC", "ETH", "SOL"],
                "excluded_coins": ["DOGE"],
                "max_alloc_pct": {
                    "BTC": 40,
                    "ETH": 30,
                    "SOL": 20
                },
                "max_trade_risk_pct": 2
            }
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/mandate", json=mandate_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Mandate update failed: {resp.status_code}")
            return False
        
        # Update portfolio to hold DOGE
        portfolio_payload = {
            "pid": pid,
            "usdc": 50000,
            "positions": [{"asset": "DOGE", "size": 5000, "avg_entry": 0.1}]
        }
        resp = requests.post(f"{BASE_URL}/v1/portfolio", json=portfolio_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Portfolio update failed: {resp.status_code}")
            return False
        
        log(f"✓ Setup complete: holding DOGE (excluded)")
        
        # 6. Create SELL intent for DOGE
        log(f"\n6. Creating SELL order intent for DOGE...")
        create_payload = {
            "pid": pid,
            "asset": "DOGE",
            "idempotencyKey": "k_slip_sell"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Create SELL failed: {resp.status_code}")
            return False
        
        data = resp.json()
        intent = data.get('intent', {})
        order_id_sell = intent.get('orderIntentId')
        side = intent.get('side')
        
        if side != 'SELL':
            log(f"❌ TEST F FAILED: Expected side SELL, got {side}")
            return False
        
        log(f"✓ SELL intent created: {order_id_sell}, side={side}")
        log(f"  referencePrice: {intent.get('referencePrice')}")
        log(f"  minSellPrice: {intent.get('minSellPrice')}")
        
        # Verify minSellPrice is approximately referencePrice * (1 - slippageBps/10000)
        ref_price = intent.get('referencePrice')
        min_sell = intent.get('minSellPrice')
        slippage_bps = intent.get('slippageToleranceBps', 50)
        expected_min = ref_price * (1 - slippage_bps / 10000.0)
        
        if abs(min_sell - expected_min) > 0.01:
            log(f"❌ TEST F FAILED: minSellPrice {min_sell} doesn't match expected {expected_min}")
            return False
        
        log(f"✓ minSellPrice verified: {min_sell} ≈ {expected_min}")
        
        # 7. Confirm SELL
        log(f"\n7. Confirming SELL order...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_sell}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Confirm SELL failed: {resp.status_code}")
            return False
        log(f"✓ SELL order confirmed")
        
        # 8. Patch Mongo to set minSellPrice very high (force slippage rejection)
        log(f"\n8. Patching MongoDB to set minSellPrice=1e12 (force slippage)...")
        try:
            client = MongoClient(MONGO_URL)
            db = client[DB_NAME]
            coll = db['albert_order_intents']
            
            result = coll.update_one(
                {'_id': order_id_sell},
                {'$set': {'minSellPrice': 1e12}}
            )
            
            if result.modified_count != 1:
                log(f"❌ TEST F FAILED: Failed to patch minSellPrice in MongoDB")
                client.close()
                return False
            
            log(f"✓ minSellPrice patched to 1e12")
            client.close()
        except Exception as e:
            log(f"❌ TEST F FAILED: MongoDB patch error: {e}")
            return False
        
        # 9. Try to execute (should be rejected SLIPPAGE_EXCEEDED)
        log(f"\n9. Executing SELL order (should be rejected SLIPPAGE_EXCEEDED)...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_sell}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST F FAILED: Execute endpoint error: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'rejected':
            log(f"❌ TEST F FAILED: Expected status 'rejected', got {data.get('status')}")
            return False
        
        if data.get('reason') != 'SLIPPAGE_EXCEEDED':
            log(f"❌ TEST F FAILED: Expected reason SLIPPAGE_EXCEEDED, got {data.get('reason')}")
            return False
        
        log(f"✓ SELL order correctly rejected: status={data.get('status')}, reason={data.get('reason')}")
        
        log("\n✅ TEST F PASSED: DIRECTIONAL SLIPPAGE")
        return True
        
    except Exception as e:
        log(f"❌ TEST F FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_g_partial_fill_and_cancel():
    """TEST G: PARTIAL FILL + CANCEL - partial fills and cancel from various states"""
    log("\n" + "="*80)
    log("TEST G: PARTIAL FILL + CANCEL")
    log("="*80)
    
    pid = "u_TEST_E_G"
    TEST_PIDS.append(pid)
    
    try:
        # Part 1: Partial fill
        log("\n--- Part 1: Partial Fill ---")
        
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST G FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST G FAILED: No BUY symbol available")
            return False
        
        # 1. Create and confirm BUY intent
        log(f"\n1. Creating and confirming BUY order...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_partial"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        intent = data.get('intent', {})
        order_id = intent.get('orderIntentId')
        quantity = intent.get('quantity')
        
        log(f"✓ Intent created: {order_id}, quantity={quantity}")
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Confirm failed: {resp.status_code}")
            return False
        log(f"✓ Order confirmed")
        
        # 2. Execute with partial fill (40% of quantity)
        partial_qty = quantity * 0.4
        log(f"\n2. Executing with partial fill (40% = {partial_qty})...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", 
                           json={"simulateFillQty": partial_qty}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Partial execute failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'partially_filled':
            log(f"❌ TEST G FAILED: Expected status 'partially_filled', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'PARTIALLY_FILLED':
            log(f"❌ TEST G FAILED: Expected state PARTIALLY_FILLED, got {intent.get('state')}")
            return False
        
        remaining = intent.get('remainingQuantity')
        if remaining <= 0:
            log(f"❌ TEST G FAILED: remainingQuantity should be > 0, got {remaining}")
            return False
        
        log(f"✓ Partial fill successful: status={data.get('status')}, state={intent.get('state')}, remainingQuantity={remaining}")
        
        # 3. Execute again (full remaining)
        log(f"\n3. Executing again to fill remaining quantity...")
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Second execute failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'filled':
            log(f"❌ TEST G FAILED: Expected status 'filled', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'FILLED':
            log(f"❌ TEST G FAILED: Expected state FILLED, got {intent.get('state')}")
            return False
        
        log(f"✓ Second fill successful: status={data.get('status')}, state={intent.get('state')}")
        
        # 4. Check ledger has 2 fills
        fills = intent.get('fills', [])
        if len(fills) != 2:
            log(f"❌ TEST G FAILED: Expected 2 fills, got {len(fills)}")
            return False
        
        log(f"✓ Ledger has 2 fills for this intent")
        
        # Part 2: Cancel from various states
        log("\n--- Part 2: Cancel from Various States ---")
        
        # 5. Cancel from PENDING_CONFIRMATION
        log(f"\n5. Testing cancel from PENDING_CONFIRMATION...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_cancel_pending"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Create failed: {resp.status_code}")
            return False
        
        order_id_pending = resp.json().get('intent', {}).get('orderIntentId')
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_pending}/cancel", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Cancel from PENDING failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'cancelled':
            log(f"❌ TEST G FAILED: Expected status 'cancelled', got {data.get('status')}")
            return False
        
        intent = data.get('intent', {})
        if intent.get('state') != 'CANCELLED':
            log(f"❌ TEST G FAILED: Expected state CANCELLED, got {intent.get('state')}")
            return False
        
        log(f"✓ Cancel from PENDING_CONFIRMATION successful")
        
        # 6. Cancel from CONFIRMED
        log(f"\n6. Testing cancel from CONFIRMED...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_cancel_confirmed"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Create failed: {resp.status_code}")
            return False
        
        order_id_confirmed = resp.json().get('intent', {}).get('orderIntentId')
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_confirmed}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Confirm failed: {resp.status_code}")
            return False
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_confirmed}/cancel", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Cancel from CONFIRMED failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'cancelled':
            log(f"❌ TEST G FAILED: Expected status 'cancelled', got {data.get('status')}")
            return False
        
        log(f"✓ Cancel from CONFIRMED successful")
        
        # 7. Cancel from PARTIALLY_FILLED
        log(f"\n7. Testing cancel from PARTIALLY_FILLED...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_cancel_partial"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        order_id_partial = data.get('intent', {}).get('orderIntentId')
        quantity = data.get('intent', {}).get('quantity')
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_partial}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Confirm failed: {resp.status_code}")
            return False
        
        # Partial fill
        partial_qty = quantity * 0.3
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_partial}/execute", 
                           json={"simulateFillQty": partial_qty}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Partial execute failed: {resp.status_code}")
            return False
        
        # Cancel
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id_partial}/cancel", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST G FAILED: Cancel from PARTIALLY_FILLED failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'cancelled':
            log(f"❌ TEST G FAILED: Expected status 'cancelled', got {data.get('status')}")
            log(f"  Full response: {data}")
            return False
        
        log(f"✓ Cancel from PARTIALLY_FILLED successful")
        
        log("\n✅ TEST G PASSED: PARTIAL FILL + CANCEL")
        return True
        
    except Exception as e:
        log(f"❌ TEST G FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_h_explain_read_only():
    """TEST H: EXPLAIN READ-ONLY - explain endpoint doesn't mutate intent"""
    log("\n" + "="*80)
    log("TEST H: EXPLAIN READ-ONLY")
    log("="*80)
    
    pid = "u_TEST_E_H"
    TEST_PIDS.append(pid)
    
    try:
        # Setup
        if not setup_mandate_and_portfolio(pid):
            log("❌ TEST H FAILED: Setup failed")
            return False
        
        sym = get_buy_symbol(pid)
        if not sym:
            log("❌ TEST H FAILED: No BUY symbol available")
            return False
        
        # 1. Create, confirm, and execute a full order
        log(f"\n1. Creating, confirming, and executing order...")
        create_payload = {
            "pid": pid,
            "asset": sym,
            "idempotencyKey": "k_explain"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/order/create", json=create_payload, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST H FAILED: Create failed: {resp.status_code}")
            return False
        
        data = resp.json()
        order_id = data.get('intent', {}).get('orderIntentId')
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/confirm", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST H FAILED: Confirm failed: {resp.status_code}")
            return False
        
        resp = requests.post(f"{BASE_URL}/v1/albert/order/{order_id}/execute", json={}, timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST H FAILED: Execute failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'filled':
            log(f"❌ TEST H FAILED: Expected status 'filled', got {data.get('status')}")
            return False
        
        original_intent = data.get('intent', {})
        original_order_id = original_intent.get('orderIntentId')
        original_state = original_intent.get('state')
        original_amount = original_intent.get('amountUsd')
        
        log(f"✓ Order FILLED: {order_id}")
        log(f"  orderIntentId: {original_order_id}")
        log(f"  state: {original_state}")
        log(f"  amountUsd: {original_amount}")
        
        # 2. Call explain endpoint
        log(f"\n2. Calling explain endpoint (allow up to 90s for LLM)...")
        explain_payload = {
            "pid": pid,
            "orderIntentId": order_id,
            "question": "why was this created and what makes it stale?"
        }
        resp = requests.post(f"{BASE_URL}/v1/albert/explain-order-intent", 
                           json=explain_payload, timeout=90)
        if resp.status_code != 200:
            log(f"❌ TEST H FAILED: Explain failed: {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'ready':
            log(f"❌ TEST H FAILED: Expected status 'ready', got {data.get('status')}")
            return False
        
        explanation = data.get('explanation', '')
        if not explanation or len(explanation) == 0:
            log(f"❌ TEST H FAILED: Explanation is empty")
            return False
        
        log(f"✓ Explain returned status 'ready' with explanation ({len(explanation)} chars)")
        log(f"  Explanation preview: {explanation[:200]}...")
        
        # 3. Verify intent is UNCHANGED
        returned_intent = data.get('intent', {})
        returned_order_id = returned_intent.get('orderIntentId')
        returned_state = returned_intent.get('state')
        returned_amount = returned_intent.get('amountUsd')
        
        if returned_order_id != original_order_id:
            log(f"❌ TEST H FAILED: orderIntentId changed: {original_order_id} -> {returned_order_id}")
            return False
        
        if returned_state != original_state:
            log(f"❌ TEST H FAILED: state changed: {original_state} -> {returned_state}")
            return False
        
        if returned_amount != original_amount:
            log(f"❌ TEST H FAILED: amountUsd changed: {original_amount} -> {returned_amount}")
            return False
        
        log(f"✓ Intent returned UNCHANGED:")
        log(f"  orderIntentId: {returned_order_id} (same)")
        log(f"  state: {returned_state} (same)")
        log(f"  amountUsd: {returned_amount} (same)")
        
        # 4. Verify intent in DB is also unchanged
        log(f"\n3. Verifying intent in database is unchanged...")
        resp = requests.get(f"{BASE_URL}/v1/albert/order/{order_id}", timeout=30)
        if resp.status_code != 200:
            log(f"❌ TEST H FAILED: Get order failed: {resp.status_code}")
            return False
        
        data = resp.json()
        db_intent = data.get('intent', {})
        db_state = db_intent.get('state')
        db_amount = db_intent.get('amountUsd')
        
        if db_state != original_state:
            log(f"❌ TEST H FAILED: DB state changed: {original_state} -> {db_state}")
            return False
        
        if db_amount != original_amount:
            log(f"❌ TEST H FAILED: DB amountUsd changed: {original_amount} -> {db_amount}")
            return False
        
        log(f"✓ Intent in database is UNCHANGED (state={db_state}, amountUsd={db_amount})")
        
        log("\n✅ TEST H PASSED: EXPLAIN READ-ONLY")
        return True
        
    except Exception as e:
        log(f"❌ TEST H FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    log("="*80)
    log("PHASE E BACKEND TESTING — PAPER ORDER MANAGER")
    log("="*80)
    log(f"Base URL: {BASE_URL}")
    log(f"MongoDB: {MONGO_URL}/{DB_NAME}")
    log("")
    
    results = {}
    
    # Run all tests
    results['A'] = test_a_happy_full_fill()
    results['B'] = test_b_idempotency()
    results['C'] = test_c_staleness_at_confirm()
    results['D'] = test_d_staleness_at_execute()
    results['E'] = test_e_expiry()
    results['F'] = test_f_directional_slippage()
    results['G'] = test_g_partial_fill_and_cancel()
    results['H'] = test_h_explain_read_only()
    
    # Cleanup
    log("\n" + "="*80)
    log("CLEANUP")
    log("="*80)
    cleanup_test_data()
    
    # Summary
    log("\n" + "="*80)
    log("TEST SUMMARY")
    log("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"Test {test}: {status}")
    
    log("")
    log(f"TOTAL: {passed}/{total} tests passed")
    
    if passed == total:
        log("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        log(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
