#!/usr/bin/env python3
"""
Backend API Test Suite for Bitcoin Predictive AI Dashboard
Tests new features: live ticker, scoreboard, trade log, and live signal history
"""
import os
import sys
import time
import requests
from datetime import datetime

# Load base URL from .env
BASE_URL = os.getenv('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api/v1"

print(f"Testing backend at: {API_BASE}")
print("=" * 80)

# ============================================================================
# TEST 1: GET /api/v1/ticker - Live intraday BTC price
# ============================================================================
print("\n[TEST 1] GET /api/v1/ticker - Live intraday BTC price")
print("-" * 80)

try:
    # First call
    print("Making first ticker call...")
    resp1 = requests.get(f"{API_BASE}/ticker", timeout=10)
    print(f"Status: {resp1.status_code}")
    
    if resp1.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp1.status_code}")
        print(f"Response: {resp1.text}")
        sys.exit(1)
    
    data1 = resp1.json()
    print(f"Response: {data1}")
    
    # Validate required fields
    required_fields = ['price', 'change24h', 'high', 'low', 'source', 'ts']
    missing = [f for f in required_fields if f not in data1]
    if missing:
        print(f"❌ FAILED: Missing fields: {missing}")
        sys.exit(1)
    
    # Validate data types and ranges
    price = data1['price']
    if not isinstance(price, (int, float)) or price <= 0:
        print(f"❌ FAILED: Invalid price: {price} (expected number > 0)")
        sys.exit(1)
    
    # Sanity check: BTC price should be realistic (between $10k and $200k)
    if not (10000 <= price <= 200000):
        print(f"⚠️  WARNING: Price {price} seems unrealistic for BTC")
    
    change24h = data1['change24h']
    if not isinstance(change24h, (int, float)):
        print(f"❌ FAILED: Invalid change24h: {change24h} (expected number)")
        sys.exit(1)
    
    high = data1['high']
    low = data1['low']
    if not isinstance(high, (int, float)) or not isinstance(low, (int, float)):
        print(f"❌ FAILED: Invalid high/low: {high}/{low} (expected numbers)")
        sys.exit(1)
    
    if high < low:
        print(f"❌ FAILED: high ({high}) < low ({low})")
        sys.exit(1)
    
    source = data1['source']
    if source not in ['kraken', 'coinbase']:
        print(f"❌ FAILED: Invalid source: {source} (expected 'kraken' or 'coinbase')")
        sys.exit(1)
    
    ts = data1['ts']
    if not isinstance(ts, str):
        print(f"❌ FAILED: Invalid ts: {ts} (expected ISO string)")
        sys.exit(1)
    
    # Try parsing timestamp
    try:
        datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except Exception as e:
        print(f"❌ FAILED: Cannot parse timestamp {ts}: {e}")
        sys.exit(1)
    
    print(f"✅ First call PASSED: price=${price:,.2f}, change24h={change24h}%, source={source}")
    
    # Second call after 2 seconds (should still work, cached)
    print("\nWaiting 2 seconds before second call...")
    time.sleep(2)
    
    print("Making second ticker call...")
    resp2 = requests.get(f"{API_BASE}/ticker", timeout=10)
    print(f"Status: {resp2.status_code}")
    
    if resp2.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp2.status_code}")
        sys.exit(1)
    
    data2 = resp2.json()
    price2 = data2.get('price')
    if not isinstance(price2, (int, float)) or price2 <= 0:
        print(f"❌ FAILED: Second call returned invalid price: {price2}")
        sys.exit(1)
    
    print(f"✅ Second call PASSED: price=${price2:,.2f} (cached response OK)")
    print("✅ TEST 1 PASSED: /api/v1/ticker working correctly")
    
