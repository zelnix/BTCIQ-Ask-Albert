#!/usr/bin/env python3
"""
Backend test for Probabilistic Forecasts: Quantile Price Cones + Expected-Value per horizon
Test the new probabilistic forecast layer (quantile price cones + Expected Value) in the BitMarkAI FastAPI app.
Base URL: https://quant-features.preview.emergentagent.com/api
"""

import requests
import sys

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_dashboard_quantiles_and_ev():
    """
    TEST 1: GET /api/v1/dashboard — expect 200, status "ready"
    For EACH item in forecasts (and spot-check long_outlook if present):
    - forecast.quantiles exists with keys p10, p25, p50, p75, p90, all numbers, and MONOTONICALLY INCREASING
    - forecast.ev exists with: win_prob (0-100), avg_up_pct (>=0), avg_down_pct (>=0), payoff_ratio (number or null), 
      ev_pct (number), verdict (one of "Positive edge"/"Negative edge"/"Flat / no edge")
    - Sanity: p50 should be close to forecast.base (within ~2%)
    - Report the observed quantiles + ev for the 24H, 7D, and 30D horizons
    """
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/dashboard - Quantiles + Expected Value validation")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"Requesting: {url}")
        resp = requests.get(url, timeout=30)
        print(f"✅ HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✅ status='ready'")
        
        # Check forecasts exist
        forecasts = data.get('forecasts')
        if not forecasts:
            print(f"❌ FAILED: 'forecasts' field missing or empty")
            return False
        print(f"✅ forecasts field present with {len(forecasts)} items")
        
        # Validate each forecast
        horizons_to_report = ['24H', '7D', '30D']
        reported_horizons = []
        
        for i, forecast in enumerate(forecasts):
            horizon = forecast.get('horizon', f'forecast[{i}]')
            print(f"\n--- Validating forecast: {horizon} ---")
            
            # 1. Check quantiles exist
            quantiles = forecast.get('quantiles')
            if not quantiles:
                print(f"❌ FAILED: forecast.quantiles missing for {horizon}")
                return False
            print(f"✅ forecast.quantiles exists")
            
            # 2. Check all quantile keys present and are numbers
            required_quantiles = ['p10', 'p25', 'p50', 'p75', 'p90']
            for q in required_quantiles:
                if q not in quantiles:
                    print(f"❌ FAILED: quantiles.{q} missing for {horizon}")
                    return False
                if not isinstance(quantiles[q], (int, float)):
                    print(f"❌ FAILED: quantiles.{q} is not a number for {horizon} (got {type(quantiles[q])})")
                    return False
            print(f"✅ All quantile keys present (p10, p25, p50, p75, p90) and are numbers")
            
            # 3. Check monotonically increasing
            q_values = [quantiles['p10'], quantiles['p25'], quantiles['p50'], quantiles['p75'], quantiles['p90']]
            if not all(q_values[i] <= q_values[i+1] for i in range(len(q_values)-1)):
                print(f"❌ FAILED: quantiles NOT monotonically increasing for {horizon}")
                print(f"   Values: p10={quantiles['p10']}, p25={quantiles['p25']}, p50={quantiles['p50']}, p75={quantiles['p75']}, p90={quantiles['p90']}")
                return False
            print(f"✅ Quantiles are MONOTONICALLY INCREASING: p10 <= p25 <= p50 <= p75 <= p90")
            print(f"   p10=${quantiles['p10']:,.2f}, p25=${quantiles['p25']:,.2f}, p50=${quantiles['p50']:,.2f}, p75=${quantiles['p75']:,.2f}, p90=${quantiles['p90']:,.2f}")
            
            # 4. Check ev exists
            ev = forecast.get('ev')
            if not ev:
                print(f"❌ FAILED: forecast.ev missing for {horizon}")
                return False
            print(f"✅ forecast.ev exists")
            
            # 5. Check ev fields
            # win_prob (0-100)
            win_prob = ev.get('win_prob')
            if win_prob is None or not isinstance(win_prob, (int, float)):
                print(f"❌ FAILED: ev.win_prob missing or not a number for {horizon}")
                return False
            if not (0 <= win_prob <= 100):
                print(f"❌ FAILED: ev.win_prob out of range [0, 100] for {horizon} (got {win_prob})")
                return False
            print(f"✅ ev.win_prob={win_prob:.1f}% (valid range 0-100)")
            
            # avg_up_pct (>=0)
            avg_up_pct = ev.get('avg_up_pct')
            if avg_up_pct is None or not isinstance(avg_up_pct, (int, float)):
                print(f"❌ FAILED: ev.avg_up_pct missing or not a number for {horizon}")
                return False
            if avg_up_pct < 0:
                print(f"❌ FAILED: ev.avg_up_pct < 0 for {horizon} (got {avg_up_pct})")
                return False
            print(f"✅ ev.avg_up_pct={avg_up_pct:.2f}% (>=0)")
            
            # avg_down_pct (>=0)
            avg_down_pct = ev.get('avg_down_pct')
            if avg_down_pct is None or not isinstance(avg_down_pct, (int, float)):
                print(f"❌ FAILED: ev.avg_down_pct missing or not a number for {horizon}")
                return False
            if avg_down_pct < 0:
                print(f"❌ FAILED: ev.avg_down_pct < 0 for {horizon} (got {avg_down_pct})")
                return False
            print(f"✅ ev.avg_down_pct={avg_down_pct:.2f}% (>=0)")
            
            # payoff_ratio (number or null)
            payoff_ratio = ev.get('payoff_ratio')
            if payoff_ratio is not None and not isinstance(payoff_ratio, (int, float)):
                print(f"❌ FAILED: ev.payoff_ratio is not a number or null for {horizon} (got {type(payoff_ratio)})")
                return False
            print(f"✅ ev.payoff_ratio={payoff_ratio if payoff_ratio is not None else 'null'} (number or null)")
            
            # ev_pct (number)
            ev_pct = ev.get('ev_pct')
            if ev_pct is None or not isinstance(ev_pct, (int, float)):
                print(f"❌ FAILED: ev.ev_pct missing or not a number for {horizon}")
                return False
            print(f"✅ ev.ev_pct={ev_pct:.2f}% (number)")
            
            # verdict (one of "Positive edge"/"Negative edge"/"Flat / no edge")
            verdict = ev.get('verdict')
            valid_verdicts = ["Positive edge", "Negative edge", "Flat / no edge"]
            if verdict not in valid_verdicts:
                print(f"❌ FAILED: ev.verdict invalid for {horizon} (got '{verdict}', expected one of {valid_verdicts})")
                return False
            print(f"✅ ev.verdict='{verdict}' (valid)")
            
            # 6. Sanity check: p50 should be close to forecast.base (within ~2%)
            base = forecast.get('base')
            if base is not None:
                p50 = quantiles['p50']
                diff_pct = abs(p50 - base) / base * 100
                if diff_pct > 2.0:
                    print(f"⚠️  WARNING: p50 (${p50:,.2f}) differs from base (${base:,.2f}) by {diff_pct:.2f}% (>2%)")
                else:
                    print(f"✅ Sanity check: p50 (${p50:,.2f}) ≈ base (${base:,.2f}), diff={diff_pct:.2f}% (<=2%)")
            
            # Report for 24H, 7D, 30D
            if horizon in horizons_to_report:
                reported_horizons.append({
                    'horizon': horizon,
                    'quantiles': quantiles,
                    'ev': ev
                })
        
        # Report observed values for 24H, 7D, 30D
        print("\n" + "="*80)
        print("OBSERVED VALUES FOR 24H, 7D, 30D HORIZONS:")
        print("="*80)
        for item in reported_horizons:
            h = item['horizon']
            q = item['quantiles']
            e = item['ev']
            print(f"\n{h} HORIZON:")
            print(f"  Quantiles: p10=${q['p10']:,.2f}, p25=${q['p25']:,.2f}, p50=${q['p50']:,.2f}, p75=${q['p75']:,.2f}, p90=${q['p90']:,.2f}")
            print(f"  Expected Value: win_prob={e['win_prob']:.1f}%, avg_up={e['avg_up_pct']:.2f}%, avg_down={e['avg_down_pct']:.2f}%, payoff_ratio={e['payoff_ratio'] if e['payoff_ratio'] is not None else 'null'}, ev_pct={e['ev_pct']:.2f}%, verdict='{e['verdict']}'")
        
        # Spot-check long_outlook if present
        long_outlook = data.get('long_outlook')
        if long_outlook:
            print(f"\n--- Spot-checking long_outlook ({len(long_outlook)} items) ---")
            for lo in long_outlook:
                horizon = lo.get('horizon', 'unknown')
                quantiles = lo.get('quantiles')
                ev = lo.get('ev')
                
                if quantiles:
                    # Quick check: all keys present and monotonic
                    if all(k in quantiles for k in ['p10', 'p25', 'p50', 'p75', 'p90']):
                        q_values = [quantiles['p10'], quantiles['p25'], quantiles['p50'], quantiles['p75'], quantiles['p90']]
                        if all(q_values[i] <= q_values[i+1] for i in range(len(q_values)-1)):
                            print(f"✅ long_outlook[{horizon}].quantiles: monotonic, p50=${quantiles['p50']:,.2f}")
                        else:
                            print(f"❌ long_outlook[{horizon}].quantiles: NOT monotonic")
                            return False
                
                if ev:
                    verdict = ev.get('verdict')
                    if verdict in valid_verdicts:
                        print(f"✅ long_outlook[{horizon}].ev: verdict='{verdict}', ev_pct={ev.get('ev_pct', 'N/A')}")
                    else:
                        print(f"❌ long_outlook[{horizon}].ev: invalid verdict '{verdict}'")
                        return False
        
        print("\n✅ TEST 1 PASSED: All forecasts have valid quantiles + EV")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression_dashboard():
    """
    TEST 2: GET /api/v1/dashboard - Regression checks
    - decision.weights_mode == "dynamic"
    - decision.scenarios_block present
    """
    print("\n" + "="*80)
    print("TEST 2: GET /api/v1/dashboard - Regression (weights_mode, scenarios_block)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"Requesting: {url}")
        resp = requests.get(url, timeout=30)
        print(f"✅ HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        
        # Check decision.weights_mode
        decision = data.get('decision')
        if not decision:
            print(f"❌ FAILED: 'decision' field missing")
            return False
        
        weights_mode = decision.get('weights_mode')
        if weights_mode != 'dynamic':
            print(f"❌ FAILED: decision.weights_mode != 'dynamic' (got '{weights_mode}')")
            return False
        print(f"✅ decision.weights_mode='dynamic'")
        
        # Check decision.scenarios_block present
        scenarios_block = decision.get('scenarios_block')
        if not scenarios_block:
            print(f"❌ FAILED: decision.scenarios_block missing or null")
            return False
        print(f"✅ decision.scenarios_block present")
        
        print("\n✅ TEST 2 PASSED: Dashboard regression checks passed")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression_forecast_regime():
    """
    TEST 3: GET /api/v1/forecast/regime - status "ready"
    """
    print("\n" + "="*80)
    print("TEST 3: GET /api/v1/forecast/regime - Regression")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/forecast/regime"
        print(f"Requesting: {url}")
        resp = requests.get(url, timeout=30)
        print(f"✅ HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✅ status='ready'")
        
        print("\n✅ TEST 3 PASSED: Forecast regime endpoint working")
        return True
        
    except Exception as e:
        print(f"❌ TEST 3 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression_data_audit():
    """
    TEST 4: GET /api/v1/data-audit - status "ready" (10 feeds)
    """
    print("\n" + "="*80)
    print("TEST 4: GET /api/v1/data-audit - Regression (10 feeds)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/data-audit"
        print(f"Requesting: {url}")
        resp = requests.get(url, timeout=30)
        print(f"✅ HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✅ status='ready'")
        
        feeds = data.get('feeds')
        if not feeds or len(feeds) != 10:
            print(f"❌ FAILED: Expected 10 feeds, got {len(feeds) if feeds else 0}")
            return False
        print(f"✅ feeds count=10")
        
        print("\n✅ TEST 4 PASSED: Data audit endpoint working with 10 feeds")
        return True
        
    except Exception as e:
        print(f"❌ TEST 4 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression_scorecard():
    """
    TEST 5: GET /api/v1/scorecard - status "ready" with reliability block present
    """
    print("\n" + "="*80)
    print("TEST 5: GET /api/v1/scorecard - Regression (reliability block)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/scorecard"
        print(f"Requesting: {url}")
        resp = requests.get(url, timeout=30)
        print(f"✅ HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
            return False
        
        data = resp.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print(f"✅ status='ready'")
        
        reliability = data.get('reliability')
        if not reliability:
            print(f"❌ FAILED: 'reliability' block missing")
            return False
        print(f"✅ reliability block present")
        
        print("\n✅ TEST 5 PASSED: Scorecard endpoint working with reliability block")
        return True
        
    except Exception as e:
        print(f"❌ TEST 5 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*80)
    print("PROBABILISTIC FORECASTS BACKEND TEST SUITE")
    print("Testing: Quantile Price Cones + Expected-Value per horizon")
    print("Base URL:", BASE_URL)
    print("="*80)
    
    results = []
    
    # Run all tests
    results.append(("Dashboard Quantiles + EV", test_dashboard_quantiles_and_ev()))
    results.append(("Dashboard Regression", test_regression_dashboard()))
    results.append(("Forecast Regime Regression", test_regression_forecast_regime()))
    results.append(("Data Audit Regression", test_regression_data_audit()))
    results.append(("Scorecard Regression", test_regression_scorecard()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Feature is fully functional")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
