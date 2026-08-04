#!/usr/bin/env python3
"""
Comprehensive Backend Test for BTCIQ Dashboard
Tests all new features: Decision Engine, News→Forecast Link, Ask Quant Chat, Ticker AUD
"""
import requests
import json
import sys
import time

BASE_URL = "https://quant-features.preview.emergentagent.com/api/v1"

def log_pass(msg):
    print(f"✅ PASS: {msg}")

def log_fail(msg):
    print(f"❌ FAIL: {msg}")
    
def log_info(msg):
    print(f"ℹ️  INFO: {msg}")

def test_health():
    """Regression: GET /api/v1/health"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/health (REGRESSION)")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
        if r.status_code != 200:
            log_fail(f"Health endpoint returned {r.status_code}")
            return False
        data = r.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        # Validate required fields
        if data.get('status') != 'ok':
            log_fail(f"status is not 'ok': {data.get('status')}")
            return False
        log_pass("status = 'ok'")
        
        if 'compute_status' not in data:
            log_fail("compute_status field missing")
            return False
        log_pass(f"compute_status = '{data['compute_status']}'")
        
        if 'runs' not in data or not isinstance(data['runs'], int) or data['runs'] < 1:
            log_fail(f"runs field invalid: {data.get('runs')}")
            return False
        log_pass(f"runs = {data['runs']} (>= 1)")
        
        log_pass("GET /api/v1/health - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Health test exception: {e}")
        return False

def test_ticker():
    """FEATURE 4: GET /api/v1/ticker - validate price_aud field"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/ticker (FEATURE 4 - AUD PRICE)")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/ticker", timeout=15)
        if r.status_code != 200:
            log_fail(f"Ticker endpoint returned {r.status_code}")
            return False
        data = r.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        # Validate required fields
        required = ['price', 'price_aud', 'aud_rate', 'change24h', 'source']
        for field in required:
            if field not in data:
                log_fail(f"Missing required field: {field}")
                return False
        log_pass(f"All required fields present: {required}")
        
        # Validate price
        price = data['price']
        if not isinstance(price, (int, float)) or price <= 0:
            log_fail(f"Invalid price: {price}")
            return False
        log_pass(f"price = ${price:,.2f} (valid number > 0)")
        
        # Validate price_aud (NEW FEATURE)
        price_aud = data['price_aud']
        if price_aud is None:
            log_fail("price_aud is None (should be a number)")
            return False
        if not isinstance(price_aud, (int, float)) or price_aud <= 0:
            log_fail(f"Invalid price_aud: {price_aud}")
            return False
        log_pass(f"price_aud = ${price_aud:,.2f} (valid number > 0)")
        
        # Validate aud_rate
        aud_rate = data['aud_rate']
        if aud_rate is None:
            log_fail("aud_rate is None (should be a number)")
            return False
        if not isinstance(aud_rate, (int, float)) or aud_rate <= 0:
            log_fail(f"Invalid aud_rate: {aud_rate}")
            return False
        # AUD rate should be around 1.3-1.7 (AUD is weaker than USD)
        if not (1.0 < aud_rate < 2.0):
            log_fail(f"aud_rate {aud_rate} outside expected range 1.0-2.0")
            return False
        log_pass(f"aud_rate = {aud_rate} (valid, in range 1.0-2.0)")
        
        # Validate price_aud ≈ price * aud_rate
        expected_aud = price * aud_rate
        diff_pct = abs(price_aud - expected_aud) / expected_aud * 100
        if diff_pct > 1.0:
            log_fail(f"price_aud ({price_aud}) != price * aud_rate ({expected_aud:.2f}), diff {diff_pct:.2f}%")
            return False
        log_pass(f"price_aud ≈ price * aud_rate (diff {diff_pct:.3f}%)")
        
        # Validate price_aud > price (since AUD > USD)
        if price_aud <= price:
            log_fail(f"price_aud ({price_aud}) should be > price ({price}) since AUD > USD")
            return False
        log_pass(f"price_aud (${price_aud:,.2f}) > price (${price:,.2f}) ✓")
        
        # Validate change24h
        if not isinstance(data['change24h'], (int, float)):
            log_fail(f"Invalid change24h: {data['change24h']}")
            return False
        log_pass(f"change24h = {data['change24h']}%")
        
        # Validate source
        if data['source'] not in ['kraken', 'coinbase']:
            log_fail(f"Invalid source: {data['source']}")
            return False
        log_pass(f"source = '{data['source']}'")
        
        log_pass("GET /api/v1/ticker - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Ticker test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard_decision():
    """FEATURE 1: GET /api/v1/dashboard - validate decision object"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/dashboard - DECISION ENGINE (FEATURE 1)")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/dashboard", timeout=20)
        if r.status_code != 200:
            log_fail(f"Dashboard endpoint returned {r.status_code}")
            return False
        data = r.json()
        
        if data.get('status') != 'ready':
            log_fail(f"Dashboard status is not 'ready': {data.get('status')}")
            return False
        log_pass("status = 'ready'")
        
        # Validate decision object exists
        if 'decision' not in data:
            log_fail("decision object missing from dashboard")
            return False
        log_pass("decision object present")
        
        decision = data['decision']
        log_info(f"Decision keys: {list(decision.keys())}")
        
        # Validate overall_score
        if 'overall_score' not in decision:
            log_fail("decision.overall_score missing")
            return False
        score = decision['overall_score']
        if not isinstance(score, int) or not (0 <= score <= 100):
            log_fail(f"overall_score invalid: {score} (should be int 0-100)")
            return False
        log_pass(f"overall_score = {score} (int 0-100)")
        
        # Validate label
        if 'label' not in decision or not decision['label']:
            log_fail("decision.label missing or empty")
            return False
        log_pass(f"label = '{decision['label']}' (non-empty)")
        
        # Validate regime
        if 'regime' not in decision or not decision['regime']:
            log_fail("decision.regime missing or empty")
            return False
        log_pass(f"regime = '{decision['regime']}' (non-empty)")
        
        # Validate regime_description
        if 'regime_description' not in decision or not decision['regime_description']:
            log_fail("decision.regime_description missing or empty")
            return False
        log_pass(f"regime_description present (len={len(decision['regime_description'])})")
        
        # Validate alignment
        if 'alignment' not in decision or not decision['alignment']:
            log_fail("decision.alignment missing or empty")
            return False
        log_pass(f"alignment = '{decision['alignment']}' (non-empty)")
        
        # Validate components (should be exactly 4)
        if 'components' not in decision:
            log_fail("decision.components missing")
            return False
        components = decision['components']
        if not isinstance(components, list) or len(components) != 4:
            log_fail(f"components should be list of 4 items, got {len(components)}")
            return False
        log_pass(f"components has exactly 4 items")
        
        # Validate component names
        expected_names = ['Technicals', 'Macro / Policy', 'Chart Structure', 'News Flow']
        actual_names = [c['name'] for c in components]
        if actual_names != expected_names:
            log_fail(f"Component names mismatch. Expected {expected_names}, got {actual_names}")
            return False
        log_pass(f"Component names correct: {actual_names}")
        
        # Validate each component
        for comp in components:
            if 'score' not in comp or not isinstance(comp['score'], int) or not (0 <= comp['score'] <= 100):
                log_fail(f"Component {comp.get('name')} has invalid score: {comp.get('score')}")
                return False
            if 'weight' not in comp or not isinstance(comp['weight'], int):
                log_fail(f"Component {comp.get('name')} has invalid weight: {comp.get('weight')}")
                return False
        log_pass("All components have valid score (0-100) and weight (int)")
        
        # Validate risk_level
        if 'risk_level' not in decision:
            log_fail("decision.risk_level missing")
            return False
        risk_level = decision['risk_level']
        valid_levels = ['Low', 'Moderate', 'Elevated', 'High', 'Extreme']
        if risk_level not in valid_levels:
            log_fail(f"risk_level '{risk_level}' not in {valid_levels}")
            return False
        log_pass(f"risk_level = '{risk_level}' (valid)")
        
        # Validate risk_score
        if 'risk_score' not in decision:
            log_fail("decision.risk_score missing")
            return False
        risk_score = decision['risk_score']
        if not isinstance(risk_score, int) or not (0 <= risk_score <= 100):
            log_fail(f"risk_score invalid: {risk_score} (should be int 0-100)")
            return False
        log_pass(f"risk_score = {risk_score} (int 0-100)")
        
        # Validate risk_drivers
        if 'risk_drivers' not in decision:
            log_fail("decision.risk_drivers missing")
            return False
        risk_drivers = decision['risk_drivers']
        required_drivers = ['volatility_percentile', 'event_risk', 'news_risk']
        for driver in required_drivers:
            if driver not in risk_drivers:
                log_fail(f"risk_drivers.{driver} missing")
                return False
        log_pass(f"risk_drivers has all required fields: {required_drivers}")
        
        # Validate outlook (should be 6 items: 24H, 7D, 30D, 3M, 6M, 1Y)
        if 'outlook' not in decision:
            log_fail("decision.outlook missing")
            return False
        outlook = decision['outlook']
        if not isinstance(outlook, list) or len(outlook) != 6:
            log_fail(f"outlook should be list of 6 items, got {len(outlook)}")
            return False
        log_pass(f"outlook has exactly 6 items")
        
        # Validate outlook horizons
        expected_horizons = ['24H', '7D', '30D', '3M', '6M', '1Y']
        actual_horizons = [o['horizon'] for o in outlook]
        if actual_horizons != expected_horizons:
            log_fail(f"Outlook horizons mismatch. Expected {expected_horizons}, got {actual_horizons}")
            return False
        log_pass(f"Outlook horizons correct: {actual_horizons}")
        
        # Validate each outlook item
        for o in outlook:
            required_fields = ['label', 'higher', 'lower', 'lean', 'confidence', 'base', 'bull', 'bear', 'expiry', 'news_adjusted']
            for field in required_fields:
                if field not in o:
                    log_fail(f"Outlook {o['horizon']} missing field: {field}")
                    return False
            
            # Validate higher + lower ≈ 100
            if abs(o['higher'] + o['lower'] - 100) > 0.2:
                log_fail(f"Outlook {o['horizon']}: higher ({o['higher']}) + lower ({o['lower']}) != 100")
                return False
            
            # Validate lean
            if o['lean'] not in ['UP', 'DOWN']:
                log_fail(f"Outlook {o['horizon']}: lean '{o['lean']}' not in ['UP', 'DOWN']")
                return False
            
            # Validate lean logic: UP if higher >= 50
            expected_lean = 'UP' if o['higher'] >= 50 else 'DOWN'
            if o['lean'] != expected_lean:
                log_fail(f"Outlook {o['horizon']}: lean '{o['lean']}' doesn't match higher={o['higher']} (expected '{expected_lean}')")
                return False
        
        log_pass("All outlook items have required fields and valid values")
        
        # Validate summary
        if 'summary' not in decision or not decision['summary']:
            log_fail("decision.summary missing or empty")
            return False
        log_pass(f"summary present (len={len(decision['summary'])})")
        
        # Validate news_signal
        if 'news_signal' not in decision:
            log_fail("decision.news_signal missing")
            return False
        log_pass(f"news_signal = {decision['news_signal']}")
        
        # Validate news_bias
        if 'news_bias' not in decision:
            log_fail("decision.news_bias missing")
            return False
        log_pass(f"news_bias = '{decision['news_bias']}'")
        
        log_pass("GET /api/v1/dashboard - DECISION ENGINE - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Dashboard decision test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard_news_link():
    """FEATURE 2: News→Forecast Link"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/dashboard - NEWS→FORECAST LINK (FEATURE 2)")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/dashboard", timeout=20)
        if r.status_code != 200:
            log_fail(f"Dashboard endpoint returned {r.status_code}")
            return False
        data = r.json()
        
        # Validate news_forecast_link exists
        if 'news_forecast_link' not in data:
            log_fail("news_forecast_link missing from dashboard")
            return False
        log_pass("news_forecast_link present")
        
        nfl = data['news_forecast_link']
        log_info(f"news_forecast_link keys: {list(nfl.keys())}")
        
        # Validate news_forecast_link fields
        required_fields = ['signal', 'bias', 'n_high_impact', 'n_stories', 'top_driver', 'top_driver_dir', 'model_bias', 'applied']
        for field in required_fields:
            if field not in nfl:
                log_fail(f"news_forecast_link.{field} missing")
                return False
        log_pass(f"news_forecast_link has all required fields: {required_fields}")
        
        # Validate signal range
        signal = nfl['signal']
        if not isinstance(signal, (int, float)) or not (-1 <= signal <= 1):
            log_fail(f"news_forecast_link.signal invalid: {signal} (should be -1..1)")
            return False
        log_pass(f"signal = {signal} (in range -1..1)")
        
        # Validate applied list
        if not isinstance(nfl['applied'], list):
            log_fail(f"news_forecast_link.applied should be list, got {type(nfl['applied'])}")
            return False
        log_pass(f"applied is list with {len(nfl['applied'])} items")
        
        # Validate each applied item
        for item in nfl['applied']:
            required = ['horizon', 'base', 'adj', 'delta']
            for field in required:
                if field not in item:
                    log_fail(f"applied item missing field: {field}")
                    return False
        log_pass("All applied items have required fields (horizon, base, adj, delta)")
        
        # Validate forecasts array
        if 'forecasts' not in data:
            log_fail("forecasts missing from dashboard")
            return False
        forecasts = data['forecasts']
        
        # Find 24H, 7D, 30D forecasts
        f24 = next((f for f in forecasts if f['horizon'] == '24H'), None)
        f7 = next((f for f in forecasts if f['horizon'] == '7D'), None)
        f30 = next((f for f in forecasts if f['horizon'] == '30D'), None)
        
        if not f24:
            log_fail("24H forecast not found")
            return False
        if not f7:
            log_fail("7D forecast not found")
            return False
        if not f30:
            log_fail("30D forecast not found")
            return False
        
        # Validate 24H has news_link
        if 'news_link' not in f24:
            log_fail("24H forecast missing news_link")
            return False
        log_pass("24H forecast has news_link")
        
        nl24 = f24['news_link']
        required_nl_fields = ['applied', 'higher_base', 'higher_adj', 'lower_base', 'lower_adj', 'delta', 'bias', 'signal', 'top_driver']
        for field in required_nl_fields:
            if field not in nl24:
                log_fail(f"24H news_link missing field: {field}")
                return False
        log_pass(f"24H news_link has all required fields")
        
        # Validate 24H higher_adj/lower_adj fields
        if 'higher_adj' not in f24:
            log_fail("24H forecast missing higher_adj")
            return False
        if 'lower_adj' not in f24:
            log_fail("24H forecast missing lower_adj")
            return False
        log_pass("24H forecast has higher_adj and lower_adj")
        
        # Validate 24H adjustment logic: higher_adj ≈ clamp(higher_base + delta)
        expected_adj = max(2.0, min(98.0, nl24['higher_base'] + nl24['delta']))
        if abs(nl24['higher_adj'] - expected_adj) > 0.2:
            log_fail(f"24H higher_adj ({nl24['higher_adj']}) != clamp(higher_base + delta) ({expected_adj:.1f})")
            return False
        log_pass(f"24H higher_adj = {nl24['higher_adj']} ≈ clamp({nl24['higher_base']} + {nl24['delta']}) ✓")
        
        # Validate 24H lower_adj ≈ 100 - higher_adj
        if abs(nl24['lower_adj'] - (100 - nl24['higher_adj'])) > 0.2:
            log_fail(f"24H lower_adj ({nl24['lower_adj']}) != 100 - higher_adj ({100 - nl24['higher_adj']})")
            return False
        log_pass(f"24H lower_adj = {nl24['lower_adj']} ≈ 100 - higher_adj ✓")
        
        # Validate 7D has news_link
        if 'news_link' not in f7:
            log_fail("7D forecast missing news_link")
            return False
        log_pass("7D forecast has news_link")
        
        nl7 = f7['news_link']
        for field in required_nl_fields:
            if field not in nl7:
                log_fail(f"7D news_link missing field: {field}")
                return False
        log_pass(f"7D news_link has all required fields")
        
        # Validate 7D higher_adj/lower_adj fields
        if 'higher_adj' not in f7:
            log_fail("7D forecast missing higher_adj")
            return False
        if 'lower_adj' not in f7:
            log_fail("7D forecast missing lower_adj")
            return False
        log_pass("7D forecast has higher_adj and lower_adj")
        
        # Validate 7D adjustment logic
        expected_adj_7 = max(2.0, min(98.0, nl7['higher_base'] + nl7['delta']))
        if abs(nl7['higher_adj'] - expected_adj_7) > 0.2:
            log_fail(f"7D higher_adj ({nl7['higher_adj']}) != clamp(higher_base + delta) ({expected_adj_7:.1f})")
            return False
        log_pass(f"7D higher_adj = {nl7['higher_adj']} ≈ clamp({nl7['higher_base']} + {nl7['delta']}) ✓")
        
        # Validate 7D lower_adj ≈ 100 - higher_adj
        if abs(nl7['lower_adj'] - (100 - nl7['higher_adj'])) > 0.2:
            log_fail(f"7D lower_adj ({nl7['lower_adj']}) != 100 - higher_adj ({100 - nl7['higher_adj']})")
            return False
        log_pass(f"7D lower_adj = {nl7['lower_adj']} ≈ 100 - higher_adj ✓")
        
        # Validate 30D does NOT have news_link
        if 'news_link' in f30:
            log_fail("30D forecast should NOT have news_link")
            return False
        log_pass("30D forecast correctly does NOT have news_link")
        
        log_pass("GET /api/v1/dashboard - NEWS→FORECAST LINK - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"News→Forecast Link test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard_long_outlook():
    """Validate long_outlook field"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/dashboard - LONG_OUTLOOK")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/dashboard", timeout=20)
        if r.status_code != 200:
            log_fail(f"Dashboard endpoint returned {r.status_code}")
            return False
        data = r.json()
        
        # Validate long_outlook exists
        if 'long_outlook' not in data:
            log_fail("long_outlook missing from dashboard")
            return False
        log_pass("long_outlook present")
        
        long_outlook = data['long_outlook']
        if not isinstance(long_outlook, list) or len(long_outlook) != 3:
            log_fail(f"long_outlook should be list of 3 items, got {len(long_outlook)}")
            return False
        log_pass(f"long_outlook has exactly 3 items")
        
        # Validate horizons
        expected_horizons = ['3M', '6M', '1Y']
        actual_horizons = [o['horizon'] for o in long_outlook]
        if actual_horizons != expected_horizons:
            log_fail(f"long_outlook horizons mismatch. Expected {expected_horizons}, got {actual_horizons}")
            return False
        log_pass(f"long_outlook horizons correct: {actual_horizons}")
        
        # Validate each item has required fields
        for o in long_outlook:
            required = ['higher', 'base', 'bull', 'bear']
            for field in required:
                if field not in o:
                    log_fail(f"long_outlook {o['horizon']} missing field: {field}")
                    return False
        log_pass("All long_outlook items have required fields (higher, base, bull, bear)")
        
        log_pass("GET /api/v1/dashboard - LONG_OUTLOOK - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Long outlook test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_basic():
    """FEATURE 3: POST /api/v1/chat - basic functionality"""
    print("\n" + "="*80)
    print("TEST: POST /api/v1/chat - BASIC FUNCTIONALITY (FEATURE 3)")
    print("="*80)
    try:
        session_id = f"test-{int(time.time())}-1"
        payload = {
            "session_id": session_id,
            "message": "What is the current quant score and 7-day outlook?"
        }
        
        r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        if r.status_code != 200:
            log_fail(f"Chat endpoint returned {r.status_code}")
            return False
        
        data = r.json()
        log_info(f"Response keys: {list(data.keys())}")
        
        # Validate response structure
        if 'session_id' not in data:
            log_fail("session_id missing from response")
            return False
        log_pass(f"session_id = '{data['session_id']}'")
        
        if 'text' not in data or not data['text']:
            log_fail("text missing or empty from response")
            return False
        log_pass(f"text present (len={len(data['text'])})")
        log_info(f"Response text: {data['text'][:200]}...")
        
        if 'model' not in data:
            log_fail("model missing from response")
            return False
        if data['model'] != 'gemini-3-flash-preview':
            log_fail(f"model should be 'gemini-3-flash-preview', got '{data['model']}'")
            return False
        log_pass(f"model = '{data['model']}' ✓")
        
        log_pass("POST /api/v1/chat - BASIC FUNCTIONALITY - ALL CHECKS PASSED")
        return True, session_id
    except Exception as e:
        log_fail(f"Chat basic test exception: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_chat_memory(session_id):
    """FEATURE 3: POST /api/v1/chat - multi-turn memory"""
    print("\n" + "="*80)
    print("TEST: POST /api/v1/chat - MULTI-TURN MEMORY (FEATURE 3)")
    print("="*80)
    try:
        if not session_id:
            log_fail("No session_id from previous test")
            return False
        
        payload = {
            "session_id": session_id,
            "message": "what score did you just tell me?"
        }
        
        r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        if r.status_code != 200:
            log_fail(f"Chat endpoint returned {r.status_code}")
            return False
        
        data = r.json()
        log_info(f"Response text: {data.get('text', '')[:300]}...")
        
        if 'text' not in data or not data['text']:
            log_fail("text missing or empty from response")
            return False
        
        # The response should reference the prior score (should contain numbers or "score")
        text_lower = data['text'].lower()
        if 'score' not in text_lower and not any(char.isdigit() for char in data['text']):
            log_fail("Response doesn't seem to reference the prior score (no 'score' or numbers found)")
            return False
        log_pass("Response references prior conversation (contains 'score' or numbers)")
        
        log_pass("POST /api/v1/chat - MULTI-TURN MEMORY - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Chat memory test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_anti_hallucination():
    """FEATURE 3: POST /api/v1/chat - anti-hallucination"""
    print("\n" + "="*80)
    print("TEST: POST /api/v1/chat - ANTI-HALLUCINATION (FEATURE 3)")
    print("="*80)
    try:
        session_id = f"test-{int(time.time())}-2"
        payload = {
            "session_id": session_id,
            "message": "Tell me the exact Bitcoin price on Christmas Day and the current Ethereum gas fee"
        }
        
        r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        if r.status_code != 200:
            log_fail(f"Chat endpoint returned {r.status_code}")
            return False
        
        data = r.json()
        log_info(f"Response text: {data.get('text', '')[:300]}...")
        
        if 'text' not in data or not data['text']:
            log_fail("text missing or empty from response")
            return False
        
        # The response should decline or say it lacks that data
        text_lower = data['text'].lower()
        decline_phrases = ['don\'t have', 'do not have', 'cannot', 'can\'t', 'unable', 'not available', 
                          'don\'t know', 'do not know', 'no data', 'lack', 'future', 'predict']
        if not any(phrase in text_lower for phrase in decline_phrases):
            log_fail("Response should decline/say it lacks that data (no decline phrases found)")
            log_info(f"Expected one of: {decline_phrases}")
            return False
        log_pass("Response correctly declines to provide unavailable data")
        
        log_pass("POST /api/v1/chat - ANTI-HALLUCINATION - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Chat anti-hallucination test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_empty_message():
    """FEATURE 3: POST /api/v1/chat - empty message handling"""
    print("\n" + "="*80)
    print("TEST: POST /api/v1/chat - EMPTY MESSAGE HANDLING (FEATURE 3)")
    print("="*80)
    try:
        session_id = f"test-{int(time.time())}-3"
        payload = {
            "session_id": session_id,
            "message": ""
        }
        
        r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=15)
        if r.status_code != 200:
            log_fail(f"Chat endpoint returned {r.status_code} (should return 200 with error object)")
            return False
        
        data = r.json()
        log_info(f"Response: {json.dumps(data, indent=2)}")
        
        # Should return a friendly error, not crash
        if 'error' not in data:
            log_fail("Expected 'error' field in response for empty message")
            return False
        log_pass(f"error field present: '{data['error']}'")
        
        if 'text' not in data or not data['text']:
            log_fail("Expected friendly 'text' message for empty input")
            return False
        log_pass(f"Friendly error message: '{data['text']}'")
        
        log_pass("POST /api/v1/chat - EMPTY MESSAGE HANDLING - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Chat empty message test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_history(session_id):
    """FEATURE 3: GET /api/v1/chat/history"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/chat/history (FEATURE 3)")
    print("="*80)
    try:
        if not session_id:
            log_fail("No session_id from previous test")
            return False
        
        r = requests.get(f"{BASE_URL}/chat/history?session_id={session_id}", timeout=15)
        if r.status_code != 200:
            log_fail(f"Chat history endpoint returned {r.status_code}")
            return False
        
        data = r.json()
        log_info(f"Response keys: {list(data.keys())}")
        
        # Validate response structure
        if 'session_id' not in data:
            log_fail("session_id missing from response")
            return False
        log_pass(f"session_id = '{data['session_id']}'")
        
        if 'messages' not in data:
            log_fail("messages missing from response")
            return False
        
        messages = data['messages']
        if not isinstance(messages, list):
            log_fail(f"messages should be list, got {type(messages)}")
            return False
        log_pass(f"messages is list with {len(messages)} items")
        
        # Should have at least 2 messages from earlier tests
        if len(messages) < 2:
            log_fail(f"Expected at least 2 messages, got {len(messages)}")
            return False
        log_pass(f"History contains {len(messages)} messages (>= 2)")
        
        # Validate message structure
        for msg in messages:
            if 'user' not in msg or 'assistant' not in msg:
                log_fail(f"Message missing 'user' or 'assistant' field")
                return False
        log_pass("All messages have 'user' and 'assistant' fields")
        
        log_pass("GET /api/v1/chat/history - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Chat history test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard_regression():
    """REGRESSION: Validate all existing fields still present"""
    print("\n" + "="*80)
    print("TEST: GET /api/v1/dashboard - REGRESSION (ALL EXISTING FIELDS)")
    print("="*80)
    try:
        r = requests.get(f"{BASE_URL}/dashboard", timeout=20)
        if r.status_code != 200:
            log_fail(f"Dashboard endpoint returned {r.status_code}")
            return False
        data = r.json()
        
        # List of all existing fields that must be present
        required_fields = [
            'status', 'signal', 'confidence', 'prob_up', 'prob_down',
            'forecasts', 'scoreboard', 'trades', 'quant_score', 'quant_label',
            'quant_breakdown', 'regime', 'factors', 'importances', 'performance',
            'features', 'policy', 'dominance', 'chart', 'cycle', 'alerts'
        ]
        
        missing = []
        for field in required_fields:
            if field not in data:
                missing.append(field)
        
        if missing:
            log_fail(f"Missing existing fields: {missing}")
            return False
        log_pass(f"All {len(required_fields)} existing fields present")
        
        log_pass("GET /api/v1/dashboard - REGRESSION - ALL CHECKS PASSED")
        return True
    except Exception as e:
        log_fail(f"Dashboard regression test exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*80)
    print("BTCIQ BACKEND COMPREHENSIVE TEST SUITE")
    print("Testing: Decision Engine, News→Forecast Link, Ask Quant Chat, Ticker AUD")
    print("="*80)
    
    results = {}
    
    # Run all tests
    results['health'] = test_health()
    results['ticker'] = test_ticker()
    results['dashboard_decision'] = test_dashboard_decision()
    results['dashboard_news_link'] = test_dashboard_news_link()
    results['dashboard_long_outlook'] = test_dashboard_long_outlook()
    results['dashboard_regression'] = test_dashboard_regression()
    
    # Chat tests
    chat_basic_result = test_chat_basic()
    if isinstance(chat_basic_result, tuple):
        results['chat_basic'], session_id = chat_basic_result
    else:
        results['chat_basic'] = chat_basic_result
        session_id = None
    
    results['chat_memory'] = test_chat_memory(session_id)
    results['chat_anti_hallucination'] = test_chat_anti_hallucination()
    results['chat_empty_message'] = test_chat_empty_message()
    results['chat_history'] = test_chat_history(session_id)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! 🎉\n")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
