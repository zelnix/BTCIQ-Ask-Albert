#!/usr/bin/env python3
"""
Backend Test for Alert Engine
Tests all 5 Alert Engine endpoints with proper timeout handling for slow ccxt calls.
"""
import requests
import json
import time
import sys

# Base URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

# Timeout for readings endpoints (can take 10-30s per request)
READINGS_TIMEOUT = 60

# Default timeout for other endpoints
DEFAULT_TIMEOUT = 30

def print_test(msg):
    print(f"\n{'='*80}")
    print(f"TEST: {msg}")
    print('='*80)

def print_pass(msg):
    print(f"✅ PASS: {msg}")

def print_fail(msg):
    print(f"❌ FAIL: {msg}")

def print_info(msg):
    print(f"ℹ️  INFO: {msg}")

def test_step_1_get_config():
    """
    STEP 1: GET /api/v1/alert-engine/config
    Expect 200 JSON {status:'ready', settings:{...}, coins:[...], netflow_note}
    Assert coins has 20 items (each with symbol+name)
    Assert settings contains signals, filters, volume_mult, watchlist
    """
    print_test("STEP 1: GET /api/v1/alert-engine/config")
    
    try:
        url = f"{BASE_URL}/v1/alert-engine/config"
        print_info(f"GET {url}")
        
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            print_info(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print_info(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print_fail(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_pass("status='ready'")
        
        # Check coins array
        coins = data.get('coins', [])
        if not isinstance(coins, list):
            print_fail(f"Expected coins to be a list, got {type(coins)}")
            return False
        
        if len(coins) != 20:
            print_fail(f"Expected 20 coins, got {len(coins)}")
            return False
        print_pass(f"coins has 20 items")
        
        # Check first coin structure
        if coins:
            first_coin = coins[0]
            if 'symbol' not in first_coin or 'name' not in first_coin:
                print_fail(f"Coin missing symbol or name: {first_coin}")
                return False
            print_pass(f"Each coin has symbol+name (e.g., {first_coin})")
        
        # Check settings structure
        settings = data.get('settings', {})
        if not isinstance(settings, dict):
            print_fail(f"Expected settings to be a dict, got {type(settings)}")
            return False
        
        # Check signals
        signals = settings.get('signals', {})
        required_signals = ['gmma_crossover', 'dip_buy', 'squeeze', 'rsi_exhaustion']
        for sig in required_signals:
            if sig not in signals:
                print_fail(f"Missing signal: {sig}")
                return False
        print_pass(f"settings.signals contains all required signals: {required_signals}")
        
        # Check filters
        filters = settings.get('filters', {})
        required_filters = ['volume', 'funding', 'netflow', 'fng']
        for filt in required_filters:
            if filt not in filters:
                print_fail(f"Missing filter: {filt}")
                return False
        print_pass(f"settings.filters contains all required filters: {required_filters}")
        
        # Check other settings fields
        if 'volume_mult' not in settings:
            print_fail("Missing settings.volume_mult")
            return False
        print_pass(f"settings.volume_mult = {settings['volume_mult']}")
        
        if 'watchlist' not in settings:
            print_fail("Missing settings.watchlist")
            return False
        watchlist = settings['watchlist']
        if not isinstance(watchlist, list):
            print_fail(f"Expected watchlist to be a list, got {type(watchlist)}")
            return False
        print_pass(f"settings.watchlist is an array with {len(watchlist)} items")
        
        # Check netflow_note
        if 'netflow_note' not in data:
            print_fail("Missing netflow_note")
            return False
        print_pass(f"netflow_note present")
        
        print_pass("STEP 1 PASSED - GET /api/v1/alert-engine/config returns valid structure")
        return True
        
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_step_2_post_config():
    """
    STEP 2: POST /api/v1/alert-engine/config with body 
    {"settings":{"signals":{"squeeze":false},"watchlist":["BTC","ETH","SOL"]}
    Expect 200. Then GET and confirm settings.signals.squeeze==false and watchlist has 3 items.
    """
    print_test("STEP 2: POST /api/v1/alert-engine/config (modify settings)")
    
    try:
        url = f"{BASE_URL}/v1/alert-engine/config"
        payload = {
            "settings": {
                "signals": {"squeeze": False},
                "watchlist": ["BTC", "ETH", "SOL"]
            }
        }
        
        print_info(f"POST {url}")
        print_info(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            print_info(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print_pass("POST returned 200")
        
        # Now GET to verify persistence
        print_info("Verifying persistence with GET...")
        get_response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        
        if get_response.status_code != 200:
            print_fail(f"GET after POST failed with status {get_response.status_code}")
            return False
        
        get_data = get_response.json()
        settings = get_data.get('settings', {})
        
        # Check squeeze is False
        squeeze = settings.get('signals', {}).get('squeeze')
        if squeeze is not False:
            print_fail(f"Expected settings.signals.squeeze=False, got {squeeze}")
            return False
        print_pass("settings.signals.squeeze == False (persisted)")
        
        # Check watchlist has exactly 3 items
        watchlist = settings.get('watchlist', [])
        if len(watchlist) != 3:
            print_fail(f"Expected watchlist with 3 items, got {len(watchlist)}: {watchlist}")
            return False
        print_pass(f"settings.watchlist has exactly 3 items: {watchlist}")
        
        print_pass("STEP 2 PASSED - POST config persists and GET reflects changes")
        return True
        
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_step_3_get_readings():
    """
    STEP 3: GET /api/v1/alert-engine/readings?symbol=BTC
    Expect 200 {status:'ready', readings:{...}, filters:{...}, candidates:[...]}
    Assert readings.gmma_state is one of bull/bear/mixed
    Assert readings.rsi is a number
    Assert readings.bb_width_pct is a number
    Assert filters has funding + fng_value keys
    Repeat for symbol=ETH (must also succeed)
    
    IMPORTANT: Can take 10-30s per request, use 60s timeout
    """
    print_test("STEP 3: GET /api/v1/alert-engine/readings (BTC and ETH)")
    
    symbols = ['BTC', 'ETH']
    
    for symbol in symbols:
        print_info(f"\n--- Testing symbol: {symbol} ---")
        
        try:
            url = f"{BASE_URL}/v1/alert-engine/readings?symbol={symbol}"
            print_info(f"GET {url}")
            print_info(f"⏱️  WARNING: This can take 10-30s (fetching real OHLCV via ccxt)...")
            
            start_time = time.time()
            response = requests.get(url, timeout=READINGS_TIMEOUT)
            elapsed = time.time() - start_time
            
            print_info(f"Status Code: {response.status_code} (took {elapsed:.1f}s)")
            
            if response.status_code != 200:
                print_fail(f"Expected status 200, got {response.status_code}")
                print_info(f"Response: {response.text[:500]}")
                return False
            
            data = response.json()
            
            # Check status
            if data.get('status') != 'ready':
                # Check if it's an error due to rate limiting (acceptable for altcoins)
                if data.get('status') == 'error' and 'no_data' in str(data.get('error', '')):
                    if symbol in ['BTC', 'ETH']:
                        print_fail(f"{symbol} must return valid readings (got error: {data.get('error')})")
                        return False
                    else:
                        print_info(f"Altcoin {symbol} returned error (acceptable): {data.get('error')}")
                        continue
                else:
                    print_fail(f"Expected status='ready', got '{data.get('status')}'")
                    return False
            print_pass(f"{symbol}: status='ready'")
            
            # Check readings
            readings = data.get('readings', {})
            if not isinstance(readings, dict):
                print_fail(f"{symbol}: Expected readings to be a dict, got {type(readings)}")
                return False
            
            # Check gmma_state
            gmma_state = readings.get('gmma_state')
            valid_states = ['bull', 'bear', 'mixed']
            if gmma_state not in valid_states:
                print_fail(f"{symbol}: Expected gmma_state in {valid_states}, got '{gmma_state}'")
                return False
            print_pass(f"{symbol}: readings.gmma_state = '{gmma_state}' (valid)")
            
            # Check rsi is a number
            rsi = readings.get('rsi')
            if not isinstance(rsi, (int, float)):
                print_fail(f"{symbol}: Expected rsi to be a number, got {type(rsi)}: {rsi}")
                return False
            print_pass(f"{symbol}: readings.rsi = {rsi} (numeric)")
            
            # Check bb_width_pct is a number
            bb_width_pct = readings.get('bb_width_pct')
            if not isinstance(bb_width_pct, (int, float)):
                print_fail(f"{symbol}: Expected bb_width_pct to be a number, got {type(bb_width_pct)}: {bb_width_pct}")
                return False
            print_pass(f"{symbol}: readings.bb_width_pct = {bb_width_pct} (numeric)")
            
            # Check filters
            filters = data.get('filters', {})
            if not isinstance(filters, dict):
                print_fail(f"{symbol}: Expected filters to be a dict, got {type(filters)}")
                return False
            
            # Check funding key
            if 'funding' not in filters:
                print_fail(f"{symbol}: Missing filters.funding")
                return False
            print_pass(f"{symbol}: filters.funding present")
            
            # Check fng_value key
            if 'fng_value' not in filters:
                print_fail(f"{symbol}: Missing filters.fng_value")
                return False
            print_pass(f"{symbol}: filters.fng_value present")
            
            # Check candidates
            candidates = data.get('candidates', [])
            if not isinstance(candidates, list):
                print_fail(f"{symbol}: Expected candidates to be a list, got {type(candidates)}")
                return False
            print_pass(f"{symbol}: candidates is a list (length: {len(candidates)})")
            
            print_pass(f"{symbol}: All validations passed")
            
        except requests.exceptions.Timeout:
            print_fail(f"{symbol}: Request timed out after {READINGS_TIMEOUT}s")
            return False
        except Exception as e:
            print_fail(f"{symbol}: Exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    print_pass("STEP 3 PASSED - GET readings for BTC and ETH both succeed")
    return True

def test_step_4_post_scan():
    """
    STEP 4: POST /api/v1/alert-engine/scan with body {"symbol":"BTC"}
    Expect 200 {status:'ready', scanned:["BTC"], result:{...}}
    """
    print_test("STEP 4: POST /api/v1/alert-engine/scan")
    
    try:
        url = f"{BASE_URL}/v1/alert-engine/scan"
        payload = {"symbol": "BTC"}
        
        print_info(f"POST {url}")
        print_info(f"Payload: {json.dumps(payload, indent=2)}")
        print_info(f"⏱️  WARNING: This can take 10-30s (fetching real OHLCV via ccxt)...")
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=READINGS_TIMEOUT)
        elapsed = time.time() - start_time
        
        print_info(f"Status Code: {response.status_code} (took {elapsed:.1f}s)")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            print_info(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print_info(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print_fail(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_pass("status='ready'")
        
        # Check scanned array
        scanned = data.get('scanned', [])
        if not isinstance(scanned, list):
            print_fail(f"Expected scanned to be a list, got {type(scanned)}")
            return False
        
        if 'BTC' not in scanned:
            print_fail(f"Expected 'BTC' in scanned list, got {scanned}")
            return False
        print_pass(f"scanned contains 'BTC': {scanned}")
        
        # Check result
        result = data.get('result')
        if result is None:
            print_fail("Missing result field")
            return False
        print_pass(f"result field present (type: {type(result)})")
        
        print_pass("STEP 4 PASSED - POST scan returns valid response")
        return True
        
    except requests.exceptions.Timeout:
        print_fail(f"Request timed out after {READINGS_TIMEOUT}s")
        return False
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_step_5_get_recent():
    """
    STEP 5: GET /api/v1/alert-engine/recent
    Expect 200 {status:'ready', alerts:[...]} (array may be empty; that's OK)
    """
    print_test("STEP 5: GET /api/v1/alert-engine/recent")
    
    try:
        url = f"{BASE_URL}/v1/alert-engine/recent"
        print_info(f"GET {url}")
        
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            print_info(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print_info(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print_fail(f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_pass("status='ready'")
        
        # Check alerts array
        alerts = data.get('alerts', [])
        if not isinstance(alerts, list):
            print_fail(f"Expected alerts to be a list, got {type(alerts)}")
            return False
        print_pass(f"alerts is a list (length: {len(alerts)}, empty is OK)")
        
        print_pass("STEP 5 PASSED - GET recent returns valid response")
        return True
        
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cleanup_reset_config():
    """
    CLEANUP (REQUIRED): POST /api/v1/alert-engine/config to reset defaults
    Reset to: enabled:true, all signals on, all filters on, volume_mult 1.5, 
    watchlist all 20 coins, squeeze:true
    """
    print_test("CLEANUP: Reset config to defaults")
    
    try:
        url = f"{BASE_URL}/v1/alert-engine/config"
        
        # Default settings from backend code
        payload = {
            "settings": {
                "enabled": True,
                "signals": {
                    "gmma_crossover": True,
                    "dip_buy": True,
                    "squeeze": True,
                    "rsi_exhaustion": True
                },
                "filters": {
                    "volume": True,
                    "funding": True,
                    "netflow": True,
                    "fng": True
                },
                "volume_mult": 1.5,
                "rsi_low": 30,
                "rsi_high": 80,
                "funding_threshold": 0.05,
                "greed_threshold": 78,
                "fear_threshold": 22,
                "watchlist": ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", 
                             "DOT", "LTC", "MATIC", "ATOM", "BCH", "XLM", "ETC", "UNI", 
                             "AAVE", "FIL", "NEAR", "APT"]
            }
        }
        
        print_info(f"POST {url}")
        print_info(f"Resetting to defaults...")
        
        response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        print_info(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            print_info(f"Response: {response.text[:500]}")
            return False
        
        print_pass("POST returned 200")
        
        # Verify with GET
        print_info("Verifying reset with GET...")
        get_response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        
        if get_response.status_code != 200:
            print_fail(f"GET after reset failed with status {get_response.status_code}")
            return False
        
        get_data = get_response.json()
        settings = get_data.get('settings', {})
        
        # Check squeeze is True
        squeeze = settings.get('signals', {}).get('squeeze')
        if squeeze is not True:
            print_fail(f"Expected settings.signals.squeeze=True after reset, got {squeeze}")
            return False
        print_pass("settings.signals.squeeze == True (reset confirmed)")
        
        # Check watchlist has 20 items
        watchlist = settings.get('watchlist', [])
        if len(watchlist) != 20:
            print_fail(f"Expected watchlist with 20 items after reset, got {len(watchlist)}")
            return False
        print_pass(f"settings.watchlist has 20 items (reset confirmed)")
        
        print_pass("CLEANUP PASSED - Config reset to defaults")
        return True
        
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*80)
    print("ALERT ENGINE BACKEND TEST")
    print("Testing 5 Alert Engine endpoints with proper timeout handling")
    print("="*80)
    
    results = []
    
    # Run all tests
    results.append(("STEP 1: GET config", test_step_1_get_config()))
    results.append(("STEP 2: POST config (modify)", test_step_2_post_config()))
    results.append(("STEP 3: GET readings (BTC+ETH)", test_step_3_get_readings()))
    results.append(("STEP 4: POST scan", test_step_4_post_scan()))
    results.append(("STEP 5: GET recent", test_step_5_get_recent()))
    results.append(("CLEANUP: Reset config", test_cleanup_reset_config()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
