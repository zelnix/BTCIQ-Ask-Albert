#!/usr/bin/env python3
"""
Backend API Test Suite for Albert Insight and Compare Coins endpoints
Tests via external base URL with /api prefix (not localhost)
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv('/app/.env')

BASE_URL = os.environ.get('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api/v1"

def test_albert_insight():
    """Test Albert insight endpoint with mode and refresh parameters"""
    print("\n" + "="*80)
    print("A) TESTING ALBERT INSIGHT ENDPOINT")
    print("="*80)
    
    results = []
    
    # Test 1: section=overview&mode=plain (first call, should not be cached)
    print("\n[Test 1] GET /api/v1/albert/insight?section=overview&mode=plain")
    try:
        start = time.time()
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'overview', 'mode': 'plain'}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 1: overview plain', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            print(f"  Response keys: {list(data.keys())}")
            print(f"  status: {data.get('status')}")
            print(f"  mode: {data.get('mode')}")
            print(f"  cached: {data.get('cached')}")
            
            text = data.get('text', '')
            word_count = len(text.split())
            first_50_chars = text[:50] if text else ''
            print(f"  text length: {len(text)} chars, {word_count} words")
            print(f"  First 50 chars: '{first_50_chars}'")
            
            # Check for greeting at start
            greeting_words = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            has_greeting = any(text.lower().startswith(g) for g in greeting_words)
            
            # Check if complete (ends with sentence punctuation)
            is_complete = text.rstrip()[-1:] in '.!?")'
            
            issues = []
            if data.get('status') != 'ready':
                issues.append(f"status is '{data.get('status')}' not 'ready'")
            if data.get('mode') != 'plain':
                issues.append(f"mode is '{data.get('mode')}' not 'plain'")
            if word_count < 80:
                issues.append(f"text too short ({word_count} words, expected 80-150)")
            if has_greeting:
                issues.append(f"text starts with greeting: '{first_50_chars}'")
            if not is_complete:
                issues.append(f"text appears truncated (doesn't end with punctuation)")
            
            if issues:
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 1: overview plain', False, '; '.join(issues)))
            else:
                print(f"  ✅ PASSED: status=ready, mode=plain, {word_count} words, complete, no greeting")
                results.append(('Test 1: overview plain', True, f"{word_count} words, complete"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 1: overview plain', False, str(e)))
    
    # Test 2: Same call again (should be cached)
    print("\n[Test 2] Same call again (should be cached)")
    try:
        time.sleep(1)  # Brief pause
        start = time.time()
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'overview', 'mode': 'plain'}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 2: cached call', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            cached = data.get('cached')
            print(f"  cached: {cached}")
            
            if cached is True:
                print(f"  ✅ PASSED: cached=true, fast response ({latency:.2f}s)")
                results.append(('Test 2: cached call', True, f"cached=true, {latency:.2f}s"))
            else:
                print(f"  ❌ FAILED: cached={cached}, expected true")
                results.append(('Test 2: cached call', False, f"cached={cached}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 2: cached call', False, str(e)))
    
    # Test 3: section=overview&mode=technical (separate cache)
    print("\n[Test 3] GET /api/v1/albert/insight?section=overview&mode=technical")
    try:
        start = time.time()
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'overview', 'mode': 'technical'}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 3: overview technical', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            text = data.get('text', '')
            word_count = len(text.split())
            first_50_chars = text[:50] if text else ''
            print(f"  status: {data.get('status')}")
            print(f"  mode: {data.get('mode')}")
            print(f"  text length: {len(text)} chars, {word_count} words")
            print(f"  First 50 chars: '{first_50_chars}'")
            
            greeting_words = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            has_greeting = any(text.lower().startswith(g) for g in greeting_words)
            is_complete = text.rstrip()[-1:] in '.!?")'
            
            issues = []
            if data.get('status') != 'ready':
                issues.append(f"status is '{data.get('status')}' not 'ready'")
            if data.get('mode') != 'technical':
                issues.append(f"mode is '{data.get('mode')}' not 'technical'")
            if word_count < 90:
                issues.append(f"text too short ({word_count} words, expected 90-150)")
            if has_greeting:
                issues.append(f"text starts with greeting: '{first_50_chars}'")
            if not is_complete:
                issues.append(f"text appears truncated")
            
            if issues:
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 3: overview technical', False, '; '.join(issues)))
            else:
                print(f"  ✅ PASSED: status=ready, mode=technical, {word_count} words, complete, no greeting")
                results.append(('Test 3: overview technical', True, f"{word_count} words, complete"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 3: overview technical', False, str(e)))
    
    # Test 4: section=performance&mode=plain and &mode=technical
    print("\n[Test 4] GET /api/v1/albert/insight?section=performance&mode=plain")
    try:
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'performance', 'mode': 'plain'}, timeout=30)
        print(f"  Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 4a: performance plain', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            text = data.get('text', '')
            word_count = len(text.split())
            first_50_chars = text[:50] if text else ''
            print(f"  status: {data.get('status')}, mode: {data.get('mode')}, words: {word_count}")
            print(f"  First 50 chars: '{first_50_chars}'")
            
            greeting_words = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            has_greeting = any(text.lower().startswith(g) for g in greeting_words)
            is_complete = text.rstrip()[-1:] in '.!?")'
            
            if data.get('status') == 'ready' and not has_greeting and is_complete and word_count >= 80:
                print(f"  ✅ PASSED: performance plain - complete, no greeting")
                results.append(('Test 4a: performance plain', True, f"{word_count} words"))
            else:
                issues = []
                if data.get('status') != 'ready':
                    issues.append(f"status={data.get('status')}")
                if has_greeting:
                    issues.append("has greeting")
                if not is_complete:
                    issues.append("truncated")
                if word_count < 80:
                    issues.append(f"only {word_count} words")
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 4a: performance plain', False, '; '.join(issues)))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 4a: performance plain', False, str(e)))
    
    print("\n[Test 4b] GET /api/v1/albert/insight?section=performance&mode=technical")
    try:
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'performance', 'mode': 'technical'}, timeout=30)
        print(f"  Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 4b: performance technical', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            text = data.get('text', '')
            word_count = len(text.split())
            first_50_chars = text[:50] if text else ''
            print(f"  status: {data.get('status')}, mode: {data.get('mode')}, words: {word_count}")
            print(f"  First 50 chars: '{first_50_chars}'")
            
            greeting_words = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            has_greeting = any(text.lower().startswith(g) for g in greeting_words)
            is_complete = text.rstrip()[-1:] in '.!?")'
            
            if data.get('status') == 'ready' and not has_greeting and is_complete and word_count >= 90:
                print(f"  ✅ PASSED: performance technical - complete, no greeting")
                results.append(('Test 4b: performance technical', True, f"{word_count} words"))
            else:
                issues = []
                if data.get('status') != 'ready':
                    issues.append(f"status={data.get('status')}")
                if has_greeting:
                    issues.append("has greeting")
                if not is_complete:
                    issues.append("truncated")
                if word_count < 90:
                    issues.append(f"only {word_count} words")
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 4b: performance technical', False, '; '.join(issues)))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 4b: performance technical', False, str(e)))
    
    # Test 5: refresh=1 (regenerates)
    print("\n[Test 5] GET /api/v1/albert/insight?section=overview&mode=plain&refresh=1")
    try:
        start = time.time()
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'overview', 'mode': 'plain', 'refresh': 1}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 5: refresh=1', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            cached = data.get('cached')
            text = data.get('text', '')
            word_count = len(text.split())
            first_50_chars = text[:50] if text else ''
            print(f"  cached: {cached}")
            print(f"  text length: {len(text)} chars, {word_count} words")
            print(f"  First 50 chars: '{first_50_chars}'")
            
            greeting_words = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            has_greeting = any(text.lower().startswith(g) for g in greeting_words)
            is_complete = text.rstrip()[-1:] in '.!?")'
            
            issues = []
            if cached is not False:
                issues.append(f"cached={cached}, expected false")
            if has_greeting:
                issues.append("has greeting")
            if not is_complete:
                issues.append("truncated")
            if word_count < 80:
                issues.append(f"only {word_count} words")
            
            if issues:
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 5: refresh=1', False, '; '.join(issues)))
            else:
                print(f"  ✅ PASSED: cached=false (regenerated), complete, no greeting")
                results.append(('Test 5: refresh=1', True, f"regenerated, {word_count} words"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 5: refresh=1', False, str(e)))
    
    # Test 6: No 500s check (already covered above, but let's verify one more edge case)
    print("\n[Test 6] Edge case: unknown section (should not 500)")
    try:
        r = requests.get(f"{API_BASE}/albert/insight", params={'section': 'unknown_section_xyz', 'mode': 'plain'}, timeout=30)
        print(f"  Status: {r.status_code}")
        
        if r.status_code == 500:
            print(f"  ❌ FAILED: Got 500 error")
            results.append(('Test 6: no 500s', False, "Got 500 on unknown section"))
        else:
            print(f"  ✅ PASSED: No 500 error (status={r.status_code})")
            results.append(('Test 6: no 500s', True, f"status={r.status_code}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 6: no 500s', False, str(e)))
    
    return results


def test_compare_coins():
    """Test Compare Coins endpoints"""
    print("\n" + "="*80)
    print("B) TESTING COMPARE COINS ENDPOINTS")
    print("="*80)
    
    results = []
    
    # Test 7: GET /api/v1/compare/coins (list)
    print("\n[Test 7] GET /api/v1/compare/coins")
    try:
        r = requests.get(f"{API_BASE}/compare/coins", timeout=15)
        print(f"  Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 7: list coins', False, f"HTTP {r.status_code}"))
        else:
            data = r.json()
            coins = data.get('coins', [])
            print(f"  coins: {coins}")
            
            symbols = [c.get('symbol') for c in coins]
            expected = ['BTC', 'ETH', 'SOL']
            
            if set(symbols) >= set(expected):
                print(f"  ✅ PASSED: Found BTC, ETH, SOL")
                results.append(('Test 7: list coins', True, f"Found {len(coins)} coins"))
            else:
                print(f"  ❌ FAILED: Missing coins. Expected {expected}, got {symbols}")
                results.append(('Test 7: list coins', False, f"Missing coins: {set(expected) - set(symbols)}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 7: list coins', False, str(e)))
    
    # Test 8: GET /api/v1/compare/coin?symbol=BTC (first call, may take ~6s)
    print("\n[Test 8] GET /api/v1/compare/coin?symbol=BTC (first call)")
    try:
        start = time.time()
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'BTC'}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 8: BTC first call', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            print(f"  status: {resp.get('status')}")
            print(f"  cached: {resp.get('cached')}")
            
            data = resp.get('data', {})
            required_fields = ['symbol', 'name', 'price', 'day_change_pct', 'quant_score', 'quant_label', 
                             'regime', 'forecast_24h', 'forecast_7d', 'bullish', 'risk', 
                             'support', 'resistance', 'spark', 'as_of']
            
            issues = []
            if resp.get('status') != 'ready':
                issues.append(f"status={resp.get('status')}")
            
            for field in required_fields:
                if field not in data:
                    issues.append(f"missing field: {field}")
            
            price = data.get('price')
            if not isinstance(price, (int, float)) or price <= 0:
                issues.append(f"price={price} (not numeric >0)")
            
            spark = data.get('spark', [])
            if not isinstance(spark, list) or len(spark) != 60:
                issues.append(f"spark length={len(spark)} (expected 60)")
            
            quant_score = data.get('quant_score')
            if not isinstance(quant_score, int) or not (0 <= quant_score <= 100):
                issues.append(f"quant_score={quant_score} (not 0-100)")
            
            print(f"  Data fields: symbol={data.get('symbol')}, price={price}, quant_score={quant_score}, spark_len={len(spark)}")
            
            if issues:
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 8: BTC first call', False, '; '.join(issues)))
            else:
                print(f"  ✅ PASSED: All required fields present, price={price}, spark has 60 points")
                results.append(('Test 8: BTC first call', True, f"price={price}, {latency:.2f}s"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 8: BTC first call', False, str(e)))
    
    # Test 9: Same call again (should be cached)
    print("\n[Test 9] Same BTC call again (should be cached)")
    try:
        time.sleep(1)
        start = time.time()
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'BTC'}, timeout=15)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 9: BTC cached', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            cached = resp.get('cached')
            print(f"  cached: {cached}")
            
            if cached is True:
                print(f"  ✅ PASSED: cached=true, fast response ({latency:.2f}s)")
                results.append(('Test 9: BTC cached', True, f"cached=true, {latency:.2f}s"))
            else:
                print(f"  ❌ FAILED: cached={cached}, expected true")
                results.append(('Test 9: BTC cached', False, f"cached={cached}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 9: BTC cached', False, str(e)))
    
    # Test 10: ETH and SOL
    print("\n[Test 10a] GET /api/v1/compare/coin?symbol=ETH")
    try:
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'ETH'}, timeout=30)
        print(f"  Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 10a: ETH', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            data = resp.get('data', {})
            price = data.get('price')
            spark = data.get('spark', [])
            
            print(f"  status: {resp.get('status')}, price: {price}, spark_len: {len(spark)}")
            
            if resp.get('status') == 'ready' and isinstance(price, (int, float)) and price > 0 and len(spark) == 60:
                print(f"  ✅ PASSED: ETH ready with numeric price and 60-point spark")
                results.append(('Test 10a: ETH', True, f"price={price}"))
            else:
                issues = []
                if resp.get('status') != 'ready':
                    issues.append(f"status={resp.get('status')}")
                if not isinstance(price, (int, float)) or price <= 0:
                    issues.append(f"price={price}")
                if len(spark) != 60:
                    issues.append(f"spark_len={len(spark)}")
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 10a: ETH', False, '; '.join(issues)))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 10a: ETH', False, str(e)))
    
    print("\n[Test 10b] GET /api/v1/compare/coin?symbol=SOL")
    try:
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'SOL'}, timeout=30)
        print(f"  Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 10b: SOL', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            data = resp.get('data', {})
            price = data.get('price')
            spark = data.get('spark', [])
            
            print(f"  status: {resp.get('status')}, price: {price}, spark_len: {len(spark)}")
            
            if resp.get('status') == 'ready' and isinstance(price, (int, float)) and price > 0 and len(spark) == 60:
                print(f"  ✅ PASSED: SOL ready with numeric price and 60-point spark")
                results.append(('Test 10b: SOL', True, f"price={price}"))
            else:
                issues = []
                if resp.get('status') != 'ready':
                    issues.append(f"status={resp.get('status')}")
                if not isinstance(price, (int, float)) or price <= 0:
                    issues.append(f"price={price}")
                if len(spark) != 60:
                    issues.append(f"spark_len={len(spark)}")
                print(f"  ❌ FAILED: {'; '.join(issues)}")
                results.append(('Test 10b: SOL', False, '; '.join(issues)))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 10b: SOL', False, str(e)))
    
    # Test 11: Unsupported symbol (DOGE)
    print("\n[Test 11] GET /api/v1/compare/coin?symbol=DOGE (unsupported)")
    try:
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'DOGE'}, timeout=15)
        print(f"  Status: {r.status_code}")
        
        if r.status_code == 500:
            print(f"  ❌ FAILED: Got 500 error (should return 200 with error status)")
            results.append(('Test 11: DOGE unsupported', False, "Got 500 instead of error status"))
        elif r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 11: DOGE unsupported', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            status = resp.get('status')
            reason = resp.get('reason')
            print(f"  status: {status}, reason: {reason}")
            
            if status == 'error' and reason == 'unsupported_symbol':
                print(f"  ✅ PASSED: Returns error status with unsupported_symbol reason (not 500)")
                results.append(('Test 11: DOGE unsupported', True, "error status returned"))
            else:
                print(f"  ❌ FAILED: status={status}, reason={reason} (expected status='error', reason='unsupported_symbol')")
                results.append(('Test 11: DOGE unsupported', False, f"status={status}, reason={reason}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 11: DOGE unsupported', False, str(e)))
    
    # Test 12: refresh=1 (recomputes)
    print("\n[Test 12] GET /api/v1/compare/coin?symbol=BTC&refresh=1")
    try:
        start = time.time()
        r = requests.get(f"{API_BASE}/compare/coin", params={'symbol': 'BTC', 'refresh': 1}, timeout=30)
        latency = time.time() - start
        print(f"  Status: {r.status_code}")
        print(f"  Latency: {latency:.2f}s")
        
        if r.status_code != 200:
            print(f"  ❌ FAILED: Expected 200, got {r.status_code}")
            results.append(('Test 12: BTC refresh=1', False, f"HTTP {r.status_code}"))
        else:
            resp = r.json()
            cached = resp.get('cached')
            print(f"  cached: {cached}")
            
            if cached is False:
                print(f"  ✅ PASSED: cached=false (recomputed)")
                results.append(('Test 12: BTC refresh=1', True, f"recomputed, {latency:.2f}s"))
            else:
                print(f"  ❌ FAILED: cached={cached}, expected false")
                results.append(('Test 12: BTC refresh=1', False, f"cached={cached}"))
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        results.append(('Test 12: BTC refresh=1', False, str(e)))
    
    return results


def main():
    print("\n" + "="*80)
    print("BACKEND API TEST SUITE")
    print(f"Testing against: {API_BASE}")
    print("="*80)
    
    all_results = []
    
    # Run Albert Insight tests
    albert_results = test_albert_insight()
    all_results.extend(albert_results)
    
    # Run Compare Coins tests
    compare_results = test_compare_coins()
    all_results.extend(compare_results)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in all_results if success)
    failed = sum(1 for _, success, _ in all_results if not success)
    total = len(all_results)
    
    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    
    if failed > 0:
        print("\nFailed tests:")
        for name, success, detail in all_results:
            if not success:
                print(f"  ❌ {name}: {detail}")
    
    print("\nPassed tests:")
    for name, success, detail in all_results:
        if success:
            print(f"  ✅ {name}: {detail}")
    
    print("\n" + "="*80)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
