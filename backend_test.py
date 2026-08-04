#!/usr/bin/env python3
"""
Backend Test Suite for Bitcoin Quant Dashboard - Institutional-Grade Engine Fields
Tests all NEW fields: cycle, dominance, chart, market_intel, and forecasts[*].contributions
"""
import requests
import sys
from datetime import datetime

# External base URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_health():
    """Test GET /api/v1/health endpoint"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/health")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/v1/health", timeout=15)
        print(f"✓ Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"✗ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"✓ Response: {data}")
        
        # Validate required fields
        required = ['status', 'compute_status', 'runs']
        for field in required:
            if field not in data:
                print(f"✗ FAILED: Missing required field '{field}'")
                return False
            print(f"✓ Field '{field}': {data[field]}")
        
        # Validate compute_status is likely 'done'
        if data['compute_status'] not in ['done', 'running', 'idle']:
            print(f"✗ WARNING: Unexpected compute_status: {data['compute_status']}")
        
        print("✓ PASSED: Health endpoint working correctly")
        return True
        
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        return False


def test_ticker():
    """Test GET /api/v1/ticker endpoint"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/ticker")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/v1/ticker", timeout=15)
        print(f"✓ Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"✗ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        print(f"✓ Response: {data}")
        
        # Validate required fields
        required = ['price', 'change24h', 'high', 'low', 'source', 'ts']
        for field in required:
            if field not in data:
                print(f"✗ FAILED: Missing required field '{field}'")
                return False
        
        # Validate price is a live number
        if not isinstance(data['price'], (int, float)) or data['price'] <= 0:
            print(f"✗ FAILED: Invalid price: {data['price']}")
            return False
        
        print(f"✓ Live BTC Price: ${data['price']:,.2f}")
        print(f"✓ 24h Change: {data['change24h']}%")
        print(f"✓ Source: {data['source']}")
        
        print("✓ PASSED: Ticker endpoint working correctly")
        return True
        
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        return False


def test_dashboard_new_fields():
    """Test GET /api/v1/dashboard - NEW institutional-grade engine fields"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/v1/dashboard - NEW INSTITUTIONAL-GRADE FIELDS")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/v1/dashboard", timeout=30)
        print(f"✓ Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"✗ FAILED: Expected 200, got {response.status_code}")
            return False
        
        data = response.json()
        
        # Validate status is 'ready'
        if data.get('status') != 'ready':
            print(f"✗ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✓ Status: {data['status']}")
        
        # Validate all EXISTING keys are still present
        existing_keys = ['quant_score', 'quant_breakdown', 'regime', 'forecasts', 'factors', 
                        'scoreboard', 'trades', 'live_record', 'signal', 'confidence', 
                        'cv_folds', 'importances', 'performance', 'features']
        
        print("\n--- Validating EXISTING keys still present ---")
        for key in existing_keys:
            if key not in data:
                print(f"✗ FAILED: Missing existing key '{key}'")
                return False
            print(f"✓ Existing key '{key}': present")
        
        # =====================================================================
        # TEST NEW FIELD 1: cycle
        # =====================================================================
        print("\n" + "-"*80)
        print("NEW FIELD 1: cycle")
        print("-"*80)
        
        if 'cycle' not in data:
            print("✗ FAILED: Missing 'cycle' field")
            return False
        
        cycle = data['cycle']
        if cycle is None:
            print("✗ FAILED: 'cycle' is null (block height fetch may have failed)")
            return False
        
        print(f"✓ cycle field present: {type(cycle)}")
        
        # Validate cycle fields
        cycle_required = {
            'block_height': (int, lambda x: x > 800000, "int > 800000"),
            'epoch': (int, lambda x: True, "int"),
            'reward': ((int, float), lambda x: x > 0, "number > 0 (e.g., 3.125)"),
            'last_halving_date': (str, lambda x: len(x) == 10 and x.count('-') == 2, "YYYY-MM-DD string"),
            'days_since_halving': (int, lambda x: x > 0, "int > 0"),
            'next_halving_block': (int, lambda x: True, "int"),
            'blocks_to_next': (int, lambda x: x >= 0, "int >= 0"),
            'est_days_to_next': ((int, float), lambda x: x >= 0, "number >= 0"),
            'cycle_perf_pct': ((int, float, type(None)), lambda x: True, "number or null"),
            'cycle_progress_pct': ((int, float), lambda x: 0 <= x <= 100, "0-100"),
            'phase': (str, lambda x: len(x) > 0, "non-empty string"),
        }
        
        for field, (expected_type, validator, desc) in cycle_required.items():
            if field not in cycle:
                print(f"✗ FAILED: cycle missing field '{field}'")
                return False
            
            value = cycle[field]
            
            # Type check
            if not isinstance(value, expected_type):
                print(f"✗ FAILED: cycle.{field} wrong type. Expected {desc}, got {type(value).__name__}: {value}")
                return False
            
            # Value validation
            if value is not None and not validator(value):
                print(f"✗ FAILED: cycle.{field} invalid value. Expected {desc}, got: {value}")
                return False
            
            print(f"✓ cycle.{field}: {value} ({desc})")
        
        print("✓ PASSED: cycle field validation complete")
        
        # =====================================================================
        # TEST NEW FIELD 2: dominance
        # =====================================================================
        print("\n" + "-"*80)
        print("NEW FIELD 2: dominance")
        print("-"*80)
        
        if 'dominance' not in data:
            print("✗ FAILED: Missing 'dominance' field")
            return False
        
        dominance = data['dominance']
        if dominance is None:
            print("✗ FAILED: 'dominance' is null (CoinGecko fetch may have failed)")
            return False
        
        print(f"✓ dominance field present: {type(dominance)}")
        
        # Validate dominance fields
        dominance_required = {
            'dominance': ((int, float), lambda x: 0 <= x <= 100, "number 0-100 (realistic ~40-70)"),
            'total_mcap_t': ((int, float), lambda x: x > 0, "number > 0"),
            'change_7d': ((int, float, type(None)), lambda x: True, "number or null"),
            'change_30d': ((int, float, type(None)), lambda x: True, "number or null"),
            'direction': (str, lambda x: len(x) > 0, "string"),
            'interpretation': (str, lambda x: len(x) > 0, "non-empty string"),
            'history_points': (int, lambda x: x >= 1, "int >= 1"),
        }
        
        for field, (expected_type, validator, desc) in dominance_required.items():
            if field not in dominance:
                print(f"✗ FAILED: dominance missing field '{field}'")
                return False
            
            value = dominance[field]
            
            # Type check
            if not isinstance(value, expected_type):
                print(f"✗ FAILED: dominance.{field} wrong type. Expected {desc}, got {type(value).__name__}: {value}")
                return False
            
            # Value validation
            if value is not None and not validator(value):
                print(f"✗ FAILED: dominance.{field} invalid value. Expected {desc}, got: {value}")
                return False
            
            print(f"✓ dominance.{field}: {value} ({desc})")
        
        print("✓ PASSED: dominance field validation complete")
        
        # =====================================================================
        # TEST NEW FIELD 3: chart
        # =====================================================================
        print("\n" + "-"*80)
        print("NEW FIELD 3: chart")
        print("-"*80)
        
        if 'chart' not in data:
            print("✗ FAILED: Missing 'chart' field")
            return False
        
        chart = data['chart']
        if chart is None:
            print("✗ FAILED: 'chart' is null")
            return False
        
        print(f"✓ chart field present: {type(chart)}")
        
        # Validate chart.structure and chart.structure_bias
        if 'structure' not in chart or not isinstance(chart['structure'], str) or len(chart['structure']) == 0:
            print(f"✗ FAILED: chart.structure invalid: {chart.get('structure')}")
            return False
        print(f"✓ chart.structure: {chart['structure']}")
        
        if 'structure_bias' not in chart or chart['structure_bias'] not in ['Bullish', 'Bearish', 'Neutral']:
            print(f"✗ FAILED: chart.structure_bias invalid: {chart.get('structure_bias')}")
            return False
        print(f"✓ chart.structure_bias: {chart['structure_bias']}")
        
        # Validate chart.signals (non-empty list)
        if 'signals' not in chart or not isinstance(chart['signals'], list) or len(chart['signals']) == 0:
            print(f"✗ FAILED: chart.signals must be non-empty list, got: {chart.get('signals')}")
            return False
        
        print(f"✓ chart.signals: {len(chart['signals'])} items")
        
        # Validate each signal has required fields
        for i, signal in enumerate(chart['signals'][:3]):  # Check first 3
            if not all(k in signal for k in ['type', 'bias', 'detail']):
                print(f"✗ FAILED: chart.signals[{i}] missing required fields")
                return False
            print(f"  ✓ Signal {i+1}: type='{signal['type']}', bias='{signal['bias']}'")
        
        # Validate chart.sr_levels (non-empty list)
        if 'sr_levels' not in chart or not isinstance(chart['sr_levels'], list) or len(chart['sr_levels']) == 0:
            print(f"✗ FAILED: chart.sr_levels must be non-empty list, got: {chart.get('sr_levels')}")
            return False
        
        print(f"✓ chart.sr_levels: {len(chart['sr_levels'])} items")
        
        # Validate each sr_level has required fields
        for i, level in enumerate(chart['sr_levels'][:3]):  # Check first 3
            if 'price' not in level or not isinstance(level['price'], (int, float)) or level['price'] <= 0:
                print(f"✗ FAILED: chart.sr_levels[{i}].price invalid: {level.get('price')}")
                return False
            if 'type' not in level or level['type'] not in ['support', 'resistance']:
                print(f"✗ FAILED: chart.sr_levels[{i}].type invalid: {level.get('type')}")
                return False
            if 'strength' not in level or not isinstance(level['strength'], int) or level['strength'] < 1:
                print(f"✗ FAILED: chart.sr_levels[{i}].strength invalid: {level.get('strength')}")
                return False
            print(f"  ✓ Level {i+1}: price=${level['price']:,.0f}, type='{level['type']}', strength={level['strength']}")
        
        # Validate chart.predictive
        if 'predictive' not in chart or not isinstance(chart['predictive'], dict):
            print(f"✗ FAILED: chart.predictive must be object, got: {chart.get('predictive')}")
            return False
        
        predictive = chart['predictive']
        predictive_required = ['breakout_up', 'breakdown', 'consolidation', 'primary_setup']
        for field in predictive_required:
            if field not in predictive:
                print(f"✗ FAILED: chart.predictive missing field '{field}'")
                return False
        
        # Validate numeric fields
        for field in ['breakout_up', 'breakdown', 'consolidation']:
            if not isinstance(predictive[field], (int, float)):
                print(f"✗ FAILED: chart.predictive.{field} must be number, got: {predictive[field]}")
                return False
            print(f"✓ chart.predictive.{field}: {predictive[field]}")
        
        if not isinstance(predictive['primary_setup'], str) or len(predictive['primary_setup']) == 0:
            print(f"✗ FAILED: chart.predictive.primary_setup must be non-empty string")
            return False
        print(f"✓ chart.predictive.primary_setup: {predictive['primary_setup'][:60]}...")
        
        # Validate chart.ohlc (list of ~90)
        if 'ohlc' not in chart or not isinstance(chart['ohlc'], list):
            print(f"✗ FAILED: chart.ohlc must be list, got: {chart.get('ohlc')}")
            return False
        
        if len(chart['ohlc']) < 80 or len(chart['ohlc']) > 100:
            print(f"✗ WARNING: chart.ohlc expected ~90 items, got {len(chart['ohlc'])}")
        else:
            print(f"✓ chart.ohlc: {len(chart['ohlc'])} items")
        
        # Validate first ohlc item
        if len(chart['ohlc']) > 0:
            ohlc = chart['ohlc'][0]
            required_ohlc = ['t', 'o', 'h', 'l', 'c']
            if not all(k in ohlc for k in required_ohlc):
                print(f"✗ FAILED: chart.ohlc[0] missing required fields")
                return False
            print(f"  ✓ OHLC sample: t={ohlc['t']}, o={ohlc['o']}, h={ohlc['h']}, l={ohlc['l']}, c={ohlc['c']}")
        
        # Validate chart.range20
        if 'range20' not in chart or not isinstance(chart['range20'], dict):
            print(f"✗ FAILED: chart.range20 must be object, got: {chart.get('range20')}")
            return False
        
        range20 = chart['range20']
        if 'high' not in range20 or 'low' not in range20:
            print(f"✗ FAILED: chart.range20 missing high/low fields")
            return False
        print(f"✓ chart.range20: high={range20['high']}, low={range20['low']}")
        
        print("✓ PASSED: chart field validation complete")
        
        # =====================================================================
        # TEST NEW FIELD 4: market_intel
        # =====================================================================
        print("\n" + "-"*80)
        print("NEW FIELD 4: market_intel")
        print("-"*80)
        
        if 'market_intel' not in data:
            print("✗ FAILED: Missing 'market_intel' field")
            return False
        
        market_intel = data['market_intel']
        if market_intel is None:
            print("✗ FAILED: 'market_intel' is null")
            return False
        
        print(f"✓ market_intel field present: {type(market_intel)}")
        
        # Validate market_intel fields
        market_intel_required = {
            'quant_score': (int, "int"),
            'quant_label': (str, "str"),
            'regime': (str, "str"),
            'higher_24h': ((int, float, type(None)), "number or null"),
            'higher_7d': ((int, float, type(None)), "number or null"),
            'confidence': (str, "str"),
            'technical_structure': (str, "str"),
            'dominance': (str, "str"),
            'cycle_phase': (str, "str"),
            'top_positive': (str, "str"),
            'top_risk': (str, "str"),
        }
        
        for field, (expected_type, desc) in market_intel_required.items():
            if field not in market_intel:
                print(f"✗ FAILED: market_intel missing field '{field}'")
                return False
            
            value = market_intel[field]
            
            # Type check
            if not isinstance(value, expected_type):
                print(f"✗ FAILED: market_intel.{field} wrong type. Expected {desc}, got {type(value).__name__}: {value}")
                return False
            
            # Check for "Awaiting data source" messages (EXPECTED, not a bug)
            if isinstance(value, str) and "Awaiting data source" in value:
                print(f"✓ market_intel.{field}: {value} (EXPECTED - not yet integrated)")
            else:
                print(f"✓ market_intel.{field}: {value}")
        
        print("✓ PASSED: market_intel field validation complete")
        
        # =====================================================================
        # TEST NEW FIELD 5: forecasts[*].contributions (SHAP)
        # =====================================================================
        print("\n" + "-"*80)
        print("NEW FIELD 5: forecasts[*].contributions (SHAP)")
        print("-"*80)
        
        if 'forecasts' not in data or not isinstance(data['forecasts'], list):
            print(f"✗ FAILED: forecasts must be list, got: {data.get('forecasts')}")
            return False
        
        forecasts = data['forecasts']
        if len(forecasts) != 3:
            print(f"✗ FAILED: Expected 3 forecasts, got {len(forecasts)}")
            return False
        
        print(f"✓ forecasts: {len(forecasts)} items")
        
        # Check each forecast for contributions
        has_contributions = False
        for i, forecast in enumerate(forecasts):
            horizon = forecast.get('horizon', f'forecast_{i}')
            
            if 'contributions' not in forecast:
                print(f"✗ FAILED: forecasts[{i}] ({horizon}) missing 'contributions' field")
                return False
            
            contributions = forecast['contributions']
            
            if not isinstance(contributions, list):
                print(f"✗ FAILED: forecasts[{i}] ({horizon}) contributions must be list, got: {type(contributions)}")
                return False
            
            print(f"✓ forecasts[{i}] ({horizon}) contributions: {len(contributions)} items")
            
            if len(contributions) > 0:
                has_contributions = True
                
                # Validate first contribution item
                contrib = contributions[0]
                required_contrib = ['feature', 'label', 'category', 'contribution']
                
                for field in required_contrib:
                    if field not in contrib:
                        print(f"✗ FAILED: forecasts[{i}] ({horizon}) contributions[0] missing field '{field}'")
                        return False
                
                # Validate contribution is a number (can be negative)
                if not isinstance(contrib['contribution'], (int, float)):
                    print(f"✗ FAILED: forecasts[{i}] ({horizon}) contributions[0].contribution must be number, got: {contrib['contribution']}")
                    return False
                
                print(f"  ✓ Sample contribution: feature='{contrib['feature']}', label='{contrib['label']}', "
                      f"category='{contrib['category']}', contribution={contrib['contribution']}")
                
                # Show top 3 contributions
                for j, c in enumerate(contributions[:3]):
                    print(f"    {j+1}. {c['label']}: {c['contribution']:+.2f}")
        
        if not has_contributions:
            print("✗ WARNING: No forecasts have contributions (SHAP may not be available)")
        else:
            print("✓ PASSED: At least one forecast has contributions (SHAP working)")
        
        print("\n" + "="*80)
        print("✓ ALL NEW FIELDS VALIDATED SUCCESSFULLY")
        print("="*80)
        return True
        
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BITCOIN QUANT BACKEND TEST SUITE - INSTITUTIONAL-GRADE ENGINE FIELDS")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # Run tests
    results.append(("Health Endpoint", test_health()))
    results.append(("Ticker Endpoint", test_ticker()))
    results.append(("Dashboard NEW Fields", test_dashboard_new_fields()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Backend is working correctly!")
        return 0
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
