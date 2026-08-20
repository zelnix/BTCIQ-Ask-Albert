"""
Backend test for Dynamic Regime-Switching engine (Gaussian HMM).

Tests the new endpoints:
1. GET /api/v1/forecast/regime
2. POST /api/v1/forecast/reconcile-signals
3. GET /api/v1/dashboard (regression - decision.weights_mode == 'dynamic')
4. GET /api/v1/health (regression)
5. GET /api/v1/scorecard (regression)

Base URL: https://quant-features.preview.emergentagent.com/api
Admin passcode: 000000
DO NOT trigger any email endpoints.
"""
import requests
import json

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

def test_forecast_regime():
    """Test GET /api/v1/forecast/regime endpoint."""
    print("\n" + "="*80)
    print("TEST 1: GET /api/v1/forecast/regime")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/forecast/regime"
        print(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        # Check current_regime
        current_regime = data.get('current_regime')
        expected_regimes = ['consolidation', 'bull_momentum', 'bear_distribution', 'high_vol_squeeze']
        if current_regime not in expected_regimes:
            print(f"❌ FAILED: current_regime='{current_regime}' not in {expected_regimes}")
            return False
        print(f"✅ current_regime='{current_regime}' (valid)")
        
        # Check regime_label
        regime_label = data.get('regime_label')
        if not regime_label or not isinstance(regime_label, str):
            print(f"❌ FAILED: regime_label missing or invalid: {regime_label}")
            return False
        print(f"✅ regime_label='{regime_label}'")
        
        # Check regime_probabilities
        regime_probs = data.get('regime_probabilities')
        if not regime_probs or not isinstance(regime_probs, dict):
            print(f"❌ FAILED: regime_probabilities missing or not a dict")
            return False
        
        # Validate all 4 regimes present
        for regime in expected_regimes:
            if regime not in regime_probs:
                print(f"❌ FAILED: regime '{regime}' missing from regime_probabilities")
                return False
        print(f"✅ regime_probabilities has all 4 regimes: {list(regime_probs.keys())}")
        
        # Validate probabilities sum to ~1.0
        prob_sum = sum(regime_probs.values())
        if not (0.98 <= prob_sum <= 1.02):
            print(f"❌ FAILED: regime_probabilities sum={prob_sum:.4f}, expected ~1.0 (±0.02)")
            return False
        print(f"✅ regime_probabilities sum={prob_sum:.4f} (within 0.98-1.02)")
        
        # Validate current_regime == argmax(regime_probabilities)
        max_regime = max(regime_probs, key=regime_probs.get)
        if current_regime != max_regime:
            print(f"❌ FAILED: current_regime='{current_regime}' != argmax(regime_probabilities)='{max_regime}'")
            return False
        print(f"✅ current_regime == argmax(regime_probabilities) = '{max_regime}'")
        
        # Check active_weights
        active_weights = data.get('active_weights')
        if not active_weights or not isinstance(active_weights, dict):
            print(f"❌ FAILED: active_weights missing or not a dict")
            return False
        
        expected_signals = ['technicals', 'macro_policy', 'chart_structure', 'news_flow']
        for signal in expected_signals:
            if signal not in active_weights:
                print(f"❌ FAILED: signal '{signal}' missing from active_weights")
                return False
        print(f"✅ active_weights has all 4 signals: {list(active_weights.keys())}")
        
        # Validate weights sum to ~1.0
        weights_sum = sum(active_weights.values())
        if not (0.98 <= weights_sum <= 1.02):
            print(f"❌ FAILED: active_weights sum={weights_sum:.4f}, expected ~1.0 (±0.02)")
            return False
        print(f"✅ active_weights sum={weights_sum:.4f} (within 0.98-1.02)")
        print(f"   Weights: technicals={active_weights['technicals']:.4f}, macro_policy={active_weights['macro_policy']:.4f}, chart_structure={active_weights['chart_structure']:.4f}, news_flow={active_weights['news_flow']:.4f}")
        
        # Check confidence_24h
        confidence_24h = data.get('confidence_24h')
        if not confidence_24h or not isinstance(confidence_24h, dict):
            print(f"❌ FAILED: confidence_24h missing or not a dict")
            return False
        
        required_keys = ['lower_pct', 'expected_pct', 'upper_pct']
        for key in required_keys:
            if key not in confidence_24h:
                print(f"❌ FAILED: '{key}' missing from confidence_24h")
                return False
        print(f"✅ confidence_24h present with keys: {list(confidence_24h.keys())}")
        print(f"   24h cone: lower={confidence_24h['lower_pct']}%, expected={confidence_24h['expected_pct']}%, upper={confidence_24h['upper_pct']}%")
        
        # Check weight_matrix
        weight_matrix = data.get('weight_matrix')
        if not weight_matrix or not isinstance(weight_matrix, dict):
            print(f"❌ FAILED: weight_matrix missing or not a dict")
            return False
        
        for regime in expected_regimes:
            if regime not in weight_matrix:
                print(f"❌ FAILED: regime '{regime}' missing from weight_matrix")
                return False
        print(f"✅ weight_matrix has all 4 regimes")
        
        # Check regime_labels
        regime_labels = data.get('regime_labels')
        if not regime_labels or not isinstance(regime_labels, dict):
            print(f"❌ FAILED: regime_labels missing or not a dict")
            return False
        
        for regime in expected_regimes:
            if regime not in regime_labels:
                print(f"❌ FAILED: regime '{regime}' missing from regime_labels")
                return False
        print(f"✅ regime_labels has all 4 regimes")
        
        print("\n✅ TEST 1 PASSED: GET /api/v1/forecast/regime")
        print(f"   Current regime: {current_regime} ({regime_label})")
        print(f"   Regime probabilities: {json.dumps(regime_probs, indent=2)}")
        print(f"   Active weights: {json.dumps(active_weights, indent=2)}")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reconcile_signals_default():
    """Test POST /api/v1/forecast/reconcile-signals with empty body {}."""
    print("\n" + "="*80)
    print("TEST 2a: POST /api/v1/forecast/reconcile-signals (empty body {})")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/forecast/reconcile-signals"
        print(f"Requesting: {url}")
        print(f"Body: {{}}")
        
        response = requests.post(url, json={}, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        # Check composite_quant_score
        composite = data.get('composite_quant_score')
        if composite is None or not isinstance(composite, (int, float)):
            print(f"❌ FAILED: composite_quant_score missing or not numeric: {composite}")
            return False
        if not (0 <= composite <= 100):
            print(f"❌ FAILED: composite_quant_score={composite} not in range [0, 100]")
            return False
        print(f"✅ composite_quant_score={composite} (numeric in [0, 100])")
        
        # Check signals_used
        signals_used = data.get('signals_used')
        if not signals_used or not isinstance(signals_used, dict):
            print(f"❌ FAILED: signals_used missing or not a dict")
            return False
        
        expected_signals = ['technicals', 'macro_policy', 'chart_structure', 'news_flow']
        for signal in expected_signals:
            if signal not in signals_used:
                print(f"❌ FAILED: signal '{signal}' missing from signals_used")
                return False
        print(f"✅ signals_used has all 4 keys: {list(signals_used.keys())}")
        print(f"   Values: {json.dumps(signals_used, indent=2)}")
        
        # Check signals_overridden (should be empty for default body)
        signals_overridden = data.get('signals_overridden')
        if not isinstance(signals_overridden, list):
            print(f"❌ FAILED: signals_overridden not a list: {signals_overridden}")
            return False
        if len(signals_overridden) != 0:
            print(f"❌ FAILED: signals_overridden should be [] for empty body, got {signals_overridden}")
            return False
        print(f"✅ signals_overridden=[] (empty as expected)")
        
        # Check confidence_interval_24h
        confidence = data.get('confidence_interval_24h')
        if confidence and isinstance(confidence, dict):
            print(f"✅ confidence_interval_24h present: {confidence}")
        else:
            print(f"⚠️  confidence_interval_24h missing or invalid (optional)")
        
        print("\n✅ TEST 2a PASSED: POST /api/v1/forecast/reconcile-signals (empty body)")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2a FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reconcile_signals_override():
    """Test POST /api/v1/forecast/reconcile-signals with partial override."""
    print("\n" + "="*80)
    print("TEST 2b: POST /api/v1/forecast/reconcile-signals (with overrides)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/forecast/reconcile-signals"
        body = {"news_flow": 90, "technicals": 30}
        print(f"Requesting: {url}")
        print(f"Body: {json.dumps(body)}")
        
        response = requests.post(url, json=body, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        # Check signals_used reflects overrides
        signals_used = data.get('signals_used')
        if not signals_used:
            print(f"❌ FAILED: signals_used missing")
            return False
        
        if signals_used.get('news_flow') != 90:
            print(f"❌ FAILED: signals_used.news_flow={signals_used.get('news_flow')}, expected 90")
            return False
        print(f"✅ signals_used.news_flow=90 (override applied)")
        
        if signals_used.get('technicals') != 30:
            print(f"❌ FAILED: signals_used.technicals={signals_used.get('technicals')}, expected 30")
            return False
        print(f"✅ signals_used.technicals=30 (override applied)")
        
        # Check signals_overridden contains the overridden keys
        signals_overridden = data.get('signals_overridden')
        if not isinstance(signals_overridden, list):
            print(f"❌ FAILED: signals_overridden not a list")
            return False
        
        if 'news_flow' not in signals_overridden:
            print(f"❌ FAILED: 'news_flow' not in signals_overridden: {signals_overridden}")
            return False
        print(f"✅ 'news_flow' in signals_overridden")
        
        if 'technicals' not in signals_overridden:
            print(f"❌ FAILED: 'technicals' not in signals_overridden: {signals_overridden}")
            return False
        print(f"✅ 'technicals' in signals_overridden")
        
        # Check composite_quant_score is still valid
        composite = data.get('composite_quant_score')
        if composite is None or not isinstance(composite, (int, float)):
            print(f"❌ FAILED: composite_quant_score missing or not numeric")
            return False
        if not (0 <= composite <= 100):
            print(f"❌ FAILED: composite_quant_score={composite} not in range [0, 100]")
            return False
        print(f"✅ composite_quant_score={composite} (numeric in [0, 100])")
        
        # Check confidence_interval_24h
        confidence = data.get('confidence_interval_24h')
        if confidence and isinstance(confidence, dict):
            print(f"✅ confidence_interval_24h present")
        
        print("\n✅ TEST 2b PASSED: POST /api/v1/forecast/reconcile-signals (with overrides)")
        print(f"   Overridden signals: {signals_overridden}")
        print(f"   Composite score: {composite}")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2b FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reconcile_signals_single_override():
    """Test POST /api/v1/forecast/reconcile-signals with single override."""
    print("\n" + "="*80)
    print("TEST 2c: POST /api/v1/forecast/reconcile-signals (single override)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/forecast/reconcile-signals"
        body = {"technicals": 100}
        print(f"Requesting: {url}")
        print(f"Body: {json.dumps(body)}")
        
        response = requests.post(url, json=body, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        # Check signals_used.technicals == 100
        signals_used = data.get('signals_used')
        if signals_used.get('technicals') != 100:
            print(f"❌ FAILED: signals_used.technicals={signals_used.get('technicals')}, expected 100")
            return False
        print(f"✅ signals_used.technicals=100")
        
        # Check composite is valid numeric
        composite = data.get('composite_quant_score')
        if composite is None or not isinstance(composite, (int, float)):
            print(f"❌ FAILED: composite_quant_score missing or not numeric")
            return False
        if not (0 <= composite <= 100):
            print(f"❌ FAILED: composite_quant_score={composite} not in range [0, 100]")
            return False
        print(f"✅ composite_quant_score={composite} (valid numeric)")
        
        print("\n✅ TEST 2c PASSED: POST /api/v1/forecast/reconcile-signals (single override)")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2c FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_regression():
    """Test GET /api/v1/dashboard - decision.weights_mode == 'dynamic'."""
    print("\n" + "="*80)
    print("TEST 3: GET /api/v1/dashboard (regression - dynamic weights)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/dashboard"
        print(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        # Check decision object exists
        decision = data.get('decision')
        if not decision or not isinstance(decision, dict):
            print(f"❌ FAILED: decision object missing or not a dict")
            return False
        print("✅ decision object present")
        
        # Check weights_mode == 'dynamic'
        weights_mode = decision.get('weights_mode')
        if weights_mode != 'dynamic':
            print(f"❌ FAILED: decision.weights_mode='{weights_mode}', expected 'dynamic'")
            return False
        print(f"✅ decision.weights_mode='dynamic'")
        
        # Check components is a list with 4 items
        components = decision.get('components')
        if not components or not isinstance(components, list):
            print(f"❌ FAILED: decision.components missing or not a list")
            return False
        
        if len(components) != 4:
            print(f"❌ FAILED: decision.components has {len(components)} items, expected 4")
            return False
        print(f"✅ decision.components has 4 items")
        
        # Check component weights sum to ~100
        total_weight = sum(c.get('weight', 0) for c in components)
        if not (99 <= total_weight <= 101):
            print(f"❌ FAILED: component weights sum={total_weight}, expected ~100 (±1)")
            return False
        print(f"✅ component weights sum={total_weight} (within 99-101)")
        
        # Print component details
        print("   Components:")
        for c in components:
            print(f"     - {c.get('name')}: score={c.get('score')}, weight={c.get('weight')}%")
        
        # Check regime_engine or regime_analysis present
        regime_engine = decision.get('regime_engine')
        regime_analysis = data.get('regime_analysis')
        
        if regime_engine:
            print(f"✅ decision.regime_engine present")
            if isinstance(regime_engine, dict) and regime_engine.get('available'):
                print(f"   regime_engine.available=true")
            else:
                print(f"   regime_engine: {regime_engine}")
        elif regime_analysis:
            print(f"✅ top-level regime_analysis present")
            if isinstance(regime_analysis, dict) and regime_analysis.get('available'):
                print(f"   regime_analysis.available=true")
        else:
            print(f"⚠️  Neither decision.regime_engine nor regime_analysis found (may be computing)")
        
        print("\n✅ TEST 3 PASSED: GET /api/v1/dashboard (dynamic weights confirmed)")
        return True
        
    except Exception as e:
        print(f"❌ TEST 3 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_health_regression():
    """Test GET /api/v1/health (regression)."""
    print("\n" + "="*80)
    print("TEST 4: GET /api/v1/health (regression)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/health"
        print(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ok':
            print(f"❌ FAILED: Expected status='ok', got '{data.get('status')}'")
            return False
        print("✅ status='ok'")
        
        print(f"   compute_status: {data.get('compute_status')}")
        print(f"   runs: {data.get('runs')}")
        
        print("\n✅ TEST 4 PASSED: GET /api/v1/health")
        return True
        
    except Exception as e:
        print(f"❌ TEST 4 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scorecard_regression():
    """Test GET /api/v1/scorecard (regression)."""
    print("\n" + "="*80)
    print("TEST 5: GET /api/v1/scorecard (regression)")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/v1/scorecard"
        print(f"Requesting: {url}")
        
        response = requests.get(url, timeout=30)
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Expected HTTP 200, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        # Check status
        if data.get('status') != 'ready':
            print(f"❌ FAILED: Expected status='ready', got '{data.get('status')}'")
            return False
        print("✅ status='ready'")
        
        print(f"   total_logged: {data.get('total_logged')}")
        print(f"   backtested: {data.get('backtested')}")
        
        print("\n✅ TEST 5 PASSED: GET /api/v1/scorecard")
        return True
        
    except Exception as e:
        print(f"❌ TEST 5 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("DYNAMIC REGIME-SWITCHING ENGINE BACKEND TEST")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin passcode: 000000")
    print(f"DO NOT trigger any email endpoints")
    print("="*80)
    
    results = []
    
    # Test 1: GET /api/v1/forecast/regime
    results.append(("GET /api/v1/forecast/regime", test_forecast_regime()))
    
    # Test 2a: POST /api/v1/forecast/reconcile-signals (empty body)
    results.append(("POST /api/v1/forecast/reconcile-signals (empty body)", test_reconcile_signals_default()))
    
    # Test 2b: POST /api/v1/forecast/reconcile-signals (with overrides)
    results.append(("POST /api/v1/forecast/reconcile-signals (overrides)", test_reconcile_signals_override()))
    
    # Test 2c: POST /api/v1/forecast/reconcile-signals (single override)
    results.append(("POST /api/v1/forecast/reconcile-signals (single)", test_reconcile_signals_single_override()))
    
    # Test 3: GET /api/v1/dashboard (regression)
    results.append(("GET /api/v1/dashboard (regression)", test_dashboard_regression()))
    
    # Test 4: GET /api/v1/health (regression)
    results.append(("GET /api/v1/health (regression)", test_health_regression()))
    
    # Test 5: GET /api/v1/scorecard (regression)
    results.append(("GET /api/v1/scorecard (regression)", test_scorecard_regression()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
