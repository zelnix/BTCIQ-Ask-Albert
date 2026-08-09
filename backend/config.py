"""Central configuration for the BitMarkAI backend.

Holds environment loading, the MongoDB connection, all collection handles, and the
API keys / model names. Extracted from server.py as part of the Option A refactor
(no behaviour changes — same env vars, same collection names, same defaults).
"""
import logging
import os

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/.env')

logger = logging.getLogger("btciq.config")

# --- environment sanity check -------------------------------------------------
# MONGO_URL / DB_NAME are injected by the deployment platform from the app secrets.
# Previously a missing injection silently fell back to mongodb://localhost:27017 and a
# database literally named "your_database_name", so the service booted "healthy" while
# talking to the wrong (or no) database. Now it is impossible to miss.
REQUIRED_ENV = ('MONGO_URL', 'DB_NAME')
_missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
if _missing:
    _msg = (
        'Missing required environment variable(s): %s. These are normally injected by '
        'the deployment platform from this app\'s secrets. Falling back to local '
        'development defaults - data will NOT be where you expect. Set STRICT_ENV=1 to '
        'refuse to start instead.' % ', '.join(_missing)
    )
    if os.environ.get('STRICT_ENV', '0').lower() in ('1', 'true', 'yes'):
        raise RuntimeError(_msg)
    logger.error('[config] %s', _msg)
    print('[config] ERROR: ' + _msg, flush=True)
else:
    logger.info('[config] all required environment variables present')
# ------------------------------------------------------------------------------

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'your_database_name')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

runs_col = db['btc_runs']
signals_col = db['live_signals']
dominance_col = db['dominance_hist']
news_col = db['news']
chat_col = db['ask_quant_chat']
predictions_col = db['predictions']
bitmark_col = db['bitmark_snapshots']
smart_alerts_col = db['smart_alerts']
audit_col = db['forecast_audit']
rate_col = db['rate_limits']  # cluster-wide per-client rate limiter (shared across replicas)
try:
    # Auto-expire hits after 25h so the 24h daily window is always fully covered.
    rate_col.create_index('ts', expireAfterSeconds=90000)
    rate_col.create_index([('key', 1), ('ts', 1)])
except Exception:  # noqa
    pass
insights_col = db['albert_insights']  # cache for AI-generated section insights
compare_col = db['compare_coins']  # cache for per-coin comparison summaries
coin_dash_col = db['coin_dashboards']  # cache for per-coin full dashboards (altcoins)
coin_news_col = db['coin_news']  # cache for per-coin news (altcoins)
coin_dom_col = db['coin_dominance_hist']  # per-coin market-cap dominance history
markets_col = db['markets_cache']  # per-coin vs traditional-markets comparison, cached daily
analogs_col = db['analogs_cache']  # historical-analog engine (Bitcoin), cached daily
glassnode_col = db['glassnode_cache']  # cached Glassnode on-chain metrics (Smart Money panel)
# Additional feature-engine / cache collections (consolidated here from server.py)
onchain_col = db['onchain_engine']
lev_col = db['leverage_engine']
misc_col = db['misc_cache']
usage_col = db['usage_stats']
etf_col = db['etf_flows']
whale_col = db['whale_wallets']
whale_hist_col = db['whale_history']
whale_tx_col = db['whale_tx_feed']

# Glassnode on-chain data (Smart Money panel). Advanced Light tier: 14d daily history, low call budget.
GLASSNODE_API_KEY = os.environ.get('GLASSNODE_API_KEY')
# Admin passcode gate for manual forecast runs (Stage-1: passcode instead of full auth).
# Default to empty so an unset env var DENIES access (fail-closed) rather than using a known default.
ADMIN_PASSCODE = os.environ.get('ADMIN_PASSCODE', '')

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
GEMINI_MODEL = 'gemini-2.5-flash'
# Ask Quant conversational model (Gemini 3 Flash via Emergent gateway, verified available)
CHAT_MODEL = os.environ.get('CHAT_MODEL', 'gemini-3-flash-preview')
