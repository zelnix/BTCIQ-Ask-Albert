import requests
import json

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

print("=" * 80)
print("MODEL RELIABILITY BLOCK + REGRESSION TEST")
print("=" * 80)

# TEST 1: GET /api/v1/scorecard - Model Reliability block
print("\n[TEST 1] GET /api/v1/scorecard - Model Reliability block")
print("-" * 80)

try:
    response = requests.get(f"{BASE_URL}/v1/scorecard", timeout=30)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ HTTP 200 OK")
        
        # Check status
        if data.get("status") == "ready":
            print(f"✅ status='ready'")
        else:
            print(f"❌ status='{data.get('status')}' (expected 'ready')")
        
        # Check reliability object exists
        reliability = data.get("reliability")
        if reliability is None:
            print(f"❌ CRITICAL: 'reliability' object is missing from response")
        else:
            print(f"✅ 'reliability' object exists")
            
            # Validate n (int > 0)
            n = reliability.get("n")
            if isinstance(n, int) and n > 0:
                print(f"✅ n={n} (int > 0)")
            else:
                print(f"❌ n={n} (expected int > 0)")
            
            # Validate brier (float)
            brier = reliability.get("brier")
            if isinstance(brier, (int, float)):
                print(f"✅ brier={brier:.4f} (float)")
            else:
                print(f"❌ brier={brier} (expected float)")
            
            # Validate brier_baseline == 0.25
            brier_baseline = reliability.get("brier_baseline")
            if brier_baseline == 0.25:
                print(f"✅ brier_baseline={brier_baseline} (== 0.25)")
            else:
                print(f"❌ brier_baseline={brier_baseline} (expected 0.25)")
            
            # Validate brier_skill (float)
            brier_skill = reliability.get("brier_skill")
            if isinstance(brier_skill, (int, float)):
                print(f"✅ brier_skill={brier_skill:.4f} (float)")
            else:
                print(f"❌ brier_skill={brier_skill} (expected float)")
            
            # Validate ece (float)
            ece = reliability.get("ece")
            if isinstance(ece, (int, float)):
                print(f"✅ ece={ece:.2f} (float)")
            else:
                print(f"❌ ece={ece} (expected float)")
            
            # Validate grade (str)
            grade = reliability.get("grade")
            if isinstance(grade, str) and len(grade) > 0:
                print(f"✅ grade='{grade}' (non-empty string)")
            else:
                print(f"❌ grade='{grade}' (expected non-empty string)")
            
            # Validate curve (non-empty list)
            curve = reliability.get("curve")
            if isinstance(curve, list) and len(curve) > 0:
                print(f"✅ curve: {len(curve)} bins (non-empty list)")
                
                # Validate first curve item structure
                if len(curve) > 0:
                    first_bin = curve[0]
                    
                    # Check bin (str like "40-50")
                    bin_label = first_bin.get("bin")
                    if isinstance(bin_label, str) and "-" in bin_label:
                        print(f"✅ curve[0].bin='{bin_label}' (str like 'X-Y')")
                    else:
                        print(f"❌ curve[0].bin='{bin_label}' (expected str like 'X-Y')")
                    
                    # Check avg_pred (float 0-100)
                    avg_pred = first_bin.get("avg_pred")
                    if isinstance(avg_pred, (int, float)) and 0 <= avg_pred <= 100:
                        print(f"✅ curve[0].avg_pred={avg_pred:.2f} (float 0-100)")
                    else:
                        print(f"❌ curve[0].avg_pred={avg_pred} (expected float 0-100)")
                    
                    # Check realised_up (float 0-100)
                    realised_up = first_bin.get("realised_up")
                    if isinstance(realised_up, (int, float)) and 0 <= realised_up <= 100:
                        print(f"✅ curve[0].realised_up={realised_up:.2f} (float 0-100)")
                    else:
                        print(f"❌ curve[0].realised_up={realised_up} (expected float 0-100)")
                    
                    # Check n (int >= 3)
                    bin_n = first_bin.get("n")
                    if isinstance(bin_n, int) and bin_n >= 3:
                        print(f"✅ curve[0].n={bin_n} (int >= 3)")
                    else:
                        print(f"❌ curve[0].n={bin_n} (expected int >= 3)")
            else:
                print(f"❌ curve={curve} (expected non-empty list)")
            
            # Report observed values
            print(f"\n📊 OBSERVED VALUES:")
            print(f"   - n: {n}")
            print(f"   - brier: {brier:.4f}")
            print(f"   - brier_skill: {brier_skill:.4f}")
            print(f"   - ece: {ece:.2f}")
            print(f"   - grade: '{grade}'")
            print(f"   - curve bins: {len(curve)}")
            
    else:
        print(f"❌ HTTP {response.status_code} (expected 200)")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"❌ EXCEPTION: {str(e)}")

