import asyncio
import aiohttp
import sys

BASE_URL = "https://quant-features.preview.emergentagent.com/api"

async def test_data_audit():
    """Test the new real-time Data Audit endpoint"""
    print("\n" + "="*80)
    print("TEST 1 — GET /api/v1/data-audit (Real-time Data Audit)")
    print("="*80)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/v1/data-audit"
            print(f"\nRequesting: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                status_code = response.status
                data = await response.json()
                
                print(f"✅ HTTP {status_code}")
                
                # 1. Check status == "ready"
                if data.get("status") != "ready":
                    print(f"❌ FAIL: Expected status='ready', got '{data.get('status')}'")
                    return False
                print(f"✅ status='ready'")
                
                # 2. Check required fields
                required_fields = ["feeds", "score", "level", "live", "degraded", "stale", "faded", "note", "checked_at"]
                for field in required_fields:
                    if field not in data:
                        print(f"❌ FAIL: Missing required field '{field}'")
                        return False
                print(f"✅ All required fields present: {', '.join(required_fields)}")
                
                # 3. Validate score (int 0-100)
                score = data.get("score")
                if not isinstance(score, (int, float)) or not (0 <= score <= 100):
                    print(f"❌ FAIL: score={score} not in range [0, 100]")
                    return False
                print(f"✅ score={score} (int 0-100)")
                
                # 4. Validate level (str)
                level = data.get("level")
                valid_levels = ["High", "Good", "Degraded", "Low"]
                if level not in valid_levels:
                    print(f"❌ FAIL: level='{level}' not in {valid_levels}")
                    return False
                print(f"✅ level='{level}' (valid)")
                
                # 5. Validate counts (ints >= 0)
                live = data.get("live")
                degraded = data.get("degraded")
                stale = data.get("stale")
                if not all(isinstance(x, int) and x >= 0 for x in [live, degraded, stale]):
                    print(f"❌ FAIL: Invalid counts - live={live}, degraded={degraded}, stale={stale}")
                    return False
                print(f"✅ Counts: live={live}, degraded={degraded}, stale={stale} (all valid ints >= 0)")
                
                # 6. Validate faded (bool)
                faded = data.get("faded")
                if not isinstance(faded, bool):
                    print(f"❌ FAIL: faded={faded} not a boolean")
                    return False
                print(f"✅ faded={faded} (bool)")
                
                # 7. Validate note (str)
                note = data.get("note")
                if not isinstance(note, str):
                    print(f"❌ FAIL: note is not a string")
                    return False
                print(f"✅ note='{note[:60]}...' (string)")
                
                # 8. Validate checked_at (str)
                checked_at = data.get("checked_at")
                if not isinstance(checked_at, str):
                    print(f"❌ FAIL: checked_at is not a string")
                    return False
                print(f"✅ checked_at='{checked_at}' (string)")
                
                # 9. Validate feeds list
                feeds = data.get("feeds", [])
                if not isinstance(feeds, list) or len(feeds) == 0:
                    print(f"❌ FAIL: feeds is not a non-empty list")
                    return False
                print(f"✅ feeds: {len(feeds)} items (non-empty list)")
                
                # 10. Check for required CORE feeds (core=true)
                required_core_ids = ["price", "dominance", "crossmarket", "policy", "news", "fx"]
                core_feeds = [f for f in feeds if f.get("core") == True]
                core_ids = [f.get("id") for f in core_feeds]
                
                missing_core = [fid for fid in required_core_ids if fid not in core_ids]
                if missing_core:
                    print(f"❌ FAIL: Missing required CORE feeds: {missing_core}")
                    return False
                print(f"✅ All 6 CORE feeds present: {required_core_ids}")
                
                # 11. Check for required AUXILIARY feeds (core=false)
                required_aux_ids = ["etf", "onchain", "leverage", "sentiment"]
                aux_feeds = [f for f in feeds if f.get("core") == False]
                aux_ids = [f.get("id") for f in aux_feeds]
                
                missing_aux = [fid for fid in required_aux_ids if fid not in aux_ids]
                if missing_aux:
                    print(f"❌ FAIL: Missing required AUXILIARY feeds: {missing_aux}")
                    return False
                print(f"✅ All 4 AUXILIARY feeds present: {required_aux_ids}")
                
                # 12. Validate each feed has required fields
                print(f"\n--- Validating individual feeds ---")
                for feed in feeds:
                    feed_id = feed.get("id")
                    required_feed_fields = ["id", "label", "provider", "status", "confidence", "methodology", "core"]
                    missing_fields = [f for f in required_feed_fields if f not in feed]
                    if missing_fields:
                        print(f"❌ FAIL: Feed '{feed_id}' missing fields: {missing_fields}")
                        return False
                    
                    # Validate status
                    status = feed.get("status")
                    valid_statuses = ["live", "degraded", "stale", "down"]
                    if status not in valid_statuses:
                        print(f"❌ FAIL: Feed '{feed_id}' has invalid status '{status}'")
                        return False
                    
                    # Validate confidence (int 0-100)
                    confidence = feed.get("confidence")
                    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 100):
                        print(f"❌ FAIL: Feed '{feed_id}' has invalid confidence {confidence}")
                        return False
                    
                    # Validate core (bool)
                    core = feed.get("core")
                    if not isinstance(core, bool):
                        print(f"❌ FAIL: Feed '{feed_id}' has invalid core value {core}")
                        return False
                    
                    # Report feed details
                    age_min = feed.get("age_min", "N/A")
                    print(f"  ✅ {feed_id}: status={status}, age_min={age_min}, core={core}, confidence={confidence}")
                
                # 13. Validate that score is computed from CORE feeds only
                # The live/degraded/stale counts should equal counts among core feeds only
                core_live = sum(1 for f in core_feeds if f.get("status") == "live")
                core_degraded = sum(1 for f in core_feeds if f.get("status") == "degraded")
                core_stale = sum(1 for f in core_feeds if f.get("status") in ["stale", "down"])
                
                print(f"\n--- Validating score computation (CORE feeds only) ---")
                print(f"  Core feeds: live={core_live}, degraded={core_degraded}, stale={core_stale}")
                print(f"  Headline counts: live={live}, degraded={degraded}, stale={stale}")
                
                if live != core_live or degraded != core_degraded or stale != core_stale:
                    print(f"❌ FAIL: Headline counts do NOT match core feed counts")
                    print(f"  Expected (from core): live={core_live}, degraded={core_degraded}, stale={core_stale}")
                    print(f"  Got (headline): live={live}, degraded={degraded}, stale={stale}")
                    return False
                print(f"✅ Score computed from CORE feeds only (headline counts match core feed counts)")
                
                print(f"\n✅ TEST 1 PASSED - All validations successful")
                return True
                
        except asyncio.TimeoutError:
            print(f"❌ FAIL: Request timed out after 60s")
            return False
        except Exception as e:
            print(f"❌ FAIL: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_dashboard_regression():
    """Test that dashboard still works with decision.weights_mode == 'dynamic'"""
    print("\n" + "="*80)
    print("TEST 2 — GET /api/v1/dashboard (Regression)")
    print("="*80)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/v1/dashboard"
            print(f"\nRequesting: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                status_code = response.status
                data = await response.json()
                
                print(f"✅ HTTP {status_code}")
                
                # 1. Check status == "ready"
                if data.get("status") != "ready":
                    print(f"❌ FAIL: Expected status='ready', got '{data.get('status')}'")
                    return False
                print(f"✅ status='ready'")
                
                # 2. Check decision object exists
                decision = data.get("decision")
                if not decision:
                    print(f"❌ FAIL: Missing 'decision' object")
                    return False
                print(f"✅ decision object present")
                
                # 3. Check decision.weights_mode == "dynamic"
                weights_mode = decision.get("weights_mode")
                if weights_mode != "dynamic":
                    print(f"❌ FAIL: Expected weights_mode='dynamic', got '{weights_mode}'")
                    return False
                print(f"✅ decision.weights_mode='dynamic'")
                
                print(f"\n✅ TEST 2 PASSED - Dashboard regression successful")
                return True
                
        except asyncio.TimeoutError:
            print(f"❌ FAIL: Request timed out after 60s")
            return False
        except Exception as e:
            print(f"❌ FAIL: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_forecast_regime_regression():
    """Test that forecast/regime endpoint still works"""
    print("\n" + "="*80)
    print("TEST 3 — GET /api/v1/forecast/regime (Regression)")
    print("="*80)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/v1/forecast/regime"
            print(f"\nRequesting: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                status_code = response.status
                data = await response.json()
                
                print(f"✅ HTTP {status_code}")
                
                # 1. Check status == "ready"
                if data.get("status") != "ready":
                    print(f"❌ FAIL: Expected status='ready', got '{data.get('status')}'")
                    return False
                print(f"✅ status='ready'")
                
                print(f"\n✅ TEST 3 PASSED - Forecast regime regression successful")
                return True
                
        except asyncio.TimeoutError:
            print(f"❌ FAIL: Request timed out after 60s")
            return False
        except Exception as e:
            print(f"❌ FAIL: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    print("\n" + "="*80)
    print("REAL-TIME DATA AUDIT BACKEND TEST SUITE")
    print("Base URL:", BASE_URL)
    print("="*80)
    
    results = []
    
    # Test 1: Data Audit endpoint
    result1 = await test_data_audit()
    results.append(("Data Audit endpoint", result1))
    
    # Test 2: Dashboard regression
    result2 = await test_dashboard_regression()
    results.append(("Dashboard regression", result2))
    
    # Test 3: Forecast regime regression
    result3 = await test_forecast_regime_regression()
    results.append(("Forecast regime regression", result3))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Feature is production-ready")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
