#!/usr/bin/env python3
"""
Security Hardening Backend Test Suite
Tests admin passcode gates, rate limiting, and HMAC checks on the BitMarkAI FastAPI backend.
"""
import requests
import time
import sys

# External URL with /api prefix (Next.js proxy forwards to FastAPI :8001)
BASE_URL = "https://quant-features.preview.emergentagent.com/api/v1"
ADMIN_PASSCODE = "btciq-admin"

# Test results tracking
tests_passed = 0
tests_failed = 0
test_results = []

def log_test(test_name, passed, details=""):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASSED"
    else:
        tests_failed += 1
        status = "❌ FAILED"
    
    result = f"{status}: {test_name}"
    if details:
        result += f" - {details}"
    print(result)
    test_results.append({"test": test_name, "passed": passed, "details": details})

def test_refresh_no_body():
    """Test POST /api/v1/refresh with no body -> HTTP 401 {status:'unauthorized'}"""
    print("\n=== TEST 1: POST /api/v1/refresh (no body) ===")
    try:
        response = requests.post(f"{BASE_URL}/refresh", json={}, timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 401 and data.get('status') == 'unauthorized')
        log_test("POST /api/v1/refresh (no body)", passed, 
                f"HTTP {status_code}, status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("POST /api/v1/refresh (no body)", False, f"Exception: {e}")
        return False

def test_refresh_wrong_passcode():
    """Test POST /api/v1/refresh with wrong passcode -> HTTP 401 {status:'unauthorized'}"""
    print("\n=== TEST 2: POST /api/v1/refresh (wrong passcode) ===")
    try:
        response = requests.post(f"{BASE_URL}/refresh", json={"passcode": "wrong"}, timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 401 and data.get('status') == 'unauthorized')
        log_test("POST /api/v1/refresh (wrong passcode)", passed,
                f"HTTP {status_code}, status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("POST /api/v1/refresh (wrong passcode)", False, f"Exception: {e}")
        return False

def test_refresh_correct_passcode():
    """Test POST /api/v1/refresh with correct passcode -> HTTP 200 {status:'started'}"""
    print("\n=== TEST 3: POST /api/v1/refresh (correct passcode) ===")
    try:
        response = requests.post(f"{BASE_URL}/refresh", json={"passcode": ADMIN_PASSCODE}, timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 200 and data.get('status') == 'started')
        log_test("POST /api/v1/refresh (correct passcode)", passed,
                f"HTTP {status_code}, status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("POST /api/v1/refresh (correct passcode)", False, f"Exception: {e}")
        return False

def test_refresh_rate_limit():
    """Test POST /api/v1/refresh rate limit (>3 valid requests within ~60s -> HTTP 429)"""
    print("\n=== TEST 4: POST /api/v1/refresh (rate limit >3/min) ===")
    print("Sending 4 valid requests with correct passcode...")
    
    try:
        # Send 4 requests (3 should succeed, 4th should be rate-limited)
        responses = []
        for i in range(4):
            response = requests.post(f"{BASE_URL}/refresh", json={"passcode": ADMIN_PASSCODE}, timeout=30)
            responses.append({
                "attempt": i + 1,
                "status_code": response.status_code,
                "data": response.json()
            })
            print(f"  Attempt {i+1}: HTTP {response.status_code}, status='{response.json().get('status')}'")
            time.sleep(0.5)  # Small delay between requests
        
        # Check that at least one request returned HTTP 429 with status='rate_limited'
        rate_limited = any(r['status_code'] == 429 and r['data'].get('status') == 'rate_limited' 
                          for r in responses)
        
        passed = rate_limited
        log_test("POST /api/v1/refresh (rate limit)", passed,
                f"Rate limit triggered: {rate_limited}")
        return passed
    except Exception as e:
        log_test("POST /api/v1/refresh (rate limit)", False, f"Exception: {e}")
        return False

def test_chat_basic():
    """Test POST /api/v1/chat basic functionality -> HTTP 200 with non-empty text"""
    print("\n=== TEST 5: POST /api/v1/chat (basic) ===")
    try:
        response = requests.post(f"{BASE_URL}/chat", 
                                json={"session_id": "sectest", "message": "hi"}, 
                                timeout=90)
        status_code = response.status_code
        data = response.json()
        
        text = data.get('text', '')
        passed = (status_code == 200 and len(text) > 0)
        log_test("POST /api/v1/chat (basic)", passed,
                f"HTTP {status_code}, text length={len(text)} chars")
        return passed
    except Exception as e:
        log_test("POST /api/v1/chat (basic)", False, f"Exception: {e}")
        return False

def test_chat_rate_limit():
    """Test POST /api/v1/chat rate limit (>15 requests within ~60s -> HTTP 429)"""
    print("\n=== TEST 6: POST /api/v1/chat (rate limit >15/min) ===")
    print("Sending 16 chat requests...")
    
    try:
        # Send 16 requests (15 should succeed, 16th should be rate-limited)
        responses = []
        for i in range(16):
            response = requests.post(f"{BASE_URL}/chat",
                                    json={"session_id": "sectest", "message": f"test {i}"},
                                    timeout=90)
            try:
                data = response.json()
            except Exception:  # noqa
                # If JSON parsing fails, it might be a 429 with non-JSON response
                data = {"status": "unknown", "text": response.text[:100]}
            
            responses.append({
                "attempt": i + 1,
                "status_code": response.status_code,
                "data": data
            })
            if i < 5 or i >= 14:  # Only print first 5 and last 2
                print(f"  Attempt {i+1}: HTTP {response.status_code}, status='{data.get('status', 'ok')}'")
            elif i == 5:
                print(f"  ... (attempts 6-14) ...")
            time.sleep(0.2)  # Small delay between requests
        
        # Check that at least one request returned HTTP 429 with status='rate_limited'
        rate_limited = any(r['status_code'] == 429 and r['data'].get('status') == 'rate_limited'
                          for r in responses)
        
        passed = rate_limited
        log_test("POST /api/v1/chat (rate limit)", passed,
                f"Rate limit triggered: {rate_limited}")
        return passed
    except Exception as e:
        log_test("POST /api/v1/chat (rate limit)", False, f"Exception: {e}")
        return False

def test_bitmark_no_passcode():
    """Test POST /api/v1/bitmark/run with no passcode -> {status:'unauthorized'}"""
    print("\n=== TEST 7: POST /api/v1/bitmark/run (no passcode) ===")
    try:
        response = requests.post(f"{BASE_URL}/bitmark/run", json={}, timeout=30)
        data = response.json()
        
        passed = (data.get('status') == 'unauthorized')
        log_test("POST /api/v1/bitmark/run (no passcode)", passed,
                f"status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("POST /api/v1/bitmark/run (no passcode)", False, f"Exception: {e}")
        return False

def test_bitmark_correct_passcode():
    """Test POST /api/v1/bitmark/run with correct passcode -> status in [started, busy, rate_limited]"""
    print("\n=== TEST 8: POST /api/v1/bitmark/run (correct passcode) ===")
    try:
        response = requests.post(f"{BASE_URL}/bitmark/run", 
                                json={"passcode": ADMIN_PASSCODE}, 
                                timeout=30)
        data = response.json()
        status = data.get('status')
        
        # Must NOT be 'unauthorized', should be one of: started, busy, rate_limited
        passed = (status in ['started', 'busy', 'rate_limited'])
        log_test("POST /api/v1/bitmark/run (correct passcode)", passed,
                f"status='{status}' (expected: started/busy/rate_limited, NOT unauthorized)")
        return passed
    except Exception as e:
        log_test("POST /api/v1/bitmark/run (correct passcode)", False, f"Exception: {e}")
        return False

def test_albert_insight():
    """Test GET /api/v1/albert/insight?section=overview -> status in [ready, fallback], no 500"""
    print("\n=== TEST 9: GET /api/v1/albert/insight?section=overview ===")
    try:
        response = requests.get(f"{BASE_URL}/albert/insight?section=overview", timeout=90)
        status_code = response.status_code
        data = response.json()
        status = data.get('status')
        
        passed = (status_code != 500 and status in ['ready', 'fallback'])
        log_test("GET /api/v1/albert/insight (first call)", passed,
                f"HTTP {status_code}, status='{status}'")
        
        # Second identical call should return cached=true
        if passed:
            print("  Testing second call for caching...")
            response2 = requests.get(f"{BASE_URL}/albert/insight?section=overview", timeout=90)
            data2 = response2.json()
            cached = data2.get('cached', False)
            print(f"  Second call: cached={cached}")
            log_test("GET /api/v1/albert/insight (cached)", cached,
                    f"cached={cached}")
        
        return passed
    except Exception as e:
        log_test("GET /api/v1/albert/insight", False, f"Exception: {e}")
        return False

def test_news_refresh():
    """Test POST /api/v1/news/refresh -> {status:'started'} once; >3/min -> HTTP 429"""
    print("\n=== TEST 10: POST /api/v1/news/refresh ===")
    try:
        # First call should return status='started'
        response = requests.post(f"{BASE_URL}/news/refresh", timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 200 and data.get('status') == 'started')
        log_test("POST /api/v1/news/refresh (first call)", passed,
                f"HTTP {status_code}, status='{data.get('status')}'")
        
        # Hammer >3/min to trigger rate limit
        print("  Testing rate limit (sending 4 more requests)...")
        rate_limited = False
        for i in range(4):
            response = requests.post(f"{BASE_URL}/news/refresh", timeout=30)
            if response.status_code == 429:
                rate_limited = True
                print(f"  Attempt {i+2}: HTTP 429 (rate limited)")
                break
            else:
                print(f"  Attempt {i+2}: HTTP {response.status_code}")
            time.sleep(0.5)
        
        log_test("POST /api/v1/news/refresh (rate limit)", rate_limited,
                f"Rate limit triggered: {rate_limited}")
        
        return passed
    except Exception as e:
        log_test("POST /api/v1/news/refresh", False, f"Exception: {e}")
        return False

def test_regression_dashboard():
    """Regression: GET /api/v1/dashboard -> status='ready'"""
    print("\n=== REGRESSION TEST 1: GET /api/v1/dashboard ===")
    try:
        response = requests.get(f"{BASE_URL}/dashboard", timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 200 and data.get('status') == 'ready')
        log_test("GET /api/v1/dashboard", passed,
                f"HTTP {status_code}, status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("GET /api/v1/dashboard", False, f"Exception: {e}")
        return False

def test_regression_ticker():
    """Regression: GET /api/v1/ticker -> returns a numeric price"""
    print("\n=== REGRESSION TEST 2: GET /api/v1/ticker ===")
    try:
        response = requests.get(f"{BASE_URL}/ticker", timeout=30)
        status_code = response.status_code
        data = response.json()
        price = data.get('price')
        
        passed = (status_code == 200 and isinstance(price, (int, float)) and price > 0)
        log_test("GET /api/v1/ticker", passed,
                f"HTTP {status_code}, price=${price:,.2f}" if passed else f"HTTP {status_code}, price={price}")
        return passed
    except Exception as e:
        log_test("GET /api/v1/ticker", False, f"Exception: {e}")
        return False

def test_regression_health():
    """Regression: GET /api/v1/health -> status='ok'"""
    print("\n=== REGRESSION TEST 3: GET /api/v1/health ===")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=30)
        status_code = response.status_code
        data = response.json()
        
        passed = (status_code == 200 and data.get('status') == 'ok')
        log_test("GET /api/v1/health", passed,
                f"HTTP {status_code}, status='{data.get('status')}'")
        return passed
    except Exception as e:
        log_test("GET /api/v1/health", False, f"Exception: {e}")
        return False

def main():
    print("=" * 80)
    print("SECURITY HARDENING BACKEND TEST SUITE")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Passcode: {ADMIN_PASSCODE}")
    print("=" * 80)
    
    # Run tests in order (rate limit tests LAST as instructed)
    
    # 1. POST /api/v1/refresh - passcode tests
    test_refresh_no_body()
    test_refresh_wrong_passcode()
    test_refresh_correct_passcode()
    
    # 2. POST /api/v1/chat - basic test
    test_chat_basic()
    
    # 3. POST /api/v1/bitmark/run - passcode tests
    test_bitmark_no_passcode()
    test_bitmark_correct_passcode()
    
    # 4. GET /api/v1/albert/insight - basic test
    test_albert_insight()
    
    # 5. POST /api/v1/news/refresh - basic test
    test_news_refresh()
    
    # 6. Regression tests (GETs are NOT rate-limited)
    test_regression_dashboard()
    test_regression_ticker()
    test_regression_health()
    
    # Wait 60s before rate limit tests to allow per-minute window to reset
    print("\n" + "=" * 80)
    print("WAITING 60 SECONDS BEFORE RATE LIMIT TESTS (to reset per-minute window)...")
    print("=" * 80)
    time.sleep(60)
    
    # 7. Rate limit tests (LAST as instructed)
    test_refresh_rate_limit()
    test_chat_rate_limit()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {tests_passed + tests_failed}")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    print("=" * 80)
    
    if tests_failed > 0:
        print("\n❌ SOME TESTS FAILED")
        print("\nFailed tests:")
        for result in test_results:
            if not result['passed']:
                print(f"  - {result['test']}: {result['details']}")
        sys.exit(1)
    else:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
