#!/usr/bin/env python3
"""
Backend test for Native Google Sign-In (GIS ID-token) + regression tests.
Tests negative/structure paths only (cannot mint a real Google ID token).
"""
import requests
import json
import sys

# Base URL from .env NEXT_PUBLIC_BASE_URL
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_auth_config():
    """Test 1: GET /api/auth/config -> 200 {configured: true, client_id: "50938428801-..."}"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/auth/config")
    print("="*80)
    try:
        resp = requests.get(f"{BASE_URL}/auth/config", timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert data.get('configured') == True, f"Expected configured=true, got {data.get('configured')}"
        assert data.get('client_id', '').startswith('50938428801-'), f"Expected client_id starting with '50938428801-', got {data.get('client_id')}"
        assert data.get('client_id', '').endswith('.apps.googleusercontent.com'), f"Expected client_id ending with '.apps.googleusercontent.com', got {data.get('client_id')}"
        
        print("✅ PASSED: GET /api/auth/config returns 200 with configured=true and valid client_id")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_me_no_cookie():
    """Test 2: GET /api/auth/me with NO cookie -> 401 {detail:"Not authenticated"}"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/auth/me (no cookie)")
    print("="*80)
    try:
        resp = requests.get(f"{BASE_URL}/auth/me", timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert 'detail' in data, f"Expected 'detail' field in response"
        assert 'not authenticated' in data['detail'].lower(), f"Expected 'Not authenticated' message, got {data['detail']}"
        
        print("✅ PASSED: GET /api/auth/me (no cookie) returns 401 with 'Not authenticated'")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_me_bogus_cookie():
    """Test 3: GET /api/auth/me with bogus cookie -> 401 (Session expired / invalid)"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/auth/me (bogus cookie)")
    print("="*80)
    try:
        headers = {'Cookie': 'albert_session=doesnotexist'}
        resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert 'detail' in data, f"Expected 'detail' field in response"
        
        print("✅ PASSED: GET /api/auth/me (bogus cookie) returns 401")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_me_bogus_bearer():
    """Test 4: GET /api/auth/me with header 'Authorization: Bearer bogus' -> 401"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/auth/me (bogus Bearer token)")
    print("="*80)
    try:
        headers = {'Authorization': 'Bearer bogus'}
        resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert 'detail' in data, f"Expected 'detail' field in response"
        
        print("✅ PASSED: GET /api/auth/me (bogus Bearer token) returns 401")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_google_empty():
    """Test 5: POST /api/auth/google {} (empty) -> 400 {detail:"Missing Google credential"}"""
    print("\n" + "="*80)
    print("TEST 5: POST /api/auth/google (empty body)")
    print("="*80)
    try:
        resp = requests.post(f"{BASE_URL}/auth/google", json={}, timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert 'detail' in data, f"Expected 'detail' field in response"
        assert 'missing google credential' in data['detail'].lower(), f"Expected 'Missing Google credential' message, got {data['detail']}"
        
        print("✅ PASSED: POST /api/auth/google (empty) returns 400 with 'Missing Google credential'")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_google_bad_token():
    """Test 6: POST /api/auth/google {"credential":"bad.jwt.here"} -> 401 {detail:"Invalid Google token"}"""
    print("\n" + "="*80)
    print("TEST 6: POST /api/auth/google (bad token)")
    print("="*80)
    try:
        resp = requests.post(f"{BASE_URL}/auth/google", json={"credential": "bad.jwt.here"}, timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert 'detail' in data, f"Expected 'detail' field in response"
        assert 'invalid google token' in data['detail'].lower(), f"Expected 'Invalid Google token' message, got {data['detail']}"
        
        print("✅ PASSED: POST /api/auth/google (bad token) returns 401 with 'Invalid Google token'")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_auth_logout_no_cookie():
    """Test 7: POST /api/auth/logout (no cookie) -> 200 {ok: true}"""
    print("\n" + "="*80)
    print("TEST 7: POST /api/auth/logout (no cookie)")
    print("="*80)
    try:
        resp = requests.post(f"{BASE_URL}/auth/logout", timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validations
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert data.get('ok') == True, f"Expected ok=true, got {data.get('ok')}"
        
        print("✅ PASSED: POST /api/auth/logout (no cookie) returns 200 with ok=true")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_regression_dashboard():
    """Test 8: GET /api/v1/dashboard -> 200"""
    print("\n" + "="*80)
    print("TEST 8: GET /api/v1/dashboard (regression)")
    print("="*80)
    try:
        resp = requests.get(f"{BASE_URL}/v1/dashboard", timeout=60)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Validations
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert 'status' in data, f"Expected 'status' field in response"
        
        print("✅ PASSED: GET /api/v1/dashboard returns 200")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_regression_chat():
    """Test 9: POST /api/v1/chat -> 200 non-empty text, model 'gemini-3-flash-preview'"""
    print("\n" + "="*80)
    print("TEST 9: POST /api/v1/chat (regression)")
    print("="*80)
    try:
        payload = {
            "session_id": "auth-reg",
            "message": "One line BTC read?",
            "deep": False,
            "symbol": "BTC"
        }
        resp = requests.post(f"{BASE_URL}/v1/chat", json=payload, timeout=60)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response keys: {list(data.keys())}")
        if 'text' in data:
            print(f"Text length: {len(data['text'])} chars")
            print(f"Text preview: {data['text'][:100]}...")
        if 'model' in data:
            print(f"Model: {data['model']}")
        
        # Validations
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert 'text' in data, f"Expected 'text' field in response"
        assert len(data['text']) > 0, f"Expected non-empty text, got empty string"
        assert 'model' in data, f"Expected 'model' field in response"
        assert data['model'] == 'gemini-3-flash-preview', f"Expected model 'gemini-3-flash-preview', got {data['model']}"
        
        print("✅ PASSED: POST /api/v1/chat returns 200 with non-empty text and model 'gemini-3-flash-preview'")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def test_regression_models():
    """Test 10: GET /api/v1/settings/models -> 200 (model switcher still works)"""
    print("\n" + "="*80)
    print("TEST 10: GET /api/v1/settings/models (regression)")
    print("="*80)
    try:
        resp = requests.get(f"{BASE_URL}/v1/settings/models", timeout=30)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Validations
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert 'status' in data, f"Expected 'status' field in response"
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        print("✅ PASSED: GET /api/v1/settings/models returns 200 with status='ready'")
        return True
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def main():
    print("\n" + "="*80)
    print("NATIVE GOOGLE SIGN-IN BACKEND TEST")
    print("Testing negative/structure paths only (cannot mint real Google ID token)")
    print("Base URL: " + BASE_URL)
    print("="*80)
    
    results = []
    
    # Auth endpoint tests
    results.append(("Test 1: GET /api/auth/config", test_auth_config()))
    results.append(("Test 2: GET /api/auth/me (no cookie)", test_auth_me_no_cookie()))
    results.append(("Test 3: GET /api/auth/me (bogus cookie)", test_auth_me_bogus_cookie()))
    results.append(("Test 4: GET /api/auth/me (bogus Bearer)", test_auth_me_bogus_bearer()))
    results.append(("Test 5: POST /api/auth/google (empty)", test_auth_google_empty()))
    results.append(("Test 6: POST /api/auth/google (bad token)", test_auth_google_bad_token()))
    results.append(("Test 7: POST /api/auth/logout (no cookie)", test_auth_logout_no_cookie()))
    
    # Regression tests
    results.append(("Test 8: GET /api/v1/dashboard", test_regression_dashboard()))
    results.append(("Test 9: POST /api/v1/chat", test_regression_chat()))
    results.append(("Test 10: GET /api/v1/settings/models", test_regression_models()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
