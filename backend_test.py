#!/usr/bin/env python3
"""
BTCIQ Backend Testing Script - Phase 2 Features
Tests via Next.js proxy at external base URL with /api/v1/... prefix
Data is REAL (ccxt Kraken) except clearly-flagged DEMO panels
"""
import os
import sys
import time
import json
import requests
from datetime import datetime

# Load base URL from .env
BASE_URL = os.environ.get('NEXT_PUBLIC_BASE_URL', 'https://quant-features.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api/v1"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def test_open_forecast_confidence():
    """A) P0 — Open Forecast confidence: GET /api/v1/scorecard and GET /api/v1/dashboard"""
    log("=" * 80)
    log("TEST A: Open Forecast Confidence (P0)")
    log("=" * 80)
    
    try:
        # Test GET /api/v1/scorecard
        log("Testing GET /api/v1/scorecard...")
        r = requests.get(f"{API_BASE}/scorecard", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        log(f"Response keys: {list(data.keys())}")
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Check pending forecasts
        pending = data.get('pending', [])
        log(f"Pending forecasts: {len(pending)}")
        assert len(pending) > 0, "Expected at least one pending forecast"
        
        # Validate each pending item has confidence and confidence_pct
        for i, item in enumerate(pending):
            log(f"\nPending item {i+1}:")
            log(f"  horizon: {item.get('horizon')}")
            log(f"  direction: {item.get('direction')}")
            log(f"  confidence: {item.get('confidence')}")
            log(f"  confidence_pct: {item.get('confidence_pct')}")
            
            # MUST have both fields
            assert 'confidence' in item, f"Item {i+1} missing 'confidence' field"
            assert 'confidence_pct' in item, f"Item {i+1} missing 'confidence_pct' field"
            
            # Validate confidence label
            conf_label = item['confidence']
            assert conf_label in ['Low', 'Moderate', 'High'], f"Invalid confidence label: {conf_label}"
            
            # Validate confidence_pct
            conf_pct = item['confidence_pct']
            assert isinstance(conf_pct, (int, float)), f"confidence_pct must be int, got {type(conf_pct)}"
            assert 0 <= conf_pct <= 100, f"confidence_pct must be 0-100, got {conf_pct}"
            
            # Check internal consistency (higher pct -> stronger label)
            prob_higher = item.get('prob_higher', 50)
            margin = abs(prob_higher - 50)
            expected_pct = round(margin / 50 * 100)
            
            # Allow some tolerance for rounding
            assert abs(conf_pct - expected_pct) <= 5, f"confidence_pct ({conf_pct}) not consistent with prob_higher ({prob_higher}), expected ~{expected_pct}"
            
            # Check label consistency
            if conf_pct > 45:
                assert conf_label == 'High', f"High pct ({conf_pct}) should have 'High' label, got {conf_label}"
            elif conf_pct > 20:
                assert conf_label == 'Moderate', f"Moderate pct ({conf_pct}) should have 'Moderate' label, got {conf_label}"
            else:
                assert conf_label == 'Low', f"Low pct ({conf_pct}) should have 'Low' label, got {conf_label}"
            
            # Check existing fields still present
            assert 'horizon' in item, "Missing 'horizon' field"
            assert 'direction' in item, "Missing 'direction' field"
            assert 'prob_higher' in item, "Missing 'prob_higher' field"
            assert 'target_date' in item, "Missing 'target_date' field"
        
        # Also check dashboard.prediction_ledger
        log("\nTesting GET /api/v1/dashboard -> prediction_ledger...")
        r2 = requests.get(f"{API_BASE}/dashboard", timeout=30)
        assert r2.status_code == 200, f"Dashboard request failed: {r2.status_code}"
        
        dash = r2.json()
        assert dash.get('status') == 'ready', "Dashboard not ready"
        
        pred_ledger = dash.get('prediction_ledger', {})
        assert pred_ledger, "Missing prediction_ledger in dashboard"
        
        dash_pending = pred_ledger.get('pending', [])
        log(f"Dashboard pending forecasts: {len(dash_pending)}")
        
        # Validate dashboard pending items too
        for item in dash_pending:
            assert 'confidence' in item, "Dashboard pending item missing 'confidence'"
            assert 'confidence_pct' in item, "Dashboard pending item missing 'confidence_pct'"
            assert item['confidence'] in ['Low', 'Moderate', 'High'], f"Invalid confidence: {item['confidence']}"
            assert 0 <= item['confidence_pct'] <= 100, f"Invalid confidence_pct: {item['confidence_pct']}"
        
        log("\n✅ TEST A PASSED: Open Forecast Confidence")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST A FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST A ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_smart_alerts():
    """B) Smart Alerts: GET /api/v1/alerts, POST /api/v1/alerts/ack"""
    log("\n" + "=" * 80)
    log("TEST B: Smart Alerts")
    log("=" * 80)
    
    try:
        # Test GET /api/v1/alerts
        log("Testing GET /api/v1/alerts...")
        r = requests.get(f"{API_BASE}/alerts", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        log(f"Response keys: {list(data.keys())}")
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Check required fields
        assert 'alerts' in data, "Missing 'alerts' field"
        assert 'unseen' in data, "Missing 'unseen' field"
        assert 'total' in data, "Missing 'total' field"
        
        alerts = data['alerts']
        unseen_count = data['unseen']
        total_count = data['total']
        
        log(f"Total alerts: {total_count}")
        log(f"Unseen alerts: {unseen_count}")
        log(f"Alerts returned: {len(alerts)}")
        
        assert isinstance(alerts, list), "alerts must be a list"
        assert isinstance(unseen_count, int), "unseen must be int"
        assert isinstance(total_count, int), "total must be int"
        
        # Validate alert structure
        if len(alerts) > 0:
            log("\nValidating alert structure (first alert):")
            alert = alerts[0]
            log(f"Alert: {json.dumps(alert, indent=2)}")
            
            required_fields = ['id', 'ts', 'as_of', 'category', 'severity', 'title', 'message', 'seen']
            for field in required_fields:
                assert field in alert, f"Alert missing required field: {field}"
            
            # Validate category
            valid_categories = ['Regime', 'Market State', 'Quant Score', 'Data Trust', 'Event Risk', 'Volatility']
            assert alert['category'] in valid_categories, f"Invalid category: {alert['category']}"
            
            # Validate severity
            valid_severities = ['high', 'warning', 'success', 'info']
            assert alert['severity'] in valid_severities, f"Invalid severity: {alert['severity']}"
            
            # Validate seen is boolean
            assert isinstance(alert['seen'], bool), f"seen must be boolean, got {type(alert['seen'])}"
            
            # Validate ts is ISO format
            try:
                datetime.fromisoformat(alert['ts'].replace('Z', '+00:00'))
            except Exception:
                raise AssertionError(f"Invalid ISO timestamp: {alert['ts']}")
        
        # Test POST /api/v1/alerts/ack with specific ID
        if len(alerts) > 0 and unseen_count > 0:
            # Find an unseen alert
            unseen_alert = next((a for a in alerts if not a['seen']), None)
            if unseen_alert:
                log(f"\nTesting POST /api/v1/alerts/ack with specific ID: {unseen_alert['id']}")
                r2 = requests.post(f"{API_BASE}/alerts/ack", 
                                  json={"ids": [unseen_alert['id']]}, 
                                  timeout=30)
                log(f"Status: {r2.status_code}")
                assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
                
                ack_data = r2.json()
                log(f"Response: {ack_data}")
                assert ack_data.get('status') == 'ok', f"Expected status='ok', got {ack_data.get('status')}"
        
        # Test POST /api/v1/alerts/ack with empty body (mark all seen)
        log("\nTesting POST /api/v1/alerts/ack with empty body (mark all seen)...")
        r3 = requests.post(f"{API_BASE}/alerts/ack", json={}, timeout=30)
        log(f"Status: {r3.status_code}")
        assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
        
        ack_all_data = r3.json()
        log(f"Response: {ack_all_data}")
        assert ack_all_data.get('status') == 'ok', f"Expected status='ok', got {ack_all_data.get('status')}"
        
        # Verify unseen count is now 0
        log("\nVerifying unseen count after ack all...")
        r4 = requests.get(f"{API_BASE}/alerts", timeout=30)
        data4 = r4.json()
        log(f"Unseen count after ack: {data4.get('unseen')}")
        assert data4.get('unseen') == 0, f"Expected unseen=0 after ack all, got {data4.get('unseen')}"
        
        # Test dashboard.smart_alerts
        log("\nTesting GET /api/v1/dashboard -> smart_alerts...")
        r5 = requests.get(f"{API_BASE}/dashboard", timeout=30)
        assert r5.status_code == 200, f"Dashboard request failed: {r5.status_code}"
        
        dash = r5.json()
        assert 'smart_alerts' in dash, "Missing smart_alerts in dashboard"
        
        smart_alerts = dash['smart_alerts']
        log(f"Dashboard smart_alerts keys: {list(smart_alerts.keys())}")
        assert 'alerts' in smart_alerts, "Missing 'alerts' in smart_alerts"
        assert 'unseen' in smart_alerts, "Missing 'unseen' in smart_alerts"
        assert 'total' in smart_alerts, "Missing 'total' in smart_alerts"
        
        log("\n✅ TEST B PASSED: Smart Alerts")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST B FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST B ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_time_machine():
    """C) Time Machine: GET /api/v1/replay"""
    log("\n" + "=" * 80)
    log("TEST C: Time Machine Historical Replay")
    log("=" * 80)
    
    try:
        # Test GET /api/v1/replay (no date - defaults to max_date)
        log("Testing GET /api/v1/replay (no date)...")
        r = requests.get(f"{API_BASE}/replay", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        log(f"Response keys: {list(data.keys())}")
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Validate required fields
        required_fields = ['pick_date', 'signal', 'confidence', 'close', 'next_close', 
                          'actual', 'move_pct', 'correct', 'window', 'rolling_accuracy',
                          'min_date', 'max_date', 'n']
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        log(f"\nReplay data:")
        log(f"  pick_date: {data['pick_date']}")
        log(f"  signal: {data['signal']}")
        log(f"  confidence: {data['confidence']}")
        log(f"  close: {data['close']}")
        log(f"  next_close: {data['next_close']}")
        log(f"  actual: {data['actual']}")
        log(f"  move_pct: {data['move_pct']}")
        log(f"  correct: {data['correct']}")
        log(f"  rolling_accuracy: {data['rolling_accuracy']}")
        log(f"  min_date: {data['min_date']}")
        log(f"  max_date: {data['max_date']}")
        log(f"  n: {data['n']}")
        
        # Validate signal
        assert data['signal'] in ['UP', 'DOWN'], f"Invalid signal: {data['signal']}"
        
        # Validate confidence is a number
        assert isinstance(data['confidence'], (int, float)), f"confidence must be number, got {type(data['confidence'])}"
        
        # Validate close and next_close > 0
        assert data['close'] > 0, f"close must be > 0, got {data['close']}"
        assert data['next_close'] > 0, f"next_close must be > 0, got {data['next_close']}"
        
        # Validate actual
        assert data['actual'] in ['UP', 'DOWN'], f"Invalid actual: {data['actual']}"
        
        # Validate correct is boolean
        assert isinstance(data['correct'], bool), f"correct must be boolean, got {type(data['correct'])}"
        
        # Validate logic: correct == (signal == actual)
        expected_correct = (data['signal'] == data['actual'])
        assert data['correct'] == expected_correct, f"correct logic error: signal={data['signal']}, actual={data['actual']}, correct={data['correct']}"
        
        # Validate logic: actual == 'UP' iff next_close > close
        expected_actual = 'UP' if data['next_close'] > data['close'] else 'DOWN'
        assert data['actual'] == expected_actual, f"actual logic error: next_close={data['next_close']}, close={data['close']}, actual={data['actual']}"
        
        # Validate window
        window = data['window']
        assert isinstance(window, list), "window must be a list"
        assert len(window) > 0, "window must be non-empty"
        
        log(f"\nWindow: {len(window)} items")
        
        # Check window structure
        for i, item in enumerate(window[:3]):  # Check first 3
            assert 'date' in item, f"Window item {i} missing 'date'"
            assert 'close' in item, f"Window item {i} missing 'close'"
            assert 'is_pick' in item, f"Window item {i} missing 'is_pick'"
        
        # Exactly one item should have is_pick=True
        pick_count = sum(1 for item in window if item.get('is_pick'))
        assert pick_count == 1, f"Expected exactly 1 is_pick=True, got {pick_count}"
        
        # Test GET /api/v1/replay?date=2025-11-15&window=20
        log("\nTesting GET /api/v1/replay?date=2025-11-15&window=20...")
        r2 = requests.get(f"{API_BASE}/replay?date=2025-11-15&window=20", timeout=30)
        log(f"Status: {r2.status_code}")
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
        
        data2 = r2.json()
        assert data2.get('status') == 'ready', f"Expected status='ready', got {data2.get('status')}"
        
        log(f"\nReplay for 2025-11-15:")
        log(f"  pick_date: {data2['pick_date']}")
        log(f"  signal: {data2['signal']}")
        log(f"  actual: {data2['actual']}")
        log(f"  correct: {data2['correct']}")
        log(f"  window length: {len(data2['window'])}")
        
        # pick_date should be ~2025-11-15 (nearest <=)
        pick_date = data2['pick_date']
        assert pick_date <= '2025-11-15', f"pick_date {pick_date} should be <= 2025-11-15"
        
        # Exactly one window item has is_pick=True
        pick_count2 = sum(1 for item in data2['window'] if item.get('is_pick'))
        assert pick_count2 == 1, f"Expected exactly 1 is_pick=True, got {pick_count2}"
        
        # The is_pick item should match pick_date
        pick_item = next((item for item in data2['window'] if item.get('is_pick')), None)
        assert pick_item is not None, "No is_pick=True item found"
        assert pick_item['date'] == pick_date, f"is_pick item date {pick_item['date']} != pick_date {pick_date}"
        
        log("\n✅ TEST C PASSED: Time Machine")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST C FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST C ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_engine():
    """D) Risk Engine: GET /api/v1/dashboard -> risk object"""
    log("\n" + "=" * 80)
    log("TEST D: Risk Engine")
    log("=" * 80)
    
    try:
        log("Testing GET /api/v1/dashboard -> risk...")
        r = requests.get(f"{API_BASE}/dashboard", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Check risk object exists
        assert 'risk' in data, "Missing 'risk' object in dashboard"
        
        risk = data['risk']
        log(f"\nRisk object keys: {list(risk.keys())}")
        
        # Validate required fields
        required_fields = ['level', 'score', 'state_scale', 'expected_move', 
                          'realised_vol_annual', 'vol_percentile', 'downside_zone',
                          'upside_zone', 'macro_event_risk', 'data_uncertainty', 
                          'drivers', 'demo', 'note']
        for field in required_fields:
            assert field in risk, f"Missing required field: {field}"
        
        # Validate level
        valid_levels = ['Low', 'Normal', 'Elevated', 'High', 'Extreme']
        assert risk['level'] in valid_levels, f"Invalid level: {risk['level']}"
        log(f"  level: {risk['level']}")
        
        # Validate score
        assert isinstance(risk['score'], int), f"score must be int, got {type(risk['score'])}"
        assert 0 <= risk['score'] <= 100, f"score must be 0-100, got {risk['score']}"
        log(f"  score: {risk['score']}")
        
        # Validate state_scale
        assert isinstance(risk['state_scale'], list), "state_scale must be list"
        assert len(risk['state_scale']) == 5, f"state_scale must have 5 items, got {len(risk['state_scale'])}"
        log(f"  state_scale: {risk['state_scale']}")
        
        # Validate expected_move
        expected_move = risk['expected_move']
        assert isinstance(expected_move, dict), "expected_move must be dict"
        for horizon in ['24H', '7D', '30D']:
            assert horizon in expected_move, f"Missing {horizon} in expected_move"
            move = expected_move[horizon]
            assert 'pct' in move, f"Missing 'pct' in {horizon}"
            assert 'low' in move, f"Missing 'low' in {horizon}"
            assert 'high' in move, f"Missing 'high' in {horizon}"
            
            # Validate ranges: low < close < high
            close = data.get('last_close', 0)
            assert move['low'] < close < move['high'], f"{horizon}: low ({move['low']}) < close ({close}) < high ({move['high']}) failed"
            log(f"  expected_move.{horizon}: {move['pct']}% (${move['low']} - ${move['high']})")
        
        # Validate realised_vol_annual
        assert isinstance(risk['realised_vol_annual'], (int, float)), "realised_vol_annual must be number"
        log(f"  realised_vol_annual: {risk['realised_vol_annual']}")
        
        # Validate vol_percentile
        assert isinstance(risk['vol_percentile'], int), "vol_percentile must be int"
        assert 0 <= risk['vol_percentile'] <= 100, f"vol_percentile must be 0-100, got {risk['vol_percentile']}"
        log(f"  vol_percentile: {risk['vol_percentile']}")
        
        # Validate downside_zone and upside_zone (can be null or object)
        if risk['downside_zone'] is not None:
            assert isinstance(risk['downside_zone'], dict), "downside_zone must be dict or null"
            assert 'price' in risk['downside_zone'], "downside_zone missing 'price'"
            assert 'distance_pct' in risk['downside_zone'], "downside_zone missing 'distance_pct'"
            log(f"  downside_zone: ${risk['downside_zone']['price']} ({risk['downside_zone']['distance_pct']}%)")
        
        if risk['upside_zone'] is not None:
            assert isinstance(risk['upside_zone'], dict), "upside_zone must be dict or null"
            assert 'price' in risk['upside_zone'], "upside_zone missing 'price'"
            assert 'distance_pct' in risk['upside_zone'], "upside_zone missing 'distance_pct'"
            log(f"  upside_zone: ${risk['upside_zone']['price']} ({risk['upside_zone']['distance_pct']}%)")
        
        # Validate macro_event_risk
        assert isinstance(risk['macro_event_risk'], str), "macro_event_risk must be string"
        log(f"  macro_event_risk: {risk['macro_event_risk']}")
        
        # Validate data_uncertainty
        assert isinstance(risk['data_uncertainty'], str), "data_uncertainty must be string"
        log(f"  data_uncertainty: {risk['data_uncertainty']}")
        
        # Validate drivers
        drivers = risk['drivers']
        assert isinstance(drivers, list), "drivers must be list"
        assert len(drivers) > 0, "drivers must be non-empty"
        log(f"  drivers: {len(drivers)} items")
        
        for driver in drivers:
            assert 'name' in driver, "driver missing 'name'"
            assert 'state' in driver, "driver missing 'state'"
            assert 'value' in driver, "driver missing 'value'"
            assert 'demo' in driver, "driver missing 'demo'"
            assert isinstance(driver['demo'], bool), "driver.demo must be boolean"
        
        # Validate demo object
        demo = risk['demo']
        assert isinstance(demo, dict), "demo must be dict"
        log(f"  demo keys: {list(demo.keys())}")
        
        # Validate note
        assert isinstance(risk['note'], str), "note must be string"
        assert len(risk['note']) > 0, "note must be non-empty"
        
        log("\n✅ TEST D PASSED: Risk Engine")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST D FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST D ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_smart_money_institutional():
    """E) Smart Money & Institutional DEMO: GET /api/v1/dashboard"""
    log("\n" + "=" * 80)
    log("TEST E: Smart Money & Institutional DEMO")
    log("=" * 80)
    
    try:
        log("Testing GET /api/v1/dashboard -> smart_money and institutional...")
        r = requests.get(f"{API_BASE}/dashboard", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Check smart_money object
        assert 'smart_money' in data, "Missing 'smart_money' object in dashboard"
        smart_money = data['smart_money']
        log(f"\nsmart_money keys: {list(smart_money.keys())}")
        
        # Validate smart_money
        assert smart_money.get('demo') == True, f"smart_money.demo must be True, got {smart_money.get('demo')}"
        assert 'source' in smart_money, "smart_money missing 'source'"
        assert 'needs key' in smart_money['source'].lower(), f"smart_money.source should mention 'needs key', got: {smart_money['source']}"
        assert 'headline' in smart_money, "smart_money missing 'headline'"
        assert isinstance(smart_money['headline'], str), "smart_money.headline must be string"
        assert len(smart_money['headline']) > 0, "smart_money.headline must be non-empty"
        
        # Validate metrics
        assert 'metrics' in smart_money, "smart_money missing 'metrics'"
        metrics = smart_money['metrics']
        assert isinstance(metrics, list), "smart_money.metrics must be list"
        assert len(metrics) > 0, "smart_money.metrics must be non-empty"
        
        log(f"  demo: {smart_money['demo']}")
        log(f"  source: {smart_money['source']}")
        log(f"  headline: {smart_money['headline']}")
        log(f"  metrics: {len(metrics)} items")
        
        for metric in metrics:
            assert 'name' in metric, "metric missing 'name'"
            assert 'value' in metric, "metric missing 'value'"
            assert 'signal' in metric, "metric missing 'signal'"
        
        # Check institutional object
        assert 'institutional' in data, "Missing 'institutional' object in dashboard"
        institutional = data['institutional']
        log(f"\ninstitutional keys: {list(institutional.keys())}")
        
        # Validate institutional
        assert institutional.get('demo') == True, f"institutional.demo must be True, got {institutional.get('demo')}"
        assert 'source' in institutional, "institutional missing 'source'"
        assert 'needs key' in institutional['source'].lower(), f"institutional.source should mention 'needs key', got: {institutional['source']}"
        assert 'headline' in institutional, "institutional missing 'headline'"
        assert isinstance(institutional['headline'], str), "institutional.headline must be string"
        assert len(institutional['headline']) > 0, "institutional.headline must be non-empty"
        
        # Validate metrics
        assert 'metrics' in institutional, "institutional missing 'metrics'"
        inst_metrics = institutional['metrics']
        assert isinstance(inst_metrics, list), "institutional.metrics must be list"
        assert len(inst_metrics) > 0, "institutional.metrics must be non-empty"
        
        log(f"  demo: {institutional['demo']}")
        log(f"  source: {institutional['source']}")
        log(f"  headline: {institutional['headline']}")
        log(f"  metrics: {len(inst_metrics)} items")
        
        for metric in inst_metrics:
            assert 'name' in metric, "metric missing 'name'"
            assert 'value' in metric, "metric missing 'value'"
            assert 'signal' in metric, "metric missing 'signal'"
        
        log("\n✅ TEST E PASSED: Smart Money & Institutional DEMO")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST E FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST E ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_manual_forecast_passcode():
    """F) Manual forecast passcode gate + audit"""
    log("\n" + "=" * 80)
    log("TEST F: Manual Forecast Passcode Gate + Audit")
    log("=" * 80)
    
    try:
        # Test 1: POST with no passcode
        log("Test 1: POST /api/v1/bitmark/run with no passcode...")
        r1 = requests.post(f"{API_BASE}/bitmark/run", json={}, timeout=30)
        log(f"Status: {r1.status_code}")
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"
        
        data1 = r1.json()
        log(f"Response: {data1}")
        assert data1.get('status') == 'unauthorized', f"Expected status='unauthorized', got {data1.get('status')}"
        
        # Test 2: POST with wrong passcode
        log("\nTest 2: POST /api/v1/bitmark/run with wrong passcode...")
        r2 = requests.post(f"{API_BASE}/bitmark/run", json={"passcode": "wrong"}, timeout=30)
        log(f"Status: {r2.status_code}")
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
        
        data2 = r2.json()
        log(f"Response: {data2}")
        assert data2.get('status') == 'unauthorized', f"Expected status='unauthorized', got {data2.get('status')}"
        
        # Test 3: POST with correct passcode
        log("\nTest 3: POST /api/v1/bitmark/run with correct passcode...")
        r3 = requests.post(f"{API_BASE}/bitmark/run", json={"passcode": "btciq-admin"}, timeout=30)
        log(f"Status: {r3.status_code}")
        assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
        
        data3 = r3.json()
        log(f"Response: {data3}")
        
        # Should be 'started', 'rate_limited', or 'busy' - all acceptable (means passcode accepted)
        valid_statuses = ['started', 'rate_limited', 'busy']
        assert data3.get('status') in valid_statuses, f"Expected status in {valid_statuses}, got {data3.get('status')}"
        
        # Must NOT be 'unauthorized'
        assert data3.get('status') != 'unauthorized', "Correct passcode should not return 'unauthorized'"
        
        log(f"✓ Passcode accepted, status: {data3.get('status')}")
        
        # Test 4: GET /api/v1/audit
        log("\nTest 4: GET /api/v1/audit...")
        r4 = requests.get(f"{API_BASE}/audit", timeout=30)
        log(f"Status: {r4.status_code}")
        assert r4.status_code == 200, f"Expected 200, got {r4.status_code}"
        
        data4 = r4.json()
        log(f"Response keys: {list(data4.keys())}")
        assert data4.get('status') == 'ready', f"Expected status='ready', got {data4.get('status')}"
        
        # Check entries
        assert 'entries' in data4, "Missing 'entries' field"
        entries = data4['entries']
        assert isinstance(entries, list), "entries must be list"
        assert len(entries) > 0, "Expected at least one audit entry"
        
        log(f"Audit entries: {len(entries)}")
        
        # Check for denied attempts
        denied_entries = [e for e in entries if e.get('result') == 'denied']
        log(f"Denied attempts: {len(denied_entries)}")
        
        # We should have at least 2 denied entries from our tests above
        assert len(denied_entries) >= 2, f"Expected at least 2 denied entries, got {len(denied_entries)}"
        
        # Validate entry structure
        if len(entries) > 0:
            entry = entries[0]
            log(f"\nFirst audit entry: {json.dumps(entry, indent=2)}")
            assert 'ts' in entry, "entry missing 'ts'"
            assert 'action' in entry, "entry missing 'action'"
            assert 'result' in entry, "entry missing 'result'"
        
        log("\n✅ TEST F PASSED: Manual Forecast Passcode Gate + Audit")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST F FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST F ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression():
    """G) REGRESSION: Verify all prior fields still present"""
    log("\n" + "=" * 80)
    log("TEST G: REGRESSION - All Prior Fields")
    log("=" * 80)
    
    try:
        # Test GET /api/v1/dashboard
        log("Testing GET /api/v1/dashboard...")
        r = requests.get(f"{API_BASE}/dashboard", timeout=30)
        log(f"Status: {r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        data = r.json()
        assert data.get('status') == 'ready', f"Expected status='ready', got {data.get('status')}"
        
        # Check all required prior fields
        required_fields = [
            'decision', 'forecasts', 'bitmark', 'data_health', 'event_calendar',
            'prediction_ledger', 'quant_score', 'regime', 'cycle', 'dominance',
            'policy', 'chart', 'smart_alerts', 'news_forecast_link'
        ]
        
        log("\nChecking required fields in dashboard:")
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            log(f"  ✓ {field}")
        
        # Test GET /api/v1/health
        log("\nTesting GET /api/v1/health...")
        r2 = requests.get(f"{API_BASE}/health", timeout=30)
        log(f"Status: {r2.status_code}")
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
        
        health = r2.json()
        log(f"Health: {health}")
        assert health.get('status') == 'ok', f"Expected status='ok', got {health.get('status')}"
        
        # Test POST /api/v1/chat (Albert persona)
        log("\nTesting POST /api/v1/chat (Albert persona)...")
        r3 = requests.post(f"{API_BASE}/chat", 
                          json={"session_id": "albert-test", "message": "Who are you?"}, 
                          timeout=30)
        log(f"Status: {r3.status_code}")
        assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
        
        chat = r3.json()
        log(f"Chat response keys: {list(chat.keys())}")
        assert 'model' in chat, "Missing 'model' field"
        assert chat['model'] == 'gemini-3-flash-preview', f"Expected model='gemini-3-flash-preview', got {chat['model']}"
        
        # Check if Albert identifies itself
        text = chat.get('text', '').lower()
        log(f"Chat text (first 200 chars): {chat.get('text', '')[:200]}")
        assert 'albert' in text, "Assistant should identify itself as 'Albert'"
        
        log("\n✅ TEST G PASSED: REGRESSION")
        return True
        
    except AssertionError as e:
        log(f"\n❌ TEST G FAILED: {e}")
        return False
    except Exception as e:
        log(f"\n❌ TEST G ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    log("=" * 80)
    log("BTCIQ BACKEND TESTING - PHASE 2 FEATURES")
    log(f"Base URL: {BASE_URL}")
    log(f"API Base: {API_BASE}")
    log("=" * 80)
    
    results = {}
    
    # Run all tests
    results['A_open_forecast_confidence'] = test_open_forecast_confidence()
    results['B_smart_alerts'] = test_smart_alerts()
    results['C_time_machine'] = test_time_machine()
    results['D_risk_engine'] = test_risk_engine()
    results['E_smart_money_institutional'] = test_smart_money_institutional()
    results['F_manual_forecast_passcode'] = test_manual_forecast_passcode()
    results['G_regression'] = test_regression()
    
    # Summary
    log("\n" + "=" * 80)
    log("TEST SUMMARY")
    log("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        log(f"{test_name}: {status}")
    
    log(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        log("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        log(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
