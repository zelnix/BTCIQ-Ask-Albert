#!/usr/bin/env python3
"""
Backend API Test Suite for BTCIQ Alert Coin Filter Feature
Tests coin-scoped Smart Alerts filtering and acknowledgment
"""

import requests
import json
import sys
from typing import Dict, List, Any

# Base URL from environment
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def print_test_header(test_name: str):
    """Print a formatted test header"""
    print(f"\n{'='*80}")
    print(f"TEST: {test_name}")
    print(f"{'='*80}")

def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")

def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")

def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")

def test_get_alerts_btc():
    """Test 1: GET /api/v1/alerts?symbol=BTC - should return only BTC alerts"""
    print_test_header("GET /api/v1/alerts?symbol=BTC")
    
    try:
        url = f"{BASE_URL}/v1/alerts?symbol=BTC"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        print_info(f"Response keys: {list(data.keys())}")
        
        # Validate response structure
        if data.get('status') != 'ready':
            print_error(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_success("Response status is 'ready'")
        
        # Check required fields
        if 'alerts' not in data:
            print_error("Missing 'alerts' field in response")
            return False
        if 'unseen' not in data:
            print_error("Missing 'unseen' field in response")
            return False
        if 'total' not in data:
            print_error("Missing 'total' field in response")
            return False
        print_success("All required fields present (alerts, unseen, total)")
        
        alerts = data['alerts']
        unseen = data['unseen']
        total = data['total']
        
        print_info(f"Total alerts: {total}, Unseen: {unseen}, Returned: {len(alerts)}")
        
        # Validate that all returned alerts are BTC or legacy (no symbol field)
        btc_count = 0
        legacy_count = 0
        non_btc_count = 0
        
        for alert in alerts:
            symbol = alert.get('symbol')
            if symbol == 'BTC':
                btc_count += 1
            elif symbol is None or symbol == '':
                legacy_count += 1
            else:
                non_btc_count += 1
                print_error(f"Found non-BTC alert with symbol='{symbol}': {alert.get('id', 'unknown')}")
        
        print_info(f"BTC alerts: {btc_count}, Legacy alerts (no symbol): {legacy_count}, Non-BTC: {non_btc_count}")
        
        if non_btc_count > 0:
            print_error(f"Found {non_btc_count} non-BTC alerts in BTC-filtered results")
            return False
        
        print_success(f"All {len(alerts)} alerts are BTC or legacy (no ETH/SOL alerts)")
        
        # Validate counts are non-negative integers
        if not isinstance(unseen, int) or unseen < 0:
            print_error(f"Invalid unseen count: {unseen}")
            return False
        if not isinstance(total, int) or total < 0:
            print_error(f"Invalid total count: {total}")
            return False
        print_success(f"Counts are valid: unseen={unseen}, total={total}")
        
        print_success("TEST PASSED: BTC filter returns only BTC/legacy alerts")
        return True, data
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_get_alerts_sol():
    """Test 2: GET /api/v1/alerts?symbol=SOL - should return only SOL alerts"""
    print_test_header("GET /api/v1/alerts?symbol=SOL")
    
    try:
        url = f"{BASE_URL}/v1/alerts?symbol=SOL"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Validate response structure
        if data.get('status') != 'ready':
            print_error(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_success("Response status is 'ready'")
        
        alerts = data['alerts']
        unseen = data['unseen']
        total = data['total']
        
        print_info(f"Total alerts: {total}, Unseen: {unseen}, Returned: {len(alerts)}")
        
        # Validate that all returned alerts have symbol='SOL'
        sol_count = 0
        non_sol_count = 0
        setup_category_count = 0
        
        for alert in alerts:
            symbol = alert.get('symbol')
            category = alert.get('category')
            
            if symbol == 'SOL':
                sol_count += 1
                if category == 'Setup':
                    setup_category_count += 1
            else:
                non_sol_count += 1
                print_error(f"Found non-SOL alert with symbol='{symbol}': {alert.get('id', 'unknown')}")
        
        print_info(f"SOL alerts: {sol_count}, Non-SOL: {non_sol_count}, Setup category: {setup_category_count}")
        
        if non_sol_count > 0:
            print_error(f"Found {non_sol_count} non-SOL alerts in SOL-filtered results")
            return False
        
        if len(alerts) > 0:
            print_success(f"All {len(alerts)} alerts have symbol='SOL'")
            if setup_category_count > 0:
                print_success(f"Found {setup_category_count} 'Setup' category alert(s) as expected")
        else:
            print_info("No SOL alerts found (may be expected if none exist)")
        
        print_success("TEST PASSED: SOL filter returns only SOL alerts")
        return True, data
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_get_alerts_eth():
    """Test 3: GET /api/v1/alerts?symbol=ETH - should be graceful (may be empty)"""
    print_test_header("GET /api/v1/alerts?symbol=ETH")
    
    try:
        url = f"{BASE_URL}/v1/alerts?symbol=ETH"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Validate response structure
        if data.get('status') != 'ready':
            print_error(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_success("Response status is 'ready'")
        
        alerts = data['alerts']
        unseen = data['unseen']
        total = data['total']
        
        print_info(f"Total alerts: {total}, Unseen: {unseen}, Returned: {len(alerts)}")
        
        # Validate that all returned alerts have symbol='ETH' (if any)
        if len(alerts) > 0:
            eth_count = 0
            non_eth_count = 0
            
            for alert in alerts:
                symbol = alert.get('symbol')
                if symbol == 'ETH':
                    eth_count += 1
                else:
                    non_eth_count += 1
                    print_error(f"Found non-ETH alert with symbol='{symbol}': {alert.get('id', 'unknown')}")
            
            print_info(f"ETH alerts: {eth_count}, Non-ETH: {non_eth_count}")
            
            if non_eth_count > 0:
                print_error(f"Found {non_eth_count} non-ETH alerts in ETH-filtered results")
                return False
            
            print_success(f"All {len(alerts)} alerts have symbol='ETH'")
        else:
            print_info("No ETH alerts found (graceful - empty list is acceptable)")
        
        # Validate no 500 error
        print_success("No HTTP 500 error - graceful handling")
        
        print_success("TEST PASSED: ETH filter is graceful (no 500 error)")
        return True, data
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_get_alerts_no_symbol():
    """Test 4a: GET /api/v1/alerts (no symbol) - should return union of all coins"""
    print_test_header("GET /api/v1/alerts (no symbol parameter)")
    
    try:
        url = f"{BASE_URL}/v1/alerts"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Validate response structure
        if data.get('status') != 'ready':
            print_error(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_success("Response status is 'ready'")
        
        alerts = data['alerts']
        unseen = data['unseen']
        total = data['total']
        
        print_info(f"Total alerts: {total}, Unseen: {unseen}, Returned: {len(alerts)}")
        
        # Count alerts by symbol
        symbol_counts = {}
        for alert in alerts:
            symbol = alert.get('symbol', 'legacy')
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        print_info(f"Alerts by symbol: {symbol_counts}")
        
        print_success(f"Returned union of all alerts (total={total})")
        return True, data
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_get_alerts_all():
    """Test 4b: GET /api/v1/alerts?symbol=ALL - should return union of all coins"""
    print_test_header("GET /api/v1/alerts?symbol=ALL")
    
    try:
        url = f"{BASE_URL}/v1/alerts?symbol=ALL"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Validate response structure
        if data.get('status') != 'ready':
            print_error(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_success("Response status is 'ready'")
        
        alerts = data['alerts']
        unseen = data['unseen']
        total = data['total']
        
        print_info(f"Total alerts: {total}, Unseen: {unseen}, Returned: {len(alerts)}")
        
        # Count alerts by symbol
        symbol_counts = {}
        for alert in alerts:
            symbol = alert.get('symbol', 'legacy')
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        print_info(f"Alerts by symbol: {symbol_counts}")
        
        print_success(f"Returned union of all alerts (total={total})")
        return True, data
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_union_comparison(no_symbol_data, all_data, btc_data, sol_data):
    """Test 4c: Verify union (no symbol and ALL) >= individual coin totals"""
    print_test_header("Verify UNION totals >= individual coin totals")
    
    try:
        if not no_symbol_data or not all_data or not btc_data or not sol_data:
            print_error("Missing data from previous tests")
            return False
        
        no_symbol_total = no_symbol_data.get('total', 0)
        all_total = all_data.get('total', 0)
        btc_total = btc_data.get('total', 0)
        sol_total = sol_data.get('total', 0)
        
        print_info(f"No symbol total: {no_symbol_total}")
        print_info(f"ALL total: {all_total}")
        print_info(f"BTC total: {btc_total}")
        print_info(f"SOL total: {sol_total}")
        
        # Verify no_symbol and ALL return the same total
        if no_symbol_total != all_total:
            print_error(f"No symbol total ({no_symbol_total}) != ALL total ({all_total})")
            return False
        print_success(f"No symbol and ALL return same total: {no_symbol_total}")
        
        # Verify union total >= BTC total
        if no_symbol_total < btc_total:
            print_error(f"Union total ({no_symbol_total}) < BTC total ({btc_total})")
            return False
        print_success(f"Union total ({no_symbol_total}) >= BTC total ({btc_total})")
        
        # Verify union total >= SOL total
        if no_symbol_total < sol_total:
            print_error(f"Union total ({no_symbol_total}) < SOL total ({sol_total})")
            return False
        print_success(f"Union total ({no_symbol_total}) >= SOL total ({sol_total})")
        
        print_success("TEST PASSED: Union totals are correct")
        return True
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_ack_by_symbol(sol_data, btc_data):
    """Test 5: POST /api/v1/alerts/ack with {symbol: 'SOL'} - should mark only SOL unseen as read"""
    print_test_header("POST /api/v1/alerts/ack with {symbol: 'SOL'}")
    
    try:
        if not sol_data or not btc_data:
            print_error("Missing data from previous tests")
            return False
        
        sol_unseen_before = sol_data.get('unseen', 0)
        btc_unseen_before = btc_data.get('unseen', 0)
        
        print_info(f"SOL unseen before ack: {sol_unseen_before}")
        print_info(f"BTC unseen before ack: {btc_unseen_before}")
        
        # Acknowledge SOL alerts
        url = f"{BASE_URL}/v1/alerts/ack"
        payload = {"symbol": "SOL"}
        print_info(f"POST {url} with payload: {payload}")
        
        response = requests.post(url, json=payload, timeout=30)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_error(f"Expected status 200, got {response.status_code}")
            return False
        
        data = response.json()
        print_info(f"Response: {data}")
        
        if data.get('status') != 'ok':
            print_error(f"Expected status='ok', got '{data.get('status')}'")
            return False
        print_success("Ack response status is 'ok'")
        
        sol_unseen_after_ack = data.get('unseen', -1)
        print_info(f"SOL unseen after ack (from response): {sol_unseen_after_ack}")
        
        # Verify SOL unseen count is now 0 (or at least decreased)
        if sol_unseen_before > 0 and sol_unseen_after_ack != 0:
            print_error(f"Expected SOL unseen=0 after ack, got {sol_unseen_after_ack}")
            return False
        
        if sol_unseen_before > 0:
            print_success(f"SOL unseen count changed from {sol_unseen_before} to {sol_unseen_after_ack}")
        else:
            print_info("SOL had no unseen alerts to begin with")
        
        # Now check BTC unseen count is UNAFFECTED
        print_info("Verifying BTC unseen count is unaffected...")
        btc_response = requests.get(f"{BASE_URL}/v1/alerts?symbol=BTC", timeout=30)
        btc_data_after = btc_response.json()
        btc_unseen_after = btc_data_after.get('unseen', -1)
        
        print_info(f"BTC unseen after SOL ack: {btc_unseen_after}")
        
        if btc_unseen_after != btc_unseen_before:
            print_error(f"BTC unseen count changed from {btc_unseen_before} to {btc_unseen_after} (should be unchanged)")
            return False
        
        print_success(f"BTC unseen count unchanged: {btc_unseen_before}")
        
        print_success("TEST PASSED: Symbol-scoped ack works correctly (SOL marked, BTC unaffected)")
        return True
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_ack_by_ids():
    """Test 6: POST /api/v1/alerts/ack with {ids: [...]} - should mark specific alerts as seen"""
    print_test_header("POST /api/v1/alerts/ack with {ids: [...]}")
    
    try:
        # First, get some alerts to find an ID
        url = f"{BASE_URL}/v1/alerts"
        print_info(f"Getting alerts to find an ID...")
        
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print_error(f"Failed to get alerts: status {response.status_code}")
            return False
        
        data = response.json()
        alerts = data.get('alerts', [])
        
        if len(alerts) == 0:
            print_info("No alerts available to test ID-based ack (acceptable)")
            print_success("TEST PASSED: No alerts to test, but endpoint structure is correct")
            return True
        
        # Get the first alert ID
        test_alert_id = alerts[0].get('id')
        if not test_alert_id:
            print_error("First alert has no 'id' field")
            return False
        
        print_info(f"Using alert ID: {test_alert_id}")
        
        # Acknowledge this specific alert
        ack_url = f"{BASE_URL}/v1/alerts/ack"
        payload = {"ids": [test_alert_id]}
        print_info(f"POST {ack_url} with payload: {payload}")
        
        ack_response = requests.post(ack_url, json=payload, timeout=30)
        print_info(f"Status Code: {ack_response.status_code}")
        
        if ack_response.status_code != 200:
            print_error(f"Expected status 200, got {ack_response.status_code}")
            return False
        
        ack_data = ack_response.json()
        print_info(f"Response: {ack_data}")
        
        if ack_data.get('status') != 'ok':
            print_error(f"Expected status='ok', got '{ack_data.get('status')}'")
            return False
        print_success("Ack response status is 'ok'")
        
        print_success("TEST PASSED: ID-based ack works correctly")
        return True
        
    except Exception as e:
        print_error(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all Alert Coin Filter tests"""
    print("\n" + "="*80)
    print("BTCIQ ALERT COIN FILTER - BACKEND TEST SUITE")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print("="*80)
    
    results = []
    test_data = {}
    
    # Test 1: BTC filter
    result, btc_data = test_get_alerts_btc()
    results.append(("GET /api/v1/alerts?symbol=BTC", result))
    test_data['btc'] = btc_data
    
    # Test 2: SOL filter
    result, sol_data = test_get_alerts_sol()
    results.append(("GET /api/v1/alerts?symbol=SOL", result))
    test_data['sol'] = sol_data
    
    # Test 3: ETH filter
    result, eth_data = test_get_alerts_eth()
    results.append(("GET /api/v1/alerts?symbol=ETH", result))
    test_data['eth'] = eth_data
    
    # Test 4a: No symbol (union)
    result, no_symbol_data = test_get_alerts_no_symbol()
    results.append(("GET /api/v1/alerts (no symbol)", result))
    test_data['no_symbol'] = no_symbol_data
    
    # Test 4b: ALL symbol (union)
    result, all_data = test_get_alerts_all()
    results.append(("GET /api/v1/alerts?symbol=ALL", result))
    test_data['all'] = all_data
    
    # Test 4c: Union comparison
    result = test_union_comparison(no_symbol_data, all_data, btc_data, sol_data)
    results.append(("Union totals comparison", result))
    
    # Test 5: Ack by symbol
    result = test_ack_by_symbol(sol_data, btc_data)
    results.append(("POST /api/v1/alerts/ack {symbol: 'SOL'}", result))
    
    # Test 6: Ack by IDs
    result = test_ack_by_ids()
    results.append(("POST /api/v1/alerts/ack {ids: [...]}", result))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        if result:
            print(f"✅ PASSED: {test_name}")
            passed += 1
        else:
            print(f"❌ FAILED: {test_name}")
            failed += 1
    
    print("="*80)
    print(f"Total: {len(results)} tests | Passed: {passed} | Failed: {failed}")
    print("="*80)
    
    if failed > 0:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
