"""
Backend API Test Suite for Albert Voice Selection Endpoints
Tests the new voice picker endpoints as per review request.
"""
import requests
import json
import time

# Load base URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_tts_voices():
    """
    Test 1: GET /api/v1/tts/voices
    Expect HTTP 200 JSON with keys {status:'ready', default:'Charon', tts_available:true, voices:[...]}
    Assert voices is a non-empty array (should be 12), each item has 'id','name','desc'
    Assert the list of ids includes 'Charon' and 'Fenrir'
    """
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/tts/voices")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/tts/voices"
        print(f"Request: GET {url}")
        
        response = requests.get(url, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        # Validate required keys
        assert 'status' in data, "Missing 'status' key"
        assert data['status'] == 'ready', f"Expected status='ready', got {data['status']}"
        
        assert 'default' in data, "Missing 'default' key"
        assert data['default'] == 'Charon', f"Expected default='Charon', got {data['default']}"
        
        assert 'tts_available' in data, "Missing 'tts_available' key"
        assert data['tts_available'] == True, f"Expected tts_available=true, got {data['tts_available']}"
        
        assert 'voices' in data, "Missing 'voices' key"
        assert isinstance(data['voices'], list), "voices should be a list"
        assert len(data['voices']) > 0, "voices array should not be empty"
        assert len(data['voices']) == 12, f"Expected 12 voices, got {len(data['voices'])}"
        
        # Validate each voice has required fields
        for voice in data['voices']:
            assert 'id' in voice, f"Voice missing 'id': {voice}"
            assert 'name' in voice, f"Voice missing 'name': {voice}"
            assert 'desc' in voice, f"Voice missing 'desc': {voice}"
        
        # Check that Charon and Fenrir are in the list
        voice_ids = [v['id'] for v in data['voices']]
        assert 'Charon' in voice_ids, "Expected 'Charon' in voice ids"
        assert 'Fenrir' in voice_ids, "Expected 'Fenrir' in voice ids"
        
        print("✅ TEST 1 PASSED: GET /api/v1/tts/voices returns correct structure with 12 voices including Charon and Fenrir")
        return True
        
    except AssertionError as e:
        print(f"❌ TEST 1 FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 1 ERROR: {e}")
        return False


def test_get_voice_pref():
    """
    Test 2: GET /api/v1/albert/voice-pref
    Expect HTTP 200 JSON with keys {status:'ready', engine, voice, browser_voice_uri}
    """
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/albert/voice-pref")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/albert/voice-pref"
        print(f"Request: GET {url}")
        
        response = requests.get(url, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        # Validate required keys
        assert 'status' in data, "Missing 'status' key"
        assert data['status'] == 'ready', f"Expected status='ready', got {data['status']}"
        
        assert 'engine' in data, "Missing 'engine' key"
        assert 'voice' in data, "Missing 'voice' key"
        assert 'browser_voice_uri' in data, "Missing 'browser_voice_uri' key"
        
        print("✅ TEST 2 PASSED: GET /api/v1/albert/voice-pref returns correct structure")
        return True
        
    except AssertionError as e:
        print(f"❌ TEST 2 FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 2 ERROR: {e}")
        return False


def test_post_voice_pref_fenrir():
    """
    Test 3a: POST /api/v1/albert/voice-pref with body {"engine":"gemini","voice":"Fenrir"}
    Expect 200 echoing voice:"Fenrir", engine:"gemini"
    Then GET /api/v1/albert/voice-pref and confirm it now returns voice:"Fenrir"
    """
    print("\n" + "="*80)
    print("TEST 3a: POST /api/v1/albert/voice-pref with valid voice (Fenrir)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/albert/voice-pref"
        payload = {"engine": "gemini", "voice": "Fenrir"}
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        # Validate response
        assert data.get('voice') == 'Fenrir', f"Expected voice='Fenrir', got {data.get('voice')}"
        assert data.get('engine') == 'gemini', f"Expected engine='gemini', got {data.get('engine')}"
        
        # Now GET to confirm persistence
        print("\nVerifying persistence with GET...")
        get_response = requests.get(url, timeout=30)
        assert get_response.status_code == 200, f"GET failed with {get_response.status_code}"
        
        get_data = get_response.json()
        print(f"GET Response Data: {json.dumps(get_data, indent=2)}")
        
        assert get_data.get('voice') == 'Fenrir', f"Expected persisted voice='Fenrir', got {get_data.get('voice')}"
        
        print("✅ TEST 3a PASSED: POST with Fenrir persists correctly")
        return True
        
    except AssertionError as e:
        print(f"❌ TEST 3a FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 3a ERROR: {e}")
        return False


def test_post_voice_pref_invalid():
    """
    Test 3b: POST /api/v1/albert/voice-pref with body {"engine":"gemini","voice":"NotARealVoice"}
    Expect 200 and voice should have FALLEN BACK to "Charon" (invalid voice rejected)
    """
    print("\n" + "="*80)
    print("TEST 3b: POST /api/v1/albert/voice-pref with invalid voice (NotARealVoice)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/albert/voice-pref"
        payload = {"engine": "gemini", "voice": "NotARealVoice"}
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        # Validate fallback to Charon
        assert data.get('voice') == 'Charon', f"Expected fallback to voice='Charon', got {data.get('voice')}"
        
        print("✅ TEST 3b PASSED: Invalid voice correctly falls back to Charon")
        return True
        
    except AssertionError as e:
        print(f"❌ TEST 3b FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 3b ERROR: {e}")
        return False


def test_post_voice_pref_browser():
    """
    Test 3c: POST /api/v1/albert/voice-pref with body {"engine":"browser","browser_voice_uri":"com.apple.voice.x"}
    Expect 200 with engine:"browser"
    """
    print("\n" + "="*80)
    print("TEST 3c: POST /api/v1/albert/voice-pref with browser engine")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/albert/voice-pref"
        payload = {"engine": "browser", "browser_voice_uri": "com.apple.voice.x"}
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        # Validate engine is browser
        assert data.get('engine') == 'browser', f"Expected engine='browser', got {data.get('engine')}"
        
        print("✅ TEST 3c PASSED: Browser engine set correctly")
        return True
        
    except AssertionError as e:
        print(f"❌ TEST 3c FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 3c ERROR: {e}")
        return False


def test_post_tts_with_voice():
    """
    Test 4: POST /api/v1/tts with body {"text":"Hello from Albert","voice":"Puck"}
    IDEALLY 200 with non-empty audio_base64
    HOWEVER the GEMINI_API_KEY is FREE TIER, so a 429/502/503 (quota exhausted) response is ACCEPTABLE
    Only flag a real failure if it returns 500 with a code error unrelated to quota, or 400 for valid non-empty text
    """
    print("\n" + "="*80)
    print("TEST 4: POST /api/v1/tts with voice parameter (Puck)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/tts"
        payload = {"text": "Hello from Albert", "voice": "Puck"}
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=60)
        print(f"Response Status: {response.status_code}")
        
        # Acceptable status codes: 200 (success), 429/502/503 (quota/rate limit)
        acceptable_codes = [200, 429, 502, 503]
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response Data Keys: {list(data.keys())}")
            
            # Validate audio_base64 is present and non-empty
            assert 'audio_base64' in data, "Missing 'audio_base64' key"
            assert len(data['audio_base64']) > 0, "audio_base64 should not be empty"
            
            print(f"✅ TEST 4 PASSED: POST /api/v1/tts with voice='Puck' returns audio (audio_base64 length: {len(data['audio_base64'])} chars)")
            return True
            
        elif response.status_code in [429, 502, 503]:
            print(f"⚠️  TEST 4 ACCEPTABLE: Free-tier quota/rate limit hit (status {response.status_code})")
            print("This is expected behavior for free-tier Gemini API key")
            return True
            
        elif response.status_code == 400:
            # 400 for valid non-empty text is a failure
            print(f"❌ TEST 4 FAILED: Got 400 for valid non-empty text")
            return False
            
        elif response.status_code == 500:
            # 500 is a code error (not acceptable)
            print(f"❌ TEST 4 FAILED: Got 500 (code error)")
            return False
            
        else:
            print(f"❌ TEST 4 FAILED: Unexpected status code {response.status_code}")
            return False
        
    except AssertionError as e:
        print(f"❌ TEST 4 FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ TEST 4 ERROR: {e}")
        return False


def test_cleanup_reset_to_charon():
    """
    Cleanup: POST /api/v1/albert/voice-pref with {"engine":"gemini","voice":"Charon"}
    to reset the user's default to clean state
    """
    print("\n" + "="*80)
    print("CLEANUP: Reset voice preference to Charon")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/albert/voice-pref"
        payload = {"engine": "gemini", "voice": "Charon"}
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print(f"Response Data: {json.dumps(data, indent=2)}")
        
        assert data.get('voice') == 'Charon', f"Expected voice='Charon', got {data.get('voice')}"
        assert data.get('engine') == 'gemini', f"Expected engine='gemini', got {data.get('engine')}"
        
        print("✅ CLEANUP PASSED: Voice preference reset to Charon")
        return True
        
    except AssertionError as e:
        print(f"❌ CLEANUP FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ CLEANUP ERROR: {e}")
        return False


def main():
    """Run all tests in sequence"""
    print("\n" + "="*80)
    print("ALBERT VOICE SELECTION ENDPOINTS - BACKEND TEST SUITE")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    
    results = []
    
    # Test 1: GET /api/v1/tts/voices
    results.append(("GET /api/v1/tts/voices", test_tts_voices()))
    
    # Test 2: GET /api/v1/albert/voice-pref
    results.append(("GET /api/v1/albert/voice-pref", test_get_voice_pref()))
    
    # Test 3a: POST valid voice (Fenrir)
    results.append(("POST voice-pref (Fenrir)", test_post_voice_pref_fenrir()))
    
    # Test 3b: POST invalid voice (fallback to Charon)
    results.append(("POST voice-pref (invalid)", test_post_voice_pref_invalid()))
    
    # Test 3c: POST browser engine
    results.append(("POST voice-pref (browser)", test_post_voice_pref_browser()))
    
    # Test 4: POST /api/v1/tts with voice parameter
    results.append(("POST /api/v1/tts (voice=Puck)", test_post_tts_with_voice()))
    
    # Cleanup: Reset to Charon
    results.append(("CLEANUP (reset to Charon)", test_cleanup_reset_to_charon()))
    
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


if __name__ == "__main__":
    exit(main())
