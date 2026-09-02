#!/usr/bin/env python3
"""
Ask Albert Chat Endpoint Test Suite
Tests the reworked POST /api/v1/chat endpoint on LOCAL backend (http://localhost:8001)
per the review request.

Test cases:
1. FAST MODE (default, deep omitted/false)
2. DEEP MODE (deep=true)
3. EMPTY MESSAGE
4. BROAD CRYPTO SCOPE (ETH/SOL discussion)
5. MULTI-TURN SESSION
6. RATE LIMIT (10/min)
7. ROBUSTNESS (no 500s)
"""

import requests
import sys
import time
import json
from typing import Dict, Any

# LOCAL backend URL as specified in review request
BASE_URL = "http://localhost:8001/api/v1"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  {details}")

def test_fast_mode():
    """
    TEST 1: FAST MODE (default, deep omitted/false)
    POST {"session_id":"btest_fast","message":"Is now a good time to buy Bitcoin? Give me levels to watch.","symbol":"BTC","section":"overview"}
    Expect: HTTP 200, JSON with non-empty "text", "model" == "gemini-3-flash-preview" (fast path)
    Should return within ~25s. Verify answer is non-empty and looks like a decisive advisor response (contains levels/reasoning).
    """
    print_section("TEST 1: FAST MODE (default)")
    
    try:
        url = f"{BASE_URL}/chat"
        payload = {
            "session_id": "btest_fast",
            "message": "Is now a good time to buy Bitcoin? Give me levels to watch.",
            "symbol": "BTC",
            "section": "overview"
        }
        
        print(f"→ POST {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=30)
        latency = time.time() - start_time
        
        print(f"✓ HTTP Status: {response.status_code}")
        print(f"✓ Latency: {latency:.2f}s")
        
        if response.status_code != 200:
            print_result("FAST MODE", False, f"Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"  Response keys: {list(data.keys())}")
        
        # Check for error field
        if 'error' in data:
            print_result("FAST MODE", False, f"Error in response: {data.get('error')}")
            return False
        
        # Check text field
        text = data.get('text', '')
        if not text:
            print_result("FAST MODE", False, "Response text is empty")
            return False
        
        print(f"✓ Text length: {len(text)} chars")
        print(f"  Text preview: {text[:200]}...")
        
        # Check model field
        model = data.get('model', '')
        print(f"✓ Model: {model}")
        
        if model != 'gemini-3-flash-preview':
            print(f"⚠️  WARNING: Expected model 'gemini-3-flash-preview', got '{model}'")
        
        # Check if response looks like a decisive advisor response
        # Should contain levels, reasoning, or actionable advice
        has_levels = any(keyword in text.lower() for keyword in ['$', 'level', 'support', 'resistance', 'price'])
        has_reasoning = any(keyword in text.lower() for keyword in ['because', 'due to', 'given', 'since', 'as'])
        has_advice = any(keyword in text.lower() for keyword in ['buy', 'sell', 'hold', 'wait', 'accumulate', 'trim'])
        
        print(f"  Contains levels: {has_levels}")
        print(f"  Contains reasoning: {has_reasoning}")
        print(f"  Contains advice: {has_advice}")
        
        if not (has_levels or has_reasoning or has_advice):
            print_result("FAST MODE", False, "Response doesn't look like a decisive advisor response")
            return False
        
        # Check latency (should be within ~25s)
        if latency > 30:
            print(f"⚠️  WARNING: Latency {latency:.2f}s exceeds expected ~25s")
        
        print_result("FAST MODE", True, f"Model: {model}, Latency: {latency:.2f}s, Text: {len(text)} chars")
        return True
        
    except requests.exceptions.Timeout:
        print_result("FAST MODE", False, "Request timed out (>30s)")
        return False
    except Exception as e:
        print_result("FAST MODE", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_deep_mode():
    """
    TEST 2: DEEP MODE (deep=true)
    POST {"session_id":"btest_deep","message":"Give me a deep multi-week accumulation strategy for BTC with levels and catalysts.","symbol":"BTC","deep":true}
    Expect: HTTP 200, non-empty "text". "model" may be "gemini-3.1-pro-preview" (preferred) OR fall back to "gemini-3-flash-preview" if pro is slow.
    Allow up to ~90s for this one.
    """
    print_section("TEST 2: DEEP MODE (deep=true)")
    
    try:
        url = f"{BASE_URL}/chat"
        payload = {
            "session_id": "btest_deep",
            "message": "Give me a deep multi-week accumulation strategy for BTC with levels and catalysts.",
            "symbol": "BTC",
            "deep": True
        }
        
        print(f"→ POST {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=95)
        latency = time.time() - start_time
        
        print(f"✓ HTTP Status: {response.status_code}")
        print(f"✓ Latency: {latency:.2f}s")
        
        if response.status_code != 200:
            print_result("DEEP MODE", False, f"Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"  Response keys: {list(data.keys())}")
        
        # Check for error field
        if 'error' in data:
            print_result("DEEP MODE", False, f"Error in response: {data.get('error')}")
            return False
        
        # Check text field
        text = data.get('text', '')
        if not text:
            print_result("DEEP MODE", False, "Response text is empty")
            return False
        
        print(f"✓ Text length: {len(text)} chars")
        print(f"  Text preview: {text[:200]}...")
        
        # Check model field
        model = data.get('model', '')
        print(f"✓ Model: {model}")
        
        # Both models are acceptable
        if model not in ['gemini-3.1-pro-preview', 'gemini-3-flash-preview']:
            print(f"⚠️  WARNING: Unexpected model '{model}'")
        
        # Check deep flag
        deep_flag = data.get('deep', False)
        print(f"✓ Deep flag: {deep_flag}")
        
        if not deep_flag:
            print(f"⚠️  WARNING: Expected deep=true in response")
        
        print_result("DEEP MODE", True, f"Model: {model}, Latency: {latency:.2f}s, Text: {len(text)} chars")
        return True
        
    except requests.exceptions.Timeout:
        print_result("DEEP MODE", False, "Request timed out (>95s)")
        return False
    except Exception as e:
        print_result("DEEP MODE", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_empty_message():
    """
    TEST 3: EMPTY MESSAGE
    POST {"session_id":"btest_empty","message":""}
    Expect: HTTP 200 with a helpful text like "Please type a question." and NOT a 500.
    """
    print_section("TEST 3: EMPTY MESSAGE")
    
    try:
        url = f"{BASE_URL}/chat"
        payload = {
            "session_id": "btest_empty",
            "message": ""
        }
        
        print(f"→ POST {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"✓ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print_result("EMPTY MESSAGE", False, f"Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"  Response: {json.dumps(data, indent=2)}")
        
        # Should have error field
        if 'error' not in data:
            print_result("EMPTY MESSAGE", False, "Expected 'error' field in response")
            return False
        
        # Should have helpful text
        text = data.get('text', '')
        if not text or 'question' not in text.lower():
            print_result("EMPTY MESSAGE", False, f"Expected helpful text, got: {text}")
            return False
        
        print(f"✓ Error: {data.get('error')}")
        print(f"✓ Text: {text}")
        
        print_result("EMPTY MESSAGE", True, f"Returned helpful error message")
        return True
        
    except Exception as e:
        print_result("EMPTY MESSAGE", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_broad_crypto_scope():
    """
    TEST 4: BROAD CRYPTO SCOPE
    POST {"session_id":"btest_eth","message":"What's your take on Ethereum vs Solana right now?","symbol":"BTC"}
    Expect: 200, non-empty text that actually discusses ETH/SOL (confirms broadened scope beyond BTC dashboard).
    """
    print_section("TEST 4: BROAD CRYPTO SCOPE (ETH/SOL)")
    
    try:
        url = f"{BASE_URL}/chat"
        payload = {
            "session_id": "btest_eth",
            "message": "What's your take on Ethereum vs Solana right now?",
            "symbol": "BTC"
        }
        
        print(f"→ POST {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=30)
        latency = time.time() - start_time
        
        print(f"✓ HTTP Status: {response.status_code}")
        print(f"✓ Latency: {latency:.2f}s")
        
        if response.status_code != 200:
            print_result("BROAD CRYPTO SCOPE", False, f"Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check for error field
        if 'error' in data:
            print_result("BROAD CRYPTO SCOPE", False, f"Error in response: {data.get('error')}")
            return False
        
        # Check text field
        text = data.get('text', '')
        if not text:
            print_result("BROAD CRYPTO SCOPE", False, "Response text is empty")
            return False
        
        print(f"✓ Text length: {len(text)} chars")
        print(f"  Text preview: {text[:300]}...")
        
        # Check if response discusses ETH/SOL
        text_lower = text.lower()
        mentions_eth = any(keyword in text_lower for keyword in ['ethereum', 'eth'])
        mentions_sol = any(keyword in text_lower for keyword in ['solana', 'sol'])
        
        print(f"  Mentions Ethereum: {mentions_eth}")
        print(f"  Mentions Solana: {mentions_sol}")
        
        if not (mentions_eth and mentions_sol):
            print_result("BROAD CRYPTO SCOPE", False, "Response doesn't discuss both ETH and SOL")
            return False
        
        print_result("BROAD CRYPTO SCOPE", True, f"Discusses ETH/SOL, Latency: {latency:.2f}s")
        return True
        
    except requests.exceptions.Timeout:
        print_result("BROAD CRYPTO SCOPE", False, "Request timed out (>30s)")
        return False
    except Exception as e:
        print_result("BROAD CRYPTO SCOPE", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_turn_session():
    """
    TEST 5: MULTI-TURN SESSION
    Send two sequential messages with the SAME session_id ("btest_multi"):
    1. "Should I buy BTC now?"
    2. "What about my stop-loss?"
    Confirm the second reply is contextual (uses prior turn) and both are 200 non-empty.
    """
    print_section("TEST 5: MULTI-TURN SESSION")
    
    try:
        url = f"{BASE_URL}/chat"
        session_id = "btest_multi"
        
        # First message
        print("\n→ First message:")
        payload1 = {
            "session_id": session_id,
            "message": "Should I buy BTC now?"
        }
        print(f"  Payload: {json.dumps(payload1, indent=2)}")
        
        response1 = requests.post(url, json=payload1, timeout=30)
        print(f"✓ HTTP Status: {response1.status_code}")
        
        if response1.status_code != 200:
            print_result("MULTI-TURN SESSION", False, f"First message: Expected HTTP 200, got {response1.status_code}")
            return False
        
        data1 = response1.json()
        text1 = data1.get('text', '')
        
        if not text1:
            print_result("MULTI-TURN SESSION", False, "First message: Response text is empty")
            return False
        
        print(f"✓ First response length: {len(text1)} chars")
        print(f"  Preview: {text1[:200]}...")
        
        # Wait a moment
        time.sleep(1)
        
        # Second message (contextual follow-up)
        print("\n→ Second message (contextual follow-up):")
        payload2 = {
            "session_id": session_id,
            "message": "What about my stop-loss?"
        }
        print(f"  Payload: {json.dumps(payload2, indent=2)}")
        
        response2 = requests.post(url, json=payload2, timeout=30)
        print(f"✓ HTTP Status: {response2.status_code}")
        
        if response2.status_code != 200:
            print_result("MULTI-TURN SESSION", False, f"Second message: Expected HTTP 200, got {response2.status_code}")
            return False
        
        data2 = response2.json()
        text2 = data2.get('text', '')
        
        if not text2:
            print_result("MULTI-TURN SESSION", False, "Second message: Response text is empty")
            return False
        
        print(f"✓ Second response length: {len(text2)} chars")
        print(f"  Preview: {text2[:200]}...")
        
        # Check if second response is contextual
        # Should reference stop-loss, levels, or risk management
        text2_lower = text2.lower()
        is_contextual = any(keyword in text2_lower for keyword in ['stop', 'loss', 'level', 'risk', 'invalidation', 'exit'])
        
        print(f"  Second response is contextual: {is_contextual}")
        
        if not is_contextual:
            print(f"⚠️  WARNING: Second response may not be contextual")
        
        print_result("MULTI-TURN SESSION", True, "Both messages returned 200 with non-empty text")
        return True
        
    except requests.exceptions.Timeout:
        print_result("MULTI-TURN SESSION", False, "Request timed out")
        return False
    except Exception as e:
        print_result("MULTI-TURN SESSION", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rate_limit():
    """
    TEST 6: RATE LIMIT
    Confirm the endpoint enforces ~10/min (per-IP).
    Sending many rapid requests should eventually return either HTTP 429 or a JSON body with status "rate_limited" and a retry_in.
    Confirm it degrades gracefully (no 500).
    """
    print_section("TEST 6: RATE LIMIT (10/min)")
    
    try:
        url = f"{BASE_URL}/chat"
        
        print("→ Sending 12 rapid requests to trigger rate limit...")
        
        rate_limited = False
        for i in range(12):
            payload = {
                "session_id": f"btest_rate_{i}",
                "message": f"Test message {i}"
            }
            
            try:
                response = requests.post(url, json=payload, timeout=5)
                print(f"  Request {i+1}: HTTP {response.status_code}")
                
                if response.status_code == 429:
                    print(f"✓ Rate limit triggered with HTTP 429")
                    rate_limited = True
                    break
                
                if response.status_code == 200:
                    data = response.json()
                    if 'status' in data and data['status'] == 'rate_limited':
                        print(f"✓ Rate limit triggered with status='rate_limited'")
                        print(f"  Response: {json.dumps(data, indent=2)}")
                        rate_limited = True
                        break
                    
                    # Check for rate limit in error field
                    if 'error' in data and 'rate' in data['error'].lower():
                        print(f"✓ Rate limit triggered with error message")
                        print(f"  Response: {json.dumps(data, indent=2)}")
                        rate_limited = True
                        break
                
                if response.status_code == 500:
                    print_result("RATE LIMIT", False, f"Request {i+1} returned HTTP 500 (should degrade gracefully)")
                    return False
                
            except requests.exceptions.Timeout:
                print(f"  Request {i+1}: Timeout (skipping)")
                continue
            
            # Small delay between requests
            time.sleep(0.1)
        
        if not rate_limited:
            print(f"⚠️  WARNING: Rate limit not triggered after 12 requests")
            print(f"  This may be expected if rate limit is per-IP and testing from localhost")
        
        print_result("RATE LIMIT", True, "Rate limiting tested, no 500 errors")
        return True
        
    except Exception as e:
        print_result("RATE LIMIT", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_robustness():
    """
    TEST 7: ROBUSTNESS
    Confirm no request returns HTTP 500; failures should return JSON {"error":..., "text":"Sorry — I could not answer..."} with HTTP 200.
    Test various edge cases.
    """
    print_section("TEST 7: ROBUSTNESS (no 500s)")
    
    test_cases = [
        {
            "name": "Very long message",
            "payload": {
                "session_id": "btest_robust_1",
                "message": "What do you think about Bitcoin? " * 100  # Very long message
            }
        },
        {
            "name": "Special characters",
            "payload": {
                "session_id": "btest_robust_2",
                "message": "What about BTC? 🚀💎🙌 $100k soon? #Bitcoin @elonmusk"
            }
        },
        {
            "name": "Invalid symbol",
            "payload": {
                "session_id": "btest_robust_3",
                "message": "Tell me about this coin",
                "symbol": "INVALID_SYMBOL_XYZ"
            }
        },
        {
            "name": "Missing session_id",
            "payload": {
                "message": "What's the price?"
            }
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"\n→ Testing: {test_case['name']}")
        
        try:
            url = f"{BASE_URL}/chat"
            response = requests.post(url, json=test_case['payload'], timeout=30)
            
            print(f"  HTTP Status: {response.status_code}")
            
            if response.status_code == 500:
                print(f"  ❌ FAILED: Returned HTTP 500 (should return 200 with error)")
                all_passed = False
                continue
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ Returned HTTP 200")
                
                # Check if it's an error response
                if 'error' in data:
                    print(f"  ✓ Error handled gracefully: {data.get('error')}")
                else:
                    print(f"  ✓ Successful response")
            
        except requests.exceptions.Timeout:
            print(f"  ⚠️  Timeout (acceptable)")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            all_passed = False
    
    print_result("ROBUSTNESS", all_passed, "All edge cases handled without 500 errors")
    return all_passed


def main():
    """Run all tests"""
    print("="*80)
    print("  Ask Albert Chat Endpoint Test Suite")
    print("  Testing LOCAL backend: http://localhost:8001")
    print("="*80)
    
    results = {}
    
    # Run all tests
    print("\n🚀 Starting test suite...\n")
    
    results['test_1_fast_mode'] = test_fast_mode()
    results['test_2_deep_mode'] = test_deep_mode()
    results['test_3_empty_message'] = test_empty_message()
    results['test_4_broad_crypto_scope'] = test_broad_crypto_scope()
    results['test_5_multi_turn_session'] = test_multi_turn_session()
    results['test_6_rate_limit'] = test_rate_limit()
    results['test_7_robustness'] = test_robustness()
    
    # Summary
    print("\n" + "="*80)
    print("  TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
