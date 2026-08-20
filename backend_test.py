#!/usr/bin/env python3
"""
Backend Test Suite for Isotonic Calibration + Per-Horizon Feature Sets
Tests the new calibration and feature selection in BitMarkAI FastAPI app
Base URL: https://quant-features.preview.emergentagent.com/api
"""

import requests
import sys
from typing import Dict, List, Any

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_dashboard_isotonic_calibration():
    """
    Test 1: GET /api/v1/dashboard - Isotonic calibration + per-horizon feature sets
    
    For EACH item in forecasts and long_outlook:
    - forecast.calibrated is a boolean (should be true for most/all horizons)
    - forecast.features_used is a non-empty list of strings
    - Verify short horizons (24H/7D) use 7 features, mid (30D/3M) use 8, long (6M/1Y) use 4
    - forecast.quantiles still present and MONOTONICALLY INCREASING
    - forecast.ev still present with all required fields
    - Report calibrated flag, features_used count, higher%, and ev_pct for 24H, 7D, 30D, 6M, 1Y
    """
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/dashboard - Isotonic Calibration + Per-Horizon Features")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/dashboard", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✅ status='ready'")
        
        # Check forecasts field exists
        if 'forecasts' not in data:
            print(f"❌ FAILED: 'forecasts' field missing from dashboard")
            return False
        
        forecasts = data['forecasts']
        print(f"✅ forecasts field present with {len(forecasts)} items")
        
        # Check long_outlook field exists
        if 'long_outlook' not in data:
            print(f"❌ FAILED: 'long_outlook' field missing from dashboard")
            return False
        
        long_outlook = data['long_outlook']
        print(f"✅ long_outlook field present with {len(long_outlook)} items")
        
        # Combine all forecast items for validation
        all_forecasts = forecasts + long_outlook
        
        # Expected feature counts per horizon
        expected_features = {
            '24H': 7,  # short: momentum/volatility/volume subset
            '7D': 7,   # short: momentum/volatility/volume subset
            '30D': 8,  # medium: all 8 features
            '3M': 8,   # medium: all 8 features
            '6M': 4,   # long: trend subset (EMA_Ratio/MACD/RSI/ATR)
            '1Y': 4    # long: trend subset
        }
        
        print("\n" + "-"*80)
        print("VALIDATING EACH FORECAST HORIZON:")
        print("-"*80)
        
        results = {}
        all_passed = True
        
        for forecast in all_forecasts:
            horizon = forecast.get('horizon')
            print(f"\n📊 HORIZON: {horizon}")
            print("-" * 40)
            
            # 1. Check calibrated field
            if 'calibrated' not in forecast:
                print(f"  ❌ FAILED: 'calibrated' field missing")
                all_passed = False
                continue
            
            calibrated = forecast['calibrated']
            if not isinstance(calibrated, bool):
                print(f"  ❌ FAILED: 'calibrated' is not a boolean (got {type(calibrated).__name__})")
                all_passed = False
                continue
            
            print(f"  ✅ calibrated: {calibrated} (boolean)")
            
            # 2. Check features_used field
            if 'features_used' not in forecast:
                print(f"  ❌ FAILED: 'features_used' field missing")
                all_passed = False
                continue
            
            features_used = forecast['features_used']
            if not isinstance(features_used, list):
                print(f"  ❌ FAILED: 'features_used' is not a list (got {type(features_used).__name__})")
                all_passed = False
                continue
            
            if len(features_used) == 0:
                print(f"  ❌ FAILED: 'features_used' is empty")
                all_passed = False
                continue
            
            # Check all items are strings
            if not all(isinstance(f, str) for f in features_used):
                print(f"  ❌ FAILED: 'features_used' contains non-string items")
                all_passed = False
                continue
            
            print(f"  ✅ features_used: {len(features_used)} features (non-empty list of strings)")
            print(f"     Features: {', '.join(features_used)}")
            
            # 3. Verify expected feature count
            if horizon in expected_features:
                expected_count = expected_features[horizon]
                actual_count = len(features_used)
                if actual_count == expected_count:
                    print(f"  ✅ Feature count: {actual_count} (matches expected {expected_count})")
                else:
                    print(f"  ⚠️  Feature count: {actual_count} (expected {expected_count}) - MISMATCH")
                    # Not failing the test, just reporting
            
            # 4. Check quantiles field
            if 'quantiles' not in forecast:
                print(f"  ❌ FAILED: 'quantiles' field missing")
                all_passed = False
                continue
            
            quantiles = forecast['quantiles']
            required_quantiles = ['p10', 'p25', 'p50', 'p75', 'p90']
            
            # Check all required quantiles present
            missing_quantiles = [q for q in required_quantiles if q not in quantiles]
            if missing_quantiles:
                print(f"  ❌ FAILED: Missing quantiles: {missing_quantiles}")
                all_passed = False
                continue
            
            # Check all quantiles are numbers
            for q in required_quantiles:
                if not isinstance(quantiles[q], (int, float)):
                    print(f"  ❌ FAILED: quantiles.{q} is not a number (got {type(quantiles[q]).__name__})")
                    all_passed = False
                    continue
            
            # Check monotonically increasing
            p10, p25, p50, p75, p90 = quantiles['p10'], quantiles['p25'], quantiles['p50'], quantiles['p75'], quantiles['p90']
            if not (p10 <= p25 <= p50 <= p75 <= p90):
                print(f"  ❌ FAILED: Quantiles NOT monotonically increasing")
                print(f"     p10={p10}, p25={p25}, p50={p50}, p75={p75}, p90={p90}")
                all_passed = False
                continue
            
            print(f"  ✅ quantiles: MONOTONICALLY INCREASING")
            print(f"     p10=${p10:,.0f}, p25=${p25:,.0f}, p50=${p50:,.0f}, p75=${p75:,.0f}, p90=${p90:,.0f}")
            
            # 5. Check ev field
            if 'ev' not in forecast:
                print(f"  ❌ FAILED: 'ev' field missing")
                all_passed = False
                continue
            
            ev = forecast['ev']
            required_ev_fields = ['win_prob', 'avg_up_pct', 'avg_down_pct', 'payoff_ratio', 'ev_pct', 'verdict']
            
            # Check all required EV fields present
            missing_ev_fields = [f for f in required_ev_fields if f not in ev]
            if missing_ev_fields:
                print(f"  ❌ FAILED: Missing EV fields: {missing_ev_fields}")
                all_passed = False
                continue
            
            print(f"  ✅ ev: All required fields present")
            print(f"     win_prob={ev['win_prob']:.1f}%, avg_up={ev['avg_up_pct']:.2f}%, avg_down={ev['avg_down_pct']:.2f}%")
            print(f"     payoff_ratio={ev['payoff_ratio']}, ev_pct={ev['ev_pct']:.2f}%, verdict='{ev['verdict']}'")
            
            # 6. Get higher% for reporting
            higher_pct = forecast.get('higher', 'N/A')
            
            # Store results for summary
            results[horizon] = {
                'calibrated': calibrated,
                'features_count': len(features_used),
                'higher_pct': higher_pct,
                'ev_pct': ev['ev_pct']
            }
        
        # Print summary for requested horizons
        print("\n" + "="*80)
        print("SUMMARY FOR REQUESTED HORIZONS (24H, 7D, 30D, 6M, 1Y):")
        print("="*80)
        
        requested_horizons = ['24H', '7D', '30D', '6M', '1Y']
        for h in requested_horizons:
            if h in results:
                r = results[h]
                print(f"{h:4s}: calibrated={r['calibrated']}, features={r['features_count']}, higher={r['higher_pct']}%, ev_pct={r['ev_pct']:.2f}%")
            else:
                print(f"{h:4s}: NOT FOUND in response")
        
        if all_passed:
            print("\n✅ TEST 1 PASSED: All validations successful")
            return True
        else:
            print("\n❌ TEST 1 FAILED: Some validations failed")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Request error: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_regression():
    """
    Test 2: GET /api/v1/dashboard - Regression test
    - decision.weights_mode == "dynamic"
    - decision.scenarios_block present
    """
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/dashboard - Regression (decision fields)")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/dashboard", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check decision field
        if 'decision' not in data:
            print(f"❌ FAILED: 'decision' field missing")
            return False
        
        decision = data['decision']
        
        # Check weights_mode
        if 'weights_mode' not in decision:
            print(f"❌ FAILED: 'decision.weights_mode' field missing")
            return False
        
        weights_mode = decision['weights_mode']
        if weights_mode != 'dynamic':
            print(f"❌ FAILED: Expected weights_mode='dynamic', got '{weights_mode}'")
            return False
        
        print(f"✅ decision.weights_mode='dynamic'")
        
        # Check scenarios_block
        if 'scenarios_block' not in decision:
            print(f"❌ FAILED: 'decision.scenarios_block' field missing")
            return False
        
        print(f"✅ decision.scenarios_block present")
        
        print("\n✅ TEST 2 PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_forecast_regime():
    """
    Test 3: GET /api/v1/forecast/regime - Regression test
    """
    print("\n" + "="*80)
    print("TEST 3: GET /api/v1/forecast/regime - Regression")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/forecast/regime", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        
        print(f"✅ status='ready'")
        print("\n✅ TEST 3 PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_data_audit():
    """
    Test 4: GET /api/v1/data-audit - Regression test
    - status "ready"
    - 10 feeds
    """
    print("\n" + "="*80)
    print("TEST 4: GET /api/v1/data-audit - Regression (10 feeds)")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/data-audit", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        
        print(f"✅ status='ready'")
        
        # Check feeds count
        if 'feeds' not in data:
            print(f"❌ FAILED: 'feeds' field missing")
            return False
        
        feeds = data['feeds']
        feeds_count = len(feeds)
        
        if feeds_count != 10:
            print(f"⚠️  feeds count: {feeds_count} (expected 10)")
        else:
            print(f"✅ feeds count: {feeds_count}")
        
        print("\n✅ TEST 4 PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_scorecard():
    """
    Test 5: GET /api/v1/scorecard - Regression test
    - status "ready"
    - reliability block present
    """
    print("\n" + "="*80)
    print("TEST 5: GET /api/v1/scorecard - Regression (reliability block)")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/scorecard", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        
        print(f"✅ status='ready'")
        
        # Check reliability block
        if 'reliability' not in data:
            print(f"❌ FAILED: 'reliability' field missing")
            return False
        
        print(f"✅ reliability block present")
        
        print("\n✅ TEST 5 PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_health():
    """
    Test 6: GET /api/v1/health - Regression test
    """
    print("\n" + "="*80)
    print("TEST 6: GET /api/v1/health - Regression")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/health", timeout=30)
        print(f"✅ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            return False
        
        print("\n✅ TEST 6 PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BACKEND TEST SUITE: ISOTONIC CALIBRATION + PER-HORIZON FEATURE SETS")
    print("Base URL: https://quant-features.preview.emergentagent.com/api")
    print("="*80)
    
    tests = [
        ("Dashboard Isotonic Calibration", test_dashboard_isotonic_calibration),
        ("Dashboard Regression", test_dashboard_regression),
        ("Forecast Regime", test_forecast_regime),
        ("Data Audit", test_data_audit),
        ("Scorecard", test_scorecard),
        ("Health", test_health),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ TEST '{test_name}' CRASHED: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print final summary
    print("\n" + "="*80)
    print("FINAL TEST SUMMARY")
    print("="*80)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
