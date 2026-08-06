#!/usr/bin/env python3
"""
Backend test for Global Coin Switch feature.
Tests BTC regression, ETH new coin flow, and error handling.
"""
import requests
import time
import sys

# Use external URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com/api/v1"

def test_btc_regression():
    """Test BTC endpoints to ensure no regression."""
    print("\n" + "="*80)
    print("TEST 1: BTC REGRESSION (CRITICAL)")
    print("="*80)
    
    # Test 1.1: GET /api/v1/dashboard (default BTC)
    print("\n[1.1] Testing GET /api/v1/dashboard (default BTC)...")
    try:
        resp = requests.get(f"{BASE_URL}/dashboard", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        print("  ✅ Status: ready")
        
        # Check pair
        assert data.get('pair') == 'BTC/USD', f"Expected pair='BTC/USD', got {data.get('pair')}"
        print("  ✅ Pair: BTC/USD")
        
        # Check BTC-only fields are PRESENT and non-null
        btc_only_fields = ['cycle', 'dominance', 'smart_money', 'institutional', 'policy', 'prediction_ledger']
        for field in btc_only_fields:
            assert field in data, f"BTC-only field '{field}' missing"
            assert data[field] is not None, f"BTC-only field '{field}' is null"
            print(f"  ✅ BTC-only field '{field}': present and non-null")
        
        # Check quant_score
        assert 'quant_score' in data, "quant_score missing"
        assert isinstance(data['quant_score'], (int, float)), "quant_score not a number"
        print(f"  ✅ quant_score: {data['quant_score']}")
        
        print("\n✅ TEST 1.1 PASSED: GET /api/v1/dashboard (default BTC)")
        
    except Exception as e:
        print(f"\n❌ TEST 1.1 FAILED: {e}")
        return False
    
    # Test 1.2: GET /api/v1/dashboard?symbol=BTC
    print("\n[1.2] Testing GET /api/v1/dashboard?symbol=BTC...")
    try:
        resp = requests.get(f"{BASE_URL}/dashboard?symbol=BTC", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        print("  ✅ Status: ready")
        
        # Check pair
        assert data.get('pair') == 'BTC/USD', f"Expected pair='BTC/USD', got {data.get('pair')}"
        print("  ✅ Pair: BTC/USD")
        
        # Check BTC-only fields are PRESENT
        btc_only_fields = ['cycle', 'dominance', 'smart_money', 'institutional', 'policy', 'prediction_ledger']
        for field in btc_only_fields:
            assert field in data, f"BTC-only field '{field}' missing"
            assert data[field] is not None, f"BTC-only field '{field}' is null"
        print("  ✅ All BTC-only fields present and non-null")
        
        print("\n✅ TEST 1.2 PASSED: GET /api/v1/dashboard?symbol=BTC")
        
    except Exception as e:
        print(f"\n❌ TEST 1.2 FAILED: {e}")
        return False
    
    # Test 1.3: GET /api/v1/ticker
    print("\n[1.3] Testing GET /api/v1/ticker (default BTC)...")
    try:
        resp = requests.get(f"{BASE_URL}/ticker", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check price is a number
        assert 'price' in data, "price field missing"
        assert isinstance(data['price'], (int, float)), "price not a number"
        assert data['price'] > 0, "price not positive"
        print(f"  ✅ Price: ${data['price']:,.2f}")
        
        print("\n✅ TEST 1.3 PASSED: GET /api/v1/ticker")
        
    except Exception as e:
        print(f"\n❌ TEST 1.3 FAILED: {e}")
        return False
    
    # Test 1.4: GET /api/v1/news
    print("\n[1.4] Testing GET /api/v1/news (default BTC)...")
    try:
        resp = requests.get(f"{BASE_URL}/news", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        print("  ✅ Status: ready")
        
        # Check cards
        assert 'cards' in data, "cards field missing"
        assert isinstance(data['cards'], list), "cards not a list"
        print(f"  ✅ Cards: {len(data['cards'])} news items")
        
        print("\n✅ TEST 1.4 PASSED: GET /api/v1/news")
        
    except Exception as e:
        print(f"\n❌ TEST 1.4 FAILED: {e}")
        return False
    
    # Test 1.5: GET /api/v1/albert/insight?section=overview&mode=plain&symbol=BTC
    print("\n[1.5] Testing GET /api/v1/albert/insight?section=overview&mode=plain&symbol=BTC...")
    try:
        resp = requests.get(f"{BASE_URL}/albert/insight?section=overview&mode=plain&symbol=BTC", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        print("  ✅ Status: ready")
        
        # Check text mentions Bitcoin
        assert 'text' in data, "text field missing"
        text = data['text'].lower()
        assert 'bitcoin' in text or 'btc' in text, "Text doesn't mention Bitcoin"
        print(f"  ✅ Text mentions Bitcoin (length: {len(data['text'])} chars)")
        
        print("\n✅ TEST 1.5 PASSED: GET /api/v1/albert/insight")
        
    except Exception as e:
        print(f"\n❌ TEST 1.5 FAILED: {e}")
        return False
    
    print("\n" + "="*80)
    print("✅ ALL BTC REGRESSION TESTS PASSED")
    print("="*80)
    return True


def test_eth_new_coin_flow():
    """Test ETH new coin flow with polling."""
    print("\n" + "="*80)
    print("TEST 2: ETH NEW COIN FLOW (POLL WITH GENEROUS TIMEOUTS)")
    print("="*80)
    
    # Test 2.1: GET /api/v1/dashboard?symbol=ETH (poll until ready)
    print("\n[2.1] Testing GET /api/v1/dashboard?symbol=ETH (polling up to 120s)...")
    try:
        max_attempts = 15  # 15 attempts * 8s = 120s
        attempt = 0
        data = None
        
        while attempt < max_attempts:
            attempt += 1
            print(f"  Attempt {attempt}/{max_attempts}...")
            resp = requests.get(f"{BASE_URL}/dashboard?symbol=ETH", timeout=30)
            print(f"  Status: {resp.status_code}")
            data = resp.json()
            
            if data.get('status') == 'ready':
                print("  ✅ Status: ready (compute complete)")
                break
            elif data.get('status') == 'computing':
                print("  ⏳ Status: computing (waiting 8s before retry)...")
                if attempt < max_attempts:
                    time.sleep(8)
            else:
                print(f"  ⚠️  Unexpected status: {data.get('status')}")
                break
        
        # Verify final status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')} after {attempt} attempts"
        print(f"\n  ✅ Dashboard ready after {attempt} attempts")
        
        # Check symbol and coin_name
        assert data.get('symbol') == 'ETH', f"Expected symbol='ETH', got {data.get('symbol')}"
        print("  ✅ Symbol: ETH")
        
        assert data.get('coin_name') == 'Ethereum', f"Expected coin_name='Ethereum', got {data.get('coin_name')}"
        print("  ✅ Coin name: Ethereum")
        
        # Check pair
        assert data.get('pair') == 'ETH/USD', f"Expected pair='ETH/USD', got {data.get('pair')}"
        print("  ✅ Pair: ETH/USD")
        
        # Check quant_score
        assert 'quant_score' in data, "quant_score missing"
        assert isinstance(data['quant_score'], (int, float)), "quant_score not a number"
        print(f"  ✅ quant_score: {data['quant_score']}")
        
        # Check regime
        assert 'regime' in data, "regime missing"
        print(f"  ✅ regime: {data['regime']}")
        
        # Check forecasts
        assert 'forecasts' in data, "forecasts missing"
        assert isinstance(data['forecasts'], list), "forecasts not a list"
        assert len(data['forecasts']) >= 1, "forecasts list empty"
        print(f"  ✅ forecasts: {len(data['forecasts'])} items")
        
        # Check performance
        assert 'performance' in data, "performance missing"
        assert isinstance(data['performance'], list), "performance not a list"
        assert len(data['performance']) >= 1, "performance list empty"
        print(f"  ✅ performance: {len(data['performance'])} items")
        
        # Check decision
        assert 'decision' in data, "decision missing"
        assert data['decision'] is not None, "decision is null"
        print("  ✅ decision: present and non-null")
        
        # Check risk
        assert 'risk' in data, "risk missing"
        assert data['risk'] is not None, "risk is null"
        print("  ✅ risk: present and non-null")
        
        # Check chart
        assert 'chart' in data, "chart missing"
        assert data['chart'] is not None, "chart is null"
        print("  ✅ chart: present and non-null")
        
        # Check BTC-only fields are null/None
        btc_only_fields = ['cycle', 'dominance', 'policy', 'smart_money', 'institutional', 
                          'event_calendar', 'prediction_ledger', 'bitmark', 'data_health']
        for field in btc_only_fields:
            assert field in data, f"BTC-only field '{field}' missing from response"
            assert data[field] is None, f"BTC-only field '{field}' should be null for ETH, got {data[field]}"
        print("  ✅ All BTC-only fields are null (as expected for ETH)")
        
        print("\n✅ TEST 2.1 PASSED: GET /api/v1/dashboard?symbol=ETH")
        
    except Exception as e:
        print(f"\n❌ TEST 2.1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2.2: GET /api/v1/ticker?symbol=ETH
    print("\n[2.2] Testing GET /api/v1/ticker?symbol=ETH...")
    try:
        resp = requests.get(f"{BASE_URL}/ticker?symbol=ETH", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check price is a number
        assert 'price' in data, "price field missing"
        assert isinstance(data['price'], (int, float)), "price not a number"
        assert data['price'] > 0, "price not positive"
        print(f"  ✅ Price: ${data['price']:,.2f}")
        
        # Check symbol
        assert data.get('symbol') == 'ETH', f"Expected symbol='ETH', got {data.get('symbol')}"
        print("  ✅ Symbol: ETH")
        
        print("\n✅ TEST 2.2 PASSED: GET /api/v1/ticker?symbol=ETH")
        
    except Exception as e:
        print(f"\n❌ TEST 2.2 FAILED: {e}")
        return False
    
    # Test 2.3: GET /api/v1/news?symbol=ETH (poll until ready)
    print("\n[2.3] Testing GET /api/v1/news?symbol=ETH (polling up to 90s)...")
    try:
        max_attempts = 12  # 12 attempts * 8s = 96s
        attempt = 0
        data = None
        
        while attempt < max_attempts:
            attempt += 1
            print(f"  Attempt {attempt}/{max_attempts}...")
            resp = requests.get(f"{BASE_URL}/news?symbol=ETH", timeout=30)
            print(f"  Status: {resp.status_code}")
            data = resp.json()
            
            if data.get('status') == 'ready':
                print("  ✅ Status: ready (news compute complete)")
                break
            elif data.get('status') == 'computing':
                print("  ⏳ Status: computing (waiting 8s before retry)...")
                if attempt < max_attempts:
                    time.sleep(8)
            else:
                print(f"  ⚠️  Unexpected status: {data.get('status')}")
                break
        
        # Verify final status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')} after {attempt} attempts"
        print(f"\n  ✅ News ready after {attempt} attempts")
        
        # Check coin_name
        assert data.get('coin_name') == 'Ethereum', f"Expected coin_name='Ethereum', got {data.get('coin_name')}"
        print("  ✅ Coin name: Ethereum")
        
        # Check cards
        assert 'cards' in data, "cards field missing"
        assert isinstance(data['cards'], list), "cards not a list"
        print(f"  ✅ Cards: {len(data['cards'])} news items (may be small)")
        
        print("\n✅ TEST 2.3 PASSED: GET /api/v1/news?symbol=ETH")
        
    except Exception as e:
        print(f"\n❌ TEST 2.3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2.4: GET /api/v1/albert/insight?section=overview&mode=plain&symbol=ETH
    print("\n[2.4] Testing GET /api/v1/albert/insight?section=overview&mode=plain&symbol=ETH...")
    try:
        resp = requests.get(f"{BASE_URL}/albert/insight?section=overview&mode=plain&symbol=ETH", timeout=30)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        
        # Check status
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        print("  ✅ Status: ready")
        
        # Check text mentions Ethereum (not Bitcoin)
        assert 'text' in data, "text field missing"
        text = data['text'].lower()
        assert 'ethereum' in text or 'eth' in text, "Text doesn't mention Ethereum"
        print(f"  ✅ Text mentions Ethereum (length: {len(data['text'])} chars)")
        
        # Verify it's not framed as Bitcoin
        if 'bitcoin' in text and 'ethereum' not in text:
            print(f"  ⚠️  WARNING: Text mentions Bitcoin but not Ethereum")
        
        print("\n✅ TEST 2.4 PASSED: GET /api/v1/albert/insight?symbol=ETH")
        
    except Exception as e:
        print(f"\n❌ TEST 2.4 FAILED: {e}")
        return False
    
    print("\n" + "="*80)
    print("✅ ALL ETH NEW COIN FLOW TESTS PASSED")
    print("="*80)
    return True


def test_error_handling():
    """Test error handling for unsupported symbols."""
    print("\n" + "="*80)
    print("TEST 3: ERROR HANDLING")
    print("="*80)
    
    # Test 3.1: GET /api/v1/dashboard?symbol=FOO
    print("\n[3.1] Testing GET /api/v1/dashboard?symbol=FOO (unsupported symbol)...")
    try:
        resp = requests.get(f"{BASE_URL}/dashboard?symbol=FOO", timeout=30)
        print(f"  Status: {resp.status_code}")
        
        # Should NOT return 500
        assert resp.status_code != 500, "Server returned 500 error (should handle gracefully)"
        print("  ✅ No 500 error")
        
        data = resp.json()
        
        # Should return error status
        assert data.get('status') == 'error', f"Expected status='error', got {data.get('status')}"
        print("  ✅ Status: error (graceful error handling)")
        
        print("\n✅ TEST 3.1 PASSED: GET /api/v1/dashboard?symbol=FOO")
        
    except Exception as e:
        print(f"\n❌ TEST 3.1 FAILED: {e}")
        return False
    
    # Test 3.2: GET /api/v1/news?symbol=FOO
    print("\n[3.2] Testing GET /api/v1/news?symbol=FOO (unsupported symbol)...")
    try:
        resp = requests.get(f"{BASE_URL}/news?symbol=FOO", timeout=30)
        print(f"  Status: {resp.status_code}")
        
        # Should NOT return 500
        assert resp.status_code != 500, "Server returned 500 error (should handle gracefully)"
        print("  ✅ No 500 error")
        
        data = resp.json()
        
        # Should return error status
        assert data.get('status') == 'error', f"Expected status='error', got {data.get('status')}"
        print("  ✅ Status: error (graceful error handling)")
        
        print("\n✅ TEST 3.2 PASSED: GET /api/v1/news?symbol=FOO")
        
    except Exception as e:
        print(f"\n❌ TEST 3.2 FAILED: {e}")
        return False
    
    print("\n" + "="*80)
    print("✅ ALL ERROR HANDLING TESTS PASSED")
    print("="*80)
    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("GLOBAL COIN SWITCH BACKEND TEST SUITE")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print("="*80)
    
    results = {
        'BTC Regression': False,
        'ETH New Coin Flow': False,
        'Error Handling': False,
    }
    
    # Run tests
    results['BTC Regression'] = test_btc_regression()
    results['ETH New Coin Flow'] = test_eth_new_coin_flow()
    results['Error Handling'] = test_error_handling()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    print("="*80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("="*80)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*80)
        return 1


if __name__ == '__main__':
    sys.exit(main())
