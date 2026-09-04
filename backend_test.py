#!/usr/bin/env python3
"""
Backend test for Albert Trading Strategies endpoints.
Tests the complete flow: build -> activate -> get -> list -> close + cleanup.
"""
import os
import sys
import requests
import json
from pymongo import MongoClient

# Configuration
BASE_URL = os.getenv('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api"
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'btciq')

print(f"Testing Albert Trading Strategies endpoints")
print(f"API Base URL: {API_BASE}")
print(f"MongoDB: {MONGO_URL}/{DB_NAME}")
print("=" * 80)

# Track created strategy IDs for cleanup
created_strategy_ids = []

def test_step(step_num, description):
    """Print test step header"""
    print(f"\n{'='*80}")
    print(f"STEP {step_num}: {description}")
    print(f"{'='*80}")

def assert_field(obj, field, expected_type=None, msg=""):
    """Assert a field exists and optionally check its type"""
    if field not in obj:
        print(f"❌ FAIL: Missing field '{field}' {msg}")
        return False
    if expected_type and not isinstance(obj[field], expected_type):
        print(f"❌ FAIL: Field '{field}' has wrong type. Expected {expected_type}, got {type(obj[field])} {msg}")
        return False
    return True

def assert_non_empty(obj, field, msg=""):
    """Assert a field exists and is non-empty"""
    if not assert_field(obj, field, msg=msg):
        return False
    if isinstance(obj[field], (list, dict, str)) and len(obj[field]) == 0:
        print(f"❌ FAIL: Field '{field}' is empty {msg}")
        return False
    return True

