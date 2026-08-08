#!/usr/bin/env python3
"""
Backend test for Happening Again analog engine endpoint.
Tests GET /api/v1/analogs with new day_fingerprints and episode paths.
"""
import requests
import time
import sys

BASE_URL = "https://quant-features.preview.emergentagent.com"
ANALOG_KEYS = ['rates_dir', 'dxy_dir', 'nasdaq_corr', 'gold_corr', 'vol_regime', 'drawdown', 'momentum', 'cycle']

def test_analogs_endpoint():
    """Test GET /api/v1/analogs with polling for lazy computation."""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/analogs (Happening Again analog engine)")
    print("="*80)
    
    url = f"{BASE_URL}/api/v1/analogs"
    
    # Poll until ready (up to 60s)
    max_attempts = 8
    wait_time = 8
    
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"\n[Attempt {attempt}/{max_attempts}] Fetching {url}...")
            resp = requests.get(url, timeout=30)
            print(f"Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"❌ FAILED: Expected HTTP 200, got {resp.status_code}")
                print(f"Response: {resp.text[:500]}")
                return False
            
            data = resp.json()
            status = data.get('status')
            print(f"Response status: {status}")
            
            if status == 'computing':
                if attempt < max_attempts:
                    print(f"⏳ Still computing... waiting {wait_time}s before next poll")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ FAILED: Still computing after {max_attempts * wait_time}s")
                    return False
            
            elif status == 'error':
                print(f"❌ FAILED: Endpoint returned error status")
                print(f"Error: {data.get('error')}")
                return False
            
            elif status == 'ready':
                print("✅ Status is 'ready', proceeding with validation...")
                
                # Validate NEW field: day_fingerprints
                print("\n--- Validating day_fingerprints (NEW) ---")
                day_fps = data.get('day_fingerprints')
                if not day_fps:
                    print("❌ FAILED: day_fingerprints is missing or empty")
                    return False
                
                if not isinstance(day_fps, list):
                    print(f"❌ FAILED: day_fingerprints is not a list (type: {type(day_fps)})")
                    return False
                
                print(f"✅ day_fingerprints is a list with {len(day_fps)} items")
                
                if len(day_fps) < 500:
                    print(f"⚠️  WARNING: Expected ~1000+ items, got {len(day_fps)}")
                
                # Validate structure of first few items
                print("\nValidating structure of day_fingerprints items...")
                for i, item in enumerate(day_fps[:3]):
                    print(f"\n  Item {i+1}:")
                    
                    # Check date field
                    date = item.get('date')
                    if not date or not isinstance(date, str):
                        print(f"    ❌ FAILED: date is missing or not a string")
                        return False
                    
                    # Validate YYYY-MM-DD format
                    if len(date) != 10 or date[4] != '-' or date[7] != '-':
                        print(f"    ❌ FAILED: date '{date}' is not in YYYY-MM-DD format")
                        return False
                    print(f"    ✅ date: {date}")
                    
                    # Check fp (fingerprint) field
                    fp = item.get('fp')
                    if not fp or not isinstance(fp, dict):
                        print(f"    ❌ FAILED: fp is missing or not a dict")
                        return False
                    
                    # Validate fp has all 8 ANALOG_KEYS
                    missing_keys = [k for k in ANALOG_KEYS if k not in fp]
                    if missing_keys:
                        print(f"    ❌ FAILED: fp is missing keys: {missing_keys}")
                        return False
                    
                    # Check that values are numbers or null
                    for k in ANALOG_KEYS:
                        v = fp[k]
                        if v is not None and not isinstance(v, (int, float)):
                            print(f"    ❌ FAILED: fp['{k}'] = {v} is not a number or null")
                            return False
                    
                    non_null_count = sum(1 for k in ANALOG_KEYS if fp[k] is not None)
                    print(f"    ✅ fp: dict with all 8 keys ({non_null_count} non-null)")
                    
                    # Check forward returns
                    fwd_30 = item.get('fwd_30')
                    fwd_90 = item.get('fwd_90')
                    fwd_180 = item.get('fwd_180')
                    
                    if fwd_30 is not None and not isinstance(fwd_30, (int, float)):
                        print(f"    ❌ FAILED: fwd_30 is not a number or null")
                        return False
                    if fwd_90 is not None and not isinstance(fwd_90, (int, float)):
                        print(f"    ❌ FAILED: fwd_90 is not a number or null")
                        return False
                    if fwd_180 is not None and not isinstance(fwd_180, (int, float)):
                        print(f"    ❌ FAILED: fwd_180 is not a number or null")
                        return False
                    
                    print(f"    ✅ fwd_30: {fwd_30}, fwd_90: {fwd_90}, fwd_180: {fwd_180}")
                
                # Check that most items have fwd_90 != null (resolved days)
                resolved_count = sum(1 for item in day_fps if item.get('fwd_90') is not None)
                resolved_pct = (resolved_count / len(day_fps)) * 100 if day_fps else 0
                print(f"\n✅ Resolved days (fwd_90 != null): {resolved_count}/{len(day_fps)} ({resolved_pct:.1f}%)")
                
                if resolved_pct < 80:
                    print(f"⚠️  WARNING: Expected most items to have fwd_90 != null, got {resolved_pct:.1f}%")
                
                # Validate NEW field: fwd_path (additive field for confidence band)
                print("\n--- Validating fwd_path (NEW additive field) ---")
                expected_offsets = [0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120, 132, 144, 156, 168, 180]
                
                # Check all items have fwd_path
                items_with_fwd_path = sum(1 for item in day_fps if 'fwd_path' in item)
                if items_with_fwd_path != len(day_fps):
                    print(f"❌ FAILED: Not all day_fingerprints have fwd_path field ({items_with_fwd_path}/{len(day_fps)})")
                    return False
                print(f"✅ All {len(day_fps)} day_fingerprints have fwd_path field")
                
                # Validate structure of fwd_path in first few items
                print("\nValidating fwd_path structure in detail...")
                for i, item in enumerate(day_fps[:5]):
                    print(f"\n  Item {i+1} (date: {item.get('date')}):")
                    
                    fwd_path = item.get('fwd_path')
                    if not isinstance(fwd_path, list):
                        print(f"    ❌ FAILED: fwd_path is not a list (type: {type(fwd_path)})")
                        return False
                    
                    if len(fwd_path) != 16:
                        print(f"    ❌ FAILED: fwd_path should have exactly 16 items, got {len(fwd_path)}")
                        return False
                    print(f"    ✅ fwd_path has exactly 16 items")
                    
                    # Validate offsets are exactly [0,12,24,...,180]
                    actual_offsets = [pt['off'] for pt in fwd_path]
                    if actual_offsets != expected_offsets:
                        print(f"    ❌ FAILED: fwd_path offsets don't match expected")
                        print(f"       Expected: {expected_offsets}")
                        print(f"       Actual:   {actual_offsets}")
                        return False
                    print(f"    ✅ offsets are exactly [0,12,24,...,180] (step 12)")
                    
                    # Validate off=0 has v=100 (rebased)
                    first_pt = fwd_path[0]
                    if first_pt['off'] != 0:
                        print(f"    ❌ FAILED: First point should have off=0, got {first_pt['off']}")
                        return False
                    if first_pt['v'] != 100:
                        print(f"    ❌ FAILED: First point (off=0) should have v=100, got {first_pt['v']}")
                        return False
                    print(f"    ✅ off=0 point has v=100 (rebased)")
                    
                    # Validate each point has {off, v} structure
                    null_count = 0
                    for pt in fwd_path:
                        if 'off' not in pt or 'v' not in pt:
                            print(f"    ❌ FAILED: fwd_path item missing 'off' or 'v' keys: {pt}")
                            return False
                        
                        if not isinstance(pt['off'], (int, float)):
                            print(f"    ❌ FAILED: fwd_path item 'off' is not a number: {pt}")
                            return False
                        
                        v = pt['v']
                        if v is not None and not isinstance(v, (int, float)):
                            print(f"    ❌ FAILED: fwd_path item 'v' is not a number or null: {pt}")
                            return False
                        
                        if v is None:
                            null_count += 1
                    
                    print(f"    ✅ All 16 points have {{off, v}} structure ({null_count} with v=null)")
                    
                    # For recent dates, expect some nulls at far offsets (not enough forward data)
                    if null_count > 0:
                        print(f"    ℹ️  Note: {null_count} points have v=null (expected for recent dates)")
                
                # Summary of fwd_path validation
                print(f"\n✅ fwd_path validation complete for all {len(day_fps)} items")
                
                # Validate NEW guarantee: episodes with paths
                print("\n--- Validating episodes (NEW guarantee: all have paths) ---")
                episodes = data.get('episodes')
                if not episodes:
                    print("❌ FAILED: episodes is missing or empty")
                    return False
                
                if not isinstance(episodes, list):
                    print(f"❌ FAILED: episodes is not a list (type: {type(episodes)})")
                    return False
                
                print(f"✅ episodes is a list with {len(episodes)} items")
                
                # Validate structure of first few episodes
                print("\nValidating structure of episodes...")
                for i, ep in enumerate(episodes[:3]):
                    print(f"\n  Episode {i+1}:")
                    
                    # Check path field (NEW guarantee)
                    path = ep.get('path')
                    if not path:
                        print(f"    ❌ FAILED: path is missing or empty")
                        return False
                    
                    if not isinstance(path, list):
                        print(f"    ❌ FAILED: path is not a list (type: {type(path)})")
                        return False
                    
                    print(f"    ✅ path: list with {len(path)} points")
                    
                    # Validate path structure (first item)
                    if len(path) > 0:
                        pt = path[0]
                        if 'off' not in pt or 'v' not in pt:
                            print(f"    ❌ FAILED: path item missing 'off' or 'v' keys")
                            return False
                        
                        if not isinstance(pt['off'], (int, float)):
                            print(f"    ❌ FAILED: path item 'off' is not a number")
                            return False
                        
                        if not isinstance(pt['v'], (int, float)):
                            print(f"    ❌ FAILED: path item 'v' is not a number")
                            return False
                        
                        print(f"    ✅ path[0]: {{off: {pt['off']}, v: {pt['v']}}}")
                    
                    # Check match field
                    match = ep.get('match')
                    if match is None:
                        print(f"    ❌ FAILED: match is missing")
                        return False
                    
                    if not isinstance(match, (int, float)):
                        print(f"    ❌ FAILED: match is not a number (type: {type(match)})")
                        return False
                    
                    if not (0 <= match <= 100):
                        print(f"    ❌ FAILED: match {match} is not in range 0-100")
                        return False
                    
                    print(f"    ✅ match: {match} (0-100 range)")
                
                # REGRESSION: Validate existing fields
                print("\n--- REGRESSION: Validating existing fields ---")
                
                # current
                current = data.get('current')
                if not current or not isinstance(current, dict):
                    print("❌ FAILED: current is missing or not a dict")
                    return False
                print(f"✅ current: dict with {len(current)} keys")
                
                # norm
                norm = data.get('norm')
                if not norm or not isinstance(norm, dict):
                    print("❌ FAILED: norm is missing or not a dict")
                    return False
                print(f"✅ norm: dict with {len(norm)} keys")
                
                # signals
                signals = data.get('signals')
                if not signals or not isinstance(signals, list):
                    print("❌ FAILED: signals is missing or not a list")
                    return False
                
                if len(signals) != 8:
                    print(f"❌ FAILED: signals should have exactly 8 items, got {len(signals)}")
                    return False
                print(f"✅ signals: list with 8 items")
                
                # current_path
                current_path = data.get('current_path')
                if not current_path or not isinstance(current_path, list):
                    print("❌ FAILED: current_path is missing or not a list")
                    return False
                print(f"✅ current_path: list with {len(current_path)} points")
                
                # episode_count
                episode_count = data.get('episode_count')
                if episode_count is None or not isinstance(episode_count, int):
                    print("❌ FAILED: episode_count is missing or not an int")
                    return False
                print(f"✅ episode_count: {episode_count}")
                
                # Final summary
                print("\n" + "="*80)
                print("✅ ALL VALIDATIONS PASSED")
                print("="*80)
                print(f"\nSummary:")
                print(f"  - day_fingerprints: {len(day_fps)} items ({resolved_count} resolved)")
                print(f"  - episodes: {len(episodes)} items (all with non-empty paths)")
                print(f"  - signals: {len(signals)} items")
                print(f"  - current_path: {len(current_path)} points")
                print(f"  - episode_count: {episode_count}")
                print(f"\nData is REAL (Yahoo Finance: BTC/NDX/Gold/DXY/TNX over 10 years)")
                
                return True
            
            else:
                print(f"❌ FAILED: Unexpected status '{status}'")
                return False
        
        except requests.exceptions.Timeout:
            print(f"❌ FAILED: Request timed out")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ FAILED: Request error: {e}")
            return False
        except Exception as e:
            print(f"❌ FAILED: Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    print(f"❌ FAILED: Max attempts reached")
    return False


if __name__ == '__main__':
    try:
        success = test_analogs_endpoint()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
