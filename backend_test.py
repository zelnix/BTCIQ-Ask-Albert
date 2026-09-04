#!/usr/bin/env python3
"""
Backend API Test Suite - Model Switcher + Albert Knows the Engines
Tests via external /api proxy with ~60s timeouts
"""
import requests
import json
import time
import sys

# Base URL from .env NEXT_PUBLIC_BASE_URL
BASE_URL = "https://quant-features.preview.emergentagent.com/api"
TIMEOUT = 60  # Allow up to 60s for LLM calls

def log_test(step, message):
    """Log test step with formatting"""
    print(f"\n{'='*80}")
    print(f"STEP {step}: {message}")
    print('='*80)

def log_pass(message):
    """Log passing validation"""
    print(f"✅ {message}")

def log_fail(message):
    """Log failing validation"""
    print(f"❌ {message}")

def log_info(message):
    """Log informational message"""
    print(f"ℹ️  {message}")

def test_model_switcher():
    """Test A: Model Switcher - GET/POST /api/v1/settings/models"""
    results = []
    
    # STEP 1: GET /api/v1/settings/models - verify structure and defaults
    log_test("A1", "GET /api/v1/settings/models - Verify structure and defaults")
    try:
        resp = requests.get(f"{BASE_URL}/v1/settings/models", timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("A1", False, f"HTTP {resp.status_code}"))
            return results
        
        data = resp.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        # Validate structure
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        log_pass("status='ready'")
        
        # Validate prefs
        prefs = data.get('prefs', {})
        assert isinstance(prefs, dict), "prefs should be a dict"
        log_pass(f"prefs: {prefs}")
        
        # Validate models
        models = data.get('models', {})
        assert models.get('flash') == 'gemini-3-flash-preview', f"Expected flash='gemini-3-flash-preview', got {models.get('flash')}"
        assert models.get('pro') == 'gemini-3.1-pro-preview', f"Expected pro='gemini-3.1-pro-preview', got {models.get('pro')}"
        log_pass(f"models: flash='{models['flash']}', pro='{models['pro']}'")
        
        # Validate features
        features = data.get('features', [])
        assert len(features) == 6, f"Expected 6 features, got {len(features)}"
        log_pass(f"features: {len(features)} items")
        
        feature_keys = [f['key'] for f in features]
        expected_keys = ['chat_standard', 'chat_deep', 'insight', 'brief', 'strategy', 'news']
        assert set(feature_keys) == set(expected_keys), f"Expected keys {expected_keys}, got {feature_keys}"
        log_pass(f"feature keys: {feature_keys}")
        
        # Validate defaults
        assert prefs.get('chat_deep') == 'pro', f"Expected chat_deep='pro', got {prefs.get('chat_deep')}"
        log_pass("chat_deep='pro' (default)")
        
        for key in ['chat_standard', 'insight', 'brief', 'strategy', 'news']:
            assert prefs.get(key) == 'flash', f"Expected {key}='flash', got {prefs.get(key)}"
        log_pass("All other features default to 'flash'")
        
        results.append(("A1", True, "GET /api/v1/settings/models structure and defaults validated"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("A1", False, str(e)))
        return results
    
    # STEP 2: POST to change insight to 'pro' and verify persistence
    log_test("A2", "POST /api/v1/settings/models - Change insight to 'pro'")
    try:
        payload = {"prefs": {"insight": "pro"}}
        resp = requests.post(f"{BASE_URL}/v1/settings/models", json=payload, timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("A2", False, f"HTTP {resp.status_code}"))
            return results
        
        data = resp.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        log_pass("POST status='ready'")
        
        # Verify GET reflects the change
        resp_get = requests.get(f"{BASE_URL}/v1/settings/models", timeout=TIMEOUT)
        data_get = resp_get.json()
        prefs_get = data_get.get('prefs', {})
        
        assert prefs_get.get('insight') == 'pro', f"Expected insight='pro' after POST, got {prefs_get.get('insight')}"
        log_pass("GET confirms insight='pro' (persisted)")
        
        results.append(("A2", True, "POST insight='pro' persisted successfully"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("A2", False, str(e)))
        return results
    
    # STEP 3: POST invalid value and verify it's ignored
    log_test("A3", "POST /api/v1/settings/models - Invalid value 'xxx' should be ignored")
    try:
        payload = {"prefs": {"insight": "xxx"}}
        resp = requests.post(f"{BASE_URL}/v1/settings/models", json=payload, timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("A3", False, f"HTTP {resp.status_code}"))
            return results
        
        data = resp.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        # Verify GET still shows insight='pro' (invalid value ignored)
        resp_get = requests.get(f"{BASE_URL}/v1/settings/models", timeout=TIMEOUT)
        data_get = resp_get.json()
        prefs_get = data_get.get('prefs', {})
        
        assert prefs_get.get('insight') == 'pro', f"Expected insight='pro' (invalid ignored), got {prefs_get.get('insight')}"
        log_pass("GET confirms insight='pro' (invalid value 'xxx' ignored)")
        
        results.append(("A3", True, "Invalid value correctly ignored"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("A3", False, str(e)))
        return results
    
    # STEP 4: RESET to defaults
    log_test("A4", "POST /api/v1/settings/models - RESET to defaults")
    try:
        payload = {
            "prefs": {
                "chat_standard": "flash",
                "chat_deep": "pro",
                "insight": "flash",
                "brief": "flash",
                "strategy": "flash",
                "news": "flash"
            }
        }
        resp = requests.post(f"{BASE_URL}/v1/settings/models", json=payload, timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("A4", False, f"HTTP {resp.status_code}"))
            return results
        
        # Verify GET confirms all defaults
        resp_get = requests.get(f"{BASE_URL}/v1/settings/models", timeout=TIMEOUT)
        data_get = resp_get.json()
        prefs_get = data_get.get('prefs', {})
        
        assert prefs_get.get('chat_deep') == 'pro', f"Expected chat_deep='pro', got {prefs_get.get('chat_deep')}"
        for key in ['chat_standard', 'insight', 'brief', 'strategy', 'news']:
            assert prefs_get.get(key) == 'flash', f"Expected {key}='flash', got {prefs_get.get(key)}"
        
        log_pass("All preferences reset to defaults")
        log_info(f"Final prefs: {prefs_get}")
        
        results.append(("A4", True, "RESET to defaults successful"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("A4", False, str(e)))
    
    return results


def test_albert_engines():
    """Test B: Albert Knows the Engines"""
    results = []
    
    # STEP 5: GET /api/v1/albert/engine-brief?symbol=BTC
    log_test("B5", "GET /api/v1/albert/engine-brief?symbol=BTC - Verify context")
    try:
        resp = requests.get(f"{BASE_URL}/v1/albert/engine-brief?symbol=BTC", timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("B5", False, f"HTTP {resp.status_code}"))
            return results
        
        data = resp.json()
        log_info(f"Response keys: {list(data.keys())}")
        
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        log_pass("status='ready'")
        
        context = data.get('context', '')
        assert isinstance(context, str), "context should be a string"
        log_pass(f"context is string (length: {len(context)} chars)")
        
        # Context should be non-empty (at minimum active strategies or recent signals)
        # Empty edge board is acceptable (warmer populates ~40s after boot + every 3h)
        if not context.strip():
            log_info("⚠️  Context is empty - this is acceptable if snapshot is cold (warmer runs ~40s after boot + every 3h)")
            log_info("Empty edge board is NOT a failure per requirements")
        else:
            log_pass(f"Context is non-empty ({len(context)} chars)")
            log_info(f"Context preview (first 500 chars):\n{context[:500]}")
            
            # Check for expected sections (optional, not required)
            if 'ALERT ENGINE' in context:
                log_pass("Context includes 'ALERT ENGINE' edge board rows")
            if 'SECTOR ROTATION' in context:
                log_pass("Context includes 'SECTOR ROTATION' data")
            if 'RECENT SIGNALS' in context:
                log_pass("Context includes 'RECENT SIGNALS'")
            if 'ACTIVE STRATEGIES' in context:
                log_pass("Context includes 'ACTIVE STRATEGIES'")
        
        results.append(("B5", True, f"engine-brief returned context ({len(context)} chars)"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("B5", False, str(e)))
        return results
    
    # STEP 6: POST /api/v1/chat asking about edge setup and sectors
    log_test("B6", "POST /api/v1/chat - Ask about best edge setup and sector rotation")
    try:
        payload = {
            "session_id": "eng-test",
            "message": "What's my best edge setup right now, and which sectors are rotating in?",
            "deep": False,
            "symbol": "BTC"
        }
        resp = requests.post(f"{BASE_URL}/v1/chat", json=payload, timeout=TIMEOUT)
        log_info(f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.1f}s)")
        
        if resp.status_code != 200:
            log_fail(f"Expected HTTP 200, got {resp.status_code}")
            results.append(("B6", False, f"HTTP {resp.status_code}"))
            return results
        
        data = resp.json()
        log_info(f"Response keys: {list(data.keys())}")
        
        text = data.get('text', '')
        assert text, "Expected non-empty text response"
        log_pass(f"Response text is non-empty ({len(text)} chars)")
        
        model = data.get('model', '')
        assert model == 'gemini-3-flash-preview', f"Expected model='gemini-3-flash-preview', got {model}"
        log_pass(f"model='{model}'")
        
        log_info(f"Response text preview (first 500 chars):\n{text[:500]}")
        
        # Check if response is appropriate based on snapshot state
        # If snapshot is warm, should name specific coin + detector + edge score + sector
        # If cold, should say engine hasn't produced a read yet (NOT fabricate)
        text_lower = text.lower()
        
        # Look for signs of warm snapshot (specific data)
        has_specific_coin = any(coin in text_lower for coin in ['btc', 'eth', 'sol', 'ada', 'dot', 'link', 'uni', 'aave'])
        has_detector = any(det in text_lower for det in ['squeeze', 'gmma', 'rsi', 'dip', 'crossover', 'overbought', 'oversold'])
        has_sector = any(sec in text_lower for sec in ['defi', 'layer', 'gaming', 'metaverse', 'sector'])
        
        if has_specific_coin or has_detector or has_sector:
            log_pass("Response includes specific data (coin/detector/sector) - snapshot appears warm")
        else:
            # Check if it's saying data isn't available yet
            if any(phrase in text_lower for phrase in ["hasn't produced", "not available", "no data", "haven't run", "not ready"]):
                log_pass("Response correctly indicates engine hasn't produced a read yet (cold snapshot)")
            else:
                log_info("⚠️  Response doesn't clearly indicate warm or cold state - review manually")
        
        results.append(("B6", True, f"Chat response received ({len(text)} chars, model={model})"))
        
    except Exception as e:
        log_fail(f"Test failed: {str(e)}")
        results.append(("B6", False, str(e)))
        return results
    
    # STEP 7: Regression tests
    log_test("B7", "Regression - POST /api/v1/chat standard + deep, GET /api/v1/albert/insight")
    try:
        # Test standard chat
        payload_std = {
            "session_id": "reg-test-std",
            "message": "Quick BTC read?",
            "deep": False,
            "symbol": "BTC"
        }
        resp_std = requests.post(f"{BASE_URL}/v1/chat", json=payload_std, timeout=TIMEOUT)
        log_info(f"Standard chat: HTTP {resp_std.status_code} ({resp_std.elapsed.total_seconds():.1f}s)")
        
        if resp_std.status_code != 200:
            log_fail(f"Standard chat: Expected HTTP 200, got {resp_std.status_code}")
            results.append(("B7-std", False, f"HTTP {resp_std.status_code}"))
        else:
            data_std = resp_std.json()
            assert data_std.get('text'), "Standard chat: Expected non-empty text"
            log_pass(f"Standard chat: 200 with non-empty text ({len(data_std.get('text', ''))} chars)")
            results.append(("B7-std", True, "Standard chat regression passed"))
        
        # Test deep chat
        payload_deep = {
            "session_id": "reg-test-deep",
            "message": "Deep dive on BTC?",
            "deep": True,
            "symbol": "BTC"
        }
        resp_deep = requests.post(f"{BASE_URL}/v1/chat", json=payload_deep, timeout=TIMEOUT)
        log_info(f"Deep chat: HTTP {resp_deep.status_code} ({resp_deep.elapsed.total_seconds():.1f}s)")
        
        if resp_deep.status_code != 200:
            log_fail(f"Deep chat: Expected HTTP 200, got {resp_deep.status_code}")
            results.append(("B7-deep", False, f"HTTP {resp_deep.status_code}"))
        else:
            data_deep = resp_deep.json()
            assert data_deep.get('text'), "Deep chat: Expected non-empty text"
            log_pass(f"Deep chat: 200 with non-empty text ({len(data_deep.get('text', ''))} chars)")
            results.append(("B7-deep", True, "Deep chat regression passed"))
        
        # Test insight endpoint (insight was reset to flash in step A4)
        resp_insight = requests.get(f"{BASE_URL}/v1/albert/insight?section=overview&refresh=1", timeout=TIMEOUT)
        log_info(f"Insight: HTTP {resp_insight.status_code} ({resp_insight.elapsed.total_seconds():.1f}s)")
        
        if resp_insight.status_code != 200:
            log_fail(f"Insight: Expected HTTP 200, got {resp_insight.status_code}")
            results.append(("B7-insight", False, f"HTTP {resp_insight.status_code}"))
        else:
            data_insight = resp_insight.json()
            assert data_insight.get('status') == 'ready', f"Insight: Expected status='ready', got {data_insight.get('status')}"
            log_pass(f"Insight: status='ready'")
            results.append(("B7-insight", True, "Insight regression passed"))
        
    except Exception as e:
        log_fail(f"Regression test failed: {str(e)}")
        results.append(("B7", False, str(e)))
    
    return results


def main():
    """Run all tests and generate summary"""
    print("\n" + "="*80)
    print("BACKEND API TEST SUITE - Model Switcher + Albert Knows the Engines")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")
    print("="*80)
    
    all_results = []
    
    # Test A: Model Switcher
    print("\n" + "="*80)
    print("TEST SUITE A: MODEL SWITCHER")
    print("="*80)
    results_a = test_model_switcher()
    all_results.extend(results_a)
    
    # Test B: Albert Knows the Engines
    print("\n" + "="*80)
    print("TEST SUITE B: ALBERT KNOWS THE ENGINES")
    print("="*80)
    results_b = test_albert_engines()
    all_results.extend(results_b)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = [r for r in all_results if r[1]]
    failed = [r for r in all_results if not r[1]]
    
    print(f"\nTotal tests: {len(all_results)}")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")
    
    if passed:
        print("\n✅ PASSED TESTS:")
        for step, _, msg in passed:
            print(f"  {step}: {msg}")
    
    if failed:
        print("\n❌ FAILED TESTS:")
        for step, _, msg in failed:
            print(f"  {step}: {msg}")
    
    print("\n" + "="*80)
    
    # Exit code
    sys.exit(0 if len(failed) == 0 else 1)


if __name__ == "__main__":
    main()