try:
    # ========================================================================
    # STEP 1: Build BTC strategy
    # ========================================================================
    test_step(1, "POST /api/v1/albert/strategy/build with BTC")
    
    response = requests.post(f"{API_BASE}/v1/albert/strategy/build", 
                            json={"symbol": "BTC"},
                            timeout=60)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    btc_build_data = response.json()
    print(f"Response keys: {list(btc_build_data.keys())}")
    
    # Validate response structure
    if not assert_field(btc_build_data, 'status', str):
        sys.exit(1)
    if btc_build_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{btc_build_data['status']}'")
        sys.exit(1)
    print(f"✅ status='ready'")
    
    if not assert_field(btc_build_data, 'draft', dict):
        sys.exit(1)
    
    btc_draft = btc_build_data['draft']
    print(f"Draft keys: {list(btc_draft.keys())}")
    
    # Validate draft structure
    required_fields = ['title', 'bias', 'position', 'thesis', 'horizon_days', 'targets', 'rules']
    for field in required_fields:
        if not assert_non_empty(btc_draft, field, f"in BTC draft"):
            sys.exit(1)
    
    print(f"✅ Draft has all required fields: {required_fields}")
    
    # Validate targets array
    if not isinstance(btc_draft['targets'], list) or len(btc_draft['targets']) == 0:
        print(f"❌ FAIL: 'targets' must be a non-empty array")
        sys.exit(1)
    print(f"✅ targets is non-empty array with {len(btc_draft['targets'])} items")
    
    # Validate rules array
    if not isinstance(btc_draft['rules'], list) or len(btc_draft['rules']) == 0:
        print(f"❌ FAIL: 'rules' must be a non-empty array")
        sys.exit(1)
    print(f"✅ rules is non-empty array with {len(btc_draft['rules'])} items")
    
    print(f"✅ BTC draft structure validated:")
    print(f"   - title: {btc_draft['title']}")
    print(f"   - bias: {btc_draft['bias']}")
    print(f"   - position: {btc_draft['position']}")
    print(f"   - horizon_days: {btc_draft['horizon_days']}")
    print(f"   - targets: {len(btc_draft['targets'])} items")
    print(f"   - rules: {len(btc_draft['rules'])} items")
    
    # ========================================================================
    # STEP 1b: Build ETH strategy with goal
    # ========================================================================
    test_step("1b", "POST /api/v1/albert/strategy/build with ETH and goal")
    
    response = requests.post(f"{API_BASE}/v1/albert/strategy/build", 
                            json={"symbol": "ETH", "goal": "swing long"},
                            timeout=60)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    eth_build_data = response.json()
    
    if eth_build_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{eth_build_data['status']}'")
        sys.exit(1)
    print(f"✅ status='ready'")
    
    eth_draft = eth_build_data['draft']
    
    # Validate ETH draft structure (same as BTC)
    for field in required_fields:
        if not assert_non_empty(eth_draft, field, f"in ETH draft"):
            sys.exit(1)
    
    if not isinstance(eth_draft['targets'], list) or len(eth_draft['targets']) == 0:
        print(f"❌ FAIL: ETH 'targets' must be a non-empty array")
        sys.exit(1)
    
    if not isinstance(eth_draft['rules'], list) or len(eth_draft['rules']) == 0:
        print(f"❌ FAIL: ETH 'rules' must be a non-empty array")
        sys.exit(1)
    
    print(f"✅ ETH draft structure validated:")
    print(f"   - title: {eth_draft['title']}")
    print(f"   - bias: {eth_draft['bias']}")
    print(f"   - position: {eth_draft['position']}")
    print(f"   - horizon_days: {eth_draft['horizon_days']}")
    print(f"   - targets: {len(eth_draft['targets'])} items")
    print(f"   - rules: {len(eth_draft['rules'])} items")
    
    # ========================================================================
    # STEP 2: Activate BTC strategy
    # ========================================================================
    test_step(2, "POST /api/v1/albert/strategy to activate BTC draft")
    
    response = requests.post(f"{API_BASE}/v1/albert/strategy", 
                            json={"draft": btc_draft},
                            timeout=30)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    btc_activate_data = response.json()
    
    if btc_activate_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{btc_activate_data['status']}'")
        sys.exit(1)
    print(f"✅ status='ready'")
    
    if not assert_field(btc_activate_data, 'strategy', dict):
        sys.exit(1)
    
    btc_strategy = btc_activate_data['strategy']
    print(f"Strategy keys: {list(btc_strategy.keys())}")
    
    # Track for cleanup
    if 'id' in btc_strategy:
        created_strategy_ids.append(btc_strategy['id'])
        print(f"✅ Strategy ID: {btc_strategy['id']}")
    
    # Validate strategy structure
    if not assert_field(btc_strategy, 'status', str):
        sys.exit(1)
    if btc_strategy['status'] != 'active':
        print(f"❌ FAIL: Expected strategy.status='active', got '{btc_strategy['status']}'")
        sys.exit(1)
    print(f"✅ strategy.status='active'")
    
    if not assert_field(btc_strategy, 'entry_price', (int, float)):
        sys.exit(1)
    if btc_strategy['entry_price'] <= 0:
        print(f"❌ FAIL: entry_price must be > 0, got {btc_strategy['entry_price']}")
        sys.exit(1)
    print(f"✅ entry_price={btc_strategy['entry_price']} (> 0)")
    
    if not assert_field(btc_strategy, 'perf', dict):
        sys.exit(1)
    print(f"✅ perf object present")
    
    if not assert_field(btc_strategy, 'events', list):
        sys.exit(1)
    if len(btc_strategy['events']) == 0:
        print(f"❌ FAIL: events array must not be empty")
        sys.exit(1)
    
    # Check for 'opened' event
    opened_event = None
    for event in btc_strategy['events']:
        if event.get('type') == 'opened':
            opened_event = event
            break
    
    if not opened_event:
        print(f"❌ FAIL: No 'opened' event found in events array")
        print(f"Events: {btc_strategy['events']}")
        sys.exit(1)
    print(f"✅ events contains 'opened' event")
    
    print(f"✅ BTC strategy activated successfully")
    
    # ========================================================================
    # STEP 3: ONE-ACTIVE-PER-COIN test
    # ========================================================================
    test_step(3, "ONE-ACTIVE-PER-COIN: Build and activate another BTC strategy")
    
    # Build another BTC strategy
    response = requests.post(f"{API_BASE}/v1/albert/strategy/build", 
                            json={"symbol": "BTC"},
                            timeout=60)
    if response.status_code != 200:
        print(f"❌ FAIL: Build failed with {response.status_code}")
        sys.exit(1)
    
    btc_draft_2 = response.json()['draft']
    print(f"✅ Built second BTC draft")
    
    # Activate the second BTC strategy
    response = requests.post(f"{API_BASE}/v1/albert/strategy", 
                            json={"draft": btc_draft_2},
                            timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: Activate failed with {response.status_code}")
        sys.exit(1)
    
    btc_strategy_2 = response.json()['strategy']
    if 'id' in btc_strategy_2:
        created_strategy_ids.append(btc_strategy_2['id'])
    
    print(f"✅ Activated second BTC strategy (ID: {btc_strategy_2.get('id')})")
    
    # Now GET /api/v1/albert/strategies?symbol=BTC to verify one-active-per-coin
    response = requests.get(f"{API_BASE}/v1/albert/strategies?symbol=BTC", timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: GET strategies failed with {response.status_code}")
        sys.exit(1)
    
    strategies_data = response.json()
    print(f"Strategies response keys: {list(strategies_data.keys())}")
    
    if strategies_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{strategies_data['status']}'")
        sys.exit(1)
    
    if not assert_field(strategies_data, 'active', (dict, type(None))):
        sys.exit(1)
    
    if not assert_field(strategies_data, 'history', list):
        sys.exit(1)
    
    # Verify exactly ONE active strategy
    if strategies_data['active'] is None:
        print(f"❌ FAIL: Expected one active strategy, got None")
        sys.exit(1)
    
    active_strategy = strategies_data['active']
    print(f"✅ Found ONE active strategy (ID: {active_strategy.get('id')})")
    
    # Verify the active strategy is the second one
    if active_strategy.get('id') != btc_strategy_2.get('id'):
        print(f"❌ FAIL: Active strategy ID mismatch. Expected {btc_strategy_2.get('id')}, got {active_strategy.get('id')}")
        sys.exit(1)
    print(f"✅ Active strategy is the second one (most recent)")
    
    # Verify the first strategy is now in history with status 'closed' and close_reason 'superseded'
    first_strategy_in_history = None
    for h in strategies_data['history']:
        if h.get('id') == btc_strategy.get('id'):
            first_strategy_in_history = h
            break
    
    if not first_strategy_in_history:
        print(f"❌ FAIL: First strategy (ID: {btc_strategy.get('id')}) not found in history")
        print(f"History IDs: {[h.get('id') for h in strategies_data['history']]}")
        sys.exit(1)
    
    if first_strategy_in_history.get('status') != 'closed':
        print(f"❌ FAIL: First strategy status should be 'closed', got '{first_strategy_in_history.get('status')}'")
        sys.exit(1)
    print(f"✅ First strategy status='closed'")
    
    if first_strategy_in_history.get('close_reason') != 'superseded':
        print(f"❌ FAIL: First strategy close_reason should be 'superseded', got '{first_strategy_in_history.get('close_reason')}'")
        sys.exit(1)
    print(f"✅ First strategy close_reason='superseded'")
    
    print(f"✅ ONE-ACTIVE-PER-COIN validation passed")
    
    # ========================================================================
    # STEP 4: GET active strategy and list strategies
    # ========================================================================
    test_step(4, "GET /api/v1/albert/strategy?symbol=BTC (active strategy)")
    
    response = requests.get(f"{API_BASE}/v1/albert/strategy?symbol=BTC", timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        sys.exit(1)
    
    active_data = response.json()
    
    if active_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{active_data['status']}'")
        sys.exit(1)
    print(f"✅ status='ready'")
    
    if not assert_field(active_data, 'strategy', dict):
        sys.exit(1)
    
    active_strat = active_data['strategy']
    if active_strat.get('status') != 'active':
        print(f"❌ FAIL: Expected strategy.status='active', got '{active_strat.get('status')}'")
        sys.exit(1)
    print(f"✅ Returned active strategy (ID: {active_strat.get('id')})")
    
    # Test GET /api/v1/albert/strategies?symbol=BTC (already tested above, but verify again)
    test_step("4b", "GET /api/v1/albert/strategies?symbol=BTC (list)")
    
    response = requests.get(f"{API_BASE}/v1/albert/strategies?symbol=BTC", timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        sys.exit(1)
    
    list_data = response.json()
    
    if list_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{list_data['status']}'")
        sys.exit(1)
    
    if not assert_field(list_data, 'active', (dict, type(None))):
        sys.exit(1)
    if not assert_field(list_data, 'history', list):
        sys.exit(1)
    if not assert_field(list_data, 'stats', dict):
        sys.exit(1)
    
    print(f"✅ List response structure validated:")
    print(f"   - active: {list_data['active'] is not None}")
    print(f"   - history: {len(list_data['history'])} items")
    print(f"   - stats: {list(list_data['stats'].keys())}")
    
    # ========================================================================
    # STEP 5: Close active BTC strategy
    # ========================================================================
    test_step(5, "POST /api/v1/albert/strategy/{id}/close with reason='manual'")
    
    active_id = btc_strategy_2.get('id')
    response = requests.post(f"{API_BASE}/v1/albert/strategy/{active_id}/close", 
                            json={"reason": "manual"},
                            timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    close_data = response.json()
    
    if close_data['status'] != 'ready':
        print(f"❌ FAIL: Expected status='ready', got '{close_data['status']}'")
        sys.exit(1)
    
    closed_strategy = close_data['strategy']
    
    if closed_strategy.get('status') != 'closed':
        print(f"❌ FAIL: Expected strategy.status='closed', got '{closed_strategy.get('status')}'")
        sys.exit(1)
    print(f"✅ strategy.status='closed'")
    
    if not assert_field(closed_strategy, 'final_pnl_pct', (int, float)):
        sys.exit(1)
    print(f"✅ final_pnl_pct present: {closed_strategy['final_pnl_pct']}")
    
    if not assert_field(closed_strategy, 'outcome', str):
        sys.exit(1)
    print(f"✅ outcome present: {closed_strategy['outcome']}")
    
    print(f"✅ Strategy closed successfully")
    
    # Verify GET /api/v1/albert/strategy?symbol=BTC now returns status='none'
    test_step("5b", "Verify GET /api/v1/albert/strategy?symbol=BTC returns status='none'")
    
    response = requests.get(f"{API_BASE}/v1/albert/strategy?symbol=BTC", timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        sys.exit(1)
    
    none_data = response.json()
    
    if none_data['status'] != 'none':
        print(f"❌ FAIL: Expected status='none', got '{none_data['status']}'")
        sys.exit(1)
    print(f"✅ status='none' (no active BTC strategy)")
    
    # ========================================================================
    # STEP 6: Activate and close ETH strategy
    # ========================================================================
    test_step(6, "Activate and close ETH strategy")
    
    # Activate ETH strategy
    response = requests.post(f"{API_BASE}/v1/albert/strategy", 
                            json={"draft": eth_draft},
                            timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: ETH activate failed with {response.status_code}")
        sys.exit(1)
    
    eth_strategy = response.json()['strategy']
    if 'id' in eth_strategy:
        created_strategy_ids.append(eth_strategy['id'])
    
    if eth_strategy.get('status') != 'active':
        print(f"❌ FAIL: ETH strategy status should be 'active', got '{eth_strategy.get('status')}'")
        sys.exit(1)
    print(f"✅ ETH strategy activated (ID: {eth_strategy.get('id')})")
    
    # Close ETH strategy
    eth_id = eth_strategy.get('id')
    response = requests.post(f"{API_BASE}/v1/albert/strategy/{eth_id}/close", 
                            json={"reason": "manual"},
                            timeout=30)
    if response.status_code != 200:
        print(f"❌ FAIL: ETH close failed with {response.status_code}")
        sys.exit(1)
    
    eth_closed = response.json()['strategy']
    
    if eth_closed.get('status') != 'closed':
        print(f"❌ FAIL: ETH strategy status should be 'closed', got '{eth_closed.get('status')}'")
        sys.exit(1)
    print(f"✅ ETH strategy closed successfully")
    
    # ========================================================================
    # CLEANUP: Delete all created strategies from MongoDB
    # ========================================================================
    test_step("CLEANUP", "Delete all created strategies from MongoDB")
    
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        strategies_col = db['strategies']
        
        # Delete all strategies we created
        if created_strategy_ids:
            result = strategies_col.delete_many({'id': {'$in': created_strategy_ids}})
            print(f"✅ Deleted {result.deleted_count} strategies from MongoDB")
        
        # Verify collection is empty (or at least our strategies are gone)
        remaining = strategies_col.count_documents({'id': {'$in': created_strategy_ids}})
        if remaining > 0:
            print(f"⚠️  WARNING: {remaining} strategies still remain in collection")
        else:
            print(f"✅ All created strategies removed from collection")
        
        # Show total count in collection
        total_count = strategies_col.count_documents({})
        print(f"✅ Total strategies in collection: {total_count}")
        
        client.close()
        
    except Exception as e:
        print(f"❌ CLEANUP ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print(f"\n{'='*80}")
    print(f"✅ ALL TESTS PASSED")
    print(f"{'='*80}")
    print(f"Summary:")
    print(f"  1. ✅ POST /api/v1/albert/strategy/build (BTC) - draft with targets and rules")
    print(f"  2. ✅ POST /api/v1/albert/strategy/build (ETH with goal) - draft with targets and rules")
    print(f"  3. ✅ POST /api/v1/albert/strategy (activate BTC) - active strategy with entry_price and 'opened' event")
    print(f"  4. ✅ ONE-ACTIVE-PER-COIN - second BTC strategy supersedes first")
    print(f"  5. ✅ GET /api/v1/albert/strategy?symbol=BTC - returns active strategy")
    print(f"  6. ✅ GET /api/v1/albert/strategies?symbol=BTC - returns active + history + stats")
    print(f"  7. ✅ POST /api/v1/albert/strategy/{{id}}/close - closes strategy with final_pnl_pct and outcome")
    print(f"  8. ✅ GET /api/v1/albert/strategy?symbol=BTC after close - returns status='none'")
    print(f"  9. ✅ ETH strategy activate and close - same flow works for ETH")
    print(f" 10. ✅ CLEANUP - all created strategies deleted from MongoDB")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"\n{'='*80}")
    print(f"❌ TEST FAILED WITH EXCEPTION")
    print(f"{'='*80}")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    
    # Attempt cleanup even on failure
    if created_strategy_ids:
        print(f"\nAttempting cleanup of {len(created_strategy_ids)} strategies...")
        try:
            client = MongoClient(MONGO_URL)
            db = client[DB_NAME]
            strategies_col = db['strategies']
            result = strategies_col.delete_many({'id': {'$in': created_strategy_ids}})
            print(f"✅ Cleanup: Deleted {result.deleted_count} strategies")
            client.close()
        except Exception as cleanup_error:
            print(f"❌ Cleanup failed: {cleanup_error}")
    
    sys.exit(1)