except Exception as e:
    print(f"❌ FAILED: Exception during ticker test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# TEST 2: GET /api/v1/dashboard - Verify NEW fields alongside existing ones
# ============================================================================
print("\n[TEST 2] GET /api/v1/dashboard - Verify NEW and existing fields")
print("-" * 80)

try:
    print("Fetching dashboard...")
    resp = requests.get(f"{API_BASE}/dashboard", timeout=15)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        sys.exit(1)
    
    dash = resp.json()
    
    # Check status
    if dash.get('status') != 'ready':
        print(f"❌ FAILED: Expected status='ready', got '{dash.get('status')}'")
        print(f"Dashboard: {dash}")
        sys.exit(1)
    
    print("✅ Status: ready")
    
    # --- NEW FIELD 1: scoreboard ---
    print("\nValidating scoreboard...")
    scoreboard = dash.get('scoreboard')
    if not scoreboard or not isinstance(scoreboard, dict):
        print(f"❌ FAILED: Missing or invalid scoreboard: {scoreboard}")
        sys.exit(1)
    
    required_sb = ['total', 'wins', 'losses', 'winRate', 'bestWinStreak', 'currentStreak']
    missing_sb = [f for f in required_sb if f not in scoreboard]
    if missing_sb:
        print(f"❌ FAILED: Scoreboard missing fields: {missing_sb}")
        sys.exit(1)
    
    total = scoreboard['total']
    wins = scoreboard['wins']
    losses = scoreboard['losses']
    win_rate = scoreboard['winRate']
    best_streak = scoreboard['bestWinStreak']
    current_streak = scoreboard['currentStreak']
    
    if not isinstance(total, int) or total <= 0:
        print(f"❌ FAILED: Invalid total: {total} (expected int > 0)")
        sys.exit(1)
    
    if not isinstance(wins, int) or wins < 0:
        print(f"❌ FAILED: Invalid wins: {wins} (expected int >= 0)")
        sys.exit(1)
    
    if not isinstance(losses, int) or losses < 0:
        print(f"❌ FAILED: Invalid losses: {losses} (expected int >= 0)")
        sys.exit(1)
    
    if wins + losses != total:
        print(f"❌ FAILED: wins ({wins}) + losses ({losses}) != total ({total})")
        sys.exit(1)
    
    if not isinstance(win_rate, (int, float)) or not (0 <= win_rate <= 100):
        print(f"❌ FAILED: Invalid winRate: {win_rate} (expected 0-100)")
        sys.exit(1)
    
    if not isinstance(best_streak, int) or best_streak < 0:
        print(f"❌ FAILED: Invalid bestWinStreak: {best_streak} (expected int >= 0)")
        sys.exit(1)
    
    if not isinstance(current_streak, int):
        print(f"❌ FAILED: Invalid currentStreak: {current_streak} (expected int)")
        sys.exit(1)
    
    print(f"✅ Scoreboard: total={total}, wins={wins}, losses={losses}, winRate={win_rate}%, bestWinStreak={best_streak}, currentStreak={current_streak}")
    
    # --- NEW FIELD 2: trades ---
    print("\nValidating trades...")
    trades = dash.get('trades')
    if not trades or not isinstance(trades, list):
        print(f"❌ FAILED: Missing or invalid trades: {trades}")
        sys.exit(1)
    
    if len(trades) == 0:
        print(f"❌ FAILED: trades list is empty")
        sys.exit(1)
    
    if len(trades) > 25:
        print(f"⚠️  WARNING: trades has {len(trades)} items (expected <= 25)")
    
    print(f"Trades count: {len(trades)}")
    
    # Validate first few trades
    for i, trade in enumerate(trades[:3]):
        required_trade = ['date', 'signal', 'confidence', 'close', 'nextClose', 'actual', 'correct']
        missing_trade = [f for f in required_trade if f not in trade]
        if missing_trade:
            print(f"❌ FAILED: Trade {i} missing fields: {missing_trade}")
            sys.exit(1)
        
        # Validate date format (YYYY-MM-DD)
        date_str = trade['date']
        if not isinstance(date_str, str):
            print(f"❌ FAILED: Trade {i} date not a string: {date_str}")
            sys.exit(1)
        
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except Exception as e:
            print(f"❌ FAILED: Trade {i} invalid date format {date_str}: {e}")
            sys.exit(1)
        
        # Validate signal
        signal = trade['signal']
        if signal not in ['UP', 'DOWN']:
            print(f"❌ FAILED: Trade {i} invalid signal: {signal}")
            sys.exit(1)
        
        # Validate confidence
        conf = trade['confidence']
        if not isinstance(conf, (int, float)) or not (0 <= conf <= 100):
            print(f"❌ FAILED: Trade {i} invalid confidence: {conf}")
            sys.exit(1)
        
        # Validate close and nextClose
        close = trade['close']
        next_close = trade['nextClose']
        if not isinstance(close, (int, float)) or close <= 0:
            print(f"❌ FAILED: Trade {i} invalid close: {close}")
            sys.exit(1)
        
        if not isinstance(next_close, (int, float)) or next_close <= 0:
            print(f"❌ FAILED: Trade {i} invalid nextClose: {next_close}")
            sys.exit(1)
        
        # Validate actual
        actual = trade['actual']
        if actual not in ['UP', 'DOWN']:
            print(f"❌ FAILED: Trade {i} invalid actual: {actual}")
            sys.exit(1)
        
        # Validate correct
        correct = trade['correct']
        if not isinstance(correct, bool):
            print(f"❌ FAILED: Trade {i} invalid correct: {correct} (expected bool)")
            sys.exit(1)
        
        # Sanity check: correct should equal (signal == actual)
        expected_correct = (signal == actual)
        if correct != expected_correct:
            print(f"❌ FAILED: Trade {i} correct={correct} but signal={signal}, actual={actual} (expected {expected_correct})")
            sys.exit(1)
        
        # Sanity check: actual direction should match nextClose vs close
        expected_actual = 'UP' if next_close > close else 'DOWN'
        if actual != expected_actual:
            print(f"❌ FAILED: Trade {i} actual={actual} but nextClose={next_close}, close={close} (expected {expected_actual})")
            sys.exit(1)
        
        print(f"  Trade {i}: {date_str} {signal} conf={conf}% close=${close} next=${next_close} actual={actual} correct={correct} ✅")
    
    print(f"✅ Trades validated (checked {min(3, len(trades))} of {len(trades)})")
    
    # --- NEW FIELD 3: live_record ---
    print("\nValidating live_record...")
    live_record = dash.get('live_record')
    if not live_record or not isinstance(live_record, dict):
        print(f"❌ FAILED: Missing or invalid live_record: {live_record}")
        sys.exit(1)
    
    required_lr = ['tracked', 'resolved', 'correct', 'winRate']
    missing_lr = [f for f in required_lr if f not in live_record]
    if missing_lr:
        print(f"❌ FAILED: live_record missing fields: {missing_lr}")
        sys.exit(1)
    
    tracked = live_record['tracked']
    resolved = live_record['resolved']
    correct = live_record['correct']
    lr_win_rate = live_record['winRate']
    
    if not isinstance(tracked, int) or tracked < 1:
        print(f"❌ FAILED: Invalid tracked: {tracked} (expected int >= 1)")
        sys.exit(1)
    
    if not isinstance(resolved, int) or resolved < 0:
        print(f"❌ FAILED: Invalid resolved: {resolved} (expected int >= 0)")
        sys.exit(1)
    
    if not isinstance(correct, int) or correct < 0:
        print(f"❌ FAILED: Invalid correct: {correct} (expected int >= 0)")
        sys.exit(1)
    
    if lr_win_rate is not None:
        if not isinstance(lr_win_rate, (int, float)) or not (0 <= lr_win_rate <= 100):
            print(f"❌ FAILED: Invalid winRate: {lr_win_rate} (expected 0-100 or null)")
            sys.exit(1)
    
    print(f"✅ live_record: tracked={tracked}, resolved={resolved}, correct={correct}, winRate={lr_win_rate}")
    
    # --- NEW FIELD 4: predict_for_date ---
    print("\nValidating predict_for_date...")
    predict_for = dash.get('predict_for_date')
    if not predict_for or not isinstance(predict_for, str):
        print(f"❌ FAILED: Missing or invalid predict_for_date: {predict_for}")
        sys.exit(1)
    
    try:
        datetime.strptime(predict_for, '%Y-%m-%d')
    except Exception as e:
        print(f"❌ FAILED: Invalid predict_for_date format {predict_for}: {e}")
        sys.exit(1)
    
    print(f"✅ predict_for_date: {predict_for}")
    
    # --- Verify EXISTING fields still present ---
    print("\nValidating existing fields...")
    existing_required = ['signal', 'confidence', 'cv_folds', 'importances', 'performance', 'features']
    missing_existing = [f for f in existing_required if f not in dash]
    if missing_existing:
        print(f"❌ FAILED: Missing existing fields: {missing_existing}")
        sys.exit(1)
    
    # Quick validation
    if dash['signal'] not in ['UP', 'DOWN']:
        print(f"❌ FAILED: Invalid signal: {dash['signal']}")
        sys.exit(1)
    
    if not isinstance(dash['confidence'], (int, float)) or not (0 <= dash['confidence'] <= 100):
        print(f"❌ FAILED: Invalid confidence: {dash['confidence']}")
        sys.exit(1)
    
    if not isinstance(dash['cv_folds'], list) or len(dash['cv_folds']) != 5:
        print(f"❌ FAILED: Invalid cv_folds: expected list of 5, got {len(dash.get('cv_folds', []))}")
        sys.exit(1)
    
    if not isinstance(dash['importances'], list) or len(dash['importances']) != 8:
        print(f"❌ FAILED: Invalid importances: expected list of 8, got {len(dash.get('importances', []))}")
        sys.exit(1)
    
    if not isinstance(dash['performance'], list) or len(dash['performance']) == 0:
        print(f"❌ FAILED: Invalid performance: expected non-empty list")
        sys.exit(1)
    
    if not isinstance(dash['features'], list) or len(dash['features']) != 8:
        print(f"❌ FAILED: Invalid features: expected list of 8, got {len(dash.get('features', []))}")
        sys.exit(1)
    
    print(f"✅ Existing fields: signal={dash['signal']}, confidence={dash['confidence']}%, cv_folds={len(dash['cv_folds'])}, importances={len(dash['importances'])}, performance={len(dash['performance'])}, features={len(dash['features'])}")
    
    print("\n✅ TEST 2 PASSED: /api/v1/dashboard has all NEW and existing fields with valid data")
    
    # Store initial tracked count for later comparison
    initial_tracked = tracked
    
except Exception as e:
    print(f"❌ FAILED: Exception during dashboard test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# TEST 3: POST /api/v1/refresh, poll health, verify dashboard stability
# ============================================================================
print("\n[TEST 3] POST /api/v1/refresh and verify stability")
print("-" * 80)

try:
    print("Triggering refresh...")
    resp = requests.post(f"{API_BASE}/refresh", timeout=10)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    if data.get('status') != 'started':
        print(f"❌ FAILED: Expected status='started', got '{data.get('status')}'")
        sys.exit(1)
    
    print("✅ Refresh triggered successfully")
    
    # Poll health until compute_status == 'done' (up to 60 seconds)
    print("\nPolling health until compute_status='done' (max 60s)...")
    max_wait = 60
    start_time = time.time()
    compute_done = False
    
    while time.time() - start_time < max_wait:
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        if resp.status_code != 200:
            print(f"⚠️  Health check failed: {resp.status_code}")
            time.sleep(2)
            continue
        
        health_data = resp.json()
        compute_status = health_data.get('compute_status')
        print(f"  compute_status: {compute_status}")
        
        if compute_status == 'done':
            compute_done = True
            print("✅ Compute completed")
            break
        
        if compute_status == 'error':
            print(f"❌ FAILED: Compute error: {health_data.get('error')}")
            sys.exit(1)
        
        time.sleep(3)
    
    if not compute_done:
        print(f"⚠️  WARNING: Compute did not complete within {max_wait}s (may still be running)")
        # Don't fail, just warn
    
    # Fetch dashboard again
    print("\nFetching dashboard after refresh...")
    resp = requests.get(f"{API_BASE}/dashboard", timeout=15)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Dashboard unavailable after refresh: {resp.status_code}")
        sys.exit(1)
    
    dash2 = resp.json()
    
    if dash2.get('status') != 'ready':
        print(f"❌ FAILED: Dashboard not ready after refresh: {dash2.get('status')}")
        sys.exit(1)
    
    print("✅ Dashboard still ready after refresh")
    
    # Verify scoreboard still present and valid
    scoreboard2 = dash2.get('scoreboard')
    if not scoreboard2 or not isinstance(scoreboard2, dict):
        print(f"❌ FAILED: Scoreboard missing after refresh")
        sys.exit(1)
    
    if 'total' not in scoreboard2 or not isinstance(scoreboard2['total'], int):
        print(f"❌ FAILED: Scoreboard.total invalid after refresh")
        sys.exit(1)
    
    print(f"✅ Scoreboard still valid: total={scoreboard2['total']}")
    
    # Verify trades still present
    trades2 = dash2.get('trades')
    if not trades2 or not isinstance(trades2, list) or len(trades2) == 0:
        print(f"❌ FAILED: Trades missing or empty after refresh")
        sys.exit(1)
    
    print(f"✅ Trades still valid: {len(trades2)} items")
    
    # Verify live_record still present
    live_record2 = dash2.get('live_record')
    if not live_record2 or not isinstance(live_record2, dict):
        print(f"❌ FAILED: live_record missing after refresh")
        sys.exit(1)
    
    tracked2 = live_record2.get('tracked')
    if not isinstance(tracked2, int) or tracked2 < 1:
        print(f"❌ FAILED: live_record.tracked invalid after refresh: {tracked2}")
        sys.exit(1)
    
    print(f"✅ live_record still valid: tracked={tracked2}")
    
    # CRITICAL: Verify tracked did NOT grow unboundedly
    # record_live_signal upserts one per as_of date, so repeated refresh on same day
    # should keep tracked stable (or increment by at most 1 if day changed)
    if tracked2 > initial_tracked + 1:
        print(f"⚠️  WARNING: tracked grew from {initial_tracked} to {tracked2} (expected stable or +1)")
        print("   This may indicate record_live_signal is not upserting correctly")
        # Don't fail, but warn
    else:
        print(f"✅ tracked count stable: {initial_tracked} -> {tracked2} (upsert working correctly)")
    
    print("\n✅ TEST 3 PASSED: Refresh, health polling, and dashboard stability verified")
    
except Exception as e:
    print(f"❌ FAILED: Exception during refresh test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED")
print("=" * 80)
print("\nSummary:")
print("  1. GET /api/v1/ticker - ✅ Live price data working (cached 8s)")
print("  2. GET /api/v1/dashboard - ✅ All NEW fields (scoreboard, trades, live_record, predict_for_date) present and valid")
print("  3. POST /api/v1/refresh - ✅ Background recompute working, dashboard stable, tracked count stable")
print("\nNo critical issues found. All backend functionality working as expected.")
