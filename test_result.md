#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Build a Bitcoin Predictive AI Quant Dashboard. User explicitly requested Python + FastAPI
  (not JS reimplementation). Pipeline: real BTC/USD daily data -> price-agnostic stationary
  features (RSI, StochRSI, MACD hist, EMA 9/21 ratio, ATR%, Bollinger width%, Volume Z-score,
  Volume ratio) -> RandomForest classifier predicting next-day direction -> TimeSeriesSplit CV +
  walk-forward backtest (accuracy over time) -> persisted to MongoDB, refreshed daily via
  APScheduler (Celery replaced with APScheduler per user agreement). FastAPI runs internally on
  :8001; Next.js /api/* catch-all proxies to it. Frontend shows Recharts dual-axis success-rate
  chart + next-day signal card + feature matrix + importance + CV folds.
  NOTE: Binance is geo-blocked from this server; Kraken is primary, Coinbase fallback (both via ccxt).

backend:
  - task: "FastAPI ML engine - real BTC data fetch (ccxt Kraken primary, Coinbase fallback)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "Verified via curl: kraken returns 720 daily bars, real last_close ~64040. Binance blocked."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive backend test. Real Kraken data confirmed: last_close=$64,040.3, 720 bars fetched, all features computed correctly."
  - task: "GET /api/v1/dashboard - signal, confidence, features, importances, cv_folds, performance"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "Returns status=ready with signal DOWN 52.69%, 491 perf points, 8 features, 5 CV folds via Next.js proxy."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED all validations via external URL. Returns status='ready', signal='DOWN', confidence=52.69%, prob_up=47.31%, prob_down=52.69%, last_close=$64,040.3, data_source='kraken', overall_accuracy=46.0%, cv_mean=49.14%, 5 CV folds (correct structure), 8 importances (sum ~100%), 491 performance points (non-empty), 8 features (all required keys present). All data types and ranges validated."
  - task: "GET /api/v1/health and POST /api/v1/refresh (background retrain thread)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "health shows compute_status done, runs=1. refresh triggers background thread."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED both endpoints. GET /api/v1/health returns status='ok', compute_status='done', runs=1. POST /api/v1/refresh returns status='started', triggers background thread successfully. System remains stable after refresh (health shows compute_status='running', dashboard still returns 'ready' with cached data)."
  - task: "Next.js /api catch-all proxy to internal FastAPI :8001"
    implemented: true
    working: true
    file: "app/api/[[...path]]/route.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "curl to localhost:3000/api/v1/dashboard returns full payload proxied from FastAPI."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED proxy functionality. All endpoints (health, dashboard, refresh) accessible via external base URL with /api prefix. Proxy correctly forwards requests to internal FastAPI :8001 and returns responses with proper status codes and content-type headers."
  - task: "GET /api/v1/ticker - live intraday BTC price (ccxt, cached ~8s)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "New endpoint. Returns real live price via kraken (e.g. 63908.0) with change24h, high, low, source. Cached 8s. Verified manually via proxy; needs agent validation."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive test. Returns price=$63,770.10, change24h=0.49%, high=$64,183.50, low=$63,270.30, source='kraken', ts='2026-08-04T15:33:32.649292'. All fields present and valid. Tested twice 2s apart - caching working correctly (8s cache). Price in realistic BTC range. Timestamp parseable as ISO format."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED NEW AUD PRICE FEATURE validation. Ticker now returns price_aud and aud_rate fields: price=$63,900.60, price_aud=$90,713.29, aud_rate=1.4196 ✅ All validations passed: (1) price_aud is valid number > 0 ✅ (2) aud_rate in valid range 1.0-2.0 ✅ (3) price_aud ≈ price * aud_rate (diff 0.000%) ✅ (4) price_aud > price (since AUD > USD) ✅ All required fields present (price, price_aud, aud_rate, change24h, source) ✅"
  - task: "Trade Log + Scoreboard from walk-forward (dashboard.trades, dashboard.scoreboard)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "New dashboard fields. scoreboard: total 500, wins 230, losses 270, winRate 46.0, bestWinStreak, currentStreak. trades: 25 recent each with date/signal/confidence/close/nextClose/actual/correct."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation. Scoreboard: total=500, wins=230, losses=270, winRate=46.0%, bestWinStreak=6, currentStreak=-1. All fields present and valid. Sanity check passed: wins+losses=total. Trades: 25 items returned (correct limit). Validated 3 trades in detail - all have required fields (date, signal, confidence, close, nextClose, actual, correct). Date format YYYY-MM-DD validated. Logic checks passed: correct=(signal==actual), actual direction matches (nextClose vs close). All data types and ranges correct."
  - task: "Forward signal history (live_signals): record pending + grade on next candle (dashboard.live_record, predict_for_date)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "New. live_record: tracked/resolved/correct/winRate. record_live_signal upserts one per as_of date; grade_pending resolves when target candle close known. predict_for_date returned."
  - task: "Intelligence layer: quant_score, quant_label, quant_breakdown, regime, forecasts (24H/7D/30D), factors"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "New dashboard fields. quant_score 0-100 + label; quant_breakdown 9 categories (4 active Trend/Momentum/Volume/Volatility + 5 coming-soon with score null); regime object (regime/description/behavior/trend30d_pct/vol_percentile); forecasts list of 3 {horizon,higher,lower,bull,base,bear,expected_low,expected_high,confidence,confidence_pct,accuracy,invalidation,invalidation_dir,lean,expiry}; factors {bullish[], risk[]}. Verified via curl: score 44 Weakly Bearish, regime Weak Bearish Trend, 3 forecasts."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive intelligence layer validation. All NEW fields validated: (1) quant_score=44 (integer 0-100) ✅ (2) quant_label='Weakly Bearish' (non-empty string) ✅ (3) quant_breakdown: 9 items with exactly 4 active (Trend=35%, Momentum=30%, Volume=20%, Volatility=15%) and 5 inactive (Derivatives, Liquidity, On-chain, Sentiment, Macro with score=null, weight=0) ✅ (4) regime: 'Weak Bearish Trend' with all required fields (regime, description, behavior, trend30d_pct=0.5%, vol_percentile=14) ✅ (5) forecasts: 3 items (24H, 7D, 30D) with all required fields validated - higher+lower≈100%, bull>bear, invalidation_dir logic correct (lean=UP→below, lean=DOWN→above), expiry dates valid YYYY-MM-DD format ✅ (6) factors: bullish (1 item) and risk (2 items) lists non-empty with valid strings ✅ (7) All EXISTING fields still present (signal, confidence, cv_folds, importances, performance, features, scoreboard, trades, live_record) ✅ Also verified GET /api/v1/health (compute_status='done', runs=6) ✅ and GET /api/v1/ticker (live price=$64,110.50 from Kraken) ✅ working correctly."
  - task: "Unified Decision Engine (dashboard.decision) - overall_score, regime, risk_level, alignment, components, 24H→1Y outlook, summary"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW. compute_decision_engine reconciles technicals (quant_score), macro/policy (policy score), chart structure and news flow into a master Bitcoin Market State. dashboard.decision returns: overall_score (0-100), label, regime, regime_description, alignment (Strong Agreement/Conflicting/Mixed), components (4 items: Technicals w45, Macro/Policy w20, Chart Structure w20, News Flow w15), risk_level (Low→Extreme) + risk_score + risk_drivers, outlook (list across 24H/7D/30D/3M/6M/1Y each with label/higher/lower/lean/confidence/base/bull/bear/expiry/news_adjusted), summary (plain-English), news_signal, news_bias. Verified via curl: overall 48 Neutral, risk Low, 6 outlook horizons. Also dashboard.long_outlook added (3M/6M/1Y horizons, shrinkage toward 50% applied for long horizons)."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. Decision object fully validated: (1) overall_score=48 (int 0-100) ✅ (2) label='Neutral' (non-empty) ✅ (3) regime='Weak Bearish Trend' (non-empty) ✅ (4) regime_description present ✅ (5) alignment='Mixed / Neutral' (non-empty) ✅ (6) components: exactly 4 items with correct names ['Technicals', 'Macro / Policy', 'Chart Structure', 'News Flow'], all with valid score (0-100) and weight (int) ✅ (7) risk_level='Low' (valid enum) ✅ (8) risk_score=8 (int 0-100) ✅ (9) risk_drivers has all required fields (volatility_percentile, event_risk, news_risk) ✅ (10) outlook: exactly 6 items with correct horizons ['24H', '7D', '30D', '3M', '6M', '1Y'], all with required fields, higher+lower≈100%, lean logic correct (UP if higher>=50) ✅ (11) summary present (792 chars) ✅ (12) news_signal=-0.163 ✅ (13) news_bias='Bearish' ✅ Also validated long_outlook: 3 items (3M, 6M, 1Y) with required fields (higher, base, bull, bear) ✅ All existing dashboard fields still present (regression test passed) ✅"
  - task: "News → Forecast Link (dashboard.news_forecast_link + forecasts[].news_link) - impact-weighted news nudges 24H/7D probabilities"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW. compute_news_signal builds an impact-weighted directional signal in [-1,1] from the latest news cards. apply_news_link nudges the 24H (K=7) and 7D (K=4.5) forecast probabilities (capped ±8 pts) and attaches forecasts[].news_link = {applied, higher_base, higher_adj, lower_base, lower_adj, delta, bias, signal, top_driver}; also sets forecasts[].higher_adj/lower_adj. dashboard.news_forecast_link summarises {signal, bias, n_high_impact, n_stories, top_driver, top_driver_dir, model_bias, applied:[{horizon,base,adj,delta}]}. Verified via curl: signal=-0.163 Bearish, 24H 45.7%→44.6% (-1.1), 7D 48.2%→47.5% (-0.7). Only 24H/7D get news_link; 30D unchanged."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. News→Forecast Link fully validated: (1) dashboard.news_forecast_link present with all required fields (signal, bias, n_high_impact, n_stories, top_driver, top_driver_dir, model_bias, applied) ✅ (2) signal=-0.163 (valid range -1..1) ✅ (3) applied list has 2 items (24H, 7D) with required fields (horizon, base, adj, delta) ✅ (4) 24H forecast has news_link object with all required fields (applied, higher_base, higher_adj, lower_base, lower_adj, delta, bias, signal, top_driver) ✅ (5) 24H has higher_adj=45.0 and lower_adj=55.0 fields ✅ (6) 24H adjustment logic validated: higher_adj ≈ clamp(higher_base + delta) = clamp(46.1 + -1.1) = 45.0 ✅ (7) 24H lower_adj ≈ 100 - higher_adj (55.0 ≈ 100 - 45.0) ✅ (8) 7D forecast has news_link with all required fields ✅ (9) 7D has higher_adj=47.2 and lower_adj=52.8 ✅ (10) 7D adjustment logic validated: higher_adj ≈ clamp(47.9 + -0.7) = 47.2 ✅ (11) 7D lower_adj ≈ 100 - higher_adj ✅ (12) 30D forecast correctly does NOT have news_link ✅ All math and logic checks passed."
  - task: "Ask Quant chat (POST /api/v1/chat, GET /api/v1/chat/history) - Gemini 3 Flash grounded in live dashboard data"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW. POST /api/v1/chat {session_id, message} builds a grounded system prompt from build_chat_context() (latest run + news docs: score, regime, decision, forecasts, long_outlook, factors, policy, dominance, cycle, chart, scoreboard, top news) and calls Gemini via emergentintegrations LlmChat with model CHAT_MODEL='gemini-3-flash-preview' (verified available on the Emergent gateway). Stores each Q&A in ask_quant_chat collection; replays last 5 turns for multi-turn memory. Returns {session_id, text, model}. GET /api/v1/chat/history?session_id returns stored messages. Verified via curl: grounded answer with correct score, multi-turn memory recalled prior score, and anti-hallucination (declined to predict an exact Christmas price / Ethereum gas not in data). Empty message returns friendly error."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. Ask Quant chat fully validated: (1) POST /api/v1/chat basic functionality: returns HTTP 200 with {session_id, text (non-empty, 502 chars), model='gemini-3-flash-preview'} ✅ Response correctly answered question about quant score (46/100) and 7-day outlook (52.8% lower) ✅ (2) Multi-turn memory: follow-up question 'what score did you just tell me?' correctly referenced prior conversation (mentioned score 46/100 and additional context) ✅ (3) Anti-hallucination: request for exact Christmas BTC price and ETH gas fee correctly declined with 'I do not have the data' response ✅ (4) Empty message handling: returns friendly error {error: 'empty message', text: 'Please type a question.'} without crashing ✅ (5) GET /api/v1/chat/history: returns {session_id, messages: [...]} with 2+ messages from earlier turns, all with 'user' and 'assistant' fields ✅ All chat scenarios passed including grounding, memory, anti-hallucination, and error handling."
  - task: "Data Trust Layer (dashboard.data_health + decision.data_trust) - feed health monitoring + odds fading"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW ENGINE 1. compute_data_health monitors 6 data feeds (price, dominance, crossmarket, policy, news, fx) and returns score 0-100, level (High/Good/Degraded/Low), live/degraded/stale counts, faded bool, note, checked_at, feeds list. apply_data_fade adds decision.data_trust {score, level, faded} and decision.odds_faded; when faded=True, shrinks outlook probabilities toward 50% and flags them. Normally all 6 feeds live with score ~97."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. ENGINE 1 - Data Trust Layer fully validated: (1) data_health object present with all 9 required fields (score, level, live, degraded, stale, faded, note, checked_at, feeds) ✅ (2) score=97 (int 0-100) ✅ (3) level='High' (valid enum) ✅ (4) Counts: live=6, degraded=0, stale=0 (all valid ints >=0) ✅ (5) faded=False (bool) ✅ (6) note present (58 chars, non-empty string) ✅ (7) checked_at valid ISO format ✅ (8) feeds: exactly 6 items, all validated with required fields (id, label, provider, status in [live,degraded,stale,down], updated, age_min, confidence 0-100, methodology) ✅ (9) Live feeds: 6/6 (expected normally all 6) ✅ (10) Score 97 is healthy (>=90, expected ~97) ✅ (11) decision.data_trust present with score=97, level='High', faded=False ✅ (12) decision.odds_faded=False (bool) ✅ (13) When faded=False, no outlook items have 'faded' flag (odds not shrunk) ✅ All validations passed. Data is REAL (ccxt Kraken)."
  - task: "Prediction Ledger + Scorecard (dashboard.prediction_ledger + GET /api/v1/scorecard) - immutable forecast log + performance tracking"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW ENGINE 2. record_predictions logs every horizon forecast (24H/7D/30D/3M/6M/1Y) BEFORE outcome known (idempotent per as_of+horizon). resolve_predictions grades matured forecasts against actual close. compute_scorecard returns overall {n, accuracy, brier, mae_pct, range_hit_pct}, by_horizon (dict), calibration (list of buckets), pending (list), recent (list), total_logged, live_logged, backtested (~500 from walk-forward seed), model_version='rf-quant-v1'. GET /api/v1/scorecard endpoint returns same structure with status='ready'."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. ENGINE 2 - Prediction Ledger + Scorecard fully validated: (1) dashboard.prediction_ledger present with all 9 required fields ✅ (2) overall: n=500 (total resolved), accuracy=46.0%, brier=0.2632, mae_pct=None, range_hit_pct=None - all valid ✅ (3) by_horizon: dict with key '24H' containing n/accuracy/brier ✅ (4) calibration: 4 buckets, each with bucket/n/avg_pred/realised_up ✅ (5) pending: 6 predictions, each with horizon/direction (UP/DOWN)/prob_higher/target_date ✅ (6) recent: 0 predictions (list) ✅ (7) total_logged=506 (int >0) ✅ (8) live_logged=6 (int >=0) ✅ (9) backtested=500 (expected ~500 from walk-forward seed) ✅ (10) model_version='rf-quant-v1' ✅ (11) GET /api/v1/scorecard returns status='ready' with all required fields ✅ (12) Scorecard numbers match dashboard prediction_ledger (total_logged=506, backtested=500) ✅ Minor: overall.n=500 != total_logged=506 (may include unresolved). All validations passed. Data is REAL."
  - task: "Event Intelligence Calendar (dashboard.event_calendar) - 120-day forward event window with macro/derivatives/on-chain events"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW ENGINE 3. compute_event_calendar generates a 120-day forward calendar with macro events (CPI, NFP, FOMC), derivatives expiries (monthly/quarterly), on-chain events (difficulty adjustments). Returns window_days (==120), generated (date str), counts (dict of category->count), events (list sorted ascending by date), next_high_impact (object or null). Each event has: date (YYYY-MM-DD), days_until (0-120), category (Macro/Derivatives/On-Chain/Regulatory), title, description, importance (Low/Medium/High/Very High), expected_volatility (Low/Elevated/High/Very High). next_high_impact must have importance in [High, Very High]."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive validation via external URL. ENGINE 3 - Event Intelligence Calendar fully validated: (1) event_calendar object present with all 5 required fields (window_days, generated, counts, events, next_high_impact) ✅ (2) window_days=120 ✅ (3) generated='2026-08-04' (valid YYYY-MM-DD) ✅ (4) counts: {'On-Chain': 9, 'Macro': 10, 'Derivatives': 4} (dict) ✅ (5) events: 23 items (non-empty list) ✅ (6) All events validated (checked first 10): each has 7 required fields (date, days_until, category, title, description, importance, expected_volatility) ✅ (7) date format YYYY-MM-DD validated ✅ (8) days_until: int 0-120 ✅ (9) category in [Macro,Derivatives,On-Chain,Regulatory] ✅ (10) title and description: non-empty strings ✅ (11) importance in [Low,Medium,High,Very High] ✅ (12) expected_volatility in [Low,Elevated,High,Very High] ✅ (13) Events sorted ascending by date ✅ (14) next_high_impact: 'US Nonfarm Payrolls' with importance='High' (valid enum [High,Very High]) ✅ All validations passed. Data is REAL."
  - task: "BitMarkAI Engine (dashboard.bitmark + POST /api/v1/bitmark/run) - 7-horizon forecast with model (1W-1Y) and scenario (2Y-5Y) projections"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW BitMarkAI engine. GET /api/v1/dashboard returns top-level 'bitmark' object with model_version='bitmark-v1', trigger (scheduled/manual/event), issued (YYYY-MM-DD), next_scheduled_update (issued + 7 days), current_price, regime, change_explanation, generated_at, and horizons (list of 7). First 5 horizons (1W,1M,3M,6M,1Y) are type='model' with prob_above/prob_below, base_low/base_high, bull_low/bull_high, bear_low/bear_high, expected_volatility, model_confidence, weighting (sum ~100), top_positive, top_risk, issued, next_update. Last 2 horizons (2Y,5Y) are type='scenario' with prob_above/prob_below, expected_volatility='Very High', model_confidence in [Low,Very Low], scenarios (4 named: Adoption Expansion, Base Adoption, Restrictive Policy, Severe Disruption, each with prob/low/high/note, probs sum to 100), weighting. POST /api/v1/bitmark/run triggers manual forecast with 5-minute rate limit (returns status: started/busy/rate_limited with retry_in)."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED comprehensive BitMarkAI certification via external URL. All 3 tests passed: (1) GET /api/v1/dashboard bitmark object: model_version='bitmark-v1' ✅, trigger='manual' ✅, issued='2026-08-04' ✅, next_scheduled_update='2026-08-11' (= issued + 7 days) ✅, current_price=$64,319 ✅, regime='Weak Bearish Trend' ✅, change_explanation (244 chars) ✅, generated_at ISO format ✅, horizons: EXACTLY 7 items ✅, codes exactly [1W,1M,3M,6M,1Y,2Y,5Y] in order ✅. MODEL horizons (1W-1Y): all have type='model' ✅, prob_above+prob_below=100 ✅, range logic bear_low<=base_low<=base_high<=bull_high ✅, expected_volatility in [Low,Elevated,High,Very High] ✅, model_confidence in [Low,Moderate,High,Very Low] ✅, weighting sum=100% ✅, top_positive/top_risk present ✅. SCENARIO horizons (2Y,5Y): type='scenario' ✅, expected_volatility='Very High' ✅, model_confidence in [Low,Very Low] ✅, scenarios: 4 items with exact names [Adoption Expansion, Base Adoption, Restrictive Policy, Severe Disruption] ✅, each with prob/low/high/note ✅, high>low ✅, probs sum=100% ✅, weighting present ✅. (2) POST /api/v1/bitmark/run: first call returned status='started' ✅, immediate second call returned status='rate_limited' with retry_in=299s (<=300) ✅, message present ✅. (3) REGRESSION: GET /api/v1/dashboard status='ready' with all 14 prior fields (decision, news_forecast_link, data_health, event_calendar, prediction_ledger, forecasts(3), long_outlook(3), quant_score, regime, dominance, cycle, policy, chart, alerts) ✅, GET /api/v1/scorecard status='ready' ✅, GET /api/v1/health compute_status='running', runs=14 ✅, GET /api/v1/ticker price=$64,255.90, price_aud=$91,159.84 ✅. All validations passed. Data is REAL (ccxt Kraken). WebSockets NOT tested (as instructed)."

  - task: "Prediction Ledger confidence for Open Forecasts (dashboard.prediction_ledger.pending[].confidence + confidence_pct)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW. record_predictions now stores confidence_pct alongside confidence for every logged forecast. compute_scorecard() backfills any legacy pending doc missing confidence_pct by deriving BOTH label + pct from prob_higher margin so badge and % always agree. Each item in prediction_ledger.pending (and GET /api/v1/scorecard pending) now has confidence (Low/Moderate/High) and confidence_pct (int 0-100). Verified via curl: 6 pending items all have consistent confidence + confidence_pct."
  - task: "Smart Alerts engine (GET /api/v1/alerts, POST /api/v1/alerts/ack, dashboard.smart_alerts)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW Phase-2 feature. compute_smart_alerts(doc, prev_doc) compares each run vs the previous run and logs state-change events (Regime shift, Market State/decision-label change, Quant Score band crossing, Data Trust degrade/recover, high-impact Event Risk within 3 days, large daily Volatility move) into smart_alerts collection, de-duplicated by as_of+category+signature via $setOnInsert. GET /api/v1/alerts returns {status:'ready', alerts:[...recent 50 sorted ts desc, each with id/ts/as_of/category/severity/title/message/seen], unseen:int, total:int}. POST /api/v1/alerts/ack {ids?:[...]} marks those (or all unseen if no ids) seen and returns {status:'ok', unseen}. Verified via curl: 1 alert fired (Event Risk NFP in 3d), unseen=1; ack works."
  - task: "Time Machine historical replay (GET /api/v1/replay?date=&window=)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "NEW Phase-2 feature. compute() now persists a 'replay' payload in the stored run doc (NOT in the dashboard response): full price series [{date,close}] + full walk-forward trades [{date,signal,confidence,close,nextClose,actual,correct}] + min_date/max_date/n. GET /api/v1/replay?date=YYYY-MM-DD&window=30 returns {status:'ready', pick_date, signal(UP/DOWN), confidence, close, next_close, actual(UP/DOWN), move_pct, correct(bool), window:[{date,close,is_pick}], rolling_accuracy, min_date, max_date, n}. No date -> defaults to max_date. Picks nearest trade at/just-before target_date; no future leakage. Verified via curl for default + 2025-11-15 (signal UP, actual DOWN, correct false, 41-pt window)."
    implemented: true
    working: true
    file: "app/page.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "Verified via screenshot - all sections render with real data. Not yet tested by frontend agent (awaiting user permission)."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 6
  run_ui: false

test_plan:
  current_focus:
    - "Prediction Ledger confidence for Open Forecasts (dashboard.prediction_ledger.pending[].confidence + confidence_pct)"
    - "Smart Alerts engine (GET /api/v1/alerts, POST /api/v1/alerts/ack, dashboard.smart_alerts)"
    - "Time Machine historical replay (GET /api/v1/replay?date=&window=)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: |
      NEW backend work to test (Phase 2 + P0). Test via Next.js proxy (external base URL + /api/v1/...).
      Data is REAL (ccxt Kraken). No new keys needed. Do NOT test WebSockets.

      1) P0 — Open Forecast confidence: GET /api/v1/scorecard (and GET /api/v1/dashboard -> prediction_ledger).
         Every item in `pending` MUST now have BOTH `confidence` (one of Low/Moderate/High) and
         `confidence_pct` (int 0-100). They must be internally consistent (High<->high pct, etc.).
         Confirm existing fields (horizon, direction, base, price_at_issue, target_date, prob_higher) still present.

      2) Smart Alerts:
         - GET /api/v1/alerts -> {status:'ready', alerts:[...], unseen:int, total:int}. Each alert has
           id, ts (ISO), as_of, category (Regime/Market State/Quant Score/Data Trust/Event Risk/Volatility),
           severity (high/warning/success/info), title, message, seen(bool).
         - POST /api/v1/alerts/ack with {} should mark ALL unseen as seen and return {status:'ok', unseen:0}.
         - POST /api/v1/alerts/ack with {"ids":["<an id>"]} should mark only that one seen.
         - GET /api/v1/dashboard should include top-level `smart_alerts` object {alerts, unseen, total}.

      3) Time Machine replay:
         - GET /api/v1/replay (no date) -> status:'ready', defaults to max_date. Validate fields:
           pick_date, signal (UP/DOWN), confidence (number), close, next_close, actual (UP/DOWN),
           move_pct (number), correct (bool), window (non-empty list of {date, close, is_pick}), rolling_accuracy,
           min_date, max_date, n.
         - GET /api/v1/replay?date=2025-11-15&window=20 -> pick_date == 2025-11-15 (or nearest <=), window
           length ~ up to 41 (2*20+1), exactly one window item has is_pick=true matching pick_date.
         - Logic check: correct == (signal == actual); actual == 'UP' iff next_close > close.

      REGRESSION: GET /api/v1/dashboard still status='ready' with all prior fields (decision, forecasts,
      bitmark, data_health, event_calendar, prediction_ledger, quant_score, regime, etc.). POST /api/v1/chat
      still returns model 'gemini-3-flash-preview' (persona now 'Albert').
      Data is REAL (ccxt Kraken); no keys needed except EMERGENT_LLM_KEY (already set) for chat.

      1) GET /api/v1/dashboard -> validate NEW top-level 'decision' object:
         - overall_score (int 0-100), label (str), regime (str), regime_description (str)
         - alignment (str), components (list of 4: names Technicals/Macro-Policy/Chart Structure/News Flow, each score 0-100 + weight)
         - risk_level in [Low,Moderate,Elevated,High,Extreme], risk_score (0-100), risk_drivers (dict)
         - outlook: list (6 items) horizons 24H,7D,30D,3M,6M,1Y; each has label, higher, lower(≈100-higher), lean in [UP,DOWN], confidence, base/bull/bear, expiry, news_adjusted(bool)
         - summary (non-empty str), news_signal, news_bias
         Also validate NEW 'long_outlook' (3 items: 3M,6M,1Y with higher/base/bull/bear) and that 'news_forecast_link' exists.

      2) News Forecast Link: dashboard.news_forecast_link = {signal(-1..1), bias, n_high_impact, n_stories, top_driver, top_driver_dir, model_bias, applied:[{horizon,base,adj,delta}]}.
         In dashboard.forecasts, the 24H and 7D items MUST have a 'news_link' object {applied, higher_base, higher_adj, lower_base, lower_adj, delta, bias, signal, top_driver} and higher_adj/lower_adj fields; 30D must NOT have news_link. Validate higher_adj = clamp(higher_base + delta) and lower_adj ≈ 100-higher_adj.

      3) POST /api/v1/chat with {session_id:"test-1", message:"What is the current quant score and 7-day outlook?"} -> expect 200 JSON {session_id, text (non-empty), model:"gemini-3-flash-preview"}. Then POST again same session with a follow-up ("what score did you just say?") to confirm multi-turn memory. Then POST {session_id:"test-2", message:"predict the exact BTC price on Christmas and Ethereum gas fee"} to confirm it declines/says it lacks that data (anti-hallucination). Empty message should return a friendly error (no crash). GET /api/v1/chat/history?session_id=test-1 should return the stored messages.

      IMPORTANT: Do NOT test WebSockets. Confirm all EXISTING dashboard fields still present (signal, forecasts, scoreboard, trades, quant_score, regime, policy, dominance, chart, cycle, alerts, news).
    -agent: "testing"
    -message: |
      ✅ ALL BACKEND TESTS PASSED (3/3)
      
      Tested all endpoints via external base URL (https://quant-features.preview.emergentagent.com/api/v1/*):
      
      1. GET /api/v1/health - ✅ PASSED
         - Returns status='ok', compute_status='done', runs=1
         - All required fields present and valid
      
      2. GET /api/v1/dashboard - ✅ PASSED
         - Returns status='ready' with complete ML data
         - Real Kraken BTC data: last_close=$64,040.3
         - Signal: DOWN with 52.69% confidence
         - All required fields validated:
           * 5 CV folds (correct structure)
           * 8 feature importances (sum ~100%)
           * 491 performance data points
           * 8 features with values and units
         - All numeric values in expected ranges
         - Data types correct
      
      3. POST /api/v1/refresh - ✅ PASSED
         - Returns status='started'
         - Background retraining triggered successfully
         - System remains stable (health and dashboard still respond)
      
      Next.js proxy working correctly - all requests properly forwarded to internal FastAPI :8001.
      
      NO CRITICAL ISSUES FOUND. All backend functionality working as expected with real data.
        - GET /api/v1/health -> expect {status:'ok', compute_status:'done', runs>=1}
        - GET /api/v1/dashboard -> expect status:'ready' with keys: signal (UP/DOWN), confidence,
          prob_up, prob_down, last_close, data_source ('kraken' or 'coinbase'), overall_accuracy,
          cv_mean, cv_folds (len 5), importances (len 8), performance (list of {date,iso,btcPrice,
          aiAccuracy}), features (len 8). Validate values are real/plausible (last_close > 0,
          confidence between 0-100, performance non-empty).
        - POST /api/v1/refresh -> expect {status:'started'}; then health/dashboard still return ready.
      Data is REAL (ccxt Kraken). Do NOT expect Binance (geo-blocked). No API keys required.
      Do not test WebSockets (not implemented).
    -agent: "testing"
    -message: |
      ✅ ALL NEW BACKEND FEATURES TESTED AND PASSED (3/3)
      
      Completed comprehensive testing of new live updates, scoreboard, and trade log features:
      
      1. GET /api/v1/ticker - ✅ PASSED
         - Live BTC price: $63,770.10 (Kraken)
         - All fields present: price, change24h (0.49%), high, low, source, ts
         - Caching working correctly (8s cache, tested 2s apart)
         - Timestamp parseable as ISO format
         - Price in realistic BTC range
      
      2. GET /api/v1/dashboard NEW FIELDS - ✅ PASSED
         - scoreboard: total=500, wins=230, losses=270, winRate=46.0%, bestWinStreak=6, currentStreak=-1
           * All fields present and valid types
           * Sanity check passed: wins + losses = total
         - trades: 25 items (correct limit)
           * All required fields present: date, signal, confidence, close, nextClose, actual, correct
           * Date format YYYY-MM-DD validated
           * Logic checks passed: correct = (signal == actual)
           * Actual direction matches (nextClose vs close)
         - live_record: tracked=1, resolved=0, correct=0, winRate=null
           * All fields present and valid
         - predict_for_date: '2026-08-05' (valid format)
         - All EXISTING fields still present and valid
      
      3. POST /api/v1/refresh + stability - ✅ PASSED
         - Refresh triggered successfully
         - Polled health until compute_status='done' (~18s)
         - Dashboard still ready after refresh
         - Scoreboard, trades, live_record all still valid
         - CRITICAL: tracked count stable (1->1), confirming upsert logic working correctly
      
      NO CRITICAL ISSUES FOUND. All new backend features working as expected with real data.
    -agent: "testing"
    -message: |
      ✅ INTELLIGENCE LAYER TESTS COMPLETED - ALL PASSED
      
      Completed comprehensive validation of NEW intelligence layer fields on GET /api/v1/dashboard:
      
      1. quant_score - ✅ PASSED
         - Value: 44 (valid integer 0-100)
         - Type validation: integer ✅
         - Range validation: 0-100 ✅
      
      2. quant_label - ✅ PASSED
         - Value: 'Weakly Bearish' (non-empty string)
         - Type validation: string ✅
         - Non-empty validation: ✅
      
      3. quant_breakdown - ✅ PASSED
         - Count: 9 items (exactly as expected) ✅
         - Active items (4): Trend (35%), Momentum (30%), Volume (20%), Volatility (15%)
           * All have score 0-100 ✅
           * All have weight in {35,30,20,15} ✅
           * All have valid signal strings ✅
           * All have active=true ✅
         - Inactive items (5): Derivatives, Liquidity, On-chain, Sentiment, Macro
           * All have score=null ✅
           * All have weight=0 ✅
           * All have active=false ✅
         - All items have required fields: name, score, weight, signal, active, note ✅
      
      4. regime - ✅ PASSED
         - Value: 'Weak Bearish Trend'
         - All required fields present: regime, description, behavior, trend30d_pct, vol_percentile ✅
         - regime: non-empty string ✅
         - description: string ✅
         - behavior: string ✅
         - trend30d_pct: 0.5% (number) ✅
         - vol_percentile: 14 (number 0-100) ✅
      
      5. forecasts - ✅ PASSED
         - Count: 3 items (exactly as expected) ✅
         - Horizons: 24H, 7D, 30D (all present) ✅
         - All items have 15 required fields ✅
         - Validation checks for each forecast:
           * higher + lower ≈ 100% ✅
           * bull > bear ✅
           * bull, base, bear > 0 ✅
           * expected_low, expected_high > 0 ✅
           * confidence in ['Low','Moderate','High'] ✅
           * confidence_pct is number ✅
           * accuracy 0-100 ✅
           * invalidation > 0 ✅
           * invalidation_dir in ['above','below'] ✅
           * lean in ['UP','DOWN'] ✅
           * Logic check: lean=UP → invalidation_dir='below', lean=DOWN → invalidation_dir='above' ✅
           * expiry valid YYYY-MM-DD format ✅
         - Example: 24H forecast: higher=47.7%, lower=52.3%, bull=$64,888, bear=$62,563, lean=DOWN, invalidation_dir=above ✅
      
      6. factors - ✅ PASSED
         - Structure: object with 'bullish' and 'risk' keys ✅
         - bullish: list with 1 item (non-empty, up to 3 items) ✅
         - risk: list with 2 items (non-empty, up to 3 items) ✅
         - All items are non-empty strings ✅
      
      7. Existing fields - ✅ PASSED
         - All existing fields still present: signal, confidence, cv_folds, importances, performance, features, scoreboard, trades, live_record ✅
      
      Also verified:
      - GET /api/v1/health: compute_status='done', runs=6 ✅
      - GET /api/v1/ticker: live price=$64,110.50 from Kraken ✅
      
      NO CRITICAL ISSUES FOUND. All intelligence layer fields working as expected with real data.
      Data is REAL (ccxt Kraken). All validations passed including type checks, range checks, logic checks, and format validations.
    -agent: "testing"
    -message: |
      ✅ ALL NEW BACKEND FEATURES TESTED AND PASSED (4/4 + REGRESSION)
      
      Completed comprehensive testing of ALL new features via external URL (https://quant-features.preview.emergentagent.com/api/v1/*):
      
      FEATURE 1 - Decision Engine (dashboard.decision) - ✅ PASSED
      - Validated all 13 required fields: overall_score (48, int 0-100), label ('Neutral'), regime ('Weak Bearish Trend'), 
        regime_description, alignment ('Mixed / Neutral'), components (4 items with correct names), risk_level ('Low'), 
        risk_score (8), risk_drivers (3 fields), outlook (6 items: 24H/7D/30D/3M/6M/1Y), summary (792 chars), 
        news_signal (-0.163), news_bias ('Bearish')
      - All outlook items validated: higher+lower≈100%, lean logic correct (UP if higher>=50)
      - Also validated long_outlook: 3 items (3M/6M/1Y) with required fields
      
      FEATURE 2 - News→Forecast Link - ✅ PASSED
      - dashboard.news_forecast_link validated: signal=-0.163 (range -1..1), all 8 required fields present
      - 24H forecast: has news_link with all 9 required fields, higher_adj=45.0 ≈ clamp(46.1 + -1.1), lower_adj=55.0 ≈ 100-45.0
      - 7D forecast: has news_link with all required fields, higher_adj=47.2 ≈ clamp(47.9 + -0.7), lower_adj=52.8 ≈ 100-47.2
      - 30D forecast: correctly does NOT have news_link
      - All adjustment math validated
      
      FEATURE 3 - Ask Quant Chat - ✅ PASSED (5 scenarios)
      - Basic: POST /api/v1/chat returns {session_id, text (502 chars), model='gemini-3-flash-preview'}, correctly answered quant score question
      - Multi-turn memory: follow-up question correctly referenced prior conversation
      - Anti-hallucination: correctly declined to provide unavailable data (Christmas price, ETH gas)
      - Empty message: returns friendly error without crashing
      - History: GET /api/v1/chat/history returns stored messages with correct structure
      
      FEATURE 4 - Ticker AUD Price - ✅ PASSED
      - GET /api/v1/ticker now returns price_aud=$90,713.29 and aud_rate=1.4196
      - Validated: price_aud ≈ price * aud_rate (diff 0.000%), price_aud > price (AUD > USD), aud_rate in range 1.0-2.0
      
      REGRESSION - ✅ PASSED
      - GET /api/v1/health: status='ok', compute_status='idle', runs=11
      - GET /api/v1/dashboard: all 21 existing fields still present (signal, confidence, prob_up, prob_down, forecasts, 
        scoreboard, trades, quant_score, quant_label, quant_breakdown, regime, factors, importances, performance, 
        features, policy, dominance, chart, cycle, alerts)
      
      TEST SUMMARY: 11/11 tests passed
      - health (regression)
      - ticker (AUD price feature)
      - dashboard_decision (feature 1)
      - dashboard_news_link (feature 2)
      - dashboard_long_outlook
      - dashboard_regression
      - chat_basic (feature 3)
      - chat_memory (feature 3)
      - chat_anti_hallucination (feature 3)
      - chat_empty_message (feature 3)
      - chat_history (feature 3)
      
      NO CRITICAL ISSUES FOUND. All backend features working as expected with real data (ccxt Kraken).
      WebSockets NOT tested (as instructed).
