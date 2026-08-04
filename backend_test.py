#!/usr/bin/env python3
"""
Backend API Test Suite for Bitcoin Predictive AI
Tests all FastAPI endpoints via Next.js proxy using external base URL
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv('/app/.env')

BASE_URL = os.environ.get('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')

def test_health_endpoint():
    """Test GET /api/v1/health"""
    print("\n" + "="*70)
    print("TEST 1: GET /api/v1/health")
    print("="*70)
    
    try:
        url = f"{BASE_URL}/api/v1/health"
        print(f"Calling: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected status 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        print(f"Response: {data}")
        
        # Validate required fields
        required_fields = ['status', 'compute_status', 'runs']
        missing = [f for f in required_fields if f not in data]
        if missing:
            print(f"❌ FAILED: Missing required fields: {missing}")
            return False
        
        # Validate status
        if data['status'] != 'ok':
            print(f"❌ FAILED: Expected status='ok', got '{data['status']}'")
            return False
        
        # Validate compute_status
        valid_compute_statuses = ['done', 'running', 'idle', 'error']
        if data['compute_status'] not in valid_compute_statuses:
            print(f"❌ FAILED: compute_status '{data['compute_status']}' not in {valid_compute_statuses}")
            return False
        
        # Validate runs count
        if not isinstance(data['runs'], int) or data['runs'] < 0:
            print(f"❌ FAILED: runs should be non-negative integer, got {data['runs']}")
            return False
        
        print(f"✅ PASSED: Health endpoint working correctly")
        print(f"   - status: {data['status']}")
        print(f"   - compute_status: {data['compute_status']}")
        print(f"   - runs: {data['runs']}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Request error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        return False


def test_dashboard_endpoint():
    """Test GET /api/v1/dashboard"""
    print("\n" + "="*70)
    print("TEST 2: GET /api/v1/dashboard")
    print("="*70)
    
    try:
        url = f"{BASE_URL}/api/v1/dashboard"
        print(f"Calling: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected status 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print(f"⚠️  Dashboard status: {data.get('status')}")
            if data.get('status') == 'computing':
                print("   ML model is still computing. This is expected on first run.")
                print("   Waiting 10 seconds and retrying...")
                time.sleep(10)
                return test_dashboard_endpoint()  # Retry once
            elif data.get('status') == 'error':
                print(f"❌ FAILED: Dashboard in error state: {data.get('error')}")
                return False
            else:
                print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
                return False
        
        # Validate required fields
        required_fields = [
            'signal', 'confidence', 'prob_up', 'prob_down', 'last_close',
            'data_source', 'overall_accuracy', 'cv_mean', 'cv_folds',
            'importances', 'performance', 'features'
        ]
        missing = [f for f in required_fields if f not in data]
        if missing:
            print(f"❌ FAILED: Missing required fields: {missing}")
            return False
        
        # Validate signal
        if data['signal'] not in ['UP', 'DOWN']:
            print(f"❌ FAILED: signal should be 'UP' or 'DOWN', got '{data['signal']}'")
            return False
        
        # Validate confidence (0-100)
        if not (0 <= data['confidence'] <= 100):
            print(f"❌ FAILED: confidence should be 0-100, got {data['confidence']}")
            return False
        
        # Validate prob_up and prob_down (0-100)
        if not (0 <= data['prob_up'] <= 100):
            print(f"❌ FAILED: prob_up should be 0-100, got {data['prob_up']}")
            return False
        if not (0 <= data['prob_down'] <= 100):
            print(f"❌ FAILED: prob_down should be 0-100, got {data['prob_down']}")
            return False
        
        # Validate last_close (should be positive real BTC price)
        if data['last_close'] <= 0:
            print(f"❌ FAILED: last_close should be > 0, got {data['last_close']}")
            return False
        if data['last_close'] < 1000 or data['last_close'] > 200000:
            print(f"⚠️  WARNING: last_close {data['last_close']} seems unusual for BTC price")
        
        # Validate data_source
        if data['data_source'] not in ['kraken', 'coinbase', 'binance']:
            print(f"❌ FAILED: data_source should be 'kraken' or 'coinbase', got '{data['data_source']}'")
            return False
        
        # Validate cv_folds (should be list of length 5)
        if not isinstance(data['cv_folds'], list) or len(data['cv_folds']) != 5:
            print(f"❌ FAILED: cv_folds should be list of length 5, got {type(data['cv_folds'])} length {len(data['cv_folds']) if isinstance(data['cv_folds'], list) else 'N/A'}")
            return False
        
        # Validate each CV fold
        for i, fold in enumerate(data['cv_folds']):
            if not all(k in fold for k in ['fold', 'accuracy', 'testSize']):
                print(f"❌ FAILED: cv_folds[{i}] missing required keys")
                return False
            if fold['fold'] != i + 1:
                print(f"❌ FAILED: cv_folds[{i}] fold number should be {i+1}, got {fold['fold']}")
                return False
        
        # Validate importances (should be list of length 8)
        if not isinstance(data['importances'], list) or len(data['importances']) != 8:
            print(f"❌ FAILED: importances should be list of length 8, got {type(data['importances'])} length {len(data['importances']) if isinstance(data['importances'], list) else 'N/A'}")
            return False
        
        # Validate each importance
        for i, imp in enumerate(data['importances']):
            if not all(k in imp for k in ['feature', 'label', 'category', 'importance']):
                print(f"❌ FAILED: importances[{i}] missing required keys")
                return False
        
        # Check importances sum to ~100
        total_importance = sum(imp['importance'] for imp in data['importances'])
        if not (95 <= total_importance <= 105):
            print(f"⚠️  WARNING: importances sum to {total_importance}, expected ~100")
        
        # Validate performance (should be non-empty list)
        if not isinstance(data['performance'], list) or len(data['performance']) == 0:
            print(f"❌ FAILED: performance should be non-empty list, got {type(data['performance'])} length {len(data['performance']) if isinstance(data['performance'], list) else 'N/A'}")
            return False
        
        # Validate first performance entry
        perf = data['performance'][0]
        if not all(k in perf for k in ['date', 'iso', 'btcPrice', 'aiAccuracy']):
            print(f"❌ FAILED: performance[0] missing required keys")
            return False
        
        # Validate features (should be list of length 8)
        if not isinstance(data['features'], list) or len(data['features']) != 8:
            print(f"❌ FAILED: features should be list of length 8, got {type(data['features'])} length {len(data['features']) if isinstance(data['features'], list) else 'N/A'}")
            return False
        
        # Validate each feature
        for i, feat in enumerate(data['features']):
            if not all(k in feat for k in ['feature', 'label', 'category', 'value', 'unit']):
                print(f"❌ FAILED: features[{i}] missing required keys")
                return False
        
        print(f"✅ PASSED: Dashboard endpoint working correctly")
        print(f"   - signal: {data['signal']}")
        print(f"   - confidence: {data['confidence']}%")
        print(f"   - prob_up: {data['prob_up']}%, prob_down: {data['prob_down']}%")
        print(f"   - last_close: ${data['last_close']}")
        print(f"   - data_source: {data['data_source']}")
        print(f"   - overall_accuracy: {data['overall_accuracy']}%")
        print(f"   - cv_mean: {data['cv_mean']}%")
        print(f"   - cv_folds: {len(data['cv_folds'])} folds")
        print(f"   - importances: {len(data['importances'])} features")
        print(f"   - performance: {len(data['performance'])} data points")
        print(f"   - features: {len(data['features'])} features")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Request error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_refresh_endpoint():
    """Test POST /api/v1/refresh"""
    print("\n" + "="*70)
    print("TEST 3: POST /api/v1/refresh")
    print("="*70)
    
    try:
        url = f"{BASE_URL}/api/v1/refresh"
        print(f"Calling: {url}")
        
        response = requests.post(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected status 200, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        print(f"Response: {data}")
        
        # Validate response
        if data.get('status') != 'started':
            print(f"❌ FAILED: Expected status='started', got '{data.get('status')}'")
            return False
        
        print(f"✅ PASSED: Refresh endpoint triggered successfully")
        
        # Wait a moment and verify health/dashboard still work
        print("\n   Waiting 3 seconds to verify system stability...")
        time.sleep(3)
        
        # Check health
        health_url = f"{BASE_URL}/api/v1/health"
        health_resp = requests.get(health_url, timeout=30)
        if health_resp.status_code != 200:
            print(f"❌ FAILED: Health endpoint not responding after refresh")
            return False
        health_data = health_resp.json()
        print(f"   Health after refresh: status={health_data['status']}, compute_status={health_data['compute_status']}")
        
        # Check dashboard
        dash_url = f"{BASE_URL}/api/v1/dashboard"
        dash_resp = requests.get(dash_url, timeout=30)
        if dash_resp.status_code != 200:
            print(f"❌ FAILED: Dashboard endpoint not responding after refresh")
            return False
        dash_data = dash_resp.json()
        print(f"   Dashboard after refresh: status={dash_data.get('status')}")
        
        if dash_data.get('status') not in ['ready', 'computing']:
            print(f"⚠️  WARNING: Dashboard status '{dash_data.get('status')}' after refresh")
        
        print(f"✅ PASSED: System stable after refresh")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Request error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        return False


def main():
    print("\n" + "="*70)
    print("BITCOIN PREDICTIVE AI - BACKEND API TEST SUITE")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print(f"Testing via Next.js proxy to FastAPI backend")
    print("="*70)
    
    results = {
        'health': False,
        'dashboard': False,
        'refresh': False,
    }
    
    # Test in order
    results['health'] = test_health_endpoint()
    results['dashboard'] = test_dashboard_endpoint()
    results['refresh'] = test_refresh_endpoint()
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ PASSED" if passed_flag else "❌ FAILED"
        print(f"{test_name.upper()}: {status}")
    
    print("="*70)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*70)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
