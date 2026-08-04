#!/usr/bin/env python3
"""
Backend Test Suite for BTCIQ Dashboard - Three New Engines
Tests via external base URL + /api/v1/... (real browser path)
"""
import requests
import sys
from datetime import datetime

# External base URL from .env
BASE_URL = "https://quant-features.preview.emergentagent.com"

def test_engine_1_data_trust_layer():
    """ENGINE 1: Data Trust Layer (GET /api/v1/dashboard)"""
    print("\n" + "="*80)
    print("ENGINE 1 - DATA TRUST LAYER")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/api/v1/dashboard"
        print(f"Testing: GET {url}")
        resp = requests.get(url, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAILED: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        # Validate data_health object
        if 'data_health' not in data:
            print("❌ FAILED: Missing 'data_health' field")
            return False
        
        dh = data['data_health']
        print(f"\n✓ data_health object present")
        
        # Validate top-level fields
        required_fields = ['score', 'level', 'live', 'degraded', 'stale', 'faded', 'note', 'checked_at', 'feeds']
        for field in required_fields:
            if field not in dh:
                print(f"❌ FAILED: Missing data_health.{field}")
                return False
        print(f"✓ All required top-level fields present")
        
        # Validate score
        score = dh['score']
        if not isinstance(score, int) or not (0 <= score <= 100):
            print(f"❌ FAILED: score={score} not int 0-100")
            return False
        print(f"✓ score={score} (valid int 0-100)")
        
        # Validate level
        level = dh['level']
        if level not in ['High', 'Good', 'Degraded', 'Low']:
            print(f"❌ FAILED: level='{level}' not in [High,Good,Degraded,Low]")
            return False
        print(f"✓ level='{level}' (valid enum)")
        
        # Validate counts
        live = dh['live']
        degraded = dh['degraded']
        stale = dh['stale']
        if not all(isinstance(x, int) and x >= 0 for x in [live, degraded, stale]):
            print(f"❌ FAILED: Invalid counts: live={live}, degraded={degraded}, stale={stale}")
            return False
        print(f"✓ Counts: live={live}, degraded={degraded}, stale={stale}")
        
        # Validate faded
        faded = dh['faded']
        if not isinstance(faded, bool):
            print(f"❌ FAILED: faded={faded} not bool")
            return False
        print(f"✓ faded={faded} (bool)")
        
        # Validate note
        note = dh['note']
        if not isinstance(note, str) or not note:
            print(f"❌ FAILED: note is empty or not string")
            return False
        print(f"✓ note present ({len(note)} chars)")
        
        # Validate checked_at
        checked_at = dh['checked_at']
        try:
            datetime.fromisoformat(checked_at.replace('Z', ''))
            print(f"✓ checked_at='{checked_at}' (valid ISO format)")
        except Exception:
            print(f"❌ FAILED: checked_at='{checked_at}' not valid ISO format")
            return False
        
        # Validate feeds (must be exactly 6)
        feeds = dh['feeds']
        if not isinstance(feeds, list) or len(feeds) != 6:
            print(f"❌ FAILED: feeds has {len(feeds)} items, expected exactly 6")
            return False
        print(f"✓ feeds list has exactly 6 items")
        
        # Validate each feed
        feed_required = ['id', 'label', 'provider', 'status', 'updated', 'age_min', 'confidence', 'methodology']
        for i, feed in enumerate(feeds):
            for field in feed_required:
                if field not in feed:
                    print(f"❌ FAILED: feeds[{i}] missing '{field}'")
                    return False
            
            # Validate feed fields
            if not isinstance(feed['id'], str) or not feed['id']:
                print(f"❌ FAILED: feeds[{i}].id invalid")
                return False
            
            if not isinstance(feed['label'], str) or not feed['label']:
                print(f"❌ FAILED: feeds[{i}].label invalid")
                return False
            
            if not isinstance(feed['provider'], str) or not feed['provider']:
                print(f"❌ FAILED: feeds[{i}].provider invalid")
                return False
            
            if feed['status'] not in ['live', 'degraded', 'stale', 'down']:
                print(f"❌ FAILED: feeds[{i}].status='{feed['status']}' not in [live,degraded,stale,down]")
                return False
            
            if not isinstance(feed['confidence'], int) or not (0 <= feed['confidence'] <= 100):
                print(f"❌ FAILED: feeds[{i}].confidence={feed['confidence']} not int 0-100")
                return False
            
            if not isinstance(feed['methodology'], str) or not feed['methodology']:
                print(f"❌ FAILED: feeds[{i}].methodology invalid")
                return False
        
        print(f"✓ All 6 feeds validated successfully")
        
        # Expected: normally all feeds 'live' and score ~97
        live_feeds = sum(1 for f in feeds if f['status'] == 'live')
        print(f"✓ Live feeds: {live_feeds}/6 (expected: normally all 6)")
        if score >= 90:
            print(f"✓ Score {score} is healthy (>=90)")
        else:
            print(f"⚠ Minor: Score {score} is below 90 (expected ~97 normally)")
        
        # Validate decision.data_trust
        if 'decision' not in data:
            print("❌ FAILED: Missing 'decision' field")
            return False
        
        decision = data['decision']
        if 'data_trust' not in decision:
            print("❌ FAILED: Missing 'decision.data_trust' field")
            return False
        
        dt = decision['data_trust']
        print(f"\n✓ decision.data_trust object present")
        
        # Validate data_trust fields
        if 'score' not in dt or 'level' not in dt or 'faded' not in dt:
            print(f"❌ FAILED: decision.data_trust missing required fields")
            return False
        
        if not isinstance(dt['score'], int) or not (0 <= dt['score'] <= 100):
            print(f"❌ FAILED: decision.data_trust.score={dt['score']} not int 0-100")
            return False
        
        if dt['level'] not in ['High', 'Good', 'Degraded', 'Low']:
            print(f"❌ FAILED: decision.data_trust.level='{dt['level']}' invalid")
            return False
        
        if not isinstance(dt['faded'], bool):
            print(f"❌ FAILED: decision.data_trust.faded={dt['faded']} not bool")
            return False
        
        print(f"✓ decision.data_trust: score={dt['score']}, level='{dt['level']}', faded={dt['faded']}")
        
        # Validate decision.odds_faded
        if 'odds_faded' not in decision:
            print("❌ FAILED: Missing 'decision.odds_faded' field")
            return False
        
        if not isinstance(decision['odds_faded'], bool):
            print(f"❌ FAILED: decision.odds_faded={decision['odds_faded']} not bool")
            return False
        
        print(f"✓ decision.odds_faded={decision['odds_faded']} (bool)")
        
        # When faded=False, outlook items should NOT have 'faded' flag
        if not faded:
            outlook = decision.get('outlook', [])
            faded_items = [o for o in outlook if o.get('faded')]
            if faded_items:
                print(f"❌ FAILED: data_health.faded=False but {len(faded_items)} outlook items have 'faded' flag")
                return False
            print(f"✓ data_health.faded=False and no outlook items are shrunk (no 'faded' flag)")
        else:
            print(f"⚠ data_health.faded=True - odds are faded")
        
        print(f"\n✅ ENGINE 1 PASSED - Data Trust Layer validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_engine_2_prediction_ledger():
    """ENGINE 2: Prediction Ledger + Scorecard"""
    print("\n" + "="*80)
    print("ENGINE 2 - PREDICTION LEDGER + SCORECARD")
    print("="*80)
    
    try:
        # Test 1: GET /api/v1/dashboard -> validate prediction_ledger
        url = f"{BASE_URL}/api/v1/dashboard"
        print(f"\nTest 2.1: GET {url}")
        resp = requests.get(url, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAILED: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        if 'prediction_ledger' not in data:
            print("❌ FAILED: Missing 'prediction_ledger' field")
            return False
        
        pl = data['prediction_ledger']
        print(f"✓ prediction_ledger object present")
        
        # Validate required fields
        required_fields = ['overall', 'by_horizon', 'calibration', 'pending', 'recent', 
                          'total_logged', 'live_logged', 'backtested', 'model_version']
        for field in required_fields:
            if field not in pl:
                print(f"❌ FAILED: Missing prediction_ledger.{field}")
                return False
        print(f"✓ All required fields present")
        
        # Validate overall
        overall = pl['overall']
        if not isinstance(overall, dict):
            print(f"❌ FAILED: overall is not dict")
            return False
        
        overall_required = ['n', 'accuracy', 'brier', 'mae_pct', 'range_hit_pct']
        for field in overall_required:
            if field not in overall:
                print(f"❌ FAILED: Missing overall.{field}")
                return False
        
        n = overall['n']
        if not isinstance(n, int) or n < 0:
            print(f"❌ FAILED: overall.n={n} invalid")
            return False
        print(f"✓ overall.n={n} (total resolved predictions)")
        
        if n > 0:
            accuracy = overall['accuracy']
            if not isinstance(accuracy, (int, float)) or not (0 <= accuracy <= 100):
                print(f"❌ FAILED: overall.accuracy={accuracy} not in 0-100")
                return False
            print(f"✓ overall.accuracy={accuracy}%")
            
            brier = overall['brier']
            if brier is not None and (not isinstance(brier, (int, float)) or not (0 <= brier <= 1)):
                print(f"❌ FAILED: overall.brier={brier} not in 0-1")
                return False
            print(f"✓ overall.brier={brier}")
            
            mae_pct = overall['mae_pct']
            if mae_pct is not None and not isinstance(mae_pct, (int, float)):
                print(f"❌ FAILED: overall.mae_pct={mae_pct} invalid")
                return False
            print(f"✓ overall.mae_pct={mae_pct}")
            
            range_hit_pct = overall['range_hit_pct']
            if range_hit_pct is not None and (not isinstance(range_hit_pct, (int, float)) or not (0 <= range_hit_pct <= 100)):
                print(f"❌ FAILED: overall.range_hit_pct={range_hit_pct} not in 0-100")
                return False
            print(f"✓ overall.range_hit_pct={range_hit_pct}")
        
        # Validate by_horizon
        by_horizon = pl['by_horizon']
        if not isinstance(by_horizon, dict):
            print(f"❌ FAILED: by_horizon is not dict")
            return False
        print(f"✓ by_horizon: {list(by_horizon.keys())}")
        
        for hz, stats in by_horizon.items():
            if not isinstance(stats, dict):
                print(f"❌ FAILED: by_horizon[{hz}] is not dict")
                return False
            for field in ['n', 'accuracy', 'brier']:
                if field not in stats:
                    print(f"❌ FAILED: by_horizon[{hz}] missing '{field}'")
                    return False
        
        # Validate calibration
        calibration = pl['calibration']
        if not isinstance(calibration, list):
            print(f"❌ FAILED: calibration is not list")
            return False
        print(f"✓ calibration: {len(calibration)} buckets")
        
        for bucket in calibration:
            if not all(k in bucket for k in ['bucket', 'n', 'avg_pred', 'realised_up']):
                print(f"❌ FAILED: calibration bucket missing required fields")
                return False
        
        # Validate pending
        pending = pl['pending']
        if not isinstance(pending, list):
            print(f"❌ FAILED: pending is not list")
            return False
        print(f"✓ pending: {len(pending)} predictions")
        
        for p in pending[:3]:  # Check first 3
            required = ['horizon', 'direction', 'prob_higher', 'target_date']
            for field in required:
                if field not in p:
                    print(f"❌ FAILED: pending item missing '{field}'")
                    return False
            
            if p['direction'] not in ['UP', 'DOWN']:
                print(f"❌ FAILED: pending direction='{p['direction']}' not in [UP,DOWN]")
                return False
        
        # Validate recent
        recent = pl['recent']
        if not isinstance(recent, list):
            print(f"❌ FAILED: recent is not list")
            return False
        print(f"✓ recent: {len(recent)} predictions")
        
        # Validate counts
        total_logged = pl['total_logged']
        live_logged = pl['live_logged']
        backtested = pl['backtested']
        
        if not isinstance(total_logged, int) or total_logged <= 0:
            print(f"❌ FAILED: total_logged={total_logged} invalid")
            return False
        print(f"✓ total_logged={total_logged}")
        
        if not isinstance(live_logged, int) or live_logged < 0:
            print(f"❌ FAILED: live_logged={live_logged} invalid")
            return False
        print(f"✓ live_logged={live_logged}")
        
        if not isinstance(backtested, int) or backtested <= 0:
            print(f"❌ FAILED: backtested={backtested} invalid (expected ~500)")
            return False
        print(f"✓ backtested={backtested} (expected ~500 from walk-forward seed)")
        
        if backtested < 400:
            print(f"⚠ Minor: backtested count {backtested} is lower than expected ~500")
        
        # Validate model_version
        model_version = pl['model_version']
        if model_version != 'rf-quant-v1':
            print(f"❌ FAILED: model_version='{model_version}' != 'rf-quant-v1'")
            return False
        print(f"✓ model_version='{model_version}'")
        
        # Sanity check: overall.n should equal total resolved
        if n > 0 and n != total_logged:
            print(f"⚠ Minor: overall.n={n} != total_logged={total_logged} (may include unresolved)")
        
        # Test 2: GET /api/v1/scorecard
        url2 = f"{BASE_URL}/api/v1/scorecard"
        print(f"\nTest 2.2: GET {url2}")
        resp2 = requests.get(url2, timeout=30)
        
        if resp2.status_code != 200:
            print(f"❌ FAILED: HTTP {resp2.status_code}")
            return False
        
        scorecard = resp2.json()
        
        if scorecard.get('status') != 'ready':
            print(f"❌ FAILED: scorecard status='{scorecard.get('status')}' != 'ready'")
            return False
        print(f"✓ scorecard status='ready'")
        
        # Validate scorecard has same structure
        for field in required_fields:
            if field not in scorecard:
                print(f"❌ FAILED: scorecard missing '{field}'")
                return False
        print(f"✓ scorecard has all required fields")
        
        # Numbers should match dashboard's prediction_ledger
        if scorecard['total_logged'] != total_logged:
            print(f"❌ FAILED: scorecard.total_logged={scorecard['total_logged']} != dashboard {total_logged}")
            return False
        
        if scorecard['backtested'] != backtested:
            print(f"❌ FAILED: scorecard.backtested={scorecard['backtested']} != dashboard {backtested}")
            return False
        
        print(f"✓ scorecard numbers match dashboard prediction_ledger")
        
        print(f"\n✅ ENGINE 2 PASSED - Prediction Ledger + Scorecard validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_engine_3_event_calendar():
    """ENGINE 3: Event Intelligence Calendar"""
    print("\n" + "="*80)
    print("ENGINE 3 - EVENT INTELLIGENCE CALENDAR")
    print("="*80)
    
    try:
        url = f"{BASE_URL}/api/v1/dashboard"
        print(f"Testing: GET {url}")
        resp = requests.get(url, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAILED: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        if 'event_calendar' not in data:
            print("❌ FAILED: Missing 'event_calendar' field")
            return False
        
        ec = data['event_calendar']
        print(f"✓ event_calendar object present")
        
        # Validate required fields
        required_fields = ['window_days', 'generated', 'counts', 'events', 'next_high_impact']
        for field in required_fields:
            if field not in ec:
                print(f"❌ FAILED: Missing event_calendar.{field}")
                return False
        print(f"✓ All required fields present")
        
        # Validate window_days
        window_days = ec['window_days']
        if window_days != 120:
            print(f"❌ FAILED: window_days={window_days} != 120")
            return False
        print(f"✓ window_days=120")
        
        # Validate generated
        generated = ec['generated']
        try:
            datetime.strptime(generated, '%Y-%m-%d')
            print(f"✓ generated='{generated}' (valid YYYY-MM-DD)")
        except Exception:
            print(f"❌ FAILED: generated='{generated}' not valid YYYY-MM-DD")
            return False
        
        # Validate counts
        counts = ec['counts']
        if not isinstance(counts, dict):
            print(f"❌ FAILED: counts is not dict")
            return False
        print(f"✓ counts: {counts}")
        
        # Validate events
        events = ec['events']
        if not isinstance(events, list) or len(events) == 0:
            print(f"❌ FAILED: events is not non-empty list")
            return False
        print(f"✓ events: {len(events)} items")
        
        # Validate each event
        event_required = ['date', 'days_until', 'category', 'title', 'description', 
                         'importance', 'expected_volatility']
        
        prev_date = None
        for i, event in enumerate(events[:10]):  # Check first 10
            for field in event_required:
                if field not in event:
                    print(f"❌ FAILED: events[{i}] missing '{field}'")
                    return False
            
            # Validate date format
            date = event['date']
            try:
                event_date = datetime.strptime(date, '%Y-%m-%d')
            except Exception:
                print(f"❌ FAILED: events[{i}].date='{date}' not valid YYYY-MM-DD")
                return False
            
            # Check sorting (ascending by date)
            if prev_date and date < prev_date:
                print(f"❌ FAILED: events not sorted ascending by date (events[{i}].date={date} < prev={prev_date})")
                return False
            prev_date = date
            
            # Validate days_until
            days_until = event['days_until']
            if not isinstance(days_until, int) or not (0 <= days_until <= 120):
                print(f"❌ FAILED: events[{i}].days_until={days_until} not int 0-120")
                return False
            
            # Validate category
            category = event['category']
            if category not in ['Macro', 'Derivatives', 'On-Chain', 'Regulatory']:
                print(f"❌ FAILED: events[{i}].category='{category}' not in [Macro,Derivatives,On-Chain,Regulatory]")
                return False
            
            # Validate title
            title = event['title']
            if not isinstance(title, str) or not title:
                print(f"❌ FAILED: events[{i}].title invalid")
                return False
            
            # Validate description
            description = event['description']
            if not isinstance(description, str) or not description:
                print(f"❌ FAILED: events[{i}].description invalid")
                return False
            
            # Validate importance
            importance = event['importance']
            if importance not in ['Low', 'Medium', 'High', 'Very High']:
                print(f"❌ FAILED: events[{i}].importance='{importance}' not in [Low,Medium,High,Very High]")
                return False
            
            # Validate expected_volatility
            volatility = event['expected_volatility']
            if volatility not in ['Low', 'Elevated', 'High', 'Very High']:
                print(f"❌ FAILED: events[{i}].expected_volatility='{volatility}' not in [Low,Elevated,High,Very High]")
                return False
        
        print(f"✓ All events validated (checked first 10)")
        print(f"✓ Events sorted ascending by date")
        
        # Validate next_high_impact
        next_high = ec['next_high_impact']
        if next_high is not None:
            if not isinstance(next_high, dict):
                print(f"❌ FAILED: next_high_impact is not dict or null")
                return False
            
            if 'importance' not in next_high:
                print(f"❌ FAILED: next_high_impact missing 'importance'")
                return False
            
            importance = next_high['importance']
            if importance not in ['High', 'Very High']:
                print(f"❌ FAILED: next_high_impact.importance='{importance}' not in [High,Very High]")
                return False
            
            print(f"✓ next_high_impact: '{next_high.get('title')}' (importance={importance})")
        else:
            print(f"✓ next_high_impact=null (no high-impact events in window)")
        
        print(f"\n✅ ENGINE 3 PASSED - Event Intelligence Calendar validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_regression():
    """REGRESSION: Ensure all prior fields still present"""
    print("\n" + "="*80)
    print("REGRESSION - ALL PRIOR FIELDS PRESENT")
    print("="*80)
    
    try:
        # Test GET /api/v1/dashboard
        url = f"{BASE_URL}/api/v1/dashboard"
        print(f"\nTest: GET {url}")
        resp = requests.get(url, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAILED: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        if data.get('status') != 'ready':
            print(f"❌ FAILED: status='{data.get('status')}' != 'ready'")
            return False
        print(f"✓ status='ready'")
        
        # Check all prior fields
        prior_fields = [
            'decision', 'news_forecast_link', 'forecasts', 'long_outlook',
            'quant_score', 'regime', 'factors', 'scoreboard', 'trades',
            'policy', 'dominance', 'chart', 'cycle', 'alerts', 'signal',
            'confidence', 'prob_up', 'prob_down', 'last_close', 'data_source',
            'overall_accuracy', 'cv_folds', 'importances', 'performance', 'features'
        ]
        
        missing = []
        for field in prior_fields:
            if field not in data:
                missing.append(field)
        
        if missing:
            print(f"❌ FAILED: Missing prior fields: {missing}")
            return False
        
        print(f"✓ All {len(prior_fields)} prior fields present")
        
        # Validate decision has 6 outlook horizons
        decision = data['decision']
        outlook = decision.get('outlook', [])
        if len(outlook) != 6:
            print(f"❌ FAILED: decision.outlook has {len(outlook)} items, expected 6")
            return False
        
        horizons = [o['horizon'] for o in outlook]
        expected_horizons = ['24H', '7D', '30D', '3M', '6M', '1Y']
        if horizons != expected_horizons:
            print(f"❌ FAILED: decision.outlook horizons={horizons} != {expected_horizons}")
            return False
        print(f"✓ decision.outlook has 6 horizons: {horizons}")
        
        # Validate forecasts (3 items: 24H, 7D, 30D)
        forecasts = data['forecasts']
        if len(forecasts) != 3:
            print(f"❌ FAILED: forecasts has {len(forecasts)} items, expected 3")
            return False
        
        forecast_horizons = [f['horizon'] for f in forecasts]
        if forecast_horizons != ['24H', '7D', '30D']:
            print(f"❌ FAILED: forecast horizons={forecast_horizons} != ['24H','7D','30D']")
            return False
        print(f"✓ forecasts has 3 items: {forecast_horizons}")
        
        # Validate 24H and 7D have news_link
        for hz in ['24H', '7D']:
            f = next((x for x in forecasts if x['horizon'] == hz), None)
            if not f:
                print(f"❌ FAILED: Missing {hz} forecast")
                return False
            if 'news_link' not in f:
                print(f"❌ FAILED: {hz} forecast missing 'news_link'")
                return False
        print(f"✓ 24H and 7D forecasts have news_link")
        
        # Test GET /api/v1/ticker
        url2 = f"{BASE_URL}/api/v1/ticker"
        print(f"\nTest: GET {url2}")
        resp2 = requests.get(url2, timeout=30)
        
        if resp2.status_code != 200:
            print(f"❌ FAILED: HTTP {resp2.status_code}")
            return False
        
        ticker = resp2.json()
        
        ticker_fields = ['price', 'price_aud', 'aud_rate', 'change24h', 'source']
        for field in ticker_fields:
            if field not in ticker:
                print(f"❌ FAILED: ticker missing '{field}'")
                return False
        print(f"✓ ticker has all required fields: {ticker_fields}")
        
        # Test POST /api/v1/chat
        url3 = f"{BASE_URL}/api/v1/chat"
        print(f"\nTest: POST {url3}")
        payload = {"session_id": "test-regression", "message": "What is the current quant score?"}
        resp3 = requests.post(url3, json=payload, timeout=30)
        
        if resp3.status_code != 200:
            print(f"❌ FAILED: HTTP {resp3.status_code}")
            return False
        
        chat = resp3.json()
        
        if 'text' not in chat or 'model' not in chat:
            print(f"❌ FAILED: chat missing required fields")
            return False
        
        if chat.get('model') != 'gemini-3-flash-preview':
            print(f"❌ FAILED: chat model='{chat.get('model')}' != 'gemini-3-flash-preview'")
            return False
        print(f"✓ chat returns text and model='gemini-3-flash-preview'")
        
        # Test GET /api/v1/health
        url4 = f"{BASE_URL}/api/v1/health"
        print(f"\nTest: GET {url4}")
        resp4 = requests.get(url4, timeout=30)
        
        if resp4.status_code != 200:
            print(f"❌ FAILED: HTTP {resp4.status_code}")
            return False
        
        health = resp4.json()
        
        if 'compute_status' not in health or 'runs' not in health:
            print(f"❌ FAILED: health missing required fields")
            return False
        
        runs = health['runs']
        if not isinstance(runs, int) or runs <= 0:
            print(f"❌ FAILED: health.runs={runs} invalid")
            return False
        print(f"✓ health returns compute_status and runs={runs}")
        
        print(f"\n✅ REGRESSION PASSED - All prior fields present and working")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*80)
    print("BTCIQ DASHBOARD - THREE NEW ENGINES BACKEND TEST")
    print("Testing via external URL: " + BASE_URL)
    print("="*80)
    
    results = {}
    
    # Run all tests
    results['engine_1'] = test_engine_1_data_trust_layer()
    results['engine_2'] = test_engine_2_prediction_ledger()
    results['engine_3'] = test_engine_3_event_calendar()
    results['regression'] = test_regression()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
