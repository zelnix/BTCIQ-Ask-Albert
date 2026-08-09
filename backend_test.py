#!/usr/bin/env python3
"""
Backend test for Ask Albert per-screen data grounding (POST /api/v1/chat with section).
Tests 5 cases: leverage, whales, dataaudit, overview, empty message.
"""

import requests
import time
import json

BASE_URL = "https://quant-features.preview.emergentagent.com/api/v1"
TIMEOUT = 90  # LLM calls can take time

def test_chat_grounding():
    """Test Ask Albert per-screen live data grounding."""
    
    print("=" * 80)
    print("TESTING: Ask Albert per-screen data grounding (POST /api/v1/chat)")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "LEVERAGE SECTION",
            "session_id": "t1",
            "message": "What is the exact open interest, funding rate and squeeze risk right now?",
            "section": "leverage",
            "expected_keywords": ["open interest", "funding", "squeeze"],
            "anti_mock_keywords": ["no liquidation", "no heatmap", "not available", "unavailable"],
            "description": "Should mention OI/funding/squeeze numbers AND state NO liquidation/heatmap data"
        },
        {
            "name": "WHALES SECTION",
            "session_id": "t2",
            "message": "Are whales accumulating or distributing? Give exact BTC flow numbers.",
            "section": "whales",
            "expected_keywords": ["btc", "flow", "binance", "coinbase", "etf"],
            "anti_mock_keywords": [],
            "description": "Should mention net BTC flow and named entities (e.g., Binance) and/or ETF flows"
        },
        {
            "name": "DATA AUDIT SECTION",
            "session_id": "t3",
            "message": "What is the composite price, how confident are we, and what is the macro backdrop?",
            "section": "dataaudit",
            "expected_keywords": ["composite", "price", "confidence", "high", "medium", "low", "fed", "treasury", "macro"],
            "anti_mock_keywords": [],
            "description": "Should mention composite price + HIGH/MEDIUM/LOW confidence + FRED macro (Fed Funds/10Y)"
        },
        {
            "name": "OVERVIEW SECTION",
            "session_id": "t4",
            "message": "Give me the 10-second read on Bitcoin right now.",
            "section": "overview",
            "expected_keywords": [],
            "anti_mock_keywords": [],
            "description": "Non-empty general answer"
        },
        {
            "name": "EMPTY MESSAGE",
            "session_id": "t5",
            "message": "",
            "section": "overview",
            "expected_keywords": ["empty", "question"],
            "anti_mock_keywords": [],
            "description": "Should return friendly error (no 500)"
        }
    ]
    
    results = []
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(test_cases)}: {test['name']}")
        print(f"{'=' * 80}")
        print(f"Description: {test['description']}")
        print(f"Session ID: {test['session_id']}")
        print(f"Section: {test['section']}")
        print(f"Message: {test['message'][:80]}{'...' if len(test['message']) > 80 else ''}")
        
        try:
            # Make request
            url = f"{BASE_URL}/chat"
            payload = {
                "session_id": test['session_id'],
                "message": test['message'],
                "section": test['section']
            }
            
            print(f"\nSending POST {url}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            start_time = time.time()
            response = requests.post(url, json=payload, timeout=TIMEOUT)
            elapsed = time.time() - start_time
            
            print(f"Response time: {elapsed:.2f}s")
            print(f"HTTP Status: {response.status_code}")
            
            # Check HTTP 200
            if response.status_code != 200:
                print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
                print(f"Response: {response.text[:500]}")
                results.append({
                    "test": test['name'],
                    "passed": False,
                    "reason": f"HTTP {response.status_code}"
                })
                continue
            
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            # Check for error field (empty message case)
            if test['name'] == "EMPTY MESSAGE":
                if 'error' in data and data['error'] == 'empty message':
                    print(f"✅ PASSED: Empty message handled gracefully")
                    print(f"Error message: {data.get('text', '')}")
                    results.append({
                        "test": test['name'],
                        "passed": True,
                        "text_length": len(data.get('text', '')),
                        "text_preview": data.get('text', '')[:200]
                    })
                    continue
                else:
                    print(f"❌ FAILED: Expected 'error' field with 'empty message'")
                    print(f"Response: {json.dumps(data, indent=2)[:500]}")
                    results.append({
                        "test": test['name'],
                        "passed": False,
                        "reason": "Missing error field for empty message"
                    })
                    continue
            
            # Check required fields
            if 'text' not in data:
                print(f"❌ FAILED: Missing 'text' field")
                print(f"Response: {json.dumps(data, indent=2)[:500]}")
                results.append({
                    "test": test['name'],
                    "passed": False,
                    "reason": "Missing 'text' field"
                })
                continue
            
            if 'model' not in data:
                print(f"❌ FAILED: Missing 'model' field")
                results.append({
                    "test": test['name'],
                    "passed": False,
                    "reason": "Missing 'model' field"
                })
                continue
            
            text = data['text']
            model = data['model']
            text_length = len(text)
            
            print(f"\nModel: {model}")
            print(f"Text length: {text_length} chars")
            print(f"Text preview (first 200 chars): {text[:200]}")
            print(f"Text preview (last 100 chars): ...{text[-100:]}")
            
            # Check text length (>200 chars, NOT truncated to a few words)
            if text_length < 200:
                print(f"❌ FAILED: Text too short ({text_length} chars < 200 chars)")
                print(f"Full text: {text}")
                results.append({
                    "test": test['name'],
                    "passed": False,
                    "reason": f"Text too short ({text_length} chars)",
                    "text_length": text_length,
                    "text_preview": text[:200]
                })
                continue
            
            # Check for expected keywords (if any)
            text_lower = text.lower()
            found_keywords = []
            missing_keywords = []
            
            if test['expected_keywords']:
                for keyword in test['expected_keywords']:
                    if keyword.lower() in text_lower:
                        found_keywords.append(keyword)
                    else:
                        missing_keywords.append(keyword)
                
                print(f"\nKeyword check:")
                print(f"  Expected keywords: {test['expected_keywords']}")
                print(f"  Found: {found_keywords}")
                if missing_keywords:
                    print(f"  Missing: {missing_keywords}")
            
            # Check for anti-mock keywords (leverage case)
            anti_mock_found = []
            if test['anti_mock_keywords']:
                for keyword in test['anti_mock_keywords']:
                    if keyword.lower() in text_lower:
                        anti_mock_found.append(keyword)
                
                print(f"\nAnti-mock check (should mention NO liquidation/heatmap data):")
                print(f"  Anti-mock keywords: {test['anti_mock_keywords']}")
                print(f"  Found: {anti_mock_found}")
                
                if not anti_mock_found:
                    print(f"⚠️  WARNING: Expected anti-mock statement (NO liquidation/heatmap data) not found")
            
            # Determine pass/fail
            passed = True
            reason = "All checks passed"
            
            # For leverage, we need at least one anti-mock keyword
            if test['name'] == "LEVERAGE SECTION" and not anti_mock_found:
                passed = False
                reason = "Missing anti-mock statement (NO liquidation/heatmap data)"
            
            # For whales, we need at least one expected keyword
            if test['name'] == "WHALES SECTION" and not found_keywords:
                passed = False
                reason = "Missing expected keywords (BTC flow, entity names, ETF)"
            
            # For dataaudit, we need at least 2 expected keywords
            if test['name'] == "DATA AUDIT SECTION" and len(found_keywords) < 2:
                passed = False
                reason = f"Missing expected keywords (found {len(found_keywords)}/3+)"
            
            if passed:
                print(f"\n✅ PASSED: {test['name']}")
            else:
                print(f"\n❌ FAILED: {test['name']} - {reason}")
            
            results.append({
                "test": test['name'],
                "passed": passed,
                "reason": reason,
                "text_length": text_length,
                "text_preview": text[:200],
                "found_keywords": found_keywords,
                "anti_mock_found": anti_mock_found,
                "model": model,
                "elapsed": elapsed
            })
            
        except requests.exceptions.Timeout:
            print(f"❌ FAILED: Request timeout (>{TIMEOUT}s)")
            results.append({
                "test": test['name'],
                "passed": False,
                "reason": f"Timeout (>{TIMEOUT}s)"
            })
        except Exception as e:
            print(f"❌ FAILED: Exception: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "test": test['name'],
                "passed": False,
                "reason": f"Exception: {e}"
            })
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    passed_count = sum(1 for r in results if r['passed'])
    total_count = len(results)
    
    for result in results:
        status = "✅ PASSED" if result['passed'] else "❌ FAILED"
        print(f"{status}: {result['test']}")
        if not result['passed']:
            print(f"  Reason: {result['reason']}")
        else:
            if 'text_length' in result:
                print(f"  Text length: {result['text_length']} chars")
            if 'text_preview' in result:
                print(f"  Preview: {result['text_preview'][:100]}...")
            if 'found_keywords' in result and result['found_keywords']:
                print(f"  Found keywords: {result['found_keywords']}")
            if 'anti_mock_found' in result and result['anti_mock_found']:
                print(f"  Anti-mock found: {result['anti_mock_found']}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return False

if __name__ == "__main__":
    success = test_chat_grounding()
    exit(0 if success else 1)
