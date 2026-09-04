#!/usr/bin/env python3
"""
Backend API Test Suite for NEW/CHANGED endpoints
Tests the 6 new tasks from the current session via the /api proxy
"""
import requests
import json
import base64
import time
import sys

# Use the external URL with /api prefix (proxied to internal :8001)
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_tts_endpoint():
    """Test 1: POST /api/v1/tts - Gemini TTS endpoint"""
    print("\n" + "="*80)
    print("TEST 1: POST /api/v1/tts - Gemini TTS endpoint")
    print("="*80)
    
    # Test 1a: Valid text request
    print("\n[1a] Testing valid text request...")
    try:
        payload = {"text": "Good morning from Albert."}
        response = requests.post(f"{BASE_URL}/v1/tts", json=payload, timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Response keys: {list(data.keys())}")
            
            # Validate response structure
            assert 'audio_base64' in data, "Missing audio_base64 field"
            assert 'mime_type' in data, "Missing mime_type field"
            assert 'cached' in data, "Missing cached field"
            
            # Validate audio_base64 is non-empty and valid base64
            audio_b64 = data['audio_base64']
            assert len(audio_b64) > 0, "audio_base64 is empty"
            try:
                audio_bytes = base64.b64decode(audio_b64)
                assert len(audio_bytes) > 0, "Decoded audio is empty"
                print(f"✅ audio_base64: non-empty ({len(audio_b64)} chars), decodes to {len(audio_bytes)} bytes")
            except Exception as e:
                print(f"❌ audio_base64 is not valid base64: {e}")
                return False
            
            # Validate mime_type
            assert data['mime_type'] == 'audio/wav', f"Expected mime_type 'audio/wav', got '{data['mime_type']}'"
            print(f"✅ mime_type: {data['mime_type']}")
            
            # Validate cached field
            assert isinstance(data['cached'], bool), "cached field is not boolean"
            print(f"✅ cached: {data['cached']} (first call, expected False)")
            
            print("✅ TEST 1a PASSED: Valid text returns 200 with non-empty audio_base64 (base64-decodable WAV)")
        else:
            print(f"❌ TEST 1a FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ TEST 1a FAILED with exception: {e}")
        return False
    
    # Test 1b: Repeat same text (should be cached)
    print("\n[1b] Testing cache (repeat same text)...")
    try:
        time.sleep(1)
        payload = {"text": "Good morning from Albert."}
        response = requests.post(f"{BASE_URL}/v1/tts", json=payload, timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert data.get('cached') == True, f"Expected cached=True, got {data.get('cached')}"
            print(f"✅ cached: {data['cached']} (second call, expected True)")
            print("✅ TEST 1b PASSED: Repeat text returns cached=True")
        else:
            print(f"❌ TEST 1b FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 1b FAILED with exception: {e}")
        return False
    
    # Test 1c: Empty text (should return 400)
    print("\n[1c] Testing empty text (should return 400)...")
    try:
        payload = {"text": ""}
        response = requests.post(f"{BASE_URL}/v1/tts", json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 400:
            print("✅ TEST 1c PASSED: Empty text returns 400")
        else:
            print(f"❌ TEST 1c FAILED: Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 1c FAILED with exception: {e}")
        return False
    
    print("\n✅ ALL TTS TESTS PASSED")
    return True


def test_albert_brief():
    """Test 2: GET /api/v1/albert/brief - Coin-specific Morning Brief"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/albert/brief - Coin-specific Morning Brief")
    print("="*80)
    
    # Test 2a: BTC brief (default)
    print("\n[2a] Testing BTC brief (default)...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/brief", timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            assert data.get('status') == 'ready', f"Expected status='ready', got '{data.get('status')}'"
            print(f"✅ status: {data['status']}")
            print("✅ TEST 2a PASSED: BTC brief returns status='ready'")
        else:
            print(f"❌ TEST 2a FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ TEST 2a FAILED with exception: {e}")
        return False
    
    # Test 2b: ETH brief (first call may be slow ~15-25s)
    print("\n[2b] Testing ETH brief (may take 15-25s on first call)...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/brief?symbol=ETH", timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            assert data.get('status') == 'ready', f"Expected status='ready', got '{data.get('status')}'"
            assert data.get('coin') == 'Ethereum', f"Expected coin='Ethereum', got '{data.get('coin')}'"
            print(f"✅ status: {data['status']}")
            print(f"✅ coin: {data['coin']}")
            
            # Check if observations mention ETH
            observations = data.get('observations', [])
            text = data.get('text', '')
            eth_mentioned = any('ETH' in str(obs).upper() or 'ETHEREUM' in str(obs).upper() for obs in observations) or 'ETH' in text.upper() or 'ETHEREUM' in text.upper()
            if eth_mentioned:
                print(f"✅ observations/text reference ETH/Ethereum")
            else:
                print(f"⚠️  observations/text do not explicitly mention ETH (may be acceptable)")
            
            print("✅ TEST 2b PASSED: ETH brief returns status='ready', coin='Ethereum'")
        else:
            print(f"❌ TEST 2b FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ TEST 2b FAILED with exception: {e}")
        return False
    
    # Test 2c: Unsupported symbol (should return error)
    print("\n[2c] Testing unsupported symbol (ZZZ)...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/brief?symbol=ZZZ", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert data.get('status') == 'error', f"Expected status='error', got '{data.get('status')}'"
            print(f"✅ status: {data['status']}")
            print("✅ TEST 2c PASSED: Unsupported symbol returns status='error'")
        else:
            print(f"❌ TEST 2c FAILED: Expected 200 with status='error', got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 2c FAILED with exception: {e}")
        return False
    
    # Test 2d: Refresh parameter (regenerates)
    print("\n[2d] Testing refresh=1 (regenerates)...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/brief?refresh=1", timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert data.get('status') == 'ready', f"Expected status='ready', got '{data.get('status')}'"
            assert data.get('cached') == False, f"Expected cached=False with refresh=1, got {data.get('cached')}"
            print(f"✅ status: {data['status']}")
            print(f"✅ cached: {data['cached']} (refresh=1, expected False)")
            print("✅ TEST 2d PASSED: refresh=1 regenerates (cached=False)")
        else:
            print(f"❌ TEST 2d FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 2d FAILED with exception: {e}")
        return False
    
    print("\n✅ ALL BRIEF TESTS PASSED")
    return True


def test_brief_watchlist():
    """Test 3: GET/POST /api/v1/albert/brief-watchlist"""
    print("\n" + "="*80)
    print("TEST 3: GET/POST /api/v1/albert/brief-watchlist")
    print("="*80)
    
    # Test 3a: GET watchlist
    print("\n[3a] Testing GET watchlist...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/brief-watchlist", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            assert 'coins' in data, "Missing 'coins' field"
            assert 'available' in data, "Missing 'available' field"
            assert 'BTC' in data['coins'], "BTC should always be in coins list"
            print(f"✅ coins: {data['coins']}")
            print(f"✅ available: {[c['symbol'] for c in data['available']]}")
            print("✅ TEST 3a PASSED: GET watchlist returns {coins, available} with BTC included")
        else:
            print(f"❌ TEST 3a FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 3a FAILED with exception: {e}")
        return False
    
    # Test 3b: POST with valid coins (BTC should be forced in)
    print("\n[3b] Testing POST with ['ETH', 'SOL'] (BTC should be forced in)...")
    try:
        payload = {"coins": ["ETH", "SOL"]}
        response = requests.post(f"{BASE_URL}/v1/albert/brief-watchlist", json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert 'BTC' in data['coins'], "BTC should be forced into coins list"
            assert 'ETH' in data['coins'], "ETH should be in coins list"
            assert 'SOL' in data['coins'], "SOL should be in coins list"
            print(f"✅ coins: {data['coins']}")
            print("✅ TEST 3b PASSED: POST saves coins with BTC forced in")
        else:
            print(f"❌ TEST 3b FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 3b FAILED with exception: {e}")
        return False
    
    # Test 3c: POST with invalid symbol (should return only BTC)
    print("\n[3c] Testing POST with ['ZZZ'] (should return only BTC)...")
    try:
        payload = {"coins": ["ZZZ"]}
        response = requests.post(f"{BASE_URL}/v1/albert/brief-watchlist", json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert data['coins'] == ['BTC'], f"Expected only ['BTC'], got {data['coins']}"
            print(f"✅ coins: {data['coins']}")
            print("✅ TEST 3c PASSED: Invalid symbol returns only BTC")
        else:
            print(f"❌ TEST 3c FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 3c FAILED with exception: {e}")
        return False
    
    # Test 3d: Reset to default ['ETH', 'SOL']
    print("\n[3d] Resetting watchlist to ['ETH', 'SOL']...")
    try:
        payload = {"coins": ["ETH", "SOL"]}
        response = requests.post(f"{BASE_URL}/v1/albert/brief-watchlist", json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Reset complete. coins: {data['coins']}")
            print("✅ TEST 3d PASSED: Watchlist reset to default")
        else:
            print(f"❌ TEST 3d FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 3d FAILED with exception: {e}")
        return False
    
    print("\n✅ ALL WATCHLIST TESTS PASSED")
    return True


def test_track_record():
    """Test 4: GET /api/v1/albert/track-record"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/v1/albert/track-record")
    print("="*80)
    
    print("\n[4] Testing track-record endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/track-record", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            # Validate required keys exist
            required_keys = ['best_call', 'worst_call', 'streak', 'longest_win_streak']
            for key in required_keys:
                assert key in data, f"Missing required key: {key}"
                print(f"✅ {key}: {data[key]} (may be null/None if no graded calls)")
            
            # Validate status
            assert data.get('status') == 'ready', f"Expected status='ready', got '{data.get('status')}'"
            print(f"✅ status: {data['status']}")
            
            print("✅ TEST 4 PASSED: track-record returns 200 with all required keys (best_call, worst_call, streak, longest_win_streak)")
        else:
            print(f"❌ TEST 4 FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ TEST 4 FAILED with exception: {e}")
        return False
    
    return True


def test_weekly_recap_history():
    """Test 5: GET /api/v1/albert/weekly-recap/history"""
    print("\n" + "="*80)
    print("TEST 5: GET /api/v1/albert/weekly-recap/history")
    print("="*80)
    
    print("\n[5] Testing weekly-recap/history endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/v1/albert/weekly-recap/history", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            # Validate required keys
            assert 'status' in data, "Missing 'status' field"
            assert 'recaps' in data, "Missing 'recaps' field"
            assert data['status'] == 'ready', f"Expected status='ready', got '{data['status']}'"
            assert isinstance(data['recaps'], list), "recaps should be a list"
            
            print(f"✅ status: {data['status']}")
            print(f"✅ recaps: list with {len(data['recaps'])} items")
            
            print("✅ TEST 5 PASSED: weekly-recap/history returns 200 with {status:'ready', recaps:[...]}")
        else:
            print(f"❌ TEST 5 FAILED: Expected 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ TEST 5 FAILED with exception: {e}")
        return False
    
    return True


def test_regression_sanity():
    """Test 6: Regression sanity checks (health, alerts)"""
    print("\n" + "="*80)
    print("TEST 6: Regression sanity checks (health, alerts)")
    print("="*80)
    
    # Test 6a: GET /api/v1/health
    print("\n[6a] Testing GET /api/v1/health...")
    try:
        response = requests.get(f"{BASE_URL}/v1/health", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {data}")
            print("✅ TEST 6a PASSED: /api/v1/health returns 200")
        else:
            print(f"❌ TEST 6a FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 6a FAILED with exception: {e}")
        return False
    
    # Test 6b: GET /api/v1/alerts
    print("\n[6b] Testing GET /api/v1/alerts...")
    try:
        response = requests.get(f"{BASE_URL}/v1/alerts", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            print("✅ TEST 6b PASSED: /api/v1/alerts returns 200")
        else:
            print(f"❌ TEST 6b FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 6b FAILED with exception: {e}")
        return False
    
    # Test 6c: GET /api/v1/alerts?limit=50
    print("\n[6c] Testing GET /api/v1/alerts?limit=50...")
    try:
        response = requests.get(f"{BASE_URL}/v1/alerts?limit=50", timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            print("✅ TEST 6c PASSED: /api/v1/alerts?limit=50 returns 200")
        else:
            print(f"❌ TEST 6c FAILED: Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TEST 6c FAILED with exception: {e}")
        return False
    
    print("\n✅ ALL REGRESSION TESTS PASSED")
    return True


def main():
    """Run all backend tests"""
    print("\n" + "="*80)
    print("BACKEND API TEST SUITE - NEW/CHANGED ENDPOINTS")
    print("Testing via external URL: " + BASE_URL)
    print("="*80)
    
    results = {
        "TTS Endpoint": test_tts_endpoint(),
        "Albert Brief": test_albert_brief(),
        "Brief Watchlist": test_brief_watchlist(),
        "Track Record": test_track_record(),
        "Weekly Recap History": test_weekly_recap_history(),
        "Regression Sanity": test_regression_sanity(),
    }
    
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED 🎉")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
