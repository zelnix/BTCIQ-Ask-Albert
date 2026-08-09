#!/usr/bin/env python3
"""
BitMarkAI Backend Regression Test (Test Sequence 11)
====================================================
Regression test after Option A refactor (config.py + security.py extraction).
Tests via external URL /api prefix. Admin passcode is now 000000.

Tests:
1) GET /api/v1/health -> HTTP 200, status='ok'
2) GET /api/v1/dashboard -> status='ready' with real data (signal, quant_score, price)
3) GET /api/v1/ticker -> HTTP 200 with numeric BTC price
4) POST /api/v1/refresh (admin gate + rate limit, passcode = 000000):
   - no body / empty body -> HTTP 401 {status:'unauthorized'}
   - {"passcode":"wrong"} -> HTTP 401
   - {"passcode":"000000"} -> HTTP 200 {status:'started'}
   - send >3 valid {"passcode":"000000"} within ~60s -> HTTP 429 {status:'rate_limited'} with numeric "retry_in"
5) POST /api/v1/chat {"session_id":"reftest","message":"hi"} -> HTTP 200 with non-empty "text"
6) Spot-check GET /api/v1/news-signals and GET /api/v1/macro-fred -> HTTP 200 with data (not 500)
"""
import sys
import time
import json
import requests

BASE_URL = "https://quant-features.preview.emergentagent.com/api"
TIMEOUT = 90  # seconds

