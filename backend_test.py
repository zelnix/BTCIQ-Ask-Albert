#!/usr/bin/env python3
"""
Backend Test Suite for BitMarkAI Quant - Ensemble Weighting + Coverage History Validation
Base URL: https://quant-features.preview.emergentagent.com/api
"""

import requests
import json
from typing import Dict, Any, List

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def print_test_header(test_name: str):
    """Print formatted test header"""
    print(f"\n{'='*80}")
    print(f"TEST: {test_name}")
    print(f"{'='*80}")

def print_result(passed: bool, message: str):
    """Print test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"{status}: {message}")

def validate_validation_endpoint():
    """
    TEST 1: GET /api/v1/validation
    Validate NEW fields: coverage_history, coverage_target
    Validate EXISTING fields still present
    """
    print_test_header("GET /api/v1/validation - Coverage History + Validation Metrics")
    
    try:
        url = f"{BASE_URL}/v1/validation"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print_result(False, f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_result(True, "status='ready'")
        
        # NEW FIELD 1: coverage_history
        coverage_history = data.get('coverage_history')
        if not coverage_history:
            print_result(False, "coverage_history is missing or empty")
            return False
        
        if not isinstance(coverage_history, list):
            print_result(False, f"coverage_history should be a list, got {type(coverage_history)}")
            return False
        
        print_result(True, f"coverage_history is a non-empty list with {len(coverage_history)} items")
        
        # Validate coverage_history structure
        for i, item in enumerate(coverage_history[:3]):  # Check first 3
            if not isinstance(item, dict):
                print_result(False, f"coverage_history[{i}] should be a dict, got {type(item)}")
                return False
            
            # Check required fields
            if 'week' not in item:
                print_result(False, f"coverage_history[{i}] missing 'week' field")
                return False
            if not isinstance(item['week'], int):
                print_result(False, f"coverage_history[{i}].week should be int, got {type(item['week'])}")
                return False
            
            if 'coverage' not in item:
                print_result(False, f"coverage_history[{i}] missing 'coverage' field")
                return False
            if not isinstance(item['coverage'], (int, float)):
                print_result(False, f"coverage_history[{i}].coverage should be number, got {type(item['coverage'])}")
                return False
            if not (0 <= item['coverage'] <= 100):
                print_result(False, f"coverage_history[{i}].coverage should be 0-100, got {item['coverage']}")
                return False
            
            if 'n' not in item:
                print_result(False, f"coverage_history[{i}] missing 'n' field")
                return False
            if not isinstance(item['n'], int):
                print_result(False, f"coverage_history[{i}].n should be int, got {type(item['n'])}")
                return False
        
        print_result(True, "coverage_history structure validated (week: int, coverage: 0-100 number, n: int)")
        
        # Report first 3 coverage values
        first_3_coverage = [item['coverage'] for item in coverage_history[:3]]
        print(f"📊 REPORT: coverage_history length = {len(coverage_history)}")
        print(f"📊 REPORT: First 3 coverage values = {first_3_coverage}")
        
        # NEW FIELD 2: coverage_target
        coverage_target = data.get('coverage_target')
        if coverage_target is None:
            print_result(False, "coverage_target is missing")
            return False
        
        if not isinstance(coverage_target, (int, float)):
            print_result(False, f"coverage_target should be a number, got {type(coverage_target)}")
            return False
        
        print_result(True, f"coverage_target present = {coverage_target} (expected 90)")
        
        if coverage_target != 90:
            print(f"⚠️  WARNING: coverage_target is {coverage_target}, expected 90")
        
        # EXISTING FIELDS - Validate they are still present
        existing_fields = [
            'n_trades', 'brier_score', 'probabilistic_sharpe_ratio', 
            'deflated_sharpe_ratio', 'annualized_sharpe', 'rolling_brier_history',
            'rolling_brier_slope', 'benchmarks', 'thresholds'
        ]
        
        missing_fields = []
        for field in existing_fields:
            if field not in data:
                missing_fields.append(field)
        
        if missing_fields:
            print_result(False, f"Missing existing fields: {missing_fields}")
            return False
        
        print_result(True, f"All existing fields still present: {existing_fields}")
        
        # Validate types of existing fields
        if not isinstance(data['n_trades'], int):
            print_result(False, f"n_trades should be int, got {type(data['n_trades'])}")
            return False
        
        if not isinstance(data['brier_score'], (int, float)):
            print_result(False, f"brier_score should be number, got {type(data['brier_score'])}")
            return False
        
        if not isinstance(data['rolling_brier_history'], list):
            print_result(False, f"rolling_brier_history should be list, got {type(data['rolling_brier_history'])}")
            return False
        
        if not isinstance(data['benchmarks'], dict):
            print_result(False, f"benchmarks should be dict, got {type(data['benchmarks'])}")
            return False
        
        if not isinstance(data['thresholds'], dict):
            print_result(False, f"thresholds should be dict, got {type(data['thresholds'])}")
            return False
        
        print_result(True, "All existing field types validated")
        
        print("\n" + "="*80)
        print("TEST 1 SUMMARY: ✅ ALL VALIDATIONS PASSED")
        print("="*80)
        return True
        
    except requests.exceptions.RequestException as e:
        print_result(False, f"Request failed: {e}")
        return False
    except Exception as e:
        print_result(False, f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_dashboard_forecasts():
    """
    TEST 2: GET /api/v1/dashboard - Forecasts with ensemble_weight, decaying, horizon_brier
    """
    print_test_header("GET /api/v1/dashboard - Forecasts Ensemble Weighting")
    
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print_result(False, f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_result(True, "status='ready'")
        
        # Get forecasts
        forecasts = data.get('forecasts')
        if not forecasts:
            print_result(False, "forecasts field is missing or empty")
            return False
        
        if not isinstance(forecasts, list):
            print_result(False, f"forecasts should be a list, got {type(forecasts)}")
            return False
        
        print_result(True, f"forecasts is a list with {len(forecasts)} items")
        
        # Find 24H and 7D forecasts (matured horizons)
        forecast_24h = None
        forecast_7d = None
        forecast_30d = None
        
        for forecast in forecasts:
            horizon = forecast.get('horizon')
            if horizon == '24H':
                forecast_24h = forecast
            elif horizon == '7D':
                forecast_7d = forecast
            elif horizon == '30D':
                forecast_30d = forecast
        
        if not forecast_24h:
            print_result(False, "24H forecast not found")
            return False
        
        if not forecast_7d:
            print_result(False, "7D forecast not found")
            return False
        
        print_result(True, "Found 24H and 7D forecasts")
        
        # Validate 24H forecast
        print("\n--- Validating 24H Forecast ---")
        
        # NEW FIELDS: ensemble_weight, decaying, horizon_brier
        ensemble_weight_24h = forecast_24h.get('ensemble_weight')
        if ensemble_weight_24h is None:
            print_result(False, "24H forecast.ensemble_weight is missing")
            return False
        
        if not isinstance(ensemble_weight_24h, (int, float)):
            print_result(False, f"24H ensemble_weight should be number, got {type(ensemble_weight_24h)}")
            return False
        
        if not (0.3 <= ensemble_weight_24h <= 1.0):
            print_result(False, f"24H ensemble_weight should be in [0.3, 1.0], got {ensemble_weight_24h}")
            return False
        
        print_result(True, f"24H ensemble_weight = {ensemble_weight_24h} (in [0.3, 1.0])")
        
        decaying_24h = forecast_24h.get('decaying')
        if decaying_24h is None:
            print_result(False, "24H forecast.decaying is missing")
            return False
        
        if not isinstance(decaying_24h, bool):
            print_result(False, f"24H decaying should be bool, got {type(decaying_24h)}")
            return False
        
        print_result(True, f"24H decaying = {decaying_24h} (bool)")
        
        horizon_brier_24h = forecast_24h.get('horizon_brier')
        if horizon_brier_24h is None:
            print_result(False, "24H forecast.horizon_brier is missing")
            return False
        
        if not isinstance(horizon_brier_24h, (int, float)):
            print_result(False, f"24H horizon_brier should be number, got {type(horizon_brier_24h)}")
            return False
        
        print_result(True, f"24H horizon_brier = {horizon_brier_24h} (number)")
        
        # EXISTING FIELDS - Validate they are still present
        if forecast_24h.get('label_method') != 'triple_barrier':
            print_result(False, f"24H label_method should be 'triple_barrier', got '{forecast_24h.get('label_method')}'")
            return False
        print_result(True, "24H label_method = 'triple_barrier'")
        
        if 'conformal' not in forecast_24h:
            print_result(False, "24H conformal field is missing")
            return False
        print_result(True, "24H conformal field present")
        
        if forecast_24h.get('calibrated') != True:
            print_result(False, f"24H calibrated should be true, got {forecast_24h.get('calibrated')}")
            return False
        print_result(True, "24H calibrated = true")
        
        if 'quantiles' not in forecast_24h:
            print_result(False, "24H quantiles field is missing")
            return False
        print_result(True, "24H quantiles field present")
        
        if 'ev' not in forecast_24h:
            print_result(False, "24H ev field is missing")
            return False
        print_result(True, "24H ev field present")
        
        higher_24h = forecast_24h.get('higher')
        print(f"📊 REPORT: 24H higher = {higher_24h}%")
        
        # Validate 7D forecast
        print("\n--- Validating 7D Forecast ---")
        
        ensemble_weight_7d = forecast_7d.get('ensemble_weight')
        if ensemble_weight_7d is None:
            print_result(False, "7D forecast.ensemble_weight is missing")
            return False
        
        if not isinstance(ensemble_weight_7d, (int, float)):
            print_result(False, f"7D ensemble_weight should be number, got {type(ensemble_weight_7d)}")
            return False
        
        if not (0.3 <= ensemble_weight_7d <= 1.0):
            print_result(False, f"7D ensemble_weight should be in [0.3, 1.0], got {ensemble_weight_7d}")
            return False
        
        print_result(True, f"7D ensemble_weight = {ensemble_weight_7d} (in [0.3, 1.0])")
        
        decaying_7d = forecast_7d.get('decaying')
        if decaying_7d is None:
            print_result(False, "7D forecast.decaying is missing")
            return False
        
        if not isinstance(decaying_7d, bool):
            print_result(False, f"7D decaying should be bool, got {type(decaying_7d)}")
            return False
        
        print_result(True, f"7D decaying = {decaying_7d} (bool)")
        
        horizon_brier_7d = forecast_7d.get('horizon_brier')
        if horizon_brier_7d is None:
            print_result(False, "7D forecast.horizon_brier is missing")
            return False
        
        if not isinstance(horizon_brier_7d, (int, float)):
            print_result(False, f"7D horizon_brier should be number, got {type(horizon_brier_7d)}")
            return False
        
        print_result(True, f"7D horizon_brier = {horizon_brier_7d} (number)")
        
        # EXISTING FIELDS
        if forecast_7d.get('label_method') != 'triple_barrier':
            print_result(False, f"7D label_method should be 'triple_barrier', got '{forecast_7d.get('label_method')}'")
            return False
        print_result(True, "7D label_method = 'triple_barrier'")
        
        if 'conformal' not in forecast_7d:
            print_result(False, "7D conformal field is missing")
            return False
        print_result(True, "7D conformal field present")
        
        if forecast_7d.get('calibrated') != True:
            print_result(False, f"7D calibrated should be true, got {forecast_7d.get('calibrated')}")
            return False
        print_result(True, "7D calibrated = true")
        
        if 'quantiles' not in forecast_7d:
            print_result(False, "7D quantiles field is missing")
            return False
        print_result(True, "7D quantiles field present")
        
        if 'ev' not in forecast_7d:
            print_result(False, "7D ev field is missing")
            return False
        print_result(True, "7D ev field present")
        
        higher_7d = forecast_7d.get('higher')
        print(f"📊 REPORT: 7D higher = {higher_7d}%")
        
        # Validate 30D forecast (longer horizon - may have null ensemble_weight)
        if forecast_30d:
            print("\n--- Validating 30D Forecast (longer horizon) ---")
            ensemble_weight_30d = forecast_30d.get('ensemble_weight')
            print(f"30D ensemble_weight = {ensemble_weight_30d} (may be null for longer horizons - acceptable)")
            
            if ensemble_weight_30d is not None:
                if not isinstance(ensemble_weight_30d, (int, float)):
                    print_result(False, f"30D ensemble_weight should be number or null, got {type(ensemble_weight_30d)}")
                    return False
                if not (0.3 <= ensemble_weight_30d <= 1.0):
                    print_result(False, f"30D ensemble_weight should be in [0.3, 1.0] or null, got {ensemble_weight_30d}")
                    return False
        
        # Final report
        print("\n" + "="*80)
        print("📊 FINAL REPORT:")
        print(f"  24H: ensemble_weight={ensemble_weight_24h}, decaying={decaying_24h}, higher={higher_24h}%")
        print(f"  7D:  ensemble_weight={ensemble_weight_7d}, decaying={decaying_7d}, higher={higher_7d}%")
        print("="*80)
        
        print("\n" + "="*80)
        print("TEST 2 SUMMARY: ✅ ALL VALIDATIONS PASSED")
        print("="*80)
        return True
        
    except requests.exceptions.RequestException as e:
        print_result(False, f"Request failed: {e}")
        return False
    except Exception as e:
        print_result(False, f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_scorecard():
    """
    TEST 3: GET /api/v1/scorecard - by_horizon with ensemble_weight + decaying, reliability block
    """
    print_test_header("GET /api/v1/scorecard - Ensemble Weighting in by_horizon")
    
    try:
        url = f"{BASE_URL}/v1/scorecard"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print_result(False, f"Expected status='ready', got '{data.get('status')}'")
            return False
        print_result(True, "status='ready'")
        
        # Check by_horizon
        by_horizon = data.get('by_horizon')
        if not by_horizon:
            print_result(False, "by_horizon field is missing or empty")
            return False
        
        if not isinstance(by_horizon, dict):
            print_result(False, f"by_horizon should be a dict, got {type(by_horizon)}")
            return False
        
        print_result(True, f"by_horizon is a dict with {len(by_horizon)} entries")
        
        # Check for 24H and 7D entries
        if '24H' not in by_horizon:
            print_result(False, "by_horizon missing '24H' entry")
            return False
        
        if '7D' not in by_horizon:
            print_result(False, "by_horizon missing '7D' entry")
            return False
        
        print_result(True, "by_horizon has '24H' and '7D' entries")
        
        # Validate 24H entry
        print("\n--- Validating by_horizon['24H'] ---")
        horizon_24h = by_horizon['24H']
        
        if 'ensemble_weight' not in horizon_24h:
            print_result(False, "by_horizon['24H'] missing 'ensemble_weight'")
            return False
        
        ensemble_weight = horizon_24h['ensemble_weight']
        if not isinstance(ensemble_weight, (int, float)):
            print_result(False, f"by_horizon['24H'].ensemble_weight should be number, got {type(ensemble_weight)}")
            return False
        
        if not (0.3 <= ensemble_weight <= 1.0):
            print_result(False, f"by_horizon['24H'].ensemble_weight should be in [0.3, 1.0], got {ensemble_weight}")
            return False
        
        print_result(True, f"by_horizon['24H'].ensemble_weight = {ensemble_weight}")
        
        if 'decaying' not in horizon_24h:
            print_result(False, "by_horizon['24H'] missing 'decaying'")
            return False
        
        decaying = horizon_24h['decaying']
        if not isinstance(decaying, bool):
            print_result(False, f"by_horizon['24H'].decaying should be bool, got {type(decaying)}")
            return False
        
        print_result(True, f"by_horizon['24H'].decaying = {decaying}")
        
        # Validate 7D entry
        print("\n--- Validating by_horizon['7D'] ---")
        horizon_7d = by_horizon['7D']
        
        if 'ensemble_weight' not in horizon_7d:
            print_result(False, "by_horizon['7D'] missing 'ensemble_weight'")
            return False
        
        ensemble_weight_7d = horizon_7d['ensemble_weight']
        if not isinstance(ensemble_weight_7d, (int, float)):
            print_result(False, f"by_horizon['7D'].ensemble_weight should be number, got {type(ensemble_weight_7d)}")
            return False
        
        if not (0.3 <= ensemble_weight_7d <= 1.0):
            print_result(False, f"by_horizon['7D'].ensemble_weight should be in [0.3, 1.0], got {ensemble_weight_7d}")
            return False
        
        print_result(True, f"by_horizon['7D'].ensemble_weight = {ensemble_weight_7d}")
        
        if 'decaying' not in horizon_7d:
            print_result(False, "by_horizon['7D'] missing 'decaying'")
            return False
        
        decaying_7d = horizon_7d['decaying']
        if not isinstance(decaying_7d, bool):
            print_result(False, f"by_horizon['7D'].decaying should be bool, got {type(decaying_7d)}")
            return False
        
        print_result(True, f"by_horizon['7D'].decaying = {decaying_7d}")
        
        # Check reliability block
        if 'reliability' not in data:
            print_result(False, "reliability block is missing")
            return False
        
        print_result(True, "reliability block present")
        
        print("\n" + "="*80)
        print("TEST 3 SUMMARY: ✅ ALL VALIDATIONS PASSED")
        print("="*80)
        return True
        
    except requests.exceptions.RequestException as e:
        print_result(False, f"Request failed: {e}")
        return False
    except Exception as e:
        print_result(False, f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_regression_endpoints():
    """
    TEST 4: Regression tests - all endpoints should return 200
    """
    print_test_header("Regression Tests - Multiple Endpoints")
    
    all_passed = True
    
    # Test 1: GET /api/v1/forecast/regime
    try:
        print("\n--- Testing GET /api/v1/forecast/regime ---")
        url = f"{BASE_URL}/v1/forecast/regime"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            all_passed = False
        else:
            data = response.json()
            if data.get('status') != 'ready':
                print_result(False, f"Expected status='ready', got '{data.get('status')}'")
                all_passed = False
            else:
                print_result(True, "GET /api/v1/forecast/regime returns 200, status='ready'")
    except Exception as e:
        print_result(False, f"GET /api/v1/forecast/regime failed: {e}")
        all_passed = False
    
    # Test 2: GET /api/v1/data-audit
    try:
        print("\n--- Testing GET /api/v1/data-audit ---")
        url = f"{BASE_URL}/v1/data-audit"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            all_passed = False
        else:
            data = response.json()
            if data.get('status') != 'ready':
                print_result(False, f"Expected status='ready', got '{data.get('status')}'")
                all_passed = False
            else:
                feeds = data.get('feeds', [])
                if len(feeds) != 10:
                    print_result(False, f"Expected 10 feeds, got {len(feeds)}")
                    all_passed = False
                else:
                    print_result(True, f"GET /api/v1/data-audit returns 200, status='ready', 10 feeds")
    except Exception as e:
        print_result(False, f"GET /api/v1/data-audit failed: {e}")
        all_passed = False
    
    # Test 3: GET /api/v1/health
    try:
        print("\n--- Testing GET /api/v1/health ---")
        url = f"{BASE_URL}/v1/health"
        print(f"Requesting: {url}")
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print_result(False, f"Expected 200, got {response.status_code}")
            all_passed = False
        else:
            print_result(True, "GET /api/v1/health returns 200")
    except Exception as e:
        print_result(False, f"GET /api/v1/health failed: {e}")
        all_passed = False
    
    if all_passed:
        print("\n" + "="*80)
        print("TEST 4 SUMMARY: ✅ ALL REGRESSION TESTS PASSED")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("TEST 4 SUMMARY: ❌ SOME REGRESSION TESTS FAILED")
        print("="*80)
    
    return all_passed


def main():
    """Run all tests"""
    print("="*80)
    print("BitMarkAI Quant - Ensemble Weighting + Coverage History Validation")
    print("Base URL: https://quant-features.preview.emergentagent.com/api")
    print("="*80)
    
    results = {
        "Test 1 - GET /api/v1/validation": False,
        "Test 2 - GET /api/v1/dashboard (Forecasts)": False,
        "Test 3 - GET /api/v1/scorecard": False,
        "Test 4 - Regression Tests": False
    }
    
    # Run all tests
    results["Test 1 - GET /api/v1/validation"] = validate_validation_endpoint()
    results["Test 2 - GET /api/v1/dashboard (Forecasts)"] = validate_dashboard_forecasts()
    results["Test 3 - GET /api/v1/scorecard"] = validate_scorecard()
    results["Test 4 - Regression Tests"] = validate_regression_endpoints()
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL TEST SUMMARY")
    print("="*80)
    
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("="*80)
    print(f"OVERALL: {passed_count}/{total_count} tests passed")
    print("="*80)
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Feature is fully functional.")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Please review the failures above.")
        return 1


if __name__ == "__main__":
    exit(main())
