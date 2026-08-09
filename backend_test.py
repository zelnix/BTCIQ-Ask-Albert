#!/usr/bin/env python3
"""
Backend test for multi-coin Happening Again analog engine
Tests GET /api/v1/analogs?symbol={BTC|ETH|SOL}
"""
import os
import sys
import time
import requests
from datetime import datetime

# Get base URL from environment
BASE_URL = os.getenv('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f'{BASE_URL}/api/v1'

def test_analog_engine_multi_coin():
    """Test the multi-coin analog engine for BTC, ETH, and SOL"""
    print("=" * 80)
    print("MULTI-COIN ANALOG ENGINE TEST")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Testing symbols: BTC, ETH, SOL")
    print()
    
    symbols = ['BTC', 'ETH', 'SOL']
    results = {}
    
    for symbol in symbols:
        print(f"\n{'=' * 80}")
        print(f"TESTING SYMBOL: {symbol}")
        print(f"{'=' * 80}\n")
        
        # Poll until ready (up to 70 seconds)
        url = f'{API_BASE}/analogs?symbol={symbol}'
        print(f"GET {url}")
        
        max_attempts = 9  # 9 attempts * 8 seconds = 72 seconds
        attempt = 0
        data = None
        
        while attempt < max_attempts:
            attempt += 1
            try:
                response = requests.get(url, timeout=30)
                print(f"  Attempt {attempt}: HTTP {response.status_code}")
                
                if response.status_code != 200:
                    print(f"  ❌ FAILED: Expected HTTP 200, got {response.status_code}")
                    results[symbol] = {'success': False, 'error': f'HTTP {response.status_code}'}
                    break
                
                data = response.json()
                status = data.get('status')
                print(f"  Status: {status}")
                
                if status == 'ready':
                    print(f"  ✅ Status is 'ready' after {attempt} attempt(s)")
                    results[symbol] = {'success': True, 'data': data, 'attempts': attempt}
                    break
                elif status == 'computing':
                    if attempt < max_attempts:
                        print(f"  ⏳ Computing... waiting 8 seconds before retry")
                        time.sleep(8)
                    else:
                        print(f"  ❌ FAILED: Still computing after {attempt} attempts (~{attempt*8}s)")
                        results[symbol] = {'success': False, 'error': 'timeout_computing'}
                        break
                elif status == 'error':
                    print(f"  ❌ FAILED: API returned status='error'")
                    print(f"  Error details: {data}")
                    results[symbol] = {'success': False, 'error': 'api_error', 'details': data}
                    break
                else:
                    print(f"  ❌ FAILED: Unexpected status '{status}'")
                    results[symbol] = {'success': False, 'error': f'unexpected_status_{status}'}
                    break
                    
            except requests.exceptions.Timeout:
                print(f"  ❌ FAILED: Request timeout")
                results[symbol] = {'success': False, 'error': 'request_timeout'}
                break
            except Exception as e:
                print(f"  ❌ FAILED: Exception: {e}")
                results[symbol] = {'success': False, 'error': str(e)}
                break
    
    print(f"\n{'=' * 80}")
    print("VALIDATION PHASE")
    print(f"{'=' * 80}\n")
    
    # Validate each symbol's response
    validation_results = {}
    
    for symbol in symbols:
        print(f"\n--- Validating {symbol} ---\n")
        
        if not results[symbol]['success']:
            print(f"❌ {symbol}: Skipping validation (fetch failed)")
            validation_results[symbol] = {'passed': False, 'reason': 'fetch_failed'}
            continue
        
        data = results[symbol]['data']
        checks = []
        
        # Check 1: symbol field matches requested symbol
        returned_symbol = data.get('symbol')
        if returned_symbol == symbol:
            print(f"✅ Check 1: symbol field = '{returned_symbol}' (matches requested)")
            checks.append(True)
        else:
            print(f"❌ Check 1: symbol field = '{returned_symbol}' (expected '{symbol}')")
            checks.append(False)
        
        # Check 2: signals array
        signals = data.get('signals', [])
        signal_keys = [s['key'] for s in signals]
        expected_common_keys = ['rates_dir', 'dxy_dir', 'nasdaq_corr', 'gold_corr', 'vol_regime', 'drawdown', 'momentum']
        
        if symbol == 'BTC':
            # BTC must have exactly 8 signals including 'cycle'
            if len(signals) == 8:
                print(f"✅ Check 2a: BTC has exactly 8 signals")
                checks.append(True)
            else:
                print(f"❌ Check 2a: BTC has {len(signals)} signals (expected 8)")
                checks.append(False)
            
            if 'cycle' in signal_keys:
                print(f"✅ Check 2b: BTC signals include 'cycle' key")
                checks.append(True)
            else:
                print(f"❌ Check 2b: BTC signals missing 'cycle' key")
                print(f"   Signal keys: {signal_keys}")
                checks.append(False)
            
            # Check all common keys are present
            missing = [k for k in expected_common_keys if k not in signal_keys]
            if not missing:
                print(f"✅ Check 2c: BTC has all 7 common signal keys")
                checks.append(True)
            else:
                print(f"❌ Check 2c: BTC missing signal keys: {missing}")
                checks.append(False)
        else:
            # ETH and SOL must have exactly 7 signals without 'cycle'
            if len(signals) == 7:
                print(f"✅ Check 2a: {symbol} has exactly 7 signals")
                checks.append(True)
            else:
                print(f"❌ Check 2a: {symbol} has {len(signals)} signals (expected 7)")
                checks.append(False)
            
            if 'cycle' not in signal_keys:
                print(f"✅ Check 2b: {symbol} signals do NOT include 'cycle' key (correct)")
                checks.append(True)
            else:
                print(f"❌ Check 2b: {symbol} signals incorrectly include 'cycle' key")
                print(f"   Signal keys: {signal_keys}")
                checks.append(False)
            
            # Check all common keys are present
            missing = [k for k in expected_common_keys if k not in signal_keys]
            if not missing:
                print(f"✅ Check 2c: {symbol} has all 7 expected signal keys")
                checks.append(True)
            else:
                print(f"❌ Check 2c: {symbol} missing signal keys: {missing}")
                checks.append(False)
        
        # Check 3: episodes array
        episodes = data.get('episodes', [])
        if len(episodes) > 0:
            print(f"✅ Check 3a: episodes is non-empty ({len(episodes)} episodes)")
            checks.append(True)
            
            # Validate first episode structure
            ep = episodes[0]
            required_ep_fields = ['match', 'path']
            missing_ep = [f for f in required_ep_fields if f not in ep]
            
            if not missing_ep:
                print(f"✅ Check 3b: First episode has required fields (match, path)")
                checks.append(True)
                
                # Validate match is 0-100
                match = ep.get('match')
                if isinstance(match, (int, float)) and 0 <= match <= 100:
                    print(f"✅ Check 3c: match = {match} (valid range 0-100)")
                    checks.append(True)
                else:
                    print(f"❌ Check 3c: match = {match} (invalid, expected 0-100)")
                    checks.append(False)
                
                # Validate path is non-empty list
                path = ep.get('path', [])
                if isinstance(path, list) and len(path) > 0:
                    print(f"✅ Check 3d: path is non-empty list ({len(path)} points)")
                    checks.append(True)
                    
                    # Validate path structure
                    if all(isinstance(p, dict) and 'off' in p and 'v' in p for p in path[:3]):
                        print(f"✅ Check 3e: path items have {{off, v}} structure")
                        checks.append(True)
                    else:
                        print(f"❌ Check 3e: path items missing {{off, v}} structure")
                        checks.append(False)
                else:
                    print(f"❌ Check 3d: path is empty or not a list")
                    checks.append(False)
            else:
                print(f"❌ Check 3b: First episode missing fields: {missing_ep}")
                checks.append(False)
        else:
            print(f"❌ Check 3a: episodes is empty")
            checks.append(False)
        
        # Check 4: day_fingerprints array
        day_fingerprints = data.get('day_fingerprints', [])
        if len(day_fingerprints) > 0:
            print(f"✅ Check 4a: day_fingerprints is non-empty ({len(day_fingerprints)} items)")
            checks.append(True)
            
            # Validate first day_fingerprint structure
            dfp = day_fingerprints[0]
            required_dfp_fields = ['date', 'fp', 'fwd_30', 'fwd_90', 'fwd_180', 'fwd_path']
            missing_dfp = [f for f in required_dfp_fields if f not in dfp]
            
            if not missing_dfp:
                print(f"✅ Check 4b: First day_fingerprint has all required fields")
                checks.append(True)
                
                # Validate date format
                date_str = dfp.get('date')
                try:
                    datetime.strptime(date_str, '%Y-%m-%d')
                    print(f"✅ Check 4c: date = '{date_str}' (valid YYYY-MM-DD format)")
                    checks.append(True)
                except Exception:
                    print(f"❌ Check 4c: date = '{date_str}' (invalid format)")
                    checks.append(False)
                
                # Validate fp is dict with signal keys
                fp = dfp.get('fp', {})
                if isinstance(fp, dict):
                    fp_keys = list(fp.keys())
                    if set(fp_keys) == set(signal_keys):
                        print(f"✅ Check 4d: fp dict keys match coin's signal keys")
                        checks.append(True)
                    else:
                        print(f"❌ Check 4d: fp dict keys don't match signal keys")
                        print(f"   fp keys: {fp_keys}")
                        print(f"   signal keys: {signal_keys}")
                        checks.append(False)
                else:
                    print(f"❌ Check 4d: fp is not a dict")
                    checks.append(False)
                
                # Validate fwd_path structure
                fwd_path = dfp.get('fwd_path', [])
                if isinstance(fwd_path, list) and len(fwd_path) == 16:
                    print(f"✅ Check 4e: fwd_path has exactly 16 points")
                    checks.append(True)
                    
                    # Check offsets are 0..180 step 12
                    offsets = [p['off'] for p in fwd_path if isinstance(p, dict) and 'off' in p]
                    expected_offsets = list(range(0, 181, 12))
                    if offsets == expected_offsets:
                        print(f"✅ Check 4f: fwd_path offsets are [0,12,24,...,180]")
                        checks.append(True)
                    else:
                        print(f"❌ Check 4f: fwd_path offsets incorrect")
                        print(f"   Got: {offsets}")
                        print(f"   Expected: {expected_offsets}")
                        checks.append(False)
                    
                    # Check off=0 has v=100
                    first_point = fwd_path[0] if fwd_path else {}
                    if first_point.get('off') == 0 and first_point.get('v') == 100:
                        print(f"✅ Check 4g: fwd_path[0] = {{off:0, v:100}} (rebased)")
                        checks.append(True)
                    else:
                        print(f"❌ Check 4g: fwd_path[0] incorrect: {first_point}")
                        checks.append(False)
                else:
                    print(f"❌ Check 4e: fwd_path has {len(fwd_path)} points (expected 16)")
                    checks.append(False)
            else:
                print(f"❌ Check 4b: First day_fingerprint missing fields: {missing_dfp}")
                checks.append(False)
        else:
            print(f"❌ Check 4a: day_fingerprints is empty")
            checks.append(False)
        
        # Check 5: current, norm, current_path, episode_count
        required_top_fields = ['current', 'norm', 'current_path', 'episode_count']
        missing_top = [f for f in required_top_fields if f not in data]
        
        if not missing_top:
            print(f"✅ Check 5a: All required top-level fields present")
            checks.append(True)
            
            # Validate current is dict
            current = data.get('current', {})
            if isinstance(current, dict) and len(current) > 0:
                print(f"✅ Check 5b: current is non-empty dict ({len(current)} keys)")
                checks.append(True)
            else:
                print(f"❌ Check 5b: current is empty or not a dict")
                checks.append(False)
            
            # Validate norm is dict
            norm = data.get('norm', {})
            if isinstance(norm, dict) and len(norm) > 0:
                print(f"✅ Check 5c: norm is non-empty dict ({len(norm)} keys)")
                checks.append(True)
            else:
                print(f"❌ Check 5c: norm is empty or not a dict")
                checks.append(False)
            
            # Validate current_path is non-empty list
            current_path = data.get('current_path', [])
            if isinstance(current_path, list) and len(current_path) > 0:
                print(f"✅ Check 5d: current_path is non-empty list ({len(current_path)} points)")
                checks.append(True)
            else:
                print(f"❌ Check 5d: current_path is empty or not a list")
                checks.append(False)
            
            # Validate episode_count
            episode_count = data.get('episode_count')
            if isinstance(episode_count, int) and episode_count > 0:
                print(f"✅ Check 5e: episode_count = {episode_count} (valid)")
                checks.append(True)
            else:
                print(f"❌ Check 5e: episode_count = {episode_count} (invalid)")
                checks.append(False)
        else:
            print(f"❌ Check 5a: Missing top-level fields: {missing_top}")
            checks.append(False)
        
        # Check 6: history_from field
        history_from = data.get('history_from')
        if history_from:
            print(f"✅ Check 6: history_from = '{history_from}'")
            checks.append(True)
        else:
            print(f"❌ Check 6: history_from missing or empty")
            checks.append(False)
        
        # Summary for this symbol
        passed = all(checks)
        total_checks = len(checks)
        passed_checks = sum(checks)
        
        print(f"\n{symbol} VALIDATION SUMMARY: {passed_checks}/{total_checks} checks passed")
        
        validation_results[symbol] = {
            'passed': passed,
            'checks_passed': passed_checks,
            'checks_total': total_checks,
            'history_from': history_from,
            'episode_count': data.get('episode_count'),
            'signal_count': len(signals),
            'signal_keys': signal_keys,
        }
    
    # Cross-symbol validation
    print(f"\n{'=' * 80}")
    print("CROSS-SYMBOL VALIDATION")
    print(f"{'=' * 80}\n")
    
    cross_checks = []
    
    # Check that all three symbols have different history_from dates
    if all(validation_results[s]['passed'] for s in symbols):
        history_dates = {s: validation_results[s]['history_from'] for s in symbols}
        print(f"History dates:")
        for s in symbols:
            print(f"  {s}: {history_dates[s]}")
        
        unique_dates = len(set(history_dates.values()))
        if unique_dates == 3:
            print(f"✅ All three symbols have DIFFERENT history_from dates")
            cross_checks.append(True)
        else:
            print(f"❌ Only {unique_dates} unique history_from dates (expected 3)")
            cross_checks.append(False)
        
        # Rough validation of expected history ranges
        # SOL ~2020, ETH ~2017, BTC ~2016
        btc_year = int(history_dates['BTC'][:4]) if history_dates.get('BTC') else 0
        eth_year = int(history_dates['ETH'][:4]) if history_dates.get('ETH') else 0
        sol_year = int(history_dates['SOL'][:4]) if history_dates.get('SOL') else 0
        
        if btc_year <= 2016:
            print(f"✅ BTC history starts ~2016 or earlier ({btc_year})")
            cross_checks.append(True)
        else:
            print(f"⚠️  BTC history starts {btc_year} (expected ~2016)")
            cross_checks.append(True)  # Not a hard failure
        
        if 2017 <= eth_year <= 2018:
            print(f"✅ ETH history starts ~2017 ({eth_year})")
            cross_checks.append(True)
        else:
            print(f"⚠️  ETH history starts {eth_year} (expected ~2017)")
            cross_checks.append(True)  # Not a hard failure
        
        if 2020 <= sol_year <= 2021:
            print(f"✅ SOL history starts ~2020 ({sol_year})")
            cross_checks.append(True)
        else:
            print(f"⚠️  SOL history starts {sol_year} (expected ~2020)")
            cross_checks.append(True)  # Not a hard failure
        
        # Check that episode counts are different (different price histories)
        episode_counts = {s: validation_results[s]['episode_count'] for s in symbols}
        print(f"\nEpisode counts:")
        for s in symbols:
            print(f"  {s}: {episode_counts[s]}")
        
        unique_counts = len(set(episode_counts.values()))
        if unique_counts >= 2:
            print(f"✅ Symbols have different episode counts (proving different histories)")
            cross_checks.append(True)
        else:
            print(f"⚠️  All symbols have same episode count (unusual but not necessarily wrong)")
            cross_checks.append(True)  # Not a hard failure
    else:
        print(f"❌ Cannot perform cross-symbol validation (some symbols failed)")
        cross_checks.append(False)
    
    # Final summary
    print(f"\n{'=' * 80}")
    print("FINAL TEST SUMMARY")
    print(f"{'=' * 80}\n")
    
    all_passed = all(validation_results[s]['passed'] for s in symbols) and all(cross_checks)
    
    for symbol in symbols:
        status = "✅ PASSED" if validation_results[symbol]['passed'] else "❌ FAILED"
        print(f"{symbol}: {status} ({validation_results[symbol]['checks_passed']}/{validation_results[symbol]['checks_total']} checks)")
    
    print(f"\nCross-symbol checks: {sum(cross_checks)}/{len(cross_checks)} passed")
    
    if all_passed:
        print(f"\n{'=' * 80}")
        print("🎉 ALL TESTS PASSED 🎉")
        print(f"{'=' * 80}")
        return 0
    else:
        print(f"\n{'=' * 80}")
        print("❌ SOME TESTS FAILED")
        print(f"{'=' * 80}")
        return 1

if __name__ == '__main__':
    try:
        exit_code = test_analog_engine_multi_coin()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ TEST SCRIPT EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