def test_health():
    """Test 1: GET /api/v1/health -> HTTP 200, status='ok'"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/health")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/health"
        print(f"Request: GET {url}")
        resp = requests.get(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'ok':
            print(f"❌ FAILED: Expected status='ok', got {data.get('status')}")
            return False
        
        print("✅ PASSED: GET /api/v1/health returns HTTP 200 with status='ok'")
        return True
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False

def test_dashboard():
    """Test 2: GET /api/v1/dashboard -> status='ready' with real data"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/dashboard")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"Request: GET {url}")
        resp = requests.get(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            print(f"Body: {resp.text[:500]}")
            return False
        
        data = resp.json()
        status = data.get('status')
        
        # May be 'computing' briefly, retry a few times
        retries = 0
        while status == 'computing' and retries < 5:
            print(f"Status is 'computing', retrying in 3s... (attempt {retries+1}/5)")
            time.sleep(3)
            resp = requests.get(url, timeout=TIMEOUT)
            data = resp.json()
            status = data.get('status')
            retries += 1
        
        if status != 'ready':
            print(f"❌ FAILED: Expected status='ready', got {status}")
            print(f"Body: {json.dumps(data, indent=2)[:1000]}")
            return False
        
        # Validate real data fields
        signal = data.get('signal')
        quant_score = data.get('quant_score')
        last_close = data.get('last_close')
        
        if not signal:
            print(f"❌ FAILED: Missing 'signal' field")
            return False
        if quant_score is None:
            print(f"❌ FAILED: Missing 'quant_score' field")
            return False
        if not last_close or not isinstance(last_close, (int, float)):
            print(f"❌ FAILED: Missing or invalid 'last_close' (price) field")
            return False
        
        print(f"✅ PASSED: GET /api/v1/dashboard returns status='ready'")
        print(f"   - signal: {signal}")
        print(f"   - quant_score: {quant_score}")
        print(f"   - price (last_close): ${last_close:,.2f}")
        return True
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ticker():
    """Test 3: GET /api/v1/ticker -> HTTP 200 with numeric BTC price"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/v1/ticker")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/ticker"
        print(f"Request: GET {url}")
        resp = requests.get(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        price = data.get('price')
        
        if not price or not isinstance(price, (int, float)):
            print(f"❌ FAILED: Missing or invalid 'price' field")
            return False
        
        print(f"✅ PASSED: GET /api/v1/ticker returns HTTP 200 with numeric price: ${price:,.2f}")
        return True
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False

def test_refresh_auth():
    """Test 4: POST /api/v1/refresh - auth tests (no body, wrong passcode, correct passcode)"""
    print("\n" + "="*80)
    print("TEST 4: POST /api/v1/refresh - Auth Tests")
    print("="*80)
    
    url = f"{BASE_URL}/v1/refresh"
    
    # Test 4a: No body / empty body -> HTTP 401
    print("\n--- Test 4a: No body ---")
    try:
        print(f"Request: POST {url} (no body)")
        resp = requests.post(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code != 401:
            print(f"❌ FAILED: Expected HTTP 401, got {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'unauthorized':
            print(f"❌ FAILED: Expected status='unauthorized', got {data.get('status')}")
            return False
        
        print("✅ PASSED: No body returns HTTP 401 with status='unauthorized'")
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False
    
    # Test 4b: Wrong passcode -> HTTP 401
    print("\n--- Test 4b: Wrong passcode ---")
    try:
        payload = {"passcode": "wrong"}
        print(f"Request: POST {url}")
        print(f"Body: {json.dumps(payload)}")
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code != 401:
            print(f"❌ FAILED: Expected HTTP 401, got {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'unauthorized':
            print(f"❌ FAILED: Expected status='unauthorized', got {data.get('status')}")
            return False
        
        print("✅ PASSED: Wrong passcode returns HTTP 401 with status='unauthorized'")
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False
    
    # Test 4c: Correct passcode (000000) -> HTTP 200
    print("\n--- Test 4c: Correct passcode (000000) ---")
    try:
        payload = {"passcode": "000000"}
        print(f"Request: POST {url}")
        print(f"Body: {json.dumps(payload)}")
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        if data.get('status') != 'started':
            print(f"❌ FAILED: Expected status='started', got {data.get('status')}")
            return False
        
        print("✅ PASSED: Correct passcode (000000) returns HTTP 200 with status='started'")
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False
    
    return True

def test_refresh_rate_limit():
    """Test 4d: POST /api/v1/refresh - rate limit test (>3 requests within 60s)"""
    print("\n" + "="*80)
    print("TEST 4d: POST /api/v1/refresh - Rate Limit Test")
    print("="*80)
    
    url = f"{BASE_URL}/v1/refresh"
    payload = {"passcode": "000000"}
    
    print("Sending 4 valid requests with correct passcode to trigger rate limit...")
    print("(Rate limit is 3 per minute)")
    
    for i in range(4):
        try:
            print(f"\n--- Request {i+1}/4 ---")
            print(f"Request: POST {url}")
            print(f"Body: {json.dumps(payload)}")
            resp = requests.post(url, json=payload, timeout=TIMEOUT)
            print(f"Response: HTTP {resp.status_code}")
            print(f"Body: {resp.text[:500]}")
            
            if i < 3:
                # First 3 should succeed (or may already be rate-limited if previous tests ran recently)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Status: {data.get('status')}")
                elif resp.status_code == 429:
                    print("⚠️  Already rate-limited from previous requests (acceptable)")
                    # If we hit rate limit early, validate the 429 response
                    data = resp.json()
                    if data.get('status') != 'rate_limited':
                        print(f"❌ FAILED: Expected status='rate_limited', got {data.get('status')}")
                        return False
                    retry_in = data.get('retry_in')
                    if not isinstance(retry_in, (int, float)):
                        print(f"❌ FAILED: Expected numeric 'retry_in', got {retry_in}")
                        return False
                    print(f"✅ Rate limit response valid: retry_in={retry_in}s")
                    return True
            else:
                # 4th request should be rate-limited (HTTP 429)
                if resp.status_code != 429:
                    print(f"❌ FAILED: Expected HTTP 429 on 4th request, got {resp.status_code}")
                    return False
                
                data = resp.json()
                if data.get('status') != 'rate_limited':
                    print(f"❌ FAILED: Expected status='rate_limited', got {data.get('status')}")
                    return False
                
                retry_in = data.get('retry_in')
                if not isinstance(retry_in, (int, float)):
                    print(f"❌ FAILED: Expected numeric 'retry_in', got {retry_in}")
                    return False
                
                print(f"✅ PASSED: 4th request returns HTTP 429 with status='rate_limited' and retry_in={retry_in}s")
                return True
            
            time.sleep(0.5)  # Small delay between requests
        except Exception as e:
            print(f"❌ FAILED: Exception: {e}")
            return False
    
    print("❌ FAILED: Did not receive rate limit response after 4 requests")
    return False

def test_chat():
    """Test 5: POST /api/v1/chat -> HTTP 200 with non-empty text"""
    print("\n" + "="*80)
    print("TEST 5: POST /api/v1/chat")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/chat"
        payload = {"session_id": "reftest", "message": "hi"}
        print(f"Request: POST {url}")
        print(f"Body: {json.dumps(payload)}")
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            print(f"Body: {resp.text[:500]}")
            return False
        
        data = resp.json()
        text = data.get('text')
        
        if not text or not isinstance(text, str) or len(text) == 0:
            print(f"❌ FAILED: Missing or empty 'text' field")
            print(f"Body: {json.dumps(data, indent=2)[:1000]}")
            return False
        
        print(f"✅ PASSED: POST /api/v1/chat returns HTTP 200 with non-empty text")
        print(f"   - text length: {len(text)} chars")
        print(f"   - text preview: {text[:200]}...")
        return True
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_news_signals():
    """Test 6a: GET /api/v1/news-signals -> HTTP 200 with data (not 500)"""
    print("\n" + "="*80)
    print("TEST 6a: GET /api/v1/news-signals")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/news-signals"
        print(f"Request: GET {url}")
        resp = requests.get(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code == 500:
            print(f"❌ FAILED: Got HTTP 500 (internal server error)")
            return False
        
        if resp.status_code != 200:
            print(f"⚠️  WARNING: Expected HTTP 200, got {resp.status_code} (but not 500, so acceptable)")
        
        # Check if response is valid JSON
        try:
            data = resp.json()
            status = data.get('status')
            print(f"   - status: {status}")
            
            # Both 'ready' and 'unavailable' are acceptable (GDELT may be rate-limited)
            if status in ['ready', 'unavailable']:
                print(f"✅ PASSED: GET /api/v1/news-signals returns HTTP {resp.status_code} with status='{status}' (no 500)")
            else:
                print(f"⚠️  WARNING: Unexpected status '{status}', but no 500 error")
            return True
        except json.JSONDecodeError:
            print(f"❌ FAILED: Response is not valid JSON")
            return False
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False

def test_macro_fred():
    """Test 6b: GET /api/v1/macro-fred -> HTTP 200 with data (not 500)"""
    print("\n" + "="*80)
    print("TEST 6b: GET /api/v1/macro-fred")
    print("="*80)
    try:
        url = f"{BASE_URL}/v1/macro-fred"
        print(f"Request: GET {url}")
        resp = requests.get(url, timeout=TIMEOUT)
        print(f"Response: HTTP {resp.status_code}")
        print(f"Body: {resp.text[:500]}")
        
        if resp.status_code == 500:
            print(f"❌ FAILED: Got HTTP 500 (internal server error)")
            return False
        
        if resp.status_code != 200:
            print(f"⚠️  WARNING: Expected HTTP 200, got {resp.status_code} (but not 500, so acceptable)")
        
        # Check if response is valid JSON
        try:
            data = resp.json()
            status = data.get('status')
            print(f"   - status: {status}")
            
            if status == 'ready':
                series = data.get('series', [])
                print(f"   - series count: {len(series)}")
                print(f"✅ PASSED: GET /api/v1/macro-fred returns HTTP {resp.status_code} with status='ready' and {len(series)} series (no 500)")
            else:
                print(f"⚠️  WARNING: Unexpected status '{status}', but no 500 error")
            return True
        except json.JSONDecodeError:
            print(f"❌ FAILED: Response is not valid JSON")
            return False
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        return False

def main():
    print("="*80)
    print("BitMarkAI Backend Regression Test (Test Sequence 11)")
    print("Option A Refactor: config.py + security.py extraction")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Passcode: 000000")
    print(f"Timeout: {TIMEOUT}s")
    
    results = []
    
    # Run all tests
    results.append(("Health Check", test_health()))
    results.append(("Dashboard", test_dashboard()))
    results.append(("Ticker", test_ticker()))
    results.append(("Refresh Auth", test_refresh_auth()))
    results.append(("Refresh Rate Limit", test_refresh_rate_limit()))
    results.append(("Chat", test_chat()))
    results.append(("News Signals", test_news_signals()))
    results.append(("Macro FRED", test_macro_fred()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Refactor did not break any endpoints!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - Refactor may have introduced issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())
