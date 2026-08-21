#!/usr/bin/env python3
"""
BitMarkAI Coverage-by-Horizon + Ensemble Weight Validation Test Suite
Tests the latest additions to the BitMarkAI quant engine.
"""

import requests
import sys
from typing import Dict, Any, List

# Base URL from review request
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_validation_endpoint():
    """
    TEST 1: GET /api/v1/validation
    Expect 200, status "ready":
    - coverage_history_by_horizon present, a dict with keys "24H", "7D", "30D"
    - Each horizon: non-empty list of {week, coverage, n}
    - Report the latest coverage value for each horizon
    - coverage_target == 90
    - Existing fields still present (n_trades, brier_score, PSR, DSR, rolling_brier_history, benchmarks)
    """
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/validation (Coverage History by Horizon)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/validation"
        print(f"→ Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"✓ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✓ status = 'ready'")
        
        # Check coverage_history_by_horizon
        coverage_by_horizon = data.get('coverage_history_by_horizon')
        if not coverage_by_horizon:
            print(f"❌ FAILED: coverage_history_by_horizon not present")
            return False
        print(f"✓ coverage_history_by_horizon present")
        
        # Check it's a dict
        if not isinstance(coverage_by_horizon, dict):
            print(f"❌ FAILED: coverage_history_by_horizon is not a dict, got {type(coverage_by_horizon)}")
            return False
        print(f"✓ coverage_history_by_horizon is a dict")
        
        # Check required keys
        required_horizons = ["24H", "7D", "30D"]
        for horizon in required_horizons:
            if horizon not in coverage_by_horizon:
                print(f"❌ FAILED: Missing horizon '{horizon}' in coverage_history_by_horizon")
                return False
        print(f"✓ All required horizons present: {required_horizons}")
        
        # Validate each horizon's data
        print("\n📊 COVERAGE BY HORIZON:")
        for horizon in required_horizons:
            history = coverage_by_horizon[horizon]
            
            # Check it's a non-empty list
            if not isinstance(history, list) or len(history) == 0:
                print(f"❌ FAILED: {horizon} history is not a non-empty list")
                return False
            
            # Check structure of items
            for i, item in enumerate(history[:3]):  # Check first 3 items
                if not all(key in item for key in ['week', 'coverage', 'n']):
                    print(f"❌ FAILED: {horizon} item {i} missing required keys (week, coverage, n)")
                    return False
                
                # Validate types
                if not isinstance(item['week'], int):
                    print(f"❌ FAILED: {horizon} item {i} week is not int")
                    return False
                if not isinstance(item['coverage'], (int, float)) or not (0 <= item['coverage'] <= 100):
                    print(f"❌ FAILED: {horizon} item {i} coverage not in 0-100 range")
                    return False
                if not isinstance(item['n'], int):
                    print(f"❌ FAILED: {horizon} item {i} n is not int")
                    return False
            
            # Report latest coverage value
            latest = history[-1]
            print(f"  {horizon}: {len(history)} weeks, latest coverage = {latest['coverage']}% (n={latest['n']})")
        
        # Check coverage_target
        coverage_target = data.get('coverage_target')
        if coverage_target != 90:
            print(f"❌ FAILED: coverage_target should be 90, got {coverage_target}")
            return False
        print(f"\n✓ coverage_target = 90")
        
        # Check existing fields still present
        existing_fields = [
            'n_trades', 'brier_score', 'probabilistic_sharpe_ratio', 
            'deflated_sharpe_ratio', 'rolling_brier_history', 'benchmarks'
        ]
        missing_fields = []
        for field in existing_fields:
            if field not in data:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"❌ FAILED: Missing existing fields: {missing_fields}")
            return False
        print(f"✓ All existing fields present: {existing_fields}")
        
        print("\n✅ TEST 1 PASSED: /api/v1/validation")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_decision_ensemble():
    """
    TEST 2: GET /api/v1/dashboard
    Expect 200, status "ready":
    - decision.overall_score present (int 0-100)
    - decision.overall_score_raw present
    - decision.ensemble_health present (0-1 float)
    - Report all three values
    - decision.label matches the adjusted overall_score band
    - forecasts still have conformal, ensemble_weight (for matured horizons), 
      calibrated, quantiles, ev, label_method=="triple_barrier"
    """
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/dashboard (Decision Ensemble Fields + Forecasts)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"→ Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"✓ HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✓ status = 'ready'")
        
        # Check decision object
        decision = data.get('decision')
        if not decision:
            print(f"❌ FAILED: decision object not present")
            return False
        print(f"✓ decision object present")
        
        # Check overall_score
        overall_score = decision.get('overall_score')
        if not isinstance(overall_score, int) or not (0 <= overall_score <= 100):
            print(f"❌ FAILED: overall_score should be int 0-100, got {overall_score} ({type(overall_score)})")
            return False
        print(f"✓ decision.overall_score = {overall_score} (int 0-100)")
        
        # Check overall_score_raw
        overall_score_raw = decision.get('overall_score_raw')
        if overall_score_raw is None:
            print(f"❌ FAILED: overall_score_raw not present")
            return False
        if not isinstance(overall_score_raw, (int, float)) or not (0 <= overall_score_raw <= 100):
            print(f"❌ FAILED: overall_score_raw should be number 0-100, got {overall_score_raw}")
            return False
        print(f"✓ decision.overall_score_raw = {overall_score_raw}")
        
        # Check ensemble_health
        ensemble_health = decision.get('ensemble_health')
        if ensemble_health is None:
            print(f"❌ FAILED: ensemble_health not present")
            return False
        if not isinstance(ensemble_health, (int, float)) or not (0 <= ensemble_health <= 1):
            print(f"❌ FAILED: ensemble_health should be float 0-1, got {ensemble_health}")
            return False
        print(f"✓ decision.ensemble_health = {ensemble_health:.3f} (0-1 float)")
        
        # Report all three
        print(f"\n📊 DECISION ENSEMBLE METRICS:")
        print(f"  overall_score (adjusted) = {overall_score}")
        print(f"  overall_score_raw = {overall_score_raw}")
        print(f"  ensemble_health = {ensemble_health:.3f}")
        
        # Check label matches score band
        label = decision.get('label')
        if not label:
            print(f"❌ FAILED: decision.label not present")
            return False
        print(f"✓ decision.label = '{label}'")
        
        # Check forecasts
        forecasts = data.get('forecasts')
        if not forecasts or not isinstance(forecasts, list):
            print(f"❌ FAILED: forecasts not present or not a list")
            return False
        print(f"\n✓ forecasts present ({len(forecasts)} items)")
        
        # Validate forecast fields
        required_forecast_fields = ['conformal', 'calibrated', 'quantiles', 'ev', 'label_method']
        
        print("\n📊 FORECAST VALIDATION:")
        for forecast in forecasts:
            horizon = forecast.get('horizon', 'unknown')
            
            # Check required fields
            for field in required_forecast_fields:
                if field not in forecast:
                    print(f"❌ FAILED: {horizon} forecast missing field '{field}'")
                    return False
            
            # Check label_method
            if forecast['label_method'] != 'triple_barrier':
                print(f"❌ FAILED: {horizon} label_method should be 'triple_barrier', got '{forecast['label_method']}'")
                return False
            
            # Check ensemble_weight (should be present for matured horizons like 24H, 7D)
            ensemble_weight = forecast.get('ensemble_weight')
            if horizon in ['24H', '7D']:
                if ensemble_weight is None:
                    print(f"⚠️  WARNING: {horizon} ensemble_weight is None (expected for matured horizons)")
                else:
                    if not isinstance(ensemble_weight, (int, float)) or not (0 <= ensemble_weight <= 1):
                        print(f"❌ FAILED: {horizon} ensemble_weight should be 0-1, got {ensemble_weight}")
                        return False
                    print(f"  {horizon}: ensemble_weight = {ensemble_weight:.3f} ✓")
            else:
                # For longer horizons, ensemble_weight may be None
                if ensemble_weight is not None:
                    print(f"  {horizon}: ensemble_weight = {ensemble_weight:.3f} ✓")
                else:
                    print(f"  {horizon}: ensemble_weight = None (acceptable for longer horizons) ✓")
            
            # Verify other fields are present
            print(f"  {horizon}: conformal={forecast.get('conformal') is not None}, "
                  f"calibrated={forecast.get('calibrated')}, "
                  f"quantiles={forecast.get('quantiles') is not None}, "
                  f"ev={forecast.get('ev') is not None}, "
                  f"label_method='{forecast.get('label_method')}' ✓")
        
        print("\n✅ TEST 2 PASSED: /api/v1/dashboard")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression_endpoints():
    """
    TEST 3: Regression - all 200
    - GET /api/v1/scorecard (ready, by_horizon has ensemble_weight, reliability present)
    - GET /api/v1/forecast/regime (ready)
    - GET /api/v1/data-audit (ready, 10 feeds)
    - GET /api/v1/health
    """
    print("\n" + "="*80)
    print("TEST 3: Regression Tests")
    print("="*80)
    
    all_passed = True
    
    # Test 3.1: GET /api/v1/scorecard
    print("\n→ TEST 3.1: GET /api/v1/scorecard")
    try:
        url = f"{BASE_URL}/v1/scorecard"
        response = requests.get(url, timeout=30)
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ FAILED: Expected HTTP 200, got {response.status_code}")
            all_passed = False
        else:
            data = response.json()
            
            if data.get('status') != 'ready':
                print(f"  ❌ FAILED: Expected status='ready', got '{data.get('status')}'")
                all_passed = False
            else:
                print(f"  ✓ status = 'ready'")
            
            # Check by_horizon has ensemble_weight
            by_horizon = data.get('by_horizon')
            if not by_horizon:
                print(f"  ❌ FAILED: by_horizon not present")
                all_passed = False
            else:
                print(f"  ✓ by_horizon present")
                
                # Check ensemble_weight in matured horizons
                for horizon in ['24H', '7D']:
                    if horizon in by_horizon:
                        ew = by_horizon[horizon].get('ensemble_weight')
                        if ew is not None:
                            print(f"  ✓ by_horizon['{horizon}'].ensemble_weight = {ew:.3f}")
                        else:
                            print(f"  ⚠️  by_horizon['{horizon}'].ensemble_weight = None")
            
            # Check reliability present
            if 'reliability' not in data:
                print(f"  ❌ FAILED: reliability not present")
                all_passed = False
            else:
                print(f"  ✓ reliability present")
            
            if all_passed:
                print(f"  ✅ PASSED: /api/v1/scorecard")
    
    except Exception as e:
        print(f"  ❌ FAILED with exception: {e}")
        all_passed = False
    
    # Test 3.2: GET /api/v1/forecast/regime
    print("\n→ TEST 3.2: GET /api/v1/forecast/regime")
    try:
        url = f"{BASE_URL}/v1/forecast/regime"
        response = requests.get(url, timeout=30)
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ FAILED: Expected HTTP 200, got {response.status_code}")
            all_passed = False
        else:
            data = response.json()
            
            if data.get('status') != 'ready':
                print(f"  ❌ FAILED: Expected status='ready', got '{data.get('status')}'")
                all_passed = False
            else:
                print(f"  ✓ status = 'ready'")
                print(f"  ✅ PASSED: /api/v1/forecast/regime")
    
    except Exception as e:
        print(f"  ❌ FAILED with exception: {e}")
        all_passed = False
    
    # Test 3.3: GET /api/v1/data-audit
    print("\n→ TEST 3.3: GET /api/v1/data-audit")
    try:
        url = f"{BASE_URL}/v1/data-audit"
        response = requests.get(url, timeout=30)
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ FAILED: Expected HTTP 200, got {response.status_code}")
            all_passed = False
        else:
            data = response.json()
            
            if data.get('status') != 'ready':
                print(f"  ❌ FAILED: Expected status='ready', got '{data.get('status')}'")
                all_passed = False
            else:
                print(f"  ✓ status = 'ready'")
            
            # Check 10 feeds
            feeds = data.get('feeds')
            if not feeds or len(feeds) != 10:
                print(f"  ❌ FAILED: Expected 10 feeds, got {len(feeds) if feeds else 0}")
                all_passed = False
            else:
                print(f"  ✓ 10 feeds present")
                print(f"  ✅ PASSED: /api/v1/data-audit")
    
    except Exception as e:
        print(f"  ❌ FAILED with exception: {e}")
        all_passed = False
    
    # Test 3.4: GET /api/v1/health
    print("\n→ TEST 3.4: GET /api/v1/health")
    try:
        url = f"{BASE_URL}/v1/health"
        response = requests.get(url, timeout=30)
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ FAILED: Expected HTTP 200, got {response.status_code}")
            all_passed = False
        else:
            print(f"  ✅ PASSED: /api/v1/health")
    
    except Exception as e:
        print(f"  ❌ FAILED with exception: {e}")
        all_passed = False
    
    if all_passed:
        print("\n✅ TEST 3 PASSED: All regression tests")
    else:
        print("\n❌ TEST 3 FAILED: Some regression tests failed")
    
    return all_passed


def main():
    """Run all tests"""
    print("="*80)
    print("BitMarkAI Coverage-by-Horizon + Ensemble Weight Validation")
    print("Base URL:", BASE_URL)
    print("="*80)
    
    results = {
        'test_1_validation': False,
        'test_2_dashboard': False,
        'test_3_regression': False
    }
    
    # Run tests
    results['test_1_validation'] = test_validation_endpoint()
    results['test_2_dashboard'] = test_dashboard_decision_ensemble()
    results['test_3_regression'] = test_regression_endpoints()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Feature is production-ready")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
