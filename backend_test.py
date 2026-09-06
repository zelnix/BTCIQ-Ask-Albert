#!/usr/bin/env python3
"""
Backend Test Script for Chat Rebalance and Basket Rotation Features
Tests A-E as specified in the review request
"""
import os
import sys
import time
import json
import requests
from typing import Dict, List, Any, Optional

# Base URL from environment
BASE_URL = os.getenv('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api"

# Test configuration
TIMEOUT = 90  # 90s timeout for LLM/basket-build calls
SHORT_TIMEOUT = 30  # 30s for regular API calls

# Test PIDs
PID_NO_BASKETS = "u_CR_NONE"
PID_ONE_BASKET = "u_CR_ONE"
PID_TWO_BASKETS = "u_CR_TWO"

# Track created baskets for cleanup
created_baskets = []

def log_test(test_name: str, message: str):
    """Log test progress"""
    print(f"\n{'='*80}")
    print(f"[{test_name}] {message}")
    print('='*80)

def log_result(test_name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status} - {test_name}")
    if details:
        print(f"Details: {details}")

def build_basket(goal: str, timeout: int = TIMEOUT) -> Optional[Dict]:
    """Build a basket draft"""
    try:
        log_test("BUILD_BASKET", f"Building basket with goal: {goal}")
        response = requests.post(
            f"{API_BASE}/v1/albert/strategy/basket/build",
            json={"goal": goal},
            timeout=timeout
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ready' and data.get('draft'):
                draft = data['draft']
                print(f"Draft created: {draft.get('title')}")
                print(f"Legs: {len(draft.get('legs', []))} coins")
                return draft
        print(f"Failed to build basket: {response.text[:200]}")
        return None
    except Exception as e:
        print(f"Error building basket: {e}")
        return None

def save_basket(draft: Dict, pid: str, timeout: int = SHORT_TIMEOUT) -> Optional[Dict]:
    """Save/activate a basket"""
    try:
        log_test("SAVE_BASKET", f"Saving basket for pid: {pid}")
        response = requests.post(
            f"{API_BASE}/v1/albert/strategy/basket",
            json={"draft": draft, "pid": pid},
            timeout=timeout
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ready' and data.get('basket'):
                basket = data['basket']
                basket_id = basket.get('id')
                print(f"Basket saved: {basket_id}")
                print(f"Title: {basket.get('title')}")
                created_baskets.append({'id': basket_id, 'pid': pid})
                return basket
        print(f"Failed to save basket: {response.text[:200]}")
        return None
    except Exception as e:
        print(f"Error saving basket: {e}")
        return None

def list_baskets(pid: str, timeout: int = SHORT_TIMEOUT) -> Dict:
    """List baskets for a pid"""
    try:
        response = requests.get(
            f"{API_BASE}/v1/albert/strategy/baskets",
            params={"pid": pid},
            timeout=timeout
        )
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception as e:
        print(f"Error listing baskets: {e}")
        return {}

def close_basket(basket_id: str, timeout: int = SHORT_TIMEOUT) -> bool:
    """Close a basket"""
    try:
        response = requests.post(
            f"{API_BASE}/v1/albert/strategy/basket/{basket_id}/close",
            json={},
            timeout=timeout
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Error closing basket: {e}")
        return False

def chat(session_id: str, message: str, pid: str, timeout: int = TIMEOUT) -> Optional[Dict]:
    """Send a chat message"""
    try:
        response = requests.post(
            f"{API_BASE}/v1/chat",
            json={"session_id": session_id, "message": message, "pid": pid},
            timeout=timeout
        )
        print(f"Chat response status: {response.status_code}")
        if response.status_code == 200:
            return response.json()
        print(f"Chat failed: {response.text[:200]}")
        return None
    except Exception as e:
        print(f"Error in chat: {e}")
        return None

def test_a_no_baskets():
    """TEST A — No baskets: chat should say no active baskets, NO basket_rebalance"""
    log_test("TEST A", "Testing chat rebalance with NO active baskets")
    
    try:
        # Ensure no baskets exist for this pid
        baskets_data = list_baskets(PID_NO_BASKETS)
        active = baskets_data.get('active', [])
        if active:
            print(f"Cleaning up {len(active)} existing baskets...")
            for b in active:
                close_basket(b['id'])
        
        # Send rebalance request
        response = chat("cr-a", "rebalance my basket", PID_NO_BASKETS)
        
        if not response:
            log_result("TEST A", False, "Chat request failed")
            return False
        
        # Validate response
        has_basket_rebalance = 'basket_rebalance' in response and response['basket_rebalance'] is not None
        text = response.get('text', '')
        mentions_no_baskets = any(phrase in text.lower() for phrase in ['no active basket', "don't have any", 'no basket'])
        
        passed = not has_basket_rebalance and mentions_no_baskets
        
        details = f"basket_rebalance present: {has_basket_rebalance}, text mentions no baskets: {mentions_no_baskets}"
        if not has_basket_rebalance:
            details += f"\nText: {text[:200]}"
        
        log_result("TEST A", passed, details)
        return passed
        
    except Exception as e:
        log_result("TEST A", False, f"Exception: {e}")
        return False

def test_b_single_basket():
    """TEST B — Single basket, direct intent: should return basket_rebalance with weights"""
    log_test("TEST B", "Testing chat rebalance with ONE active basket")
    
    try:
        # Clean up any existing baskets
        baskets_data = list_baskets(PID_ONE_BASKET)
        for b in baskets_data.get('active', []):
            close_basket(b['id'])
        
        # Build and save ONE basket
        draft = build_basket("long the majors")
        if not draft:
            log_result("TEST B", False, "Failed to build basket")
            return False
        
        basket = save_basket(draft, PID_ONE_BASKET)
        if not basket:
            log_result("TEST B", False, "Failed to save basket")
            return False
        
        basket_title = basket.get('title', '')
        print(f"Created basket: {basket_title}")
        
        # Test 1: "rebalance my basket"
        response1 = chat("cr-b", "rebalance my basket", PID_ONE_BASKET)
        if not response1:
            log_result("TEST B", False, "Chat request 1 failed")
            return False
        
        # Validate response 1
        basket_rebalance1 = response1.get('basket_rebalance')
        if not basket_rebalance1:
            log_result("TEST B", False, "No basket_rebalance in response 1")
            return False
        
        # Check required fields
        has_basket_id = 'basket_id' in basket_rebalance1
        has_title = 'title' in basket_rebalance1
        has_rationale = 'rationale' in basket_rebalance1
        has_legs = 'legs' in basket_rebalance1 and isinstance(basket_rebalance1['legs'], list)
        
        if not all([has_basket_id, has_title, has_rationale, has_legs]):
            log_result("TEST B", False, f"Missing fields: basket_id={has_basket_id}, title={has_title}, rationale={has_rationale}, legs={has_legs}")
            return False
        
        # Validate legs structure
        legs = basket_rebalance1['legs']
        if not legs:
            log_result("TEST B", False, "No legs in basket_rebalance")
            return False
        
        print(f"\nBasket rebalance response:")
        print(f"  Title: {basket_rebalance1['title']}")
        print(f"  Rationale: {basket_rebalance1['rationale'][:100]}...")
        print(f"  Legs: {len(legs)}")
        
        # Check each leg has required fields
        total_suggested = 0
        for i, leg in enumerate(legs):
            has_symbol = 'symbol' in leg
            has_position = 'position' in leg
            has_current = 'current_weight' in leg
            has_suggested = 'suggested_weight' in leg
            
            if not all([has_symbol, has_position, has_current, has_suggested]):
                log_result("TEST B", False, f"Leg {i} missing fields: symbol={has_symbol}, position={has_position}, current_weight={has_current}, suggested_weight={has_suggested}")
                return False
            
            total_suggested += leg['suggested_weight']
            print(f"  {leg['symbol']} {leg['position']}: {leg['current_weight']}% -> {leg['suggested_weight']}%")
        
        # Validate weights sum to ~100
        if not (95 <= total_suggested <= 105):
            log_result("TEST B", False, f"Suggested weights sum to {total_suggested}, expected ~100")
            return False
        
        # Test 2: "reweight my basket please"
        response2 = chat("cr-b2", "reweight my basket please", PID_ONE_BASKET)
        if not response2:
            log_result("TEST B", False, "Chat request 2 failed")
            return False
        
        basket_rebalance2 = response2.get('basket_rebalance')
        if not basket_rebalance2:
            log_result("TEST B", False, "No basket_rebalance in response 2 (reweight)")
            return False
        
        log_result("TEST B", True, f"Both 'rebalance' and 'reweight' triggered basket_rebalance. Weights sum to {total_suggested}%")
        return True
        
    except Exception as e:
        log_result("TEST B", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_c_multiple_baskets():
    """TEST C — Multiple baskets, name match: should match by title/legs"""
    log_test("TEST C", "Testing chat rebalance with TWO active baskets")
    
    try:
        # Clean up any existing baskets
        baskets_data = list_baskets(PID_TWO_BASKETS)
        for b in baskets_data.get('active', []):
            close_basket(b['id'])
        
        # Build and save TWO baskets with distinct themes
        draft1 = build_basket("long defi leaders like UNI AAVE LINK")
        if not draft1:
            log_result("TEST C", False, "Failed to build basket 1")
            return False
        
        basket1 = save_basket(draft1, PID_TWO_BASKETS)
        if not basket1:
            log_result("TEST C", False, "Failed to save basket 1")
            return False
        
        title1 = basket1.get('title', '')
        print(f"Created basket 1: {title1}")
        
        time.sleep(2)  # Brief pause between builds
        
        draft2 = build_basket("long the large cap majors BTC ETH")
        if not draft2:
            log_result("TEST C", False, "Failed to build basket 2")
            return False
        
        basket2 = save_basket(draft2, PID_TWO_BASKETS)
        if not basket2:
            log_result("TEST C", False, "Failed to save basket 2")
            return False
        
        title2 = basket2.get('title', '')
        print(f"Created basket 2: {title2}")
        
        # Test 1: Try to match DeFi basket
        response1 = chat("cr-c1", "rebalance my defi basket", PID_TWO_BASKETS)
        if not response1:
            log_result("TEST C", False, "Chat request 1 failed")
            return False
        
        basket_rebalance1 = response1.get('basket_rebalance')
        if basket_rebalance1:
            matched_title = basket_rebalance1.get('title', '')
            print(f"\nMatched basket: {matched_title}")
            print(f"Expected DeFi-themed basket (basket 1): {title1}")
            
            # Check if it matched the DeFi basket (basket1)
            # We'll check if the matched title is basket1's title
            matched_correctly = matched_title == title1
            
            if not matched_correctly:
                # If titles don't match exactly, check if it's at least not basket2
                matched_correctly = matched_title != title2
                print(f"Note: Title match not exact, but avoided majors basket: {matched_correctly}")
        else:
            log_result("TEST C", False, "No basket_rebalance in response 1 (should match DeFi basket)")
            return False
        
        # Test 2: Ambiguous request (should ask which basket)
        response2 = chat("cr-c2", "rebalance my basket", PID_TWO_BASKETS)
        if not response2:
            log_result("TEST C", False, "Chat request 2 failed")
            return False
        
        basket_rebalance2 = response2.get('basket_rebalance')
        text2 = response2.get('text', '')
        
        # Should NOT have basket_rebalance and should ask which basket
        asks_which = any(phrase in text2.lower() for phrase in ['which basket', 'you have'])
        mentions_titles = title1.lower() in text2.lower() or title2.lower() in text2.lower()
        
        ambiguous_handled = not basket_rebalance2 and asks_which
        
        print(f"\nAmbiguous request handling:")
        print(f"  Has basket_rebalance: {basket_rebalance2 is not None}")
        print(f"  Asks which basket: {asks_which}")
        print(f"  Mentions basket titles: {mentions_titles}")
        print(f"  Text: {text2[:200]}")
        
        passed = matched_correctly and ambiguous_handled
        
        details = f"DeFi match: {matched_correctly}, Ambiguous handled: {ambiguous_handled}"
        log_result("TEST C", passed, details)
        return passed
        
    except Exception as e:
        log_result("TEST C", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_d_rotation_field():
    """TEST D — Rotation field: baskets should have rotation array with sector data"""
    log_test("TEST D", "Testing rotation field in basket list")
    
    try:
        # Use PID_ONE_BASKET which should have an active basket from TEST B
        baskets_data = list_baskets(PID_ONE_BASKET)
        
        if not baskets_data:
            log_result("TEST D", False, "Failed to get baskets list")
            return False
        
        active = baskets_data.get('active', [])
        if not active:
            log_result("TEST D", False, "No active baskets found (TEST B should have created one)")
            return False
        
        print(f"\nFound {len(active)} active basket(s)")
        
        # Check first basket
        basket = active[0]
        print(f"Checking basket: {basket.get('title')}")
        
        # Check rotation field exists
        if 'rotation' not in basket:
            log_result("TEST D", False, "No 'rotation' field in basket")
            return False
        
        rotation = basket['rotation']
        if not isinstance(rotation, list):
            log_result("TEST D", False, f"'rotation' is not a list: {type(rotation)}")
            return False
        
        print(f"Rotation array has {len(rotation)} entries")
        
        # Check each rotation entry
        for i, entry in enumerate(rotation):
            has_sector = 'sector' in entry
            has_strength = 'strength' in entry
            has_hot = 'hot' in entry
            has_symbols = 'symbols' in entry and isinstance(entry['symbols'], list)
            
            if not all([has_sector, has_strength, has_hot, has_symbols]):
                log_result("TEST D", False, f"Rotation entry {i} missing fields: sector={has_sector}, strength={has_strength}, hot={has_hot}, symbols={has_symbols}")
                return False
            
            # Validate types
            if not isinstance(entry['hot'], bool):
                log_result("TEST D", False, f"Rotation entry {i} 'hot' is not bool: {type(entry['hot'])}")
                return False
            
            # strength can be number or null
            if entry['strength'] is not None and not isinstance(entry['strength'], (int, float)):
                log_result("TEST D", False, f"Rotation entry {i} 'strength' is not number or null: {type(entry['strength'])}")
                return False
            
            print(f"  {entry['sector']}: strength={entry['strength']}, hot={entry['hot']}, symbols={entry['symbols']}")
        
        # Check perf field still exists (no regression)
        if 'perf' not in basket:
            log_result("TEST D", False, "No 'perf' field in basket (regression)")
            return False
        
        perf = basket['perf']
        has_total_pnl = 'total_pnl_pct' in perf
        has_legs = 'legs' in perf and isinstance(perf['legs'], list)
        
        if not all([has_total_pnl, has_legs]):
            log_result("TEST D", False, f"Perf field incomplete: total_pnl_pct={has_total_pnl}, legs={has_legs}")
            return False
        
        log_result("TEST D", True, f"Rotation array validated with {len(rotation)} sectors. Perf field intact.")
        return True
        
    except Exception as e:
        log_result("TEST D", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_e_intent_isolation():
    """TEST E — Intent isolation: status queries should NOT trigger rebalance/build"""
    log_test("TEST E", "Testing intent isolation (no false positives)")
    
    try:
        # Test 1: Status query "how are my baskets doing?"
        response1 = chat("cr-e1", "how are my baskets doing?", PID_ONE_BASKET)
        if not response1:
            log_result("TEST E", False, "Chat request 1 failed")
            return False
        
        has_basket_rebalance1 = 'basket_rebalance' in response1 and response1['basket_rebalance'] is not None
        has_basket_draft1 = 'basket_draft' in response1 and response1['basket_draft'] is not None
        
        test1_passed = not has_basket_rebalance1 and not has_basket_draft1
        
        print(f"\nTest 1 - 'how are my baskets doing?':")
        print(f"  Has basket_rebalance: {has_basket_rebalance1}")
        print(f"  Has basket_draft: {has_basket_draft1}")
        print(f"  Passed: {test1_passed}")
        
        # Test 2: General market query "what's your read on BTC right now?"
        response2 = chat("cr-e2", "what's your read on BTC right now?", PID_ONE_BASKET)
        if not response2:
            log_result("TEST E", False, "Chat request 2 failed")
            return False
        
        has_basket_rebalance2 = 'basket_rebalance' in response2 and response2['basket_rebalance'] is not None
        has_basket_draft2 = 'basket_draft' in response2 and response2['basket_draft'] is not None
        
        test2_passed = not has_basket_rebalance2 and not has_basket_draft2
        
        print(f"\nTest 2 - 'what's your read on BTC right now?':")
        print(f"  Has basket_rebalance: {has_basket_rebalance2}")
        print(f"  Has basket_draft: {has_basket_draft2}")
        print(f"  Passed: {test2_passed}")
        
        passed = test1_passed and test2_passed
        
        details = f"Status query isolated: {test1_passed}, Market query isolated: {test2_passed}"
        log_result("TEST E", passed, details)
        return passed
        
    except Exception as e:
        log_result("TEST E", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup():
    """Clean up created baskets"""
    log_test("CLEANUP", f"Cleaning up {len(created_baskets)} created baskets")
    
    for basket_info in created_baskets:
        basket_id = basket_info['id']
        pid = basket_info['pid']
        try:
            success = close_basket(basket_id)
            print(f"Closed basket {basket_id}: {success}")
        except Exception as e:
            print(f"Failed to close basket {basket_id}: {e}")
    
    print("\nCleanup complete")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("CHAT REBALANCE & BASKET ROTATION TESTING")
    print(f"Base URL: {API_BASE}")
    print("="*80)
    
    results = {}
    
    # Run tests in order
    try:
        results['TEST A'] = test_a_no_baskets()
        time.sleep(2)
        
        results['TEST B'] = test_b_single_basket()
        time.sleep(2)
        
        results['TEST C'] = test_c_multiple_baskets()
        time.sleep(2)
        
        results['TEST D'] = test_d_rotation_field()
        time.sleep(2)
        
        results['TEST E'] = test_e_intent_isolation()
        
    finally:
        # Always cleanup
        time.sleep(2)
        cleanup()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    total = len(results)
    passed_count = sum(1 for p in results.values() if p)
    
    print(f"\nTotal: {passed_count}/{total} tests passed")
    print("="*80)
    
    # Exit with appropriate code
    sys.exit(0 if passed_count == total else 1)

if __name__ == "__main__":
    main()