# TEST 2: REGRESSION - GET /api/v1/dashboard
print("\n[TEST 2] REGRESSION - GET /api/v1/dashboard")
print("-" * 80)

try:
    response = requests.get(f"{BASE_URL}/v1/dashboard", timeout=30)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ HTTP 200 OK")
        
        # Check status
        if data.get("status") == "ready":
            print(f"✅ status='ready'")
        else:
            print(f"❌ status='{data.get('status')}' (expected 'ready')")
        
        # Check decision.weights_mode == "dynamic"
        decision = data.get("decision", {})
        weights_mode = decision.get("weights_mode")
        if weights_mode == "dynamic":
            print(f"✅ decision.weights_mode='dynamic'")
        else:
            print(f"❌ decision.weights_mode='{weights_mode}' (expected 'dynamic')")
        
        # Check decision.scenarios_block present
        scenarios_block = decision.get("scenarios_block")
        if scenarios_block is not None:
            print(f"✅ decision.scenarios_block present")
            
            # Check scenarios list has 2 items
            scenarios = scenarios_block.get("scenarios", [])
            if len(scenarios) == 2:
                print(f"✅ decision.scenarios_block.scenarios: 2 scenarios")
            else:
                print(f"❌ decision.scenarios_block.scenarios: {len(scenarios)} scenarios (expected 2)")
            
            # Check contradiction object present
            contradiction = scenarios_block.get("contradiction")
            if contradiction is not None:
                print(f"✅ decision.scenarios_block.contradiction present")
            else:
                print(f"❌ decision.scenarios_block.contradiction missing")
        else:
            print(f"❌ decision.scenarios_block missing")
        
    else:
        print(f"❌ HTTP {response.status_code} (expected 200)")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"❌ EXCEPTION: {str(e)}")

# TEST 3: REGRESSION - GET /api/v1/forecast/regime
print("\n[TEST 3] REGRESSION - GET /api/v1/forecast/regime")
print("-" * 80)

try:
    response = requests.get(f"{BASE_URL}/v1/forecast/regime", timeout=30)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ HTTP 200 OK")
        
        # Check status
        if data.get("status") == "ready":
            print(f"✅ status='ready'")
        else:
            print(f"❌ status='{data.get('status')}' (expected 'ready')")
        
    else:
        print(f"❌ HTTP {response.status_code} (expected 200)")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"❌ EXCEPTION: {str(e)}")

# TEST 4: REGRESSION - GET /api/v1/data-audit
print("\n[TEST 4] REGRESSION - GET /api/v1/data-audit")
print("-" * 80)

try:
    response = requests.get(f"{BASE_URL}/v1/data-audit", timeout=30)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ HTTP 200 OK")
        
        # Check status
        if data.get("status") == "ready":
            print(f"✅ status='ready'")
        else:
            print(f"❌ status='{data.get('status')}' (expected 'ready')")
        
        # Check feeds count (should be 10: 6 core + 4 aux)
        feeds = data.get("feeds", [])
        if len(feeds) == 10:
            print(f"✅ feeds: 10 items (6 core + 4 aux)")
        else:
            print(f"❌ feeds: {len(feeds)} items (expected 10)")
        
    else:
        print(f"❌ HTTP {response.status_code} (expected 200)")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"❌ EXCEPTION: {str(e)}")

# TEST 5: REGRESSION - GET /api/v1/health
print("\n[TEST 5] REGRESSION - GET /api/v1/health")
print("-" * 80)

try:
    response = requests.get(f"{BASE_URL}/v1/health", timeout=30)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ HTTP 200 OK")
        
        # Check status
        if data.get("status") == "ok":
            print(f"✅ status='ok'")
        else:
            print(f"❌ status='{data.get('status')}' (expected 'ok')")
        
    else:
        print(f"❌ HTTP {response.status_code} (expected 200)")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"❌ EXCEPTION: {str(e)}")

print("\n" + "=" * 80)
print("TEST SUITE COMPLETE")
print("=" * 80)
