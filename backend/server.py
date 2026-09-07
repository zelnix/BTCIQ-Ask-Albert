"""
Bitcoin Predictive AI - FastAPI ML Microservice
----------------------------------------------
Real BTC/USD daily data (ccxt: Kraken primary, Coinbase fallback)
 -> price-agnostic stationary features (RSI, StochRSI, MACD hist, EMA ratio,
    ATR%, Bollinger width%, Volume Z-score, Volume ratio)
 -> RandomForest classifier (predict if tomorrow's close > today's close)
 -> TimeSeriesSplit cross-validation + walk-forward backtest (accuracy over time)
 -> persisted to MongoDB, refreshed daily via APScheduler.

Exposed under /api/v1/* and proxied by the Next.js /api layer.
"""
import os
import re
import time
import uuid
import math
import json
import base64
import io
import wave
import asyncio
import concurrent.futures
_LLM_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='albert-llm')
import threading
import datetime
import traceback
import urllib.request

import requests

import ccxt
import numpy as np
import pandas as pd
try:
    import shap  # SHAP factor contributions
    _HAS_SHAP = True
except Exception:  # noqa
    _HAS_SHAP = False
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit
from fastapi import FastAPI, Body, Request, Cookie, Header, Depends, Response, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

# --- Central configuration (env, Mongo connection, collections, API keys) ---
# Extracted to config.py (Option A refactor) — imported here for use across the module.
from config import (
    db, runs_col, signals_col, dominance_col, news_col, chat_col, predictions_col,
    bitmark_col, smart_alerts_col, audit_col, insights_col, compare_col, coin_dash_col,
    coin_news_col, coin_dom_col, markets_col, analogs_col, glassnode_col,
    onchain_col, lev_col, misc_col, usage_col, etf_col, whale_col, whale_hist_col, whale_tx_col,
    GLASSNODE_API_KEY, ADMIN_PASSCODE, GEMINI_MODEL, CHAT_MODEL, ALBERT_CHAT_MODEL,
    GEMINI_API_KEY, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE,
    RESEND_API_KEY, RESEND_FROM, DIGEST_TZ, DIGEST_HOUR, DIGEST_MINUTE,
    email_recipients_col, email_log_col, email_settings_col,
    PUBLIC_BASE_URL, UNSUB_SECRET, WEEKLY_HOUR, WEEKLY_MINUTE, regime_col,
    portfolio_col, price_watch_col, albert_calls_col, recap_col, mandate_col,
    paper_portfolio_col,
    users_col, auth_sessions_col, GOOGLE_CLIENT_ID,
)
from email_service import send_email, resend_configured
import regime_engine
import quant_validation
import drift_monitor
import orderflow
import time_machine

# CryptoMarkAI forecast trigger state (set by manual/event triggers, read by compute)
_forecast_trigger = {'reason': None}
_bitmark_last_manual = {'ts': 0.0}
_CORRIDOR_WIDEN = {}  # horizon label -> q_hat widen factor (self-heals corridors toward 90% coverage)

try:
    import feedparser
    _HAS_FEEDPARSER = True
except Exception:  # noqa
    _HAS_FEEDPARSER = False

# =====================================================================
# LLM BACKEND — direct Google Gemini via the official google-genai SDK.
# Previously all LLM traffic was routed through emergentintegrations; it now
# goes straight to Gemini keyed on GEMINI_API_KEY. A thin drop-in shim keeps
# every original LlmChat(...).with_model().with_params().with_tools()
# .send_message()/.send_message_with_tools() call site working unchanged.
# Stateless single-turn: callers assemble prior turns into the prompt.
# =====================================================================
# Legacy readiness flag (kept name-compatible across the file) now reflects the
# Gemini key — all `if LLM_READY_KEY ...` gates key off Gemini availability.
LLM_READY_KEY = GEMINI_API_KEY
_HAS_LLM = bool(GEMINI_API_KEY)


class UserMessage:
    """Minimal stand-in for emergentintegrations' UserMessage."""

    def __init__(self, text=''):
        self.text = text or ''


class _GeminiReply:
    """Reply wrapper exposing .content/.text (consumed by _extract) and .raw
    (the raw google-genai response, used for grounding-source extraction)."""

    def __init__(self, text, raw):
        self.content = text
        self.text = text
        self.raw = raw


class LlmChat:
    """Drop-in replacement for emergentintegrations.LlmChat backed by google-genai.
    Stateless single-turn — history is assembled into the prompt by callers."""

    def __init__(self, api_key=None, session_id=None, system_message=None):
        self._system = system_message
        self._model = None
        self._temp = None
        self._max = None
        self._tools = False

    def with_model(self, provider, model):
        self._model = model
        return self

    def with_params(self, temperature=None, max_tokens=None, **kwargs):
        self._temp = temperature
        self._max = max_tokens
        return self

    def with_tools(self, tools):
        # Only Google Search grounding is used anywhere in this app.
        self._tools = bool(tools)
        return self

    def _sync_generate(self, text):
        from google.genai import types
        model = self._model or CHAT_MODEL
        cfg = {}
        if self._system:
            cfg['system_instruction'] = self._system
        if self._max:
            cfg['max_output_tokens'] = int(self._max)
        if self._temp is not None:
            cfg['temperature'] = self._temp
        if self._tools:
            cfg['tools'] = [types.Tool(google_search=types.GoogleSearch())]
            # Google Search grounding is supported on Flash, not the Pro preview —
            # route grounded requests to Flash to avoid tool-unsupported errors.
            if 'pro' in (model or '').lower():
                model = CHAT_MODEL
        client = _get_genai_client()
        resp = client.models.generate_content(
            model=model, contents=(text or ''),
            config=types.GenerateContentConfig(**cfg))
        return _GeminiReply((getattr(resp, 'text', '') or '').strip(), resp)

    async def send_message(self, user_message):
        text = getattr(user_message, 'text', None) or str(user_message)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_generate, text)

    async def send_message_with_tools(self, user_message):
        return await self.send_message(user_message)

# in-memory ticker cache (avoid hammering the exchange on every poll)
_ticker_cache = {}  # symbol -> {'data':..., 'ts':...}
# USD->AUD fx rate cache (refreshed ~30 min)
_fx_cache = {'rate': None, 'ts': 0.0}


def grade_pending(df):
    """Resolve pending forward signals whose target candle close is now known."""
    close_by_date = {
        row['timestamp'].strftime('%Y-%m-%d'): float(row['close'])
        for _, row in df.iterrows()
    }
    for s in signals_col.find({'resolved': False}):
        tgt = s.get('predict_for_date')
        base = s.get('close_at_signal')
        if tgt in close_by_date and base:
            nc = close_by_date[tgt]
            actual = 'UP' if nc > base else 'DOWN'
            signals_col.update_one(
                {'_id': s['_id']},
                {'$set': {'resolved': True, 'next_close': round(nc, 2),
                          'actual': actual, 'correct': bool(actual == s['signal'])}},
            )


def record_live_signal(as_of, predict_for, signal, confidence, close):
    """Store today's forward signal as pending (one per as_of date)."""
    signals_col.update_one(
        {'as_of': as_of},
        {'$setOnInsert': {
            '_id': str(uuid.uuid4()), 'as_of': as_of,
            'predict_for_date': predict_for, 'signal': signal,
            'confidence': confidence, 'close_at_signal': close,
            'resolved': False, 'created_at': datetime.datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


def compute_live_record():
    resolved = list(signals_col.find({'resolved': True}, {'_id': 0}))
    tracked = signals_col.count_documents({})
    r = len(resolved)
    correct = sum(1 for s in resolved if s.get('correct'))
    return {
        'tracked': int(tracked), 'resolved': int(r), 'correct': int(correct),
        'winRate': round(correct / r * 100, 1) if r else None,
    }

app = FastAPI(title='BTC Predictive AI Engine')
# CORS: the browser talks to the backend only through the same-origin Next.js /api proxy,
# so lock direct cross-origin access to known origins (env-overridable) instead of '*'.
_cors_env = os.environ.get('CORS_ORIGINS', '')
_cors_origins = [o.strip() for o in _cors_env.split(',') if o.strip()]
if not _cors_origins:
    _base = os.environ.get('NEXT_PUBLIC_BASE_URL', '').strip().rstrip('/')
    _cors_origins = [o for o in [_base, 'http://localhost:3000', 'http://localhost:8001'] if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ['http://localhost:3000'],
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['*'],
)


# ---- Security helpers (per-client rate limiting + admin passcode) ----
# Extracted to security.py (Option A refactor).
from security import _client_key, _rate_limited, _passcode_ok, _retry_after_secs, _too_many

_state = {'status': 'idle', 'error': None, 'started_at': None}
_scheduler = None  # set in _startup(); read by the diagnostics endpoint
_lock = threading.Lock()

FEATURE_COLS = [
    'RSI', 'StochRSI', 'MACD_Hist_Norm', 'EMA_Ratio',
    'ATR_Pct', 'BB_Width_Pct', 'Volume_Z', 'Volume_Ratio',
]

FEATURE_META = {
    'RSI': {'label': 'RSI (14)', 'category': 'Momentum'},
    'StochRSI': {'label': 'Stochastic RSI', 'category': 'Momentum'},
    'MACD_Hist_Norm': {'label': 'MACD Histogram', 'category': 'Trend'},
    'EMA_Ratio': {'label': 'EMA 9/21 Ratio', 'category': 'Trend'},
    'ATR_Pct': {'label': 'ATR %', 'category': 'Volatility'},
    'BB_Width_Pct': {'label': 'Bollinger Width %', 'category': 'Volatility'},
    'Volume_Z': {'label': 'Volume Z-Score', 'category': 'Volume'},
    'Volume_Ratio': {'label': 'Volume Ratio', 'category': 'Volume'},
}


# =====================================================================
# STEP 1: FETCH RAW BITCOIN OHLCV DATA (real data, no API key needed)
# =====================================================================
def fetch_ohlcv():
    errors = []
    for name, sym in [('kraken', 'BTC/USD'), ('coinbase', 'BTC/USD')]:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            bars = ex.fetch_ohlcv(sym, timeframe='1d', limit=720)
            if bars and len(bars) > 250:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.sort_values('timestamp').reset_index(drop=True)
                return df, name
        except Exception as e:  # noqa
            errors.append(f'{name}: {e}')
    raise RuntimeError('All data sources failed: ' + ' | '.join(errors))


# =====================================================================
# STEP 2: PRICE-AGNOSTIC STATIONARY FEATURES (manual, numpy/pandas)
# =====================================================================
def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def _atr(high, low, close, length=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def build_features(df):
    df = df.copy()
    close = df['close']

    # Momentum
    rsi_raw = _rsi(close, 14)
    df['RSI'] = rsi_raw / 100.0
    min_r = rsi_raw.rolling(14).min()
    max_r = rsi_raw.rolling(14).max()
    df['StochRSI'] = ((rsi_raw - min_r) / (max_r - min_r).replace(0, np.nan)).clip(0, 1)

    # Trend
    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    df['MACD_Hist_Norm'] = (macd - signal) / close
    df['EMA_Ratio'] = (_ema(close, 9) / _ema(close, 21)) - 1.0

    # Volatility
    df['ATR_Pct'] = _atr(df['high'], df['low'], close, 14) / close
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    df['BB_Width_Pct'] = ((mid + 2 * std) - (mid - 2 * std)) / mid

    # Volume
    vol_ma = df['volume'].rolling(20).mean()
    vol_std = df['volume'].rolling(20).std()
    df['Volume_Z'] = (df['volume'] - vol_ma) / vol_std.replace(0, np.nan)
    df['Volume_Ratio'] = df['volume'] / vol_ma

    return df


# =====================================================================
# INSTITUTIONAL-GRADE ENGINES (no-key: block data, CoinGecko, chart TA)
# =====================================================================
def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'BitcoinQuant/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _http_text(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'BitcoinQuant/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8').strip()


HALVINGS = [
    (0, '2009-01-03', 50.0),
    (210000, '2012-11-28', 25.0),
    (420000, '2016-07-09', 12.5),
    (630000, '2020-05-11', 6.25),
    (840000, '2024-04-20', 3.125),
]
HALVING_REF_PRICE = {1: 12.0, 2: 650.0, 3: 8600.0, 4: 63900.0}  # approx BTC price on halving day
CYCLE_DAYS = 1460  # ~4 years


def fetch_block_height():
    for url in ['https://mempool.space/api/blocks/tip/height', 'https://blockchain.info/q/getblockcount']:
        try:
            return int(_http_text(url))
        except Exception:  # noqa
            continue
    return None


def compute_cycle_context(price, regime_name):
  try:
    height = fetch_block_height()
    if not height:
        return None
    interval = 210000
    epoch = max(0, min(height // interval, len(HALVINGS) - 1))
    reward = 50.0 / (2 ** epoch)
    last_block, last_date, _ = HALVINGS[epoch]
    next_block = (epoch + 1) * interval
    blocks_to_next = max(0, next_block - height)
    est_days_to_next = round(blocks_to_next * 10 / 1440, 1)
    last_dt = datetime.datetime.strptime(last_date, '%Y-%m-%d')
    days_since = (datetime.datetime.utcnow() - last_dt).days
    ref = HALVING_REF_PRICE.get(epoch)
    cycle_perf = round((price / ref - 1) * 100, 1) if ref else None
    progress = round(min(1.0, days_since / CYCLE_DAYS) * 100, 1)

    frac = days_since / CYCLE_DAYS
    if blocks_to_next < 21000:
        phase = 'Pre-Halving Transition'
    elif frac < 0.10:
        phase = 'Post-Halving Repricing'
    elif frac < 0.35:
        phase = 'Expansion'
    elif frac < 0.50:
        phase = 'Price Discovery'
    elif frac < 0.62:
        phase = 'Distribution Risk'
    elif frac < 0.85:
        phase = 'Contraction'
    else:
        phase = 'Accumulation'
    # blend with live regime (calendar is only context, not destiny)
    if 'Bearish' in regime_name and phase in ('Price Discovery', 'Distribution Risk'):
        phase = 'Contraction'
    return {
        'block_height': height, 'epoch': epoch, 'halving_number': epoch,
        'reward': reward, 'last_halving_date': last_date, 'days_since_halving': days_since,
        'next_halving_block': next_block, 'blocks_to_next': blocks_to_next,
        'est_days_to_next': est_days_to_next, 'cycle_perf_pct': cycle_perf,
        'cycle_progress_pct': progress, 'phase': phase,
    }
  except Exception:  # noqa
    traceback.print_exc()
    return None


def fetch_dominance(price_change_24h):
    try:
        g = _http_json('https://api.coingecko.com/api/v3/global')['data']
    except Exception:  # noqa
        return None
    dom = round(float(g['market_cap_percentage']['btc']), 2)
    total = float(g['total_market_cap']['usd'])
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    dominance_col.update_one({'date': today},
                             {'$set': {'dominance': dom, 'total_mcap': total}}, upsert=True)
    # derive change from stored history if present
    hist = list(dominance_col.find({}, {'_id': 0}).sort('date', -1).limit(40))

    def change_over(days):
        if len(hist) <= days:
            return None
        return round(dom - hist[days]['dominance'], 2)

    d7 = change_over(7)
    d30 = change_over(30)
    dom_dir = 'Neutral'
    ref = d7 if d7 is not None else None
    if ref is not None:
        dom_dir = 'Rising' if ref > 0.15 else ('Falling' if ref < -0.15 else 'Neutral')
    # 2D interpretation (price vs dominance)
    p_up = price_change_24h >= 0
    if dom_dir == 'Neutral':
        interp = 'Dominance is flat — no strong rotation signal yet (history is still building).'
    elif p_up and dom_dir == 'Rising':
        interp = 'Price up + dominance up: capital is concentrating into Bitcoin.'
    elif p_up and dom_dir == 'Falling':
        interp = 'Price up + dominance down: broad crypto risk-on expansion.'
    elif (not p_up) and dom_dir == 'Rising':
        interp = 'Price down + dominance up: defensive rotation out of altcoins into Bitcoin.'
    else:
        interp = 'Price down + dominance down: broad crypto-market weakness.'
    history = [{'date': h['date'], 'dominance': h['dominance']} for h in reversed(hist)][-30:]
    return {'dominance': dom, 'total_mcap_t': round(total / 1e12, 3),
            'change_7d': d7, 'change_30d': d30, 'direction': dom_dir,
            'interpretation': interp, 'history_points': len(hist), 'history': history}


COINGECKO_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'XRP': 'ripple',
    'ADA': 'cardano', 'DOGE': 'dogecoin', 'AVAX': 'avalanche-2', 'LINK': 'chainlink',
    'DOT': 'polkadot', 'LTC': 'litecoin', 'MATIC': 'matic-network', 'ATOM': 'cosmos',
}


def compute_coin_dominance(symbol, price_change_24h):
    """Real market-cap dominance (share of total crypto market cap) for any coin,
    keyless via CoinGecko. Shaped like the BTC dominance object so the UI can reuse it."""
    try:
        g = _http_json('https://api.coingecko.com/api/v3/global')['data']
    except Exception:  # noqa
        return None
    total = float(g['total_market_cap']['usd'])
    pct = g.get('market_cap_percentage', {}) or {}
    key = symbol.lower()
    dom = None
    mcap = None
    if key in pct:
        dom = round(float(pct[key]), 3)
        mcap = total * dom / 100.0
    else:
        cid = COINGECKO_IDS.get(symbol)
        if cid:
            try:
                arr = _http_json(f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={cid}')
                if arr and arr[0].get('market_cap'):
                    mcap = float(arr[0]['market_cap'])
                    dom = round(mcap / total * 100.0, 4)
            except Exception:  # noqa
                pass
    if dom is None:
        return None
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    coin_dom_col.update_one({'symbol': symbol, 'date': today},
                            {'$set': {'symbol': symbol, 'date': today, 'dominance': dom, 'total_mcap': total}},
                            upsert=True)
    hist = list(coin_dom_col.find({'symbol': symbol}, {'_id': 0}).sort('date', -1).limit(40))

    def change_over(days):
        if len(hist) <= days:
            return None
        return round(dom - hist[days]['dominance'], 3)
    d7 = change_over(7)
    d30 = change_over(30)
    dom_dir = 'Neutral'
    if d7 is not None:
        thr = max(0.02, dom * 0.03)
        dom_dir = 'Rising' if d7 > thr else ('Falling' if d7 < -thr else 'Neutral')
    p_up = price_change_24h >= 0
    name = COMPARE_COINS.get(symbol, {}).get('name', symbol) if 'COMPARE_COINS' in globals() else symbol
    if dom_dir == 'Neutral':
        interp = f'{name}\u2019s market share is holding steady (history is still building).'
    elif p_up and dom_dir == 'Rising':
        interp = f'Price up + share rising: capital is rotating into {name}.'
    elif p_up and dom_dir == 'Falling':
        interp = f'Price up but share slipping: the broader market is rising even faster than {name}.'
    elif (not p_up) and dom_dir == 'Rising':
        interp = f'Price down but share rising: {name} is holding up better than the market.'
    else:
        interp = f'Price down + share falling: {name} is underperforming the broader market.'
    history = [{'date': h['date'], 'dominance': h['dominance']} for h in reversed(hist)][-30:]
    return {'dominance': dom, 'total_mcap_t': round(total / 1e12, 3),
            'mcap_usd': round(mcap) if mcap else None,
            'change_7d': d7, 'change_30d': d30, 'direction': dom_dir,
            'interpretation': interp, 'history_points': len(hist), 'history': history}


def _swings(series, order=4):
    vals = series.values
    highs, lows = [], []
    for i in range(order, len(vals) - order):
        w = vals[i - order:i + order + 1]
        if vals[i] == w.max():
            highs.append((i, float(vals[i])))
        if vals[i] == w.min():
            lows.append((i, float(vals[i])))
    return highs, lows


def _cluster_levels(points, price, tol=0.015):
    levels = []
    for _, p in sorted(points, key=lambda z: z[1]):
        placed = False
        for lv in levels:
            if abs(p - lv['price']) / price < tol:
                lv['price'] = (lv['price'] * lv['strength'] + p) / (lv['strength'] + 1)
                lv['strength'] += 1
                placed = True
                break
        if not placed:
            levels.append({'price': p, 'strength': 1})
    return levels


def compute_chart_intelligence(df):
    d = df.tail(260).reset_index(drop=True)
    close = d['close']; high = d['high']; low = d['low']; vol = d['volume']
    price = float(close.iloc[-1])
    ema20 = _ema(close, 20).iloc[-1]; ema50 = _ema(close, 50).iloc[-1]
    ema200 = _ema(close, 200).iloc[-1] if len(close) >= 200 else _ema(close, 100).iloc[-1]

    if price > ema20 > ema50 and price > ema200:
        structure = 'Uptrend'; struct_bias = 'Bullish'
    elif price < ema20 < ema50 and price < ema200:
        structure = 'Downtrend'; struct_bias = 'Bearish'
    else:
        structure = 'Range / Transition'; struct_bias = 'Neutral'

    highs, lows = _swings(close, order=4)
    res = [lv for lv in _cluster_levels(highs, price) if lv['price'] > price * 1.001]
    sup = [lv for lv in _cluster_levels(lows, price) if lv['price'] < price * 0.999]
    res = sorted(res, key=lambda z: (-z['strength'], z['price']))[:3]
    sup = sorted(sup, key=lambda z: (-z['strength'], -z['price']))[:3]
    sr_levels = ([{'price': round(l['price'], 0), 'type': 'resistance', 'strength': int(l['strength'])} for l in res]
                 + [{'price': round(l['price'], 0), 'type': 'support', 'strength': int(l['strength'])} for l in sup])

    signals = []
    signals.append({'type': 'Moving-Average Structure', 'bias': struct_bias,
                    'detail': f'Price {"above" if price>ema50 else "below"} EMA50 and EMA200 — {structure.lower()} structure.'})

    hi20 = float(high.iloc[-21:-1].max()); lo20 = float(low.iloc[-21:-1].min())
    volz = float((vol.iloc[-1] - vol.tail(20).mean()) / (vol.tail(20).std() or 1))
    if price > hi20:
        signals.append({'type': 'Breakout', 'bias': 'Bullish',
                        'detail': f'Close broke above the 20-day high (${hi20:,.0f}){" with volume confirmation" if volz>0.5 else " but volume is light"}.'})
    elif price < lo20:
        signals.append({'type': 'Breakdown', 'bias': 'Bearish',
                        'detail': f'Close broke below the 20-day low (${lo20:,.0f}){" with volume confirmation" if volz>0.5 else " but volume is light"}.'})

    bbw = ((close.rolling(20).mean() + 2 * close.rolling(20).std()) - (close.rolling(20).mean() - 2 * close.rolling(20).std())) / close.rolling(20).mean()
    bbw_pct = float((bbw.tail(180) < bbw.iloc[-1]).mean())
    if bbw_pct < 0.2:
        signals.append({'type': 'Volatility Compression', 'bias': 'Neutral',
                        'detail': f'Bollinger Band width is in the {round(bbw_pct*100)}th percentile — a squeeze that often precedes a large move.'})

    rsi_s = _rsi(close, 14)
    if len(lows) >= 2 and len(highs) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p2 < p1 and rsi_s.iloc[i2] > rsi_s.iloc[i1]:
            signals.append({'type': 'Bullish Momentum Divergence', 'bias': 'Bullish',
                            'detail': 'Price made a lower low while RSI made a higher low — waning downside momentum.'})
        (j1, q1), (j2, q2) = highs[-2], highs[-1]
        if q2 > q1 and rsi_s.iloc[j2] < rsi_s.iloc[j1]:
            signals.append({'type': 'Bearish Momentum Divergence', 'bias': 'Bearish',
                            'detail': 'Price made a higher high while RSI made a lower high — waning upside momentum.'})

    # last-candle pattern
    o1, c1, h1, l1 = float(d['open'].iloc[-1]), price, float(high.iloc[-1]), float(low.iloc[-1])
    o0, c0 = float(d['open'].iloc[-2]), float(close.iloc[-2])
    body = abs(c1 - o1); rng = max(h1 - l1, 1e-9); upper = h1 - max(c1, o1); lower = min(c1, o1) - l1
    pattern = None
    if c1 > o1 and c0 < o0 and c1 >= o0 and o1 <= c0:
        pattern = ('Bullish Engulfing', 'Bullish')
    elif c1 < o1 and c0 > o0 and o1 >= c0 and c1 <= o0:
        pattern = ('Bearish Engulfing', 'Bearish')
    elif lower > body * 2 and upper < body:
        pattern = ('Hammer', 'Bullish')
    elif upper > body * 2 and lower < body:
        pattern = ('Shooting Star', 'Bearish')
    elif body < rng * 0.1:
        pattern = ('Doji', 'Neutral')
    if pattern:
        signals.append({'type': f'Candlestick: {pattern[0]}', 'bias': pattern[1],
                        'detail': f'The latest daily candle printed a {pattern[0].lower()} pattern.'})

    # Predictive chart model: historical base rates over full df
    cf = df['close']
    up_break = cf > cf.rolling(20).max().shift(1)
    dn_break = cf < cf.rolling(20).min().shift(1)
    fwd5_up = cf.shift(-5) > cf
    bo_up = float(fwd5_up[up_break].mean()) if up_break.sum() > 5 else 0.5
    bo_dn = float((~fwd5_up)[dn_break].mean()) if dn_break.sum() > 5 else 0.5
    breakout_up = round(bo_up * 100, 1)
    breakdown = round(bo_dn * 100, 1)
    consolidation = round(max(0.0, 100 - breakout_up - breakdown), 1)
    near_res = res[0]['price'] if res else None
    near_sup = sup[0]['price'] if sup else None
    if price > hi20:
        primary = f'Fresh breakout above ${hi20:,.0f}. Historically {breakout_up}% of 20-day-high breakouts saw a higher close within 5 days.'
    elif near_res and (near_res - price) / price < 0.03:
        primary = f'Price is testing resistance near ${near_res:,.0f}. A 4h/daily close above it with volume would favour continuation.'
    elif near_sup and (price - near_sup) / price < 0.03:
        primary = f'Price is leaning on support near ${near_sup:,.0f}. Holding it keeps the structure intact.'
    else:
        primary = f'Price is mid-range between support (${near_sup:,.0f})' if near_sup else 'Price is in open air'
        primary += f' and resistance (${near_res:,.0f}).' if near_res else '.'

    ohlc = [{'t': r['timestamp'].strftime('%m/%d'),
             'o': round(float(r['open']), 0), 'h': round(float(r['high']), 0),
             'l': round(float(r['low']), 0), 'c': round(float(r['close']), 0)}
            for _, r in df.tail(90).iterrows()]

    return {
        'structure': structure, 'structure_bias': struct_bias,
        'signals': signals, 'sr_levels': sr_levels,
        'predictive': {'breakout_up': breakout_up, 'breakdown': breakdown,
                       'consolidation': consolidation, 'primary_setup': primary},
        'ohlc': ohlc,
        'range20': {'high': round(hi20, 0), 'low': round(lo20, 0)},
    }


def build_market_intel(quant, forecasts, cycle, dominance, chart):
    f24 = next((f for f in forecasts if f['horizon'] == '24H'), None)
    f7 = next((f for f in forecasts if f['horizon'] == '7D'), None)
    dom_txt = f"{dominance['direction']} ({dominance['dominance']}%)" if dominance else 'n/a'
    return {
        'quant_score': quant['quant_score'], 'quant_label': quant['quant_label'],
        'regime': quant['regime']['regime'],
        'higher_24h': f24['higher'] if f24 else None,
        'higher_7d': f7['higher'] if f7 else None,
        'confidence': f7['confidence'] if f7 else (f24['confidence'] if f24 else 'n/a'),
        'technical_structure': chart['structure'] if chart else 'n/a',
        'pressure_map': 'Awaiting data source (Glassnode)',
        'smart_money': 'Awaiting data source (Glassnode)',
        'exchange_supply': 'Awaiting data source (Glassnode)',
        'derivatives_risk': 'Awaiting data source (CoinGlass/CME)',
        'crowd': 'Awaiting data source (LunarCrush)',
        'hype_risk': 'Awaiting data source (LunarCrush)',
        'dominance': dom_txt,
        'cycle_phase': cycle['phase'] if cycle else 'n/a',
        'top_positive': quant['factors']['bullish'][0],
        'top_risk': quant['factors']['risk'][0],
    }


# =====================================================================
# CROSS-MARKET + POLICY & LIQUIDITY + ALERTS (keyless: Yahoo + curated)
# =====================================================================
def fetch_yahoo_series(symbol, rng='6mo'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={rng}'
    d = _http_json(url)['chart']['result'][0]
    ts = d['timestamp']; cl = d['indicators']['quote'][0]['close']
    s = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        s[datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')] = float(c)
    return pd.Series(s).sort_index()


CROSS_ASSETS = [('Nasdaq 100', '%5ENDX'), ('S&P 500', '%5EGSPC'), ('US Dollar (DXY)', 'DX-Y.NYB'),
                ('10Y Yield', '%5ETNX'), ('VIX', '%5EVIX'), ('Gold', 'GC=F')]


def compute_crossmarket():
    btc = fetch_yahoo_series('BTC-USD')
    btc_ret = np.log(btc / btc.shift(1))
    raw = {}; out = []
    for name, sym in CROSS_ASSETS:
        try:
            s = fetch_yahoo_series(sym); raw[name] = s
            r = np.log(s / s.shift(1))
            j = pd.concat([btc_ret, r], axis=1, keys=['b', 'a']).dropna()

            def corr(n):
                x = j.tail(n)
                return round(float(x['b'].corr(x['a'])), 2) if len(x) > 3 else None
            c30 = corr(30)
            beta = None
            x = j.tail(30)
            if len(x) > 3 and x['a'].var() > 0:
                beta = round(float(x['b'].cov(x['a']) / x['a'].var()), 2)
            ar = abs(c30 or 0)
            lab = ('Strong' if ar > 0.6 else 'Moderate' if ar > 0.3 else 'Weak') + (' Positive' if (c30 or 0) >= 0 else ' Negative')
            out.append({'asset': name, 'price': round(float(s.iloc[-1]), 2),
                        'corr_7d': corr(7), 'corr_30d': c30, 'corr_90d': corr(90),
                        'beta_30d': beta, 'label': lab})
        except Exception:  # noqa
            traceback.print_exc()
    return out, raw


CENTRAL_BANKS = [
    ('US Federal Reserve', '3.50–3.75%', 'Hold', '2026-07-29'),
    ('European Central Bank', '2.15%', 'Cut', '2026-06'),
    ('Bank of England', '3.75%', 'Cut', '2026-06'),
    ('Bank of Japan', '0.75%', 'Hold', '2026-07'),
    ('Reserve Bank of Australia', '3.35%', 'Cut', '2026-07'),
    ('Bank of Canada', '2.25%', 'Hold', '2026-06'),
    ("People's Bank of China", '2.90% (1Y LPR)', 'Hold', '2026-07'),
]
REG_EVENTS = [
    {'title': 'US spot Bitcoin ETFs', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Strong access-positive', 'note': 'Institutional access channel live and growing.'},
    {'title': 'EU MiCA framework', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'EU', 'impact': 'Certainty-positive', 'note': 'Fully applicable since 2024-12-30. Commission review during 2026 may amend.'},
    {'title': 'SEC SAB 122 (rescinds SAB 121)', 'stage': 'Effective & implemented', 'stage_num': 10, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Access-positive', 'note': 'Removed the SEC accounting rule deterring bank custody (2025-01-30). Not a blanket authorisation — prudential/AML rules still apply.'},
    {'title': 'US CLARITY Act (market structure)', 'stage': 'Passed one chamber; Senate cmte reported', 'stage_num': 6, 'direction': 1,
     'jurisdiction': 'US', 'impact': 'Positive but UNCONFIRMED', 'note': 'Passed House Jul 2025; Senate Banking advanced May 2026; reported Jun 1 2026. PROPOSED legislation — not yet law.'},
]
POLICY_CALENDAR = [
    {'event': 'US CPI', 'date': '2026-08-12', 'importance': 'Very High', 'btc_sensitivity': 'High'},
    {'event': 'US PCE', 'date': '2026-08-28', 'importance': 'High', 'btc_sensitivity': 'Moderate'},
    {'event': 'US Nonfarm Payrolls', 'date': '2026-09-04', 'importance': 'High', 'btc_sensitivity': 'Moderate'},
    {'event': 'FOMC Rate Decision', 'date': '2026-09-16', 'importance': 'Very High', 'btc_sensitivity': 'High'},
]


def _zscore(series):
    s = series.dropna()
    if len(s) < 20:
        return 0.0
    return float((s.iloc[-1] - s.tail(90).mean()) / (s.tail(90).std() or 1))


def compute_policy(raw):
    dxy = raw.get('US Dollar (DXY)'); y10 = raw.get('10Y Yield'); vix = raw.get('VIX')
    dxy_z = _zscore(dxy) if dxy is not None else 0.0
    y10_z = _zscore(y10) if y10 is not None else 0.0
    vix_z = _zscore(vix) if vix is not None else 0.0
    impulse_z = float(np.mean([-dxy_z, -y10_z, -vix_z]))
    liq = round(max(0, min(100, 50 + impulse_z * 18)))
    liq_state = ('Strong Liquidity Expansion' if liq >= 80 else 'Moderate Expansion' if liq >= 65
                 else 'Neutral / Transitioning' if liq >= 45 else 'Moderate Contraction' if liq >= 30
                 else 'Strong Liquidity Contraction')
    monetary_path = 60          # Fed on hold, market pricing gradual cuts (curated)
    real_dollar = round(max(0, min(100, 50 - (dxy_z + y10_z) * 15)))
    banking_access = 68         # SAB122 + spot ETFs live (curated)
    reg_direction = 64          # net enacted-positive (MiCA, ETFs) vs proposed CLARITY (curated)
    legislative_certainty = 45  # CLARITY still proposed
    event_risk = 55
    score = round(liq * 0.25 + monetary_path * 0.20 + real_dollar * 0.15 + banking_access * 0.15
                  + reg_direction * 0.15 + legislative_certainty * 0.05 + event_risk * 0.05)
    label = ('Strongly Supportive' if score >= 80 else 'Moderately Supportive' if score >= 65
             else 'Mixed / Neutral' if score >= 45 else 'Moderately Restrictive' if score >= 30
             else 'Strongly Restrictive')
    return {
        'score': score, 'label': label,
        'liquidity_impulse': liq, 'liquidity_state': liq_state,
        'components': {'dxy_z': round(dxy_z, 2), 'y10_z': round(y10_z, 2), 'vix_z': round(vix_z, 2)},
        'dxy': round(float(dxy.iloc[-1]), 2) if dxy is not None else None,
        'y10': round(float(y10.iloc[-1]), 2) if y10 is not None else None,
        'vix': round(float(vix.iloc[-1]), 2) if vix is not None else None,
        'central_banks': [{'bank': b, 'rate': r, 'last': d2, 'date': dt} for b, r, d2, dt in CENTRAL_BANKS],
        'regulation': REG_EVENTS, 'calendar': POLICY_CALENDAR,
        'tailwind': 'Global liquidity is stabilising and institutional access (spot ETFs, post-SAB122 custody) is expanding.',
        'risk': 'Real yields and the dollar remain firm, and major US market-structure law (CLARITY Act) is still only proposed.',
        'interpretation': 'Policy conditions are constructive but not yet fully confirmed by capital flows.',
    }


def compute_alerts(quant, cycle, policy, chart, cm):
    a = []
    now = datetime.datetime.utcnow()
    ts = now.strftime('%Y-%m-%d %H:%M UTC')

    def add(level, typ, msg):
        a.append({'level': level, 'type': typ, 'message': msg, 'ts': ts})

    add('info', 'Regime', f"Market regime: {quant['regime']['regime']}. {quant['regime']['behavior']}")
    if policy:
        add('info', 'Liquidity', f"Global Liquidity Impulse {policy['liquidity_impulse']}/100 — {policy['liquidity_state']}. Policy & Liquidity Score {policy['score']} ({policy['label']}).")
        for e in policy['calendar']:
            try:
                days = (datetime.datetime.strptime(e['date'], '%Y-%m-%d').date() - now.date()).days
                if 0 <= days <= 10:
                    add('warning', 'Event Risk', f"{e['event']} in {days}d — {e['importance']} importance, BTC sensitivity {e['btc_sensitivity']}.")
            except Exception:  # noqa
                pass
    if chart:
        for s in chart['signals']:
            if s['type'].startswith('Breakout') or s['type'].startswith('Breakdown') or 'Divergence' in s['type']:
                add('danger' if s['bias'] == 'Bearish' else 'success', 'Chart', f"{s['type']}: {s['detail']}")
    if cm:
        nd = next((x for x in cm if x['asset'] == 'Nasdaq 100'), None)
        if nd and nd['corr_30d'] is not None and abs(nd['corr_30d']) > 0.6:
            add('info', 'Cross-Market', f"BTC–Nasdaq 30d correlation {nd['corr_30d']} ({nd['label']}) — equities currently carry more weight in the 24h/7d models.")
    return a


# =====================================================================
# BTC NEWS INTELLIGENCE (keyless RSS + Gemini 2.5 Flash summaries)
# =====================================================================
NEWS_SOURCES = [
    ('CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 72),
    ('Cointelegraph', 'https://cointelegraph.com/rss', 68),
    ('Bitcoin Magazine', 'https://bitcoinmagazine.com/feed', 68),
    ('Decrypt', 'https://decrypt.co/feed', 68),
    ('Federal Reserve', 'https://www.federalreserve.gov/feeds/press_all.xml', 95),
]
BTC_KEYWORDS = ['bitcoin', 'btc', 'crypto', 'ether', 'ethereum', 'sec', 'etf', 'federal reserve',
                'interest rate', 'rate cut', 'rate hike', 'inflation', 'cpi', 'stablecoin', 'coinbase',
                'binance', 'microstrategy', 'halving', 'mining', 'blackrock', 'custody', 'fomc',
                'monetary', 'open market', 'payroll', 'employment', 'treasury']

NEWS_SYSTEM = (
    "You are a Bitcoin market news analyst. Given a headline and article text, return ONLY one JSON "
    "object (no markdown, no prose) with EXACTLY these keys: "
    '{"summary": "2-sentence factual summary", "why_it_matters": "1-2 sentences on why it matters for Bitcoin", '
    '"direction": "bullish|bearish|mixed|neutral", "bullish_pct": int, "bearish_pct": int, "neutral_pct": int, '
    '"impact_score": int 0-100, "confidence": float 0-1, '
    '"time_horizons": {"immediate":"bullish|bearish|mixed|neutral","seven_day":"...","long_term":"..."}, '
    '"categories": ["one or more of: central_banks, inflation_employment, regulation, etf, institutional_adoption, '
    'corporate_holdings, exchange_custody, security_breach, mining_network, stablecoins, whale_onchain, derivatives, '
    'geopolitics, technology_protocol, social_sentiment, rumor"]}. '
    "Rules: bullish_pct+bearish_pct+neutral_pct MUST sum to 100. Only use the provided material; never invent facts "
    "or quotes. If the story is not Bitcoin-relevant, set direction neutral and a low impact_score. "
    "Keep 'summary' under 40 words and 'why_it_matters' under 35 words. Output compact valid JSON only."
)


def generate_news_summary(headline, text):
    chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'news-{abs(hash(headline)) % 99999}',
                    system_message=NEWS_SYSTEM)
            .with_model('gemini', _model_for('news'))
            .with_params(temperature=0.0, max_tokens=1200))
    reply = asyncio.run(chat.send_message(UserMessage(text=f'Headline: {headline}\n\nArticle:\n{text[:4000]}')))
    raw = (getattr(reply, 'text', None) or str(reply)).strip()
    if '```' in raw:
        raw = re.sub(r'```(?:json)?', '', raw).strip()
    s, e = raw.find('{'), raw.rfind('}')
    obj = json.loads(raw[s:e + 1])
    return obj


def _norm_title(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())[:45]


def fetch_news():
    entries = []
    for name, url, cred in NEWS_SOURCES:
        try:
            fp = feedparser.parse(url)
            for e in fp.entries[:12]:
                title = e.get('title', '')
                summ = re.sub('<[^>]+>', '', e.get('summary', e.get('description', '')))[:1400]
                blob = (title + ' ' + summ).lower()
                if name != 'Federal Reserve' and not any(k in blob for k in BTC_KEYWORDS):
                    continue
                entries.append({'source': name, 'credibility': cred, 'title': title,
                                'summary': summ.strip(), 'link': e.get('link', ''),
                                'published': e.get('published', e.get('updated', ''))})
        except Exception:  # noqa
            traceback.print_exc()

    # --- Cluster near-duplicate stories across sources into one story each ---
    def _toks(t):
        stop = {'the', 'a', 'an', 'to', 'of', 'in', 'on', 'for', 'and', 'is', 'as', 'at',
                'by', 'it', 'be', 'with', 'from', 'that', 'this', 'its', 'are', 'will', 'has'}
        return set(w for w in re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower()).split()
                   if len(w) > 2 and w not in stop)

    clusters = []
    for e in entries:
        et = _toks(e['title'])
        if not et:
            continue
        placed = False
        for cl in clusters:
            inter = len(et & cl['tokens'])
            union = len(et | cl['tokens']) or 1
            if inter / union >= 0.34 or (inter >= 3 and inter >= 0.6 * min(len(et), len(cl['tokens']))):
                cl['members'].append(e)
                cl['tokens'] |= et
                placed = True
                break
        if not placed:
            clusters.append({'tokens': set(et), 'members': [e]})

    clusters.sort(key=lambda cl: (-len(set(m['source'] for m in cl['members'])),
                                  -max(m['credibility'] for m in cl['members'])))
    clusters = clusters[:8]

    SPEC_WORDS = ('rumor', 'rumour', 'reportedly', 'could ', 'may ', 'might', 'proposal',
                  'proposed', 'unconfirmed', 'alleged', 'speculat', 'plans to', 'considering',
                  'reports', 'said to', 'expected to')

    cards = []
    for cl in clusters:
        members = cl['members']
        rep = max(members, key=lambda m: m['credibility'])
        sources = [{'source': m['source'], 'link': m['link'], 'credibility': m['credibility'],
                    'published': m['published'], 'title': m['title']} for m in members]
        n_src = len(set(m['source'] for m in members))
        ai = None
        if LLM_READY_KEY and _HAS_LLM:
            try:
                ai = generate_news_summary(rep['title'], rep['summary'] or rep['title'])
            except Exception:  # noqa
                traceback.print_exc()
        if not ai:
            ai = {'summary': (rep['summary'] or rep['title'])[:220], 'why_it_matters': '',
                  'direction': 'neutral', 'bullish_pct': 40, 'bearish_pct': 30, 'neutral_pct': 30,
                  'impact_score': 40, 'confidence': 0.4,
                  'time_horizons': {'immediate': 'neutral', 'seven_day': 'neutral', 'long_term': 'neutral'},
                  'categories': ['general']}
        try:
            imp = int(round(float(ai.get('impact_score', 40)) * (0.55 + 0.45 * rep['credibility'] / 100)))
        except Exception:  # noqa
            imp = 40
        imp = max(0, min(100, imp))
        imp_label = ('Market Moving' if imp >= 85 else 'High Impact' if imp >= 70 else 'Important'
                     if imp >= 50 else 'Monitor' if imp >= 30 else 'Low Significance')
        # Confirmed vs unconfirmed
        blob = (rep['title'] + ' ' + (rep['summary'] or '')).lower()
        speculative = any(w in blob for w in SPEC_WORDS)
        max_cred = max(m['credibility'] for m in members)
        if n_src >= 2 and max_cred >= 65 and not speculative:
            verification = 'Confirmed'
        elif speculative or max_cred < 55:
            verification = 'Unconfirmed'
        else:
            verification = 'Single-source'
        # Per-story forecast impact (model interpretation, honest & bounded)
        dirn = ai.get('direction', 'neutral')
        sign = 1 if dirn == 'bullish' else -1 if dirn == 'bearish' else 0
        nudge = round(sign * imp / 100 * 3.0, 1)
        forecast_impact = {
            'direction': dirn, 'nudge_pts': nudge,
            'horizons': ['24H', '7D'] if imp >= 50 else ['24H'],
            'note': (f'Nudges near-term higher-odds by {"+" if nudge > 0 else ""}{nudge} pts'
                     if nudge else 'No material push to the near-term odds') + ' (model interpretation).',
        }
        cards.append({**rep, 'ai': ai, 'impact': imp, 'impact_label': imp_label,
                      'sources': sources, 'n_sources': n_src,
                      'verification': verification, 'forecast_impact': forecast_impact})
    cards.sort(key=lambda c: -c['impact'])

    bull = sum(1 for c in cards if c['ai'].get('direction') == 'bullish')
    bear = sum(1 for c in cards if c['ai'].get('direction') == 'bearish')
    bias = 'Moderately Bullish' if bull > bear else 'Moderately Bearish' if bear > bull else 'Mixed / Neutral'
    tail = next((c for c in cards if c['ai'].get('direction') == 'bullish'), None)
    risk = next((c for c in cards if c['ai'].get('direction') == 'bearish'), None)
    briefing = {
        'bias': bias, 'total': len(cards),
        'major_stories': sum(1 for c in cards if c['impact'] >= 70),
        'market_moving': sum(1 for c in cards if c['impact'] >= 85),
        'top_tailwind': (tail['ai'].get('why_it_matters') or tail['title']) if tail else 'No clear bullish catalyst in the current feed.',
        'top_risk': (risk['ai'].get('why_it_matters') or risk['title']) if risk else 'No clear bearish catalyst in the current feed.',
        'next_event': POLICY_CALENDAR[0] if POLICY_CALENDAR else None,
    }
    doc = {'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
           'cards': cards, 'briefing': briefing,
           'model': (GEMINI_MODEL if (LLM_READY_KEY and _HAS_LLM) else 'rule-based')}
    try:
        fire_news_alerts(cards)
    except Exception:  # noqa
        traceback.print_exc()
    # Keep only the most-recent news snapshots. Insert BEFORE trimming (so there is
    # never an empty window) and only ever trim OLDER docs beyond a small retention
    # window — a bounded cleanup, never a full-collection wipe on a managed DB.
    news_col.insert_one({**doc, '_id': doc['id']})
    try:
        keep_ids = [d['_id'] for d in news_col.find({}, {'_id': 1}).sort('created_at', -1).limit(5)]
        if keep_ids:
            news_col.delete_many({'_id': {'$nin': keep_ids}})
    except Exception:  # noqa
        traceback.print_exc()
    return doc


def fire_news_alerts(cards):
    """Turn each Confirmed, high-impact story into a Smart Alert (once ever, per story)."""
    as_of = datetime.date.today().isoformat()
    now_iso = datetime.datetime.utcnow().isoformat()
    for c in cards:
        # Fire for corroborated OR single-source stories (skip clearly speculative/unconfirmed),
        # with a slightly looser impact bar so meaningful news reliably surfaces as an alert.
        if c.get('verification') == 'Unconfirmed' or int(c.get('impact', 0) or 0) < 60:
            continue
        key = 'news_' + _norm_title(c.get('title', ''))
        if not key or key == 'news_':
            continue
        fi = c.get('forecast_impact') or {}
        why = (c.get('ai') or {}).get('why_it_matters') or (c.get('ai') or {}).get('summary') or ''
        sev = 'high' if int(c.get('impact', 0)) >= 85 else 'warning'
        msg = f"{why} Effect on CryptoMarkAI forecast: {fi.get('note', 'neutral')}".strip()
        try:
            smart_alerts_col.update_one(
                {'_id': key},
                {'$setOnInsert': {
                    '_id': key, 'id': key, 'ts': now_iso, 'as_of': as_of, 'symbol': 'BTC',
                    'category': 'News', 'severity': sev,
                    'title': c.get('title', 'High-impact story')[:120],
                    'message': msg[:400], 'seen': False,
                    'link': c.get('link'), 'impact': int(c.get('impact', 0)),
                    'forecast_nudge': fi.get('nudge_pts'),
                }}, upsert=True)
        except Exception:  # noqa
            traceback.print_exc()


_news_state = {'status': 'idle', 'error': None}


def run_news_bg():
    if _news_state['status'] == 'running':
        return
    _news_state['status'] = 'running'
    _news_state['error'] = None
    try:
        fetch_news()
        _news_state['status'] = 'done'
    except Exception as ex:  # noqa
        _news_state['status'] = 'error'
        _news_state['error'] = str(ex)
        traceback.print_exc()


# =====================================================================
# STEP 3-5: TARGET, CV, WALK-FORWARD BACKTEST, LIVE SIGNAL
# =====================================================================
def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _quant_score_label(s):
    if s >= 80: return 'Strongly Bullish'
    if s >= 60: return 'Moderately Bullish'
    if s >= 55: return 'Weakly Bullish'
    if s > 45:  return 'Neutral'
    if s > 40:  return 'Weakly Bearish'
    if s > 20:  return 'Bearish'
    return 'Strongly Bearish'


def _sig_word(s):
    if s >= 58: return 'Bullish'
    if s <= 42: return 'Bearish'
    return 'Neutral'


def _triple_barrier_target(close, high, low, h, atr_frac, pt_mult=1.5, sl_mult=1.0):
    """ATR-scaled Triple-Barrier labels (López de Prado), mapped to a binary directional
    target: 1 = take-profit hit first OR time-stop closed up; 0 = stop-loss hit first OR
    time-stop closed down. Barriers scale with per-bar ATR so labels track volatility."""
    n = len(close)
    c = np.asarray(close, dtype=float)
    hi = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    a = np.asarray(atr_frac, dtype=float)
    out = np.full(n, np.nan)
    for i in range(n):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = c[i]
        up_b = entry * (1 + pt_mult * a[i])
        dn_b = entry * (1 - sl_mult * a[i])
        end = min(i + h, n - 1)
        lab = None
        for j in range(i + 1, end + 1):
            uh = hi[j] >= up_b
            lh = lo[j] <= dn_b
            if uh and lh:
                lab = 0  # conservative: assume stop hit first within the bar
                break
            if uh:
                lab = 1
                break
            if lh:
                lab = 0
                break
        if lab is None:  # vertical (time) barrier -> sign of realised return
            lab = 1 if c[end] > entry else 0
        out[i] = lab
    return pd.Series(out, index=close.index)


def _conformal_corridor(Xf, close, lx, h, price, alpha=0.10):
    """Conformalized Quantile Regression (CQR): distribution-free price corridor with a
    (1-alpha) coverage guarantee. Trains GBR quantile models on future h-day RETURNS, then
    corrects the raw quantiles by the conformal non-conformity factor q_hat on an unseen
    calibration split. Returns lower/upper prices, width, empirical coverage and q_hat."""
    try:
        n = len(Xf)
        y = (close.shift(-h) / close - 1.0)  # future h-day return (stationary target)
        Xv = Xf.iloc[:n - h].reset_index(drop=True)
        yv = y.iloc[:n - h].reset_index(drop=True)
        m = len(Xv)
        if m < 120:
            return None
        cut = int(m * 0.7)
        Xtr, ytr = Xv.iloc[:cut], yv.iloc[:cut]
        Xcal, ycal = Xv.iloc[cut:], yv.iloc[cut:]
        if len(Xcal) < 20:
            return None
        q_lo, q_hi = alpha / 2.0, 1.0 - alpha / 2.0
        gl = GradientBoostingRegressor(loss='quantile', alpha=q_lo, n_estimators=60,
                                       max_depth=3, learning_rate=0.05, random_state=42)
        gh = GradientBoostingRegressor(loss='quantile', alpha=q_hi, n_estimators=60,
                                       max_depth=3, learning_rate=0.05, random_state=42)
        gl.fit(Xtr, ytr)
        gh.fit(Xtr, ytr)
        cal_lo = gl.predict(Xcal)
        cal_hi = gh.predict(Xcal)
        scores = np.maximum(cal_lo - ycal.values, ycal.values - cal_hi)
        k = int(np.ceil((len(scores) + 1) * (1 - alpha)))
        k = min(max(k, 1), len(scores))
        q_hat = float(np.sort(scores)[k - 1])
        # Self-healing: widen the corridor when this horizon's recent coverage dipped below target.
        _lbl = {1: '24H', 7: '7D', 30: '30D'}.get(h)
        widen = float(_CORRIDOR_WIDEN.get(_lbl, 1.0)) if _lbl else 1.0
        widen = max(1.0, min(widen, 1.6))
        q_hat_eff = q_hat * widen
        # empirical coverage on the calibration set after conformal correction
        covered = ((ycal.values >= cal_lo - q_hat_eff) & (ycal.values <= cal_hi + q_hat_eff)).mean()
        raw_lo = float(gl.predict(lx)[0])
        raw_hi = float(gh.predict(lx)[0])
        lo_ret, hi_ret = raw_lo - q_hat_eff, raw_hi + q_hat_eff
        return {
            'lower': round(price * (1 + lo_ret), 0),
            'upper': round(price * (1 + hi_ret), 0),
            'width_pct': round((hi_ret - lo_ret) * 100, 2),
            'coverage': round(float(covered) * 100, 1),
            'target_coverage': int(round((1 - alpha) * 100)),
            'q_hat_pct': round(q_hat * 100, 2),
            'widen': round(widen, 3),
            'n_calib': int(len(Xcal)),
        }
    except Exception:  # noqa
        traceback.print_exc()
        return None


def _horizon_features(h):
    """Sub-Model Depth: horizon-appropriate feature subset.
    Short horizons lean on fast microstructure (momentum/volatility/volume); long horizons
    lean on slower trend/structure. All drawn from the existing engineered feature set."""
    short = ['RSI', 'StochRSI', 'MACD_Hist_Norm', 'ATR_Pct', 'BB_Width_Pct', 'Volume_Z', 'Volume_Ratio']
    longf = ['EMA_Ratio', 'MACD_Hist_Norm', 'RSI', 'ATR_Pct']
    if h <= 7:
        cols = short
    elif h <= 90:
        cols = FEATURE_COLS  # balanced across all categories
    else:
        cols = longf
    return [c for c in cols if c in FEATURE_COLS] or list(FEATURE_COLS)


def _horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts, light=False,
                      highs=None, lows=None):
    """Train a horizon-specific model (per-horizon feature set) with out-of-fold ISOTONIC
    calibration so the stated probability is honest, then project bull/base/bear ranges.
    Uses ATR-scaled Triple-Barrier labels (path-dependent, tradable) when highs/lows are
    supplied, else falls back to the raw up/down label.
    light=True skips SHAP contributions (used for long-horizon outlooks to save compute)."""
    n = len(Xfull)
    cols = _horizon_features(h)
    Xf = Xfull[cols]
    lx = live_X[cols]
    tb_used = False
    try:
        if highs is not None and lows is not None and 'ATR_Pct' in Xfull.columns:
            y_h = _triple_barrier_target(close, highs, lows, h, Xfull['ATR_Pct'],
                                         pt_mult=1.5, sl_mult=1.0)
            tb_used = True
        else:
            y_h = (close.shift(-h) > close).astype(float)
    except Exception:  # noqa
        y_h = (close.shift(-h) > close).astype(float)
        tb_used = False
    Xv = Xf.iloc[:n - h]
    yv = y_h.iloc[:n - h]
    # drop warm-up / unlabeled rows (Triple-Barrier leaves NaN where ATR is undefined)
    _mask = yv.notna()
    Xv = Xv[_mask]
    yv = yv[_mask].astype(int)
    # backtest accuracy via time-series split
    accs = []
    try:
        tscv = TimeSeriesSplit(n_splits=3)
        for tr, te in tscv.split(Xv):
            m = RandomForestClassifier(n_estimators=120, max_depth=5, random_state=42, n_jobs=-1)
            m.fit(Xv.iloc[tr], yv.iloc[tr])
            accs.append(accuracy_score(yv.iloc[te], m.predict(Xv.iloc[te])))
    except Exception:  # noqa
        accs = [0.5]
    acc = float(np.mean(accs)) if accs else 0.5
    # final model -> live probability (raw RF; also used for SHAP)
    fm = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
    fm.fit(Xv, yv)
    cl = list(fm.classes_)
    pr = fm.predict_proba(lx)[0]
    p_up = float(pr[cl.index(1)]) if 1 in cl else 0.0

    # --- Out-of-fold ISOTONIC calibration of the directional probability ---
    # Guarantees the stated odds match realised frequencies; graceful fallback to raw
    # when a horizon has too few samples / a rare class to calibrate reliably.
    calibrated = False
    try:
        vc = yv.value_counts()
        if len(Xv) >= 150 and yv.nunique() == 2 and int(vc.min()) >= 30:
            base = RandomForestClassifier(n_estimators=120, max_depth=5, random_state=42, n_jobs=-1)
            cal = CalibratedClassifierCV(base, method='isotonic', cv=3)
            cal.fit(Xv, yv)
            clc = list(cal.classes_)
            pc = cal.predict_proba(lx)[0]
            if 1 in clc:
                p_up = float(pc[clc.index(1)])
                calibrated = True
    except Exception:  # noqa
        calibrated = False

    # --- Conformalized Quantile Regression corridor (distribution-free 90% coverage) ---
    conformal = None
    if not light:
        conformal = _conformal_corridor(Xf, close, lx, h, price, alpha=0.10)

    # SHAP factor contributions for the live prediction (probability space, class = up)
    contributions = []
    if _HAS_SHAP and not light:
        try:
            expl = shap.TreeExplainer(fm)
            sv = expl.shap_values(lx)
            arr = None
            if isinstance(sv, list):
                arr = np.array(sv[1][0]) if len(sv) > 1 else np.array(sv[0][0])
            else:
                a = np.array(sv)
                arr = a[0, :, 1] if (a.ndim == 3 and a.shape[2] > 1) else (a[0, :, 0] if a.ndim == 3 else a[0])
            for f, val in zip(cols, arr):
                contributions.append({'feature': f, 'label': FEATURE_META[f]['label'],
                                      'category': FEATURE_META[f]['category'],
                                      'contribution': round(float(val) * 100, 2)})
            contributions.sort(key=lambda z: -abs(z['contribution']))
        except Exception:  # noqa
            contributions = []
    higher = round(p_up * 100, 1)
    lower = round(100 - higher, 1)
    if light:
        # Long-horizon directional models are close to a coin-flip; shrink the displayed
        # probability toward 50% by the realised backtest edge so it is not over-confident.
        edge = max(0.0, (acc - 0.5)) * 2          # 0..1
        weight = min(1.0, 0.25 + edge)            # never fully trusted; floor 0.25
        p_disp = 0.5 + (p_up - 0.5) * weight
        higher = round(p_disp * 100, 1)
        lower = round(100 - higher, 1)
    # scenario ranges from drift + volatility scaled by sqrt(horizon)
    drift = mu * h
    vol = sigma * math.sqrt(h)
    base = price * math.exp(drift)
    bull = price * math.exp(drift + vol)
    bear = price * math.exp(drift - vol)
    exp_low = price * math.exp(drift - 0.5 * vol)
    exp_high = price * math.exp(drift + 0.5 * vol)
    # confidence from probability margin + realised backtest edge
    margin = abs(p_up - 0.5) * 2
    conf_val = margin * 0.6 + max(0.0, (acc - 0.5)) * 2 * 0.4
    conf_label = 'High' if conf_val > 0.45 else ('Moderate' if conf_val > 0.2 else 'Low')
    bullish_lean = higher >= lower
    invalidation = bear if bullish_lean else bull
    label = {1: '24H', 7: '7D', 30: '30D', 90: '3M', 180: '6M', 365: '1Y'}.get(h, f'{h}D')

    # --- Probabilistic price cone (log-normal quantiles) + Expected-Value framing ---
    # price_T = price * exp(drift + vol * Z), Z ~ N(0,1)  -> proper percentile bands
    _NORM_Q = {'p10': -1.2816, 'p25': -0.6745, 'p50': 0.0, 'p75': 0.6745, 'p90': 1.2816}
    quantiles = {k: round(price * math.exp(drift + vol * z), 0) for k, z in _NORM_Q.items()}
    p_up_disp = higher / 100.0
    avg_up = max(0.0, quantiles['p75'] / price - 1.0)     # representative upside (upper-half median)
    avg_dn = max(0.0, 1.0 - quantiles['p25'] / price)     # representative downside (lower-half median)
    ev = p_up_disp * avg_up - (1.0 - p_up_disp) * avg_dn  # expected return per unit
    payoff = round(avg_up / avg_dn, 2) if avg_dn > 1e-9 else None
    ev_block = {
        'win_prob': round(p_up_disp * 100, 1),
        'avg_up_pct': round(avg_up * 100, 2),
        'avg_down_pct': round(avg_dn * 100, 2),
        'payoff_ratio': payoff,
        'ev_pct': round(ev * 100, 2),
        'verdict': ('Positive edge' if ev > 0.0025 else 'Negative edge' if ev < -0.0025 else 'Flat / no edge'),
    }

    return {
        'horizon': label, 'days': h,
        'higher': higher, 'lower': lower,
        'expected_low': round(exp_low, 0), 'expected_high': round(exp_high, 0),
        'bull': round(bull, 0), 'base': round(base, 0), 'bear': round(bear, 0),
        'quantiles': quantiles, 'ev': ev_block,
        'calibrated': calibrated, 'features_used': cols, 'conformal': conformal,
        'label_method': 'triple_barrier' if tb_used else 'directional',
        'confidence': conf_label, 'confidence_pct': round(conf_val * 100, 0),
        'accuracy': round(acc * 100, 1),
        'invalidation': round(invalidation, 0),
        'invalidation_dir': 'below' if bullish_lean else 'above',
        'lean': 'UP' if bullish_lean else 'DOWN',
        'expiry': (as_of_ts + pd.Timedelta(days=h)).strftime('%Y-%m-%d'),
        'contributions': contributions,
    }


def compute_quant_analysis(df, feats, price, as_of_ts):
    close = df['close']
    logret = np.log(close / close.shift(1)).dropna()
    recent = logret.tail(90)
    mu = float(recent.mean()) if len(recent) else 0.0
    sigma = float(recent.std()) if len(recent) else 0.02

    # --- Category sub-scores (0-100, higher = more constructive) ---
    ema_ratio = float(feats['EMA_Ratio'])
    macd = float(feats['MACD_Hist_Norm'])
    rsi = float(feats['RSI']) * 100
    stoch = float(feats['StochRSI']) * 100
    vz = float(feats['Volume_Z'])
    vr = float(feats['Volume_Ratio'])
    atr_now = float(feats['ATR_Pct'])
    atr_series = df['ATR_Pct'].tail(365)
    atr_pct = float((atr_series < atr_now).mean()) if len(atr_series) else 0.5

    trend_score = _clamp(50 + 50 * math.tanh((ema_ratio / 0.02) * 0.6 + (macd / 0.004) * 0.4))
    momentum_score = _clamp(0.6 * rsi + 0.4 * stoch)
    volume_score = _clamp(50 + 50 * math.tanh(vz / 1.5))
    volatility_score = _clamp(100 * (1 - atr_pct))

    weights = {'Trend': 0.35, 'Momentum': 0.30, 'Volume': 0.20, 'Volatility': 0.15}
    scores = {'Trend': trend_score, 'Momentum': momentum_score,
              'Volume': volume_score, 'Volatility': volatility_score}
    quant = round(sum(scores[k] * weights[k] for k in weights))

    breakdown = [
        {'name': 'Trend', 'score': round(trend_score), 'weight': int(weights['Trend'] * 100),
         'signal': _sig_word(trend_score), 'active': True,
         'note': f"EMA 9/21 spread {round(ema_ratio*100,2)}%, MACD histogram {round(macd*100,3)}%"},
        {'name': 'Momentum', 'score': round(momentum_score), 'weight': int(weights['Momentum'] * 100),
         'signal': _sig_word(momentum_score), 'active': True,
         'note': f"RSI {round(rsi,1)}, Stochastic RSI {round(stoch,1)}"},
        {'name': 'Volume', 'score': round(volume_score), 'weight': int(weights['Volume'] * 100),
         'signal': _sig_word(volume_score), 'active': True,
         'note': f"Volume {round(vr,2)}x the 20-day norm (z {round(vz,2)})"},
        {'name': 'Volatility', 'score': round(volatility_score), 'weight': int(weights['Volatility'] * 100),
         'signal': 'Calm' if volatility_score >= 55 else ('Elevated' if volatility_score <= 40 else 'Normal'),
         'active': True,
         'note': f"ATR {round(atr_now*100,2)}% ({round(atr_pct*100)}th percentile of the last year)"},
        {'name': 'Derivatives', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires a derivatives data source (funding, OI, basis)'},
        {'name': 'Liquidity', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires order-book / exchange liquidity data'},
        {'name': 'On-chain', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires an on-chain provider (Glassnode / CryptoQuant)'},
        {'name': 'Sentiment', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires a social / news sentiment feed'},
        {'name': 'Macro', 'score': None, 'weight': 0, 'signal': 'Coming soon', 'active': False,
         'note': 'Requires macro data (DXY, rates, risk assets)'},
    ]

    # --- Market Regime Engine ---
    ema9 = _ema(close, 9); ema21 = _ema(close, 21); ema50 = _ema(close, 50)
    slope50 = float(ema50.iloc[-1] / ema50.iloc[-11] - 1) if len(ema50) > 11 else 0.0
    slope30 = float(close.iloc[-1] / close.iloc[-31] - 1) if len(close) > 31 else 0.0
    slope60 = float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else 0.0
    up_align = ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]
    down_align = ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]
    rng20 = float((close.tail(20).max() - close.tail(20).min()) / close.iloc[-1])
    vol_shock = atr_pct > 0.92

    if vol_shock:
        regime = 'Volatility Shock'
        regime_desc = 'Volatility is in the top decile of the past year — expect wide, erratic swings.'
        behavior = 'The engine widens risk bounds and lowers position conviction until volatility normalises.'
    elif up_align and slope30 > 0.08 and slope50 > 0.03:
        regime = 'Strong Bullish Trend'
        regime_desc = 'Price is above rising short/medium-term averages with strong upward slope.'
        behavior = 'The model favours trend-continuation and treats dips as higher-probability longs.'
    elif up_align or (slope30 > 0.02 and ema9.iloc[-1] > ema21.iloc[-1]):
        regime = 'Weak Bullish Trend'
        regime_desc = 'A mild uptrend with modest momentum and shallow slope.'
        behavior = 'The model leans bullish but keeps conviction moderate.'
    elif down_align and slope30 < -0.08 and slope50 < -0.03:
        regime = 'Strong Bearish Trend'
        regime_desc = 'Price is below falling averages with a steep downward slope.'
        behavior = 'The model avoids longs and treats rallies as lower-probability.'
    elif down_align or (slope30 < -0.02 and ema9.iloc[-1] < ema21.iloc[-1]):
        regime = 'Weak Bearish Trend'
        regime_desc = 'A mild downtrend with soft momentum.'
        behavior = 'The model leans bearish with moderate conviction.'
    elif rng20 < 0.08 and slope60 < -0.05:
        regime = 'Accumulation'
        regime_desc = 'Price is basing in a tight range after a decline, with stabilising volume.'
        behavior = 'The model watches for a breakout and treats the base as support.'
    elif rng20 < 0.08 and slope60 > 0.05:
        regime = 'Distribution'
        regime_desc = 'Price is stalling in a tight range after a rally — momentum is fading.'
        behavior = 'The model turns cautious and flags reversal risk.'
    else:
        regime = 'Consolidation'
        regime_desc = 'Range-bound price with flat moving averages and no dominant trend.'
        behavior = 'The model reduces directional conviction and waits for a break.'

    regime_obj = {'regime': regime, 'description': regime_desc, 'behavior': behavior,
                  'trend30d_pct': round(slope30 * 100, 1), 'vol_percentile': round(atr_pct * 100)}

    # --- Multi-horizon probability forecasts ---
    global _CORRIDOR_WIDEN
    try:
        _wd = misc_col.find_one({'_id': 'corridor_widen'}) or {}
        _CORRIDOR_WIDEN = _wd.get('map', {}) or {}
    except Exception:  # noqa
        _CORRIDOR_WIDEN = {}
    Xfull = df[FEATURE_COLS]
    live_X = Xfull.iloc[[-1]]
    forecasts = []
    for h in [1, 7, 30]:
        try:
            forecasts.append(_horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts,
                                                highs=df['high'], lows=df['low']))
        except Exception:  # noqa
            traceback.print_exc()
    # --- Long-horizon outlooks (1M/3M/6M/1Y) — lighter (no SHAP) for the Decision Engine ---
    long_outlook = []
    for h in [90, 180, 365]:
        try:
            long_outlook.append(_horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts,
                                                   light=True, highs=df['high'], lows=df['low']))
        except Exception:  # noqa
            traceback.print_exc()

    # --- Explainable factors: top bullish + top risk ---
    bulls, risks = [], []
    if trend_score >= 58:
        bulls.append((trend_score - 50, f"Price is trading above its short/medium-term trend (EMA 9 > 21) with a {'positive' if macd>=0 else 'improving'} MACD histogram."))
    elif trend_score <= 42:
        risks.append((50 - trend_score, "Trend is bearish — price sits below key moving averages with a negative MACD histogram."))
    if 55 <= rsi < 72:
        bulls.append((rsi - 50, f"Momentum is constructive with RSI at {round(rsi,1)} and no overbought stress yet."))
    elif rsi >= 72:
        risks.append((rsi - 50, f"RSI is overbought at {round(rsi,1)} — elevated risk of a near-term pullback."))
    elif rsi < 45:
        risks.append((50 - rsi, f"Momentum is weak with RSI at {round(rsi,1)}, below the neutral line."))
    if vz >= 0.5:
        bulls.append((vz * 20, f"Volume is running {round(vr,2)}x its 20-day average, confirming participation behind the move."))
    elif vz <= -0.5:
        risks.append((abs(vz) * 20, f"Volume is below normal ({round(vr,2)}x) — the current move lacks conviction."))
    if atr_pct >= 0.8:
        risks.append((atr_pct * 30, f"Volatility is elevated (ATR at the {round(atr_pct*100)}th percentile), widening the risk bounds."))
    elif atr_pct <= 0.3:
        bulls.append((30 * (0.3 - atr_pct) + 5, "Volatility is subdued, a historically constructive backdrop for steady moves."))
    if stoch >= 80:
        risks.append((stoch - 60, "Stochastic RSI is stretched near the top of its band — short-term exhaustion risk."))
    elif stoch <= 20:
        bulls.append((30, "Stochastic RSI is oversold, a common spot for local reversals higher."))

    bulls = [b[1] for b in sorted(bulls, key=lambda z: -z[0])][:3]
    risks = [r[1] for r in sorted(risks, key=lambda z: -z[0])][:3]
    if not bulls:
        bulls = ["No strong bullish factors right now — signals are mixed to neutral."]
    if not risks:
        risks = ["No major risk factors flagged — conditions look relatively balanced."]

    return {
        'quant_score': int(quant),
        'quant_label': _quant_score_label(quant),
        'quant_breakdown': breakdown,
        'regime': regime_obj,
        'forecasts': forecasts,
        'long_outlook': long_outlook,
        'factors': {'bullish': bulls, 'risk': risks},
    }


# =====================================================================
# NEWS → FORECAST LINK + UNIFIED DECISION ENGINE + ASK-QUANT CONTEXT
# =====================================================================
def compute_news_signal(news_doc):
    """Turn the latest BTC news cards into an impact-weighted directional signal in [-1, 1]."""
    if not news_doc:
        return None
    cards = news_doc.get('cards', []) or []
    if not cards:
        return None
    num = den = 0.0
    drivers = []
    for c in cards:
        d = (c.get('ai') or {}).get('direction')
        imp = float(c.get('impact', 0) or 0)
        val = 1 if d == 'bullish' else (-1 if d == 'bearish' else 0)
        w = imp / 100.0
        num += val * w
        den += w
        if imp >= 55 and val != 0:
            drivers.append((imp, val, c.get('title', '')))
    signal = round((num / den), 3) if den else 0.0
    drivers.sort(key=lambda z: -z[0])
    top = drivers[0] if drivers else None
    bias = 'Bullish' if signal > 0.12 else ('Bearish' if signal < -0.12 else 'Neutral')
    return {
        'signal': signal, 'bias': bias,
        'n_high_impact': sum(1 for c in cards if float(c.get('impact', 0) or 0) >= 70),
        'n_stories': len(cards),
        'top_driver': (top[2] if top else None),
        'top_driver_dir': ('bullish' if top and top[1] > 0 else ('bearish' if top else None)),
        'model_bias': news_doc.get('briefing', {}).get('bias'),
    }


def apply_news_link(forecasts, news_sig):
    """Nudge the 24H/7D probabilities with the news signal and attach before/after data."""
    if not news_sig:
        return None
    K = {'24H': 7.0, '7D': 4.5}  # news matters more on shorter horizons
    applied = []
    for f in forecasts:
        k = K.get(f['horizon'])
        if not k:
            continue
        base = float(f['higher'])
        raw_adj = news_sig['signal'] * k
        adj = round(max(-8.0, min(8.0, raw_adj)), 1)
        newh = round(max(2.0, min(98.0, base + adj)), 1)
        f['news_link'] = {
            'applied': True, 'higher_base': round(base, 1), 'higher_adj': newh,
            'lower_base': round(100 - base, 1), 'lower_adj': round(100 - newh, 1),
            'delta': round(newh - base, 1), 'bias': news_sig['bias'],
            'signal': news_sig['signal'], 'top_driver': news_sig['top_driver'],
        }
        f['higher_adj'] = newh
        f['lower_adj'] = round(100 - newh, 1)
        applied.append({'horizon': f['horizon'], 'base': round(base, 1),
                        'adj': newh, 'delta': round(newh - base, 1)})
    return {
        'signal': news_sig['signal'], 'bias': news_sig['bias'],
        'n_high_impact': news_sig['n_high_impact'], 'n_stories': news_sig['n_stories'],
        'top_driver': news_sig['top_driver'], 'top_driver_dir': news_sig['top_driver_dir'],
        'model_bias': news_sig['model_bias'], 'applied': applied,
    }


OUTLOOK_LABELS = {'24H': 'Next 24 Hours', '7D': 'Next 7 Days', '30D': 'Next Month',
                  '3M': 'Next 3 Months', '6M': 'Next 6 Months', '1Y': 'Next Year'}


def compute_decision_engine(quant, all_outlook, policy, news_sig, chart, cycle, dominance,
                            weights=None, regime_info=None):
    """Reconcile technicals, macro/policy, news and chart into one Bitcoin Market State.

    Weights are now **dynamic** — supplied by the regime-switching engine
    (regime_engine.analyze). If no weights are provided we fall back to the legacy
    static allocation so the function keeps working standalone.
    """
    tech = int(quant['quant_score'])
    pol = int(policy['score']) if policy else 50
    news_score = int(round(50 + (news_sig['signal'] * 30))) if news_sig else 50
    news_score = max(0, min(100, news_score))
    chart_bias = chart['structure_bias'] if chart else 'Neutral'
    chart_score = 70 if chart_bias == 'Bullish' else (30 if chart_bias == 'Bearish' else 50)

    # Dynamic, regime-conditioned weights (fall back to the legacy static split).
    w = weights or {'technicals': 0.45, 'macro_policy': 0.20, 'chart_structure': 0.20, 'news_flow': 0.15}
    wt = float(w.get('technicals', 0.45))
    wm = float(w.get('macro_policy', 0.20))
    wc = float(w.get('chart_structure', 0.20))
    wn = float(w.get('news_flow', 0.15))
    _tot = (wt + wm + wc + wn) or 1.0
    wt, wm, wc, wn = wt / _tot, wm / _tot, wc / _tot, wn / _tot

    overall = int(round(tech * wt + pol * wm + news_score * wn + chart_score * wc))
    overall = max(0, min(100, overall))
    label = _quant_score_label(overall)

    comps = [
        {'name': 'Technicals', 'score': tech, 'weight': int(round(wt * 100))},
        {'name': 'Macro / Policy', 'score': pol, 'weight': int(round(wm * 100))},
        {'name': 'Chart Structure', 'score': chart_score, 'weight': int(round(wc * 100))},
        {'name': 'News Flow', 'score': news_score, 'weight': int(round(wn * 100))},
    ]
    bull = sum(1 for c in comps if c['score'] >= 55)
    bear = sum(1 for c in comps if c['score'] <= 45)
    if bull >= 3:
        alignment = 'Strong Agreement · Bullish'
    elif bear >= 3:
        alignment = 'Strong Agreement · Bearish'
    elif bull and bear:
        alignment = 'Conflicting Signals'
    else:
        alignment = 'Mixed / Neutral'

    # --- Risk level (distinct from directional score) ---
    vol_pct = float(quant['regime'].get('vol_percentile', 50) or 50)
    event_risk = 0
    now = datetime.datetime.utcnow().date()
    if policy:
        for e in policy.get('calendar', []):
            try:
                days = (datetime.datetime.strptime(e['date'], '%Y-%m-%d').date() - now).days
                if 0 <= days <= 3 and e.get('importance') == 'Very High':
                    event_risk = max(event_risk, 28)
                elif 0 <= days <= 7:
                    event_risk = max(event_risk, 16)
            except Exception:  # noqa
                pass
    news_risk = 0
    if news_sig and news_sig['bias'] == 'Bearish' and news_sig['n_high_impact'] >= 1:
        news_risk = 12
    risk_score = int(round(min(100, vol_pct * 0.6 + event_risk + news_risk)))
    risk_level = ('Extreme' if risk_score >= 80 else 'High' if risk_score >= 60
                  else 'Elevated' if risk_score >= 45 else 'Moderate' if risk_score >= 30 else 'Low')

    # --- Outlook table across every horizon (24H → 1Y) ---
    outlook = []
    for f in all_outlook:
        h = float(f.get('higher_adj', f['higher']))
        outlook.append({
            'horizon': f['horizon'], 'label': OUTLOOK_LABELS.get(f['horizon'], f['horizon']),
            'higher': round(h, 1), 'lower': round(100 - h, 1),
            'lean': 'UP' if h >= 50 else 'DOWN',
            'confidence': f.get('confidence', 'Low'), 'accuracy': f.get('accuracy'),
            'base': f.get('base'), 'bull': f.get('bull'), 'bear': f.get('bear'),
            'expiry': f.get('expiry'), 'news_adjusted': 'news_link' in f,
        })

    def _out(h):
        return next((o for o in outlook if o['horizon'] == h), None)
    o24, o7, o1m, o1y = _out('24H'), _out('7D'), _out('30D'), _out('1Y')

    def lean_txt(o):
        if not o:
            return 'unclear'
        return f"{'higher' if o['lean'] == 'UP' else 'lower'} ({max(o['higher'], o['lower'])}%)"

    regime = quant['regime']['regime']
    dom_txt = f"BTC dominance is {dominance['dominance']}% ({dominance['direction'].lower()}). " if dominance else ''
    cyc_txt = f"The halving cycle is ~{cycle['cycle_progress_pct']}% complete ({cycle['phase']}). " if cycle else ''
    news_txt = ''
    if news_sig:
        news_txt = f"News flow is {news_sig['bias'].lower()}"
        if news_sig.get('top_driver'):
            news_txt += f" (biggest driver: \"{news_sig['top_driver']}\")"
        news_txt += '. '
    summary = (
        f"Bitcoin's unified market state is {label} with an overall conviction score of {overall}/100. "
        f"The market is in a '{regime}' regime. {quant['regime']['description']} "
        f"Technicals ({tech}/100), macro & policy ({pol}/100), chart structure ({chart_bias.lower()}) and news flow "
        f"({news_score}/100) are showing {alignment.lower()}. {news_txt}{dom_txt}{cyc_txt}"
        f"Near term, the engine leans {lean_txt(o24)} over 24h and {lean_txt(o7)} over 7 days; "
        f"the longer-term view leans {lean_txt(o1m)} over the next month and {lean_txt(o1y)} over the next year. "
        f"Overall risk is currently {risk_level}. Treat every figure as probabilities, not certainties — not financial advice."
    )

    return {
        'overall_score': overall, 'label': label, 'regime': regime,
        'regime_description': quant['regime']['description'],
        'alignment': alignment, 'components': comps,
        'weights_mode': 'dynamic' if weights else 'static',
        'regime_engine': regime_info,
        'risk_level': risk_level, 'risk_score': risk_score,
        'risk_drivers': {'volatility_percentile': round(vol_pct), 'event_risk': event_risk,
                         'news_risk': news_risk},
        'outlook': outlook, 'summary': summary,
        'news_signal': (news_sig['signal'] if news_sig else None),
        'news_bias': (news_sig['bias'] if news_sig else None),
    }


# ---------------------------- Risk Engine ----------------------------
def _scoreside(score):
    return 'bullish' if score >= 55 else ('bearish' if score <= 45 else 'neutral')


def compute_scenarios(chart, decision, last_close, feats, regime_analysis):
    """Albert's actionable If-Then playbook: concrete bull/bear triggers with levels,
    targets and data-derived probabilities, plus a regime-aware resolution of any
    contradiction between the signal groups.
    """
    if not chart or not decision or not last_close:
        return None
    try:
        price = float(last_close)
        try:
            atr = float(feats['ATR_Pct'])
        except Exception:  # noqa
            atr = 0.03
        if not atr or atr != atr:  # guard NaN/0
            atr = 0.03
        sr = chart.get('sr_levels', []) or []
        res = sorted([l for l in sr if l.get('type') == 'resistance' and l['price'] > price],
                     key=lambda z: z['price'])
        sup = sorted([l for l in sr if l.get('type') == 'support' and l['price'] < price],
                     key=lambda z: -z['price'])
        pred = chart.get('predictive', {}) or {}
        bo_up = float(pred.get('breakout_up', 50) or 50)
        bo_dn = float(pred.get('breakdown', 50) or 50)
        regime = (regime_analysis or {}).get('current_regime')
        regime_label = (regime_analysis or {}).get('regime_label', regime or 'current')
        # Regime tilts the base rates: momentum favours continuation, distribution/squeeze fade it.
        bull_tilt = {'bull_momentum': 1.15, 'consolidation': 1.0,
                     'bear_distribution': 0.82, 'high_vol_squeeze': 0.9}.get(regime, 1.0)

        # ---- Bull scenario ----
        trig_res = round(res[0]['price'] if res else price * (1 + max(0.01, atr)), 0)
        tgt_bull = round(res[1]['price'] if len(res) > 1 else trig_res * (1 + max(0.015, atr * 1.5)), 0)
        p_bull = int(round(min(85, max(15, bo_up * bull_tilt))))
        # ---- Bear scenario ----
        trig_sup = round(sup[0]['price'] if sup else price * (1 - max(0.01, atr)), 0)
        tgt_bear = round(sup[1]['price'] if len(sup) > 1 else trig_sup * (1 - max(0.015, atr * 1.5)), 0)
        p_bear = int(round(min(85, max(15, bo_dn * (2 - bull_tilt)))))

        scenarios = [
            {
                'type': 'bull', 'label': 'Primary Bull Scenario',
                'trigger': f"Break & 4h/daily close above ${trig_res:,.0f} on >1.2x average volume",
                'trigger_level': trig_res, 'target_level': tgt_bull,
                'target': f"${tgt_bull:,.0f}", 'probability': p_bull,
                'move_pct': round((tgt_bull - price) / price * 100, 1),
                'rationale': (f"{round(bo_up)}% of comparable 20-day-high breakouts closed higher within 5 days; "
                              f"the {regime_label} regime {'supports' if bull_tilt >= 1 else 'tempers'} continuation."),
            },
            {
                'type': 'bear', 'label': 'Bearish Invalidation',
                'trigger': f"Loss of ${trig_sup:,.0f} support on rising volume",
                'trigger_level': trig_sup, 'target_level': tgt_bear,
                'target': f"${tgt_bear:,.0f} (liquidity sweep)", 'probability': p_bear,
                'move_pct': round((tgt_bear - price) / price * 100, 1),
                'rationale': (f"Failing to hold structure has historically resolved lower ~{round(bo_dn)}% of the time; "
                              f"a high-volume sweep toward the next support becomes the base case."),
            },
        ]

        # ---- Contradiction resolution (uses the LIVE regime weights) ----
        comps = decision.get('components', []) or []
        bulls = [c for c in comps if c['score'] >= 55]
        bears = [c for c in comps if c['score'] <= 45]

        def force(c):
            return c.get('weight', 0) * abs(c['score'] - 50)

        if bulls and bears:
            bull_force = sum(force(c) for c in bulls)
            bear_force = sum(force(c) for c in bears)
            winner = 'bullish' if bull_force >= bear_force else 'bearish'
            winners = bulls if winner == 'bullish' else bears
            losers = bears if winner == 'bullish' else bulls
            top_w = max(winners, key=force)
            top_l = max(losers, key=force)
            contradiction = {
                'present': True, 'winner': winner,
                'bull_force': round(bull_force), 'bear_force': round(bear_force),
                'summary': (f"{top_l['name']} is {_scoreside(top_l['score'])} ({top_l['score']}/100) while "
                            f"{top_w['name']} is {_scoreside(top_w['score'])} ({top_w['score']}/100). Under the "
                            f"current {regime_label} regime, {top_w['name']} carries the greater weight "
                            f"({top_w['weight']}%), so the engine leans {winner} until that flips."),
            }
        else:
            contradiction = {'present': False, 'winner': None,
                             'summary': 'Signal groups are broadly aligned — no material contradiction to resolve.'}

        return {'scenarios': scenarios, 'contradiction': contradiction,
                'price': round(price, 0), 'regime': regime, 'regime_label': regime_label}
    except Exception:  # noqa
        traceback.print_exc()
        return None



def _risk_state(score):
    return ('Extreme' if score >= 80 else 'High' if score >= 60
            else 'Elevated' if score >= 45 else 'Normal' if score >= 25 else 'Low')


def compute_risk_engine(quant, chart, decision, data_health, event_calendar, last_close, feats):
    """Dedicated risk view — direction-agnostic. Real where we have data; illustrative
    DEMO values (clearly flagged) for feeds that need paid keys (IV, leverage, order book)."""
    import math as _m
    atr_now = float(feats.get('ATR_Pct', 0.03) or 0.03)          # daily realised range fraction
    vol_pct = float(quant['regime'].get('vol_percentile', 50) or 50)
    level = (decision or {}).get('risk_level', _risk_state(round(vol_pct)))
    score = int((decision or {}).get('risk_score', round(vol_pct)))

    # Expected move (real, from ATR scaled by sqrt(time))
    def _band(days):
        mv = atr_now * _m.sqrt(days)
        return {'pct': round(mv * 100, 1),
                'low': round(last_close * (1 - mv), 0), 'high': round(last_close * (1 + mv), 0)}
    expected_move = {'24H': _band(1), '7D': _band(7), '30D': _band(30)}

    # Support / resistance zones (real, from chart intelligence)
    sr = (chart or {}).get('sr_levels', []) or []
    sup = sorted([l for l in sr if l['type'] == 'support' and l['price'] < last_close],
                 key=lambda z: last_close - z['price'])
    res = sorted([l for l in sr if l['type'] == 'resistance' and l['price'] > last_close],
                 key=lambda z: z['price'] - last_close)
    downside_zone = ({'price': sup[0]['price'], 'distance_pct': round((last_close - sup[0]['price']) / last_close * 100, 1),
                      'label': 'Primary support'} if sup else None)
    upside_zone = ({'price': res[0]['price'], 'distance_pct': round((res[0]['price'] - last_close) / last_close * 100, 1),
                    'label': 'Primary resistance'} if res else None)

    # Macro-event risk (real, from event calendar)
    nhi = (event_calendar or {}).get('next_high_impact')
    macro_event_risk = 'Low'
    macro_note = 'No high-impact events in the near window.'
    if nhi and nhi.get('days_until') is not None:
        du = nhi['days_until']
        macro_event_risk = 'High' if du <= 2 else 'Elevated' if du <= 7 else 'Normal'
        macro_note = f"{nhi.get('title')} in {du}d ({nhi.get('importance')} importance)."

    # Data uncertainty (real, from data health)
    dh_level = (data_health or {}).get('level', 'High')
    dh_score = (data_health or {}).get('score', 95)
    data_uncertainty = 'Low' if dh_score >= 90 else 'Normal' if dh_score >= 75 else 'Elevated' if dh_score >= 55 else 'High'

    # Realised vol (real percentile) -> annualised estimate
    realised_vol_annual = round(atr_now * _m.sqrt(365) * 100, 0)

    # ----- DEMO metrics (need paid feeds; clearly flagged) -----
    seed = int(last_close) % 100
    demo = {
        'implied_vol': {'value': round(realised_vol_annual + 8 + seed % 12, 0), 'unit': '% annualised',
                        'state': 'Elevated', 'demo': True, 'source': 'Deribit/CME (needs key)'},
        'leverage_risk': {'state': ['Normal', 'Elevated', 'High'][seed % 3], 'funding_bps': round((seed % 20) - 5, 1),
                          'demo': True, 'source': 'CoinGlass (needs key)'},
        'liquidation_risk': {'state': ['Normal', 'Elevated', 'High'][(seed + 1) % 3],
                             'nearest_cluster_pct': round(2 + seed % 4, 1), 'demo': True, 'source': 'CoinGlass (needs key)'},
        'orderbook_liquidity': {'state': ['Deep', 'Normal', 'Thin'][seed % 3], 'depth_2pct_musd': round(120 + seed, 0),
                                'demo': True, 'source': 'Exchange L2 (needs key)'},
    }

    drivers = [
        {'name': 'Realised volatility', 'state': _risk_state(round(vol_pct)), 'value': f'{round(vol_pct)}th pct', 'demo': False},
        {'name': 'Macro-event risk', 'state': macro_event_risk, 'value': macro_note, 'demo': False},
        {'name': 'Data uncertainty', 'state': data_uncertainty, 'value': f'{dh_level} ({dh_score}/100)', 'demo': False},
        {'name': 'Implied volatility', 'state': demo['implied_vol']['state'], 'value': f"{demo['implied_vol']['value']}%", 'demo': True},
        {'name': 'Leverage / funding', 'state': demo['leverage_risk']['state'], 'value': f"{demo['leverage_risk']['funding_bps']} bps", 'demo': True},
        {'name': 'Liquidation risk', 'state': demo['liquidation_risk']['state'], 'value': f"cluster ~{demo['liquidation_risk']['nearest_cluster_pct']}% away", 'demo': True},
        {'name': 'Order-book liquidity', 'state': demo['orderbook_liquidity']['state'], 'value': f"${demo['orderbook_liquidity']['depth_2pct_musd']}M @2%", 'demo': True},
    ]

    return {
        'level': level, 'score': score, 'state_scale': ['Low', 'Normal', 'Elevated', 'High', 'Extreme'],
        'expected_move': expected_move,
        'realised_vol_annual': realised_vol_annual,
        'vol_percentile': round(vol_pct),
        'downside_zone': downside_zone, 'upside_zone': upside_zone,
        'macro_event_risk': macro_event_risk, 'macro_note': macro_note,
        'data_uncertainty': data_uncertainty,
        'drivers': drivers, 'demo': demo,
        'note': 'Risk is measured separately from direction — a constructive outlook can still carry high risk.',
    }


# ---------------------------- Smart Money & Institutional (DEMO) ----------------------------
def compute_smart_money_demo(last_close, regime):
    """DEMO on-chain / smart-money view. Illustrative only — real values need a Glassnode key."""
    seed = int(last_close) % 100
    trend = 'accumulation' if seed % 2 == 0 else 'distribution'
    return {
        'demo': True, 'source': 'Glassnode / on-chain (needs key)',
        'headline': f'Whales in mild {trend}',
        'metrics': [
            {'name': 'Exchange reserves (30d)', 'value': f'{"-" if trend=="accumulation" else "+"}{round(1.2 + seed%3,1)}%', 'signal': 'Bullish' if trend == 'accumulation' else 'Bearish'},
            {'name': 'Whale wallets ≥1k BTC', 'value': f'{"+" if trend=="accumulation" else "-"}{round(0.3 + seed%2*0.4,1)}%', 'signal': 'Bullish' if trend == 'accumulation' else 'Bearish'},
            {'name': 'Long-term holder supply', 'value': f'+{round(0.5 + seed%3*0.3,1)}%', 'signal': 'Bullish'},
            {'name': 'Realised profit/loss ratio', 'value': f'{round(0.8 + (seed%40)/100,2)}', 'signal': 'Neutral'},
            {'name': 'Dormant supply movement', 'value': 'Quiet', 'signal': 'Neutral'},
        ],
    }


def compute_institutional_demo(last_close):
    """DEMO institutional / ETF flow view. Illustrative only — needs a paid ETF/CME feed."""
    seed = int(last_close) % 100
    net = round((seed % 60) - 20, 0)
    return {
        'demo': True, 'source': 'ETF issuers / CME (needs key)',
        'headline': f'Spot ETF net flow ~${net}M (illustrative)',
        'metrics': [
            {'name': 'Spot ETF net flow (1d)', 'value': f'${net}M', 'signal': 'Bullish' if net > 0 else 'Bearish'},
            {'name': 'Spot ETF net flow (7d)', 'value': f'${round(net*5,0)}M', 'signal': 'Bullish' if net > 0 else 'Bearish'},
            {'name': 'CME open interest', 'value': f'{round(28 + seed%8,1)}k BTC', 'signal': 'Neutral'},
            {'name': 'CME basis (annualised)', 'value': f'{round(6 + seed%6,1)}%', 'signal': 'Bullish'},
            {'name': 'Grayscale/HODL trend', 'value': 'Stabilising', 'signal': 'Neutral'},
        ],
    }


# =====================================================================
# GLASSNODE ON-CHAIN (REAL) — powers the Smart Money panel for BTC
# Advanced Light tier: 14d daily history, tight call budget -> fetch a small
# entitled metric set in the background, cache in Mongo, reuse for ~6h.
# =====================================================================
GLASSNODE_BASE = 'https://api.glassnode.com/v1/metrics'
GLASSNODE_TTL_SEC = 6 * 3600
# Only metrics entitled on the Light tier (verified). ETF/entity/net-position are Professional-only.
GN_SMART_METRICS = {
    'mvrv': 'market/mvrv',
    'sopr': 'indicators/sopr',
    'exch_balance': 'distribution/balance_exchanges',
    'active': 'addresses/active_count',
    'accum': 'indicators/accumulation_trend_score',
    'lth': 'supply/lth_sum',
}
_gn_state = {'running': False}


def _gn_point_val(pt):
    if not isinstance(pt, dict):
        return None
    v = pt.get('v')
    if v is None and isinstance(pt.get('o'), dict):
        v = pt['o'].get('score', pt['o'].get('price'))
    return v


def _gn_val(series):
    if not series:
        return None
    return _gn_point_val(series[-1])


def _gn_change_pct(series):
    if not series or len(series) < 2:
        return None
    a = _gn_point_val(series[0])
    b = _gn_point_val(series[-1])
    if a in (None, 0) or b is None:
        return None
    try:
        return round((float(b) - float(a)) / abs(float(a)) * 100, 2)
    except Exception:  # noqa
        return None


def build_smart_money_from_glassnode(series):
    mvrv = _gn_val(series.get('mvrv'))
    sopr = _gn_val(series.get('sopr'))
    accum = _gn_val(series.get('accum'))
    exch_chg = _gn_change_pct(series.get('exch_balance'))
    active_chg = _gn_change_pct(series.get('active'))
    lth_chg = _gn_change_pct(series.get('lth'))
    metrics, tally = [], {'b': 0, 'r': 0}

    def add(name, value, s):
        if s == 'Bullish':
            tally['b'] += 1
        elif s == 'Bearish':
            tally['r'] += 1
        metrics.append({'name': name, 'value': value, 'signal': s})

    if mvrv is not None:
        s = 'Bullish' if mvrv < 1 else 'Bearish' if mvrv > 3.5 else 'Neutral'
        add('MVRV ratio', f'{float(mvrv):.2f}', s)
    if exch_chg is not None:
        s = 'Bullish' if exch_chg < -0.3 else 'Bearish' if exch_chg > 0.3 else 'Neutral'
        add('Exchange balance (14d)', f'{"+" if exch_chg >= 0 else ""}{exch_chg}%', s)
    if accum is not None:
        s = 'Bullish' if accum >= 0.6 else 'Bearish' if accum <= 0.4 else 'Neutral'
        add('Accumulation trend score', f'{float(accum):.2f}', s)
    if lth_chg is not None:
        s = 'Bullish' if lth_chg > 0.1 else 'Bearish' if lth_chg < -0.1 else 'Neutral'
        add('Long-term holder supply (14d)', f'{"+" if lth_chg >= 0 else ""}{lth_chg}%', s)
    if sopr is not None:
        s = 'Bullish' if sopr < 0.98 else 'Bearish' if sopr > 1.03 else 'Neutral'
        add('SOPR', f'{float(sopr):.3f}', s)
    if active_chg is not None:
        s = 'Bullish' if active_chg > 2 else 'Bearish' if active_chg < -5 else 'Neutral'
        add('Active addresses (14d)', f'{"+" if active_chg >= 0 else ""}{active_chg}%', s)

    if not metrics:
        return None
    net = tally['b'] - tally['r']
    headline = ('On-chain smart money accumulating' if net >= 2
                else 'On-chain smart money distributing' if net <= -2
                else 'On-chain smart money mixed / neutral')
    return {'demo': False, 'source': 'Glassnode (on-chain · BTC)', 'headline': headline,
            'metrics': metrics, 'as_of': datetime.datetime.utcnow().isoformat()}


def _gn_get(path):
    try:
        r = requests.get(f'{GLASSNODE_BASE}/{path}', params={'a': 'BTC', 'i': '24h', 'f': 'json'},
                         headers={'X-Api-Key': GLASSNODE_API_KEY, 'Accept': 'application/json'}, timeout=20)
        if r.status_code == 200:
            return r.json()
        # 401 (bad key) / 403 (tier) / 429 (rate) -> skip; keep last-good value
    except Exception:  # noqa
        traceback.print_exc()
    return None


def _refresh_glassnode_bg():
    if not GLASSNODE_API_KEY or _gn_state.get('running'):
        return
    _gn_state['running'] = True
    try:
        cache = glassnode_col.find_one({'_id': 'smart_money_btc'}) or {}
        series = dict(cache.get('series') or {})
        fetched_any = False
        for k, path in GN_SMART_METRICS.items():
            js = _gn_get(path)
            if js:
                series[k] = js
                fetched_any = True
            time.sleep(9)  # respect the Light-tier burst limit
        if series:
            data = build_smart_money_from_glassnode(series)
            if data:
                glassnode_col.update_one(
                    {'_id': 'smart_money_btc'},
                    {'$set': {'_id': 'smart_money_btc',
                              'fetched_ts': time.time() if fetched_any else cache.get('fetched_ts', 0),
                              'fetched_at': datetime.datetime.utcnow().isoformat(),
                              'series': series, 'data': data}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _gn_state['running'] = False


def get_smart_money_panel():
    """Return the cached real Glassnode Smart Money panel, kicking off a background
    refresh when stale. Returns None if no key or no data yet (caller falls back to DEMO)."""
    if not GLASSNODE_API_KEY:
        return None
    cache = glassnode_col.find_one({'_id': 'smart_money_btc'}) or {}
    now = time.time()
    if (not cache.get('data')) or (now - cache.get('fetched_ts', 0) >= GLASSNODE_TTL_SEC):
        threading.Thread(target=_refresh_glassnode_bg, daemon=True).start()
    return cache.get('data')


# =====================================================================
# FREE ON-CHAIN + DERIVATIVES ENGINE (Ask Albert)
# Real Smart Money (on-chain) + Institutional/Derivatives panels from free,
# server-reachable sources: BGeometrics (bitcoin-data.com), blockchain.com,
# alternative.me (Fear & Greed), OKX public API, + Glassnode Light (bonus).
# Cached in Mongo, background refresh ~2h. ETF net flow shown as Inactive
# (no free, server-reachable feed).
# =====================================================================
# onchain_col now imported from config
ONCHAIN_TTL_SEC = 2 * 3600
_onchain_state = {}


def _engine_get(url, params=None, headers=None, timeout=12):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa
        traceback.print_exc()
    return None


def _bdata_last(metric):
    return _engine_get(f'https://bitcoin-data.com/v1/{metric}/last')


def _bc_chart(name, timespan='30days'):
    js = _engine_get('https://api.blockchain.info/charts/' + name,
                     params={'timespan': timespan, 'format': 'json'})
    if js and isinstance(js.get('values'), list):
        return js['values']
    return None


def _fng():
    js = _engine_get('https://api.alternative.me/fng/', params={'limit': 2})
    try:
        return js['data']
    except Exception:  # noqa
        return None


def _okx(path, params=None):
    js = _engine_get('https://www.okx.com' + path, params=params)
    if js and str(js.get('code')) == '0':
        return js.get('data')
    return None


def _spark(vals, n=24, nd=4):
    """Downsample a numeric series to <= n points for a tiny sparkline."""
    vals = [v for v in (vals or []) if v is not None]
    if len(vals) < 2:
        return None
    if len(vals) > n:
        step = len(vals) / n
        out = [vals[int(i * step)] for i in range(n)]
        out[-1] = vals[-1]
        vals = out
    try:
        return [round(float(v), nd) for v in vals]
    except Exception:  # noqa
        return None


def _bdata_series(metric, key, days=30):
    """Ascending-by-date value list from bitcoin-data.com (BGeometrics) for a date window."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    js = _engine_get(f'https://bitcoin-data.com/v1/{metric}',
                     params={'startday': start.isoformat(), 'endday': end.isoformat()})
    if isinstance(js, list):
        out = []
        for x in js:
            v = x.get(key)
            if v is not None:
                try:
                    out.append(float(v))
                except Exception:  # noqa
                    pass
        return out or None
    return None


def _fng_series(days=30):
    """Fear & Greed values oldest->newest."""
    js = _engine_get('https://api.alternative.me/fng/', params={'limit': days})
    try:
        vals = [int(x['value']) for x in js['data']]
        return list(reversed(vals))  # API returns newest-first
    except Exception:  # noqa
        return None


def build_smart_money_engine(gn_series=None):
    metrics, tally = [], {'b': 0, 'r': 0}

    def add(name, value, s, inactive=False, spark=None):
        if not inactive:
            if s == 'Bullish':
                tally['b'] += 1
            elif s == 'Bearish':
                tally['r'] += 1
        m = {'name': name, 'value': value, 'signal': s}
        if inactive:
            m['inactive'] = True
        if spark:
            m['spark'] = spark
        metrics.append(m)

    mzs = _bdata_series('mvrv-zscore', 'mvrvZscore', 30)
    z = mzs[-1] if mzs else None
    if z is None:
        mz = _bdata_last('mvrv-zscore')
        z = float(mz['mvrvZscore']) if (mz and mz.get('mvrvZscore') is not None) else None
    if z is not None:
        s = 'Bullish' if z < 1 else 'Bearish' if z > 5 else 'Neutral'
        add('MVRV Z-score', f'{z:.2f}', s, spark=_spark(mzs))
    sps = _bdata_series('sopr', 'sopr', 30)
    v = sps[-1] if sps else None
    if v is None:
        sp = _bdata_last('sopr')
        v = float(sp['sopr']) if (sp and sp.get('sopr') is not None) else None
    if v is not None:
        s = 'Bullish' if v < 0.98 else 'Bearish' if v > 1.03 else 'Neutral'
        add('SOPR', f'{v:.3f}', s, spark=_spark(sps))
    aa = _bc_chart('n-unique-addresses', '30days')
    if aa and len(aa) >= 2:
        try:
            a0, a1 = float(aa[0]['y']), float(aa[-1]['y'])
            chg = round((a1 - a0) / a0 * 100, 1) if a0 else None
            if chg is not None:
                s = 'Bullish' if chg > 3 else 'Bearish' if chg < -8 else 'Neutral'
                add('Active addresses (30d)', f'{"+" if chg >= 0 else ""}{chg}%', s,
                    spark=_spark([float(p['y']) for p in aa], nd=0))
        except Exception:  # noqa
            pass
    fgs = _fng_series(30)
    fg = _fng()
    if fg:
        try:
            val = int(fg[0]['value'])
            cls = fg[0].get('value_classification', '')
            # Contrarian read: extreme fear = accumulation opportunity, extreme greed = caution.
            s = 'Bullish' if val <= 25 else 'Bearish' if val >= 75 else 'Neutral'
            add(f'Fear & Greed ({cls})', str(val), s, spark=_spark(fgs, nd=0))
        except Exception:  # noqa
            pass
    if gn_series:
        exch_chg = _gn_change_pct(gn_series.get('exch_balance'))
        if exch_chg is not None:
            s = 'Bullish' if exch_chg < -0.3 else 'Bearish' if exch_chg > 0.3 else 'Neutral'
            add('Exchange balance (14d)', f'{"+" if exch_chg >= 0 else ""}{exch_chg}%', s,
                spark=_spark([_gn_point_val(p) for p in (gn_series.get('exch_balance') or [])], nd=0))
        accum = _gn_val(gn_series.get('accum'))
        if accum is not None:
            try:
                accum = float(accum)
                s = 'Bullish' if accum >= 0.6 else 'Bearish' if accum <= 0.4 else 'Neutral'
                add('Accumulation trend score', f'{accum:.2f}', s,
                    spark=_spark([_gn_point_val(p) for p in (gn_series.get('accum') or [])]))
            except Exception:  # noqa
                pass
        lth_chg = _gn_change_pct(gn_series.get('lth'))
        if lth_chg is not None:
            s = 'Bullish' if lth_chg > 0.1 else 'Bearish' if lth_chg < -0.1 else 'Neutral'
            add('Long-term holder supply (14d)', f'{"+" if lth_chg >= 0 else ""}{lth_chg}%', s,
                spark=_spark([_gn_point_val(p) for p in (gn_series.get('lth') or [])], nd=0))

    if not metrics:
        return None
    net = tally['b'] - tally['r']
    headline = ('On-chain smart money accumulating' if net >= 2
                else 'On-chain smart money distributing' if net <= -2
                else 'On-chain smart money mixed / neutral')
    src = 'BGeometrics · blockchain.com · alt.me' + (' · Glassnode' if gn_series else '')
    return {'demo': False, 'source': src, 'headline': headline, 'metrics': metrics,
            'as_of': datetime.datetime.utcnow().isoformat()}


def build_derivatives_engine(symbol='BTC'):
    sym = (symbol or 'BTC').upper()
    inst = f'{sym}-USDT-SWAP'
    metrics, tally = [], {'b': 0, 'r': 0}

    def add(name, value, s, inactive=False, count=True, spark=None):
        if not inactive and count:
            if s == 'Bullish':
                tally['b'] += 1
            elif s == 'Bearish':
                tally['r'] += 1
        m = {'name': name, 'value': value, 'signal': s}
        if inactive:
            m['inactive'] = True
        if spark:
            m['spark'] = spark
        metrics.append(m)

    oi = _okx('/api/v5/public/open-interest', {'instType': 'SWAP', 'instId': inst})
    oih = _okx('/api/v5/rubik/stat/contracts/open-interest-volume', {'ccy': sym, 'period': '1D'})
    oi_chg, oi_spark = None, None
    if oih and len(oih) >= 2:
        try:
            rows = list(reversed(oih))  # oldest -> newest
            oi_spark = _spark([float(r[1]) for r in rows], nd=0)
            latest = float(oih[0][1])
            prev = float(oih[min(7, len(oih) - 1)][1])
            oi_chg = round((latest - prev) / prev * 100, 1) if prev else None
        except Exception:  # noqa
            pass
    if oi:
        try:
            oi_usd = float(oi[0]['oiUsd'])
            val = f'${oi_usd / 1e9:.2f}B'
            if oi_chg is not None:
                val += f' ({"+" if oi_chg >= 0 else ""}{oi_chg}% 7d)'
            add('Futures open interest', val, 'Neutral', count=False, spark=oi_spark)
        except Exception:  # noqa
            pass
    fr = _okx('/api/v5/public/funding-rate', {'instId': inst})
    frh = _okx('/api/v5/public/funding-rate-history', {'instId': inst, 'limit': '30'})
    fr_spark = None
    if frh:
        try:
            fr_spark = _spark([float(r['fundingRate']) * 100 for r in reversed(frh)], nd=4)
        except Exception:  # noqa
            pass
    if fr:
        try:
            rate = float(fr[0]['fundingRate']) * 100  # % per funding interval
            s = ('Bearish' if rate > 0.03 else 'Bullish' if rate > 0.002
                 else 'Bearish' if rate < 0 else 'Neutral')
            add('Funding rate', f'{rate:+.4f}%', s, spark=fr_spark)
        except Exception:  # noqa
            pass
    ls = _okx('/api/v5/rubik/stat/contracts/long-short-account-ratio', {'ccy': sym, 'period': '1D'})
    if ls:
        try:
            ratio = float(ls[0][1])
            s = 'Bearish' if ratio > 2 else 'Bullish' if ratio < 1 else 'Neutral'
            add('Long/short account ratio', f'{ratio:.2f}', s,
                spark=_spark([float(r[1]) for r in reversed(ls)]))
        except Exception:  # noqa
            pass
    tv = _okx('/api/v5/rubik/stat/taker-volume', {'ccy': sym, 'instType': 'SPOT', 'period': '1D'})
    if tv:
        try:
            sell = float(tv[0][1])
            buy = float(tv[0][2])
            r = buy / sell if sell else None
            if r:
                s = 'Bullish' if r > 1.05 else 'Bearish' if r < 0.95 else 'Neutral'
                tv_spark = _spark([(float(x[2]) / float(x[1])) for x in reversed(tv) if float(x[1])])
                add('Taker buy/sell ratio', f'{r:.2f}', s, spark=tv_spark)
        except Exception:  # noqa
            pass
    # Spot ETF net flow: REAL for BTC (bitbo/Farside mirror). ETH has no free table.
    etf_active = False
    if sym == 'BTC':
        try:
            es = etf_summary()
        except Exception:  # noqa
            es = None
        if es and es.get('net_1d') is not None:
            etf_active = True
            n1 = es['net_1d']
            sig1 = 'Bullish' if n1 > 20 else 'Bearish' if n1 < -20 else 'Neutral'
            add(f'Spot ETF net flow (1d)', f'${n1:+,.0f}M', sig1, spark=es.get('spark'))
            n7 = es.get('net_7d')
            if n7 is not None:
                sig7 = 'Bullish' if n7 > 50 else 'Bearish' if n7 < -50 else 'Neutral'
                add(f'Spot ETF net flow (7d)', f'${n7:+,.0f}M', sig7)
        else:
            add('Spot ETF net flow', 'No ETF data available', 'Neutral', inactive=True)
    elif sym == 'ETH':
        add('Spot ETF net flow', 'No ETF data available', 'Neutral', inactive=True)

    if not [m for m in metrics if not m.get('inactive')]:
        return None
    net = tally['b'] - tally['r']
    headline = ('Derivatives leaning bullish' if net >= 2
                else 'Derivatives leaning bearish' if net <= -2
                else 'Derivatives mixed / neutral')
    src = f'OKX ({sym} derivatives)'
    if sym == 'BTC':
        src += ' · ETF flows (Farside/bitbo)' if etf_active else ' · no ETF data'
    elif sym == 'ETH':
        src += ' · no ETF data'
    return {'demo': False, 'source': src, 'headline': headline, 'metrics': metrics,
            'as_of': datetime.datetime.utcnow().isoformat()}


# =====================================================================
# LEVERAGE ENGINE — long/short positioning, OI, funding, (est.) leverage,
# liquidations, squeeze risk & heatmap. Core metrics are REAL (OKX public
# API). Liquidations, liquidation heatmap and the estimated-leverage
# percentile have no free/server-reachable source, so they are DERIVED
# from the real metrics and CLEARLY FLAGGED demo=True (structured so a
# live provider — e.g. CoinGlass — can drop in later).
# =====================================================================
# lev_col now imported from config
LEV_TTL_SEC = 5 * 60
_lev_state = {}
_TF_HOURS = {'1H': 1, '4H': 4, '1D': 24, '7D': 168}


def _okx_candles(inst, bar='1H', limit=120):
    js = _okx('/api/v5/market/candles', {'instId': inst, 'bar': bar, 'limit': str(limit)})
    out = []
    for r in (js or []):
        try:
            out.append({'t': int(r[0]), 'c': float(r[4])})
        except Exception:  # noqa
            pass
    return out  # newest first


def _lev_band(score, cuts, labels):
    for c, l in zip(cuts, labels):
        if score < c:
            return l
    return labels[-1]


def compute_leverage(timeframe='4H', symbol='BTC'):
    sym = (symbol or 'BTC').upper()
    inst = f'{sym}-USDT-SWAP'
    tf = timeframe if timeframe in _TF_HOURS else '4H'
    hrs = _TF_HOURS[tf]
    bar = '1D' if tf == '7D' else '1H'
    steps = 7 if tf == '7D' else hrs
    now_iso = datetime.datetime.utcnow().isoformat()

    # ---- price ----
    price, price_chg24 = None, None
    try:
        tk = ticker(sym)
        price = tk.get('price'); price_chg24 = tk.get('change24h')
    except Exception:  # noqa
        pass

    # ---- open interest (REAL) ----
    oi_usd, oi_series, oi_change_tf = None, [], None
    oi = _okx('/api/v5/public/open-interest', {'instType': 'SWAP', 'instId': inst})
    period = '1D' if tf == '7D' else '1H'
    oih = _okx('/api/v5/rubik/stat/contracts/open-interest-volume', {'ccy': sym, 'period': period})
    candles = _okx_candles(inst, bar, 120)
    price_by_t = {}
    for c in candles:
        price_by_t[c['t'] // (3600000 if bar == '1H' else 86400000)] = c['c']
    if oi:
        try:
            oi_usd = float(oi[0]['oiUsd'])
        except Exception:  # noqa
            pass
    if oih:
        try:
            rows = list(reversed(oih))  # oldest -> newest, [ts, oi, vol]
            for r in rows[-60:]:
                ts = int(r[0])
                key = ts // (3600000 if bar == '1H' else 86400000)
                oi_series.append({'t': ts, 'oi': round(float(r[1])), 'price': price_by_t.get(key)})
            latest = float(oih[0][1])
            idx = min(steps, len(oih) - 1)
            prev = float(oih[idx][1])
            oi_change_tf = round((latest - prev) / prev * 100, 1) if prev else None
            if oi_usd is None:
                oi_usd = latest
        except Exception:  # noqa
            pass
    oi_state = ('Rising' if (oi_change_tf or 0) > 1.5 else 'Falling' if (oi_change_tf or 0) < -1.5 else 'Stable')

    # ---- funding (REAL) ----
    funding, funding_series = None, []
    fr = _okx('/api/v5/public/funding-rate', {'instId': inst})
    frh = _okx('/api/v5/public/funding-rate-history', {'instId': inst, 'limit': '60'})
    if fr:
        try:
            funding = float(fr[0]['fundingRate']) * 100
        except Exception:  # noqa
            pass
    fr_avg = None
    if frh:
        try:
            vals = [float(r['fundingRate']) * 100 for r in reversed(frh)]
            for r in reversed(frh):
                funding_series.append({'t': int(r['fundingTime']), 'rate': round(float(r['fundingRate']) * 100, 5)})
            fr_avg = sum(vals[-9:]) / max(1, len(vals[-9:]))
            if funding is None and vals:
                funding = vals[-1]
        except Exception:  # noqa
            pass
    funding = funding if funding is not None else 0.0
    fr_avg = fr_avg if fr_avg is not None else funding
    funding_dir = 'Positive' if funding > 0 else 'Negative' if funding < 0 else 'Flat'
    funding_trend = ('Rising' if funding > fr_avg + 0.002 else 'Falling' if funding < fr_avg - 0.002 else 'Stable')
    funding_bias = ('Long Bias' if funding > 0.01 else 'Short Bias' if funding < -0.005 else 'Neutral')
    # exchange-level: OKX real; others need paid feed (flagged)
    funding_exchanges = [{'name': 'OKX', 'rate': round(funding, 5), 'demo': False}]

    # ---- long/short positioning (REAL account ratio) ----
    lsr, lsr_prev, ls_series = None, None, []
    ls = _okx('/api/v5/rubik/stat/contracts/long-short-account-ratio', {'ccy': sym, 'period': period})
    if ls:
        try:
            lsr = float(ls[0][1])
            idx = min(steps, len(ls) - 1)
            lsr_prev = float(ls[idx][1])
            for r in reversed(ls[-60:]):
                ls_series.append({'t': int(r[0]), 'ratio': round(float(r[1]), 3)})
        except Exception:  # noqa
            pass
    lsr = lsr if lsr else 1.0
    lsr_prev = lsr_prev if lsr_prev else lsr
    long_pct = round(lsr / (1 + lsr) * 100, 1)
    short_pct = round(100 - long_pct, 1)
    lsr_change = round(lsr - lsr_prev, 3)
    pos_trend = ('More long-heavy' if lsr_change > 0.02 else 'More short-heavy' if lsr_change < -0.02 else 'Little changed')
    # Size-weighted position ratio, liquidations, liquidation heatmap and an estimated-leverage
    # percentile all require a paid derivatives-data feed (e.g. CoinGlass). Per product decision we
    # do NOT fabricate these — they are surfaced as INACTIVE until a live source is connected.
    move = price_chg24 or 0

    # ---- squeeze risk (DERIVED from REAL signals: positioning, funding, OI trend, momentum) ----
    long_sq = int(max(0, min(100, 20 + (long_pct - 50) * 1.6 + max(0, funding) * 300
                             + max(0, oi_change_tf or 0) * 1.2 + max(0, -move) * 2)))
    short_sq = int(max(0, min(100, 20 + (short_pct - 50) * 1.6 + max(0, -funding) * 350
                              + max(0, oi_change_tf or 0) * 1.2 + max(0, move) * 2)))
    sq_label = lambda s: _lev_band(s, [30, 55, 75], ['Low', 'Moderate', 'Elevated', 'High'])
    long_sq_lbl, short_sq_lbl = sq_label(long_sq), sq_label(short_sq)

    # ---- summary: pressure / bias / squeeze (all from REAL signals) ----
    pressure_score = int(max(0, min(100, abs(funding) * 350 + abs(long_pct - 50) * 2.2
                                    + max(0, oi_change_tf or 0) * 2.0 + abs(lsr_change) * 60)))
    pressure = _lev_band(pressure_score, [25, 45, 65, 82], ['LOW', 'MODERATE', 'ELEVATED', 'HIGH', 'EXTREME'])
    if long_pct >= 55 or funding > 0.015:
        bias = 'Long Dominant'
    elif short_pct >= 55 or funding < -0.01:
        bias = 'Short Dominant'
    else:
        bias = 'Balanced'
    if long_sq >= short_sq + 12:
        squeeze = 'Long Squeeze Risk'
    elif short_sq >= long_sq + 12:
        squeeze = 'Short Squeeze Risk'
    else:
        squeeze = 'Neutral'

    # ---- interpretations (rule-based, measured language) ----
    def _oi_price_read():
        pr_up = (move or 0) >= 0
        if oi_state == 'Rising' and pr_up:
            return "Price and open interest are rising together, suggesting fresh leveraged longs are driving the move."
        if oi_state == 'Rising' and not pr_up:
            return "Open interest is rising while price softens, which may indicate new shorts building or longs adding into weakness."
        if oi_state == 'Falling' and pr_up:
            return "Price is rising as open interest falls, which can reflect short covering rather than fresh leveraged buying."
        if oi_state == 'Falling' and not pr_up:
            return "Both price and open interest are falling, consistent with leveraged positions being unwound (de-risking)."
        return "Open interest is broadly stable, suggesting leveraged participation is holding steady."

    summary_interp = (
        f"Leverage pressure reads {pressure}. Positioning is {long_pct:.0f}% long / {short_pct:.0f}% short "
        f"({bias.lower()}), funding is {funding:+.4f}% ({funding_bias.lower()}) and open interest is {oi_state.lower()} "
        f"({(oi_change_tf or 0):+.1f}% over {tf}). "
        + ("A larger concentration of leveraged longs could increase downside liquidation risk if support gives way."
           if squeeze == 'Long Squeeze Risk' else
           "Crowded shorts holding into a firm market could be forced to cover on a move higher, raising short-squeeze risk."
           if squeeze == 'Short Squeeze Risk' else
           "Long and short squeeze risks look broadly balanced right now."))

    funding_interp = ("Positive funding means longs are paying shorts, indicating stronger demand for leveraged long exposure."
                      if funding > 0 else
                      "Negative funding means shorts are paying longs, indicating heavier leveraged short positioning."
                      if funding < 0 else "Funding is flat — neither side is paying a meaningful premium.")

    # ---- CryptoMarkAI observations + assessment (from REAL data only) ----
    obs = []
    obs.append(f"Positioning is {long_pct:.0f}% long vs {short_pct:.0f}% short and has become {pos_trend.lower()} over the last {tf}.")
    obs.append(f"Open interest is {oi_state.lower()} ({(oi_change_tf or 0):+.1f}% over {tf}). " + _oi_price_read())
    obs.append(f"Funding is {funding:+.4f}% and {funding_trend.lower()} versus its recent average ({funding_bias.lower()}).")
    obs.append(f"The long/short account ratio is {lsr:.2f} (vs {lsr_prev:.2f} a {tf} ago), a {('rise' if lsr_change > 0 else 'fall' if lsr_change < 0 else 'flat read')} in relative long crowding.")
    obs.append(f"{'Downside long-squeeze risk' if squeeze == 'Long Squeeze Risk' else 'Upside short-squeeze risk' if squeeze == 'Short Squeeze Risk' else 'Two-sided squeeze risk'} "
               f"is currently {'elevated' if max(long_sq, short_sq) >= 55 else 'moderate' if max(long_sq, short_sq) >= 30 else 'low'} "
               f"based on positioning, funding and OI trend.")
    if squeeze == 'Long Squeeze Risk':
        assess_title = 'Elevated Long-Side Risk'
    elif squeeze == 'Short Squeeze Risk':
        assess_title = 'Elevated Short-Side Risk'
    else:
        assess_title = 'Balanced Leverage Environment'
    assess_text = (f"{summary_interp} These are probabilistic reads of positioning and leverage, not forecasts of a specific price move.")

    # ---- Albert's Call impact (leverage is ONE input) ----
    impact_points = int(round((short_sq - long_sq) / 6.0))
    impact_points = max(-15, min(15, impact_points))
    if impact_points < -2:
        impact_label = 'Bearish Pressure'
    elif impact_points > 2:
        impact_label = 'Bullish Pressure'
    else:
        impact_label = 'Neutral'
    impact_expl = (
        (f"Elevated long positioning and {oi_state.lower()} open interest are adding modest downside risk to the broader "
         f"Ask Albert assessment." if impact_points < 0 else
         f"Crowded shorts into a firm tape are adding modest upside risk to the broader Ask Albert assessment." if impact_points > 0 else
         "Leverage is broadly balanced and is a neutral input to the broader Ask Albert assessment.")
        + " Leverage is only one of many signals in Albert's Call.")

    return {
        'symbol': sym, 'timeframe': tf, 'price': price, 'price_change_24h': price_chg24, 'as_of': now_iso,
        'summary': {'pressure': pressure, 'pressure_score': pressure_score, 'bias': bias,
                    'squeeze': squeeze, 'interpretation': summary_interp},
        'positioning': {'long_pct': long_pct, 'short_pct': short_pct, 'account_ratio': round(lsr, 3),
                        'account_ratio_prev': round(lsr_prev, 3), 'position_ratio': None,
                        'position_ratio_active': False,
                        'ratio_change_tf': lsr_change, 'trend': pos_trend, 'series': ls_series},
        'open_interest': {'value_usd': oi_usd, 'change_tf_pct': oi_change_tf, 'state': oi_state,
                          'series': oi_series, 'interpretation': _oi_price_read()},
        'funding': {'rate': round(funding, 5), 'direction': funding_dir, 'trend': funding_trend,
                    'avg_recent': round(fr_avg, 5), 'bias': funding_bias, 'exchanges': funding_exchanges,
                    'series': funding_series, 'interpretation': funding_interp,
                    'exchanges_note': 'Only OKX is a live free feed; multi-exchange funding needs a paid aggregator.'},
        'estimated_leverage': {'active': False, 'status': 'No data available',
                               'reason': 'No estimated-leverage data available (needs a live leverage/exchange-reserve feed such as CoinGlass or CryptoQuant).',
                               'interpretation': 'No estimated-leverage data available.'},
        'liquidations': {'active': False, 'status': 'No data available',
                         'reason': 'No liquidation data available (needs a live liquidations feed such as CoinGlass).'},
        'heatmap': {'active': False, 'status': 'No data available', 'price': price,
                    'reason': 'No liquidation-heatmap data available (needs a live liquidation-level feed such as CoinGlass).'},
        'squeeze': {'long_risk': long_sq, 'long_label': long_sq_lbl, 'short_risk': short_sq,
                    'short_label': short_sq_lbl,
                    'long_explain': (f"Long positioning is {long_pct:.0f}% with {funding:+.4f}% funding and {oi_state.lower()} OI; "
                                     "a loss of nearby support could force leveraged longs to close."),
                    'short_explain': (f"Short positioning is {short_pct:.0f}% while BTC holds firm; "
                                      "a rapid move higher could force leveraged shorts to cover.")},
        'bitmark': {'observations': obs, 'assessment_title': assess_title, 'assessment_text': assess_text},
        'albert_call': {'impact_label': impact_label, 'impact_points': impact_points, 'explanation': impact_expl},
        'sources': ['OKX public API (open interest, funding, long/short account ratio, taker) — REAL',
                    'Liquidations, liquidation heatmap, estimated-leverage & size-weighted position ratio — NO DATA AVAILABLE (no free feed; connect a paid provider such as CoinGlass to activate)'],
        'disclaimer': ('Market data and CryptoMarkAI analysis are provided for informational purposes only and should not be '
                       'considered financial advice. Derivatives and leveraged trading involve substantial risk. Liquidation '
                       'levels and squeeze-risk indicators are estimates and may not reflect actual market outcomes.')}


def get_leverage(timeframe='4H', refresh=False):
    key = f'BTC:{timeframe}'
    c = lev_col.find_one({'_id': key}, {'_id': 0}) or {}
    stale = (time.time() - c.get('fetched_ts', 0)) >= LEV_TTL_SEC
    if refresh or not c.get('data') or stale:
        try:
            data = compute_leverage(timeframe)
            lev_col.update_one({'_id': key}, {'$set': {'_id': key, 'data': data,
                               'fetched_ts': time.time()}}, upsert=True)
            return data
        except Exception:  # noqa
            traceback.print_exc()
    return c.get('data')


# =====================================================================
# PHASE A: Fear & Greed / Network Health / Exchange Net-Flow (REAL, keyless)
# =====================================================================
# misc_col / usage_col now imported from config


def _bump_usage(kind, n=1):
    """Lightweight LLM/usage counter for the Admin screen (best-effort, non-blocking)."""
    try:
        today = datetime.date.today().isoformat()
        usage_col.update_one({'_id': f'{kind}:{today}'},
                             {'$inc': {'count': n}, '$set': {'kind': kind, 'day': today}}, upsert=True)
        usage_col.update_one({'_id': f'{kind}:total'},
                             {'$inc': {'count': n}, '$set': {'kind': kind}}, upsert=True)
    except Exception:  # noqa
        pass


def _misc_get(key, ttl, builder):
    c = misc_col.find_one({'_id': key}, {'_id': 0}) or {}
    if c.get('data') and (time.time() - c.get('fetched_ts', 0)) < ttl:
        return c['data']
    try:
        data = builder()
        if data:
            misc_col.update_one({'_id': key}, {'$set': {'_id': key, 'data': data,
                                'fetched_ts': time.time()}}, upsert=True)
            return data
    except Exception:  # noqa
        traceback.print_exc()
    return c.get('data')


# Non-blocking cache: serve cached data immediately (even if stale) and refresh in the
# background. Prevents slow upstream fetches (e.g. GDELT's 3x6s retry) from blocking the
# request and causing 504s at the proxy.
_misc_refreshing = set()
_misc_refresh_lock = threading.Lock()


def _misc_refresh_bg(key, builder):
    try:
        data = builder()
        if data:
            misc_col.update_one({'_id': key}, {'$set': {'_id': key, 'data': data,
                                'fetched_ts': time.time()}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        with _misc_refresh_lock:
            _misc_refreshing.discard(key)


def _misc_get_async(key, ttl, builder):
    c = misc_col.find_one({'_id': key}, {'_id': 0}) or {}
    data = c.get('data')
    fresh = data and (time.time() - c.get('fetched_ts', 0)) < ttl
    if not fresh:
        with _misc_refresh_lock:
            if key not in _misc_refreshing:
                _misc_refreshing.add(key)
                threading.Thread(target=_misc_refresh_bg, args=(key, builder), daemon=True).start()
    return data  # may be stale or None; the caller decides how to present it


def compute_fear_greed():
    j = _engine_get('https://api.alternative.me/fng/?limit=90&format=json')
    data = (j or {}).get('data') or []
    if not data:
        return None
    def _row(r):
        return {'value': int(r['value']), 'label': r['value_classification'],
                'ts': int(r['timestamp'])}
    latest = _row(data[0])
    hist = [_row(r) for r in reversed(data)]  # oldest -> newest
    vals = [h['value'] for h in hist]
    wk_ago = hist[-8]['value'] if len(hist) >= 8 else hist[0]['value']
    mo_ago = hist[-31]['value'] if len(hist) >= 31 else hist[0]['value']
    v = latest['value']
    if v <= 25:
        read = ("Sentiment is in Fear/Extreme Fear. Historically, crowd fear can mark points of "
                "capitulation where downside is increasingly priced in — but fear alone is not a bottom signal.")
    elif v >= 75:
        read = ("Sentiment is in Greed/Extreme Greed. Crowd euphoria has often coincided with local "
                "tops and rising fragility — it suggests caution, not a guaranteed reversal.")
    else:
        read = ("Sentiment is broadly neutral — the crowd is neither fearful nor greedy, so this indicator "
                "is not flagging an extreme right now.")
    return {'value': v, 'label': latest['label'], 'ts': latest['ts'],
            'week_ago': wk_ago, 'month_ago': mo_ago, 'history': hist,
            'read': read, 'source': 'alternative.me Crypto Fear & Greed Index'}


def compute_network_health():
    hr = _engine_get('https://mempool.space/api/v1/mining/hashrate/3m') or {}
    da = _engine_get('https://mempool.space/api/v1/difficulty-adjustment') or {}
    fees = _engine_get('https://mempool.space/api/v1/fees/recommended') or {}
    mp = _engine_get('https://mempool.space/api/mempool') or {}
    cur_hr = hr.get('currentHashrate')
    cur_diff = hr.get('currentDifficulty')
    hseries = [{'ts': x['timestamp'], 'v': round(x['avgHashrate'] / 1e18, 1)}
               for x in (hr.get('hashrates') or [])][-90:]  # EH/s
    fast = fees.get('fastestFee'); half = fees.get('halfHourFee'); hour = fees.get('hourFee')
    congestion = ('Low' if (mp.get('count') or 0) < 20000 else 'Elevated'
                  if (mp.get('count') or 0) < 80000 else 'High')
    fee_state = ('Cheap' if (fast or 0) <= 10 else 'Normal' if (fast or 0) <= 50 else 'Expensive')
    dchg = da.get('difficultyChange')
    # simple health read
    read = (f"Fees are {fee_state.lower()} (~{fast} sat/vB for a fast confirm) and the mempool looks "
            f"{congestion.lower()} ({(mp.get('count') or 0):,} txns waiting). "
            f"Next difficulty adjustment is estimated {('+' if (dchg or 0) >= 0 else '')}{(dchg or 0):.1f}% "
            f"in ~{round((da.get('remainingTime') or 0)/86400000, 1)} days. "
            "Hashrate near record levels reflects a well-secured network.")
    return {
        'hashrate_ehs': (round(cur_hr / 1e18, 1) if cur_hr else (hseries[-1]['v'] if hseries else None)),
        'difficulty': cur_diff, 'difficulty_change_pct': (round(dchg, 2) if dchg is not None else None),
        'retarget_days': round((da.get('remainingTime') or 0) / 86400000, 1),
        'retarget_progress_pct': round(da.get('progressPercent') or 0, 1),
        'fees': {'fastest': fast, 'half_hour': half, 'hour': hour, 'state': fee_state},
        'mempool': {'count': mp.get('count'), 'vsize': mp.get('vsize'), 'congestion': congestion},
        'hashrate_series': hseries, 'read': read,
        'source': 'mempool.space (hashrate, difficulty, fees, mempool)'}


def compute_exchange_flows():
    """Aggregate BTC balance held by tracked EXCHANGE wallets over time (REAL, reconstructed
    from on-chain history). Net decline = coins leaving exchanges (bullish supply reduction)."""
    meta = whale_col.find_one({'_id': '_meta'}) or {}
    price = meta.get('price')
    exch = [w for w in WHALE_SEED if w['category'] == 'Exchange']
    # gather each exchange whale's reconstructed daily series
    per = []
    all_dates = set()
    for w in exch:
        h = get_whale_history(w['address'])
        s = h.get('series') or []
        if s:
            per.append({a['date']: a['bal'] for a in s})
            all_dates.update(a['date'] for a in s)
    if not per:
        return None
    dates = sorted(all_dates)
    agg = []
    lasts = [None] * len(per)
    for dt in dates:
        tot = 0.0
        for i, m in enumerate(per):
            if dt in m:
                lasts[i] = m[dt]
            if lasts[i] is not None:
                tot += lasts[i]
        agg.append({'date': dt, 'balance': round(tot, 1)})
    # keep a reasonable window (last ~180 days) and downsample
    agg = agg[-180:]
    def _chg(days):
        if len(agg) < 2:
            return None
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        past = [a for a in agg if a['date'] <= cutoff]
        base = past[-1]['balance'] if past else agg[0]['balance']
        return round(agg[-1]['balance'] - base, 1)
    net30 = _chg(30)
    trend = ('Outflow (bullish supply reduction)' if (net30 or 0) < -200
             else 'Inflow (rising exchange supply)' if (net30 or 0) > 200 else 'Flat')
    return {'series': agg, 'current': agg[-1]['balance'], 'price': price,
            'net_7d': _chg(7), 'net_30d': net30, 'net_90d': _chg(90), 'trend': trend,
            'read': (f"Tracked exchange wallets hold ~{round(agg[-1]['balance']):,} BTC. Over 30 days the "
                     f"balance changed {('+' if (net30 or 0) >= 0 else '')}{net30:,.0f} BTC — {trend.lower()}. "
                     "Coins leaving exchanges typically reduce immediately sellable supply."),
            'source': 'mempool.space (exchange-wallet reconstruction)'}





def _refresh_onchain_bg(symbol='BTC'):
    sym = (symbol or 'BTC').upper()
    if _onchain_state.get(sym):
        return
    _onchain_state[sym] = True
    try:
        sm = None
        if sym == 'BTC':
            gc = glassnode_col.find_one({'_id': 'smart_money_btc'}) or {}
            gn = gc.get('series')
            if GLASSNODE_API_KEY and (time.time() - gc.get('fetched_ts', 0) >= GLASSNODE_TTL_SEC):
                threading.Thread(target=_refresh_glassnode_bg, daemon=True).start()
            sm = build_smart_money_engine(gn)
        dv = build_derivatives_engine(sym)
        doc_id = 'btc' if sym == 'BTC' else f'onchain_{sym}'
        onchain_col.update_one({'_id': doc_id}, {'$set': {
            '_id': doc_id, 'symbol': sym, 'fetched_ts': time.time(),
            'fetched_at': datetime.datetime.utcnow().isoformat(),
            'smart_money': sm, 'institutional': dv}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _onchain_state[sym] = False


def get_onchain_panels(symbol='BTC'):
    """Return cached {smart_money, institutional} real panels for a coin; refresh in background when stale.
    Smart Money (on-chain valuation) is BTC-only; altcoins get the OKX derivatives panel only."""
    sym = (symbol or 'BTC').upper()
    doc_id = 'btc' if sym == 'BTC' else f'onchain_{sym}'
    c = onchain_col.find_one({'_id': doc_id}) or {}
    now = time.time()
    empty = (not c.get('smart_money') and not c.get('institutional'))
    if empty or (now - c.get('fetched_ts', 0) >= ONCHAIN_TTL_SEC):
        threading.Thread(target=_refresh_onchain_bg, args=(sym,), daemon=True).start()
    return {'smart_money': c.get('smart_money'), 'institutional': c.get('institutional')}


# =====================================================================
# ETF FLOWS (REAL, keyless) — US spot Bitcoin ETF daily net flows.
# Source: bitbo.io ETF-flows table (mirrors Farside data). Farside itself
# is Cloudflare-blocked from this server, but bitbo serves the same numbers
# as a plain HTML table we can parse. Values are USD millions ($M).
# Cached in Mongo, background refresh ~3h.
# =====================================================================
# etf_col now imported from config
ETF_TTL_SEC = 3 * 3600
_etf_state = {'running': False}
ETF_UA = {'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/121 Safari/537.36')}
_MONTHS = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
           'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}


def _etf_num(s):
    s = (s or '').replace(',', '').replace('$', '').strip()
    if s in ('', '-', '—', 'n/a', 'N/A'):
        return None
    try:
        return round(float(s), 1)
    except Exception:  # noqa
        return None


def _parse_bitbo_etf():
    """Scrape bitbo.io spot BTC ETF flow table -> structured daily flows.
    Returns {issuers:[...], daily:[{date, flows:{ticker:val}, total}], summary:{...}} or None."""
    import re as _re
    import html as _html
    try:
        r = requests.get('https://bitbo.io/treasuries/etf-flows/', headers=ETF_UA, timeout=25)
        if r.status_code != 200:
            return None
        t = r.text
        i = t.lower().find('<table')
        j = t.lower().find('</table>', i)
        if i < 0 or j < 0:
            return None
        tbl = t[i:j + 8]
        trs = _re.findall(r'<tr.*?</tr>', tbl, _re.S)
        if len(trs) < 2:
            return None

        def cells(tr):
            cs = _re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, _re.S)
            return [_html.unescape(_re.sub(r'<[^>]+>', '', c)).strip() for c in cs]

        header = cells(trs[0])
        if not header or header[0].lower() != 'date':
            # some layouts put header in a thead-less first row; try to detect
            for tr in trs[:2]:
                h = cells(tr)
                if h and h[0].lower() == 'date':
                    header = h
                    break
        # issuers = header cols between Date and Totals
        try:
            tot_idx = next(k for k, h in enumerate(header) if h.lower() in ('totals', 'total'))
        except StopIteration:
            tot_idx = len(header) - 1
        issuers = header[1:tot_idx]

        daily, summary = [], {}
        summary_labels = {'total', 'average', 'maximum', 'minimum'}
        for tr in trs[1:]:
            c = cells(tr)
            if not c or len(c) < 2:
                continue
            label = c[0].strip()
            low = label.lower()
            if low in summary_labels:
                summary[low] = _etf_num(c[tot_idx]) if tot_idx < len(c) else None
                continue
            # parse date like 'Aug 06, 2026'
            m = _re.match(r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})', label)
            if not m:
                continue
            mon = _MONTHS.get(m.group(1)[:3].title())
            if not mon:
                continue
            try:
                dt = datetime.date(int(m.group(3)), mon, int(m.group(2)))
            except Exception:  # noqa
                continue
            flows = {}
            for k, tick in enumerate(issuers):
                idx = k + 1
                flows[tick] = _etf_num(c[idx]) if idx < len(c) else None
            total = _etf_num(c[tot_idx]) if tot_idx < len(c) else None
            if total is None:
                total = round(sum(v for v in flows.values() if v is not None), 1)
            daily.append({'date': dt.isoformat(), 'flows': flows, 'total': total})
        if not daily:
            return None
        # sort most-recent-first
        daily.sort(key=lambda d: d['date'], reverse=True)
        return {'issuers': issuers, 'daily': daily, 'summary': summary,
                'source': 'bitbo.io (Farside mirror)'}
    except Exception:  # noqa
        traceback.print_exc()
        return None


def _fetch_tftc_etf():
    """Full-history US spot BTC ETF daily net flows from tftc.io/bitcoin-etf-flows/data.json
    (Farside data, keyless). Values arrive in USD -> converted to $M. ~660+ days since 2024-01-11."""
    try:
        js = _engine_get('https://www.tftc.io/bitcoin-etf-flows/data.json', headers=ETF_UA, timeout=25)
        days = js.get('days') if isinstance(js, dict) else None
        if not days:
            return None
        daily = []
        for d in days:
            per = d.get('perEtfUsd') or {}
            flows = {k: round(v / 1e6, 1) for k, v in per.items() if v is not None}
            tot = d.get('netFlowUsd')
            total = round(tot / 1e6, 1) if tot is not None else round(sum(flows.values()), 1)
            daily.append({'date': d.get('date'), 'flows': flows, 'total': total,
                          'btc_close': d.get('btcCloseUsd')})
        daily = [x for x in daily if x.get('date')]
        if not daily:
            return None
        issuers = list((days[-1].get('perEtfUsd') or {}).keys())
        daily.sort(key=lambda x: x['date'], reverse=True)
        return {'issuers': issuers, 'daily': daily, 'summary': {},
                'source': 'tftc.io (Farside full-history data)'}
    except Exception:  # noqa
        traceback.print_exc()
        return None


def _refresh_etf_bg():
    if _etf_state.get('running'):
        return
    _etf_state['running'] = True
    try:
        data = _fetch_tftc_etf() or _parse_bitbo_etf()
        if data and data.get('daily'):
            data['_id'] = 'btc'
            data['fetched_ts'] = time.time()
            data['fetched_at'] = datetime.datetime.utcnow().isoformat()
            etf_col.update_one({'_id': 'btc'}, {'$set': data}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _etf_state['running'] = False


def get_etf_flows(refresh=False):
    c = etf_col.find_one({'_id': 'btc'}, {'_id': 0}) or {}
    stale = (time.time() - c.get('fetched_ts', 0)) >= ETF_TTL_SEC
    if refresh or not c.get('daily') or stale:
        if not c.get('daily'):
            _refresh_etf_bg()  # synchronous first-time fetch so UI has data
            c = etf_col.find_one({'_id': 'btc'}, {'_id': 0}) or {}
        else:
            threading.Thread(target=_refresh_etf_bg, daemon=True).start()
    return c


def etf_summary():
    """Compact ETF-flow summary for the Institutional panel (BTC only)."""
    c = get_etf_flows()
    daily = c.get('daily') or []
    if not daily:
        return None
    totals = [d.get('total') for d in daily if d.get('total') is not None]
    if not totals:
        return None
    net_1d = totals[0]
    net_7d = round(sum(totals[:7]), 1)
    # sparkline ascending (oldest -> newest) of daily totals
    spark = _spark(list(reversed(totals[:14])), n=14, nd=1)
    # leading issuer of the latest day
    latest = daily[0]
    top = None
    fl = latest.get('flows') or {}
    if fl:
        try:
            top = max(((k, v) for k, v in fl.items() if v is not None), key=lambda x: x[1])
        except ValueError:
            top = None
    return {'net_1d': net_1d, 'net_7d': net_7d, 'spark': spark,
            'latest_date': latest.get('date'), 'top_issuer': (top[0] if top else None),
            'top_issuer_flow': (top[1] if top else None)}



# =====================================================================
# WHALE WATCH (Phase 1) — curated, publicly-labeled BTC entity addresses.
# Live balances via mempool.space (fallback blockchain.info), free/no key.
# Tracks daily balance snapshots to derive accumulation/distribution + alerts.
# =====================================================================
# whale_col now imported from config
WHALE_TTL_SEC = 45 * 60
_whale_state = {'running': False}
WHALE_SEED = [
    {'address': '34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo', 'name': 'Binance', 'category': 'Exchange'},
    {'address': '3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6', 'name': 'Binance', 'category': 'Exchange'},
    {'address': 'bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h', 'name': 'Binance (hot wallet)', 'category': 'Exchange'},
    {'address': 'bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97', 'name': 'Bitfinex', 'category': 'Exchange'},
    {'address': 'bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfc27a4', 'name': 'Robinhood', 'category': 'Exchange'},
    {'address': 'bc1qa5wkgaew2dkv56kfvj49j0av5nml45x9ek9hz6', 'name': 'U.S. Government (seized)', 'category': 'Government'},
    {'address': '1FeexV6bAHb8ybZjqQMjJrcCrHGW9sb6uF', 'name': 'Dormant mega-whale (since 2011)', 'category': 'Whale'},
    {'address': '3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb', 'name': 'Unknown mega-whale', 'category': 'Whale'},
    {'address': '1LdRcdxfbSnmCYYNdeYpUnztiYzVfBEQeC', 'name': 'Unknown mega-whale', 'category': 'Whale'},
    {'address': '12ib7dApVFvg82TXKycWBNpN8kFyiAN1dr', 'name': 'Early whale', 'category': 'Whale'},
    {'address': '1PeizMg76Cf96nUQrYg8xuoZWLQozU5zGW', 'name': 'Early mega-whale', 'category': 'Whale'},
    {'address': 'bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2', 'name': 'Coinbase (cold)', 'category': 'Exchange'},
    {'address': '12tkqA9xSoowkzoERHMWNKsTey55YEBqkv', 'name': 'Poloniex (cold)', 'category': 'Exchange'},
    {'address': '1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g', 'name': 'OKX', 'category': 'Exchange'},
    {'address': 'bc1qazcm763858nkj2dj986etajv6wquslv8uxwczt', 'name': 'MicroStrategy / Strategy (attributed)', 'category': 'Treasury'},
]


def _addr_balance(addr):
    js = _engine_get(f'https://mempool.space/api/address/{addr}')
    try:
        cs = js['chain_stats']
        return {'balance': (cs['funded_txo_sum'] - cs['spent_txo_sum']) / 1e8, 'tx_count': cs.get('tx_count')}
    except Exception:  # noqa
        pass
    js = _engine_get(f'https://blockchain.info/rawaddr/{addr}', params={'limit': 0})
    try:
        return {'balance': js['final_balance'] / 1e8, 'tx_count': js.get('n_tx')}
    except Exception:  # noqa
        return None


def _fire_whale_alert(w, delta):
    """Fire a coin-scoped (BTC) smart alert on a large whale balance move."""
    try:
        direction = 'moved out of' if delta < 0 else 'received by'
        is_exch = w['category'] == 'Exchange'
        # exchange outflow = bullish (less sell supply); whale accumulation = bullish
        bullish = (delta < 0) if is_exch else (delta > 0)
        sev = 'high' if abs(delta) >= 5000 else 'medium'
        aid = f"whale_{w['address'][:10]}_{datetime.date.today().isoformat()}"
        title = f"Whale move: {w['name']} {('outflow' if delta < 0 else 'inflow')} {abs(delta):,.0f} BTC"
        msg = (f"{abs(delta):,.0f} BTC {direction} {w['name']} ({w['category']}). "
               f"{'Coins leaving an exchange often reads bullish (less sell-side supply).' if (is_exch and delta < 0) else ''}"
               f"{'Coins moving to an exchange can read bearish (potential sell-side).' if (is_exch and delta > 0) else ''}"
               f"{'Large-holder accumulation.' if (not is_exch and delta > 0) else ''}"
               f"{'Large-holder distribution.' if (not is_exch and delta < 0) else ''}").strip()
        smart_alerts_col.update_one({'_id': aid}, {'$setOnInsert': {
            '_id': aid, 'id': aid, 'ts': datetime.datetime.utcnow().isoformat(),
            'as_of': datetime.date.today().isoformat(), 'symbol': 'BTC', 'category': 'Whale',
            'severity': sev, 'title': title, 'message': msg,
            'signal': 'Bullish' if bullish else 'Bearish', 'seen': False}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()


def _refresh_whales_bg():
    if _whale_state.get('running'):
        return
    _whale_state['running'] = True
    try:
        today = datetime.date.today().isoformat()
        pj = _engine_get('https://api.coingecko.com/api/v3/simple/price',
                         params={'ids': 'bitcoin', 'vs_currencies': 'usd'})
        price = None
        try:
            price = float(pj['bitcoin']['usd'])
        except Exception:  # noqa
            pass
        for w in WHALE_SEED:
            b = _addr_balance(w['address'])
            if not b:
                continue
            bal = round(b['balance'], 4)
            doc = whale_col.find_one({'_id': w['address']}) or {}
            hist = doc.get('history') or []
            prev_bal = hist[-1]['bal'] if hist else None
            if not hist or hist[-1]['d'] != today:
                # New day: check for a big move vs the last recorded snapshot -> alert
                if prev_bal is not None and abs(bal - prev_bal) >= 1000:
                    _fire_whale_alert(w, round(bal - prev_bal))
                hist.append({'d': today, 'bal': bal})
                hist = hist[-90:]
            else:
                hist[-1]['bal'] = bal
            whale_col.update_one({'_id': w['address']}, {'$set': {
                '_id': w['address'], 'address': w['address'], 'name': w['name'],
                'category': w['category'], 'balance': bal, 'tx_count': b.get('tx_count'),
                'history': hist, 'updated': datetime.datetime.utcnow().isoformat()}}, upsert=True)
            time.sleep(0.5)
        whale_col.update_one({'_id': '_meta'}, {'$set': {
            '_id': '_meta', 'fetched_ts': time.time(), 'price': price,
            'fetched_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _whale_state['running'] = False


def get_whales():
    meta = whale_col.find_one({'_id': '_meta'}) or {}
    if time.time() - meta.get('fetched_ts', 0) >= WHALE_TTL_SEC:
        threading.Thread(target=_refresh_whales_bg, daemon=True).start()
    price = meta.get('price')
    items = list(whale_col.find({'_id': {'$ne': '_meta'}}, {'_id': 0}))
    out = []
    for w in items:
        hist = w.get('history') or []
        bal = w.get('balance')

        def chg(days):
            if bal is not None and len(hist) > days and hist[-1 - days].get('bal') is not None:
                return round(bal - hist[-1 - days]['bal'], 2)
            return None

        c1, c7 = chg(1), chg(7)
        ref = c7 if c7 is not None else c1
        is_exch = w.get('category') == 'Exchange'
        signal = 'Neutral'
        if ref is not None and abs(ref) >= 1:
            if is_exch:
                signal = 'Bullish' if ref < 0 else 'Bearish'   # outflow bullish
            else:
                signal = 'Bullish' if ref > 0 else 'Bearish'   # accumulation bullish
        spark = _spark([h['bal'] for h in hist], nd=0) if len(hist) >= 2 else None
        out.append({
            'name': w.get('name'), 'category': w.get('category'), 'address': w.get('address'),
            'balance': bal, 'balance_usd': (round(bal * price) if (bal and price) else None),
            'change_24h': c1, 'change_7d': c7, 'signal': signal, 'spark': spark,
            'tx_count': w.get('tx_count'), 'updated': w.get('updated'),
        })
    out.sort(key=lambda x: -(x['balance'] or 0))
    return {'whales': out, 'price': price, 'as_of': meta.get('fetched_at'),
            'source': 'mempool.space · blockchain.com (labels curated)'}


# =====================================================================
# WHALE HISTORY / IMPACT (Phase 2) — REAL balance-over-time reconstructed
# from each address's actual on-chain transaction history (mempool.space),
# working backward from the current balance. No paid API, no mock data.
# Cached in Mongo (whale_history) ~6h.
# =====================================================================
# whale_hist_col now imported from config
WHALE_HIST_TTL_SEC = 6 * 3600
_whale_name_by_addr = {w['address']: w['name'] for w in WHALE_SEED}
_whale_cat_by_addr = {w['address']: w['category'] for w in WHALE_SEED}


def _mempool_txs(address, max_txs=75):
    """Fetch up to max_txs confirmed txs (newest first) via mempool.space pagination."""
    out, last = [], None
    for _ in range(4):
        url = f'https://mempool.space/api/address/{address}/txs'
        if last:
            url += f'/chain/{last}'
        page = _engine_get(url)
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        last = page[-1].get('txid')
        if len(out) >= max_txs or len(page) < 25:
            break
        time.sleep(0.25)
    return out[:max_txs]


def _addr_delta(t, address):
    recv = sum(v.get('value', 0) for v in t.get('vout', [])
               if v.get('scriptpubkey_address') == address)
    sent = sum((vi.get('prevout') or {}).get('value', 0) for vi in t.get('vin', [])
               if (vi.get('prevout') or {}).get('scriptpubkey_address') == address)
    return (recv - sent) / 1e8


def _reconstruct_balance_series(address, current_balance, max_txs=75):
    """Return REAL balance-over-time [{date, bal}] ascending, reconstructed from tx history."""
    txs = _mempool_txs(address, max_txs)
    txs = [t for t in txs if (t.get('status') or {}).get('confirmed')]
    if not txs or current_balance is None:
        return []
    running = float(current_balance)
    pts = []
    for k, t in enumerate(txs):
        bt = (t.get('status') or {}).get('block_time')
        if bt:
            d = datetime.datetime.utcfromtimestamp(bt).date().isoformat()
            pts.append({'date': d, 'bal': round(running, 4)})
        running -= _addr_delta(t, address)  # step back to balance before this tx
    # add the earliest reconstructed level as a baseline point
    if txs:
        last_bt = (txs[-1].get('status') or {}).get('block_time')
        if last_bt:
            d = datetime.datetime.utcfromtimestamp(last_bt).date().isoformat()
            pts.append({'date': d, 'bal': round(running + _addr_delta(txs[-1], address), 4)})
    # collapse to one point per day (keep the last/most-recent balance that day), ascending
    by_day = {}
    for p in reversed(pts):  # oldest -> newest
        by_day[p['date']] = p['bal']
    series = [{'date': d, 'bal': by_day[d]} for d in sorted(by_day)]
    return series


def get_whale_history(address, refresh=False):
    doc = whale_hist_col.find_one({'_id': address}, {'_id': 0}) or {}
    stale = (time.time() - doc.get('fetched_ts', 0)) >= WHALE_HIST_TTL_SEC
    if refresh or not doc.get('series') or stale:
        w = whale_col.find_one({'_id': address}) or {}
        cur = w.get('balance')
        series = _reconstruct_balance_series(address, cur)
        if series:
            doc = {'series': series, 'balance': cur,
                   'fetched_ts': time.time(),
                   'fetched_at': datetime.datetime.utcnow().isoformat()}
            whale_hist_col.update_one({'_id': address}, {'$set': {'_id': address, **doc}}, upsert=True)
    return doc


def compute_whale_impact():
    """Aggregate whale accumulation/distribution over ~90d from reconstructed series,
    plus current concentration. REAL data only (no correlation faking)."""
    meta = whale_col.find_one({'_id': '_meta'}) or {}
    price = meta.get('price')
    whales = list(whale_col.find({'_id': {'$ne': '_meta'}}, {'_id': 0}))
    non_exch = [w for w in whales if w.get('category') != 'Exchange']
    exch = [w for w in whales if w.get('category') == 'Exchange']
    total = round(sum((w.get('balance') or 0) for w in whales), 2)
    net_30d = 0.0
    contributors = []
    for w in whales:
        h = get_whale_history(w['address'])
        s = h.get('series') or []
        if len(s) >= 2:
            # net change over up to last 30 daily points
            window = s[-31:] if len(s) > 31 else s
            delta = round((window[-1]['bal'] or 0) - (window[0]['bal'] or 0), 2)
            if abs(delta) >= 1:
                is_exch = w.get('category') == 'Exchange'
                # exchange outflow (delta<0) = bullish; holder accumulation (delta>0) = bullish
                bullish = (delta < 0) if is_exch else (delta > 0)
                net_30d += (-delta if is_exch else delta)
                contributors.append({
                    'name': w.get('name'), 'category': w.get('category'),
                    'address': w.get('address'), 'delta_30d': delta,
                    'signal': 'Bullish' if bullish else 'Bearish',
                    'from': window[0]['date'], 'to': window[-1]['date']})
    contributors.sort(key=lambda x: -abs(x['delta_30d']))
    net_30d = round(net_30d, 2)
    trend = ('Accumulation' if net_30d > 500 else 'Distribution' if net_30d < -500 else 'Neutral')
    return {
        'total_balance': total,
        'total_usd': (round(total * price) if (total and price) else None),
        'holder_balance': round(sum((w.get('balance') or 0) for w in non_exch), 2),
        'exchange_balance': round(sum((w.get('balance') or 0) for w in exch), 2),
        'net_flow_30d': net_30d, 'trend': trend,
        'contributors': contributors[:12],
        'price': price, 'as_of': meta.get('fetched_at'),
        'note': ('Aggregate net accumulation across curated whales (exchange outflows counted '
                 'as bullish supply reduction). Balance history reconstructed from real on-chain '
                 'transactions — depth varies by how active each address is.'),
        'source': 'mempool.space (on-chain reconstruction)'}


# =====================================================================
# LARGE-TRANSACTION FEED (Phase 3) — a single, time-sorted feed of notable
# on-chain moves across ALL curated whales, each entry LABELED with the
# known entity. REAL & keyless (mempool.space). Deep entity clustering of
# UNKNOWN wallets still requires a paid provider and is intentionally NOT done.
# =====================================================================
# whale_tx_col now imported from config
WHALE_TX_TTL_SEC = 20 * 60
_whale_tx_state = {'running': False}


def _build_whale_tx_feed(min_btc=50.0, per_addr=25):
    meta = whale_col.find_one({'_id': '_meta'}) or {}
    price = meta.get('price')
    feed = []
    for w in WHALE_SEED:
        addr = w['address']
        txs = _mempool_txs(addr, per_addr)
        for t in txs:
            st = t.get('status') or {}
            if not st.get('confirmed'):
                continue
            delta = _addr_delta(t, addr)
            amt = abs(delta)
            if amt < min_btc:
                continue
            is_exch = w['category'] == 'Exchange'
            inflow = delta > 0  # coins moved INTO this entity's wallet
            # exchange inflow -> potential sell pressure (bearish); outflow -> bullish
            if is_exch:
                impact = 'Bearish (exchange inflow)' if inflow else 'Bullish (exchange outflow)'
                signal = 'Bearish' if inflow else 'Bullish'
            else:
                impact = 'Bullish (accumulation)' if inflow else 'Bearish (distribution)'
                signal = 'Bullish' if inflow else 'Bearish'
            feed.append({
                'txid': t.get('txid'),
                'time': st.get('block_time'),
                'date': datetime.datetime.utcfromtimestamp(st['block_time']).isoformat() if st.get('block_time') else None,
                'entity': w['name'], 'category': w['category'], 'address': addr,
                'direction': 'in' if inflow else 'out',
                'amount': round(amt, 2),
                'amount_usd': (round(amt * price) if price else None),
                'signal': signal, 'impact': impact,
            })
    # de-dup by txid+address (an internal transfer can appear on both ends) and sort recent-first
    seen, uniq = set(), []
    for e in sorted(feed, key=lambda x: (x['time'] or 0), reverse=True):
        k = (e['txid'], e['address'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    return {'feed': uniq, 'price': price, 'min_btc': min_btc,
            'as_of': datetime.datetime.utcnow().isoformat(),
            'source': 'mempool.space · curated entity labels'}


WHALE_TX_ALERT_MIN = 1000.0   # BTC — fire a Smart Alert on moves at/above this size
WHALE_TX_ALERT_MAX_AGE = 14 * 86400  # seconds — only alert on recent moves (avoid backfilling old history)


def _fire_whale_tx_alert(e):
    """Fire a de-duplicated Smart Alert for a single large labeled transaction."""
    try:
        txid = e.get('txid') or ''
        aid = f"whaletx_{txid[:16]}_{e.get('address', '')[:8]}"
        amt = e.get('amount') or 0
        usd = e.get('amount_usd')
        sev = 'high' if amt >= 5000 else 'warning'
        arrow = 'into' if e.get('direction') == 'in' else 'out of'
        title = f"Whale move: {amt:,.0f} BTC {arrow} {e.get('entity')}"
        usd_txt = f" (~${usd/1e6:,.0f}M)" if usd else ''
        msg = (f"{amt:,.0f} BTC{usd_txt} moved {arrow} {e.get('entity')} ({e.get('category')}). "
               f"Read: {e.get('impact')}.")
        smart_alerts_col.update_one({'_id': aid}, {'$setOnInsert': {
            '_id': aid, 'id': aid, 'ts': datetime.datetime.utcnow().isoformat(),
            'as_of': datetime.date.today().isoformat(), 'symbol': 'BTC', 'category': 'Whale',
            'severity': sev, 'title': title, 'message': msg,
            'signal': e.get('signal', 'Neutral'), 'seen': False,
            'txid': txid, 'link': f'https://mempool.space/tx/{txid}'}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()


def _refresh_whale_tx_bg(min_btc=50.0):
    if _whale_tx_state.get('running'):
        return
    _whale_tx_state['running'] = True
    try:
        data = _build_whale_tx_feed(min_btc)
        data['_id'] = 'feed'
        data['fetched_ts'] = time.time()
        whale_tx_col.update_one({'_id': 'feed'}, {'$set': data}, upsert=True)
        # Fire Smart Alerts for big, RECENT moves (de-duped by txid)
        now = time.time()
        for e in (data.get('feed') or []):
            if (e.get('amount') or 0) >= WHALE_TX_ALERT_MIN and e.get('time') \
               and (now - e['time']) <= WHALE_TX_ALERT_MAX_AGE:
                _fire_whale_tx_alert(e)
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _whale_tx_state['running'] = False


def get_whale_tx_feed(refresh=False):
    c = whale_tx_col.find_one({'_id': 'feed'}, {'_id': 0}) or {}
    stale = (time.time() - c.get('fetched_ts', 0)) >= WHALE_TX_TTL_SEC
    if refresh or not c.get('feed') or stale:
        if not c.get('feed'):
            _refresh_whale_tx_bg()  # synchronous first fill
            c = whale_tx_col.find_one({'_id': 'feed'}, {'_id': 0}) or {}
        else:
            threading.Thread(target=_refresh_whale_tx_bg, daemon=True).start()
    return c




CHAT_SYSTEM = (
    "You are 'Albert', an elite crypto Quant Analyst, Senior Market Strategist and DECISIVE trading advisor "
    "built into the Ask Albert dashboard (Hucentai Crypto IQ). You blend a "
    "century of aggregated market wisdom — classic tape reading, commodities, equities and macro credit cycles — "
    "with deep, current crypto expertise. You are warm, witty and professor-like, but above all a sharp, "
    "battle-tested mentor who GIVES A CLEAR OPINION and a direct call. If asked who you are, say you are Albert, "
    "the Ask Albert HuCentAI Quant.\n\n"
    "### SCOPE — answer ANY crypto or market question\n"
    "Bitcoin, Ethereum, Solana and all altcoins; DeFi, L2s/rollups, staking/restaking, stablecoins, NFTs and "
    "tokenomics; spot and derivatives market structure & microstructure; on-chain analytics (MVRV, SOPR, realized "
    "price, exchange in/out-flows, whale activity, supply in profit); ETF flows; miners; macro (Fed liquidity, "
    "rates, DXY, CPI, yields, global M2); cross-asset correlations (S&P 500, Nasdaq, gold, DXY); halving / "
    "power-law cycles; and full technical & trading theory. If a question is outside crypto/markets, help briefly "
    "then steer back to what matters for the user's positioning.\n\n"
    "### BE A DECISIVE ADVISOR (do not dodge)\n"
    "When the user asks whether to buy, sell, hold, or WHEN to act, give a DIRECT, actionable call. Structure it:\n"
    "1) THE CALL — a clear stance right now: e.g. 'Buy / Accumulate the dip', 'Trim / Take profit', 'Hold', "
    "'Wait for confirmation'. State your conviction (low / medium / high).\n"
    "2) WHY — the 2-4 strongest data-driven reasons, citing the live dashboard numbers and any live web facts.\n"
    "3) LEVELS & TIMING — concrete entry / add zones, an invalidation (stop) level, and take-profit / target "
    "levels; and exactly what would flip the call ('turn bullish above $X', 'get defensive below $Y'). If they "
    "ask WHEN, give the price levels / conditions / time-window that would trigger a buy versus a sell.\n"
    "4) WHAT TO WATCH — a short checklist of the specific catalysts, levels and metrics to monitor next "
    "(macro prints, ETF flows, funding, key support/resistance, on-chain shifts).\n"
    "5) RISK PLAN — invalidation, position sizing (~1-2% account risk per tactical trade), DCA vs lump-sum, and "
    "aim for asymmetric risk-reward (>= 1:2.5).\n"
    "Signal cheat-sheet — Buy/Accumulate: high-timeframe support, deep-value cycle metrics (MVRV Z-Score, Mayer "
    "Multiple, realized-price bottoms), spot-volume absorption, flushed or negative funding. Sell/Distribute: "
    "parabolic blow-off volume, bearish RSI/MACD divergence, RSI>80, extreme positive funding, retail euphoria, "
    "heavy institutional outflows.\n\n"
    "### GROUNDING & TOOLS\n"
    "- The LIVE DASHBOARD DATA below is your primary source. When it contains a number, cite THAT exact number and "
    "never fabricate, infer or estimate values shown as 'no data'/'inactive' — say 'no [X] data available'.\n"
    "- You have a LIVE WEB SEARCH tool. Use it for anything current or external to the dashboard — the live price "
    "of any coin, breaking crypto news, latest CPI/FOMC, ETF flow headlines, other assets. Cite the source and "
    "date for time-sensitive external facts.\n"
    "- ALBERT'S ENGINES: when the section 'ALBERT'S ENGINES' is present below, it holds YOUR Alert-Engine edge "
    "board (highest backtest-edge setups), live sector rotation, recently fired signals, and the user's ACTIVE "
    "tracked strategies. Use it directly when asked things like 'what's my best edge setup right now?', 'which "
    "sectors are rotating?', or 'how are my strategies doing?' — but TRANSLATE it into plain English: name the "
    "coin and what it means in everyday words; mention a number (edge, win-rate, level) only when it genuinely "
    "helps, not as a data dump. If that section is absent or empty, say the engine hasn't produced a read yet "
    "rather than inventing setups.\n\n"
    "### STYLE\n"
    "- LAYMAN BY DEFAULT: explain like you're talking to a smart friend who is NOT a trader. Use everyday language, "
    "translate any jargon in 3-4 words, and prefer plain phrasing ('it's overheated and due a breather') over raw "
    "indicators ('RSI 72'). Go into technical detail (specific indicators, structure, exact levels) ONLY when the "
    "user explicitly asks for it (e.g. says 'technical', 'deep', 'the numbers', or turns on Deep dive).\n"
    "- Speak plainly and with conviction. Lead with the answer, then the reasoning. Use short **bold** labels and "
    "simple bullet lists for readability. Talk in odds, levels and risk-reward, not vague hedging. Keep it tight — "
    "usually 120-280 words, up to ~350 when the user wants depth. Do NOT open with a greeting. Do NOT add legal "
    "disclaimers or 'not financial advice' boilerplate — just give your best, most honest professional call.\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)


# =====================================================================
# AI MODEL SWITCHER — per-feature choice of Flash (fast/cheap) vs Pro
# (deeper reasoning). Stored in misc_col; every LLM call site resolves its
# model via _model_for(feature). Grounded web-search sub-calls still route to
# Flash inside the LlmChat shim (Pro preview lacks Search grounding).
# =====================================================================
FLASH_MODEL = CHAT_MODEL          # gemini-3-flash-preview
PRO_MODEL = ALBERT_CHAT_MODEL     # gemini-3.1-pro-preview

# feature -> default tier ('flash' | 'pro')
_MODEL_FEATURE_DEFAULTS = {
    'chat_standard': 'flash',   # quick Ask-Albert replies
    'chat_deep': 'pro',         # "Deep dive" Ask-Albert replies
    'insight': 'flash',         # per-section AI insights
    'brief': 'flash',           # morning / coin briefs + weekly recap
    'strategy': 'flash',        # strategy drafting
    'news': 'flash',            # per-headline news analysis
}
_MODEL_FEATURE_LABELS = {
    'chat_standard': 'Ask Albert — quick chat',
    'chat_deep': 'Ask Albert — deep dive',
    'insight': 'Section AI insights',
    'brief': 'Morning & coin briefs',
    'strategy': 'Strategy drafting',
    'news': 'News headline analysis',
}


def _get_model_prefs():
    """Current per-feature model tier prefs, merged over defaults."""
    doc = misc_col.find_one({'_id': 'ai_model_prefs'}) or {}
    prefs = dict(_MODEL_FEATURE_DEFAULTS)
    for k in _MODEL_FEATURE_DEFAULTS:
        v = doc.get(k)
        if v in ('flash', 'pro'):
            prefs[k] = v
    return prefs


def _model_for(feature):
    """Resolve a feature key to a concrete Gemini model id."""
    tier = _get_model_prefs().get(feature, _MODEL_FEATURE_DEFAULTS.get(feature, 'flash'))
    return PRO_MODEL if tier == 'pro' else FLASH_MODEL


@app.get('/api/v1/settings/models')
def get_model_settings():
    return {'status': 'ready', 'prefs': _get_model_prefs(),
            'models': {'flash': FLASH_MODEL, 'pro': PRO_MODEL},
            'features': [{'key': k, 'label': _MODEL_FEATURE_LABELS[k],
                          'default': _MODEL_FEATURE_DEFAULTS[k]} for k in _MODEL_FEATURE_DEFAULTS]}


@app.post('/api/v1/settings/models')
def save_model_settings(payload: dict = Body(...)):
    incoming = payload.get('prefs') or payload or {}
    update = {}
    for k in _MODEL_FEATURE_DEFAULTS:
        v = incoming.get(k)
        if v in ('flash', 'pro'):
            update[k] = v
    if update:
        misc_col.update_one({'_id': 'ai_model_prefs'}, {'$set': update}, upsert=True)
    return {'status': 'ready', 'prefs': _get_model_prefs()}


# =====================================================================
# NATIVE GOOGLE SIGN-IN (Google Identity Services ID-token flow)
# Frontend renders the Google button, gets a JWT credential, and POSTs it to
# /api/auth/google. We verify it against GOOGLE_CLIENT_ID, upsert the user, and
# issue our OWN opaque 7-day httpOnly session cookie. Sync pymongo throughout.
# =====================================================================
from google.oauth2 import id_token as _google_id_token
from google.auth.transport import requests as _google_requests

AUTH_COOKIE = 'albert_session'
AUTH_SESSION_DAYS = 7


def get_current_user(request: Request,
                     albert_session: str = Cookie(default=None, alias=AUTH_COOKIE),
                     authorization: str = Header(default=None)):
    """FastAPI dependency: resolve the signed-in user from the session cookie
    (or Authorization: Bearer <token>). Raises 401 when not authenticated."""
    token = albert_session
    if not token and authorization and authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    row = auth_sessions_col.find_one({'token': token})
    now = datetime.datetime.utcnow()
    if not row or row.get('expires_at') and row['expires_at'] <= now:
        if row:
            auth_sessions_col.delete_one({'_id': row['_id']})
        raise HTTPException(status_code=401, detail='Session expired')
    user = users_col.find_one({'_id': row['user_id']},
                              {'_id': 1, 'email': 1, 'name': 1, 'picture': 1})
    if not user:
        raise HTTPException(status_code=401, detail='User not found')
    return user


@app.post('/api/auth/google')
def auth_google(payload: dict = Body(...)):
    """Verify a Google ID-token credential, upsert the user, and set a session cookie."""
    cred = (payload.get('credential') or '').strip()
    if not cred:
        raise HTTPException(status_code=400, detail='Missing Google credential')
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail='Google sign-in is not configured')
    try:
        info = _google_id_token.verify_oauth2_token(
            cred, _google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception:  # noqa
        raise HTTPException(status_code=401, detail='Invalid Google token')
    if not info.get('email_verified'):
        raise HTTPException(status_code=400, detail='Google email not verified')
    sub = info.get('sub')
    if not sub:
        raise HTTPException(status_code=401, detail='Invalid Google token')
    now = datetime.datetime.utcnow()
    users_col.update_one(
        {'google_sub': sub},
        {'$set': {'email': (info.get('email') or '').lower(), 'name': info.get('name'),
                  'picture': info.get('picture'), 'updated_at': now},
         '$setOnInsert': {'_id': str(uuid.uuid4()), 'google_sub': sub, 'created_at': now}},
        upsert=True)
    user = users_col.find_one({'google_sub': sub})
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expires = now + datetime.timedelta(days=AUTH_SESSION_DAYS)
    auth_sessions_col.insert_one({'_id': str(uuid.uuid4()), 'token': token,
                                  'user_id': user['_id'], 'created_at': now,
                                  'expires_at': expires})
    resp = JSONResponse({'user': {'id': user['_id'], 'email': user.get('email'),
                                  'name': user.get('name'), 'picture': user.get('picture')}})
    resp.set_cookie(AUTH_COOKIE, token, max_age=AUTH_SESSION_DAYS * 86400,
                    httponly=True, secure=True, samesite='lax', path='/')
    return resp


@app.get('/api/auth/me')
def auth_me(user: dict = Depends(get_current_user)):
    return {'id': user['_id'], 'email': user.get('email'),
            'name': user.get('name'), 'picture': user.get('picture')}


@app.get('/api/auth/config')
def auth_config():
    """Public: tells the frontend whether Google sign-in is configured + the client id."""
    return {'configured': bool(GOOGLE_CLIENT_ID), 'client_id': GOOGLE_CLIENT_ID}


@app.post('/api/auth/logout')
def auth_logout(albert_session: str = Cookie(default=None, alias=AUTH_COOKIE)):
    if albert_session:
        try:
            auth_sessions_col.delete_one({'token': albert_session})
        except Exception:  # noqa
            pass
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(AUTH_COOKIE, path='/')
    return resp




def build_chat_context(symbol='BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cd = coin_dash_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
        run = (cd or {}).get('data')
        cn = coin_news_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
        news = (cn or {}).get('doc')
        label = (run or {}).get('coin_name', symbol)
        sym = symbol
    else:
        run = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
        news = news_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
        label = 'Bitcoin'
        sym = 'BTC'
    if not run:
        return 'No dashboard data is available yet.'
    dec = run.get('decision') or {}
    L = []
    if sym != 'BTC':
        L.append(f"IMPORTANT: The asset in focus is {label} ({sym}/USD), an altcoin — NOT Bitcoin. Talk about {label} throughout and ignore Bitcoin-only concepts (halving cycle, BTC dominance) which do not apply here.")
    L.append(f"As of {run.get('as_of')}: {sym}/USD last close ${run.get('last_close')} ({run.get('day_change_pct')}% on the day), data source {run.get('data_source')}.")
    L.append(f"{label} Quant Score {run.get('quant_score')}/100 ({run.get('quant_label')}). Next-day model signal: {run.get('signal')} at {run.get('confidence')}% confidence.")
    L.append(f"Market regime: {run['regime']['regime']} — {run['regime']['description']} (30d trend {run['regime'].get('trend30d_pct')}%, volatility {run['regime'].get('vol_percentile')}th percentile).")
    if dec:
        L.append(f"Unified Decision Engine: overall {dec.get('overall_score')}/100 ({dec.get('label')}), risk level {dec.get('risk_level')}, signal alignment: {dec.get('alignment')}.")
        L.append("Decision summary: " + dec.get('summary', ''))
    for f in run.get('forecasts', []):
        h = f.get('higher_adj', f['higher'])
        nl = f.get('news_link')
        extra = f" (news-adjusted from {nl['higher_base']}%)" if nl else ''
        L.append(f"{f['horizon']} forecast: {h}% higher / {round(100 - h, 1)}% lower{extra}, confidence {f['confidence']}, backtest accuracy {f['accuracy']}%. Scenarios — Bull ${f['bull']} / Base ${f['base']} / Bear ${f['bear']}. Invalidated {f['invalidation_dir']} ${f['invalidation']}.")
    for o in run.get('long_outlook', []):
        L.append(f"{o['horizon']} outlook: {o['higher']}% higher, base ${o['base']} (bull ${o['bull']} / bear ${o['bear']}).")
    L.append("Top bullish factors: " + " | ".join(run['factors']['bullish']))
    L.append("Top risk factors: " + " | ".join(run['factors']['risk']))
    if run.get('policy'):
        p = run['policy']
        L.append(f"Policy & Liquidity Score {p['score']}/100 ({p['label']}); Global Liquidity Impulse {p['liquidity_impulse']}/100 ({p['liquidity_state']}). DXY {p['dxy']}, 10Y yield {p['y10']}%, VIX {p['vix']}.")
    if run.get('dominance'):
        dm = run['dominance']
        L.append(f"BTC dominance {dm['dominance']}% ({dm['direction']}), total crypto market cap ${dm['total_mcap_t']}T. {dm['interpretation']}")
    if run.get('cycle'):
        cy = run['cycle']
        L.append(f"Halving cycle: {cy['cycle_progress_pct']}% through, phase '{cy['phase']}', {cy['days_since_halving']} days since the {cy['last_halving_date']} halving, block reward {cy['reward']} BTC.")
    if run.get('chart'):
        ch = run['chart']
        L.append(f"Chart structure: {ch['structure']} ({ch['structure_bias']}). {ch['predictive']['primary_setup']}")
    if run.get('scoreboard'):
        sb = run['scoreboard']
        L.append(f"Backtest scoreboard: {sb['winRate']}% win rate over {sb['total']} graded predictions ({sb['wins']} wins / {sb['losses']} losses).")
    if news:
        b = news.get('briefing', {})
        L.append(f"News briefing: bias {b.get('bias')}, {b.get('total')} stories, {b.get('major_stories')} high-impact. Top tailwind: {b.get('top_tailwind')}. Top risk: {b.get('top_risk')}.")
        for c in sorted(news.get('cards', []), key=lambda z: -z.get('impact', 0))[:3]:
            L.append(f"News [impact {c.get('impact')}]: {c.get('title')} — {(c.get('ai') or {}).get('direction')}.")
    if sym == 'BTC':
        feeds = _global_market_feeds()
        if feeds:
            L.append(feeds)
    return "\n".join(L)


def _global_market_feeds():
    """Compact block of ALWAYS-ON live feeds (ETF flows, derivatives, on-chain,
    cross-asset, sentiment) so Albert has this context on every screen and stops
    saying 'no data' when the data actually exists. Every branch is guarded."""
    L = ['GLOBAL MARKET FEEDS (live, cite exact numbers when present):']
    # --- Spot ETF net flows ---
    try:
        ef = get_etf_flows() or {}
        daily = ef.get('daily') or []
        totals = [x.get('total') for x in daily if x.get('total') is not None]
        if totals:
            L.append(f"- US spot BTC ETF net flow: 1d ${round(totals[0])}M, 7d ${round(sum(totals[:7]))}M, cumulative since launch ${round((ef.get('cum_total') or 0))}M.")
    except Exception:  # noqa
        pass
    # --- Derivatives: funding / OI / positioning ---
    try:
        d = get_leverage('4H') or {}
        oi = d.get('open_interest') or {}
        fu = d.get('funding') or {}
        sm = d.get('summary') or {}
        parts = []
        if fu:
            parts.append(f"funding {fu.get('rate')}% ({fu.get('direction')}, bias {fu.get('bias')})")
        if oi:
            parts.append(f"open interest {_fmt_usd(oi.get('value_usd'))} ({oi.get('state')}, {oi.get('change_tf_pct')}% this TF)")
        if sm:
            parts.append(f"leverage pressure {sm.get('pressure')} ({sm.get('pressure_score')}/100)")
        if parts:
            L.append('- Derivatives (OKX 4H): ' + ', '.join(parts) + '.')
    except Exception:  # noqa
        pass
    # --- On-chain structure (institutional + smart-money panels) ---
    try:
        panels = get_onchain_panels('BTC') or {}
        for key, tag in (('smart_money', 'Smart money'), ('institutional', 'Institutional')):
            panel = panels.get(key) or {}
            mets = panel.get('metrics') or []
            picked = [m for m in mets if m.get('value') not in (None, 'n/a', '')][:4]
            if picked:
                L.append(f"- {tag} on-chain: " + '; '.join(f"{m.get('name')} {m.get('value')} [{m.get('signal')}]" for m in picked) + '.')
    except Exception:  # noqa
        pass
    # --- Cross-asset context ---
    try:
        xa = _misc_get('cross_asset', 15 * 60, _compute_cross_asset) or {}
        if xa.get('btc_dominance'):
            L.append(f"- Cross-asset: BTC dominance {xa.get('btc_dominance')}%, ETH/BTC {xa.get('eth_btc')}, total mcap ${round((xa.get('total_market_cap_usd') or 0)/1e9)}B, regime {xa.get('regime')}.")
    except Exception:  # noqa
        pass
    # --- Sentiment ---
    try:
        fg = _misc_get('fear_greed', 30 * 60, compute_fear_greed) or {}
        if fg.get('value') is not None:
            L.append(f"- Fear & Greed: {fg.get('value')} ({fg.get('label')}); 1w ago {fg.get('week_ago')}, 1m ago {fg.get('month_ago')}.")
    except Exception:  # noqa
        pass
    return ('\n'.join(L)) if len(L) > 1 else ''


# =====================================================================
# DATA TRUST LAYER  +  PREDICTION LEDGER  +  EVENT CALENDAR
# =====================================================================
def _age_min(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace('Z', ''))
        return max(0.0, (datetime.datetime.utcnow() - t).total_seconds() / 60.0)
    except Exception:  # noqa
        return None


def _feed_iso(col, _id):
    """Return (iso_timestamp, exists) for a cache doc using its real fetched_at/fetched_ts."""
    try:
        d = col.find_one({'_id': _id}, {'fetched_ts': 1, 'fetched_at': 1})
        if not d:
            return None, False
        if d.get('fetched_at'):
            return d['fetched_at'], True
        ts = d.get('fetched_ts')
        if ts:
            return datetime.datetime.utcfromtimestamp(float(ts)).isoformat(), True
        return None, True
    except Exception:  # noqa
        return None, False


def compute_data_health(source, crossmarket, policy, dominance, news_doc, core_iso=None):
    now_iso = datetime.datetime.utcnow().isoformat()
    core_iso = core_iso or now_iso  # when the core feeds were actually refreshed (last run)
    feeds = []

    def add(fid, label, provider, ok, updated_iso, fresh_min, methodology, core=True):
        age = _age_min(updated_iso) if updated_iso else None
        if not ok:
            status, conf = 'down', 10
        elif age is None:
            status, conf = 'live', 95
        elif age <= fresh_min:
            status, conf = 'live', 97
        elif age <= fresh_min * 3:
            status, conf = 'degraded', 72
        else:
            status, conf = 'stale', 42
        feeds.append({'id': fid, 'label': label, 'provider': provider, 'status': status,
                      'updated': updated_iso, 'age_min': round(age) if age is not None else None,
                      'confidence': conf, 'methodology': methodology, 'core': core})

    add('price', 'Spot & OHLCV Price', (source or 'kraken').title(), True, core_iso, 1560,
        'Daily OHLCV via ccxt; live spot via exchange ticker (polled every ~10s).')
    add('dominance', 'BTC Dominance & Market Cap', 'CoinGecko', dominance is not None, core_iso, 1560,
        'Global market-cap share and total market cap from the CoinGecko public API.')
    add('crossmarket', 'Cross-Market (DXY, Yields, VIX, Gold, S&P)', 'Yahoo Finance',
        crossmarket is not None, core_iso, 1560, 'Daily closes for macro assets; rolling correlations vs BTC.')
    add('policy', 'Macro & Policy', 'Curated + Yahoo Finance', policy is not None, core_iso, 1560,
        'Rate/liquidity proxies plus a curated policy & regulation calendar.')
    add('news', 'Bitcoin News & AI Impact', 'RSS + Gemini',
        news_doc is not None, (news_doc or {}).get('created_at'), 180,
        'Keyless RSS feeds clustered and scored for impact/direction by Gemini.')
    add('fx', 'USD → AUD FX', 'Yahoo Finance', True, core_iso, 1800,
        'AUD=X spot rate used to convert USD prices into AUD.')

    # --- Auxiliary feeds (real cache timestamps; informational, not part of odds-fade) ---
    etf_iso, etf_ok = _feed_iso(etf_col, 'btc')
    add('etf', 'US Spot ETF Net Flows', 'Farside (tftc.io / bitbo)', etf_ok and etf_iso is not None,
        etf_iso, 4320,
        'Daily US spot BTC ETF net flows. Publishes only on US market days — weekend/holiday gaps are expected.',
        core=False)
    oc_iso, oc_ok = _feed_iso(onchain_col, 'btc')
    add('onchain', 'On-Chain (MVRV / SOPR / holder proxies)', 'Glassnode / keyless', oc_ok, oc_iso, 1440,
        'On-chain cost-basis and holder-behaviour metrics; refreshed daily.', core=False)
    lev_iso, lev_ok = _feed_iso(lev_col, 'BTC:4H')
    add('leverage', 'Derivatives & Leverage (OI / funding)', 'OKX', lev_ok, lev_iso, 720,
        'Open interest, funding and long/short positioning from OKX (4H).', core=False)
    fg_iso, fg_ok = _feed_iso(misc_col, 'fear_greed')
    add('sentiment', 'Fear & Greed Index', 'alternative.me', fg_ok, fg_iso, 1440,
        'Crowd sentiment 0-100 from the alternative.me Fear & Greed index.', core=False)

    # Odds-fade + headline score are driven by the CORE feeds only (unchanged behaviour).
    core_feeds = [f for f in feeds if f.get('core')]
    conf_vals = [f['confidence'] for f in core_feeds]
    score = int(round(sum(conf_vals) / len(conf_vals)))
    live = sum(1 for f in core_feeds if f['status'] == 'live')
    degraded = sum(1 for f in core_feeds if f['status'] == 'degraded')
    stale = sum(1 for f in core_feeds if f['status'] in ('stale', 'down'))
    # Auxiliary feed rollup (surfaced but non-fading).
    aux_feeds = [f for f in feeds if not f.get('core')]
    aux_issues = [f['label'] for f in aux_feeds if f['status'] in ('stale', 'down')]
    level = 'High' if score >= 90 else 'Good' if score >= 75 else 'Degraded' if score >= 55 else 'Low'
    faded = stale > 0 or score < 70
    if stale == 0 and degraded == 0:
        note = 'All core data feeds are live and fresh — full model confidence.'
    elif faded:
        note = f'{stale} core feed(s) stale/down, {degraded} degraded — odds are faded and confidence reduced.'
    else:
        note = f'{degraded} core feed(s) slightly delayed — minor confidence reduction.'
    if aux_issues:
        note += f' Auxiliary data unavailable: {", ".join(aux_issues)}.'
    return {'feeds': feeds, 'score': score, 'level': level, 'live': live, 'degraded': degraded,
            'stale': stale, 'faded': faded, 'note': note, 'checked_at': now_iso,
            'aux_issues': aux_issues}


def apply_data_fade(decision, health):
    """When a live feed goes stale, fade the directional odds toward 50% and flag it."""
    if not decision or not health:
        return
    faded = health['faded']
    tf = max(0.35, health['score'] / 100.0)
    decision['data_trust'] = {'score': health['score'], 'level': health['level'], 'faded': faded}
    decision['odds_faded'] = faded
    if not faded:
        return
    for o in decision.get('outlook', []):
        h = o['higher']
        nh = round(50 + (h - 50) * tf, 1)
        o['higher'], o['lower'] = nh, round(100 - nh, 1)
        o['lean'] = 'UP' if nh >= 50 else 'DOWN'
        o['faded'] = True


# ---------------------------- Prediction Ledger ----------------------------
HZ_DAYS = {'24H': 1, '7D': 7, '30D': 30, '3M': 90, '6M': 180, '1Y': 365}


def _vol_label(f):
    try:
        spread = abs(f['bull'] - f['bear']) / max(1e-9, f['base'])
    except Exception:  # noqa
        return 'Elevated'
    return 'Very High' if spread > 0.6 else 'High' if spread > 0.3 else 'Elevated' if spread > 0.12 else 'Low'


def record_predictions(as_of, price_now, all_outlook, regime, source, model_version='rf-quant-v1', trigger='scheduled'):
    """Immutably log every horizon forecast BEFORE the outcome is known (idempotent per as_of+horizon)."""
    for f in all_outlook:
        hz = f['horizon']
        days = HZ_DAYS.get(hz)
        if not days:
            continue
        higher = float(f.get('higher_adj', f['higher']))
        key = f"{as_of}_{hz}"
        doc = {
            '_id': key, 'model_version': model_version, 'trigger': trigger,
            'as_of': as_of, 'issued_at': datetime.datetime.utcnow().isoformat(),
            'horizon': hz, 'horizon_days': days, 'target_date': f.get('expiry'),
            'price_at_issue': round(float(price_now), 2), 'data_source': source,
            'direction': 'UP' if higher >= 50 else 'DOWN',
            'prob_higher': round(higher, 1), 'prob_lower': round(100 - higher, 1),
            'base': f.get('base'), 'bull': f.get('bull'), 'bear': f.get('bear'),
            'confidence': f.get('confidence'), 'confidence_pct': f.get('confidence_pct'), 'regime': regime,
            'expected_volatility': _vol_label(f),
            'resolved': False, 'actual_close': None, 'actual_direction': None,
            'correct': None, 'brier': None, 'abs_pct_error': None, 'range_hit': None,
        }
        try:
            predictions_col.update_one({'_id': key}, {'$setOnInsert': doc}, upsert=True)
        except Exception:  # noqa
            traceback.print_exc()


def seed_ledger_from_backtest(trades):
    """Bootstrap the 24H ledger from the real walk-forward backtest (trigger='backtest')."""
    try:
        existing = {d['_id'] for d in predictions_col.find({'trigger': 'backtest'}, {'_id': 1})}
        new_docs = []
        for t in trades:
            key = f"bt_{t['date']}_24H"
            if key in existing:
                continue
            prob = t['confidence'] if t['signal'] == 'UP' else (100 - t['confidence'])
            actual_up = 1 if t['actual'] == 'UP' else 0
            new_docs.append({
                '_id': key, 'model_version': 'rf-quant-v1', 'trigger': 'backtest',
                'as_of': t['date'], 'issued_at': t['date'], 'horizon': '24H', 'horizon_days': 1,
                'target_date': None, 'price_at_issue': t['close'], 'data_source': 'backtest',
                'direction': t['signal'], 'prob_higher': round(prob, 1), 'prob_lower': round(100 - prob, 1),
                'base': t['nextClose'], 'bull': None, 'bear': None, 'confidence': None, 'regime': None,
                'expected_volatility': None, 'resolved': True,
                'resolved_at': t['date'], 'actual_close': t['nextClose'], 'actual_direction': t['actual'],
                'correct': bool(t['correct']), 'brier': round((prob / 100 - actual_up) ** 2, 4),
                'abs_pct_error': None, 'range_hit': None,
            })
        if new_docs:
            predictions_col.insert_many(new_docs, ordered=False)
    except Exception:  # noqa
        traceback.print_exc()


def resolve_predictions(close_by_date, latest_date):
    """Grade any matured forward predictions against the actual close."""
    try:
        latest = datetime.datetime.strptime(latest_date, '%Y-%m-%d').date()
    except Exception:  # noqa
        return
    dates_sorted = sorted(close_by_date.keys())
    for p in list(predictions_col.find({'resolved': False})):
        td = p.get('target_date')
        if not td:
            continue
        try:
            tdd = datetime.datetime.strptime(td, '%Y-%m-%d').date()
        except Exception:  # noqa
            continue
        if tdd > latest:
            continue
        ac = close_by_date.get(td)
        if ac is None:
            fwd = [d for d in dates_sorted if d >= td]
            ac = close_by_date[fwd[0]] if fwd else close_by_date[dates_sorted[-1]]
        pi = p['price_at_issue']
        actual_dir = 'UP' if ac > pi else 'DOWN'
        prob = p['prob_higher'] / 100.0
        actual_up = 1 if ac > pi else 0
        base = p.get('base') or pi
        rng_hit = None
        if p.get('bear') and p.get('bull'):
            rng_hit = bool(p['bear'] <= ac <= p['bull'])
        predictions_col.update_one({'_id': p['_id']}, {'$set': {
            'resolved': True, 'resolved_at': datetime.datetime.utcnow().isoformat(),
            'actual_close': round(ac, 2), 'actual_direction': actual_dir,
            'correct': (p['direction'] == actual_dir),
            'brier': round((prob - actual_up) ** 2, 4),
            'abs_pct_error': round(abs(base - ac) / ac * 100, 2) if ac else None,
            'range_hit': rng_hit,
        }})


def compute_scorecard():
    resolved = list(predictions_col.find({'resolved': True}, {'_id': 0}))

    def agg(items):
        n = len(items)
        if not n:
            return None
        acc = round(sum(1 for x in items if x.get('correct')) / n * 100, 1)
        briers = [x['brier'] for x in items if x.get('brier') is not None]
        maes = [x['abs_pct_error'] for x in items if x.get('abs_pct_error') is not None]
        rngs = [x['range_hit'] for x in items if x.get('range_hit') is not None]
        return {
            'n': n, 'accuracy': acc,
            'brier': round(sum(briers) / len(briers), 4) if briers else None,
            'mae_pct': round(sum(maes) / len(maes), 2) if maes else None,
            'range_hit_pct': round(sum(1 for r in rngs if r) / len(rngs) * 100, 1) if rngs else None,
        }

    overall = agg(resolved) or {'n': 0, 'accuracy': None, 'brier': None, 'mae_pct': None, 'range_hit_pct': None}
    by_h = {}
    for hz in ['24H', '7D', '30D', '3M', '6M', '1Y']:
        a = agg([x for x in resolved if x.get('horizon') == hz])
        if a:
            # Ensemble weighting: down-weight a horizon whose Brier drifts past the 0.24
            # decay threshold (0.25 = coin flip). Weight falls linearly 1.0 -> 0.3 over
            # Brier 0.24 -> 0.36, so decaying models quietly step aside in the blend.
            br = a.get('brier')
            if br is None:
                a['ensemble_weight'], a['decaying'] = 1.0, False
            elif br <= 0.24:
                a['ensemble_weight'], a['decaying'] = 1.0, False
            else:
                w = max(0.3, 1.0 - (br - 0.24) / 0.12 * 0.7)
                a['ensemble_weight'], a['decaying'] = round(w, 3), True
            by_h[hz] = a
    # probability calibration (predicted higher% vs realised up-rate)
    calib = []
    for lo, hi in [(0, 40), (40, 50), (50, 60), (60, 100)]:
        bucket = [x for x in resolved if lo <= x.get('prob_higher', 0) < hi]
        if bucket:
            realised = round(sum(1 for x in bucket if x.get('actual_direction') == 'UP') / len(bucket) * 100, 1)
            calib.append({'bucket': f'{lo}-{hi}%', 'n': len(bucket),
                          'avg_pred': round(sum(x['prob_higher'] for x in bucket) / len(bucket), 1),
                          'realised_up': realised})
    pending = list(predictions_col.find(
        {'resolved': False, 'trigger': {'$ne': 'backtest'}}, {'_id': 0}).sort('target_date', 1))

    # Ensure every open forecast has a directional-confidence label + percentage so the
    # UI can render a badge + number even for docs logged before confidence_pct existed.
    def _conf_from_prob(prob_higher):
        margin = abs(float(prob_higher) - 50.0) / 50.0        # 0..1
        pct = round(min(100.0, margin * 100.0))
        label = 'High' if margin > 0.45 else ('Moderate' if margin > 0.2 else 'Low')
        return label, pct

    for p in pending:
        cp = p.get('confidence_pct')
        cl = p.get('confidence')
        if cp is None:
            # Legacy doc logged before confidence_pct existed — derive both from the
            # directional probability so the badge and percentage always agree.
            fb_label, fb_pct = _conf_from_prob(p.get('prob_higher', 50))
            p['confidence_pct'] = fb_pct
            p['confidence'] = fb_label
        elif cl is None:
            fb_label, _ = _conf_from_prob(p.get('prob_higher', 50))
            p['confidence'] = fb_label

    recent = sorted([x for x in resolved if x.get('trigger') != 'backtest'],
                    key=lambda z: z.get('resolved_at', ''), reverse=True)[:15]

    # Performance grouped by market regime (real resolved forecasts that carry a regime)
    by_regime = {}
    regimes = set(x.get('regime') for x in resolved if x.get('regime'))
    for rg in regimes:
        a = agg([x for x in resolved if x.get('regime') == rg])
        if a:
            by_regime[rg] = a

    # Filterable ledger: every open forecast + resolved live + a capped slice of backtested,
    # each normalised with the fields the UI filters on. Nothing is deleted or hidden.
    def _norm(x):
        return {
            'issued_date': x.get('as_of'), 'horizon': x.get('horizon'),
            'price_at_issue': x.get('price_at_issue'),
            'base': x.get('base'), 'bull': x.get('bull'), 'bear': x.get('bear'),
            'prob_higher': x.get('prob_higher'), 'prob_lower': x.get('prob_lower'),
            'direction': x.get('direction'),
            'confidence': x.get('confidence'), 'confidence_pct': x.get('confidence_pct'),
            'model_version': x.get('model_version'), 'trigger': x.get('trigger'),
            'regime': x.get('regime'), 'target_date': x.get('target_date'),
            'actual_close': x.get('actual_close'), 'actual_direction': x.get('actual_direction'),
            'correct': x.get('correct'), 'abs_pct_error': x.get('abs_pct_error'),
            'range_hit': x.get('range_hit'), 'resolved': x.get('resolved'),
        }
    resolved_live = sorted([x for x in resolved if x.get('trigger') != 'backtest'],
                           key=lambda z: z.get('resolved_at', ''), reverse=True)
    resolved_bt = sorted([x for x in resolved if x.get('trigger') == 'backtest'],
                         key=lambda z: z.get('as_of', ''), reverse=True)[:150]
    ledger = [_norm(p) for p in pending] + [_norm(x) for x in resolved_live] + [_norm(x) for x in resolved_bt]

    # --- Model Reliability: fine-grained calibration curve + Brier skill + ECE ---
    reliability = None
    try:
        graded = [x for x in resolved if x.get('prob_higher') is not None
                  and x.get('actual_direction') in ('UP', 'DOWN')]
        if graded:
            total = len(graded)
            bins, ece = [], 0.0
            for lo in range(0, 100, 10):
                hi = lo + 10
                upper = hi if hi < 100 else 100.01
                b = [x for x in graded if lo <= x['prob_higher'] < upper]
                if len(b) >= 3:
                    avg_pred = sum(x['prob_higher'] for x in b) / len(b)
                    realised = sum(1 for x in b if x['actual_direction'] == 'UP') / len(b) * 100
                    bins.append({'bin': f'{lo}-{hi}', 'avg_pred': round(avg_pred, 1),
                                 'realised_up': round(realised, 1), 'n': len(b)})
                    ece += (len(b) / total) * abs(avg_pred - realised)
            br = overall.get('brier')
            reliability = {
                'n': total,
                'brier': br,
                'brier_baseline': 0.25,   # a random 50/50 coin flip
                'brier_skill': round(1 - br / 0.25, 3) if br is not None else None,
                'ece': round(ece, 2),     # expected calibration error (percentage points)
                'curve': bins,
                'grade': ('Well calibrated' if ece < 6 else 'Fairly calibrated' if ece < 12
                          else 'Poorly calibrated') if bins else None,
            }
    except Exception:  # noqa
        traceback.print_exc()

    return {
        'overall': overall, 'by_horizon': by_h, 'by_regime': by_regime, 'calibration': calib,
        'reliability': reliability,
        'pending': pending[:24], 'recent': recent, 'ledger': ledger,
        'total_logged': predictions_col.count_documents({}),
        'live_logged': predictions_col.count_documents({'trigger': {'$ne': 'backtest'}}),
        'backtested': predictions_col.count_documents({'trigger': 'backtest'}),
        'model_version': 'rf-quant-v1',
    }


# ---------------------------- Event Calendar ----------------------------
FOMC_DATES = ['2026-01-28', '2026-03-18', '2026-04-29', '2026-06-17', '2026-07-29',
              '2026-09-16', '2026-10-28', '2026-12-09',
              '2027-01-27', '2027-03-17', '2027-04-28', '2027-06-16']


def compute_event_calendar(cycle, policy, window=120):
    import calendar as _cal
    today = datetime.datetime.utcnow().date()
    end = today + datetime.timedelta(days=window)
    ev = []

    def add(d, cat, title, desc, imp, vol):
        dd = datetime.datetime.strptime(d, '%Y-%m-%d').date() if isinstance(d, str) else d
        ev.append({'date': dd.strftime('%Y-%m-%d'), 'days_until': (dd - today).days,
                   'category': cat, 'title': title, 'description': desc,
                   'importance': imp, 'expected_volatility': vol})

    y, m = today.year, today.month
    for _ in range(6):
        d1 = datetime.date(y, m, 1)
        first_fri = d1 + datetime.timedelta(days=(4 - d1.weekday()) % 7)
        add(first_fri, 'Macro', 'US Nonfarm Payrolls',
            'Monthly US jobs report; moves rate expectations and risk appetite.', 'High', 'Elevated')
        try:
            add(datetime.date(y, m, 12), 'Macro', 'US CPI Inflation (approx.)',
                'Monthly inflation print — a strong driver of rate expectations and BTC.', 'Very High', 'High')
        except Exception:  # noqa
            pass
        last_day = _cal.monthrange(y, m)[1]
        dl = datetime.date(y, m, last_day)
        last_fri = dl - datetime.timedelta(days=(dl.weekday() - 4) % 7)
        if m in (3, 6, 9, 12):
            add(last_fri, 'Derivatives', 'Quarterly Futures & Options Expiry',
                'Large CME/Deribit quarterly expiry; elevated pinning and volatility.', 'High', 'High')
        else:
            add(last_fri, 'Derivatives', 'Monthly Options & Futures Expiry',
                'Monthly BTC options/futures expiry; short-term volatility.', 'Medium', 'Elevated')
        m += 1
        if m > 12:
            m = 1
            y += 1

    for f in FOMC_DATES:
        fd = datetime.datetime.strptime(f, '%Y-%m-%d').date()
        if today <= fd <= end:
            add(f, 'Macro', 'FOMC Rate Decision',
                'US Federal Reserve interest-rate decision & guidance — top-tier macro catalyst.',
                'Very High', 'Very High')

    anchor = datetime.date(2026, 1, 7)
    k = 0
    while k < 400:
        dd = anchor + datetime.timedelta(days=14 * k)
        k += 1
        if dd > end:
            break
        if dd < today:
            continue
        add(dd, 'On-Chain', 'Bitcoin Difficulty Adjustment',
            'Network retargets mining difficulty (~every 2 weeks); minor direct impact.', 'Low', 'Low')

    ev = [e for e in ev if 0 <= e['days_until'] <= window]
    ev.sort(key=lambda z: z['date'])
    nxt = next((e for e in ev if e['importance'] in ('Very High', 'High')), None)
    counts = {}
    for e in ev:
        counts[e['category']] = counts.get(e['category'], 0) + 1
    return {'events': ev, 'window_days': window, 'next_high_impact': nxt,
            'counts': counts, 'generated': today.strftime('%Y-%m-%d')}


# ---------------------------- CryptoMarkAI Engine ----------------------------
BM_WEIGHTS = {
    '1W': [('Price & Technicals', 30), ('Momentum & Trend', 25), ('Volatility', 15), ('News & Sentiment', 13), ('Market Regime', 10), ('Macro & Policy', 5), ('Halving Cycle', 2)],
    '1M': [('Price & Technicals', 22), ('Momentum & Trend', 20), ('News & Sentiment', 13), ('Market Regime', 12), ('Macro & Policy', 12), ('Volatility', 10), ('Halving Cycle', 7), ('Dominance & Flows', 4)],
    '3M': [('Halving Cycle', 20), ('Macro & Policy', 18), ('Momentum & Trend', 15), ('Price & Technicals', 13), ('Market Regime', 12), ('Volatility', 8), ('News & Sentiment', 8), ('Dominance & Flows', 6)],
    '6M': [('Halving Cycle', 28), ('Macro & Policy', 22), ('Momentum & Trend', 10), ('Market Regime', 10), ('Price & Technicals', 10), ('Dominance & Flows', 8), ('Volatility', 7), ('News & Sentiment', 5)],
    '1Y': [('Halving Cycle', 38), ('Macro & Policy', 22), ('Dominance & Flows', 10), ('Volatility', 8), ('Price & Technicals', 6), ('Momentum & Trend', 6), ('Market Regime', 6), ('News & Sentiment', 4)],
    '2Y': [('Halving Cycle', 45), ('Macro & Policy', 25), ('Adoption & Liquidity', 20), ('Dominance & Flows', 10)],
    '5Y': [('Adoption & Liquidity', 45), ('Halving Cycle', 25), ('Macro & Policy', 20), ('Dominance & Flows', 10)],
}
BM_LABEL = {'1W': 'Next Week', '1M': 'Next Month', '3M': 'Next 3 Months', '6M': 'Next 6 Months',
            '1Y': 'Next Year', '2Y': 'Next 2 Years', '5Y': 'Next 5 Years'}


def _bm_model_horizon(code, f, price, tp, tr, issued, next_upd):
    higher = float(f.get('higher_adj', f['higher']))
    base, bull, bear = f['base'], f['bull'], f['bear']
    spread = max(1.0, bull - bear)
    base_low, base_high = round(base - 0.15 * spread), round(base + 0.15 * spread)
    return {'horizon': code, 'label': BM_LABEL[code], 'type': 'model', 'current_price': round(price, 2),
            'prob_above': round(higher, 1), 'prob_below': round(100 - higher, 1),
            'base_low': base_low, 'base_high': base_high,
            'bull_low': base_high, 'bull_high': round(bull),
            'bear_low': round(bear), 'bear_high': base_low,
            'expected_volatility': _vol_label(f), 'model_confidence': f.get('confidence', 'Low'),
            'accuracy': f.get('accuracy'), 'top_positive': tp, 'top_risk': tr,
            'weighting': [{'category': c, 'weight': w} for c, w in BM_WEIGHTS[code]],
            'issued': issued, 'next_update': next_upd}


def _bm_scenario_horizon(code, price, years, issued, next_upd):
    scen = [
        ('Adoption Expansion', {2: (1.6, 2.6), 5: (3.0, 9.0)}, 30, 'Accelerating institutional & sovereign adoption plus easing global liquidity.'),
        ('Base Adoption', {2: (1.25, 1.7), 5: (1.8, 3.5)}, 40, 'Steady adoption growth roughly tracking prior post-halving cycles.'),
        ('Restrictive Policy', {2: (0.75, 1.05), 5: (0.9, 1.6)}, 20, 'Tight liquidity, higher-for-longer rates and heavier regulation.'),
        ('Severe Disruption', {2: (0.35, 0.65), 5: (0.5, 1.1)}, 10, 'A major shock — regulatory ban, systemic failure or a liquidity crisis.'),
    ]
    scenarios = []
    for name, mult, prob, note in scen:
        lo, hi = mult[years]
        scenarios.append({'name': name, 'prob': prob, 'low': round(price * lo), 'high': round(price * hi), 'note': note})
    prob_above = sum(s['prob'] for s in scenarios if s['low'] >= price) + \
        sum(s['prob'] * 0.5 for s in scenarios if s['low'] < price <= s['high'])
    prob_above = round(min(95, max(5, prob_above)))
    return {'horizon': code, 'label': BM_LABEL[code], 'type': 'scenario', 'current_price': round(price, 2),
            'prob_above': prob_above, 'prob_below': 100 - prob_above,
            'expected_volatility': 'Very High', 'model_confidence': 'Low' if years == 2 else 'Very Low',
            'scenarios': scenarios,
            'top_positive': 'Post-halving supply squeeze meeting sustained adoption demand.',
            'top_risk': 'Long-range regulatory and macro-liquidity uncertainty widens the range.',
            'weighting': [{'category': c, 'weight': w} for c, w in BM_WEIGHTS[code]],
            'issued': issued, 'next_update': next_upd}


def compute_bitmark(quant, cycle, price, trigger='scheduled'):
    now = datetime.datetime.utcnow()
    issued = now.strftime('%Y-%m-%d')
    next_upd = (now + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    idx = {f['horizon']: f for f in (quant['forecasts'] + quant.get('long_outlook', []))}
    bulls, risks = quant['factors']['bullish'], quant['factors']['risk']
    tp = bulls[0] if bulls else 'Constructive technical structure.'
    tr = risks[0] if risks else 'Elevated near-term volatility.'
    horizons = []
    for code, src in [('1W', '7D'), ('1M', '30D'), ('3M', '3M'), ('6M', '6M'), ('1Y', '1Y')]:
        f = idx.get(src)
        if f:
            horizons.append(_bm_model_horizon(code, f, price, tp, tr, issued, next_upd))
    horizons.append(_bm_scenario_horizon('2Y', price, 2, issued, next_upd))
    horizons.append(_bm_scenario_horizon('5Y', price, 5, issued, next_upd))

    prev = bitmark_col.find_one(sort=[('created_at', -1)])
    changes, change_text = None, None
    if prev:
        pmap = {h['horizon']: h for h in prev.get('horizons', [])}
        chlist = []
        for h in horizons:
            ph = pmap.get(h['horizon'])
            if not ph:
                continue
            d = round(h['prob_above'] - ph.get('prob_above', h['prob_above']), 1)
            if abs(d) >= 0.5:
                chlist.append({'horizon': h['horizon'], 'prob_delta': d,
                               'from': ph.get('prob_above'), 'to': h['prob_above']})
        changes = chlist
        if chlist:
            big = max(chlist, key=lambda z: abs(z['prob_delta']))
            dirw = 'increased' if big['prob_delta'] > 0 else 'decreased'
            change_text = (f"The {big['horizon']} bullish probability {dirw} from {big['from']}% to "
                           f"{big['to']}%. {tp} Key offsetting risk: {tr}")
        else:
            change_text = 'No material change since the previous forecast — probabilities and ranges are broadly stable.'
    else:
        change_text = 'First CryptoMarkAI forecast recorded to the ledger.'

    snap = {'_id': str(uuid.uuid4()), 'created_at': now.isoformat(), 'trigger': trigger,
            'price': round(price, 2),
            'horizons': [{'horizon': h['horizon'], 'prob_above': h['prob_above'],
                          'confidence': h.get('model_confidence')} for h in horizons]}
    try:
        bitmark_col.insert_one(snap)
    except Exception:  # noqa
        traceback.print_exc()

    return {'model_version': 'bitmark-v1', 'trigger': trigger, 'issued': issued,
            'next_scheduled_update': next_upd, 'current_price': round(price, 2),
            'regime': quant['regime']['regime'], 'horizons': horizons,
            'changes': changes, 'change_explanation': change_text, 'generated_at': now.isoformat()}


# ---------------------------- Smart Alerts (state-change detection) ----------------------------
# Non-price, event-driven alerts triggered when the market STATE changes between runs
# (regime flips, decision-label changes, data-trust degradation, high-impact events entering
# the near window, big daily moves). Persisted + de-duplicated so users see a running feed.
_TRUST_RANK = {'High': 3, 'Good': 2, 'Degraded': 1, 'Low': 0}


def _score_band(s):
    if s is None:
        return None
    if s >= 65:
        return 'Bullish'
    if s >= 55:
        return 'Mildly Bullish'
    if s > 45:
        return 'Neutral'
    if s > 35:
        return 'Mildly Bearish'
    return 'Bearish'


# Email alerts are DISABLED — alerts are delivered via in-app bell + browser
# notifications instead. Flip to True to restore Resend email dispatch.
EMAIL_ALERTS_ENABLED = False


def push_alert(category, severity, title, message, sig, symbol='BTC', owner=None, extra=None):
    """Create an in-app notification (surfaced by the bell + browser push) for
    events that used to be emailed (drift breaker, model decay, live cascade).
    Idempotent per (day, category, sig). `owner` (optional) tags the alert with the
    user pid it belongs to (basket nudges/digests) for future per-user scoping.
    `extra` (optional) merges extra fields (e.g. an actionable 'action'/'basket_id')."""
    try:
        day = datetime.datetime.utcnow().strftime('%Y-%m-%d-%H')
        key = f"notif_{day}_{category}_{sig}"
        doc = {
            '_id': key, 'id': key, 'ts': datetime.datetime.utcnow().isoformat(),
            'as_of': day, 'symbol': (symbol or 'BTC').upper(), 'category': category, 'severity': severity,
            'title': title, 'message': message, 'seen': False,
        }
        if owner:
            doc['owner'] = str(owner)[:80]
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k not in doc:
                    doc[k] = v
        res = smart_alerts_col.update_one({'_id': key}, {'$setOnInsert': doc}, upsert=True)
        return res.upserted_id is not None
    except Exception:  # noqa
        traceback.print_exc()
        return False


def compute_smart_alerts(doc, prev_doc):
    """Compare the new run against the previous run and log meaningful state changes."""
    as_of = doc.get('as_of')
    now_iso = datetime.datetime.utcnow().isoformat()
    sym = (doc.get('symbol') or 'BTC').upper()
    fired = []

    def fire(category, severity, title, message, sig):
        key = f"{as_of}_{category}_{sig}" if sym == 'BTC' else f"{sym}_{as_of}_{category}_{sig}"
        try:
            res = smart_alerts_col.update_one(
                {'_id': key},
                {'$setOnInsert': {
                    '_id': key, 'id': key, 'ts': now_iso, 'as_of': as_of, 'symbol': sym,
                    'category': category, 'severity': severity,
                    'title': title, 'message': message, 'seen': False,
                }}, upsert=True)
            if res.upserted_id is not None:
                fired.append(key)
        except Exception:  # noqa
            traceback.print_exc()

    prev = prev_doc or {}

    # 1) Regime change
    cur_regime = (doc.get('regime') or {}).get('regime')
    prev_regime = (prev.get('regime') or {}).get('regime')
    if cur_regime and prev_regime and cur_regime != prev_regime:
        _conv = (doc.get('decision') or {}).get('overall_score')
        _wmode = (doc.get('decision') or {}).get('weights_mode')
        fire('Regime', 'high', f'Regime shift → {cur_regime}',
             f'Market regime changed from "{prev_regime}" to "{cur_regime}" '
             f'(conviction {_conv}/100, {_wmode or "dynamic"} signal weighting). '
             f'{(doc.get("regime") or {}).get("behavior", "")}', cur_regime)

    # 2) Decision label change (overall market state)
    cur_dl = (doc.get('decision') or {}).get('label')
    prev_dl = (prev.get('decision') or {}).get('label')
    if cur_dl and prev_dl and cur_dl != prev_dl:
        sev = 'high' if ('Bear' in cur_dl or 'Bull' in cur_dl) else 'warning'
        fire('Market State', sev, f'Market state → {cur_dl}',
             f'Unified decision changed from "{prev_dl}" to "{cur_dl}" '
             f'(score {(doc.get("decision") or {}).get("overall_score")}/100).', cur_dl)

    # 3) Quant-score band crossing
    cur_band = _score_band(doc.get('quant_score'))
    prev_band = _score_band(prev.get('quant_score'))
    if cur_band and prev_band and cur_band != prev_band:
        fire('Quant Score', 'info', f'Quant Score band → {cur_band}',
             f'Quant Score moved from {prev.get("quant_score")} ({prev_band}) to '
             f'{doc.get("quant_score")} ({cur_band}).', cur_band)

    # 4) Data-trust degradation / recovery
    cur_tr = (doc.get('data_health') or {}).get('level')
    prev_tr = (prev.get('data_health') or {}).get('level')
    if cur_tr and prev_tr and cur_tr != prev_tr:
        worse = _TRUST_RANK.get(cur_tr, 3) < _TRUST_RANK.get(prev_tr, 3)
        fire('Data Trust', 'warning' if worse else 'success',
             f'Data trust {"degraded" if worse else "recovered"} → {cur_tr}',
             f'Feed health changed from "{prev_tr}" to "{cur_tr}". '
             f'{"Odds are being faded toward 50%." if (doc.get("data_health") or {}).get("faded") else "Full model confidence restored."}',
             cur_tr)

    # 5) High-impact event entering the near-term (<=3 days) window
    nhi = (doc.get('event_calendar') or {}).get('next_high_impact')
    if nhi and nhi.get('days_until') is not None and 0 <= nhi['days_until'] <= 3:
        fire('Event Risk', 'warning', f'{nhi.get("title")} in {nhi["days_until"]}d',
             f'{nhi.get("importance")}-importance {nhi.get("category")} event approaching '
             f'({nhi.get("expected_volatility")} expected volatility). {nhi.get("description", "")}',
             f"{nhi.get('title')}_{nhi.get('date')}")

    # 6) Large daily move
    dc = doc.get('day_change_pct')
    if dc is not None and abs(dc) >= 5.0:
        fire('Volatility', 'high' if abs(dc) >= 8 else 'warning',
             f'Large move: {"+" if dc > 0 else ""}{dc}% in 24h',
             f'Bitcoin moved {"+" if dc > 0 else ""}{dc}% over the last daily candle to '
             f'{fmt_usd_srv(doc.get("last_close"))} — elevated volatility.', f'move_{round(dc)}')

    # 7) Liquidation cascade risk — derivatives over-leveraged (funding + OI expansion)
    try:
        lev = doc.get('leverage_snapshot') or {}
        sq = lev.get('squeeze') or {}
        long_risk = sq.get('long_risk')
        short_risk = sq.get('short_risk')
        oi_chg = lev.get('oi_change_tf_pct')
        fr = lev.get('funding_rate')
        cb_sth = (doc.get('cost_basis') or {}).get('sth')
        if long_risk is not None and oi_chg is not None and long_risk >= 70 and oi_chg >= 15:
            fire('Liquidation Risk', 'high', 'Elevated long-squeeze / cascade risk',
                 f'Derivatives look over-leveraged long: squeeze risk {long_risk}/100, open interest '
                 f'+{oi_chg}% this window, funding {fr}%. A flush toward the short-term cost basis '
                 f'(~{fmt_usd_srv(cb_sth)}) could cascade.', f'cascade_long_{round(long_risk)}_{round(oi_chg)}')
        elif short_risk is not None and oi_chg is not None and short_risk >= 70 and oi_chg >= 15:
            fire('Liquidation Risk', 'high', 'Elevated short-squeeze / cascade risk',
                 f'Derivatives look over-leveraged short: squeeze risk {short_risk}/100, open interest '
                 f'+{oi_chg}% this window, funding {fr}%. A rapid move higher could force shorts to cover.',
                 f'cascade_short_{round(short_risk)}_{round(oi_chg)}')
    except Exception:  # noqa
        traceback.print_exc()

    # 8) Pivotal basis reclaim — spot crossing the short-term-holder cost basis
    try:
        cb = doc.get('cost_basis') or {}
        sth = cb.get('sth')
        cur_px = doc.get('last_close')
        prev_px = prev.get('last_close')
        if sth and cur_px is not None and prev_px is not None:
            if prev_px < sth <= cur_px:
                fire('Basis Reclaim', 'high', 'Short-term cost basis reclaimed',
                     f'Spot closed at {fmt_usd_srv(cur_px)}, reclaiming the short-term holder cost basis '
                     f'(~{fmt_usd_srv(sth)}). Intraday bull scenario activated.', f'sth_reclaim_up_{round(sth)}')
            elif prev_px >= sth > cur_px:
                fire('Basis Reclaim', 'warning', 'Short-term cost basis lost',
                     f'Spot closed at {fmt_usd_srv(cur_px)}, losing the short-term holder cost basis '
                     f'(~{fmt_usd_srv(sth)}). Momentum turning cautious.', f'sth_lose_{round(sth)}')
    except Exception:  # noqa
        traceback.print_exc()

    return {'fired': fired, 'n_fired': len(fired)}


def fmt_usd_srv(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:  # noqa
        return str(v)


def _alert_symbol_filter(symbol):
    """Build a Mongo filter for coin-scoped alerts.
    - None / 'ALL' -> every alert (no symbol constraint)
    - 'BTC'        -> BTC alerts + legacy alerts that predate the symbol field
    - other        -> that coin's alerts only
    """
    sym = (symbol or '').strip().upper()
    if not sym or sym == 'ALL':
        return {}
    if sym == 'BTC':
        return {'$or': [{'symbol': 'BTC'}, {'symbol': {'$exists': False}}, {'symbol': None}]}
    return {'symbol': sym}


def backfill_alert_symbols():
    """One-time idempotent migration: tag legacy alerts (created before the symbol
    field existed) so coin filtering stays clean. Analog/Setup alert ids encode the
    coin (analog_<date>_<SYM>_...); everything else defaults to BTC."""
    try:
        legacy = list(smart_alerts_col.find(
            {'$or': [{'symbol': {'$exists': False}}, {'symbol': None}]}, {'_id': 1, 'id': 1}))
        for a in legacy:
            aid = a.get('id') or a.get('_id') or ''
            sym = 'BTC'
            if isinstance(aid, str) and aid.startswith('analog_'):
                parts = aid.split('_')
                # analog_<YYYY-MM-DD>_<SYM>_<hash>
                if len(parts) >= 3 and parts[2].isalpha():
                    sym = parts[2].upper()
            smart_alerts_col.update_one({'_id': a['_id']}, {'$set': {'symbol': sym}})
        if legacy:
            print(f'[alerts] backfilled symbol on {len(legacy)} legacy alert(s)')
    except Exception:  # noqa
        traceback.print_exc()


try:
    backfill_alert_symbols()
except Exception:  # noqa
    pass


def get_smart_alerts(limit=50, symbol=None):
    flt = _alert_symbol_filter(symbol)
    items = list(smart_alerts_col.find(flt, {'_id': 0}).sort('ts', -1).limit(limit))
    unseen = smart_alerts_col.count_documents({**flt, 'seen': False})
    return {'alerts': items, 'unseen': unseen, 'total': smart_alerts_col.count_documents(flt)}


# ---------------------------- Time Machine (historical replay) ----------------------------
def build_replay_payload(trades, price_series):
    """Bundle the full walk-forward predictions + price path so the frontend Time Machine
    can replay any historical day (model call vs actual outcome)."""
    return {
        'series': price_series,          # [{date, close}] full history
        'trades': trades,                # [{date, signal, confidence, close, nextClose, actual, correct}]
        'min_date': trades[0]['date'] if trades else None,
        'max_date': trades[-1]['date'] if trades else None,
        'n': len(trades),
    }


def replay_for_date(target_date, window=30):
    """Return the model's as-of prediction for target_date + actual outcome + price window."""
    run = runs_col.find_one(sort=[('created_at', -1)])
    if not run or not run.get('replay'):
        return {'status': 'unavailable', 'message': 'No replay data yet — run a compute first.'}
    rp = run['replay']
    trades = rp.get('trades', [])
    series = rp.get('series', [])
    if not trades:
        return {'status': 'unavailable', 'message': 'No historical predictions available.'}
    # nearest trade at/just-before target_date
    pick = None
    for t in trades:
        if t['date'] <= target_date:
            pick = t
        else:
            break
    if pick is None:
        pick = trades[0]
    # price window around the pick date
    idx = next((i for i, s in enumerate(series) if s['date'] == pick['date']), None)
    if idx is None:
        idx = next((i for i, s in enumerate(series) if s['date'] >= pick['date']), len(series) - 1)
    lo = max(0, idx - window)
    hi = min(len(series), idx + window + 1)
    win = [{**s, 'is_pick': s['date'] == pick['date']} for s in series[lo:hi]]
    # rolling accuracy over the surrounding 30 trades
    tidx = next((i for i, t in enumerate(trades) if t['date'] == pick['date']), None)
    roll = None
    if tidx is not None:
        seg = trades[max(0, tidx - 15):tidx + 15]
        if seg:
            roll = round(sum(1 for x in seg if x['correct']) / len(seg) * 100, 1)
    move_pct = round((pick['nextClose'] - pick['close']) / pick['close'] * 100, 2) if pick['close'] else 0
    return {
        'status': 'ready',
        'pick_date': pick['date'],
        'signal': pick['signal'],
        'confidence': pick['confidence'],
        'close': pick['close'],
        'next_close': pick['nextClose'],
        'actual': pick['actual'],
        'move_pct': move_pct,
        'correct': pick['correct'],
        'window': win,
        'rolling_accuracy': roll,
        'min_date': rp.get('min_date'),
        'max_date': rp.get('max_date'),
        'n': rp.get('n'),
    }


# ---------------------------- Bitcoin Time Machine: curated scenarios ----------------------------
CURATED_SCENARIOS = [
    {'id': 'covid', 'title': 'COVID Liquidity Shock', 'date': '2020-03-12', 'category': 'Macro shock',
     'description': 'Global markets crashed as COVID-19 lockdowns began. Bitcoin fell ~50% in a day ("Black Thursday") before a historic liquidity-driven recovery.'},
    {'id': 'halving2020', 'title': '3rd Bitcoin Halving', 'date': '2020-05-11', 'category': 'Halving',
     'description': 'The block reward was cut from 12.5 to 6.25 BTC. New supply issuance halved — historically a precursor to major bull phases.'},
    {'id': 'top2021', 'title': '2021 Cycle Top', 'date': '2021-11-09', 'category': 'Cycle top',
     'description': 'Bitcoin printed its ~$69k all-time high amid euphoric leverage, just before a prolonged bear market.'},
    {'id': 'chinaban', 'title': 'China Mining Ban', 'date': '2021-05-21', 'category': 'Regulation',
     'description': 'China intensified its crackdown on mining and trading, triggering a sharp sell-off and a global hashrate migration.'},
    {'id': 'ftx', 'title': 'FTX Collapse', 'date': '2022-11-08', 'category': 'Exchange failure',
     'description': 'The FTX exchange imploded, cascading liquidations and a crisis of confidence across crypto.'},
    {'id': 'capitulation', 'title': 'Bear-Market Capitulation', 'date': '2022-11-21', 'category': 'Capitulation',
     'description': 'Post-FTX capitulation drove Bitcoin toward its cycle low near $15.5k — a moment of maximum fear.'},
    {'id': 'etf', 'title': 'US Spot ETF Approval', 'date': '2024-01-10', 'category': 'Institutional',
     'description': 'The SEC approved the first US spot Bitcoin ETFs, opening a regulated institutional access channel.'},
    {'id': 'halving2024', 'title': '4th Bitcoin Halving', 'date': '2024-04-19', 'category': 'Halving',
     'description': 'The block reward was cut from 6.25 to 3.125 BTC — the fourth halving in Bitcoin history.'},
]
_scenario_cache = {}


def fetch_yahoo_daily_range(symbol, start_unix, end_unix):
    """True daily closes for an arbitrary historical window via Yahoo period1/period2."""
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?interval=1d&period1={int(start_unix)}&period2={int(end_unix)}')
    d = _http_json(url)['chart']['result'][0]
    ts = d['timestamp']
    cl = d['indicators']['quote'][0]['close']
    series = []
    for t, c in zip(ts, cl):
        if c is None:
            continue
        series.append({'date': datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d'),
                       'close': round(float(c), 2)})
    return series


def _fwd(series, idx, days):
    j = min(len(series) - 1, idx + days)
    if j <= idx:
        return None
    base = series[idx]['close']
    return round((series[j]['close'] - base) / base * 100, 1) if base else None


def build_scenario(scn, window=60):
    if scn['id'] in _scenario_cache:
        return _scenario_cache[scn['id']]
    try:
        d0 = datetime.datetime.strptime(scn['date'], '%Y-%m-%d')
        start = (d0 - datetime.timedelta(days=window + 10)).timestamp()
        end = (d0 + datetime.timedelta(days=420)).timestamp()
        series = fetch_yahoo_daily_range('BTC-USD', start, end)
    except Exception:  # noqa
        traceback.print_exc()
        series = None
    if not series:
        doc = runs_col.database['scenario_cache'].find_one({'_id': scn['id']})
        if doc:
            return doc['payload']
        return {**scn, 'status': 'unavailable'}
    idx = 0
    for i, s in enumerate(series):
        if s['date'] <= scn['date']:
            idx = i
        else:
            break
    price = series[idx]['close']
    lo = max(0, idx - window)
    hi = min(len(series), idx + window + 1)
    win = [{'date': s['date'], 'close': s['close'], 'is_pick': s['date'] == series[idx]['date']}
           for s in series[lo:hi]]
    outcomes = {'30d': _fwd(series, idx, 30), '90d': _fwd(series, idx, 90), '365d': _fwd(series, idx, 365)}
    model = None
    try:
        rep = replay_for_date(scn['date'], window=15)
        if rep.get('status') == 'ready' and rep.get('pick_date'):
            pd0 = datetime.datetime.strptime(rep['pick_date'], '%Y-%m-%d')
            if abs((pd0 - d0).days) <= 20:      # replay pick genuinely near the event
                model = {'available': True, 'pick_date': rep['pick_date'], 'signal': rep['signal'],
                         'confidence': rep['confidence'], 'actual': rep['actual'],
                         'correct': rep['correct'], 'move_pct': rep['move_pct']}
    except Exception:  # noqa
        model = None
    if model is None:
        model = {'available': False,
                 'note': 'This event pre-dates CryptoMarkAI’s live data window, so no point-in-time model call exists — shown as historical context only.'}
    payload = {**scn, 'status': 'ready', 'price_at_event': price, 'window': win,
               'outcomes': outcomes, 'model': model}
    _scenario_cache[scn['id']] = payload
    try:
        runs_col.database['scenario_cache'].update_one(
            {'_id': scn['id']}, {'$set': {'_id': scn['id'], 'payload': payload}}, upsert=True)
    except Exception:  # noqa
        pass
    return payload


def get_scenarios():
    out = []
    for scn in CURATED_SCENARIOS:
        try:
            out.append(build_scenario(scn))
        except Exception:  # noqa
            traceback.print_exc()
            out.append({**scn, 'status': 'error'})
    return {'status': 'ready', 'scenarios': out}




def compute():
    df, source = fetch_ohlcv()
    df = build_features(df)
    df = df.dropna().reset_index(drop=True)

    # Target: will tomorrow's close be higher than today's? (1 = up)
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)

    live_row = df.iloc[[-1]].copy()      # target unknown -> live prediction
    train_df = df.iloc[:-1].copy()       # valid targets

    X = train_df[FEATURE_COLS]
    y = train_df['Target']

    # --- TimeSeriesSplit cross validation (no future leakage) ---
    tscv = TimeSeriesSplit(n_splits=5)
    cv_folds = []
    for i, (tr, te) in enumerate(tscv.split(X)):
        m = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr], y.iloc[tr])
        acc = accuracy_score(y.iloc[te], m.predict(X.iloc[te]))
        cv_folds.append({'fold': i + 1, 'accuracy': round(float(acc) * 100, 2), 'testSize': int(len(te))})

    # --- Walk-forward backtest -> accuracy over time + trade log ---
    start = 200 if len(X) > 260 else max(30, int(len(X) * 0.4))
    retrain_every = 10
    model = None
    rows = []
    trades = []
    closes_full = df['close'].reset_index(drop=True)  # includes live row at end
    for i in range(start, len(X)):
        if model is None or (i - start) % retrain_every == 0:
            model = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
            model.fit(X.iloc[:i], y.iloc[:i])
        classes = list(model.classes_)
        proba = model.predict_proba(X.iloc[[i]])[0]
        pred = int(model.predict(X.iloc[[i]])[0])
        conf = float(proba[classes.index(pred)]) * 100 if pred in classes else 50.0
        actual = int(y.iloc[i])
        cur_close = float(closes_full.iloc[i])
        nxt_close = float(closes_full.iloc[i + 1])
        d = train_df['timestamp'].iloc[i]
        rows.append({'date': d, 'correct': 1 if pred == actual else 0, 'close': cur_close})
        trades.append({
            'date': d.strftime('%Y-%m-%d'),
            'signal': 'UP' if pred == 1 else 'DOWN',
            'confidence': round(conf, 1),
            'close': round(cur_close, 2),
            'nextClose': round(nxt_close, 2),
            'actual': 'UP' if actual == 1 else 'DOWN',
            'correct': bool(pred == actual),
        })

    # --- Scoreboard from real out-of-sample trades ---
    total = len(trades)
    wins = sum(1 for t in trades if t['correct'])
    losses = total - wins
    win_rate = round(wins / total * 100, 1) if total else 0.0
    best = cur = 0
    for t in trades:
        if t['correct']:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    sign = None
    streak_len = 0
    for t in reversed(trades):
        if sign is None:
            sign = t['correct']
            streak_len = 1
        elif t['correct'] == sign:
            streak_len += 1
        else:
            break
    scoreboard = {
        'total': total, 'wins': wins, 'losses': losses, 'winRate': win_rate,
        'bestWinStreak': best, 'currentStreak': (streak_len if sign else -streak_len),
    }
    recent_trades = list(reversed(trades))[:25]

    pser = pd.DataFrame(rows)
    pser['rolling_acc'] = pser['correct'].rolling(30, min_periods=10).mean() * 100
    overall_acc = round(float(pser['correct'].mean()) * 100, 2)

    performance = []
    for _, r in pser.iterrows():
        if pd.isna(r['rolling_acc']):
            continue
        d = r['date']
        performance.append({
            'date': d.strftime('%m/%d'),
            'iso': d.strftime('%Y-%m-%d'),
            'btcPrice': round(float(r['close']), 2),
            'aiAccuracy': round(float(r['rolling_acc']), 2),
        })

    # --- Final model on all training data -> live next-day signal ---
    final = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1)
    final.fit(X, y)
    live_X = live_row[FEATURE_COLS]
    pred = int(final.predict(live_X)[0])
    proba = final.predict_proba(live_X)[0]
    # guard for single-class edge case
    classes = list(final.classes_)
    p_up = float(proba[classes.index(1)]) if 1 in classes else 0.0
    p_down = float(proba[classes.index(0)]) if 0 in classes else 0.0
    confidence = round((p_up if pred == 1 else p_down) * 100, 2)

    importances = sorted(
        [{'feature': f, 'label': FEATURE_META[f]['label'], 'category': FEATURE_META[f]['category'],
          'importance': round(float(imp) * 100, 2)} for f, imp in zip(FEATURE_COLS, final.feature_importances_)],
        key=lambda z: -z['importance'],
    )

    feats = live_row.iloc[0]
    feature_snapshot = [
        {'feature': 'RSI', 'label': 'RSI (14)', 'category': 'Momentum',
         'value': round(float(feats['RSI']) * 100, 1), 'unit': ''},
        {'feature': 'StochRSI', 'label': 'Stochastic RSI', 'category': 'Momentum',
         'value': round(float(feats['StochRSI']) * 100, 1), 'unit': ''},
        {'feature': 'MACD_Hist_Norm', 'label': 'MACD Histogram', 'category': 'Trend',
         'value': round(float(feats['MACD_Hist_Norm']) * 100, 3), 'unit': '%'},
        {'feature': 'EMA_Ratio', 'label': 'EMA 9/21 Spread', 'category': 'Trend',
         'value': round(float(feats['EMA_Ratio']) * 100, 2), 'unit': '%'},
        {'feature': 'ATR_Pct', 'label': 'ATR %', 'category': 'Volatility',
         'value': round(float(feats['ATR_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'BB_Width_Pct', 'label': 'Bollinger Width', 'category': 'Volatility',
         'value': round(float(feats['BB_Width_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'Volume_Z', 'label': 'Volume Z-Score', 'category': 'Volume',
         'value': round(float(feats['Volume_Z']), 2), 'unit': 'σ'},
        {'feature': 'Volume_Ratio', 'label': 'Volume Ratio', 'category': 'Volume',
         'value': round(float(feats['Volume_Ratio']), 2), 'unit': 'x'},
    ]

    prev_close = float(train_df['close'].iloc[-1])
    last_close = float(live_row['close'].iloc[0])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)

    # --- Forward live signal history: grade prior pendings, record today's ---
    as_of = live_row['timestamp'].iloc[0].strftime('%Y-%m-%d')
    predict_for = (live_row['timestamp'].iloc[0] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        grade_pending(df)
        record_live_signal(as_of, predict_for, 'UP' if pred == 1 else 'DOWN',
                           confidence, round(last_close, 2))
    except Exception:  # noqa
        traceback.print_exc()
    live_record = compute_live_record()

    # --- Quant Score, Market Regime, multi-horizon forecasts, explainable factors ---
    quant = compute_quant_analysis(df, feats, last_close, live_row['timestamp'].iloc[0])

    # --- Institutional-grade no-key engines ---
    cycle = dominance = chart = market_intel = None
    try:
        cycle = compute_cycle_context(last_close, quant['regime']['regime'])
    except Exception:  # noqa
        traceback.print_exc()
    try:
        dominance = fetch_dominance(day_change)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        chart = compute_chart_intelligence(df)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        market_intel = build_market_intel(quant, quant['forecasts'], cycle, dominance, chart)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Cross-market correlations, Policy & Liquidity, Alerts (keyless) ---
    crossmarket = policy = alerts = None
    try:
        crossmarket, _raw = compute_crossmarket()
        policy = compute_policy(_raw)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        alerts = compute_alerts(quant, cycle, policy, chart, crossmarket)
    except Exception:  # noqa
        traceback.print_exc()

    # --- News → Forecast Link + Unified Bitcoin Decision Engine ---
    news_sig = news_forecast_link = decision = None
    try:
        news_doc = news_col.find_one(sort=[('created_at', -1)])
        news_sig = compute_news_signal(news_doc)
        news_forecast_link = apply_news_link(quant['forecasts'], news_sig)  # mutates 24H/7D
    except Exception:  # noqa
        traceback.print_exc()
    all_outlook = list(quant['forecasts']) + list(quant.get('long_outlook', []))

    # --- Dynamic Regime-Switching engine (Gaussian HMM) -> dynamic signal weights ---
    regime_analysis = None
    try:
        regime_analysis = regime_engine.analyze(df, regime_col=regime_col)
    except Exception:  # noqa
        traceback.print_exc()
    dyn_weights = (regime_analysis or {}).get('active_weights') if regime_analysis else None

    try:
        decision = compute_decision_engine(quant, all_outlook, policy, news_sig, chart, cycle,
                                           dominance, weights=dyn_weights, regime_info=regime_analysis)
        # Refresh the 24h confidence cone with the real composite score now that we have it.
        if regime_analysis and regime_analysis.get('available') and decision:
            try:
                bands = regime_engine.recompute_confidence(
                    regime_analysis['current_regime'], decision['overall_score'],
                    regime_analysis.get('realized_vol_daily_pct', 2.0))
                if bands:
                    regime_analysis['confidence_24h'] = bands
                    decision['regime_engine'] = regime_analysis
            except Exception:  # noqa
                traceback.print_exc()
    except Exception:  # noqa
        traceback.print_exc()

    # --- Data Trust Layer (source/freshness/confidence + fade odds when stale) ---
    data_health = None
    try:
        data_health = compute_data_health(source, crossmarket, policy, dominance, news_doc)
        apply_data_fade(decision, data_health)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Albert If-Then scenarios + contradiction resolution (regime-aware) ---
    try:
        if decision is not None:
            decision['scenarios_block'] = compute_scenarios(
                chart, decision, last_close, feats, regime_analysis)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Quant-grade validation (purged walk-forward + PSR/DSR/rolling Brier) ---
    quant_val = None
    try:
        quant_val = quant_validation.run_validation(df, FEATURE_COLS, horizon=5, n_splits=5)
        check_model_decay_alert(quant_val)
        # Self-healing corridors: store next-run widen factors from this run's coverage dips.
        try:
            rc = (quant_val or {}).get('recent_coverage') or {}
            tgt = (quant_val or {}).get('coverage_target', 90)
            wmap = {}
            for lbl, cov in rc.items():
                wmap[lbl] = round(max(1.0, min(1.6, tgt / cov)), 3) if cov and cov > 0 else 1.0
            if wmap:
                misc_col.update_one({'_id': 'corridor_widen'},
                                    {'$set': {'map': wmap, 'updated_at': datetime.datetime.utcnow().isoformat()}},
                                    upsert=True)
        except Exception:  # noqa
            traceback.print_exc()
    except Exception:  # noqa
        traceback.print_exc()

    # --- Event Intelligence Calendar ---
    event_calendar = None
    try:
        event_calendar = compute_event_calendar(cycle, policy)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Risk Engine + Smart Money / Institutional (DEMO) ---
    risk = smart_money = institutional = None
    try:
        risk = compute_risk_engine(quant, chart, decision, data_health, event_calendar, last_close, feats)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        _panels = get_onchain_panels()
        smart_money = _panels.get('smart_money') or compute_smart_money_demo(last_close, quant['regime']['regime'])
        institutional = _panels.get('institutional') or compute_institutional_demo(last_close)
    except Exception:  # noqa
        traceback.print_exc()

    # --- Prediction Ledger + public scorecard ---
    prediction_ledger = None
    try:
        close_by_date = {ts.strftime('%Y-%m-%d'): float(c)
                         for ts, c in zip(df['timestamp'], df['close'])}
        seed_ledger_from_backtest(trades)
        record_predictions(as_of, last_close, all_outlook, quant['regime']['regime'], source)
        resolve_predictions(close_by_date, as_of)
        prediction_ledger = compute_scorecard()
        # Ensemble weighting: annotate each live forecast with its horizon's health and
        # shrink the displayed confidence toward 50% for decaying horizons.
        try:
            bh = (prediction_ledger or {}).get('by_horizon') or {}
            for f in (quant.get('forecasts', []) + quant.get('long_outlook', [])):
                info = bh.get(f.get('horizon'))
                if not info:
                    continue
                w = info.get('ensemble_weight', 1.0)
                f['ensemble_weight'] = w
                f['decaying'] = bool(info.get('decaying'))
                f['horizon_brier'] = info.get('brier')
                if w < 1.0 and f.get('higher') is not None:
                    f['higher'] = round(50 + (f['higher'] - 50) * w, 1)
                    f['lower'] = round(100 - f['higher'], 1)
                    if f.get('confidence_pct') is not None:
                        f['confidence_pct'] = round(f['confidence_pct'] * w)
            # Feed ensemble health into the HEADLINE conviction score: decaying horizons
            # lighten the top-line call by shrinking it toward neutral (50).
            weights = [i.get('ensemble_weight') for i in bh.values() if i.get('ensemble_weight') is not None]
            if weights and decision is not None and decision.get('overall_score') is not None:
                health = sum(weights) / len(weights)
                blend = 0.7 + 0.3 * health   # 0.7 (all decaying) .. 1.0 (all healthy)
                ov = decision['overall_score']
                decision['overall_score_raw'] = ov
                decision['ensemble_health'] = round(health, 3)
                decision['overall_score'] = max(0, min(100, int(round(50 + (ov - 50) * blend))))
                decision['label'] = _quant_score_label(decision['overall_score'])
        except Exception:  # noqa
            traceback.print_exc()
    except Exception:  # noqa
        traceback.print_exc()

    # --- Pillar 2: Feature Drift Monitoring & Model-Failover Circuit Breaker ---
    drift = None
    try:
        live_feats_map = {c: float(feats[c]) for c in FEATURE_COLS if c in feats}
        drift = drift_monitor.assess(
            X, FEATURE_COLS, feature_meta=FEATURE_META,
            data_health=data_health, live_feats=live_feats_map,
            ml_signal=('UP' if pred == 1 else 'DOWN'), ml_confidence=confidence)
        if drift and drift.get('circuit_breaker') and decision is not None:
            # Downgrade conviction toward neutral and switch to the conservative
            # rule-based trend model as the effective directional call.
            ov = decision.get('overall_score')
            if ov is not None:
                decision['overall_score_pre_breaker'] = ov
                decision['overall_score'] = max(0, min(100, int(round(50 + (ov - 50) * 0.5))))
                decision['label'] = _quant_score_label(decision['overall_score'])
            decision['circuit_breaker'] = {
                'active': True,
                'model_mode': 'rule_based',
                'confidence_level': 'Low',
                'reasons': drift.get('reasons'),
                'fallback_signal': drift.get('fallback_signal'),
                'max_psi': drift.get('max_psi'),
                'data_completeness_pct': drift.get('data_completeness_pct'),
            }
            decision['confidence_level'] = 'Low'
        elif decision is not None:
            decision['confidence_level'] = (drift or {}).get('confidence_level', 'Normal')
            decision['circuit_breaker'] = {'active': False,
                                           'model_mode': 'ml',
                                           'confidence_level': (drift or {}).get('confidence_level', 'Normal')}
        # Edge-triggered admin email (reuses the Resend recipient pipeline, 24h cooldown).
        try:
            check_drift_circuit_alert(drift)
        except Exception:  # noqa
            traceback.print_exc()
    except Exception:  # noqa
        traceback.print_exc()

    # --- CryptoMarkAI prediction core (1W–5Y, per-horizon weighting, triggers) ---
    bitmark = None
    try:
        trig = _forecast_trigger.get('reason')
        if not trig:
            hi_news = bool(news_sig and news_sig.get('n_high_impact', 0) >= 2)
            trig = 'event' if (abs(day_change) >= 5.0 or hi_news) else 'scheduled'
        bitmark = compute_bitmark(quant, cycle, last_close, trigger=trig)
        _forecast_trigger['reason'] = None
    except Exception:  # noqa
        traceback.print_exc()

    # --- Pillar 4/5: holder cost-basis proxies + derivatives snapshot ---
    # (keyless, transparent proxies used for chart overlays + proactive alerts)
    cost_basis = None
    try:
        def _vwap(dd, nbars):
            tail = dd.tail(nbars)
            vol = tail['volume'].astype(float)
            tot = float(vol.sum())
            if tot > 0:
                return float((tail['close'].astype(float) * vol).sum() / tot)
            return float(tail['close'].astype(float).mean())
        sth = round(_vwap(df, 155), 2)
        lth = round(_vwap(df, 365), 2)
        cost_basis = {
            'sth': sth, 'lth': lth, 'sth_window': 155, 'lth_window': 365,
            'price': round(last_close, 2),
            'sth_reclaimed': bool(last_close >= sth),
            'lth_reclaimed': bool(last_close >= lth),
            'method': 'Volume-weighted average price proxy (keyless) for short/long-term holder cost basis.',
        }
    except Exception:  # noqa
        traceback.print_exc()

    leverage_snapshot = None
    try:
        lv = get_leverage('4H') or {}
        leverage_snapshot = {
            'funding_rate': (lv.get('funding') or {}).get('rate'),
            'funding_bias': (lv.get('funding') or {}).get('bias'),
            'funding_dir': (lv.get('funding') or {}).get('direction'),
            'oi_change_tf_pct': (lv.get('open_interest') or {}).get('change_tf_pct'),
            'oi_state': (lv.get('open_interest') or {}).get('state'),
            'squeeze': lv.get('squeeze'),
        }
    except Exception:  # noqa
        traceback.print_exc()

    doc = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.datetime.utcnow().isoformat(),
        'as_of': live_row['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'data_source': source,
        'pair': 'BTC/USD',
        'last_close': round(last_close, 2),
        'day_change_pct': day_change,
        'signal': 'UP' if pred == 1 else 'DOWN',
        'confidence': confidence,
        'prob_up': round(p_up * 100, 2),
        'prob_down': round(p_down * 100, 2),
        'overall_accuracy': overall_acc,
        'cv_folds': cv_folds,
        'cv_mean': round(float(np.mean([f['accuracy'] for f in cv_folds])), 2),
        'importances': importances,
        'performance': performance,
        'features': feature_snapshot,
        'n_samples': int(len(X)),
        'history_days': int((train_df['timestamp'].iloc[-1] - train_df['timestamp'].iloc[0]).days),
        'first_date': train_df['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'predict_for_date': predict_for,
        'scoreboard': scoreboard,
        'trades': recent_trades,
        'live_record': live_record,
        'quant_score': quant['quant_score'],
        'quant_label': quant['quant_label'],
        'quant_breakdown': quant['quant_breakdown'],
        'regime': quant['regime'],
        'forecasts': quant['forecasts'],
        'long_outlook': quant.get('long_outlook', []),
        'factors': quant['factors'],
        'decision': decision,        'news_forecast_link': news_forecast_link,
        'regime_analysis': regime_analysis,
        'drift': drift,
        'cost_basis': cost_basis,
        'leverage_snapshot': leverage_snapshot,
        'quant_validation': quant_val,
        'data_health': data_health,
        'event_calendar': event_calendar,
        'risk': risk,
        'smart_money': smart_money,
        'institutional': institutional,
        'prediction_ledger': prediction_ledger,
        'bitmark': bitmark,
        'cycle': cycle,
        'dominance': dominance,
        'chart': chart,
        'market_intel': market_intel,
        'crossmarket': crossmarket,
        'policy': policy,
        'alerts': alerts,
    }

    # --- Smart Alerts: detect state changes vs the previous run ---
    smart_alerts = None
    try:
        prev_doc = runs_col.find_one(sort=[('created_at', -1)])
        smart_alerts = compute_smart_alerts(doc, prev_doc)
    except Exception:  # noqa
        traceback.print_exc()
    doc['smart_alerts'] = get_smart_alerts()

    # --- Time Machine replay payload (stored only, not sent in dashboard) ---
    try:
        price_series = [{'date': ts.strftime('%Y-%m-%d'), 'close': round(float(c), 2)}
                        for ts, c in zip(df['timestamp'], df['close'])]
        replay = build_replay_payload(trades, price_series)
    except Exception:  # noqa
        traceback.print_exc()
        replay = None

    to_store = dict(doc)
    to_store['_id'] = doc['id']
    to_store['replay'] = replay
    # keep the full smart-alert feed out of the heavy run doc snapshot
    to_store.pop('smart_alerts', None)
    runs_col.insert_one(to_store)
    return doc


def run_compute_bg():
    with _lock:
        if _state['status'] == 'running':
            return
        _state['status'] = 'running'
        _state['error'] = None
        _state['started_at'] = datetime.datetime.utcnow().isoformat()
    try:
        compute()
        _state['status'] = 'done'
    except Exception as e:  # noqa
        _state['status'] = 'error'
        _state['error'] = str(e)
        traceback.print_exc()


@app.on_event('startup')
def _startup():
    global _scheduler
    # Pillar 1: start the real-time WebSocket order-flow ingestion pipeline.
    try:
        orderflow.start()
    except Exception:  # noqa
        traceback.print_exc()
    try:
        scheduler = BackgroundScheduler(timezone='UTC')
        scheduler.add_job(run_compute_bg, 'cron', hour=0, minute=5, id='daily_refresh')
        scheduler.add_job(run_news_bg, 'interval', hours=1, id='news_refresh')
        # Whale Watch: refresh balances daily (new snapshot -> fires whale-move alerts) + keep it fresh.
        scheduler.add_job(_refresh_whales_bg, 'cron', hour=0, minute=12, id='whale_daily')
        scheduler.add_job(_refresh_whales_bg, 'interval', hours=6, id='whale_refresh')
        # ETF flows: refresh a few times/day (US ETF data updates evening US time).
        scheduler.add_job(_refresh_etf_bg, 'interval', hours=3, id='etf_refresh')
        # Large-transaction feed: keep the labeled whale-tx feed fresh.
        scheduler.add_job(_refresh_whale_tx_bg, 'interval', minutes=30, id='whale_tx_refresh')
        # Price-watch alerts created from Albert chat: check crossings every 60s.
        scheduler.add_job(_check_price_watches, 'interval', seconds=60, id='price_watch_check')
        # Albert Trading Strategies: track active playbooks, fire nudges & paper-trade fills.
        scheduler.add_job(_strategy_eval_job, 'interval', seconds=60, id='strategy_eval',
                          replace_existing=True, coalesce=True, max_instances=1)
        # Alert Engine: scan the watchlist's daily signals hourly and fire in-app alerts.
        scheduler.add_job(_alert_engine_job, 'interval', minutes=60, id='alert_engine',
                          replace_existing=True, coalesce=True, max_instances=1)
        # Albert's engine snapshot (edge board + sector rotation) — warmed every 3h and
        # once ~40s after boot so chat/brief can reference it instantly.
        scheduler.add_job(_engine_snapshot_job, 'interval', hours=3, id='engine_snapshot',
                          replace_existing=True, coalesce=True, max_instances=1,
                          next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=40))
        # Alert Engine daily digest — one consolidated in-app summary at the local morning hour.
        try:
            scheduler.add_job(_alert_digest_job, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              timezone=DIGEST_TZ, id='alert_digest', replace_existing=True,
                              coalesce=True, max_instances=1)
        except Exception:  # noqa
            scheduler.add_job(_alert_digest_job, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              id='alert_digest', replace_existing=True, coalesce=True, max_instances=1)
        # Multi-coin BASKET daily digest — one consolidated summary per user of legs that
        # hit a target/stop in the last 24h (same local morning hour as the alert digest).
        try:
            scheduler.add_job(_basket_digest_job, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              timezone=DIGEST_TZ, id='basket_digest', replace_existing=True,
                              coalesce=True, max_instances=1)
        except Exception:  # noqa
            scheduler.add_job(_basket_digest_job, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              id='basket_digest', replace_existing=True, coalesce=True, max_instances=1)
        # Auto-rebalance cadence — Monday morning nudge to rebalance a basket when sector
        # rotation has shifted materially since last week.
        try:
            scheduler.add_job(_basket_rebalance_nudge_job, 'cron', day_of_week='mon', hour=DIGEST_HOUR,
                              minute=DIGEST_MINUTE, timezone=DIGEST_TZ, id='basket_rebal_nudge',
                              replace_existing=True, coalesce=True, max_instances=1)
        except Exception:  # noqa
            scheduler.add_job(_basket_rebalance_nudge_job, 'cron', day_of_week='mon', hour=DIGEST_HOUR,
                              minute=DIGEST_MINUTE, id='basket_rebal_nudge', replace_existing=True,
                              coalesce=True, max_instances=1)
        # Albert self-check: grade his logged buy/sell calls once their horizon elapses.
        scheduler.add_job(_grade_albert_calls, 'interval', minutes=30, id='albert_call_grade')
        # Weekly recap auto-post: drop Albert's recap into the notification bell every Monday.
        scheduler.add_job(_weekly_recap_autopost, 'cron', day_of_week='mon', hour=13, minute=30, id='weekly_recap_autopost')
        # Daily plain-English morning brief pushed to the notification bell.
        scheduler.add_job(_daily_brief_autopost, 'cron', hour=13, minute=0, id='daily_brief_autopost')
        # Daily Alert Digest email (Resend). Per-job timezone so it fires at local send time.
        try:
            scheduler.add_job(send_daily_digest_bg, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              timezone=DIGEST_TZ, id='daily_digest', replace_existing=True,
                              coalesce=True, max_instances=1)
        except Exception:  # noqa — bad tz string shouldn't kill the whole scheduler; fall back to UTC
            traceback.print_exc()
            scheduler.add_job(send_daily_digest_bg, 'cron', hour=DIGEST_HOUR, minute=DIGEST_MINUTE,
                              id='daily_digest', replace_existing=True, coalesce=True, max_instances=1)
        # Instant high-severity alert emails — checked every 5 minutes (idempotent per alert).
        scheduler.add_job(send_instant_alerts_bg, 'interval', minutes=5, id='instant_alerts',
                          replace_existing=True, coalesce=True, max_instances=1)
        # Pillar 4/1: real-time liquidation-cascade watcher on the live WS feed.
        scheduler.add_job(check_liq_cascade_alert, 'interval', seconds=30, id='liq_cascade',
                          replace_existing=True, coalesce=True, max_instances=1)
        # Weekly recap — Sundays.
        try:
            scheduler.add_job(send_weekly_recap_bg, 'cron', day_of_week='sun', hour=WEEKLY_HOUR,
                              minute=WEEKLY_MINUTE, timezone=DIGEST_TZ, id='weekly_recap',
                              replace_existing=True, coalesce=True, max_instances=1)
        except Exception:  # noqa
            traceback.print_exc()
            scheduler.add_job(send_weekly_recap_bg, 'cron', day_of_week='sun', hour=WEEKLY_HOUR,
                              minute=WEEKLY_MINUTE, id='weekly_recap', replace_existing=True,
                              coalesce=True, max_instances=1)
        scheduler.start()
        _scheduler = scheduler
    except Exception:  # noqa
        traceback.print_exc()
    if runs_col.count_documents({}) == 0:
        threading.Thread(target=run_compute_bg, daemon=True).start()
    if news_col.count_documents({}) == 0:
        threading.Thread(target=run_news_bg, daemon=True).start()
    if whale_col.count_documents({'_id': {'$ne': '_meta'}}) == 0:
        threading.Thread(target=_refresh_whales_bg, daemon=True).start()
    if etf_col.count_documents({'_id': 'btc'}) == 0:
        threading.Thread(target=_refresh_etf_bg, daemon=True).start()


@app.get('/api/v1/health')
def health():
    return {'status': 'ok', 'compute_status': _state['status'], 'error': _state['error'],
            'runs': runs_col.count_documents({})}


@app.get('/api/v1/ticker')
def ticker(symbol: str = 'BTC'):
    import time
    symbol = (symbol or 'BTC').strip().upper()[:6]
    pair = 'BTC/USD' if symbol == 'BTC' else f'{symbol}/USD'
    now = time.time()
    cache = _ticker_cache.get(symbol)
    if cache and cache.get('data') and (now - cache['ts']) < 8:
        return cache['data']

    def usd_aud():
        if _fx_cache['rate'] and (now - _fx_cache['ts']) < 1800:
            return _fx_cache['rate']
        try:
            s = fetch_yahoo_series('AUD=X', '5d')
            rate = float(s.iloc[-1])
            if rate > 0:
                _fx_cache['rate'] = rate
                _fx_cache['ts'] = now
        except Exception:  # noqa
            traceback.print_exc()
        return _fx_cache['rate']

    for name in ['kraken', 'coinbase']:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            t = ex.fetch_ticker(pair)
            last = float(t['last'])
            pct = t.get('percentage')
            if pct is None and t.get('open'):
                pct = (last - float(t['open'])) / float(t['open']) * 100
            rate = usd_aud()
            data = {
                'symbol': symbol,
                'price': round(last, 2),
                'price_aud': round(last * rate, 2) if rate else None,
                'aud_rate': round(rate, 4) if rate else None,
                'change24h': round(float(pct), 2) if pct is not None else 0.0,
                'high': round(float(t.get('high') or last), 2),
                'low': round(float(t.get('low') or last), 2),
                'source': name,
                'ts': datetime.datetime.utcnow().isoformat(),
            }
            _ticker_cache[symbol] = {'data': data, 'ts': now}
            return data
        except Exception:  # noqa
            continue
    return {'price': None, 'error': 'ticker unavailable'}


@app.get('/api/v1/dashboard')
def dashboard(symbol: str = 'BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        if symbol not in COMPARE_COINS:
            return {'status': 'error', 'error': 'unsupported_symbol'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        cached = coin_dash_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('data'):
            return {'status': 'ready', 'compute_status': 'done', **cached['data']}
        st = _coin_dash_state.get(symbol)
        if st != 'running':
            threading.Thread(target=run_coin_dash_bg, args=(symbol,), daemon=True).start()
        if st == 'error':
            return {'status': 'error', 'error': 'compute_failed'}
        return {'status': 'computing'}
    doc = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
    if not doc:
        st = _state['status']
        return {'status': 'error' if st == 'error' else 'computing', 'error': _state['error']}
    # Add smart_alerts to the response (not stored in the run doc to save space)
    doc['smart_alerts'] = get_smart_alerts()
    # Overlay freshest live Smart Money / Institutional panels (real on-chain + OKX
    # derivatives + ETF flows) so they update on their own ~2-3h cadence rather than
    # being frozen at the last daily compute.
    try:
        _live = get_onchain_panels('BTC')
        if _live.get('smart_money'):
            doc['smart_money'] = _live['smart_money']
        if _live.get('institutional'):
            doc['institutional'] = _live['institutional']
    except Exception:  # noqa
        traceback.print_exc()
    # Admin demo: force the circuit breaker to trip live (no recompute needed).
    if _breaker_sim_active():
        try:
            doc['drift'] = _sim_trip_drift(doc.get('drift') or {})
            doc['decision'] = _sim_trip_decision(doc.get('decision') or {}, doc['drift'])
        except Exception:  # noqa
            traceback.print_exc()
    return {'status': 'ready', 'compute_status': _state['status'], **doc}


@app.post('/api/v1/refresh')
def refresh(request: Request, payload: dict = Body(default={})):
    # Expensive full recompute — gate behind admin passcode + per-client rate limit.
    limited = _too_many(request, 'refresh', per_min=3, per_day=50)
    if limited is not None:
        return limited
    if not _passcode_ok((payload or {}).get('passcode', '')):
        audit_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                              'action': 'refresh', 'result': 'denied', 'reason': 'bad_passcode'})
        return JSONResponse(status_code=401, content={
            'status': 'unauthorized',
            'message': 'A valid admin passcode is required to trigger a full recompute. Enter it in Settings.'})
    threading.Thread(target=run_compute_bg, daemon=True).start()
    return {'status': 'started'}


@app.get('/api/v1/news')
def news(symbol: str = 'BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        if symbol not in COMPARE_COINS:
            return {'status': 'error', 'error': 'unsupported_symbol'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        cached = coin_news_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('doc'):
            return {'status': 'ready', 'news_status': 'done', **cached['doc']}
        st = _coin_news_state.get(symbol)
        if st != 'running':
            threading.Thread(target=run_coin_news_bg, args=(symbol,), daemon=True).start()
        if st == 'error':
            return {'status': 'error', 'error': 'news_failed'}
        return {'status': 'computing'}
    doc = news_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
    if not doc:
        if _news_state['status'] not in ('running',):
            threading.Thread(target=run_news_bg, daemon=True).start()
        return {'status': 'error' if _news_state['status'] == 'error' else 'computing', 'error': _news_state['error']}
    return {'status': 'ready', 'news_status': _news_state['status'], **doc}


@app.post('/api/v1/news/refresh')
def news_refresh(request: Request):
    limited = _too_many(request, 'news_refresh', per_min=3, per_day=60)
    if limited is not None:
        return limited
    threading.Thread(target=run_news_bg, daemon=True).start()
    return {'status': 'started'}


@app.get('/api/v1/chat/history')
def chat_history(session_id: str):
    msgs = list(chat_col.find({'session_id': session_id}, {'_id': 0}).sort('created_at', 1))
    return {'session_id': session_id, 'messages': msgs}


@app.get('/api/v1/scorecard')
def scorecard():
    try:
        return {'status': 'ready', **compute_scorecard()}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/data-audit')
def data_audit_live():
    """Real-time feed-health audit. Recomputes freshness AT REQUEST TIME using the actual
    cache timestamps (ETF/on-chain/leverage/sentiment) and the last daily-run time for the
    core feeds — so the age shown is genuinely live, not frozen at the last compute()."""
    try:
        run = runs_col.find_one(sort=[('created_at', -1)])
        news_doc = news_col.find_one(sort=[('created_at', -1)])
        health = compute_data_health(
            (run or {}).get('data_source'),
            (run or {}).get('crossmarket'),
            (run or {}).get('policy'),
            (run or {}).get('dominance'),
            news_doc,
            core_iso=(run or {}).get('created_at'),
        )
        health['last_run'] = (run or {}).get('created_at')
        return {'status': 'ready', **health}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}



@app.get('/api/v1/validation')
def quant_validation_endpoint():
    """Latest quant-grade validation: purged walk-forward OOF Brier + PSR/DSR + rolling Brier decay."""
    try:
        run = runs_col.find_one(sort=[('created_at', -1)])
        qv = (run or {}).get('quant_validation')
        if qv:
            return {'status': 'ready', **qv}
        return {'status': 'computing'}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}



_SIM_REASONS = ['Simulated market shock (admin demo) — live inputs forced out-of-distribution.']


def _breaker_sim_active():
    try:
        return bool((misc_col.find_one({'_id': 'breaker_sim'}) or {}).get('active'))
    except Exception:  # noqa
        return False


def _sim_trip_drift(drift):
    """Force a drift dict into a tripped/rule-based state for the admin demo."""
    d = dict(drift) if isinstance(drift, dict) else {}
    fb = d.get('fallback_signal') or {'signal': 'DOWN', 'confidence': 55,
                                       'basis': 'EMA 9/21 trend + MACD confirmation (conservative rule-based)'}
    d.update({
        'status': 'breaker', 'circuit_breaker': True, 'confidence_level': 'Low',
        'model_mode': 'rule_based', 'simulated': True, 'reasons': list(_SIM_REASONS),
        'fallback_signal': fb, 'effective_signal': fb.get('signal'),
        'effective_confidence': fb.get('confidence'),
        'headline': 'Circuit breaker TRIPPED (SIMULATED) — reverted to conservative rule-based trend model.',
    })
    return d


def _sim_trip_decision(decision, drift):
    if not isinstance(decision, dict):
        return decision
    ov = decision.get('overall_score')
    if ov is not None and decision.get('overall_score_pre_breaker') is None:
        decision['overall_score_pre_breaker'] = ov
        decision['overall_score'] = max(0, min(100, int(round(50 + (ov - 50) * 0.5))))
        decision['label'] = _quant_score_label(decision['overall_score'])
    decision['confidence_level'] = 'Low'
    decision['circuit_breaker'] = {'active': True, 'model_mode': 'rule_based',
                                   'confidence_level': 'Low', 'reasons': list(_SIM_REASONS),
                                   'fallback_signal': (drift or {}).get('fallback_signal'),
                                   'simulated': True}
    return decision


@app.get('/api/v1/admin/simulate-shock')
def simulate_shock_state():
    return {'active': _breaker_sim_active()}


@app.post('/api/v1/admin/simulate-shock')
def simulate_shock(request: Request, payload: dict = Body(default={})):
    """Admin-only demo switch: force the drift circuit breaker to trip live in the UI
    (without an expensive recompute). Toggle off to restore the real model state."""
    if not _passcode_ok((payload or {}).get('passcode', '')):
        return JSONResponse(status_code=401, content={
            'status': 'unauthorized', 'message': 'A valid admin passcode is required.'})
    on = bool(payload.get('on'))
    misc_col.update_one({'_id': 'breaker_sim'},
                        {'$set': {'active': on, 'updated_at': datetime.datetime.utcnow().isoformat()}},
                        upsert=True)
    return {'status': 'ok', 'active': on}


@app.get('/api/v1/orderflow')
def orderflow_endpoint():
    """Real-time order-flow microstructure snapshot (CVD, OFI, VPIN, liquidation
    cascade) computed by the 1-second aggregator over live Coinbase + Bybit WS feeds."""
    try:
        return orderflow.get_latest()
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


_tm_cache = {'ts': 0, 'df': None}


def _tm_df():
    """Cached OHLCV+features DataFrame for the Time Machine (refresh hourly)."""
    if _tm_cache['df'] is not None and (time.time() - _tm_cache['ts'] < 3600):
        return _tm_cache['df']
    dfr, _src = fetch_ohlcv()
    dfr = build_features(dfr).dropna().reset_index(drop=True)
    _tm_cache.update(ts=time.time(), df=dfr)
    return dfr


@app.get('/api/v1/time-machine/analogs')
def time_machine_analogs(k: int = 3):
    """FAISS analog engine — "when did this happen before?": top-K most similar
    historical days + their 7d/30d forward return paths + aggregate outcome."""
    try:
        k = max(1, min(6, int(k)))
        df = _tm_df()
        return time_machine.find_analogs(df, FEATURE_COLS, k=k)
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/time-machine/analog-recap')
def analog_recap(date: str, price: float = None):
    """On-demand: Albert (Gemini + live web search) recaps what actually happened
    in Bitcoin/macro around a historical analog date. Cached per date in Mongo."""
    try:
        key = f'analog_recap:{date}'
        cached = misc_col.find_one({'_id': key})
        if cached and cached.get('recap'):
            return {'date': date, 'recap': cached['recap'], 'cached': True}
        if not LLM_READY_KEY:
            return {'date': date, 'recap': None, 'error': 'LLM not configured'}
        sys = ("You are Albert, a concise market historian. Using live web search, recap what was "
               "actually happening in Bitcoin and broader markets around the given date. Reply in 2-4 "
               "short sentences covering: the price level/action, the key catalyst(s) or news (spot ETF "
               "flows, Fed/macro prints, regulation, hacks, major liquidations), and overall sentiment. "
               "Be factual and specific; no disclaimers, no bullet lists, no preamble.")
        q = f"What was happening in Bitcoin and macro markets around {date}?"
        if price:
            q += f" (BTC traded near ${round(price):,} at that time.)"
        chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'analog-{date}', system_message=sys)
                .with_model('gemini', ALBERT_CHAT_MODEL)
                .with_params(temperature=0.3, max_tokens=3000))
        text = ''
        try:
            reply = asyncio.run(chat.with_tools([{'googleSearch': {}}])
                                .send_message_with_tools(UserMessage(text=q)))
            text = (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '').strip()
        except Exception:  # noqa
            traceback.print_exc()
        if not text:
            reply2 = asyncio.run(chat.send_message(UserMessage(text=q)))
            text = (getattr(reply2, 'text', None) or str(reply2)).strip()
        if text:
            misc_col.update_one({'_id': key},
                                {'$set': {'recap': text, 'ts': datetime.datetime.utcnow().isoformat()}},
                                upsert=True)
        return {'date': date, 'recap': text, 'cached': False}
    except Exception:  # noqa
        traceback.print_exc()
        return {'date': date, 'recap': None, 'error': 'failed'}


@app.get('/api/v1/drift')
def drift_endpoint():
    """Latest Feature-Drift Circuit Breaker assessment: PSI/KS per feature, data
    completeness, breaker status, and the rule-based fallback signal."""
    try:
        run = runs_col.find_one(sort=[('created_at', -1)])
        d = (run or {}).get('drift')
        if d:
            if _breaker_sim_active():
                d = _sim_trip_drift(d)
            return {**d, 'ready': True}
        return {'ready': False, 'status': 'computing'}
    except Exception:  # noqa
        traceback.print_exc()
        return {'ready': False, 'status': 'error'}


@app.get('/api/v1/forecast/regime')
def forecast_regime():
    """Latest Dynamic Regime-Switching analysis: current regime, posterior state
    probabilities, dynamic signal weights, and the regime-scaled 24h cone."""
    try:
        doc = regime_col.find_one({'_id': 'btc'})
        latest = (doc or {}).get('latest')
        if latest:
            return {'status': 'ready', 'weight_matrix': regime_engine.REGIME_WEIGHT_MATRIX,
                    'regime_labels': regime_engine.REGIME_LABELS, **latest}
        # No snapshot yet — try to build one from the most recent run.
        run = runs_col.find_one(sort=[('created_at', -1)])
        ra = (run or {}).get('regime_analysis')
        if ra:
            return {'status': 'ready', 'weight_matrix': regime_engine.REGIME_WEIGHT_MATRIX,
                    'regime_labels': regime_engine.REGIME_LABELS, **ra}
        return {'status': 'computing'}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.post('/api/v1/forecast/reconcile-signals')
def reconcile_signals(payload: dict = Body(default={})):
    """Recompute the composite quant score under the CURRENT market regime.

    Any signal score (0-100) left null is filled from the latest live decision
    components, so the endpoint doubles as a "what-if" tool: pass a hypothetical
    technicals/news score and see how the regime-weighted composite + 24h cone move.
    """
    try:
        payload = payload or {}
        doc = regime_col.find_one({'_id': 'btc'})
        latest = (doc or {}).get('latest') or {}
        weights = latest.get('active_weights') or regime_engine.STATIC_WEIGHTS
        regime = latest.get('current_regime') or 'consolidation'
        realized_vol = latest.get('realized_vol_daily_pct', 2.0)

        # Defaults from the latest run's decision components.
        run = runs_col.find_one(sort=[('created_at', -1)])
        comp_map = {}
        for c in ((run or {}).get('decision') or {}).get('components', []):
            key = {'Technicals': 'technicals', 'Macro / Policy': 'macro_policy',
                   'Chart Structure': 'chart_structure', 'News Flow': 'news_flow'}.get(c['name'])
            if key:
                comp_map[key] = float(c['score'])

        supplied = {k: float(payload[k]) for k in regime_engine.SIGNALS
                    if payload.get(k) is not None}
        signals = {**{k: 50.0 for k in regime_engine.SIGNALS}, **comp_map, **supplied}
        signals = {k: max(0.0, min(100.0, float(v))) for k, v in signals.items()}

        wt = sum(weights.get(k, 0.0) for k in regime_engine.SIGNALS) or 1.0
        composite = sum(signals[k] * weights.get(k, 0.0) for k in regime_engine.SIGNALS) / wt
        composite = round(max(0.0, min(100.0, composite)), 2)
        bands = regime_engine.recompute_confidence(regime, composite, realized_vol)

        return {
            'status': 'ready',
            'current_regime': regime,
            'regime_label': regime_engine.REGIME_LABELS.get(regime, regime),
            'regime_probabilities': latest.get('regime_probabilities'),
            'active_weights': {k: round(weights.get(k, 0.0), 4) for k in regime_engine.SIGNALS},
            'signals_used': signals,
            'signals_overridden': list(supplied.keys()),
            'composite_quant_score': composite,
            'composite_label': _quant_score_label(round(composite)),
            'confidence_interval_24h': bands,
        }
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}



@app.get('/api/v1/whales')
def whales_feed():
    try:
        return {'status': 'ready', **get_whales()}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'whales': []}


@app.get('/api/v1/whale-activity')
def whale_activity(address: str, limit: int = 12):
    """Recent NOTABLE on-chain activity for a whale address (net effect per tx), via mempool.space.
    Filters out dust/spam sends to surface meaningful moves; falls back to raw recent if none."""
    try:
        txs = _engine_get(f'https://mempool.space/api/address/{address}/txs')
        if not isinstance(txs, list):
            return {'status': 'error', 'activity': []}
        entries = []
        for t in txs:
            recv = sum(v.get('value', 0) for v in t.get('vout', [])
                       if v.get('scriptpubkey_address') == address)
            sent = sum((vi.get('prevout') or {}).get('value', 0) for vi in t.get('vin', [])
                       if (vi.get('prevout') or {}).get('scriptpubkey_address') == address)
            net = (recv - sent) / 1e8
            st = t.get('status', {}) or {}
            entries.append({
                'txid': t.get('txid'),
                'time': st.get('block_time'),
                'confirmed': st.get('confirmed', False),
                'direction': 'in' if net >= 0 else 'out',
                'amount': round(abs(net), 4),
            })
        notable = [e for e in entries if e['amount'] >= 0.1]
        activity = (notable if notable else entries)[:max(1, min(limit, 25))]
        return {'status': 'ready', 'address': address, 'activity': activity,
                'notable_only': bool(notable)}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'activity': []}


@app.get('/api/v1/whales/history')
def whale_history_feed(address: str, refresh: int = 0):
    """REAL balance-over-time for one whale, reconstructed from on-chain tx history."""
    try:
        meta = whale_col.find_one({'_id': '_meta'}) or {}
        price = meta.get('price')
        h = get_whale_history(address, refresh=bool(refresh))
        series = h.get('series') or []
        if not series:
            return {'status': 'empty', 'address': address, 'points': []}
        bal = h.get('balance')

        def chg(days):
            if len(series) < 2:
                return None
            cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            past = [p for p in series if p['date'] <= cutoff]
            base = past[-1]['bal'] if past else series[0]['bal']
            return round((series[-1]['bal'] or 0) - (base or 0), 2)

        points = [{'date': p['date'], 'bal': p['bal'],
                   'usd': (round(p['bal'] * price) if (p['bal'] and price) else None)}
                  for p in series]
        return {'status': 'ready', 'address': address,
                'name': _whale_name_by_addr.get(address, 'Whale'),
                'category': _whale_cat_by_addr.get(address, 'Whale'),
                'balance': bal, 'price': price,
                'change_30d': chg(30), 'change_90d': chg(90),
                'span_from': series[0]['date'], 'span_to': series[-1]['date'],
                'points': points, 'as_of': h.get('fetched_at'),
                'source': 'mempool.space (on-chain reconstruction)'}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'points': []}


@app.get('/api/v1/whales/impact')
def whale_impact_feed():
    """Aggregate whale accumulation/distribution trend (REAL, reconstructed on-chain)."""
    try:
        return {'status': 'ready', **compute_whale_impact()}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'contributors': []}


@app.get('/api/v1/whales/transactions')
def whale_tx_feed(min_btc: float = 50.0, limit: int = 40, refresh: int = 0):
    """Labeled large-transaction feed across all curated whales (REAL, keyless)."""
    try:
        c = get_whale_tx_feed(refresh=bool(refresh))
        feed = c.get('feed') or []
        if min_btc and min_btc != c.get('min_btc'):
            feed = [e for e in feed if (e.get('amount') or 0) >= min_btc]
        feed = feed[:max(1, min(limit, 100))]
        if not feed and not c.get('feed'):
            return {'status': 'computing', 'feed': []}
        return {'status': 'ready', 'feed': feed, 'price': c.get('price'),
                'min_btc': min_btc, 'as_of': c.get('as_of'),
                'source': c.get('source', 'mempool.space · curated entity labels')}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'feed': []}



@app.get('/api/v1/leverage')
def leverage_feed(timeframe: str = '4H', refresh: int = 0):
    """Leverage intelligence — long/short positioning, OI, funding, (est.) leverage,
    liquidations, squeeze risk & heatmap. Core is REAL (OKX); liquidations/heatmap/
    estimated-leverage percentile are DERIVED/DEMO and flagged demo=True."""
    try:
        data = get_leverage(timeframe if timeframe in _TF_HOURS else '4H', refresh=bool(refresh))
        if not data:
            return {'status': 'computing'}
        return {'status': 'ready', **data}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/etf-flows')
def etf_flows_feed(refresh: int = 0):
    """US spot Bitcoin ETF daily net flows ($M) — REAL, keyless (Farside via tftc.io full history)."""
    try:
        c = get_etf_flows(refresh=bool(refresh))
        daily = c.get('daily') or []
        if not daily:
            return {'status': 'computing', 'daily': []}
        totals = [d.get('total') for d in daily if d.get('total') is not None]
        net_1d = totals[0] if totals else None
        net_7d = round(sum(totals[:7]), 1) if totals else None
        net_30d = round(sum(totals[:30]), 1) if totals else None
        # cumulative over FULL history (oldest -> newest) for the long-trend chart.
        # Include real BTC close (from TFTC dataset) so the UI can overlay price vs demand.
        cum, running = [], 0.0
        for d in reversed(daily):
            running += (d.get('total') or 0)
            bc = d.get('btc_close')
            cum.append({'date': d['date'], 'cum': round(running, 1),
                        'price': (round(bc) if bc else None)})
        cum_total = round(running, 1)  # net flow since inception
        # downsample cumulative to <= ~180 points for a light payload
        if len(cum) > 180:
            step = len(cum) / 180.0
            cum_ds = [cum[int(i * step)] for i in range(180)]
            cum_ds[-1] = cum[-1]
            cum = cum_ds
        has_price = any(x.get('price') for x in cum)
        # per-issuer leaderboard over the RECENT 30-day window (current demand)
        issuers = c.get('issuers') or []
        recent = daily[:30]
        board = []
        for tick in issuers:
            s = round(sum((d.get('flows') or {}).get(tick) or 0 for d in recent), 1)
            board.append({'ticker': tick, 'window_total': s})
        board.sort(key=lambda x: x['window_total'], reverse=True)
        return {'status': 'ready', 'symbol': 'BTC', 'unit': 'USD millions',
                'issuers': issuers, 'daily': daily, 'cumulative': cum,
                'cum_total': cum_total, 'history_days': len(daily), 'has_price': has_price,
                'leaderboard': board, 'leaderboard_window': 30,
                'summary': c.get('summary') or {},
                'net_1d': net_1d, 'net_7d': net_7d, 'net_30d': net_30d,
                'source': c.get('source', 'tftc.io (Farside data)'),
                'as_of': c.get('fetched_at'),
                'span_from': daily[-1].get('date'), 'latest_date': daily[0].get('date')}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'daily': []}


@app.get('/api/v1/fear-greed')
def fear_greed_feed():
    """Crypto Fear & Greed Index (REAL, keyless — alternative.me)."""
    d = _misc_get('fear_greed', 30 * 60, compute_fear_greed)
    return {'status': 'ready', **d} if d else {'status': 'computing'}


@app.get('/api/v1/network-health')
def network_health_feed():
    """Bitcoin network health — hashrate, difficulty, mempool & fees (REAL, keyless — mempool.space)."""
    d = _misc_get('network_health', 10 * 60, compute_network_health)
    return {'status': 'ready', **d} if d else {'status': 'computing'}


@app.get('/api/v1/exchange-flows')
def exchange_flows_feed(refresh: int = 0):
    """Aggregate BTC held by tracked exchange wallets over time (REAL, on-chain reconstruction)."""
    if refresh:
        d = compute_exchange_flows()
        if d:
            misc_col.update_one({'_id': 'exchange_flows'}, {'$set': {'_id': 'exchange_flows',
                                'data': d, 'fetched_ts': time.time()}}, upsert=True)
    else:
        d = _misc_get('exchange_flows', 6 * 3600, compute_exchange_flows)
    return {'status': 'ready', **d} if d else {'status': 'computing'}


@app.get('/api/v1/admin/overview')
def admin_overview():
    """Admin dashboard: integrations, data freshness, usage, costs & system health."""
    now = time.time()

    def _age(ts):
        if not ts:
            return None
        return round((now - ts) / 60, 1)  # minutes

    def _cache_ts(col, _id, field='fetched_ts'):
        d = col.find_one({'_id': _id}, {field: 1, 'fetched_at': 1}) or {}
        return d.get(field)

    # ---- integrations (no secrets exposed) ----
    integrations = [
        {'name': 'Gemini (' + str(CHAT_MODEL) + ')', 'category': 'LLM / Albert', 'auth': 'Gemini API key',
         'status': 'Active' if (LLM_READY_KEY and _HAS_LLM) else 'Inactive', 'cost': 'Metered (Gemini API key)'},
        {'name': 'OKX public API', 'category': 'Derivatives / Leverage', 'auth': 'Keyless',
         'status': 'Active', 'cost': 'Free'},
        {'name': 'mempool.space', 'category': 'Whales / Network health', 'auth': 'Keyless',
         'status': 'Active', 'cost': 'Free'},
        {'name': 'blockchain.info', 'category': 'Whale balances', 'auth': 'Keyless', 'status': 'Active', 'cost': 'Free'},
        {'name': 'tftc.io (Farside data)', 'category': 'ETF flows', 'auth': 'Keyless', 'status': 'Active', 'cost': 'Free'},
        {'name': 'CoinGecko', 'category': 'Price', 'auth': 'Keyless', 'status': 'Active', 'cost': 'Free'},
        {'name': 'alternative.me', 'category': 'Fear & Greed', 'auth': 'Keyless', 'status': 'Active', 'cost': 'Free'},
        {'name': 'Glassnode / BGeometrics', 'category': 'Smart money on-chain', 'auth': 'User key (Glassnode)',
         'status': 'Active', 'cost': 'Free tier + user key'},
        {'name': 'CoinGlass', 'category': 'Liquidations / Leverage heatmap', 'auth': 'API key required',
         'status': 'Inactive', 'cost': 'Paid — not connected'},
        {'name': 'ElevenLabs', 'category': 'Albert voice', 'auth': 'API key required',
         'status': 'Inactive', 'cost': 'Paid — not connected'},
        {'name': 'Resend', 'category': 'Email digests & instant alerts', 'auth': 'API key (Resend)',
         'status': 'Active' if RESEND_API_KEY else 'Inactive',
         'cost': 'Free tier + user key' if RESEND_API_KEY else 'Not connected'},
    ]
    active = sum(1 for i in integrations if i['status'] == 'Active')

    # ---- data freshness (minutes since last successful fetch) ----
    freshness = [
        {'source': 'ETF flows', 'age_min': _age(_cache_ts(etf_col, 'btc'))},
        {'source': 'Whale balances', 'age_min': _age((whale_col.find_one({'_id': '_meta'}) or {}).get('fetched_ts'))},
        {'source': 'Leverage (4H)', 'age_min': _age(_cache_ts(lev_col, 'BTC:4H'))},
        {'source': 'Fear & Greed', 'age_min': _age(_cache_ts(misc_col, 'fear_greed'))},
        {'source': 'Network health', 'age_min': _age(_cache_ts(misc_col, 'network_health'))},
        {'source': 'Exchange flows', 'age_min': _age(_cache_ts(misc_col, 'exchange_flows'))},
        {'source': 'On-chain panels', 'age_min': _age(_cache_ts(onchain_col, 'btc'))},
    ]

    # ---- usage (real counters + DB doc counts) ----
    def _u(kind):
        d = usage_col.find_one({'_id': f'{kind}:total'}) or {}
        t = usage_col.find_one({'_id': f'{kind}:{datetime.date.today().isoformat()}'}) or {}
        return {'total': d.get('count', 0), 'today': t.get('count', 0)}
    ins, brf = _u('llm_insight'), _u('llm_brief')
    llm_total = ins['total'] + brf['total']
    llm_today = ins['today'] + brf['today']
    # rough cost estimate (clearly labelled — NOT a billed figure)
    est_per_call_usd = 0.002  # conservative rough estimate for a Gemini Flash insight
    usage = {
        'llm_calls_total': llm_total, 'llm_calls_today': llm_today,
        'llm_insight': ins, 'llm_brief': brf,
        'cached_insights': insights_col.count_documents({}),
        'alerts_total': smart_alerts_col.count_documents({}),
        'whales_tracked': whale_col.count_documents({'_id': {'$ne': '_meta'}}),
        'runs_logged': runs_col.count_documents({}),
    }
    costs = {
        'note': ('Free/keyless feeds cost $0. The only metered cost is the LLM (Gemini, called '
                 'directly via your Google AI Studio API key). The figures below are ROUGH estimates '
                 'from call counts — NOT billed amounts. See your Google AI Studio / Cloud billing '
                 'dashboard for exact usage & spend.'),
        'emergent': {
            'service': 'Google Gemini API (google-genai SDK)',
            'model': str(CHAT_MODEL),
            'status': 'Active' if (LLM_READY_KEY and _HAS_LLM) else 'Inactive',
            'llm_calls_total': llm_total,
            'llm_calls_today': llm_today,
            'est_per_call_usd': est_per_call_usd,
            'est_cost_total_usd': round(llm_total * est_per_call_usd, 2),
            'est_cost_today_usd': round(llm_today * est_per_call_usd, 2),
            'billing_note': 'Estimate only — actual usage & spend are shown in your Google AI Studio / Cloud billing dashboard.',
        },
        'est_llm_cost_usd': round(llm_total * est_per_call_usd, 2),
        'est_llm_cost_today_usd': round(llm_today * est_per_call_usd, 2),
        'paid_feeds_active': [i['name'] for i in integrations if i['status'] == 'Active' and 'key' in i['auth'].lower()],
        'paid_feeds_available': [i['name'] for i in integrations if i['status'] == 'Inactive'],
    }

    # ---- scheduler jobs ----
    jobs = []
    try:
        for j in (_scheduler.get_jobs() if _scheduler else []):
            jobs.append({'id': j.id, 'next_run': (j.next_run_time.isoformat() if j.next_run_time else None)})
    except Exception:  # noqa
        pass

    # ---- collection sizes ----
    collections = {}
    try:
        for cn in ['runs', 'smart_alerts', 'whale_wallets', 'whale_history', 'whale_tx_feed',
                   'etf_flows', 'leverage_engine', 'onchain_engine', 'albert_insights',
                   'misc_cache', 'usage_stats']:
            try:
                collections[cn] = db[cn].count_documents({})
            except Exception:  # noqa
                pass
    except Exception:  # noqa
        pass

    return {'status': 'ready', 'as_of': datetime.datetime.utcnow().isoformat(),
            'integrations': integrations, 'integrations_active': active,
            'integrations_total': len(integrations), 'freshness': freshness,
            'usage': usage, 'costs': costs, 'scheduler_jobs': jobs, 'collections': collections}


# =====================================================================
# AUDIT PHASE 1 & 2: Composite spot price (multi-venue + confidence/provenance),
# cross-asset context, GDELT news signals, FRED macro (key-gated).
# Binance is geo-blocked (HTTP 451) from this host, so venues = Coinbase, Kraken, OKX.
# =====================================================================
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')


def _confidence(n_ok, spread_pct):
    """HIGH = >=3 venues agree tightly; MEDIUM = 2 agree; LOW = 1 or wide disagreement."""
    if n_ok >= 3 and spread_pct is not None and spread_pct < 0.5:
        return 'HIGH'
    if n_ok >= 2 and (spread_pct is None or spread_pct < 1.5):
        return 'MEDIUM'
    return 'LOW'


@app.get('/api/v1/composite-price')
def composite_price():
    """Ask Albert Composite Bitcoin Price — median of independent venues with outlier detection,
    fallback chain and data-confidence/provenance. REAL, keyless."""
    venues = []
    def add(name, fn):
        t = time.time()
        try:
            v = fn()
            if v and v > 0:
                venues.append({'source': name, 'price': round(float(v), 2),
                               'latency_ms': int((time.time() - t) * 1000), 'ok': True})
        except Exception:  # noqa
            venues.append({'source': name, 'price': None, 'ok': False})
    add('Coinbase', lambda: float(_engine_get('https://api.coinbase.com/v2/prices/BTC-USD/spot')['data']['amount']))
    add('Kraken', lambda: float(list(_engine_get('https://api.kraken.com/0/public/Ticker?pair=XBTUSD')['result'].values())[0]['c'][0]))
    add('OKX', lambda: float(_engine_get('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT')['data'][0]['last']))
    add('CoinGecko', lambda: float(_engine_get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd')['bitcoin']['usd']))
    prices = sorted(v['price'] for v in venues if v.get('ok') and v.get('price'))
    n = len(prices)
    if not n:
        return {'status': 'stale', 'confidence': 'LOW', 'venues': venues,
                'note': 'No live venue responded — no composite price available.'}
    median = prices[n // 2] if n % 2 else round((prices[n // 2 - 1] + prices[n // 2]) / 2, 2)
    spread_pct = round((prices[-1] - prices[0]) / median * 100, 3) if median else None
    # outlier detection: flag venues >0.75% from median
    outliers = []
    for v in venues:
        if v.get('ok') and v.get('price') and median:
            dev = abs(v['price'] - median) / median * 100
            v['dev_pct'] = round(dev, 3)
            if dev > 0.75:
                v['outlier'] = True
                outliers.append(v['source'])
    good = [v['price'] for v in venues if v.get('ok') and not v.get('outlier')]
    composite = round(sum(good) / len(good), 2) if good else median
    return {'status': 'ready', 'composite': composite, 'median': median,
            'venue_count': n, 'spread_pct': spread_pct, 'outliers': outliers,
            'confidence': _confidence(n, spread_pct), 'venues': venues,
            'as_of': datetime.datetime.utcnow().isoformat(),
            'fallback_chain': ['Coinbase', 'Kraken', 'OKX', 'CoinGecko (aggregator)'],
            'method': 'Outlier-trimmed mean of independent exchange feeds (venues >0.75% from median excluded).'}


@app.get('/api/v1/cross-asset')
def cross_asset():
    """Broader crypto-market context — dominance, ETH/BTC, total mcap, stablecoins. REAL (CoinGecko)."""
    d = _misc_get('cross_asset', 15 * 60, _compute_cross_asset)
    return {'status': 'ready', **d} if d else {'status': 'computing'}


def _compute_cross_asset():
    g = _engine_get('https://api.coingecko.com/api/v3/global') or {}
    data = g.get('data') or {}
    mc = data.get('market_cap_percentage') or {}
    total = (data.get('total_market_cap') or {}).get('usd')
    # ETH/BTC from OKX (native market — avoids a second rate-limited CoinGecko call)
    ethbtc = None
    try:
        ethbtc = float((_okx('/api/v5/market/ticker', {'instId': 'ETH-BTC'}) or [{}])[0].get('last'))
    except Exception:  # noqa
        pass
    # If CoinGecko /global was rate-limited/empty, fall back to the most recent BTC
    # dominance snapshot stored by the daily compute (never cache a bogus 0%).
    if not mc.get('btc'):
        snap = dominance_col.find_one(sort=[('date', -1)], projection={'_id': 0})
        if not snap or not snap.get('dominance'):
            return None
        btc_dom = round(float(snap['dominance']), 2)
        total = snap.get('total_mcap') or total
        regime = ('Risk-on (alts gaining)' if btc_dom < 52
                  else 'Risk-off (BTC dominant)' if btc_dom > 58 else 'Balanced')
        return {'btc_dominance': btc_dom, 'eth_dominance': None,
                'eth_btc': (round(ethbtc, 5) if ethbtc else None),
                'total_market_cap_usd': total, 'stablecoin_mcap_usd': 0,
                'mcap_change_24h': 0, 'regime': regime, 'confidence': 'MEDIUM',
                'read': (f"BTC dominance is {btc_dom}% ({regime.lower()}); ETH/BTC at "
                         f"{(round(ethbtc,5) if ethbtc else 'n/a')}. Dominance is from the latest stored "
                         f"snapshot (CoinGecko /global is rate-limiting this host right now)."),
                'source': 'CoinGecko (stored snapshot) + OKX ETH-BTC'}
    # stablecoin caps (best-effort; tolerate CoinGecko rate limits)
    stable = 0
    try:
        px = _engine_get('https://api.coingecko.com/api/v3/simple/price?ids=tether,usd-coin&vs_currencies=usd&include_market_cap=true') or {}
        stable = round(((px.get('tether') or {}).get('usd_market_cap', 0) or 0)
                       + ((px.get('usd-coin') or {}).get('usd_market_cap', 0) or 0))
    except Exception:  # noqa
        pass
    btc_dom = round(mc.get('btc', 0), 2)
    regime = ('Risk-on (alts gaining)' if btc_dom and btc_dom < 52
              else 'Risk-off (BTC dominant)' if btc_dom and btc_dom > 58 else 'Balanced')
    return {'btc_dominance': btc_dom, 'eth_dominance': round(mc.get('eth', 0), 2),
            'eth_btc': (round(ethbtc, 5) if ethbtc else None),
            'total_market_cap_usd': total, 'stablecoin_mcap_usd': stable,
            'mcap_change_24h': round(data.get('market_cap_change_percentage_24h_usd', 0), 2),
            'regime': regime, 'confidence': 'MEDIUM',
            'read': (f"BTC dominance is {btc_dom}% ({regime.lower()}); ETH/BTC at "
                     f"{(round(ethbtc,5) if ethbtc else 'n/a')}. Total crypto market cap "
                     f"${round((total or 0)/1e9)}B. Dominance is a single-aggregator read (CoinGecko)."),
            'source': 'CoinGecko /global + simple price'}


@app.get('/api/v1/news-signals')
def news_signals():
    """Structured Bitcoin news/media signals from GDELT (event tone & attention). REAL, keyless.
    We extract SIGNALS (tone, coverage trend) — not article text."""
    d = _misc_get_async('news_signals', 60 * 60, _compute_news_signals)
    if d:
        return {'status': 'ready', **d}
    return {'status': 'unavailable', 'active': False, 'confidence': 'LOW',
            'reason': 'News-tone data is being fetched — GDELT rate-limits this host. '
                      'It will populate automatically in a few seconds; refresh shortly.',
            'source': 'GDELT 2.0 Doc API (tone timeline)'}


def _compute_news_signals():
    # GDELT free API rate-limits shared IPs (1 req / 5s); retry with backoff.
    j = None
    for attempt in range(3):
        j = _engine_get('https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=timelinetone&format=json&timespan=21d')
        if j and (j.get('timeline')):
            break
        j = None
        time.sleep(6)
    j = j or {}
    tl = j.get('timeline') or []
    series = tl[0]['data'] if tl else []
    pts = [{'date': p['date'][:8], 'tone': round(p['value'], 3)} for p in series]
    tones = [p['tone'] for p in pts]
    if not tones:
        return None
    latest = tones[-1]
    avg = round(sum(tones) / len(tones), 3)
    recent = round(sum(tones[-3:]) / len(tones[-3:]), 3)
    direction = ('Improving' if recent > avg + 0.3 else 'Worsening' if recent < avg - 0.3 else 'Stable')
    mood = ('Positive' if latest > 0.5 else 'Negative' if latest < -0.5 else 'Neutral')
    return {'tone_latest': latest, 'tone_avg_21d': avg, 'tone_recent_3d': recent,
            'mood': mood, 'direction': direction, 'series': pts, 'confidence': 'MEDIUM',
            'read': (f"Global Bitcoin news tone is {mood.lower()} ({latest}) and {direction.lower()} vs its "
                     f"21-day average ({avg}). Tone is a media-sentiment SIGNAL from GDELT, not a price call."),
            'source': 'GDELT 2.0 Doc API (tone timeline)'}


@app.get('/api/v1/macro-fred')
def macro_fred():
    """US macro from FRED (Fed Funds, yields, CPI, M2). Needs FRED_API_KEY; otherwise inactive."""
    if not FRED_API_KEY:
        return {'status': 'inactive', 'active': False,
                'reason': 'No FRED data available — set FRED_API_KEY (free at fred.stlouisfed.org) to activate.'}
    d = _misc_get('macro_fred', 6 * 3600, _compute_macro_fred)
    return {'status': 'ready', **d} if d else {'status': 'computing'}


def _compute_macro_fred():
    series = {'DFF': 'Fed Funds Rate', 'DGS2': '2Y Treasury', 'DGS10': '10Y Treasury',
              'T10Y2Y': '10Y-2Y Spread', 'CPIAUCSL': 'CPI', 'M2SL': 'M2 Money Supply',
              'UNRATE': 'Unemployment'}
    out = []
    for sid, label in series.items():
        try:
            j = _engine_get(f'https://api.stlouisfed.org/fred/series/observations?series_id={sid}'
                            f'&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=2')
            obs = (j or {}).get('observations') or []
            if obs:
                val = float(obs[0]['value'])
                prev = float(obs[1]['value']) if len(obs) > 1 and obs[1]['value'] not in ('.', '') else None
                out.append({'id': sid, 'label': label, 'value': val,
                            'change': (round(val - prev, 3) if prev is not None else None),
                            'date': obs[0]['date']})
        except Exception:  # noqa
            pass
    return {'series': out, 'confidence': 'HIGH', 'source': 'FRED (St. Louis Fed)',
            'note': 'Latest published values. Use ALFRED vintages for look-ahead-safe backtesting.'} if out else None





@app.get('/api/v1/alerts')
def alerts_feed(limit: int = 50, symbol: str = None):
    try:
        return {'status': 'ready', **get_smart_alerts(limit, symbol)}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'alerts': [], 'unseen': 0}


@app.post('/api/v1/alerts/ack')
def alerts_ack(payload: dict = Body(default={})):
    ids = (payload or {}).get('ids')
    symbol = (payload or {}).get('symbol')
    flt = _alert_symbol_filter(symbol)
    try:
        if ids:
            smart_alerts_col.update_many({'id': {'$in': ids}}, {'$set': {'seen': True}})
        else:
            # Mark all unseen for the selected coin scope as read.
            smart_alerts_col.update_many({**flt, 'seen': False}, {'$set': {'seen': True}})
        return {'status': 'ok', 'unseen': smart_alerts_col.count_documents({**flt, 'seen': False})}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


# ---------------------------------------------------------------------------
# Email — daily Alert Digest via Resend (admin-managed recipient list)
# ---------------------------------------------------------------------------
_SEV_COLOR = {'high': '#ef4444', 'critical': '#dc2626', 'medium': '#f59e0b',
              'warning': '#f59e0b', 'low': '#3b82f6', 'info': '#64748b'}


def _recipient_list():
    try:
        return list(email_recipients_col.find({}, {'_id': 0}).sort('email', 1))
    except Exception:  # noqa
        traceback.print_exc()
        return []


def _unsub_token(email):
    import hmac
    import hashlib
    return hmac.new(UNSUB_SECRET.encode(), (email or '').lower().encode(),
                    hashlib.sha256).hexdigest()[:32]


def _unsub_url(email):
    from urllib.parse import quote
    if not PUBLIC_BASE_URL:
        return ''
    return f"{PUBLIC_BASE_URL}/api/v1/email/unsubscribe?e={quote(email)}&t={_unsub_token(email)}"


_INSTANT_SEV_CHOICES = ('low', 'medium', 'high', 'critical')


def _instant_severities():
    doc = email_settings_col.find_one({'_id': 'instant'}) or {}
    sev = doc.get('severities')
    if not isinstance(sev, list):
        return ['high', 'critical']
    clean = [s for s in sev if s in _INSTANT_SEV_CHOICES]
    return clean or ['high', 'critical']


def _send_to_recipients(recips, subject, html, text):
    """Send individually per recipient (privacy) with a per-recipient unsubscribe link + header."""
    if not EMAIL_ALERTS_ENABLED:
        # Email delivery is disabled — alerts are delivered via in-app + browser notifications.
        return {'ok': False, 'disabled': True, 'sent': 0, 'error': 'email alerts disabled'}
    sent, last_id, err = 0, None, None
    for email in recips:
        url = _unsub_url(email)
        h = html.replace('{{UNSUB}}', url or '#')
        t = (text or '').replace('{{UNSUB}}', url or '')
        headers = None
        if url:
            headers = {'List-Unsubscribe': f'<{url}>',
                       'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
        r = send_email(email, subject, h, t, headers=headers)
        if r.get('ok'):
            sent += 1
            last_id = r.get('id')
        else:
            err = r.get('error')
    return {'ok': sent > 0, 'sent': sent, 'id': last_id, 'error': err, 'recipients': len(recips)}


def _digest_sparkline_html(closes, up):
    closes = [c for c in closes if isinstance(c, (int, float))][-30:]
    if len(closes) < 2:
        return ''
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1
    col = '#34d399' if up else '#f87171'
    bars = ''
    for c in closes:
        h = 6 + int((c - lo) / rng * 52)
        bars += (f'<td valign="bottom" style="padding:0 1px;">'
                 f'<div style="width:7px;height:{h}px;background:{col};border-radius:2px;"></div></td>')
    return (f'<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">'
            f'Price · last {len(closes)} days</div>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="height:60px;"><tr>{bars}</tr></table>')


def _digest_forecast_html(forecasts):
    if not forecasts:
        return ''
    label = {'24H': 'Next 24 hours', '7D': 'Next week', '30D': 'Next month'}
    cards = ''
    for f in forecasts[:3]:
        hz = f.get('horizon')
        lean = (f.get('lean') or '').upper()
        up = lean == 'UP'
        col = '#34d399' if up else ('#f87171' if lean == 'DOWN' else '#94a3b8')
        arrow = '&#9650;' if up else ('&#9660;' if lean == 'DOWN' else '&#9632;')
        higher = f.get('higher')
        higher_txt = '—' if higher is None else f'{higher:g}%'

        def _m(v):
            return '—' if not isinstance(v, (int, float)) else f'${v:,.0f}'
        cards += (
            f'<td width="33%" valign="top" style="padding:6px;">'
            f'<div style="background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:12px;">'
            f'<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;">{label.get(hz, hz)}</div>'
            f'<div style="font-size:15px;font-weight:800;color:{col};margin:4px 0;">{arrow} {lean or "—"} · {higher_txt} higher</div>'
            f'<div style="font-size:12px;color:#94a3b8;">Base <b style="color:#e2e8f0;">{_m(f.get("base"))}</b></div>'
            f'<div style="font-size:11px;color:#64748b;">Bull {_m(f.get("bull"))} &middot; Bear {_m(f.get("bear"))}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-top:4px;">Confidence: {f.get("confidence") or "—"}</div>'
            f'</div></td>'
        )
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{cards}</tr></table>')


def build_daily_digest():
    """Build (subject, html, text, alert_count) — a richer 'morning brief': signal, price
    sparkline, CryptoMarkAI forecast horizons, and the last 24h of BTC alerts."""
    now = datetime.datetime.utcnow()
    cutoff = (now - datetime.timedelta(hours=24)).isoformat()
    try:
        alerts = list(smart_alerts_col.find(
            {'symbol': 'BTC', 'ts': {'$gte': cutoff}}, {'_id': 0}
        ).sort('ts', -1).limit(50))
    except Exception:  # noqa
        alerts = []
    run = runs_col.find_one(sort=[('created_at', -1)]) or {}
    quant = run.get('quant') or {}
    signal = run.get('signal') or quant.get('signal') or 'N/A'
    score = run.get('quant_score')
    if score is None:
        score = quant.get('score')
    score_txt = '—' if score is None else str(score)
    date_str = now.strftime('%d %b %Y')
    last_close = run.get('last_close')
    day_change = run.get('day_change_pct')
    forecasts = run.get('forecasts') or []
    closes = [c.get('c') for c in ((run.get('chart') or {}).get('ohlc') or []) if isinstance(c, dict)]
    up_trend = (isinstance(day_change, (int, float)) and day_change >= 0) or (str(signal).upper() == 'UP')

    price_txt = '—' if not isinstance(last_close, (int, float)) else f'${last_close:,.0f}'
    chg_col = '#34d399' if (isinstance(day_change, (int, float)) and day_change >= 0) else '#f87171'
    chg_txt = '' if not isinstance(day_change, (int, float)) else \
        f' <span style="color:{chg_col};">({day_change:+.2f}% 24h)</span>'

    brief = (
        '<div style="padding:18px 24px;border-bottom:1px solid #1e293b;">'
        f'<div style="font-size:22px;font-weight:800;color:#e2e8f0;">{price_txt}{chg_txt}</div>'
        f'{_digest_sparkline_html(closes, up_trend)}'
        '</div>'
    )
    forecast_html = _digest_forecast_html(forecasts)
    forecast_block = (
        '<div style="padding:14px 18px 4px;">'
        '<div style="font-size:12px;font-weight:700;color:#f59e0b;text-transform:uppercase;letter-spacing:.05em;padding:0 6px 4px;">'
        'Albert\u2019s outlook</div>'
        f'{forecast_html}</div>'
    ) if forecast_html else ''

    if alerts:
        rows = ''
        for a in alerts:
            sev = (a.get('severity') or 'info').lower()
            col = _SEV_COLOR.get(sev, '#64748b')
            title = (a.get('title') or a.get('category') or 'Alert')
            msg = (a.get('message') or '')
            when = (a.get('ts') or '')[:16].replace('T', ' ')
            rows += (
                f'<tr><td style="padding:12px 14px;border-bottom:1px solid #1e293b;border-left:4px solid {col};">'
                f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:{col};font-weight:700;">{sev}</div>'
                f'<div style="font-size:15px;color:#e2e8f0;font-weight:600;margin:2px 0;">{title}</div>'
                f'<div style="font-size:13px;color:#94a3b8;">{msg}</div>'
                f'<div style="font-size:11px;color:#64748b;margin-top:4px;">{when} UTC</div>'
                f'</td></tr>'
            )
    else:
        rows = ('<tr><td style="padding:18px;color:#94a3b8;font-size:14px;">'
                'No new alerts in the last 24 hours — markets were quiet.</td></tr>')

    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;background:#0b1220;padding:24px;">'
        '<div style="max-width:640px;margin:0 auto;background:#0f172a;border:1px solid #1e293b;border-radius:14px;overflow:hidden;">'
        '<div style="padding:22px 24px;background:linear-gradient(135deg,#f59e0b22,#1e293b);border-bottom:1px solid #1e293b;">'
        '<div style="font-size:20px;font-weight:800;color:#f59e0b;">CryptoMarkAI · Daily Brief</div>'
        f'<div style="font-size:13px;color:#94a3b8;margin-top:6px;">{date_str} · Current signal '
        f'<b style="color:#e2e8f0;">{signal}</b> (score {score_txt}) · {len(alerts)} alert(s) in 24h</div>'
        '</div>'
        f'{brief}'
        f'{forecast_block}'
        '<div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;padding:16px 24px 6px;">'
        f'Alerts · last 24h ({len(alerts)})</div>'
        f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
        '<div style="padding:16px 24px;border-top:1px solid #1e293b;font-size:11px;color:#64748b;">'
        'You are receiving this because your address is on the CryptoMarkAI digest list. '
        '<a href="{{UNSUB}}" style="color:#f59e0b;">Unsubscribe</a>. '
        'This is market information, not financial advice.'
        '</div></div></div>'
    )
    text_lines = [f'CryptoMarkAI Daily Brief — {date_str}',
                  f'Signal: {signal} (score {score_txt}) · Price {price_txt}'
                  + ('' if not isinstance(day_change, (int, float)) else f' ({day_change:+.2f}% 24h)'), '']
    for f in forecasts[:3]:
        text_lines.append(f"Outlook {f.get('horizon')}: {f.get('lean')} · {f.get('higher')}% higher · "
                          f"base ${f.get('base')}")
    text_lines.append('')
    for a in alerts:
        text_lines.append(f"- [{(a.get('severity') or 'info').upper()}] "
                          f"{a.get('title') or a.get('category')}: {a.get('message') or ''}")
    if not alerts:
        text_lines.append('No new alerts in the last 24 hours.')
    text_lines.append('\nUnsubscribe: {{UNSUB}}')
    subject = f'CryptoMarkAI Daily Brief — {signal} · {date_str}'
    return subject, html, '\n'.join(text_lines), len(alerts)


def send_daily_digest_bg(force=False):
    """Build & send the digest to all recipients. Idempotent per UTC day unless force=True."""
    try:
        recips = [d.get('email') for d in _recipient_list() if d.get('email')]
        if not recips:
            print('[digest] no recipients configured; skipping', flush=True)
            return {'ok': False, 'error': 'No recipients configured.'}
        if not resend_configured():
            return {'ok': False, 'error': 'RESEND_API_KEY is not configured on the server.'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        if not force:
            res = email_log_col.update_one(
                {'_id': f'digest_{today}'},
                {'$setOnInsert': {'_id': f'digest_{today}', 'kind': 'digest_guard',
                                  'ts': datetime.datetime.utcnow().isoformat()}},
                upsert=True)
            if res.upserted_id is None:
                print('[digest] already sent today; skipping', flush=True)
                return {'ok': False, 'error': 'Digest already sent today.'}
        subject, html, text, count = build_daily_digest()
        result = _send_to_recipients(recips, subject, html, text)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'digest_send', 'recipients': len(recips), 'alert_count': count,
                                      'ok': result.get('ok'), 'resend_id': result.get('id'),
                                      'error': result.get('error'), 'forced': bool(force)})
        except Exception:  # noqa
            pass
        return {**result, 'recipients': len(recips), 'alert_count': count}
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def _email_admin_guard(payload):
    return _passcode_ok((payload or {}).get('passcode', ''))


@app.post('/api/v1/email/recipients/list')
def email_recipients_list_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    return {'status': 'ok', 'recipients': _recipient_list(), 'from': RESEND_FROM,
            'configured': resend_configured(),
            'digest_time': f'{DIGEST_HOUR:02d}:{DIGEST_MINUTE:02d}', 'digest_tz': DIGEST_TZ,
            'instant_severities': _instant_severities(),
            'weekly_day': 'Sun', 'weekly_time': f'{WEEKLY_HOUR:02d}:{WEEKLY_MINUTE:02d}'}


@app.post('/api/v1/email/recipients')
def email_recipients_add_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    email = ((payload or {}).get('email') or '').strip().lower()
    name = ((payload or {}).get('name') or '').strip()
    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        return {'status': 'error', 'message': 'Enter a valid email address.'}
    try:
        email_recipients_col.update_one(
            {'_id': email},
            {'$set': {'_id': email, 'email': email, 'name': name,
                      'added_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}
    return {'status': 'ok', 'recipients': _recipient_list()}


@app.post('/api/v1/email/recipients/delete')
def email_recipients_delete_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    email = ((payload or {}).get('email') or '').strip().lower()
    try:
        email_recipients_col.delete_one({'_id': email})
    except Exception as e:  # noqa
        return {'status': 'error', 'message': str(e)}
    return {'status': 'ok', 'recipients': _recipient_list()}


@app.post('/api/v1/email/test')
def email_test_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    if not resend_configured():
        return {'status': 'error', 'message': 'RESEND_API_KEY is not configured on the server.'}
    to = ((payload or {}).get('to') or '').strip().lower()
    recips = [to] if to else [d.get('email') for d in _recipient_list() if d.get('email')]
    if not recips:
        return {'status': 'error', 'message': 'No recipient — add one to the list or enter a test address.'}
    html = ('<div style="font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;border-radius:12px;">'
            '<h2 style="color:#f59e0b;margin:0 0 8px;">CryptoMarkAI test email ✅</h2>'
            '<p style="color:#94a3b8;">Your Resend integration is working. Daily alert digests will arrive here.</p></div>')
    result = send_email(recips, 'CryptoMarkAI — Test email ✅', html,
                        'CryptoMarkAI test email. Your Resend integration is working.')
    try:
        email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                  'kind': 'test', 'recipients': len(recips), 'ok': result.get('ok'),
                                  'resend_id': result.get('id'), 'error': result.get('error')})
    except Exception:  # noqa
        pass
    if result.get('ok'):
        return {'status': 'ok', 'message': f'Test email sent to {len(recips)} recipient(s).',
                'id': result.get('id')}
    return {'status': 'error', 'message': result.get('error') or 'Send failed.'}


@app.post('/api/v1/email/digest/send-now')
def email_digest_now_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    result = send_daily_digest_bg(force=True)
    if result.get('ok'):
        return {'status': 'ok',
                'message': f"Digest sent to {result.get('recipients')} recipient(s) "
                           f"({result.get('alert_count')} alerts in 24h).",
                'id': result.get('id')}
    return {'status': 'error', 'message': result.get('error') or 'Send failed.'}


def build_instant_alert_email(alerts):
    n = len(alerts)
    rows = ''
    for a in alerts:
        sev = (a.get('severity') or 'high').lower()
        col = _SEV_COLOR.get(sev, '#ef4444')
        when = (a.get('ts') or '')[:16].replace('T', ' ')
        rows += (
            f'<tr><td style="padding:12px 14px;border-bottom:1px solid #1e293b;border-left:4px solid {col};">'
            f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:{col};font-weight:700;">{sev}</div>'
            f'<div style="font-size:15px;color:#e2e8f0;font-weight:600;margin:2px 0;">{a.get("title") or a.get("category") or "Alert"}</div>'
            f'<div style="font-size:13px;color:#94a3b8;">{a.get("message") or ""}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-top:4px;">{when} UTC</div>'
            f'</td></tr>'
        )
    top = alerts[0] if alerts else {}
    subject = f'CryptoMarkAI Alert: {top.get("title") or "High-priority signal"}' + (f' (+{n - 1} more)' if n > 1 else '')
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;background:#0b1220;padding:24px;">'
        '<div style="max-width:640px;margin:0 auto;background:#0f172a;border:1px solid #1e293b;border-radius:14px;overflow:hidden;">'
        '<div style="padding:20px 24px;background:linear-gradient(135deg,#ef444422,#1e293b);border-bottom:1px solid #1e293b;">'
        '<div style="font-size:19px;font-weight:800;color:#f87171;">&#9888; CryptoMarkAI Instant Alert</div>'
        f'<div style="font-size:13px;color:#94a3b8;margin-top:6px;">{n} high-priority signal(s) just triggered.</div>'
        '</div>'
        f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
        '<div style="padding:16px 24px;border-top:1px solid #1e293b;font-size:11px;color:#64748b;">'
        'Sent immediately because these are high-severity alerts. '
        '<a href="{{UNSUB}}" style="color:#f59e0b;">Unsubscribe</a>. Market information, not financial advice.'
        '</div></div></div>'
    )
    text = 'CryptoMarkAI Instant Alert\n\n' + '\n'.join(
        f"- [{(a.get('severity') or 'high').upper()}] {a.get('title') or a.get('category')}: {a.get('message') or ''}"
        for a in alerts) + '\n\nUnsubscribe: {{UNSUB}}'
    return subject, html, text


def check_model_decay_alert(quant_val):
    """Fire a one-off email when a model's rolling Brier slope turns positive AND the latest
    rolling Brier is above the 0.24 decay threshold. Edge-triggered (only on healthy->decaying
    transition) so it never spams; reuses the Resend recipient pipeline."""
    try:
        if not quant_val:
            return {'ok': False, 'reason': 'no validation'}
        slope = quant_val.get('rolling_brier_slope')
        hist = quant_val.get('rolling_brier_history') or []
        latest = hist[-1] if hist else None
        decaying = (slope is not None and slope > 0 and latest is not None and latest > 0.24)

        prev = misc_col.find_one({'_id': 'decay_alert_state'}) or {}
        was_decaying = bool(prev.get('decaying'))
        last_sent = prev.get('last_sent_at')
        # 7-day cooldown so a flapping model can't email repeatedly
        cooldown_ok = True
        if last_sent:
            try:
                elapsed = (datetime.datetime.utcnow()
                           - datetime.datetime.fromisoformat(last_sent)).total_seconds()
                cooldown_ok = elapsed >= 7 * 24 * 3600
            except Exception:  # noqa
                cooldown_ok = True
        misc_col.update_one({'_id': 'decay_alert_state'},
                            {'$set': {'decaying': decaying, 'slope': slope, 'latest_brier': latest,
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        if not (decaying and not was_decaying):
            return {'ok': True, 'sent': 0, 'decaying': decaying}
        if not cooldown_ok:
            return {'ok': True, 'sent': 0, 'decaying': decaying, 'reason': 'cooldown (7d)'}
        if not resend_configured():
            return {'ok': False, 'error': 'resend not configured'}
        recips = [r.get('email') for r in _recipient_list() if r.get('email')]
        if not recips:
            return {'ok': False, 'error': 'no recipients'}
        subject = '⚠️ Ask Albert model decay detected — rolling Brier rising'
        html = (f"<div style='font-family:system-ui,sans-serif;color:#0f172a'>"
                f"<h2 style='margin:0 0 8px'>Model decay alert</h2>"
                f"<p>The walk-forward model's <b>rolling Brier score is trending up</b> "
                f"(slope <b>{slope}</b>, latest <b>{latest}</b>), crossing the 0.24 decay threshold "
                f"(0.25 = a coin flip).</p>"
                f"<p>Decaying horizons are being auto-down-weighted in the ensemble. Review the "
                f"Quant-Grade Validation panel on the Performance screen.</p>"
                f"<p style='color:#64748b;font-size:12px'>Sent automatically by Ask Albert.</p></div>")
        text = (f"Ask Albert model decay alert. Rolling Brier slope {slope}, latest {latest} "
                f"(>0.24 decay threshold). Decaying horizons are auto-down-weighted.")
        result = _send_to_recipients(recips, subject, html, text)
        if result.get('ok'):
            misc_col.update_one({'_id': 'decay_alert_state'},
                                {'$set': {'last_sent_at': datetime.datetime.utcnow().isoformat()}},
                                upsert=True)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'decay_alert', 'recipients': len(recips),
                                      'slope': slope, 'latest_brier': latest,
                                      'ok': result.get('ok'), 'resend_id': result.get('id'),
                                      'error': result.get('error')})
        except Exception:  # noqa
            pass
        return {**result, 'sent': 1 if result.get('ok') else 0}
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def check_drift_circuit_alert(drift):
    """Edge-triggered admin email when the Feature-Drift Circuit Breaker trips
    (stable/watch -> breaker transition). 24h cooldown so a flapping regime can't
    spam. Reuses the Resend recipient pipeline. Never raises."""
    try:
        if not drift:
            return {'ok': False, 'reason': 'no drift assessment'}
        active = bool(drift.get('circuit_breaker'))
        prev = misc_col.find_one({'_id': 'drift_alert_state'}) or {}
        was_active = bool(prev.get('active'))
        last_sent = prev.get('last_sent_at')
        cooldown_ok = True
        if last_sent:
            try:
                elapsed = (datetime.datetime.utcnow()
                           - datetime.datetime.fromisoformat(last_sent)).total_seconds()
                cooldown_ok = elapsed >= 24 * 3600
            except Exception:  # noqa
                cooldown_ok = True
        misc_col.update_one({'_id': 'drift_alert_state'},
                            {'$set': {'active': active, 'max_psi': drift.get('max_psi'),
                                      'completeness': drift.get('data_completeness_pct'),
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        if not (active and not was_active):
            return {'ok': True, 'sent': 0, 'active': active}
        if not cooldown_ok:
            return {'ok': True, 'sent': 0, 'active': active, 'reason': 'cooldown (24h)'}
        push_alert('Model', 'high', 'Circuit breaker tripped',
                   'Feature-drift circuit breaker tripped — model reverted to a conservative rule-based '
                   'trend model and confidence downgraded to Low. Auto-recovers when inputs normalise.',
                   'drift_breaker')
        misc_col.update_one({'_id': 'drift_alert_state'},
                            {'$set': {'last_sent_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        if not resend_configured():
            return {'ok': True, 'sent': 1, 'notified': True}
        recips = [r.get('email') for r in _recipient_list() if r.get('email')]
        if not recips:
            return {'ok': False, 'error': 'no recipients'}
        reasons = '<br>'.join('• ' + r for r in (drift.get('reasons') or [])) or 'Distribution shift / feed gap.'
        fb = drift.get('fallback_signal') or {}
        subject = '🛑 Ask Albert circuit breaker tripped — model reverted to rule-based'
        html = (f"<div style='font-family:system-ui,sans-serif;color:#0f172a'>"
                f"<h2 style='margin:0 0 8px'>Feature-drift circuit breaker</h2>"
                f"<p>The ML model tripped its safety breaker and Ask Albert has fallen back to a "
                f"<b>conservative rule-based trend model</b>. Model confidence is downgraded to "
                f"<b>Low</b> on the dashboard.</p>"
                f"<p><b>Why:</b><br>{reasons}</p>"
                f"<p><b>Fallback call:</b> {fb.get('signal')} ({fb.get('confidence')}% — {fb.get('basis')})</p>"
                f"<p style='color:#64748b;font-size:12px'>Sent automatically by Ask Albert. Auto-recovers when "
                f"feature distributions normalise (PSI &lt; 0.25) and feeds are healthy.</p></div>")
        text = (f"Ask Albert circuit breaker tripped. Reverted to rule-based trend model; confidence downgraded to Low. "
                f"Reasons: {' | '.join(drift.get('reasons') or [])}. Fallback: {fb.get('signal')} ({fb.get('confidence')}%).")
        result = _send_to_recipients(recips, subject, html, text)
        if result.get('ok'):
            misc_col.update_one({'_id': 'drift_alert_state'},
                                {'$set': {'last_sent_at': datetime.datetime.utcnow().isoformat()}},
                                upsert=True)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'drift_circuit_breaker', 'recipients': len(recips),
                                      'max_psi': drift.get('max_psi'),
                                      'completeness': drift.get('data_completeness_pct'),
                                      'ok': result.get('ok'), 'resend_id': result.get('id'),
                                      'error': result.get('error')})
        except Exception:  # noqa
            pass
        return {**result, 'sent': 1 if result.get('ok') else 0}
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def check_liq_cascade_alert():
    """Real-time liquidation-cascade alert wired to the live WebSocket order-flow
    feed. Edge-triggered (rising edge only) with a 1h cooldown so a sustained
    cascade can't spam. Reuses the Resend recipient pipeline. Never raises."""
    try:
        snap = orderflow.get_latest() or {}
        liq = snap.get('liquidations') or {}
        active = bool(liq.get('cascade_risk'))
        prev = misc_col.find_one({'_id': 'liq_cascade_state'}) or {}
        was_active = bool(prev.get('active'))
        last_sent = prev.get('last_sent_at')
        cooldown_ok = True
        if last_sent:
            try:
                elapsed = (datetime.datetime.utcnow()
                           - datetime.datetime.fromisoformat(last_sent)).total_seconds()
                cooldown_ok = elapsed >= 3600
            except Exception:  # noqa
                cooldown_ok = True
        misc_col.update_one({'_id': 'liq_cascade_state'},
                            {'$set': {'active': active, 'cascade_10s_usd': liq.get('cascade_10s_usd'),
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        if not (active and not was_active and cooldown_ok):
            return {'ok': True, 'sent': 0, 'active': active}
        _lu = liq.get('long_usd_1m') or 0
        _su = liq.get('short_usd_1m') or 0
        _dom = 'long' if _lu >= _su else 'short'
        push_alert('Liquidation Risk', 'critical', 'Liquidation cascade detected',
                   f"Rapid cascade: >${round((liq.get('cascade_10s_usd') or 0) / 1e6, 2)}M force-liquidated "
                   f"in ~10s, dominated by {_dom}. Expect elevated volatility and slippage.",
                   f"cascade_{int(datetime.datetime.utcnow().timestamp() // 600)}")
        misc_col.update_one({'_id': 'liq_cascade_state'},
                            {'$set': {'last_sent_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        if not resend_configured():
            return {'ok': True, 'sent': 1, 'notified': True, 'active': active}
        recips = [r.get('email') for r in _recipient_list() if r.get('email')]
        if not recips:
            return {'ok': False, 'error': 'no recipients'}
        long_usd = liq.get('long_usd_1m') or 0
        short_usd = liq.get('short_usd_1m') or 0
        dom = 'long' if long_usd >= short_usd else 'short'
        px = snap.get('last_price')
        subject = '⚡ Ask Albert real-time liquidation cascade detected'
        html = (f"<div style='font-family:system-ui,sans-serif;color:#0f172a'>"
                f"<h2 style='margin:0 0 8px'>Liquidation cascade in progress</h2>"
                f"<p>The live order-flow feed just detected a rapid liquidation cascade "
                f"(&gt;${round((liq.get('cascade_10s_usd') or 0)/1e6, 2)}M force-liquidated in ~10s), "
                f"dominated by <b>{dom}</b> liquidations, with price near "
                f"<b>${'{:,.0f}'.format(px) if px else 'n/a'}</b>.</p>"
                f"<p>1-minute totals — longs ${round(long_usd):,}, shorts ${round(short_usd):,}. "
                f"Expect elevated volatility and slippage.</p>"
                f"<p style='color:#64748b;font-size:12px'>Sent automatically by Ask Albert (Coinbase + Bybit "
                f"live streams). 1-hour cooldown between cascade alerts.</p></div>")
        text = (f"Ask Albert real-time liquidation cascade: >{round((liq.get('cascade_10s_usd') or 0)/1e6, 2)}M in ~10s, "
                f"dominated by {dom}. Longs ${round(long_usd):,} / shorts ${round(short_usd):,}. Price ~{px}.")
        result = _send_to_recipients(recips, subject, html, text)
        if result.get('ok'):
            misc_col.update_one({'_id': 'liq_cascade_state'},
                                {'$set': {'last_sent_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'liq_cascade', 'recipients': len(recips),
                                      'cascade_10s_usd': liq.get('cascade_10s_usd'),
                                      'ok': result.get('ok'), 'resend_id': result.get('id'),
                                      'error': result.get('error')})
        except Exception:  # noqa
            pass
        return {**result, 'sent': 1 if result.get('ok') else 0}
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def send_instant_alerts_bg():
    """Email brand-new high/critical alerts (last 45 min) once each. Idempotent per alert id."""
    try:
        if not resend_configured():
            return {'ok': False, 'error': 'RESEND_API_KEY is not configured on the server.'}
        recips = [r.get('email') for r in _recipient_list() if r.get('email')]
        if not recips:
            return {'ok': False, 'error': 'No recipients configured.'}
        window = (datetime.datetime.utcnow() - datetime.timedelta(minutes=45)).isoformat()
        candidates = list(smart_alerts_col.find(
            {'symbol': 'BTC', 'severity': {'$in': _instant_severities()}, 'ts': {'$gte': window}}, {'_id': 0}
        ).sort('ts', -1).limit(15))
        pending = [a for a in candidates
                   if a.get('id') and not email_log_col.find_one({'_id': f"instant_{a['id']}"})]
        if not pending:
            return {'ok': True, 'sent': 0}
        subject, html, text = build_instant_alert_email(pending)
        result = _send_to_recipients(recips, subject, html, text)
        if result.get('ok'):
            for a in pending:
                email_log_col.update_one(
                    {'_id': f"instant_{a['id']}"},
                    {'$setOnInsert': {'_id': f"instant_{a['id']}", 'kind': 'instant',
                                      'ts': datetime.datetime.utcnow().isoformat(),
                                      'resend_id': result.get('id')}}, upsert=True)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'instant_send', 'recipients': len(recips),
                                      'alert_count': len(pending), 'ok': result.get('ok'),
                                      'resend_id': result.get('id'), 'error': result.get('error')})
        except Exception:  # noqa
            pass
        return {**result, 'sent': len(pending) if result.get('ok') else 0, 'recipients': len(recips)}
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


@app.post('/api/v1/email/instant/send-now')
def email_instant_now_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    result = send_instant_alerts_bg()
    if result.get('ok'):
        sent = result.get('sent', 0)
        return {'status': 'ok',
                'message': (f"Sent {sent} high-priority alert(s) to {result.get('recipients')} recipient(s)."
                            if sent else 'No new high-priority alerts to send right now.'),
                'sent': sent}
    return {'status': 'error', 'message': result.get('error') or 'Send failed.'}


def build_weekly_recap():
    now = datetime.datetime.utcnow()
    run = runs_col.find_one(sort=[('created_at', -1)]) or {}
    quant = run.get('quant') or {}
    signal = run.get('signal') or quant.get('signal') or 'N/A'
    score = run.get('quant_score')
    if score is None:
        score = quant.get('score')
    score_txt = '—' if score is None else str(score)
    ohlc = [c for c in ((run.get('chart') or {}).get('ohlc') or []) if isinstance(c, dict)]
    last7 = ohlc[-8:] if len(ohlc) >= 8 else ohlc[:]
    closes = [c.get('c') for c in last7 if isinstance(c.get('c'), (int, float))]

    def _m(v):
        return '—' if not isinstance(v, (int, float)) else f'${v:,.0f}'
    week_chg = (closes[-1] - closes[0]) / closes[0] * 100 if len(closes) >= 2 and closes[0] else None
    highs = [c.get('h') for c in last7 if isinstance(c.get('h'), (int, float))]
    lows = [c.get('l') for c in last7 if isinstance(c.get('l'), (int, float))]
    wk_high = max(highs) if highs else None
    wk_low = min(lows) if lows else None
    rets = []
    for i in range(1, len(last7)):
        p0, p1 = last7[i - 1].get('c'), last7[i].get('c')
        if isinstance(p0, (int, float)) and isinstance(p1, (int, float)) and p0:
            rets.append((last7[i].get('t'), (p1 - p0) / p0 * 100))
    best = max(rets, key=lambda x: x[1]) if rets else None
    worst = min(rets, key=lambda x: x[1]) if rets else None
    cutoff = (now - datetime.timedelta(days=7)).isoformat()
    wk_alerts = list(smart_alerts_col.find({'symbol': 'BTC', 'ts': {'$gte': cutoff}}, {'_id': 0}))
    sev_counts = {}
    for a in wk_alerts:
        s = (a.get('severity') or 'info').lower()
        sev_counts[s] = sev_counts.get(s, 0) + 1
    sev_line = ' · '.join(f'{v} {k}' for k, v in sorted(sev_counts.items(), key=lambda x: -x[1])) or 'none'
    date_str = now.strftime('%d %b %Y')
    chg_col = '#34d399' if (isinstance(week_chg, (int, float)) and week_chg >= 0) else '#f87171'
    chg_txt = '—' if not isinstance(week_chg, (int, float)) else f'{week_chg:+.2f}%'
    spark = _digest_sparkline_html([c.get('c') for c in ohlc], isinstance(week_chg, (int, float)) and week_chg >= 0)

    def card(label, value, sub='', col='#e2e8f0'):
        return (f'<td width="25%" valign="top" style="padding:6px;">'
                f'<div style="background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:12px;">'
                f'<div style="font-size:11px;color:#64748b;text-transform:uppercase;">{label}</div>'
                f'<div style="font-size:16px;font-weight:800;color:{col};margin-top:4px;">{value}</div>'
                f'<div style="font-size:11px;color:#64748b;">{sub}</div></div></td>')
    cards = (card('7-day change', chg_txt, 'BTC', chg_col) + card('Week high', _m(wk_high))
             + card('Week low', _m(wk_low)) + card('Signal now', signal, f'score {score_txt}'))
    moves = ''
    if best:
        moves += card('Best day', f'{best[1]:+.2f}%', str(best[0]), '#34d399')
    if worst:
        moves += card('Worst day', f'{worst[1]:+.2f}%', str(worst[0]), '#f87171')
    moves += card('Alerts (7d)', str(len(wk_alerts)), sev_line)
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;background:#0b1220;padding:24px;">'
        '<div style="max-width:640px;margin:0 auto;background:#0f172a;border:1px solid #1e293b;border-radius:14px;overflow:hidden;">'
        '<div style="padding:22px 24px;background:linear-gradient(135deg,#38bdf822,#1e293b);border-bottom:1px solid #1e293b;">'
        '<div style="font-size:20px;font-weight:800;color:#38bdf8;">CryptoMarkAI · Week in Review</div>'
        f'<div style="font-size:13px;color:#94a3b8;margin-top:6px;">Week ending {date_str}</div></div>'
        f'<div style="padding:16px 18px 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{cards}</tr></table></div>'
        f'<div style="padding:4px 18px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{moves}</tr></table></div>'
        f'<div style="padding:8px 24px 18px;">{spark}</div>'
        '<div style="padding:16px 24px;border-top:1px solid #1e293b;font-size:11px;color:#64748b;">'
        'Your weekly CryptoMarkAI recap. <a href="{{UNSUB}}" style="color:#f59e0b;">Unsubscribe</a>. '
        'Market information, not financial advice.'
        '</div></div></div>'
    )
    text = (f'CryptoMarkAI Week in Review — week ending {date_str}\n'
            f'7-day change: {chg_txt} · Signal {signal} (score {score_txt})\n'
            f'Week high {_m(wk_high)} · low {_m(wk_low)}\n'
            + (f'Best day {best[1]:+.2f}% ({best[0]}) ' if best else '')
            + (f'· Worst day {worst[1]:+.2f}% ({worst[0]})\n' if worst else '\n')
            + f'Alerts (7d): {len(wk_alerts)} — {sev_line}\n\nUnsubscribe: {{{{UNSUB}}}}')
    subject = f'CryptoMarkAI · Week in Review — {chg_txt} ({date_str})'
    return subject, html, text


def send_weekly_recap_bg(force=False):
    try:
        if not resend_configured():
            return {'ok': False, 'error': 'RESEND_API_KEY is not configured on the server.'}
        recips = [r.get('email') for r in _recipient_list() if r.get('email')]
        if not recips:
            return {'ok': False, 'error': 'No recipients configured.'}
        iso = datetime.datetime.utcnow().isocalendar()
        key = f'weekly_{iso[0]}_{iso[1]}'
        if not force:
            res = email_log_col.update_one({'_id': key},
                {'$setOnInsert': {'_id': key, 'kind': 'weekly_guard',
                                  'ts': datetime.datetime.utcnow().isoformat()}}, upsert=True)
            if res.upserted_id is None:
                return {'ok': False, 'error': 'Weekly recap already sent this week.'}
        subject, html, text = build_weekly_recap()
        result = _send_to_recipients(recips, subject, html, text)
        try:
            email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                      'kind': 'weekly_send', 'recipients': len(recips), 'ok': result.get('ok'),
                                      'resend_id': result.get('id'), 'error': result.get('error'),
                                      'forced': bool(force)})
        except Exception:  # noqa
            pass
        return result
    except Exception as e:  # noqa
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


@app.post('/api/v1/email/weekly/send-now')
def email_weekly_now_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    result = send_weekly_recap_bg(force=True)
    if result.get('ok'):
        return {'status': 'ok', 'message': f"Weekly recap sent to {result.get('recipients')} recipient(s)."}
    return {'status': 'error', 'message': result.get('error') or 'Send failed.'}


@app.post('/api/v1/email/settings')
def email_settings_ep(payload: dict = Body(default={})):
    if not _email_admin_guard(payload):
        return {'status': 'unauthorized', 'message': 'A valid admin passcode is required.'}
    sev = (payload or {}).get('instant_severities')
    if isinstance(sev, list):
        clean = [s for s in sev if s in _INSTANT_SEV_CHOICES]
        email_settings_col.update_one({'_id': 'instant'},
            {'$set': {'_id': 'instant', 'severities': clean or ['high', 'critical']}}, upsert=True)
    return {'status': 'ok', 'instant_severities': _instant_severities()}


def _unsub_page(msg, ok=True):
    color = '#34d399' if ok else '#f87171'
    return HTMLResponse(
        f'<html><body style="font-family:Arial;background:#0b1220;color:#e2e8f0;display:flex;'
        f'align-items:center;justify-content:center;height:100vh;margin:0;">'
        f'<div style="text-align:center;max-width:440px;padding:32px;background:#0f172a;'
        f'border:1px solid #1e293b;border-radius:14px;">'
        f'<div style="font-size:22px;font-weight:800;color:{color};margin-bottom:10px;">CryptoMarkAI</div>'
        f'<div style="font-size:15px;color:#cbd5e1;line-height:1.5;">{msg}</div></div></body></html>')


def _do_unsubscribe(e, t):
    import hmac
    email = (e or '').strip().lower()
    if not email or not t or not hmac.compare_digest(str(t), _unsub_token(email)):
        return _unsub_page('This unsubscribe link is invalid or has expired.', ok=False)
    email_recipients_col.delete_one({'_id': email})
    try:
        email_log_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                                  'kind': 'unsubscribe', 'email': email})
    except Exception:  # noqa
        pass
    return _unsub_page(f'You have been unsubscribed. <b>{email}</b> will no longer receive CryptoMarkAI emails.')


@app.get('/api/v1/email/unsubscribe')
def email_unsub_get(e: str = '', t: str = ''):
    return _do_unsubscribe(e, t)


@app.post('/api/v1/email/unsubscribe')
def email_unsub_post(e: str = '', t: str = ''):
    return _do_unsubscribe(e, t)


@app.get('/api/v1/replay')
def replay(date: str = None, window: int = 30):
    try:
        run = runs_col.find_one(sort=[('created_at', -1)])
        rp = (run or {}).get('replay') or {}
        if not date:
            # default to the most recent replayable date
            date = rp.get('max_date')
        if not date:
            return {'status': 'unavailable', 'message': 'No replay data yet.'}
        return replay_for_date(date, window=window)
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error'}


@app.get('/api/v1/scenarios')
def scenarios():
    try:
        return get_scenarios()
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'scenarios': []}


@app.post('/api/v1/bitmark/run')
def bitmark_run(payload: dict = Body(default={})):
    import time
    passcode = (payload or {}).get('passcode', '')
    if not _passcode_ok(passcode):
        audit_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                              'action': 'manual_forecast_run', 'result': 'denied', 'reason': 'bad_passcode'})
        return {'status': 'unauthorized',
                'message': 'A valid admin passcode is required to trigger a manual forecast run. Enter it in Settings.'}
    now = time.time()
    cooldown = 300  # rate limit: one manual forecast every 5 minutes
    elapsed = now - _bitmark_last_manual['ts']
    if elapsed < cooldown:
        wait = int(cooldown - elapsed)
        return {'status': 'rate_limited', 'retry_in': wait,
                'message': f'A manual forecast can only be run once every {cooldown // 60} minutes — please wait {wait}s. This stops re-running until you get an answer you like.'}
    if _state['status'] == 'running':
        return {'status': 'busy', 'message': 'A forecast is already running — please wait for it to finish.'}
    _bitmark_last_manual['ts'] = now
    _forecast_trigger['reason'] = 'manual'
    audit_col.insert_one({'id': str(uuid.uuid4()), 'ts': datetime.datetime.utcnow().isoformat(),
                          'action': 'manual_forecast_run', 'result': 'started', 'trigger': 'manual'})
    threading.Thread(target=run_compute_bg, daemon=True).start()
    return {'status': 'started',
            'message': 'Running a fresh CryptoMarkAI forecast against the latest data (~30s). The updated ranges and a "what changed" summary will appear when it completes.'}


@app.get('/api/v1/audit')
def audit_log(limit: int = 20):
    items = list(audit_col.find({}, {'_id': 0}).sort('ts', -1).limit(limit))
    return {'status': 'ready', 'entries': items}


_SECTION_FOCUS = {
    'overview': None,  # general — all things Ask Albert
    'forecasts': 'the price FORECASTS (CryptoMarkAI probability ranges from 1 week to 5 years — odds, bull/base/bear ranges, invalidation levels)',
    'market-intel': 'the MARKET INTELLIGENCE / technical picture (chart structure, key support/resistance levels, cycle position and the raw indicators)',
    'crossmarket': 'the CROSS-MARKET comparison of Bitcoin vs traditional assets (S&P 500, Nasdaq, Gold, US Dollar) — correlation, relative performance and volatility',
    'analogs': 'the HISTORICAL ANALOG (which past Bitcoin episode today most resembles and what happened next)',
    'smartmoney': 'the on-chain SMART MONEY behaviour (MVRV, SOPR, active addresses, holder accumulation, Fear & Greed)',
    'whales': 'WHALE activity (balances of the largest labeled wallets, accumulation vs distribution, exchange in/outflows)',
    'institutional': 'INSTITUTIONAL & DERIVATIVES (open interest, funding, long/short positioning, taker flow and spot ETF net flows)',
    'leverage': 'the LEVERAGE picture (open interest, funding, long/short bias, squeeze/liquidation risk)',
    'macro': 'MACRO & POLICY conditions (central-bank policy, liquidity, cross-market correlation and regulation)',
    'news': 'the NEWS flow and its likely direction and impact on Bitcoin',
    'risk': 'the RISK view (expected move, volatility, support/resistance zones, event risk and data reliability) — kept separate from direction',
    'events': 'the upcoming EVENT calendar (macro, derivatives and on-chain events that could move Bitcoin) and their expected volatility',
    'performance': 'the PERFORMANCE / prediction ledger (accuracy, Brier score, calibration and the honest scoreboard)',
    'timemachine': 'the TIME MACHINE historical replay (what the model would have predicted on a past day and what happened next)',
    'network': 'NETWORK health & sentiment (hashrate, difficulty, mempool/fees and the Fear & Greed crowd read)',
    'dataaudit': 'the DATA AUDIT (the trust-scored composite Bitcoin price and its venues/outliers, cross-asset context, GDELT news tone and FRED macro — and how confident each signal is: HIGH/MEDIUM/LOW)',
    'admin': 'the ADMIN / platform view (integrations, data-source freshness, usage and costs)',
    'settings': 'Ask Albert settings, data sources and compliance information',
}


def _section_focus_hint(section):
    sid = (section or '').strip().lower()
    if not sid or sid == 'overview':
        return None
    topic = _SECTION_FOCUS.get(sid)
    if topic is None:
        return None
    return (f"CONTEXT: The user is currently viewing the '{sid}' screen. Focus your answer on {topic}, "
            f"using the relevant numbers from the live dashboard data — unless the user clearly asks about "
            f"something else, in which case answer that instead.")


def _fmt_usd(v):
    try:
        return '$' + format(float(v), ',.0f')
    except Exception:  # noqa
        return 'n/a'


def _section_live_context(section, symbol='BTC'):
    """Return a compact block of REAL live numbers for the screen the user is on,
    so Albert can cite exact OI, funding, whale flows, composite venues, macro, etc.
    Each branch is guarded — never fabricate; omit anything unavailable."""
    sid = (section or '').strip().lower()
    if not sid or sid == 'overview':
        return ''
    L = []
    try:
        if sid == 'leverage':
            d = get_leverage('4H') or {}
            oi = d.get('open_interest') or {}
            fu = d.get('funding') or {}
            po = d.get('positioning') or {}
            sm = d.get('summary') or {}
            sq = d.get('squeeze') or {}
            L.append('LEVERAGE SCREEN LIVE DATA (OKX, 4H timeframe):')
            if d.get('price'):
                L.append(f"- Price: {_fmt_usd(d['price'])}")
            if oi:
                L.append(f"- Open interest: {_fmt_usd(oi.get('value_usd'))} (change {oi.get('change_tf_pct')}% this TF), state {oi.get('state')}")
            if fu:
                L.append(f"- Funding rate: {fu.get('rate')}% ({fu.get('direction')}), bias {fu.get('bias')}, trend {fu.get('trend')}")
            if po:
                L.append(f"- Positioning: long {po.get('long_pct')}% / short {po.get('short_pct')}%, account long/short ratio {po.get('account_ratio')} (trend {po.get('trend')})")
            if sm:
                L.append(f"- Leverage pressure: {sm.get('pressure')} ({sm.get('pressure_score')}/100), bias {sm.get('bias')}, {sm.get('squeeze')}")
            if sq:
                L.append(f"- Squeeze risk: long {sq.get('long_risk')}/100 ({sq.get('long_label')}), short {sq.get('short_risk')}/100 ({sq.get('short_label')})")
            L.append('- NOTE: liquidations, liquidation heatmap and estimated-leverage percentile have NO free feed — do NOT cite numbers for them; say "no [that] data available" if asked.')
        elif sid == 'whales':
            wi = compute_whale_impact() or {}
            L.append('WHALE SCREEN LIVE DATA (on-chain reconstruction, ~30d):')
            L.append(f"- Tracked whales total: {round(wi.get('total_balance') or 0):,} BTC ({_fmt_usd(wi.get('total_usd'))}). Held by holders: {round(wi.get('holder_balance') or 0):,} BTC; on exchanges: {round(wi.get('exchange_balance') or 0):,} BTC")
            L.append(f"- 30-day net flow: {round(wi.get('net_flow_30d') or 0):,} BTC -> trend {wi.get('trend')}")
            movers = (wi.get('contributors') or [])[:4]
            if movers:
                L.append('- Biggest movers (30d): ' + '; '.join(
                    f"{m.get('name')} {('+' if (m.get('delta_30d') or 0) >= 0 else '')}{round(m.get('delta_30d') or 0):,} BTC [{m.get('signal')}]" for m in movers))
            try:
                tx = (get_whale_tx_feed() or {}).get('feed') or []
                big = [t for t in tx if (t.get('amount') or 0) >= 500][:3]
                if big:
                    L.append('- Recent large moves: ' + '; '.join(
                        f"{round(t.get('amount') or 0):,} BTC {t.get('direction')} {t.get('entity')} [{t.get('signal')}]" for t in big))
            except Exception:  # noqa
                pass
            try:
                ef = get_etf_flows() or {}
                daily = ef.get('daily') or []
                totals = [x.get('total') for x in daily if x.get('total') is not None]
                if totals:
                    L.append(f"- US spot ETF net flows: 1d ${round(totals[0])}M, 7d ${round(sum(totals[:7]))}M, since-launch cumulative ${round((ef.get('cum_total') or 0))}M")
            except Exception:  # noqa
                pass
        elif sid == 'dataaudit':
            L.append('DATA AUDIT LIVE DATA:')
            try:
                cp = composite_price() or {}
                if cp.get('status') == 'ready':
                    vtxt = ', '.join(f"{v.get('source')} {_fmt_usd(v.get('price'))}" for v in (cp.get('venues') or []) if v.get('ok'))
                    L.append(f"- Composite BTC price: {_fmt_usd(cp.get('composite'))} (confidence {cp.get('confidence')}) from {cp.get('venue_count')} venues; {vtxt}; spread {cp.get('spread_pct')}%. Outliers: {cp.get('outliers') or 'none'}")
            except Exception:  # noqa
                pass
            try:
                xa = _misc_get('cross_asset', 15 * 60, _compute_cross_asset) or {}
                if xa.get('btc_dominance'):
                    L.append(f"- Cross-asset: BTC dominance {xa.get('btc_dominance')}%, ETH/BTC {xa.get('eth_btc')}, total mcap ${round((xa.get('total_market_cap_usd') or 0)/1e9)}B, regime {xa.get('regime')}")
            except Exception:  # noqa
                pass
            try:
                ns = _misc_get('news_signals', 60 * 60, _compute_news_signals) or {}
                if ns.get('tone_latest') is not None:
                    L.append(f"- GDELT news tone: {ns.get('tone_latest')} ({ns.get('mood')}), 21d avg {ns.get('tone_avg_21d')}, direction {ns.get('direction')}")
                else:
                    L.append('- GDELT news tone: no data available (feed rate-limited).')
            except Exception:  # noqa
                pass
            try:
                fr = _misc_get('macro_fred', 6 * 3600, _compute_macro_fred) if FRED_API_KEY else None
                rows = (fr or {}).get('series') or []
                if rows:
                    L.append('- US macro (FRED): ' + ', '.join(f"{r.get('label')} {r.get('value')}" for r in rows))
            except Exception:  # noqa
                pass
        elif sid in ('institutional', 'smartmoney'):
            panels = get_onchain_panels(symbol) or {}
            panel = panels.get('institutional' if sid == 'institutional' else 'smart_money') or {}
            mets = panel.get('metrics') or []
            if mets:
                L.append(('INSTITUTIONAL & DERIVATIVES' if sid == 'institutional' else 'SMART MONEY') + ' LIVE DATA:')
                if panel.get('headline'):
                    L.append(f"- Read: {panel.get('headline')}")
                for m in mets[:8]:
                    L.append(f"- {m.get('name')}: {m.get('value')} [{m.get('signal')}]")
        elif sid == 'network':
            try:
                fg = _misc_get('fear_greed', 30 * 60, compute_fear_greed) or {}
                nh = _misc_get('network_health', 10 * 60, compute_network_health) or {}
                L.append('NETWORK & SENTIMENT LIVE DATA:')
                if fg.get('value') is not None:
                    L.append(f"- Fear & Greed: {fg.get('value')} ({fg.get('label')}); 1w ago {fg.get('week_ago')}, 1m ago {fg.get('month_ago')}")
                if nh.get('hashrate_ehs') is not None:
                    fees = nh.get('fees') or {}
                    L.append(f"- Hashrate {nh.get('hashrate_ehs')} EH/s, next difficulty {nh.get('difficulty_change_pct')}%, fastest fee {fees.get('fastest')} sat/vB ({fees.get('state')})")
            except Exception:  # noqa
                pass
    except Exception:  # noqa
        traceback.print_exc()
        return ''
    return ('\n'.join(L)) if len(L) > 1 else ''



def _albert_answer(ctx, user_text, session_id, deep=False):
    """Run Albert's chat completion with a hard per-attempt timeout and graceful
    fallback so the endpoint never hangs past the proxy budget or returns empty.
    Attempt order:
      - deep ON : pro+search (24s) -> flash+search (16s) -> flash plain (14s)
      - deep OFF: flash+search (20s) -> flash plain (14s)
    Returns (text, model_used, sources)."""
    def _extract(reply):
        if isinstance(reply, str):
            return reply.strip()
        return (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '').strip()

    def _extract_sources(reply):
        """Pull the live web-search citations Gemini used (title + url) from the
        google-genai response's grounding_metadata."""
        out, seen = [], set()
        try:
            resp = getattr(reply, 'raw', None)
            for cand in (getattr(resp, 'candidates', None) or []):
                gm = getattr(cand, 'grounding_metadata', None)
                if not gm:
                    continue
                for ch in (getattr(gm, 'grounding_chunks', None) or []):
                    web = getattr(ch, 'web', None)
                    url = getattr(web, 'uri', None) if web else None
                    title = getattr(web, 'title', None) if web else None
                    if url and url not in seen:
                        seen.add(url)
                        out.append({'title': title or url, 'url': url})
        except Exception:  # noqa
            pass
        return out[:8]

    def _run(model, use_tools, timeout_s, max_toks):
        def _call():
            async def _go():
                chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'askquant-{session_id}',
                                system_message=CHAT_SYSTEM.format(ctx=ctx))
                        .with_model('gemini', model)
                        .with_params(temperature=0.4, max_tokens=max_toks))
                if use_tools:
                    return await chat.with_tools([{'googleSearch': {}}]).send_message_with_tools(UserMessage(text=user_text))
                return await chat.send_message(UserMessage(text=user_text))
            return asyncio.run(_go())
        # Hard wall-clock timeout via a worker thread: the emergentintegrations client
        # can block under the hood (so asyncio.wait_for cannot cancel it); future.result
        # gives a reliable deadline and simply abandons a slow call.
        fut = _LLM_POOL.submit(_call)
        return fut.result(timeout=timeout_s)

    if deep:
        _primary = _model_for('chat_deep')
        attempts = [(_primary, True, 30, 4000),
                    (CHAT_MODEL, True, 14, 4000),
                    (CHAT_MODEL, False, 12, 4000)]
    else:
        _primary = _model_for('chat_standard')
        attempts = [(_primary, True, 20, 3500),
                    (_primary, False, 14, 3500),
                    (CHAT_MODEL, False, 12, 3500)]

    for model, use_tools, tmo, mx in attempts:
        try:
            reply = _run(model, use_tools, tmo, mx)
            text = _extract(reply)
            if text:
                sources = _extract_sources(reply) if use_tools else []
                return text, model, sources
        except Exception:  # noqa
            traceback.print_exc()
            continue
    return '', (_model_for('chat_deep') if deep else _model_for('chat_standard')), []


@app.post('/api/v1/chat')
def chat_endpoint(request: Request, payload: dict = Body(...)):
    limited = _too_many(request, 'chat', per_min=10, per_day=200)
    if limited is not None:
        return limited
    session_id = (str(payload.get('session_id') or uuid.uuid4()))[:80]
    message = (payload.get('message') or '').strip()[:2000]
    deep = bool(payload.get('deep'))
    pid = (str(payload.get('pid') or '')).strip()[:80]
    sym = (payload.get('symbol') or 'BTC')
    if not message:
        return {'error': 'empty message', 'text': 'Please type a question.'}
    if not (LLM_READY_KEY and _HAS_LLM):
        return {'error': 'llm_unconfigured',
                'text': 'The Ask Quant chat model is not configured on this server.'}
    # Basket-from-chat: if the user asks Albert to BUILD a multi-coin basket, draft it
    # inline and return a save-able card (the chat UI renders a "Save & track" button).
    # Status questions ("how are my baskets doing?") fall through to normal chat.
    try:
        if _is_basket_close_request(message):
            bk, all_bks = _find_basket_for_message(pid, message)
            if not all_bks:
                return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                        'text': "You don't have any active strategies to close right now."}
            if not bk:
                names = ', '.join(f"'{b.get('title')}'" for b in all_bks)
                return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                        'text': f"Which strategy should I close? You have: {names}."}
            try:
                perf = _basket_perf(bk) or {}
            except Exception:  # noqa
                perf = {}
            pnl = perf.get('total_pnl_pct')
            txt = (f"Want me to close **{bk.get('title')}**? It's currently at "
                   f"{pnl if pnl is not None else 'n/a'}% P&L. Tap **Close strategy** below to confirm — "
                   f"this stops tracking it and moves it to your past strategies.")
            return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                    'text': txt,
                    'basket_close': {'basket_id': bk['id'], 'title': bk.get('title'),
                                     'total_pnl_pct': pnl}}
    except Exception:  # noqa
        traceback.print_exc()
    try:
        if _is_basket_rebalance_request(message):
            bk, all_bks = _find_basket_for_message(pid, message)
            if not all_bks:
                return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                        'text': ("You don't have any active strategies to rebalance yet. Ask me to build one — "
                                 "e.g. 'build a strategy long the majors, short a laggard'.")}
            if not bk:
                names = ', '.join(f"'{b.get('title')}'" for b in all_bks)
                return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                        'text': f"Which strategy should I rebalance? You have: {names}."}
            sug = albert_basket_rebalance(bk['id'])
            if isinstance(sug, dict) and sug.get('status') == 'ready':
                txt = (f"Here's how I'd rebalance **{bk.get('title')}** — {sug.get('rationale')}\n\n"
                       f"Review the new weights below and tap **Apply weights** to update it.")
                return {'session_id': session_id, 'sources': [], 'model': _model_for('strategy'),
                        'text': txt,
                        'basket_rebalance': {'basket_id': bk['id'], 'title': bk.get('title'),
                                             'rationale': sug.get('rationale'), 'legs': sug.get('legs')}}
    except Exception:  # noqa
        traceback.print_exc()
    try:
        if _is_basket_build_request(message):
            draft = _build_basket_draft(message)
            if draft and draft.get('legs'):
                legs_line = ', '.join(
                    f"{l['symbol']} {l['position']} {int(round(l.get('weight_pct') or 0))}%"
                    for l in draft['legs'])
                txt = (f"Here's a strategy I put together — **{draft.get('title', 'Multi-Coin Strategy')}**. "
                       f"{draft.get('thesis', '')}\n\nLegs: {legs_line}. "
                       f"Review it below and tap **Save & track** to start tracking it.")
                try:
                    chat_col.insert_one({'_id': str(uuid.uuid4()), 'session_id': session_id,
                                         'user': message, 'assistant': txt, 'model': _model_for('strategy'),
                                         'created_at': datetime.datetime.utcnow().isoformat()})
                except Exception:  # noqa
                    pass
                return {'session_id': session_id, 'text': txt, 'basket_draft': draft,
                        'model': _model_for('strategy'), 'deep': deep, 'sources': []}
    except Exception:  # noqa
        traceback.print_exc()
    try:
        ctx = build_chat_context(sym)
        section = payload.get('section')
        live = _section_live_context(section, sym)
        if live:
            ctx = ctx + "\n\n===== CURRENT SCREEN LIVE DATA (cite these exact numbers) =====\n" + live
        # Portfolio-aware coaching: inject the user's saved position so buy/sell calls
        # are tailored to their P&L.
        pf_ctx = _portfolio_context(pid)
        if pf_ctx:
            ctx = ctx + "\n\n===== USER PORTFOLIO (tailor buy/sell/hold to THIS position & P&L) =====\n" + pf_ctx
        # Engine awareness: Alert-Engine edge board, sector rotation, recent
        # signals and the user's active strategies.
        try:
            eng_ctx = _albert_engine_context(sym, pid)
        except Exception:  # noqa
            eng_ctx = ''
        if eng_ctx:
            ctx = ctx + "\n\n===== ALBERT'S ENGINES (edge board, sector rotation, recent signals, your strategies) =====\n" + eng_ctx
        hist = list(chat_col.find({'session_id': session_id}, {'_id': 0}).sort('created_at', 1))
        hist_txt = ''
        for h in hist[-5:]:
            hist_txt += f"User: {h.get('user')}\nQuant: {h.get('assistant')}\n"
        focus = _section_focus_hint(section)
        user_text = ((f"{focus}\n" if focus else '')
                     + (f"Recent conversation:\n{hist_txt}\n" if hist_txt else '')
                     + f"Question: {message}")
        text, used_model, sources = _albert_answer(ctx, user_text, session_id, deep=deep)
        if not text:
            return {'error': 'chat_failed',
                    'text': 'Sorry — I could not answer that just now. Please try again in a moment.'}
        chat_col.insert_one({'_id': str(uuid.uuid4()), 'session_id': session_id,
                             'user': message, 'assistant': text, 'model': used_model,
                             'created_at': datetime.datetime.utcnow().isoformat()})
        # Self-check: log Albert's directional call in the background (never blocks the reply).
        try:
            _LLM_POOL.submit(_log_albert_call, session_id, sym, message, text)
        except Exception:  # noqa
            pass
        return {'session_id': session_id, 'text': text, 'model': used_model,
                'deep': deep, 'sources': sources}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'error': 'chat_failed',
                'text': 'Sorry — I could not answer that just now. Please try again in a moment.'}


# =====================================================================
# ALBERT ADVISOR EXTRAS: server-side portfolio, price-alert watches,
# and Albert's self-check track record (grades his own calls).
# =====================================================================

def _num(v):
    try:
        return round(float(v), 2) if v not in (None, '') else None
    except Exception:  # noqa
        return None


def _spot_price(symbol='BTC'):
    """Current spot price for any supported symbol (reuses the cached ticker)."""
    try:
        t = ticker((symbol or 'BTC'))
        p = t.get('price') if isinstance(t, dict) else None
        return float(p) if p else None
    except Exception:  # noqa
        return None


def _portfolio_context(pid):
    if not pid:
        return ''
    try:
        doc = portfolio_col.find_one({'_id': pid})
    except Exception:  # noqa
        doc = None
    if not doc or not doc.get('positions'):
        return ''
    lines = []
    for p in (doc.get('positions') or [])[:12]:
        asset = str(p.get('asset', '')).upper()[:6]
        if not asset:
            continue
        size = p.get('size')
        entry = p.get('avg_entry')
        spot = _spot_price(asset)
        pnl = ''
        try:
            if spot and entry:
                pct = (spot - float(entry)) / float(entry) * 100
                val = (float(size) * spot) if size else None
                pnl = f", now ${spot:,.2f} ({pct:+.1f}% P&L" + (f", ~${val:,.0f} position" if val else '') + ")"
        except Exception:  # noqa
            pnl = ''
        lines.append(f"- {asset}: {size if size is not None else '?'} @ avg entry ${entry if entry is not None else '?'}{pnl}")
    if not lines:
        return ''
    return ("The user holds the following. Tailor EVERY buy/sell/hold call to THIS position and its P&L "
            "(where to add, where to take profit, where to cut, how it changes their risk):\n" + "\n".join(lines))


@app.get('/api/v1/portfolio')
def get_portfolio(pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'positions': []}
    doc = portfolio_col.find_one({'_id': pid}, {'_id': 0})
    return {'positions': (doc or {}).get('positions', []), 'usdc': (doc or {}).get('usdc')}


@app.post('/api/v1/portfolio')
def save_portfolio(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    clean = []
    for p in (payload.get('positions') or [])[:12]:
        try:
            asset = str(p.get('asset', '')).upper().strip()[:6]
            if not asset:
                continue
            clean.append({'asset': asset, 'size': _num(p.get('size')), 'avg_entry': _num(p.get('avg_entry'))})
        except Exception:  # noqa
            continue
    portfolio_col.update_one({'_id': pid},
                             {'$set': {'positions': clean, 'usdc': _num(payload.get('usdc')),
                                       'updated_at': datetime.datetime.utcnow().isoformat()}},
                             upsert=True)
    return {'ok': True, 'positions': clean, 'usdc': _num(payload.get('usdc'))}


# ============================================================
# Albert's Plan — Milestone 1-3 (Trading Mandate + Portfolio/USDC engine).
# The decision layer is deterministic; the LLM only explains it.
# ============================================================
_DEFAULT_MANDATE = {
    'goal': '', 'risk_tolerance': '', 'time_horizon': '',
    'max_drawdown_pct': None, 'reserve_pct': 25.0,
    'approved_coins': [], 'excluded_coins': [],
    'max_alloc_pct': {}, 'max_trade_risk_pct': 2.0,
    'leverage_enabled': False, 'preferred_strategies': [],
}


def _get_mandate(pid):
    try:
        doc = mandate_col.find_one({'_id': pid}, {'_id': 0})
    except Exception:  # noqa
        doc = None
    m = dict(_DEFAULT_MANDATE)
    if doc:
        m.update({k: v for k, v in doc.items() if k in _DEFAULT_MANDATE})
    return m


def _mandate_complete(m):
    return bool(m and m.get('risk_tolerance') and (m.get('reserve_pct') is not None))


@app.get('/api/v1/albert/mandate')
def albert_get_mandate(pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'mandate': _DEFAULT_MANDATE, 'complete': False}
    m = _get_mandate(pid)
    return {'mandate': m, 'complete': _mandate_complete(m)}


@app.post('/api/v1/albert/mandate')
def albert_save_mandate(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    src = payload.get('mandate') or payload

    def _pct(v, lo=0.0, hi=100.0, d=None):
        try:
            return max(lo, min(hi, float(v)))
        except Exception:  # noqa
            return d
    m = dict(_DEFAULT_MANDATE)
    m['goal'] = str(src.get('goal') or '')[:200]
    m['risk_tolerance'] = str(src.get('risk_tolerance') or '')[:20]
    m['time_horizon'] = str(src.get('time_horizon') or '')[:30]
    m['max_drawdown_pct'] = _pct(src.get('max_drawdown_pct'), 1, 90, None)
    m['reserve_pct'] = _pct(src.get('reserve_pct'), 0, 100, 25.0)
    m['approved_coins'] = [str(c).upper()[:8] for c in (src.get('approved_coins') or []) if c][:100]
    m['excluded_coins'] = [str(c).upper()[:8] for c in (src.get('excluded_coins') or []) if c][:100]
    mac = {}
    for k, v in (src.get('max_alloc_pct') or {}).items():
        p = _pct(v, 0, 100, None)
        if p is not None:
            mac[str(k).upper()[:8]] = p
    m['max_alloc_pct'] = mac
    m['max_trade_risk_pct'] = _pct(src.get('max_trade_risk_pct'), 0.1, 100, 2.0)
    m['leverage_enabled'] = bool(src.get('leverage_enabled'))
    m['preferred_strategies'] = [str(s)[:30] for s in (src.get('preferred_strategies') or []) if s][:12]
    mandate_col.update_one({'_id': pid},
                           {'$set': {**m, 'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    return {'mandate': m, 'complete': _mandate_complete(m)}


def _portfolio_summary(pid):
    # Phase E: once paper fills exist, the engine consumes the materialized PAPER
    # portfolio (baseline + ledger). Manual portfolio_col is the untouched baseline.
    doc = paper_portfolio_col.find_one({'_id': pid}) or portfolio_col.find_one({'_id': pid}) or {}
    positions = doc.get('positions') or []
    usdc = _num(doc.get('usdc')) or 0.0
    m = _get_mandate(pid)
    reserve_pct = m.get('reserve_pct') or 0
    holdings, holdings_value = [], 0.0
    for p in positions:
        asset = str(p.get('asset', '')).upper()[:8]
        if not asset or asset in ('USDC', 'USDT', 'USD'):
            continue
        size = _num(p.get('size')) or 0
        entry = _num(p.get('avg_entry'))
        spot = _spot_price(asset) or 0
        val = size * spot
        holdings_value += val
        upnl = ((spot - entry) / entry * 100) if (spot and entry) else None
        holdings.append({'asset': asset, 'size': size, 'avg_entry': entry, 'spot': spot,
                         'value': round(val, 2), 'unrealized_pct': round(upnl, 2) if upnl is not None else None})
    total = holdings_value + usdc
    for h in holdings:
        h['portfolio_pct'] = round((h['value'] / total * 100), 2) if total else 0
    protected = round(usdc * reserve_pct / 100.0, 2)
    deployable = round(max(0.0, usdc - protected), 2)
    return {'total_value': round(total, 2), 'usdc': round(usdc, 2), 'protected_reserve': protected,
            'deployable_usdc': deployable, 'reserve_pct': reserve_pct,
            'holdings_value': round(holdings_value, 2), 'holdings': holdings,
            'mandate_complete': _mandate_complete(m)}


@app.get('/api/v1/albert/portfolio-summary')
def albert_portfolio_summary(pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    return _portfolio_summary(pid)


# ---- Phase C/D: deterministic decision engine (extracted to albert/ package) ----
# The engine now lives in albert.engine.*; these thin wrappers preserve the
# original names/behaviour so the rest of server.py is unchanged. Market-data +
# portfolio helpers are injected into albert.deps at the bottom of this module.
import albert.deps as _albert_deps  # noqa: E402
from albert.engine import regime as _albert_regime_mod  # noqa: E402
from albert.engine import scoring as _albert_scoring_mod  # noqa: E402
from albert.engine import decision as _albert_decision_mod  # noqa: E402
from albert.repositories import decision_history as _decision_history_repo  # noqa: E402
from albert.repositories import portfolio_risk as _portfolio_risk_repo  # noqa: E402
from albert.repositories import lifecycle as _lifecycle_repo  # noqa: E402
from albert.execution import manager as _order_mgr  # noqa: E402
from albert.execution import ledger as _paper_ledger  # noqa: E402
from albert.engine.constants import (  # noqa: E402,F401
    ALBERT_ENGINE_VERSION, REGIME_BUY_THRESHOLD as _REGIME_BUY_THRESHOLD,
    REGIME_DEPLOY_CEILING as _REGIME_DEPLOY_CEILING, ALBERT_UNIVERSE as _ALBERT_UNIVERSE,
    STABLES as _STABLES,
)


def _rsi(series, n=14):
    # Retained module-global (rolling) RSI — preserves the pre-extraction behaviour
    # where this definition shadowed the earlier EWM _rsi for later callers.
    d = series.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs))


def _albert_regime():
    return _albert_regime_mod.compute_regime()


def _score_asset(symbol, regime):
    return _albert_scoring_mod.score_asset(symbol, regime)


def _albert_decisions(pid):
    return _albert_decision_mod.build_decisions(pid)


@app.get('/api/v1/albert/regime')
def albert_regime_endpoint():
    return _albert_regime()


@app.get('/api/v1/albert/decisions')
def albert_decisions_endpoint(pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    snap = _albert_decisions(pid)
    # Phase D2: reconcile against stored state -> stable ids + genuine change events only.
    try:
        events = _decision_history_repo.reconcile(pid, snap)
        snap['changeEvents'] = events
    except Exception:  # noqa
        traceback.print_exc()
        snap['changeEvents'] = []
    return snap


@app.get('/api/v1/albert/decision-history')
def albert_decision_history(pid: str = '', asset: str = '', limit: int = 50):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    rows = _decision_history_repo.list_history(pid, asset=(asset or '').strip() or None, limit=limit)
    return {'status': 'ready', 'count': len(rows), 'events': rows}


@app.get('/api/v1/albert/decision/{decision_id}')
def albert_decision_fetch(decision_id: str, pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    env = _decision_history_repo.get_snapshot(pid, decision_id)
    if not env:
        return {'status': 'not_found'}
    return {'status': 'ready', 'decision': env}


# ---- Ask Albert About This Call (read-only explanation of an immutable snapshot) ----
EXPLAIN_CALL_SYSTEM = (
    "You are Albert, a disciplined crypto risk & strategy adviser. You are given ONE immutable, "
    "already-decided DecisionSnapshot as read-only JSON. Your ONLY job is to EXPLAIN it in plain English. "
    "ABSOLUTE RULES: (1) NEVER recalculate, round, or substitute any number. Use the EXACT figures given "
    "(call, reasonCode, score, confidence, prices, quantities, sellUsd/sellQty, deployNow/tranche amounts, "
    "invalidation, flip-condition thresholds). If it says SELL $4,216.37 you say $4,216.37 — never a new number. "
    "(2) NEVER change the call or invent a different recommendation. (3) You MAY explain: why this call was made, "
    "why that amount/fraction was chosen, which lower-precedence signal lost and why (see sellPlan.allSignals + "
    "precedenceRuleApplied + precedenceOrder), the deployment tranches or sell plan, the mandate/risk constraints, "
    "and exactly what would change the call (use flipConditions verbatim in intent). "
    "(4) If asked to do maths or give a different number/target, refuse and restate the snapshot's numbers. "
    "Be concise, concrete, and cite the snapshot's own fields. Do not output JSON."
)


def _explain_dto(env):
    """Whitelisted, read-only projection of an immutable decision for the LLM."""
    sp = env.get('sellPlan') or {}
    dp = env.get('deploymentPlan') or {}
    return {
        'symbol': env.get('symbol'), 'call': env.get('call') or env.get('action'),
        'reasonCode': env.get('reasonCode'), 'precedenceRuleApplied': env.get('precedenceRuleApplied'),
        'opportunityScore': env.get('opportunityScore'), 'confidence': env.get('confidence'),
        'regime': env.get('regime'), 'buyThreshold': env.get('buyThreshold'),
        'eligible': env.get('eligible'), 'ineligibilityReason': env.get('ineligibilityReason'),
        'invalidation': env.get('invalidation'), 'currentPrice': env.get('currentPrice'),
        'positionBefore': env.get('positionBefore'), 'positionAfter': env.get('positionAfter'),
        'recommendedDeltaUsd': env.get('recommendedDeltaUsd'),
        'deploymentPlan': {'deployNowUsd': dp.get('deployNowUsd'), 'totalPlannedUsd': dp.get('totalPlannedUsd'),
                           'tranches': dp.get('tranches')} if dp else None,
        'sellPlan': {'action': sp.get('action'), 'fraction': sp.get('fraction'), 'sellUsd': sp.get('sellUsd'),
                     'sellQty': sp.get('sellQty'), 'note': sp.get('note'),
                     'allSignals': sp.get('allSignals')} if sp else None,
        'mandateChecks': env.get('mandateChecks'), 'riskFlags': env.get('riskFlags'),
        'flipConditions': env.get('flipConditions'), 'reasons': env.get('reasons'),
        'warnings': env.get('warnings'), 'precedenceOrder': env.get('precedenceOrder'),
    }


@app.post('/api/v1/albert/explain-call')
def albert_explain_call(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    decision_id = (str(payload.get('decisionId') or '')).strip()
    question = (str(payload.get('question') or '')).strip()[:400]
    # Resolve the AUTHORITATIVE immutable snapshot; the LLM never gets a writable path.
    env = None
    source = 'store'
    if decision_id:
        env = _decision_history_repo.get_snapshot(pid, decision_id)
    if env is None and payload.get('asset'):
        env = _decision_history_repo.get_current(pid, str(payload.get('asset')).upper()[:8])
    if env is None and isinstance(payload.get('decision'), dict):
        env = payload['decision']
        source = 'client'
    if not env:
        return {'status': 'not_found', 'error': 'No decision snapshot to explain.'}
    dto = _explain_dto(env)
    if not (LLM_READY_KEY and _HAS_LLM):
        return {'status': 'ready', 'explanation': '', 'decision': env, 'source': source,
                'error': 'LLM not configured'}
    try:
        q = ('Explain this decision to me.' if not question else question)
        prompt = ('Immutable DecisionSnapshot (read-only JSON):\n' + json.dumps(dto, default=str)
                  + '\n\nUser question: ' + q)

        def _call():
            async def _go():
                chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'explain-{decision_id or dto.get("symbol")}',
                                system_message=EXPLAIN_CALL_SYSTEM)
                        .with_model('gemini', _model_for('chat_standard')).with_params(temperature=0.2, max_tokens=4000))
                return await chat.send_message(UserMessage(text=prompt))
            return asyncio.run(_go())
        reply = _LLM_POOL.submit(_call).result(timeout=60)
        text = reply.strip() if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '').strip()
    except Exception:  # noqa
        traceback.print_exc()
        text = ''
    # The snapshot is returned UNCHANGED alongside the explanation (LLM cannot mutate it).
    return {'status': 'ready', 'explanation': text, 'decision': env, 'source': source,
            'model': _model_for('chat_standard')}


# ============================================================================
# Phase E — Paper Order Manager endpoints (paper-only; LLM strictly read-only)
# ============================================================================
@app.post('/api/v1/albert/order/create')
def albert_order_create(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    asset = (str(payload.get('asset') or '')).strip()
    idem = (str(payload.get('idempotencyKey') or '')).strip()
    if not pid or not asset or not idem:
        return {'status': 'error', 'error': 'pid, asset and idempotencyKey are required'}
    return _order_mgr.create_intent(pid, asset, idem, slippage_bps=payload.get('slippageBps'),
                                    portfolio_id=(payload.get('portfolioId') or 'default'),
                                    account_id=(payload.get('accountId') or 'paper'))


@app.post('/api/v1/albert/order/{order_id}/confirm')
def albert_order_confirm(order_id: str):
    return _order_mgr.confirm(order_id)


@app.post('/api/v1/albert/order/{order_id}/execute')
def albert_order_execute(order_id: str, payload: dict = Body(default={})):
    q = (payload or {}).get('simulateFillQty')
    return _order_mgr.execute(order_id, simulate_fill_qty=q)


@app.post('/api/v1/albert/order/{order_id}/cancel')
def albert_order_cancel(order_id: str):
    return _order_mgr.cancel(order_id)


@app.get('/api/v1/albert/order/{order_id}')
def albert_order_get(order_id: str):
    intent = _order_mgr.get_intent(order_id)
    if not intent:
        return {'status': 'not_found'}
    return {'status': 'ready', 'intent': intent, 'audit': _order_mgr.get_audit(order_id)}


@app.get('/api/v1/albert/orders')
def albert_orders_list(pid: str = '', limit: int = 50):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    return {'status': 'ready', 'orders': _order_mgr.list_intents(pid, limit=limit)}


@app.get('/api/v1/albert/paper-portfolio')
def albert_paper_portfolio(pid: str = '', accountId: str = 'paper'):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    materialized = _paper_ledger.materialize(pid, accountId)
    recon = _paper_ledger.reconcile(pid, accountId)
    return {'status': 'ready', 'paperPortfolio': materialized, 'reconciliation': recon}


@app.post('/api/v1/albert/paper-reset')
def albert_paper_reset(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    _paper_ledger.reset(pid, payload.get('accountId') or 'paper')
    # Phase G: a paper reset also clears the drawdown high-water mark + protection state.
    _portfolio_risk_repo.reset(pid)
    return {'status': 'reset'}


@app.get('/api/v1/albert/portfolio-risk')
def albert_portfolio_risk(pid: str = ''):
    """Phase G: current portfolio drawdown-protection state (HWM, drawdown, protection
    mode + hysteresis) for the Command Centre banner. Evaluation is deterministic and
    stateful (persisted). The full per-asset risk-reduction plan is in /decisions."""
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    summary = _portfolio_summary(pid)
    mandate = _get_mandate(pid)
    pr = _portfolio_risk_repo.evaluate(pid, summary.get('total_value'), mandate.get('max_drawdown_pct'))
    pr['triggeredAt'] = pr.get('protectionActivatedAt')
    return {'status': 'ready', 'portfolioRisk': pr}


# ---- Phase I: Top-100 Discovery ---------------------------------------------
from albert.engine import discovery as _discovery_mod  # noqa: E402

import threading as _threading

_DISCOVERY_CACHE = {'ts': 0.0, 'core': None, 'building': False}


def _discovery_universe_rows():
    """Provider layer: live top-100 by market cap via the CoinGecko public API."""
    arr = _engine_get('https://api.coingecko.com/api/v3/coins/markets', params={
        'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 100, 'page': 1,
        'price_change_percentage': '24h'}) or []
    rows, src_ts = [], None
    for c in arr:
        sym = str(c.get('symbol') or '').upper()
        if not sym:
            continue
        rows.append({'symbol': sym, 'name': c.get('name'), 'rank': c.get('market_cap_rank'),
                     'marketCapUsd': c.get('market_cap'), 'priceUsd': c.get('current_price'),
                     'volume24hUsd': c.get('total_volume')})
        if c.get('last_updated'):
            src_ts = c.get('last_updated')
    return rows, (src_ts or datetime.datetime.utcnow().isoformat())


def _discovery_build():
    """Heavy rebuild (CoinGecko + scoring). Runs in a background thread."""
    try:
        rows, src_ts = _discovery_universe_rows()
        if not rows:
            return
        tradable = set(ALERT_COIN_PAIRS.keys()) | {'BTC'}
        reg = _albert_regime() or {}
        core = _discovery_mod.assemble_core(
            rows=rows, regime=(reg.get('regime') or 'RANGE'), tradable_set=tradable,
            score_fn=_score_asset, engine_version=ALBERT_ENGINE_VERSION,
            source='coingecko', source_ts=src_ts)
        _DISCOVERY_CACHE['core'] = core
        _DISCOVERY_CACHE['ts'] = _time_mod.time()
        try:
            from config import discovery_snapshots_col
            discovery_snapshots_col.insert_one({'_id': core['universeSnapshotId'], **core})
        except Exception:  # noqa
            pass
    except Exception:  # noqa
        traceback.print_exc()
    finally:
        _DISCOVERY_CACHE['building'] = False


def _discovery_core():
    """Return the cached core; trigger a background rebuild when stale/missing so the
    request never blocks on the ~scoring pass. Serves the last snapshot while rebuilding."""
    now = _time_mod.time()
    core = _DISCOVERY_CACHE.get('core')
    fresh = core and (now - _DISCOVERY_CACHE['ts']) < _discovery_mod.DISCOVERY_TTL_SEC
    if not fresh and not _DISCOVERY_CACHE.get('building'):
        _DISCOVERY_CACHE['building'] = True
        _threading.Thread(target=_discovery_build, daemon=True).start()
    return core


@app.get('/api/v1/albert/discovery')
def albert_discovery(pid: str = ''):
    """Phase I: live top-100 discovery feed. Discovery is NOT permission to buy — the
    core (rank/liquidity/data-quality/opportunity score) is pid-independent; mandate
    eligibility + the honest discovery call are applied for this pid on top. If no
    snapshot exists yet it returns status 'building' (poll again shortly)."""
    core = _discovery_core()
    if not core:
        return {'status': 'building', 'assets': []}
    stale = (_time_mod.time() - _DISCOVERY_CACHE['ts']) >= _discovery_mod.DISCOVERY_TTL_SEC
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'status': 'ready', 'stale': stale, **core}
    summary = _portfolio_summary(pid)
    mandate = _get_mandate(pid)
    view = _discovery_mod.apply_eligibility(
        core, held={h['asset'] for h in summary.get('holdings', [])},
        excluded=set(mandate.get('excluded_coins') or []),
        approved=set(mandate.get('approved_coins') or []),
        mandate_complete=bool(summary.get('mandate_complete')))
    return {'status': 'ready', 'stale': stale, **view}


# ---- Discovery Watchlist: pin/unpin discovered assets (pin != permission to buy) ----
def _watchlist_symbols(pid):
    from config import discovery_watchlist_col
    return [d['symbol'] for d in discovery_watchlist_col.find({'pid': pid}).sort('pinnedAt', -1)]


@app.get('/api/v1/albert/watchlist')
def albert_watchlist(pid: str = ''):
    """Discovery watchlist for this pid, enriched with the CURRENT discovery core +
    per-pid eligibility so a pinned coin still shows its honest call. Pinning is a
    bookmark only — an ineligible pinned coin still shows WAIT, never BUY."""
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    symbols = _watchlist_symbols(pid)
    pinned_at = {}
    try:
        from config import discovery_watchlist_col
        for d in discovery_watchlist_col.find({'pid': pid}):
            pinned_at[d['symbol']] = d.get('pinnedAt')
    except Exception:  # noqa
        pass
    core = _DISCOVERY_CACHE.get('core')
    assets = []
    if core and symbols:
        summary = _portfolio_summary(pid)
        mandate = _get_mandate(pid)
        view = _discovery_mod.apply_eligibility(
            core, held={h['asset'] for h in summary.get('holdings', [])},
            excluded=set(mandate.get('excluded_coins') or []),
            approved=set(mandate.get('approved_coins') or []),
            mandate_complete=bool(summary.get('mandate_complete')))
        by_sym = {a['symbol']: a for a in view.get('assets', [])}
        for s in symbols:
            a = by_sym.get(s)
            if a:
                a = dict(a); a['pinnedAt'] = pinned_at.get(s); a['inUniverse'] = True
            else:
                a = {'symbol': s, 'pinnedAt': pinned_at.get(s), 'inUniverse': False,
                     'albertCall': 'WAIT', 'eligible': False, 'opportunityScore': None}
            assets.append(a)
    else:
        assets = [{'symbol': s, 'pinnedAt': pinned_at.get(s), 'inUniverse': None,
                   'albertCall': None, 'opportunityScore': None} for s in symbols]
    return {'status': 'ready', 'symbols': symbols, 'assets': assets,
            'buyThreshold': (core or {}).get('buyThreshold'), 'regime': (core or {}).get('regime'),
            'note': 'Pinning is a bookmark — eligibility & sizing stay in the Command Centre.'}


@app.post('/api/v1/albert/watchlist')
def albert_watchlist_pin(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    sym = (str(payload.get('symbol') or '')).strip().upper()[:20]
    if not pid or not sym:
        return {'error': 'pid and symbol required'}
    from config import discovery_watchlist_col
    discovery_watchlist_col.update_one(
        {'pid': pid, 'symbol': sym},
        {'$set': {'pid': pid, 'symbol': sym},
         '$setOnInsert': {'pinnedAt': datetime.datetime.utcnow().isoformat()}},
        upsert=True)
    return {'status': 'ready', 'pinned': True, 'symbols': _watchlist_symbols(pid)}


@app.delete('/api/v1/albert/watchlist/{symbol}')
def albert_watchlist_unpin(symbol: str, pid: str = ''):
    pid = (pid or '').strip()[:80]
    sym = (symbol or '').strip().upper()[:20]
    if not pid or not sym:
        return {'error': 'pid and symbol required'}
    from config import discovery_watchlist_col
    discovery_watchlist_col.delete_one({'pid': pid, 'symbol': sym})
    return {'status': 'ready', 'pinned': False, 'symbols': _watchlist_symbols(pid)}
def albert_lifecycle_assets(pid: str = ''):
    """Phase H: assets that have a stored decision journey (snapshots/history/fills),
    whether currently held or only historically traded. Powers the 'View Journey' entry."""
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    from config import decision_snapshots_col as _dsc, order_ledger_col as _olc
    assets = set()
    try:
        assets |= set(_dsc.distinct('asset', {'pid': pid}))
        assets |= set(_olc.distinct('asset', {'pid': pid}))
    except Exception:  # noqa
        pass
    return {'status': 'ready', 'assets': sorted(a for a in assets if a)}


@app.get('/api/v1/albert/lifecycle/{asset}')
def albert_lifecycle(asset: str, pid: str = ''):
    """Phase H: read-only per-asset lifecycle replay assembled from frozen snapshots,
    history, paper orders and fills. Never recomputes historical decisions."""
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    return _lifecycle_repo.build_lifecycle(pid, asset)


EXPLAIN_ORDER_SYSTEM = (
    "You are Albert. You are given ONE frozen paper OrderIntent (and its audit/fills) as read-only JSON. "
    "EXPLAIN ONLY. You may explain: why the order exists (its reasonCode + decision), the exact quantity/amount, "
    "the price limits and slippage tolerance, why it was rejected (e.g. STALE_DECISION means the engine's numbers "
    "moved so a fresh intent is required; SLIPPAGE_EXCEEDED means execution price breached the limit), partial "
    "fills, and why a new intent must be created after a terminal state. ABSOLUTE RULES: never invent or change "
    "any number, price, quantity, state, or limit; never suggest you can create/confirm/execute/cancel/amend an "
    "order — you cannot. Use the exact figures given. Do not output JSON."
)


@app.post('/api/v1/albert/explain-order-intent')
def albert_explain_order(payload: dict = Body(...)):
    order_id = (str(payload.get('orderIntentId') or '')).strip()
    question = (str(payload.get('question') or '')).strip()[:400]
    intent = _order_mgr.get_intent(order_id)
    if not intent:
        return {'status': 'not_found'}
    audit = _order_mgr.get_audit(order_id)
    dto = {'intent': intent, 'audit': audit}
    if not (LLM_READY_KEY and _HAS_LLM):
        return {'status': 'ready', 'explanation': '', 'intent': intent, 'audit': audit, 'error': 'LLM not configured'}
    try:
        q = ('Explain this order intent.' if not question else question)
        prompt = 'Frozen paper OrderIntent + audit (read-only JSON):\n' + json.dumps(dto, default=str) + '\n\nUser question: ' + q

        def _call():
            async def _go():
                chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'explain-order-{order_id}', system_message=EXPLAIN_ORDER_SYSTEM)
                        .with_model('gemini', _model_for('chat_standard')).with_params(temperature=0.2, max_tokens=3000))
                return await chat.send_message(UserMessage(text=prompt))
            return asyncio.run(_go())
        reply = _LLM_POOL.submit(_call).result(timeout=60)
        text = reply.strip() if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '').strip()
    except Exception:  # noqa
        traceback.print_exc()
        text = ''
    # OrderIntent returned UNCHANGED alongside the explanation (LLM cannot mutate it).
    return {'status': 'ready', 'explanation': text, 'intent': intent, 'audit': audit, 'model': _model_for('chat_standard')}


@app.get('/api/v1/albert/deployment-plan')
def albert_deployment_plan(pid: str = ''):
    pid = (pid or '').strip()[:80]
    if not pid:
        return {'error': 'pid required'}
    snap = _albert_decisions(pid)
    return {'regime': snap['regime'], 'deployableUsdc': snap['deployableUsdc'],
            'regimeDeployCeiling': snap['regimeDeployCeiling'], 'totalDeployNowUsd': snap['totalDeployNowUsd'],
            'albertCall': snap['albertCall'], 'sellCount': snap.get('sellCount', 0),
            'plan': [{'symbol': d['symbol'], 'action': d['action'], 'deployNow': d['recommendedDeployNowUsd'],
                      'totalPlanned': d['totalPlannedDeploymentUsd'], 'tranches': d['tranches']}
                     for d in snap['decisions'] if d['action'] == 'BUY'],
            'sells': [{'symbol': d['symbol'], 'action': d['sellPlan']['action'],
                       'reasonCode': d['reasonCode'], 'fraction': d['sellPlan']['fraction'],
                       'sellUsd': d['sellPlan']['sellUsd'], 'sellQty': d['sellPlan']['sellQty'],
                       'note': d['sellPlan']['note']}
                      for d in snap['decisions'] if d['action'] == 'SELL']}


@app.post('/api/v1/price-alert')
def create_price_alert(payload: dict = Body(...)):
    try:
        asset = str(payload.get('asset') or 'BTC').upper().strip()[:6]
        level = float(payload.get('level'))
    except Exception:  # noqa
        return {'error': 'invalid_level'}
    if level <= 0:
        return {'error': 'invalid_level'}
    pid = (str(payload.get('pid') or '')).strip()[:80]
    spot = _spot_price(asset)
    direction = payload.get('direction')
    if direction not in ('above', 'below'):
        direction = 'above' if (spot is None or level >= spot) else 'below'
    wid = str(uuid.uuid4())
    price_watch_col.insert_one({
        '_id': wid, 'id': wid, 'pid': pid, 'asset': asset, 'level': round(level, 2),
        'direction': direction, 'created_price': spot, 'triggered': False,
        'created_at': datetime.datetime.utcnow().isoformat(),
    })
    return {'ok': True, 'id': wid, 'asset': asset, 'level': round(level, 2), 'direction': direction, 'spot': spot}


@app.get('/api/v1/price-alerts')
def list_price_alerts(pid: str = ''):
    q = {}
    if pid:
        q['pid'] = pid.strip()[:80]
    active = list(price_watch_col.find({**q, 'triggered': False}, {'_id': 0}).sort('created_at', -1).limit(50))
    triggered = list(price_watch_col.find({**q, 'triggered': True}, {'_id': 0}).sort('triggered_at', -1).limit(20))
    return {'watches': active, 'triggered': triggered}


@app.delete('/api/v1/price-alert/{wid}')
def delete_price_alert(wid: str):
    price_watch_col.delete_one({'_id': wid})
    return {'ok': True}


def _check_price_watches():
    """Scheduler job: fire an in-app/browser notification when a watched level is crossed."""
    try:
        watches = list(price_watch_col.find({'triggered': False}).limit(200))
    except Exception:  # noqa
        return
    price_cache = {}
    for w in watches:
        asset = w.get('asset', 'BTC')
        if asset not in price_cache:
            price_cache[asset] = _spot_price(asset)
        spot = price_cache[asset]
        if spot is None:
            continue
        level = w.get('level')
        direction = w.get('direction')
        hit = (direction == 'above' and spot >= level) or (direction == 'below' and spot <= level)
        if not hit:
            continue
        push_alert('price_watch', 'high', f"{asset} crossed ${level:,.0f}",
                   f"{asset} is now ${spot:,.2f}, {direction} the ${level:,.0f} level Albert flagged.",
                   w.get('id'))
        price_watch_col.update_one({'_id': w['_id']},
                                   {'$set': {'triggered': True, 'triggered_price': spot,
                                             'triggered_at': datetime.datetime.utcnow().isoformat()}})


CALL_EXTRACT_SYSTEM = (
    "You extract the single primary actionable trading call from a crypto analyst's answer. "
    "Return ONLY strict minified JSON (no prose, no markdown) with keys: "
    "stance (one of 'buy','sell','hold','wait','none'), asset (ticker like BTC/ETH/SOL, default BTC), "
    "ref_price (number or null: the current/entry price the call is anchored to), "
    "target (number or null), invalidation (number or null), horizon_days (integer, default 14), "
    "conviction (one of 'low','medium','high'), summary (<=120 chars). "
    "Map accumulate/buy the dip -> 'buy'; trim/take profit/distribute/short -> 'sell'. "
    "If the answer gives no clear directional call, use stance='none'."
)


def _log_albert_call(session_id, symbol, question, answer):
    """Background self-check: parse Albert's own answer into a structured call and log it."""
    if not (LLM_READY_KEY and _HAS_LLM):
        return
    try:
        def _call():
            async def _go():
                chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'callx-{session_id}',
                                system_message=CALL_EXTRACT_SYSTEM)
                        .with_model('gemini', CHAT_MODEL).with_params(temperature=0.0, max_tokens=2000))
                return await chat.send_message(UserMessage(text=f"Analyst answer:\n{answer[:2500]}"))
            return asyncio.run(_go())
        reply = _LLM_POOL.submit(_call).result(timeout=20)
        raw = reply.strip() if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '').strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return
        data = json.loads(m.group(0))
        stance = str(data.get('stance', 'none')).lower()
        if stance not in ('buy', 'sell'):
            return  # only grade directional calls
        asset = str(data.get('asset') or symbol or 'BTC').upper()[:6]
        ref_price = _num(data.get('ref_price')) or _spot_price(asset)
        if not ref_price:
            return
        horizon = max(1, min(120, int(data.get('horizon_days') or 14)))
        cid = str(uuid.uuid4())
        albert_calls_col.insert_one({
            '_id': cid, 'id': cid, 'session_id': session_id, 'asset': asset, 'stance': stance,
            'ref_price': round(ref_price, 2), 'target': _num(data.get('target')),
            'invalidation': _num(data.get('invalidation')),
            'conviction': str(data.get('conviction') or 'medium').lower(),
            'summary': str(data.get('summary') or '')[:200], 'question': (question or '')[:200],
            'reasoning': (answer or '')[:1800],
            'horizon_days': horizon, 'created_at': datetime.datetime.utcnow().isoformat(),
            'status': 'open', 'outcome': None,
        })
    except Exception:  # noqa
        traceback.print_exc()


def _grade_albert_calls():
    """Scheduler job: grade open calls whose horizon has elapsed against actual price."""
    now = datetime.datetime.utcnow()
    try:
        open_calls = list(albert_calls_col.find({'status': 'open'}).limit(300))
    except Exception:  # noqa
        return
    price_cache = {}
    graded_any = False
    for c in open_calls:
        try:
            created = datetime.datetime.fromisoformat(c['created_at'])
        except Exception:  # noqa
            continue
        if now < created + datetime.timedelta(days=int(c.get('horizon_days') or 14)):
            continue
        asset = c.get('asset', 'BTC')
        if asset not in price_cache:
            price_cache[asset] = _spot_price(asset)
        spot = price_cache[asset]
        ref = c.get('ref_price')
        if spot is None or not ref:
            continue
        pct = (spot - ref) / ref * 100
        correct = (spot >= ref) if c.get('stance') == 'buy' else (spot <= ref)
        albert_calls_col.update_one({'_id': c['_id']}, {'$set': {
            'status': 'graded', 'outcome': 'correct' if correct else 'incorrect',
            'eval_price': round(spot, 2), 'pct_move': round(pct, 2), 'eval_at': now.isoformat(),
        }})
        graded_any = True
    if graded_any:
        try:
            _check_streak_alerts()
        except Exception:  # noqa
            traceback.print_exc()


HOT_STREAK_THRESHOLD = 3  # wins-in-a-row that counts as a "hot streak"


def _current_streak():
    """Return the current {'type','count'} streak from graded calls, or None."""
    try:
        chrono = list(albert_calls_col.find({'status': 'graded'}, {'_id': 0, 'outcome': 1, 'eval_at': 1})
                      .sort('eval_at', 1))
    except Exception:  # noqa
        return None
    if not chrono:
        return None
    last = chrono[-1].get('outcome')
    cnt = 0
    for g in reversed(chrono):
        if g.get('outcome') == last:
            cnt += 1
        else:
            break
    return {'type': 'win' if last == 'correct' else 'loss', 'count': cnt}


def _check_streak_alerts():
    """Ping the bell when Albert STARTS a hot streak or BREAKS a cold one.
    Compares the freshly-computed streak against the last-seen state in the DB."""
    cur = _current_streak()
    if not cur:
        return
    try:
        prev_doc = recap_col.find_one({'_id': 'streak_state'}) or {}
    except Exception:  # noqa
        prev_doc = {}
    prev_type = prev_doc.get('type')
    prev_count = prev_doc.get('count', 0)
    # Cold streak that was building before this update (>=2 losses in a row).
    was_cold = prev_type == 'loss' and prev_count >= 2
    if cur['type'] == 'win':
        # Breaks a cold streak: previous state was a losing run, now back to winning.
        if was_cold:
            push_alert('albert_streak', 'success', 'Albert broke his cold streak',
                       f"After {prev_count} misses in a row, Albert's latest call landed. He's back on the board — check his track record.",
                       f"coldbreak-{datetime.date.today().isoformat()}")
        # Starts a hot streak: crosses the hot-streak threshold on the way up.
        if cur['count'] >= HOT_STREAK_THRESHOLD and prev_count < HOT_STREAK_THRESHOLD:
            push_alert('albert_streak', 'success', f"Albert is on a {cur['count']}-call hot streak",
                       f"Albert has now called {cur['count']} in a row correctly. He's running hot — see his track record for the wins.",
                       f"hotstart-{datetime.date.today().isoformat()}-{cur['count']}")
    try:
        recap_col.update_one({'_id': 'streak_state'},
                             {'$set': {'type': cur['type'], 'count': cur['count'],
                                       'updated_at': datetime.datetime.utcnow().isoformat()}},
                             upsert=True)
    except Exception:  # noqa
        pass


def _target_progress(g):
    """How close a graded call got to its take-profit target vs its invalidation.
    Returns a signed ratio where 1.0 == target reached, 0 == flat at entry,
    negative == moved toward (or past) the invalidation. Direction-aware for
    buy vs sell. Falls back to directional % move when target is missing."""
    try:
        ref = g.get('ref_price')
        ev = g.get('eval_price')
        stance = g.get('stance')
        tgt = g.get('target')
        if not ref or ev is None or not stance:
            return None
        if tgt and tgt != ref:
            if stance == 'buy':
                return (ev - ref) / (tgt - ref)
            return (ref - ev) / (ref - tgt)
        # No usable target -> use directional move fraction (per-unit, e.g. 0.05 = +5%)
        dir_move = (ev - ref) / ref if stance == 'buy' else (ref - ev) / ref
        return dir_move
    except Exception:  # noqa
        return None


def _best_worst_calls(graded):
    """Pick Albert's single best and worst graded calls, ranked by how close
    each got to its target vs invalidation."""
    scored = []
    for g in graded:
        s = _target_progress(g)
        if s is None:
            continue
        dir_move = None
        try:
            if g.get('stance') == 'buy':
                dir_move = g.get('pct_move')
            else:
                dir_move = -g.get('pct_move') if g.get('pct_move') is not None else None
        except Exception:  # noqa
            dir_move = None
        scored.append({**g, 'score': round(s, 3),
                       'progress_pct': round(s * 100, 1),
                       'dir_move': round(dir_move, 2) if dir_move is not None else None})
    if not scored:
        return None, None
    best = max(scored, key=lambda x: x['score'])
    worst = min(scored, key=lambda x: x['score'])
    if best.get('id') == worst.get('id'):
        worst = None  # only one gradeable call so far
    return best, worst


_genai_client = None
_TTS_CACHE = {}
ALBERT_TTS_STYLE = ("Speak as Albert — a brilliant, delightfully eccentric professor who is absolutely "
                    "THRILLED to share what he knows. Energetic and animated, bursting with contagious "
                    "enthusiasm and childlike wonder, with lively pace, dramatic emphasis on key ideas and "
                    "a playful spark. Warm, clever and a little theatrical — never flat or monotone.")


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def _pcm_to_wav(pcm, rate=24000):
    """Gemini TTS returns raw signed-16-bit mono PCM @24kHz; wrap it in a WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


@app.post('/api/v1/tts')
def albert_tts(payload: dict = Body(...)):
    """Generate Albert's spoken audio via Google AI Studio Gemini TTS (server-side).
    Returns base64 WAV. Falls back gracefully (frontend uses browser TTS on failure)."""
    text = (payload.get('text') or '').strip()
    if not text:
        return JSONResponse({'error': 'empty'}, status_code=400)
    if not GEMINI_API_KEY:
        return JSONResponse({'error': 'tts_unavailable'}, status_code=503)
    text = text[:8000]
    voice = payload.get('voice') or GEMINI_TTS_VOICE
    style = payload.get('style') or ALBERT_TTS_STYLE
    import hashlib
    key = hashlib.md5(f'{GEMINI_TTS_MODEL}|{voice}|{style}|{text}'.encode('utf-8')).hexdigest()
    cached = _TTS_CACHE.get(key)
    if cached:
        return {'audio_base64': cached, 'mime_type': 'audio/wav', 'cached': True}
    try:
        from google.genai import types
        client = _get_genai_client()
        prompt = f"{style}\n\nRead exactly the following, and nothing else:\n{text}"

        def _gen():
            return client.models.generate_content(
                model=GEMINI_TTS_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['AUDIO'],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))),
            )
        resp = _LLM_POOL.submit(_gen).result(timeout=45)
        data = resp.candidates[0].content.parts[0].inline_data.data
        wav_b64 = base64.b64encode(_pcm_to_wav(bytes(data))).decode('ascii')
        if len(_TTS_CACHE) > 40:
            _TTS_CACHE.clear()
        _TTS_CACHE[key] = wav_b64
        return {'audio_base64': wav_b64, 'mime_type': 'audio/wav', 'cached': False}
    except Exception:  # noqa
        traceback.print_exc()
        return JSONResponse({'error': 'tts_failed'}, status_code=502)


# Curated set of Gemini prebuilt voices offered for Albert. Names are the exact
# `voice_name` values accepted by the Gemini TTS API (case-insensitive).
ALBERT_VOICE_CHOICES = [
    {'id': 'Charon', 'name': 'Albert (Classic)', 'desc': 'Informative & warm — the original Albert', 'gender': 'male'},
    {'id': 'Fenrir', 'name': 'Excitable Professor', 'desc': 'Energetic, animated, bursting with enthusiasm', 'gender': 'male'},
    {'id': 'Puck', 'name': 'Upbeat Guide', 'desc': 'Lively and upbeat, keeps things fun', 'gender': 'male'},
    {'id': 'Orus', 'name': 'Confident Analyst', 'desc': 'Firm, steady and self-assured', 'gender': 'male'},
    {'id': 'Iapetus', 'name': 'Clear Lecturer', 'desc': 'Crisp, clear and articulate', 'gender': 'male'},
    {'id': 'Algieba', 'name': 'Smooth Narrator', 'desc': 'Smooth, mellow and relaxed', 'gender': 'male'},
    {'id': 'Gacrux', 'name': 'Seasoned Veteran', 'desc': 'Mature, seasoned, well-aged wisdom', 'gender': 'male'},
    {'id': 'Rasalgethi', 'name': 'Deep Briefer', 'desc': 'Informative with a fuller, deeper tone', 'gender': 'male'},
    {'id': 'Sadaltager', 'name': 'The Scholar', 'desc': 'Knowledgeable and measured', 'gender': 'male'},
    {'id': 'Sulafat', 'name': 'Warm Companion', 'desc': 'Warm and friendly', 'gender': 'female'},
    {'id': 'Zephyr', 'name': 'Bright Assistant', 'desc': 'Bright and clear', 'gender': 'female'},
    {'id': 'Aoede', 'name': 'Breezy Host', 'desc': 'Breezy, light and easy-going', 'gender': 'female'},
]


@app.get('/api/v1/tts/voices')
def albert_tts_voices():
    """Curated Gemini voices offered on the Meet Albert voice picker."""
    return {'status': 'ready', 'default': GEMINI_TTS_VOICE,
            'tts_available': bool(GEMINI_API_KEY), 'voices': ALBERT_VOICE_CHOICES}


@app.get('/api/v1/albert/voice-pref')
def get_voice_pref(pid: str = ''):
    """User's saved Albert voice preference (per-account; falls back to the
    legacy global doc, then defaults)."""
    pid = (pid or '').strip()[:80]
    doc = {}
    try:
        if pid:
            doc = insights_col.find_one({'_id': f'cfg:albert_voice:{pid}'}, {'_id': 0}) or {}
        if not doc:
            doc = insights_col.find_one({'_id': 'cfg:albert_voice'}, {'_id': 0}) or {}
    except Exception:
        doc = {}
    return {'status': 'ready', 'engine': doc.get('engine', 'gemini'),
            'voice': doc.get('voice', GEMINI_TTS_VOICE),
            'browser_voice_uri': doc.get('browser_voice_uri', '')}


@app.post('/api/v1/albert/voice-pref')
def set_voice_pref(payload: dict = Body(...)):
    pid = (str(payload.get('pid') or '')).strip()[:80]
    engine = (payload.get('engine') or 'gemini').strip().lower()
    if engine not in ('gemini', 'browser'):
        engine = 'gemini'
    voice = (payload.get('voice') or GEMINI_TTS_VOICE).strip()
    valid = {v['id'] for v in ALBERT_VOICE_CHOICES}
    if engine == 'gemini' and voice not in valid:
        voice = GEMINI_TTS_VOICE
    browser_voice_uri = (payload.get('browser_voice_uri') or '').strip()[:200]
    doc_id = f'cfg:albert_voice:{pid}' if pid else 'cfg:albert_voice'
    insights_col.update_one({'_id': doc_id},
                            {'$set': {'_id': doc_id, 'kind': 'config', 'engine': engine,
                                      'voice': voice, 'browser_voice_uri': browser_voice_uri,
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    return {'status': 'ready', 'engine': engine, 'voice': voice, 'browser_voice_uri': browser_voice_uri}


@app.get('/api/v1/albert/track-record')
def albert_track_record(limit: int = 20):
    try:
        graded = list(albert_calls_col.find({'status': 'graded'}, {'_id': 0}).sort('eval_at', -1))
        open_calls = list(albert_calls_col.find({'status': 'open'}, {'_id': 0}).sort('created_at', -1).limit(limit))
        total = albert_calls_col.count_documents({})
    except Exception:  # noqa
        return {'status': 'ready', 'n_calls': 0, 'n_graded': 0, 'hit_rate': None, 'recent': [], 'open': []}
    n_graded = len(graded)
    n_correct = sum(1 for g in graded if g.get('outcome') == 'correct')
    # Per-coin win-rate so the UI can show where Albert is strongest.
    by_coin_map = {}
    for g in graded:
        a = g.get('asset') or '?'
        s = by_coin_map.setdefault(a, {'asset': a, 'n': 0, 'correct': 0})
        s['n'] += 1
        if g.get('outcome') == 'correct':
            s['correct'] += 1
    by_coin = sorted(
        [{'asset': v['asset'], 'n': v['n'], 'hit_rate': round(v['correct'] / v['n'] * 100, 1)} for v in by_coin_map.values()],
        key=lambda x: (-x['hit_rate'], -x['n']))
    # Cumulative hit-rate over time (chronological) so the UI can chart whether
    # Albert's calls are getting sharper.
    chrono = sorted(graded, key=lambda g: g.get('eval_at') or '')
    trend = []
    run_correct = 0
    for i, g in enumerate(chrono, 1):
        if g.get('outcome') == 'correct':
            run_correct += 1
        trend.append({'i': i, 'date': (g.get('eval_at') or '')[:10], 'hit_rate': round(run_correct / i * 100, 1)})
    price_cache = {}
    open_out = []
    for c in open_calls[:limit]:
        asset = c.get('asset', 'BTC')
        if asset not in price_cache:
            price_cache[asset] = _spot_price(asset)
        spot = price_cache[asset]
        ref = c.get('ref_price')
        live_pct = round((spot - ref) / ref * 100, 2) if (spot and ref) else None
        winning = None
        if spot and ref:
            winning = (spot >= ref) if c.get('stance') == 'buy' else (spot <= ref)
        open_out.append({**c, 'spot': spot, 'live_pct': live_pct, 'winning': winning})
    best, worst = _best_worst_calls(graded)
    # Current win/loss streak: consecutive same-outcome calls counting back from
    # the most recently graded call. Also track the longest win streak for flavour.
    streak = None
    longest_win = 0
    if chrono:
        last_outcome = chrono[-1].get('outcome')
        cnt = 0
        for g in reversed(chrono):
            if g.get('outcome') == last_outcome:
                cnt += 1
            else:
                break
        streak = {'type': 'win' if last_outcome == 'correct' else 'loss', 'count': cnt}
        run = 0
        for g in chrono:
            if g.get('outcome') == 'correct':
                run += 1
                longest_win = max(longest_win, run)
            else:
                run = 0
    return {
        'status': 'ready', 'n_calls': total, 'n_graded': n_graded, 'n_correct': n_correct,
        'hit_rate': round(n_correct / n_graded * 100, 1) if n_graded else None,
        'avg_move': round(sum(g.get('pct_move', 0) for g in graded) / n_graded, 2) if n_graded else None,
        'trend': trend, 'by_coin': by_coin,
        'best_call': best, 'worst_call': worst,
        'streak': streak, 'longest_win_streak': longest_win,
        'recent': graded[:limit], 'open': open_out,
    }


@app.get('/api/v1/albert/weekly-recap')
def albert_weekly_recap(refresh: bool = False):
    """Albert's short weekly note: how his calls performed + what he's watching next.
    Cached for ~24h (regenerate with ?refresh=true) to keep it cheap and fast."""
    now = datetime.datetime.utcnow()
    try:
        cached = recap_col.find_one({'_id': 'weekly'})
    except Exception:  # noqa
        cached = None
    if cached and not refresh:
        try:
            ts = datetime.datetime.fromisoformat(cached.get('created_at'))
            if (now - ts).total_seconds() < 24 * 3600:
                return {'status': 'ready', 'text': cached.get('text', ''), 'created_at': cached.get('created_at'), 'cached': True}
        except Exception:  # noqa
            pass
    if not (LLM_READY_KEY and _HAS_LLM):
        return {'status': 'unavailable', 'text': ''}
    # Build a compact performance digest from the last 7 days of calls.
    wk_ago = (now - datetime.timedelta(days=7)).isoformat()
    try:
        graded = list(albert_calls_col.find({'status': 'graded', 'eval_at': {'$gte': wk_ago}}, {'_id': 0}))
        open_calls = list(albert_calls_col.find({'status': 'open'}, {'_id': 0}).sort('created_at', -1).limit(10))
    except Exception:  # noqa
        graded, open_calls = [], []
    n_g = len(graded)
    n_c = sum(1 for g in graded if g.get('outcome') == 'correct')
    digest = f"Graded calls last 7d: {n_g} ({n_c} correct" + (f", {round(n_c / n_g * 100)}% hit rate)" if n_g else ")")
    for g in graded[:8]:
        digest += f"\n- {g.get('stance', '').upper()} {g.get('asset')} @ ${g.get('ref_price')}: {g.get('outcome')} ({g.get('pct_move')}% move)"
    if open_calls:
        digest += "\nStill open: " + ", ".join(f"{c.get('stance','').upper()} {c.get('asset')} @ ${c.get('ref_price')}" for c in open_calls[:6])
    ctx = build_chat_context('BTC')
    prompt = (
        "Write Albert's WEEKLY RECAP as a short, punchy note (max ~180 words). Two clearly-labelled parts:\n"
        "**How my calls did** — honestly summarise the graded results below (own the misses, celebrate the hits); "
        "if there are no graded calls yet, say the current open calls are still playing out.\n"
        "**What I'm watching next week** — 3 concrete catalysts / levels / metrics to watch (use the live dashboard "
        "data and a quick web search for next week's macro/crypto calendar).\n"
        "Use **bold** labels and tight bullets. No greeting, no disclaimer.\n\n"
        f"=== MY CALL PERFORMANCE (last 7 days) ===\n{digest}\n"
    )
    try:
        text, _model, _src = _albert_answer(ctx, prompt, 'weekly-recap', deep=False)
    except Exception:  # noqa
        text = ''
    if not text:
        return {'status': 'unavailable', 'text': ''}
    recap_col.update_one({'_id': 'weekly'},
                         {'$set': {'text': text, 'created_at': now.isoformat(),
                                   'stats': {'n_graded': n_g, 'n_correct': n_c}}}, upsert=True)
    # Archive one recap per ISO week so users can scroll back through history.
    try:
        iso = now.isocalendar()
        wk_id = f'wk-{iso[0]}-{iso[1]:02d}'
        week_label = f'Week {iso[1]}, {iso[0]}'
        recap_col.update_one({'_id': wk_id},
                             {'$set': {'kind': 'archive', 'text': text,
                                       'created_at': now.isoformat(), 'week_label': week_label,
                                       'stats': {'n_graded': n_g, 'n_correct': n_c,
                                                 'hit_rate': round(n_c / n_g * 100) if n_g else None}}},
                             upsert=True)
    except Exception:  # noqa
        pass
    return {'status': 'ready', 'text': text, 'created_at': now.isoformat(), 'cached': False}


@app.get('/api/v1/albert/weekly-recap/history')
def albert_weekly_recap_history():
    """All archived weekly recaps, newest first, so users can look back at how
    each week played out."""
    try:
        rows = list(recap_col.find({'kind': 'archive'}, {'_id': 0}).sort('created_at', -1))
    except Exception:  # noqa
        rows = []
    return {'status': 'ready', 'recaps': rows}


def _weekly_recap_autopost():
    """Scheduler (Mondays): regenerate the weekly recap and drop it into the notification bell."""
    try:
        res = albert_weekly_recap(refresh=True)
        if res.get('status') == 'ready' and res.get('text'):
            push_alert('weekly_recap', 'info', "Albert's Weekly Recap is ready",
                       "How Albert's calls did this week + what he's watching next week — open Ask Albert to read it.",
                       f"recap-{datetime.date.today().isoformat()}")
    except Exception:  # noqa
        traceback.print_exc()


BRIEF_COINS = [s.strip().upper() for s in os.environ.get('BRIEF_COINS', 'BTC,ETH,SOL').split(',') if s.strip()]


def _generate_daily_brief(symbol):
    """Ensure today's plain-English brief exists for `symbol`; return (take, coin_name)."""
    today = datetime.date.today().isoformat()
    is_btc = symbol == 'BTC'
    cache_id = f'brief:{today}:plain' if is_btc else f'brief:{today}:plain:{symbol}'
    doc = insights_col.find_one({'_id': cache_id}, {'_id': 0})
    coin_name = 'Bitcoin' if is_btc else COMPARE_COINS.get(symbol, {}).get('name', symbol)
    if doc:
        return (doc.get('take') or ''), (doc.get('coin') or coin_name)
    take = ''
    if LLM_READY_KEY and _HAS_LLM:
        if is_btc:
            ctx, as_of = _brief_context()
            sys_msg = ALBERT_BRIEF_SYSTEM.format(ctx=ctx)
        else:
            ctx, coin_name, as_of = _coin_brief_context(symbol)
            sys_msg = ALBERT_BRIEF_COIN_SYSTEM.format(ctx=ctx, coin=coin_name)
        if ctx.strip():
            def _call():
                async def _go():
                    chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'brief-{uuid.uuid4().hex[:8]}',
                                    system_message=sys_msg)
                            .with_model('gemini', _model_for('brief')).with_params(temperature=0.4, max_tokens=6000))
                    return await chat.send_message(UserMessage(text=f"Write today's {coin_name} brief now."))
                return asyncio.run(_go())
            reply = _LLM_POOL.submit(_call).result(timeout=45)
            text = (reply if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '')).strip()
            obs = []
            for ln in text.split('\n'):
                ln = ln.strip()
                if ln.upper().startswith('TAKE:'):
                    take = ln[5:].strip()
                elif ln.startswith('-'):
                    obs.append(ln.lstrip('-').strip())
            insights_col.update_one({'_id': cache_id}, {'$set': {
                '_id': cache_id, 'kind': 'brief', 'text': text, 'observations': obs, 'take': take,
                'as_of': as_of, 'mode': 'plain', 'symbol': symbol, 'coin': coin_name,
                'generated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    return take, coin_name


def _get_brief_watchlist():
    """Coins that get daily briefs + bell notifications. User-configurable, with a
    sensible default; BTC is always included."""
    try:
        doc = insights_col.find_one({'_id': 'cfg:brief_watchlist'}, {'_id': 0})
        coins = (doc or {}).get('coins')
        if coins:
            out = [c for c in coins if c == 'BTC' or c in COMPARE_COINS]
            if 'BTC' not in out:
                out = ['BTC'] + out
            return out
    except Exception:  # noqa
        pass
    return BRIEF_COINS


def _daily_brief_autopost():
    """Scheduler (daily): ensure each watched coin's brief exists, then push it to the bell."""
    today = datetime.date.today().isoformat()
    for symbol in _get_brief_watchlist():
        try:
            if symbol != 'BTC' and symbol not in COMPARE_COINS:
                continue
            take, coin_name = _generate_daily_brief(symbol)
            title = "Albert's Morning Brief is ready" if symbol == 'BTC' else f"Albert's {coin_name} Brief is ready"
            push_alert('daily_brief', 'info', title,
                       take or f"Your plain-English {coin_name} brief for today is ready — open the dashboard to read it.",
                       f"brief-{symbol}-{today}", symbol=symbol)
        except Exception:  # noqa
            traceback.print_exc()


# =====================================================================
# ALBERT SECTION INSIGHTS  (AI-generated, cached per compute-run)
# =====================================================================
ALBERT_INSIGHT_SYSTEM = (
    "You are 'Albert', the friendly HuCentAI Quant analyst in the Ask Albert Bitcoin dashboard. You are explaining "
    "this section to a curious NON-TRADER who does not know market jargon. Your goal is to be genuinely "
    "INSIGHTFUL — do NOT simply restate the numbers already on screen. Instead:\n"
    "1) Explain in plain English WHAT is actually driving Bitcoin right now / WHY it is where it is (lean on "
    "the news drivers, factors, macro and regime).\n"
    "2) Explain what that could mean going forward.\n"
    "3) Give ONE or TWO concrete 'if this happens, then this is the likely outcome' scenarios using the real "
    "price levels, invalidation points and odds in the data (e.g. 'if BTC holds $X, the model's Y% up case "
    "strengthens; if it loses $X, expect ...').\n"
    "Rules: use ONLY the live dashboard data below — never invent numbers, prices or events. If any data "
    "source is unavailable or marked 'no data'/'inactive', explicitly say 'no [X] data available' (e.g. 'no "
    "ETF data available') and do NOT estimate or infer values for it. Any term a "
    "beginner might not know, explain in 3-4 words. Always frame the future as probabilities/odds, never "
    "certainties, and never give direct buy/sell financial advice. Warm, clear, professor-like. "
    "Do NOT open with a greeting or salutation (no 'Hello', 'Hi', 'Hey', 'Hello there', and do not address "
    "the reader) — start immediately with the substance. "
    "CRITICAL: Your entire answer must be specifically ABOUT THIS SECTION'S FOCUS. If a 'SECTION-SPECIFIC "
    "DATA' block is present below, that is your PRIMARY subject — lead with its concrete specifics (the actual "
    "counts, values, names and signals) and interpret THEM; use the rest of the dashboard data only as "
    "supporting context. Do NOT default to a generic market/regime overview unless this section IS the overview.\n"
    "Write 80-130 words, at most two short paragraphs. Do not use markdown headers or bullet symbols.\n\n"
    "THIS SECTION'S FOCUS: {focus}\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)

ALBERT_SECTION_SYSTEM = (
    "You are 'Albert', the friendly HuCentAI Quant analyst in the Ask Albert dashboard, explaining ONE specific panel "
    "to a curious NON-TRADER. You are NOT giving a general Bitcoin market update.\n"
    "Your entire answer MUST be about this panel and the 'SECTION-SPECIFIC DATA' block below. Lead with, and build "
    "the whole explanation around, that block's concrete specifics — the actual counts, values, names and signals. "
    "Interpret what they mean and why they matter for this panel.\n"
    "Do NOT give a generic market/regime narrative and do NOT append price-level 'if BTC holds $X then...' scenarios "
    "unless this panel is specifically about price levels.\n"
    "Panel-specific guidance:\n"
    "- Alerts: say how many alerts there are and how many are unread, group them by category and severity, summarise "
    "the most important one or two and their likely impact, and what the user should watch.\n"
    "- Prediction Ledger / Performance: interpret accuracy vs a 50% coin-flip, what the Brier score and range-hit "
    "rate imply about trustworthiness, and where the model is strongest/weakest (by horizon or regime).\n"
    "- Smart Money / Institutional / Whales: read whether the on-chain / positioning / wallet data leans "
    "accumulation or distribution and why.\n"
    "- Risk: explain the overall risk level, the biggest driver, and the expected move ranges.\n"
    "- Events: which upcoming events matter most, when, and how to think about the risk.\n"
    "Rules: use ONLY the data below — never invent numbers, prices or events; if the data says a metric is "
    "inactive/placeholder or unavailable, explicitly say 'no [X] data available' (e.g. 'no liquidation data "
    "available') rather than interpreting or estimating it. Explain any jargon in 3-4 words. Frame things as "
    "probabilities, never certainties; no buy/sell advice. No greeting — start immediately with the substance. "
    "Write 80-130 words, at most two short paragraphs, no markdown headers or bullet symbols.\n\n"
    "THIS PANEL'S FOCUS: {focus}\n\n"
    "===== LIVE DASHBOARD DATA (supporting context) =====\n{ctx}\n===== END DATA ====="
)

ALBERT_DATA_SECTIONS = {'alerts', 'scorecard', 'performance', 'whales', 'smartmoney',
                        'institutional', 'events', 'risk'}

ALBERT_TECH_SYSTEM = (
    "You are 'Albert', the HuCentAI Quant analyst in the Ask Albert Bitcoin dashboard, now giving a MORE TECHNICAL "
    "briefing for a reader who understands markets. Be precise and quantitative:\n"
    "1) Reference the concrete numbers — scores, probabilities, confidence, backtest hit-rates, key price levels, "
    "invalidation points, regime/volatility read, and any relevant macro/liquidity or on-chain style signals.\n"
    "2) Explain the mechanism / what is driving the read, and how the signal groups reconcile (agreement vs conflict).\n"
    "3) State the actionable levels and the specific 'if BTC does X vs level Y, then Z' conditions the model watches.\n"
    "Rules: use ONLY the live dashboard data below — never invent numbers, prices or events. If any data "
    "source is unavailable or marked 'no data'/'inactive', explicitly say 'no [X] data available' and do NOT "
    "estimate or infer values for it. You may use standard "
    "trading terms without dumbing them down, but stay rigorous. Always frame outcomes as probabilities, never "
    "certainties, and never give direct buy/sell financial advice. Do NOT open with a greeting or salutation "
    "(no 'Hello', 'Hi', 'Hey') — start immediately with the analysis. Write 90-150 words, tight and information-dense, "
    "no markdown headers or bullet symbols.\n"
    "CRITICAL: Keep the whole briefing specifically ABOUT THIS SECTION'S FOCUS. If a 'SECTION-SPECIFIC DATA' "
    "block is present below, make it the primary subject — cite its concrete numbers/names/signals directly — "
    "and treat the rest as supporting context, not the headline.\n\n"
    "THIS SECTION'S FOCUS: {focus}\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)


SECTION_FOCUS = {
    'overview': "The big-picture read on Bitcoin: what is pushing the price now and what it likely means over the next day to week.",
    'forecasts': "The short and medium-term forecasts: what the odds imply, and what price action would confirm or break each call.",
    'analysis': "The Quant Score breakdown: which forces (trend, momentum, macro, etc.) are pushing Bitcoin and what their balance means.",
    'performance': "The model's real track record: how much a beginner should trust the current calls, and why.",
    'scorecard': "The Prediction Ledger scorecard: read the concrete accuracy/Brier/error/range numbers, say how trustworthy the model is right now and where it's strongest or weakest (by horizon and regime).",
    'chart': "The chart structure and key support/resistance levels: what a break above or below them would likely lead to.",
    'cycle': "The 4-year halving cycle and BTC dominance: what this stage has historically meant for the months ahead.",
    'policy': "Macro and liquidity: how interest rates, the US dollar and global liquidity are pushing or pulling Bitcoin.",
    'news': "The day's Bitcoin news: which stories actually matter for price and why.",
    'risk': "The current risk level: how big the swings could be and what could trigger a sharp move either way.",
    'crossmarket': "How this coin is performing versus traditional markets (S&P 500, Nasdaq, Nikkei, European indices, Gold, the US Dollar): whether crypto is currently moving WITH stocks (risk-on coupling) or breaking away (decoupling), how its returns and volatility stack up, and what that correlation means for a non-trader.",
    'analogs': "Historical analogs: which past Bitcoin trend episode today's market conditions most resemble (macro rates, US dollar, equity/gold correlation, volatility, drawdown, momentum and halving-cycle position), what drove that past episode, and what would confirm or break a repeat. Educational pattern-matching on a small sample — never a guarantee.",
    'smartmoney': "The on-chain 'smart money' read: what valuation (MVRV, SOPR), holder accumulation, network activity and sentiment are saying about whether long-term/large holders are accumulating or distributing, and what that implies next.",
    'institutional': "The institutional & derivatives footprint: futures open interest, funding, long/short positioning and taker flow — whether leverage and positioning are crowded or supportive, and what that means for the next move.",
    'events': "The upcoming event calendar: which scheduled macro, derivatives and on-chain events are most likely to move the price, when, and how a trader should think about the risk around them.",
    'timemachine': "How to read the Time Machine: what replaying a past day teaches about the model's behaviour and how today's setup compares to history. Keep it educational.",
    'alerts': "The recent alerts feed: summarise what just changed (regime, decision, data-trust, event risk, whale moves) and what a user should pay attention to right now.",
    'whales': "The largest labeled Bitcoin wallets: who is accumulating or distributing among major exchanges, ETF/treasury custody, governments and whales, and what net flows (especially to/from exchanges) imply for supply and price.",
}


def _latest_run_version():
    run = runs_col.find_one(sort=[('created_at', -1)], projection={'created_at': 1, 'as_of': 1})
    if not run:
        return None
    return str(run.get('created_at') or run.get('as_of') or '')


@app.get('/api/v1/albert/insight')
async def albert_insight(request: Request, section: str = 'overview', mode: str = 'plain', refresh: int = 0, symbol: str = 'BTC'):
    section = (section or 'overview').strip().lower()[:40]
    mode = 'technical' if str(mode).lower().startswith('tech') else 'plain'
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol != 'BTC':
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cd = coin_dash_col.find_one({'_id': f'{symbol}:{today}'}, {'created_at': 1})
        version = str((cd or {}).get('created_at') or today) if cd else None
    else:
        version = _latest_run_version()
    if not version:
        return {'status': 'fallback', 'reason': 'no_data'}
    cache_id = f"{symbol}:{section}:{mode}:{version}"
    if not refresh:
        cached = insights_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('text'):
            return {'status': 'ready', 'section': section, 'mode': mode, 'text': cached['text'], 'model': cached.get('model'), 'generated_at': cached.get('created_at'), 'cached': True}
    if not (LLM_READY_KEY and _HAS_LLM):
        return {'status': 'fallback', 'reason': 'llm_unconfigured'}
    # About to call the LLM (cache miss / refresh) — guard against cost abuse.
    if _rate_limited(request, 'albert_insight', per_min=20, per_day=400):
        return {'status': 'fallback', 'reason': 'rate_limited'}
    try:
        ctx = build_chat_context(symbol)
        focus = SECTION_FOCUS.get(section, "Explain what this section means for the asset's price and outlook in plain English.")
        if section == 'crossmarket':
            today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
            mk = None
            for w in ('1y', '6m', '3m', '1m', 'ytd'):
                doc = markets_col.find_one({'_id': f'{symbol}:{w}:{today}'}, {'_id': 0})
                if doc and doc.get('data'):
                    mk = doc['data']
                    break
            if mk:
                tbl = mk.get('table', [])
                coin_row = next((t for t in tbl if t.get('is_coin')), None)
                lines = [f"CROSS-MARKET DATA (as of {mk.get('as_of')}): {mk.get('coin_name')} vs traditional markets."]
                if coin_row:
                    lines.append(f"{mk.get('coin_name')} returns: 1M {coin_row.get('ret_1m')}%, 3M {coin_row.get('ret_3m')}%, 1Y {coin_row.get('ret_1y')}%, YTD {coin_row.get('ret_ytd')}%; annualized volatility {coin_row.get('vol_annual')}%.")
                for t in tbl:
                    if not t.get('is_coin'):
                        lines.append(f"{t['asset']}: 1M {t.get('ret_1m')}%, 1Y {t.get('ret_1y')}%, vol {t.get('vol_annual')}%.")
                for c in mk.get('correlations', []):
                    lines.append(f"Correlation {mk.get('coin_name')}–{c['asset']}: 30d {c.get('corr_30d')}, 90d {c.get('corr_90d')} ({c.get('label')}), beta {c.get('beta_30d')}.")
                if mk.get('best') and mk.get('worst'):
                    lines.append(f"Over the {mk.get('window')} window the best performer is {mk['best']['asset']} and the worst is {mk['worst']['asset']}; {mk.get('coin_name')} ranks #{mk.get('coin_rank')} of {mk.get('ranked_count')}.")
                ctx = ctx + "\n\n" + "\n".join(lines)
        if section == 'analogs':
            today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
            adoc = analogs_col.find_one({'_id': f'{today}_{symbol}'}, {'_id': 0})
            data = (adoc or {}).get('data')
            if data:
                cur = data.get('current', {})
                lines = [f"HISTORICAL-ANALOG DATA (as of {data.get('as_of')}). Today's {symbol} condition fingerprint:"]
                sigmap = {s['key']: s['label'] for s in data.get('signals', [])}
                for k, v in cur.items():
                    lines.append(f"- {sigmap.get(k, k)}: {v}")
                top = (data.get('episodes') or [])[:3]
                for ep in top:
                    lines.append(f"Analog: {ep['label']} ({ep['start']}→{ep['end']}) match {ep['match']}% — then moved fwd 30d {ep['fwd_30']}%, 90d {ep['fwd_90']}%, 180d {ep['fwd_180']}%. Drivers: {', '.join(t['label'] for t in ep.get('tags', [])) or 'price-driven'}.")
                ctx = ctx + "\n\n" + "\n".join(lines)
        if section in ('smartmoney', 'institutional', 'events', 'alerts', 'whales', 'scorecard', 'performance', 'risk'):
            if symbol != 'BTC':
                today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
                _cd = coin_dash_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
                _run = (_cd or {}).get('data') or {}
            else:
                _run = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0}) or {}
            lines = []
            if section == 'smartmoney':
                sm = _run.get('smart_money') or {}
                if sm and not sm.get('demo'):
                    lines.append(f"ON-CHAIN SMART MONEY (source {sm.get('source')}): {sm.get('headline')}.")
                    for m in sm.get('metrics', []):
                        lines.append(f"- {m['name']}: {m['value']} ({m['signal']}).")
                else:
                    lines.append("The Smart Money panel is currently inactive/placeholder — say so plainly and do not invent on-chain figures.")
            elif section == 'institutional':
                inst = _run.get('institutional') or {}
                if inst:
                    lines.append(f"INSTITUTIONAL & DERIVATIVES (source {inst.get('source')}): {inst.get('headline')}.")
                    for m in inst.get('metrics', []):
                        tag = ' [INACTIVE - do not interpret]' if m.get('inactive') else ''
                        lines.append(f"- {m['name']}: {m['value']} ({m['signal']}){tag}.")
                else:
                    lines.append("No live derivatives data is available right now — say so plainly.")
            elif section == 'events':
                ec = _run.get('event_calendar') or {}
                evs = ec.get('events') if isinstance(ec, dict) else (ec if isinstance(ec, list) else [])
                nh = ec.get('next_high_impact') if isinstance(ec, dict) else None
                if nh:
                    lines.append(f"Next high-impact event: {nh.get('title')} in {nh.get('days_until')} day(s).")
                for e in (evs or [])[:8]:
                    lines.append(f"- In {e.get('days_until')}d: {e.get('title')} [{e.get('category')}, importance {e.get('importance')}] — {e.get('description')}")
                if not evs:
                    lines.append("No scheduled events are in the current window.")
            elif section == 'alerts':
                al = list(smart_alerts_col.find(_alert_symbol_filter(symbol), {'_id': 0}).sort('ts', -1).limit(10))
                unseen = smart_alerts_col.count_documents({**_alert_symbol_filter(symbol), 'seen': False})
                from collections import Counter as _Counter
                cats = _Counter(a.get('category') for a in al)
                sevs = _Counter(a.get('severity') for a in al)
                lines.append(f"ALERTS SUMMARY for {symbol}: {len(al)} recent alert(s), {unseen} unread. "
                             f"By category: {dict(cats)}. By severity: {dict(sevs)}.")
                if al:
                    lines.append("The alerts (newest first):")
                    for a in al:
                        lines.append(f"- [{a.get('category')}/{a.get('severity')}] {a.get('title')}: {(a.get('message') or '')[:180]}")
                for a in (_run.get('alerts') or [])[:5]:
                    lines.append(f"- (live) [{a.get('type')}/{a.get('level')}] {a.get('message')}")
                if not al and not (_run.get('alerts')):
                    lines.append("No alerts are currently active for this coin.")
            elif section == 'whales':
                try:
                    wd = get_whales()
                    lines.append(f"LARGEST LABELED BITCOIN WALLETS (source {wd.get('source')}):")
                    for w in (wd.get('whales') or [])[:8]:
                        lines.append(f"- {w['name']} ({w['category']}): {round(w['balance']):,} BTC, 7d change {w.get('change_7d')} BTC, signal {w['signal']}.")
                except Exception:  # noqa
                    pass
                try:
                    imp = compute_whale_impact()
                    lines.append(f"WHALE IMPACT (30d, on-chain reconstruction): net flow {imp.get('net_flow_30d')} BTC -> "
                                 f"trend {imp.get('trend')}. Held by holders {round(imp.get('holder_balance') or 0):,} BTC, "
                                 f"on exchanges {round(imp.get('exchange_balance') or 0):,} BTC. "
                                 f"(Exchange OUTFLOWS read bullish = supply leaving; holder accumulation reads bullish.)")
                    for c in (imp.get('contributors') or [])[:4]:
                        lines.append(f"- Mover: {c['name']} ({c['category']}) 30d {c['delta_30d']} BTC -> {c['signal']}.")
                except Exception:  # noqa
                    pass
                try:
                    es = etf_summary()
                    if es and es.get('net_1d') is not None:
                        lines.append(f"US SPOT ETF NET FLOWS (Farside data): {es['net_1d']:+.0f} $M last day, "
                                     f"{es.get('net_7d'):+.0f} $M last 7 days. Sustained ETF inflows are institutional demand "
                                     f"(bullish); outflows are the opposite. Tie the ETF picture together with the whale flows above.")
                except Exception:  # noqa
                    pass
            elif section in ('scorecard', 'performance'):
                pl = _run.get('prediction_ledger') or {}
                o = pl.get('overall') or {}
                if o:
                    lines.append(f"PREDICTION LEDGER TRACK RECORD ({pl.get('model_version', 'model')}): graded on {o.get('n')} matured forecasts. "
                                 f"Directional accuracy {o.get('accuracy')}% (50% = coin flip). "
                                 f"Brier score {o.get('brier')} (0 = perfect, 0.25 = a random 50/50 guess; lower is better). "
                                 f"Mean absolute price error {o.get('mae_pct')}%. Range hit rate {o.get('range_hit_pct')}% "
                                 f"(how often price finished inside the quoted range).")
                    lines.append(f"Logged forecasts: {pl.get('total_logged')} total ({pl.get('live_logged')} live, {pl.get('backtested')} backtested).")
                    bh = pl.get('by_horizon') or {}
                    for hz, s in (bh.items() if isinstance(bh, dict) else []):
                        if isinstance(s, dict):
                            lines.append(f"- {hz} horizon: accuracy {s.get('accuracy')}% over {s.get('n')} calls.")
                    br = pl.get('by_regime') or {}
                    for rg, s in (br.items() if isinstance(br, dict) else []):
                        if isinstance(s, dict):
                            lines.append(f"- In '{rg}' regimes: accuracy {s.get('accuracy')}% over {s.get('n')} calls.")
                else:
                    lines.append("No graded track record is available yet.")
            elif section == 'risk':
                rk = _run.get('risk') or {}
                if rk:
                    lines.append(f"RISK ENGINE: overall risk is {rk.get('level')} (score {rk.get('score')}/100). "
                                 f"Realised volatility {rk.get('realised_vol_annual')}% annualised ({rk.get('vol_percentile')} percentile). "
                                 f"Macro event risk: {rk.get('macro_event_risk')} — {rk.get('macro_note')}. "
                                 f"Data uncertainty: {rk.get('data_uncertainty')}.")
                    em = rk.get('expected_move') or {}
                    for hz, mv in (em.items() if isinstance(em, dict) else []):
                        if isinstance(mv, dict):
                            lines.append(f"- Expected {hz} move ±{mv.get('pct')}% (range ${mv.get('low')}–${mv.get('high')}).")
                    for dv in (rk.get('drivers') or []):
                        tag = ' [INACTIVE placeholder]' if dv.get('demo') else ''
                        lines.append(f"- Driver {dv.get('name')}: {dv.get('state')} ({dv.get('value')}){tag}.")
                else:
                    lines.append("No risk data is available right now.")
            if lines:
                ctx = ctx + f"\n\n===== SECTION-SPECIFIC DATA ({section}) — BASE YOUR ANSWER ON THIS =====\n" + "\n".join(lines) + "\n===== END SECTION DATA ====="
        if mode == 'technical':
            sys_tmpl = ALBERT_TECH_SYSTEM
        elif section in ALBERT_DATA_SECTIONS:
            sys_tmpl = ALBERT_SECTION_SYSTEM
        else:
            sys_tmpl = ALBERT_INSIGHT_SYSTEM
        kind = 'technical briefing' if mode == 'technical' else 'insight'
        umsg = f"Write Albert's {kind} for the '{section}' section now, following all the rules."

        def _complete(t):
            return len(t.split()) >= 50 and t.rstrip()[-1:] in '.!?"\u201d)'

        # emergentintegrations streaming can occasionally return a truncated partial response,
        # so retry a few times and keep the first complete-looking (or longest) answer.
        best = ''
        for _ in range(3):
            chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'insight-{section}-{mode}-{uuid.uuid4().hex[:10]}',
                            system_message=sys_tmpl.format(focus=focus, ctx=ctx))
                    .with_model('gemini', _model_for('insight'))
                    .with_params(temperature=0.4, max_tokens=8000))
            reply = await chat.send_message(UserMessage(text=umsg))
            text = (getattr(reply, 'text', None) or str(reply)).strip()
            text = re.sub(r'^\s*(hello|hi|hey|greetings|good (?:morning|afternoon|evening))\b[^.!?\n]*[.!?,]?\s+', '', text, flags=re.I).lstrip()
            if len(text) > len(best):
                best = text
            if _complete(text):
                best = text
                break
        text = best
        _bump_usage('llm_insight')
        if not text:
            return {'status': 'fallback', 'reason': 'empty'}
        # Only cache complete responses so an occasional partial regenerates on the next load.
        now_iso = datetime.datetime.utcnow().isoformat()
        if _complete(text):
            insights_col.update_one(
                {'_id': cache_id},
                {'$set': {'_id': cache_id, 'section': section, 'mode': mode, 'version': version, 'text': text,
                          'model': CHAT_MODEL, 'created_at': now_iso}},
                upsert=True)
        return {'status': 'ready', 'section': section, 'mode': mode, 'text': text, 'model': CHAT_MODEL, 'generated_at': now_iso, 'cached': False}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'status': 'fallback', 'reason': 'error'}


ALBERT_BRIEF_SYSTEM = (
    "You are 'Albert', the friendly market guide in the Ask Albert Bitcoin dashboard, writing a short PLAIN-ENGLISH "
    "MORNING BRIEF for a complete beginner — a 30-second read of what's going on with Bitcoin today. Use ONLY the "
    "data below. If a data source is unavailable or marked 'no data', simply skip it (do not mention it). "
    "AVOID JARGON completely: never use terms like MVRV, SOPR, funding, open interest, basis, liquidity, hashrate, "
    "EH/s, realised/annualised vol, positioning. If a concept matters, say it in everyday words (e.g. 'big holders "
    "are quietly buying', 'it's cheaper than usual to move Bitcoin', 'traders are betting aggressively, which can "
    "cause sharp swings'). Translate every number into what it MEANS for a normal person. Output EXACTLY this shape "
    "and nothing else:\n"
    "First, 4-5 lines each starting with '- ' — each a single plain-English takeaway (the overall lean, how "
    "risky/choppy it looks, whether big players are buying or selling, demand from big funds, how excited or fearful "
    "people are, and whether the network looks healthy/busy).\n"
    "Then one final line starting with 'TAKE: ' — the overall one-sentence bottom line in simple words.\n"
    "Warm, calm, everyday language (leans/looks/seems/could). Never say definitely/guaranteed/will happen. "
    "No greeting, no markdown headers, no jargon.\n\n"
    "===== LIVE MARKET DATA =====\n{ctx}\n===== END DATA ====="
)

ALBERT_BRIEF_TECH_SYSTEM = (
    "You are 'Albert', the HuCentAI Quant analyst in the Ask Albert Bitcoin dashboard, writing a MORE TECHNICAL "
    "MORNING BRIEF for a reader who understands markets. Use ONLY the data below; if a source is unavailable or "
    "marked 'no data', say 'no [X] data available' and do NOT invent values. Be precise and quantitative — cite "
    "the concrete numbers: decision/confidence, risk score & realised vol, whale & exchange net flows (BTC), ETF $ "
    "flows, leverage/positioning, sentiment, and network fees/hashrate. Output EXACTLY this shape and nothing "
    "else:\n"
    "First, 4-5 lines each starting with '- ' (a single crisp, data-dense observation).\n"
    "Then one final line starting with 'TAKE: ' giving the overall one-sentence read.\n"
    "Measured probability language (suggests/indicates/may/could/elevated). Never say definitely/guaranteed. "
    "No greeting, no markdown headers.\n\n"
    "===== LIVE DASHBOARD DATA =====\n{ctx}\n===== END DATA ====="
)


ALBERT_BRIEF_COIN_SYSTEM = (
    "You are 'Albert', the friendly market guide in the Ask Albert dashboard, writing a short PLAIN-ENGLISH "
    "MORNING BRIEF for a complete beginner — a 30-second read of what's going on with {coin} today. Use ONLY the "
    "data below. AVOID JARGON completely: translate every number into what it MEANS for a normal person. "
    "Output EXACTLY this shape and nothing else:\n"
    "First, 4-5 lines each starting with '- ' — each a single plain-English takeaway (the overall lean, how "
    "risky/choppy it looks, the near-term odds of going up or down, the key price levels to watch, and what stands "
    "out most).\n"
    "Then one final line starting with 'TAKE: ' — the overall one-sentence bottom line in simple words.\n"
    "Warm, calm, everyday language (leans/looks/seems/could). Never say definitely/guaranteed/will happen. "
    "No greeting, no markdown headers, no jargon.\n\n"
    "===== LIVE {coin} DATA =====\n{ctx}\n===== END DATA ====="
)

ALBERT_BRIEF_COIN_TECH_SYSTEM = (
    "You are 'Albert', the HuCentAI Quant analyst in the Ask Albert dashboard, writing a MORE TECHNICAL "
    "MORNING BRIEF on {coin} for a reader who understands markets. Use ONLY the data below; do NOT invent values. "
    "Be precise and quantitative — cite the concrete numbers: quant score, regime, 24H/7D forecast direction & "
    "confidence, nearest support/resistance, and the key tailwinds/risks. Output EXACTLY this shape and nothing "
    "else:\n"
    "First, 4-5 lines each starting with '- ' (a single crisp, data-dense observation).\n"
    "Then one final line starting with 'TAKE: ' giving the overall one-sentence read.\n"
    "Measured probability language (suggests/indicates/may/could/elevated). Never say definitely/guaranteed. "
    "No greeting, no markdown headers.\n\n"
    "===== LIVE {coin} DATA =====\n{ctx}\n===== END DATA ====="
)


def _coin_brief_context(symbol):
    """Build a coin-specific brief context, reusing the cached compare summary when
    available so we don't re-fetch OHLCV on every request."""
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    data = None
    try:
        cached = compare_col.find_one({'_id': f'{symbol}:{today}'}, {'_id': 0})
        if cached and cached.get('data'):
            data = cached['data']
    except Exception:  # noqa
        data = None
    if not data:
        data = compute_coin_summary(symbol)
        try:
            compare_col.update_one({'_id': f'{symbol}:{today}'},
                                   {'$set': {'_id': f'{symbol}:{today}', 'symbol': symbol, 'day': today,
                                             'data': data, 'created_at': datetime.datetime.utcnow().isoformat()}},
                                   upsert=True)
        except Exception:  # noqa
            pass
    L = []
    L.append(f"PRICE: ${data.get('price')} ({data.get('day_change_pct'):+}% today).")
    L.append(f"QUANT SCORE: {data.get('quant_score')}/100 ({data.get('quant_label')}).")
    if data.get('regime'):
        L.append(f"REGIME: {data.get('regime')}.")
    f24 = data.get('forecast_24h') or {}
    f7 = data.get('forecast_7d') or {}
    if f24.get('confidence_pct') is not None:
        L.append(f"24H FORECAST: {'higher' if f24.get('higher') else 'lower'} with {f24.get('confidence_pct')}% confidence.")
    if f7.get('confidence_pct') is not None:
        L.append(f"7D FORECAST: {'higher' if f7.get('higher') else 'lower'} with {f7.get('confidence_pct')}% confidence.")
    if data.get('support'):
        L.append(f"NEAREST SUPPORT: ${data.get('support')}.")
    if data.get('resistance'):
        L.append(f"NEAREST RESISTANCE: ${data.get('resistance')}.")
    if data.get('bullish'):
        L.append("TAILWINDS: " + "; ".join([str(x) for x in data.get('bullish')]))
    if data.get('risk'):
        L.append("RISKS: " + "; ".join([str(x) for x in data.get('risk')]))
    return "\n".join(L), data.get('name', symbol), data.get('as_of')


def _brief_context():
    run = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0}) or {}
    L = []
    dec = run.get('decision') or {}
    if dec:
        L.append(f"DECISION: {dec.get('label') or dec.get('stance')} (confidence {dec.get('confidence')}). {dec.get('summary') or ''}".strip())
    rk = run.get('risk') or {}
    if rk:
        L.append(f"RISK: {rk.get('level')} (score {rk.get('score')}/100), realised vol {rk.get('realised_vol_annual')}% ann.")
    try:
        imp = compute_whale_impact()
        L.append(f"WHALES: 30d net flow {imp.get('net_flow_30d')} BTC -> {imp.get('trend')} (holders {round(imp.get('holder_balance') or 0):,} BTC, exchanges {round(imp.get('exchange_balance') or 0):,} BTC).")
    except Exception:  # noqa
        pass
    try:
        xf = _misc_get('exchange_flows', 6 * 3600, compute_exchange_flows)
        if xf:
            L.append(f"EXCHANGE FLOW: {xf.get('trend')}; 30d {xf.get('net_30d')} BTC.")
    except Exception:  # noqa
        pass
    try:
        es = etf_summary()
        if es and es.get('net_1d') is not None:
            L.append(f"ETF FLOWS: {es['net_1d']:+.0f} $M last day, {es.get('net_7d'):+.0f} $M last 7d.")
        else:
            L.append("ETF FLOWS: no ETF data available.")
    except Exception:  # noqa
        pass
    try:
        lev = get_leverage('4H')
        if lev:
            s = lev.get('summary', {})
            L.append(f"LEVERAGE: pressure {s.get('pressure')}, bias {s.get('bias')}, {s.get('squeeze')}; long {lev.get('positioning', {}).get('long_pct')}% / short {lev.get('positioning', {}).get('short_pct')}%.")
    except Exception:  # noqa
        pass
    try:
        fg = _misc_get('fear_greed', 30 * 60, compute_fear_greed)
        if fg:
            L.append(f"SENTIMENT: Fear & Greed {fg.get('value')} ({fg.get('label')}).")
    except Exception:  # noqa
        pass
    try:
        nh = _misc_get('network_health', 10 * 60, compute_network_health)
        if nh:
            L.append(f"NETWORK: fees {nh.get('fees', {}).get('state')} (~{nh.get('fees', {}).get('fastest')} sat/vB), mempool {nh.get('mempool', {}).get('congestion')}, hashrate ~{nh.get('hashrate_ehs')} EH/s.")
    except Exception:  # noqa
        pass
    return "\n".join(L), run.get('as_of')


@app.get('/api/v1/albert/brief-watchlist')
def get_brief_watchlist():
    """Coins the user has chosen for daily briefs + notifications."""
    return {'status': 'ready', 'coins': _get_brief_watchlist(),
            'available': [{'symbol': 'BTC', 'name': 'Bitcoin'}] + [{'symbol': k, 'name': v['name']} for k, v in COMPARE_COINS.items() if k != 'BTC']}


@app.post('/api/v1/albert/brief-watchlist')
def set_brief_watchlist(payload: dict = Body(...)):
    coins = payload.get('coins') or []
    clean = ['BTC'] + [c.strip().upper() for c in coins if c.strip().upper() != 'BTC' and c.strip().upper() in COMPARE_COINS]
    # dedupe, preserve order
    seen, out = set(), []
    for c in clean:
        if c not in seen:
            seen.add(c); out.append(c)
    insights_col.update_one({'_id': 'cfg:brief_watchlist'},
                            {'$set': {'_id': 'cfg:brief_watchlist', 'kind': 'config', 'coins': out,
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    return {'status': 'ready', 'coins': out}


# ============================================================================
# Albert Trading Strategies — AI-authored playbooks that Albert tracks and
# nudges you on. One ACTIVE strategy per coin; closed ones move to history.
# Advisory / paper-trade only (no live exchange orders).
# ============================================================================
strategies_col = db['strategies']

ALBERT_STRATEGY_SYSTEM = (
    "You are Albert, a sharp crypto quant. Design a concrete, trackable TRADING STRATEGY for the "
    "asset in focus using ONLY the live dashboard context provided. This is an advisory paper-trade "
    "plan — never assume leverage or real orders.\n\n"
    "Return STRICT minified JSON ONLY (no prose, no markdown, no code fences) with EXACTLY these keys:\n"
    "{"
    "\"title\": string (<=60 chars, punchy), "
    "\"bias\": one of \"bullish\",\"bearish\",\"neutral\", "
    "\"position\": one of \"long\",\"short\", "
    "\"thesis\": string (2-3 plain-English sentences on why), "
    "\"horizon_days\": integer (7-120), "
    "\"targets\": [ {\"price\": number, \"label\": string, \"pct_of_position\": integer 1-100} ]  (1-3 profit targets, anchored ABOVE entry for long / BELOW for short, pct summing to ~100), "
    "\"stop\": {\"price\": number} (a protective invalidation level below entry for long / above for short), "
    "\"rules\": [ {\"kind\": one of \"price\",\"time\",\"signal\", \"op\": for price one of \"above\"/\"below\" | for signal one of \"above\"/\"below\"/\"flips_to\", \"level\": number (price rules), \"by_days\": integer (time rules — days from now), \"metric\": one of \"conviction\",\"regime\" (signal rules), \"value\": number-or-string (signal rules), \"then\": one of \"take_profit\",\"add\",\"exit\",\"reassess\",\"note\", \"action_note\": string (what Albert will tell the user to do when this fires, first person, <=140 chars) } ]  (2-5 rules — MUST include at least one time rule and at least one signal rule)"
    "}\n"
    "Anchor every price to the CURRENT PRICE given. Keep levels realistic (within sensible % of current). "
    "Make action_note specific and human, e.g. 'Take half off here and trail the rest.'"
)


def _strat_coin_name(symbol):
    symbol = (symbol or 'BTC').upper()
    if symbol == 'BTC':
        return 'Bitcoin'
    return (COMPARE_COINS.get(symbol) or {}).get('name', symbol)


def _rule_default_note(kind, then, op=None, level=None):
    verb = {'take_profit': 'take profit', 'add': 'add to the position', 'exit': 'exit the trade',
            'reassess': 'reassess the setup', 'note': 'note this'}.get(then, then)
    if kind == 'time':
        return f"If the plan hasn't played out yet, {verb}."
    if kind == 'signal':
        return f"If the signal shifts, {verb}."
    return f"If price hits ${level:,.0f}, {verb}." if level else f"When triggered, {verb}."


def _normalize_strategy_draft(raw, symbol, spot):
    """Coerce an LLM (or fallback) draft into our stored schema. Not yet persisted."""
    symbol = (symbol or 'BTC').upper()
    position = (raw.get('position') or ('long' if (raw.get('bias') != 'bearish') else 'short')).lower()
    if position not in ('long', 'short'):
        position = 'long'
    try:
        horizon = int(raw.get('horizon_days') or 30)
    except Exception:
        horizon = 30
    horizon = max(3, min(180, horizon))
    targets = []
    for t in (raw.get('targets') or [])[:3]:
        try:
            price = float(t.get('price'))
        except Exception:
            continue
        try:
            pct = int(t.get('pct_of_position') or 0)
        except Exception:
            pct = 0
        targets.append({'price': round(price, 2), 'label': (t.get('label') or f'TP{len(targets)+1}')[:20],
                        'pct_of_position': max(1, min(100, pct or 50)), 'hit': False, 'hit_at': None})
    if targets:
        tot = sum(t['pct_of_position'] for t in targets)
        if tot and tot != 100:
            for t in targets:
                t['pct_of_position'] = max(1, round(t['pct_of_position'] / tot * 100))
    stop = None
    rawstop = raw.get('stop') or {}
    try:
        if rawstop.get('price') is not None:
            stop = {'price': round(float(rawstop.get('price')), 2), 'hit': False, 'hit_at': None}
    except Exception:
        stop = None
    rules = []
    for r in (raw.get('rules') or [])[:6]:
        kind = (r.get('kind') or '').lower()
        if kind not in ('price', 'time', 'signal'):
            continue
        then = (r.get('then') or 'note').lower()
        if then not in ('take_profit', 'add', 'exit', 'reassess', 'note'):
            then = 'note'
        rule = {'id': uuid.uuid4().hex[:8], 'kind': kind, 'then': then, 'status': 'pending', 'fired_at': None}
        if kind == 'price':
            try:
                rule['level'] = round(float(r.get('level')), 2)
            except Exception:
                continue
            opv = (r.get('op') or '').lower()
            rule['op'] = 'above' if opv == 'above' else ('below' if opv == 'below' else ('above' if position == 'long' else 'below'))
        elif kind == 'time':
            try:
                by_days = int(r.get('by_days') or horizon)
            except Exception:
                by_days = horizon
            rule['by_days'] = max(1, min(365, by_days))
        else:
            metric = (r.get('metric') or 'conviction').lower()
            rule['metric'] = metric if metric in ('conviction', 'regime') else 'conviction'
            rule['op'] = (r.get('op') or 'below').lower()
            rule['value'] = r.get('value')
        rule['action_note'] = (r.get('action_note') or _rule_default_note(kind, then, rule.get('op'), rule.get('level')))[:180]
        rules.append(rule)
    draft = {
        'symbol': symbol, 'coin_name': _strat_coin_name(symbol),
        'title': (raw.get('title') or f'{_strat_coin_name(symbol)} Playbook')[:70],
        'bias': (raw.get('bias') or 'neutral').lower(),
        'position': position,
        'thesis': (raw.get('thesis') or '')[:600],
        'horizon_days': horizon,
        'size_usd': 1000,
        'entry_hint': round(spot, 2) if spot else None,
        'targets': targets, 'stop': stop, 'rules': rules,
    }
    return draft


def _fallback_strategy_draft(symbol, spot, goal=''):
    """Rule-based strategy when the LLM is unavailable."""
    spot = spot or 0
    bull = 'bear' not in (goal or '').lower() and 'short' not in (goal or '').lower()
    pos = 'long' if bull else 'short'
    if pos == 'long':
        targets = [{'price': round(spot * 1.08, 2), 'label': 'TP1', 'pct_of_position': 50},
                   {'price': round(spot * 1.16, 2), 'label': 'TP2', 'pct_of_position': 50}]
        stop = {'price': round(spot * 0.92, 2)}
        add_level = round(spot * 1.03, 2)
    else:
        targets = [{'price': round(spot * 0.92, 2), 'label': 'TP1', 'pct_of_position': 50},
                   {'price': round(spot * 0.84, 2), 'label': 'TP2', 'pct_of_position': 50}]
        stop = {'price': round(spot * 1.08, 2)}
        add_level = round(spot * 0.97, 2)
    raw = {
        'title': f'{_strat_coin_name(symbol)} {"Momentum Long" if pos=="long" else "Fade Short"}',
        'bias': 'bullish' if pos == 'long' else 'bearish', 'position': pos,
        'thesis': f"A disciplined {pos} on {_strat_coin_name(symbol)} anchored at ${spot:,.0f}: scale out into strength and cut it if the thesis breaks.",
        'horizon_days': 30, 'targets': targets, 'stop': stop,
        'rules': [
            {'kind': 'price', 'op': 'above' if pos == 'long' else 'below', 'level': add_level, 'then': 'add',
             'action_note': f"Momentum confirmed — add a small tranche near ${add_level:,.0f}."},
            {'kind': 'time', 'by_days': 21, 'then': 'reassess',
             'action_note': "3 weeks in — if it's going nowhere, reassess and free up the capital."},
            {'kind': 'signal', 'metric': 'conviction', 'op': 'below', 'value': 35, 'then': 'exit',
             'action_note': "Conviction has collapsed — step aside and protect capital."},
        ],
    }
    return _normalize_strategy_draft(raw, symbol, spot)


def _build_strategy_draft(symbol, goal=''):
    symbol = (symbol or 'BTC').upper()
    spot = _spot_price(symbol)
    if not (LLM_READY_KEY and _HAS_LLM):
        return _fallback_strategy_draft(symbol, spot, goal)
    ctx = build_chat_context(symbol)
    coin = _strat_coin_name(symbol)
    umsg = (f"Asset in focus: {coin} ({symbol}). CURRENT PRICE: ${spot:,.2f}.\n"
            + (f"User's goal/constraints: {goal}\n" if goal else '')
            + f"\n=== LIVE DASHBOARD CONTEXT ===\n{ctx}\n\nDesign the strategy JSON now.")

    def _call():
        async def _go():
            chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'strategy-{uuid.uuid4().hex[:8]}',
                            system_message=ALBERT_STRATEGY_SYSTEM)
                    .with_model('gemini', _model_for('strategy')).with_params(temperature=0.5, max_tokens=3000))
            return await chat.send_message(UserMessage(text=umsg))
        return asyncio.run(_go())
    try:
        reply = _LLM_POOL.submit(_call).result(timeout=45)
        text = (reply if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '')).strip()
        s, e = text.find('{'), text.rfind('}')
        raw = json.loads(text[s:e + 1])
        draft = _normalize_strategy_draft(raw, symbol, spot)
        if not draft.get('targets'):
            return _fallback_strategy_draft(symbol, spot, goal)
        return draft
    except Exception:  # noqa
        traceback.print_exc()
        return _fallback_strategy_draft(symbol, spot, goal)


def _strategy_perf(strat, spot=None):
    """Compute live paper-trade performance for a strategy."""
    if spot is None:
        spot = _spot_price(strat.get('symbol', 'BTC'))
    entry = strat.get('entry_price') or 0
    size = strat.get('size_usd') or 1000
    long = strat.get('position', 'long') == 'long'
    remaining_pct = strat.get('remaining_pct', 100)
    realized_usd = strat.get('realized_pnl_usd', 0.0)
    sign = 1 if long else -1
    cur = spot if strat.get('status') == 'active' else (strat.get('close_price') or spot)
    unreal_pct = ((cur - entry) / entry * 100 * sign) if (entry and cur) else 0.0
    unreal_usd = size * (remaining_pct / 100.0) * (unreal_pct / 100.0)
    total_usd = realized_usd + unreal_usd
    total_pct = (total_usd / size * 100.0) if size else 0.0
    try:
        created = datetime.datetime.fromisoformat(strat.get('created_at').replace('Z', ''))
        end = datetime.datetime.utcnow() if strat.get('status') == 'active' else datetime.datetime.fromisoformat((strat.get('closed_at') or strat.get('created_at')).replace('Z', ''))
        days_active = max(0, (end - created).days)
    except Exception:
        days_active = 0
    days_left = None
    try:
        if strat.get('expires_at'):
            days_left = max(0, (datetime.datetime.fromisoformat(strat['expires_at'].replace('Z', '')) - datetime.datetime.utcnow()).days)
    except Exception:
        days_left = None
    return {
        'current_price': round(cur, 2) if cur else None,
        'entry_price': round(entry, 2) if entry else None,
        'remaining_pct': remaining_pct,
        'unrealized_pnl_pct': round(unreal_pct, 2), 'unrealized_pnl_usd': round(unreal_usd, 2),
        'realized_pnl_usd': round(realized_usd, 2),
        'total_pnl_usd': round(total_usd, 2), 'total_pnl_pct': round(total_pct, 2),
        'days_active': days_active, 'days_left': days_left,
    }


def _strat_event(strat, etype, message, price=None):
    strat.setdefault('events', []).append({
        'ts': datetime.datetime.utcnow().isoformat(), 'type': etype, 'message': message,
        'price': round(price, 2) if price else None})


def _strat_signal_read(symbol):
    """Latest conviction score + regime label for signal rules."""
    conviction = None
    regime = None
    try:
        if (symbol or 'BTC').upper() == 'BTC':
            r = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
        else:
            today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
            cd = coin_dash_col.find_one({'_id': f'{symbol.upper()}:{today}'}, {'_id': 0}) or {}
            r = cd.get('data')
        if r:
            dec = r.get('decision') or {}
            conviction = dec.get('overall_score') if dec.get('overall_score') is not None else r.get('quant_score')
            regime = ((r.get('regime') or {}).get('regime'))
    except Exception:
        pass
    return conviction, regime


def _evaluate_strategy(strat, spot):
    """Mutate strat in place: fire targets/stop/rules, generate nudges. Returns list of
    (title, message, severity) alerts to push."""
    alerts = []
    if strat.get('status') != 'active' or not spot:
        return alerts
    long = strat.get('position', 'long') == 'long'
    sign = 1 if long else -1
    entry = strat.get('entry_price') or spot
    size = strat.get('size_usd') or 1000

    for t in strat.get('targets', []):
        if t.get('hit'):
            continue
        reach = (spot >= t['price']) if long else (spot <= t['price'])
        if reach:
            t['hit'] = True
            t['hit_at'] = datetime.datetime.utcnow().isoformat()
            leg_pct = t.get('pct_of_position', 50)
            leg_pnl_pct = (t['price'] - entry) / entry * 100 * sign
            strat['realized_pnl_usd'] = strat.get('realized_pnl_usd', 0.0) + size * (leg_pct / 100.0) * (leg_pnl_pct / 100.0)
            strat['remaining_pct'] = max(0, strat.get('remaining_pct', 100) - leg_pct)
            msg = f"{t.get('label','Target')} hit at ${t['price']:,.0f} — booked {leg_pct}% ({leg_pnl_pct:+.1f}%). Take it off."
            _strat_event(strat, 'target_hit', msg, spot)
            alerts.append((f"{strat['symbol']} {t.get('label','target')} hit", msg, 'high'))
            if strat['remaining_pct'] <= 0:
                _close_strategy(strat, 'targets_hit', spot)
                return alerts

    st = strat.get('stop')
    if st and not st.get('hit'):
        reach = (spot <= st['price']) if long else (spot >= st['price'])
        if reach:
            st['hit'] = True
            st['hit_at'] = datetime.datetime.utcnow().isoformat()
            msg = f"Stop hit at ${st['price']:,.0f}. Thesis invalidated — close it and protect capital."
            _strat_event(strat, 'stop_hit', msg, spot)
            alerts.append((f"{strat['symbol']} stopped out", msg, 'high'))
            _close_strategy(strat, 'stopped_out', spot)
            return alerts

    conviction, regime = (None, None)
    read_signal = False
    now = datetime.datetime.utcnow()
    for r in strat.get('rules', []):
        if r.get('status') != 'pending':
            continue
        fired = False
        if r['kind'] == 'price':
            fired = (spot >= r['level']) if r.get('op') == 'above' else (spot <= r['level'])
        elif r['kind'] == 'time':
            try:
                by = datetime.datetime.fromisoformat(r.get('by', '').replace('Z', '')) if r.get('by') else None
                fired = bool(by and now >= by)
            except Exception:
                fired = False
        elif r['kind'] == 'signal':
            if not read_signal:
                conviction, regime = _strat_signal_read(strat['symbol'])
                read_signal = True
            if r.get('metric') == 'conviction' and conviction is not None:
                try:
                    v = float(r.get('value'))
                    fired = (conviction >= v) if r.get('op') == 'above' else (conviction <= v)
                except Exception:
                    fired = False
            elif r.get('metric') == 'regime' and regime:
                fired = str(r.get('value', '')).lower() in str(regime).lower()
        if fired:
            r['status'] = 'fired'
            r['fired_at'] = now.isoformat()
            note = r.get('action_note') or 'Time to act on this rule.'
            _strat_event(strat, 'rule_fired', note, spot)
            alerts.append((f"{strat['symbol']} strategy nudge", note, 'medium'))
            if r['then'] == 'add':
                add_usd = size * 0.5
                new_size = size + add_usd
                strat['entry_price'] = round((entry * size + spot * add_usd) / new_size, 2)
                strat['size_usd'] = round(new_size, 2)
            elif r['then'] == 'exit':
                _close_strategy(strat, 'rule_exit', spot)
                return alerts

    try:
        if strat.get('expires_at'):
            exp = datetime.datetime.fromisoformat(strat['expires_at'].replace('Z', ''))
            if now >= exp:
                _strat_event(strat, 'expired', f"Horizon reached — closing at ${spot:,.0f}.", spot)
                alerts.append((f"{strat['symbol']} strategy expired", f"The {strat.get('horizon_days')}-day horizon is up — Albert closed the paper trade.", 'medium'))
                _close_strategy(strat, 'expired', spot)
    except Exception:
        pass
    return alerts


def _close_strategy(strat, reason, price):
    strat['status'] = 'closed'
    strat['closed_at'] = datetime.datetime.utcnow().isoformat()
    strat['close_price'] = round(price, 2) if price else None
    strat['close_reason'] = reason
    perf = _strategy_perf(strat, price)
    strat['final_pnl_usd'] = perf['total_pnl_usd']
    strat['final_pnl_pct'] = perf['total_pnl_pct']
    strat['outcome'] = 'win' if perf['total_pnl_usd'] >= 0 else 'loss'


def _persist_strategy(strat):
    strat['updated_at'] = datetime.datetime.utcnow().isoformat()
    strategies_col.update_one({'id': strat['id']}, {'$set': strat}, upsert=True)


def _strategy_eval_job():
    """Scheduler: evaluate every active strategy, fire nudges, persist."""
    try:
        active = list(strategies_col.find({'status': 'active', 'kind': {'$ne': 'basket'}}, {'_id': 0}))
    except Exception:  # noqa
        return
    price_cache = {}
    for strat in active:
        sym = strat.get('symbol', 'BTC')
        if sym not in price_cache:
            price_cache[sym] = _spot_price(sym)
        spot = price_cache[sym]
        if not spot:
            continue
        try:
            alerts = _evaluate_strategy(strat, spot)
            _persist_strategy(strat)
            for (title, message, sev) in alerts:
                push_alert('strategy', sev, title, message, f"{strat['id']}-{len(strat.get('events', []))}", strat.get('symbol', 'BTC'))
        except Exception:  # noqa
            traceback.print_exc()
    # --- Multi-coin baskets: nudge when a leg hits a target or its stop ---
    try:
        baskets = list(strategies_col.find({'status': 'active', 'kind': 'basket'}, {'_id': 0}))
    except Exception:  # noqa
        baskets = []
    now_iso = datetime.datetime.utcnow().isoformat()
    for bk in baskets:
        changed = False
        for leg in bk.get('legs', []):
            sym = leg.get('symbol')
            if not sym:
                continue
            if sym not in price_cache:
                price_cache[sym] = _spot_price(sym)
            cur = price_cache[sym]
            if not cur:
                continue
            long = leg.get('position', 'long') == 'long'
            side = 'long' if long else 'short'
            for t in (leg.get('targets') or []):
                if (not t.get('hit')) and ((long and cur >= t['price']) or ((not long) and cur <= t['price'])):
                    t['hit'] = True
                    t['hit_at'] = now_iso
                    changed = True
                    push_alert('strategy', 'info', f"{bk.get('title', 'Basket')}: {sym} hit {t.get('label', 'target')}",
                               f"Your {side} {sym} leg reached {t.get('label', 'its target')} at ${t['price']:,.2f} — consider trimming this leg.",
                               f"basket-{bk['id']}-{sym}-{t.get('label')}", sym)
            stop = leg.get('stop')
            if stop and (not stop.get('hit')) and ((long and cur <= stop['price']) or ((not long) and cur >= stop['price'])):
                stop['hit'] = True
                stop['hit_at'] = now_iso
                changed = True
                push_alert('strategy', 'warning', f"{bk.get('title', 'Basket')}: {sym} stop hit",
                           f"Your {side} {sym} leg hit its stop at ${stop['price']:,.2f} — time to cut this leg to protect the basket.",
                           f"basket-{bk['id']}-{sym}-stop", sym)
        if changed:
            try:
                strategies_col.update_one({'id': bk['id']}, {'$set': {'legs': bk['legs']}})
            except Exception:  # noqa
                traceback.print_exc()


@app.post('/api/v1/albert/strategy/build')
def albert_strategy_build(payload: dict = Body(default={})):
    """Albert drafts a structured strategy for a coin (optionally guided by a goal).
    Returns a DRAFT for the user to review — not yet saved."""
    symbol = (payload.get('symbol') or 'BTC').upper()
    goal = (payload.get('goal') or '').strip()[:400]
    try:
        draft = _build_strategy_draft(symbol, goal)
        return {'status': 'ready', 'draft': draft}
    except Exception:  # noqa
        traceback.print_exc()
        return JSONResponse({'status': 'error'}, status_code=500)


# =====================================================================
# MULTI-COIN (BASKET) STRATEGIES — Albert drafts a weighted multi-leg basket
# (long &/or short); the user saves & tracks it. Coexists with single-coin
# strategies (kind='basket' vs missing/'single'). Owner-scoped by pid.
# Performance is computed live on read (no changes to the single-coin eval job).
# =====================================================================
ALBERT_BASKET_SYSTEM = (
    "You are 'Albert', a crypto quant. Design a MULTI-COIN crypto STRATEGY as STRICT JSON ONLY "
    "(no prose, no markdown). YOU decide which coins and how many (usually 2-6 liquid coins). Legs "
    "may be LONG or SHORT (a strategy can be market-neutral / a pairs trade). Refer to it as a "
    "'strategy' (never a 'basket'). Schema:\n"
    "{\n"
    '  "title": "<=70 chars",\n'
    '  "thesis": "<=500 chars, plain English",\n'
    '  "horizon_days": <int 3-180>,\n'
    '  "legs": [\n'
    '    {"symbol":"BTC","position":"long|short","weight_pct":<int>,\n'
    '     "targets":[{"price":<num>,"label":"TP1","pct_of_position":<int>}],\n'
    '     "stop":{"price":<num>}}\n'
    "  ]\n"
    "}\n"
    "Rules: use REAL ticker symbols. weight_pct across legs should sum to ~100 (leave equal if unsure). "
    "Targets/stops are ABSOLUTE USD prices near the given current prices. For SHORT legs, targets are "
    "BELOW entry and the stop is ABOVE. Output ONLY the JSON object."
)

BASKET_UNIVERSE = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOGE', 'LINK', 'DOT', 'LTC', 'TRX']


def _normalize_basket_leg(raw):
    symbol = (raw.get('symbol') or '').upper().strip()
    if not symbol:
        return None
    spot = _spot_price(symbol)
    if not spot:
        return None
    position = (raw.get('position') or 'long').lower()
    if position not in ('long', 'short'):
        position = 'long'
    try:
        weight = max(0.0, float(raw.get('weight_pct') or 0))
    except Exception:
        weight = 0.0
    targets = []
    for t in (raw.get('targets') or [])[:3]:
        try:
            price = round(float(t.get('price')), 2)
        except Exception:
            continue
        try:
            pct = int(t.get('pct_of_position') or 50)
        except Exception:
            pct = 50
        targets.append({'price': price, 'label': (t.get('label') or f'TP{len(targets)+1}')[:20],
                        'pct_of_position': max(1, min(100, pct)), 'hit': False})
    stop = None
    try:
        if (raw.get('stop') or {}).get('price') is not None:
            stop = {'price': round(float(raw['stop']['price']), 2), 'hit': False}
    except Exception:
        stop = None
    return {'symbol': symbol, 'coin_name': _strat_coin_name(symbol), 'position': position,
            'weight_pct': weight, 'entry_price': round(spot, 2), 'targets': targets, 'stop': stop}


def _normalize_basket_draft(raw):
    legs, seen = [], set()
    for lr in (raw.get('legs') or [])[:8]:
        leg = _normalize_basket_leg(lr)
        if leg and leg['symbol'] not in seen:
            seen.add(leg['symbol'])
            legs.append(leg)
    tot = sum(l['weight_pct'] for l in legs)
    if legs:
        if tot <= 0:
            eq = round(100.0 / len(legs), 2)
            for l in legs:
                l['weight_pct'] = eq
        elif abs(tot - 100) > 0.5:
            for l in legs:
                l['weight_pct'] = round(l['weight_pct'] / tot * 100, 2)
    try:
        horizon = max(3, min(180, int(raw.get('horizon_days') or 30)))
    except Exception:
        horizon = 30
    return {'title': (raw.get('title') or 'Multi-Coin Strategy')[:70],
            'thesis': (raw.get('thesis') or '')[:500], 'horizon_days': horizon, 'legs': legs}


def _fallback_basket_draft(goal=''):
    raw = {'title': 'Majors Momentum Basket',
           'thesis': 'Equal-weight long on the large-cap majors with disciplined stops — ride broad market strength.',
           'horizon_days': 30, 'legs': []}
    for s in ['BTC', 'ETH', 'SOL']:
        spot = _spot_price(s) or 0
        raw['legs'].append({'symbol': s, 'position': 'long', 'weight_pct': round(100 / 3, 2),
                            'targets': [{'price': round(spot * 1.1, 2), 'label': 'TP1', 'pct_of_position': 100}],
                            'stop': {'price': round(spot * 0.9, 2)}})
    return _normalize_basket_draft(raw)


def _build_basket_draft(goal=''):
    if not (LLM_READY_KEY and _HAS_LLM):
        return _fallback_basket_draft(goal)
    ctx = build_chat_context('BTC')
    prices = [f"{s}=${_spot_price(s):,.2f}" for s in BASKET_UNIVERSE if _spot_price(s)]
    umsg = ((f"User's goal/constraints: {goal}\n" if goal else '')
            + "Live prices: " + ', '.join(prices) + "\n\n"
            + f"=== LIVE BTC DASHBOARD CONTEXT ===\n{ctx}\n\nDesign the BASKET JSON now.")

    def _call():
        async def _go():
            chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'basket-{uuid.uuid4().hex[:8]}',
                            system_message=ALBERT_BASKET_SYSTEM)
                    .with_model('gemini', _model_for('strategy')).with_params(temperature=0.5, max_tokens=3000))
            return await chat.send_message(UserMessage(text=umsg))
        return asyncio.run(_go())
    try:
        reply = _LLM_POOL.submit(_call).result(timeout=45)
        text = (reply if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '')).strip()
        s, e = text.find('{'), text.rfind('}')
        draft = _normalize_basket_draft(json.loads(text[s:e + 1]))
        return draft if draft.get('legs') else _fallback_basket_draft(goal)
    except Exception:  # noqa
        traceback.print_exc()
        return _fallback_basket_draft(goal)


_BASKET_BUILD_VERBS = ('build', 'make', 'create', 'draft', 'design', 'construct',
                       'set up', 'put together', 'give me', 'assemble', 'come up with')
_BASKET_STATUS_HINTS = ('how are my', "how's my", 'how is my', 'how are the', "how're my",
                        'doing', 'performance', 'performing', 'p&l', 'pnl', 'rebalance',
                        'compare', 'update on', 'status of')


_STRATEGY_NOUNS = ('strategy', 'strategies', 'basket', 'portfolio')


def _is_basket_build_request(msg):
    """Detect a 'build me a (multi-coin) crypto strategy' request in free-form chat.
    Status/query messages ('how are my strategies doing?') return False and fall through
    to normal chat (the user's strategies are already in the engine context)."""
    m = (msg or '').lower()
    if not any(n in m for n in _STRATEGY_NOUNS):
        return False
    if any(k in m for k in _BASKET_STATUS_HINTS):
        return False
    if any(v in m for v in _BASKET_BUILD_VERBS):
        return True
    # e.g. "a strategy long the majors, short a laggard" — directional multi-leg intent.
    return ('long' in m) and ('short' in m)


def _is_basket_rebalance_request(msg):
    """Detect 'rebalance my <name> strategy' in chat."""
    m = (msg or '').lower()
    return 'rebalance' in m or ('reweight' in m and any(n in m for n in _STRATEGY_NOUNS))


_BASKET_STOPWORDS = {'the', 'and', 'vs', 'with', 'for', 'basket', 'long', 'short',
                     'my', 'a', 'an', 'of', 'to', 'into', 'hedge', 'strategy', 'portfolio'}


def _find_basket_for_message(pid, msg):
    """Return (best_matching_active_basket, all_active_baskets) for a chat rebalance
    request. If exactly one basket exists, use it; otherwise match on title tokens /
    leg symbols/names mentioned in the message. Returns (None, list) if ambiguous."""
    q = {'status': 'active', 'kind': 'basket'}
    if pid:
        q['owner'] = str(pid)[:80]
    baskets = list(strategies_col.find(q, {'_id': 0}).sort('created_at', -1).limit(20))
    if not baskets:
        return None, []
    if len(baskets) == 1:
        return baskets[0], baskets
    m = (msg or '').lower()
    best, best_score = None, 0
    for b in baskets:
        score = 0
        for tok in set(re.findall(r'[a-z]{3,}', (b.get('title') or '').lower())):
            if tok in _BASKET_STOPWORDS:
                continue
            if tok in m:
                score += 2
        for leg in (b.get('legs') or []):
            sym = (leg.get('symbol') or '').lower()
            name = (leg.get('coin_name') or '').lower()
            if sym and re.search(r'\b' + re.escape(sym) + r'\b', m):
                score += 1
            if name and len(name) >= 3 and name in m:
                score += 1
        if score > best_score:
            best, best_score = b, score
    return (best if best_score > 0 else None), baskets


def _is_basket_close_request(msg):
    """Detect 'close/exit/delete my <name> strategy' in chat."""
    m = (msg or '').lower()
    if not any(n in m for n in _STRATEGY_NOUNS):
        return False
    return any(v in m for v in ('close', 'exit', 'delete', 'remove', 'stop tracking',
                                'get rid of', 'shut down', 'wind down', 'unwind'))



def _basket_perf(strat):
    legs_out, weighted_pct = [], 0.0
    size = strat.get('size_usd') or 1000
    active = strat.get('status') == 'active'
    for leg in (strat.get('legs') or []):
        entry = leg.get('entry_price') or 0
        long = leg.get('position', 'long') == 'long'
        sign = 1 if long else -1
        cur = _spot_price(leg.get('symbol')) if active else (leg.get('close_price') or leg.get('entry_price'))
        pnl_pct = ((cur - entry) / entry * 100 * sign) if (entry and cur) else 0.0
        w = leg.get('weight_pct', 0) or 0
        weighted_pct += (w / 100.0) * pnl_pct
        tgts = [{**t, 'hit': bool(cur and ((long and cur >= t['price']) or ((not long) and cur <= t['price'])))}
                for t in (leg.get('targets') or [])]
        stop = leg.get('stop')
        stop_hit = bool(stop and cur and ((long and cur <= stop['price']) or ((not long) and cur >= stop['price'])))
        legs_out.append({'symbol': leg.get('symbol'), 'coin_name': leg.get('coin_name'),
                         'position': leg.get('position'), 'weight_pct': w,
                         'entry_price': round(entry, 2) if entry else None,
                         'current_price': round(cur, 2) if cur else None,
                         'pnl_pct': round(pnl_pct, 2),
                         'pnl_usd': round(size * (w / 100.0) * (pnl_pct / 100.0), 2),
                         'targets': tgts, 'stop': ({**stop, 'hit': stop_hit} if stop else None)})
    try:
        created = datetime.datetime.fromisoformat((strat.get('created_at') or '').replace('Z', ''))
        end = datetime.datetime.utcnow() if active else datetime.datetime.fromisoformat((strat.get('closed_at') or strat.get('created_at')).replace('Z', ''))
        days_active = max(0, (end - created).days)
    except Exception:
        days_active = 0
    return {'total_pnl_pct': round(weighted_pct, 2), 'total_pnl_usd': round(size * (weighted_pct / 100.0), 2),
            'days_active': days_active, 'legs': legs_out}


def _basket_public(strat):
    # Live sector-rotation strip for this basket's legs (shows why a rebalance nudge fires).
    rotation = []
    try:
        strengths = _sector_strength() or {}
        seen = {}
        for leg in (strat.get('legs') or []):
            sec = _coin_sector(leg.get('symbol'))
            seen.setdefault(sec, []).append(leg.get('symbol'))
        for sec, syms in seen.items():
            st = strengths.get(sec)
            rotation.append({'sector': sec, 'strength': st, 'hot': (st or 0) > 0, 'symbols': syms})
        rotation.sort(key=lambda r: (r['strength'] if r['strength'] is not None else -999), reverse=True)
    except Exception:  # noqa
        rotation = []
    return {'id': strat.get('id'), 'kind': 'basket', 'title': strat.get('title'),
            'thesis': strat.get('thesis'), 'horizon_days': strat.get('horizon_days'),
            'status': strat.get('status'), 'created_at': strat.get('created_at'),
            'closed_at': strat.get('closed_at'), 'size_usd': strat.get('size_usd'),
            'rotation': rotation, 'perf': _basket_perf(strat)}


@app.post('/api/v1/albert/strategy/basket/build')
def albert_basket_build(payload: dict = Body(default={})):
    """Albert drafts a multi-coin basket (he picks the coins). Returns a DRAFT (not saved)."""
    goal = (payload.get('goal') or '').strip()[:400]
    try:
        return {'status': 'ready', 'draft': _build_basket_draft(goal)}
    except Exception:  # noqa
        traceback.print_exc()
        return JSONResponse({'status': 'error'}, status_code=500)


@app.post('/api/v1/albert/strategy/basket')
def albert_basket_activate(payload: dict = Body(...)):
    """Save/activate a multi-coin basket for the signed-in user."""
    draft = payload.get('draft') or payload
    pid = (str(payload.get('pid') or draft.get('pid') or '')).strip()[:80]
    norm = _normalize_basket_draft(draft)
    if not norm.get('legs'):
        return JSONResponse({'status': 'error', 'message': 'No valid legs (need live prices for the coins).'}, status_code=400)
    now = datetime.datetime.utcnow()
    strat = {'id': uuid.uuid4().hex, 'owner': pid, 'kind': 'basket',
             'title': norm['title'], 'thesis': norm['thesis'], 'horizon_days': norm['horizon_days'],
             'legs': norm['legs'], 'size_usd': 1000, 'status': 'active',
             'created_at': now.isoformat(),
             'expires_at': (now + datetime.timedelta(days=norm['horizon_days'])).isoformat(), 'closed_at': None}
    strategies_col.update_one({'id': strat['id']}, {'$set': strat}, upsert=True)
    return {'status': 'ready', 'basket': _basket_public(strat)}


@app.get('/api/v1/albert/strategy/baskets')
def albert_basket_list(pid: str = ''):
    """List the user's multi-coin baskets (active + closed) with live performance."""
    pid = (pid or '').strip()[:80]
    try:
        rows = list(strategies_col.find({'kind': 'basket', 'owner': pid}, {'_id': 0}).sort('created_at', -1).limit(40))
    except Exception:  # noqa
        rows = []
    baskets = [_basket_public(r) for r in rows]
    return {'status': 'ready',
            'active': [b for b in baskets if b['status'] == 'active'],
            'history': [b for b in baskets if b['status'] != 'active']}


@app.post('/api/v1/albert/strategy/basket/{bid}/close')
def albert_basket_close(bid: str, payload: dict = Body(default={})):
    strat = strategies_col.find_one({'id': bid, 'kind': 'basket'}, {'_id': 0})
    if not strat:
        return JSONResponse({'status': 'error', 'message': 'Basket not found.'}, status_code=404)
    now = datetime.datetime.utcnow()
    for leg in (strat.get('legs') or []):
        leg['close_price'] = _spot_price(leg.get('symbol')) or leg.get('entry_price')
    strategies_col.update_one({'id': bid}, {'$set': {'status': 'closed', 'closed_at': now.isoformat(), 'legs': strat['legs']}})
    strat['status'] = 'closed'
    strat['closed_at'] = now.isoformat()
    return {'status': 'ready', 'basket': _basket_public(strat)}


@app.post('/api/v1/albert/strategy/basket/{bid}/rebalance')
def albert_basket_rebalance(bid: str, payload: dict = Body(default={})):
    """Albert reviews an active basket vs the live market and suggests new weights
    (plain-English rationale). Does NOT apply — the user reviews then applies."""
    strat = strategies_col.find_one({'id': bid, 'kind': 'basket', 'status': 'active'}, {'_id': 0})
    if not strat:
        return JSONResponse({'status': 'error', 'message': 'Active basket not found.'}, status_code=404)
    legs = strat.get('legs') or []
    syms = [l['symbol'] for l in legs]
    perf = _basket_perf(strat)
    leg_perf = {l['symbol']: l for l in perf.get('legs', [])}

    def _equal():
        eq = round(100.0 / max(1, len(legs)), 2)
        return {'rationale': 'Reset to equal weight to reduce single-name concentration.',
                'weights': {s: eq for s in syms}}

    result = None
    if LLM_READY_KEY and _HAS_LLM:
        lines = [f"- {l['symbol']} {l['position']}: current weight {l['weight_pct']}%, P&L {leg_perf.get(l['symbol'], {}).get('pnl_pct', 0)}%" for l in legs]
        try:
            sectors = _sector_strength()
        except Exception:  # noqa
            sectors = {}
        umsg = ("Rebalance this multi-coin crypto strategy. Keep the SAME coins; only propose new weight_pct that sum to 100. "
                "Lean into relative strength / rotation and trim laggards or overweights.\n"
                f"Basket: {strat.get('title')}\nLegs:\n" + "\n".join(lines)
                + f"\nSector 7d strength vs BTC: {sectors}\n\n"
                "Return STRICT JSON only: {\"rationale\":\"<=280 chars plain English\",\"weights\":{\"SYM\":<int>}}")

        def _call():
            async def _go():
                chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'rebal-{uuid.uuid4().hex[:8]}',
                                system_message="You are Albert, a crypto quant. Output only the requested JSON.")
                        .with_model('gemini', _model_for('strategy')).with_params(temperature=0.4, max_tokens=1200))
                return await chat.send_message(UserMessage(text=umsg))
            return asyncio.run(_go())
        try:
            reply = _LLM_POOL.submit(_call).result(timeout=40)
            text = (reply if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '')).strip()
            s, e = text.find('{'), text.rfind('}')
            raw = json.loads(text[s:e + 1])
            w = {}
            for sym in syms:
                try:
                    w[sym] = max(0.0, float((raw.get('weights') or {}).get(sym, 0)))
                except Exception:  # noqa
                    w[sym] = 0.0
            tot = sum(w.values())
            if tot > 0:
                w = {k: round(v / tot * 100, 2) for k, v in w.items()}
                result = {'rationale': (raw.get('rationale') or 'Suggested reweighting based on current momentum.')[:280], 'weights': w}
        except Exception:  # noqa
            traceback.print_exc()
    if not result:
        result = _equal()
    suggestion = [{'symbol': l['symbol'], 'position': l['position'],
                   'current_weight': l['weight_pct'],
                   'suggested_weight': result['weights'].get(l['symbol'], l['weight_pct'])} for l in legs]
    return {'status': 'ready', 'rationale': result['rationale'], 'legs': suggestion}


@app.post('/api/v1/albert/strategy/basket/{bid}/reweight')
def albert_basket_reweight(bid: str, payload: dict = Body(...)):
    """Apply new weights to an active basket's legs (normalised to 100)."""
    strat = strategies_col.find_one({'id': bid, 'kind': 'basket', 'status': 'active'}, {'_id': 0})
    if not strat:
        return JSONResponse({'status': 'error', 'message': 'Active basket not found.'}, status_code=404)
    weights = payload.get('weights') or {}
    legs = strat.get('legs') or []
    for leg in legs:
        v = weights.get(leg['symbol'])
        if v is not None:
            try:
                leg['weight_pct'] = max(0.0, float(v))
            except Exception:  # noqa
                pass
    tot = sum(l['weight_pct'] for l in legs)
    if tot > 0 and abs(tot - 100) > 0.5:
        for leg in legs:
            leg['weight_pct'] = round(leg['weight_pct'] / tot * 100, 2)
    strategies_col.update_one({'id': bid}, {'$set': {'legs': legs}})
    strat['legs'] = legs
    return {'status': 'ready', 'basket': _basket_public(strat)}


@app.post('/api/v1/albert/strategy/basket/{bid}/rebalance-apply')
def albert_basket_rebalance_apply(bid: str, payload: dict = Body(default={})):
    """One-tap: compute Albert's rebalance suggestion for this basket AND apply it in a
    single call (used by the weekly rebalance-nudge alert's 'Apply Albert's rebalance')."""
    sug = albert_basket_rebalance(bid)
    if not (isinstance(sug, dict) and sug.get('status') == 'ready'):
        return sug  # propagate the 404/error JSONResponse
    weights = {l['symbol']: l['suggested_weight'] for l in (sug.get('legs') or [])}
    applied = albert_basket_reweight(bid, {'weights': weights})
    if isinstance(applied, dict) and applied.get('status') == 'ready':
        applied['rationale'] = sug.get('rationale')
        applied['applied_weights'] = weights
    return applied


def _iso_after(iso, cutoff):
    """True if an ISO timestamp is on/after `cutoff` (a naive UTC datetime)."""
    try:
        return datetime.datetime.fromisoformat(str(iso).replace('Z', '')) >= cutoff
    except Exception:  # noqa
        return False


def _basket_digest_data(pid, cutoff, hours):
    """Roll up every basket leg that hit a target or stop since `cutoff`, per basket.
    pid='' means all owners (used by the per-owner scheduler which passes a real pid)."""
    q = {'status': 'active', 'kind': 'basket'}
    if pid:
        q['owner'] = str(pid)[:80]
    try:
        baskets = list(strategies_col.find(q, {'_id': 0}).sort('created_at', -1).limit(40))
    except Exception:  # noqa
        baskets = []
    out_baskets, total = [], 0
    for bk in baskets:
        hits = []
        for leg in (bk.get('legs') or []):
            sym = leg.get('symbol')
            side = leg.get('position', 'long')
            for t in (leg.get('targets') or []):
                if t.get('hit') and t.get('hit_at') and _iso_after(t['hit_at'], cutoff):
                    hits.append({'symbol': sym, 'side': side, 'kind': 'target',
                                 'label': t.get('label', 'TP'), 'price': t.get('price'), 'at': t['hit_at']})
            stop = leg.get('stop')
            if stop and stop.get('hit') and stop.get('hit_at') and _iso_after(stop['hit_at'], cutoff):
                hits.append({'symbol': sym, 'side': side, 'kind': 'stop',
                             'label': 'stop', 'price': stop.get('price'), 'at': stop['hit_at']})
        if hits:
            hits.sort(key=lambda h: h['at'], reverse=True)
            total += len(hits)
            out_baskets.append({'id': bk.get('id'), 'title': bk.get('title'), 'hits': hits})
    return {'window_hours': hours, 'generated_at': datetime.datetime.utcnow().isoformat(),
            'total_hits': total, 'baskets': out_baskets}


@app.get('/api/v1/albert/basket-digest')
def albert_basket_digest(pid: str = '', hours: int = 24):
    """One consolidated summary of every basket leg that hit a target/stop in the window."""
    pid = (pid or '').strip()[:80]
    try:
        hours = max(1, min(168, int(hours or 24)))
    except Exception:  # noqa
        hours = 24
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    return {'status': 'ready', **_basket_digest_data(pid, cutoff, hours)}


def _basket_digest_job():
    """Daily: push ONE in-app digest per user summarising basket legs that hit a
    target/stop in the last 24h (fires at the local morning hour)."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    try:
        owners = [o for o in strategies_col.distinct('owner', {'status': 'active', 'kind': 'basket'}) if o]
    except Exception:  # noqa
        owners = []
    today = datetime.date.today().isoformat()
    for owner in owners:
        try:
            data = _basket_digest_data(owner, cutoff, 24)
            if data['total_hits'] <= 0:
                continue
            parts = []
            for b in data['baskets']:
                tp = sum(1 for h in b['hits'] if h['kind'] == 'target')
                sl = sum(1 for h in b['hits'] if h['kind'] == 'stop')
                bits = []
                if tp:
                    bits.append(f"{tp} target{'s' if tp != 1 else ''} hit")
                if sl:
                    bits.append(f"{sl} stop{'s' if sl != 1 else ''} hit")
                parts.append(f"{b['title']}: " + ', '.join(bits))
            n = data['total_hits']
            msg = ("In the last 24h — " + '; '.join(parts)
                   + ". Open Trading Strategies to review and trim/cut those legs.")
            sym0 = data['baskets'][0]['hits'][0]['symbol'] if (data['baskets'] and data['baskets'][0]['hits']) else 'BTC'
            push_alert('strategy', 'info',
                       f"Strategy digest — {n} leg event{'s' if n != 1 else ''} today",
                       msg, f"basket-digest-{owner}-{today}", sym0, owner=owner)
        except Exception:  # noqa
            traceback.print_exc()


def _basket_rebalance_nudge_job():
    """Weekly (Mon AM): nudge users to rebalance a basket ONLY when sector rotation has
    shifted materially since the last check. Stores a rotation snapshot per basket so the
    first run just primes the baseline (no nudge), and dedupes to ~once/6 days/basket."""
    try:
        baskets = list(strategies_col.find({'status': 'active', 'kind': 'basket'}, {'_id': 0}))
    except Exception:  # noqa
        return
    if not baskets:
        return
    try:
        strengths = _sector_strength() or {}
    except Exception:  # noqa
        strengths = {}
    hot_sorted = sorted([s for s, v in strengths.items() if (v or 0) > 0],
                        key=lambda s: strengths.get(s, 0), reverse=True)
    hot_set = set(hot_sorted[:3])
    now = datetime.datetime.utcnow()
    now_iso = now.isoformat()
    today = datetime.date.today().isoformat()
    for bk in baskets:
        try:
            first_time = 'rotation_hot' not in bk
            prev = set(bk.get('rotation_hot') or [])
            # Always refresh the stored snapshot.
            strategies_col.update_one({'id': bk['id']},
                                      {'$set': {'rotation_hot': list(hot_set), 'rotation_checked_at': now_iso}})
            if first_time:
                continue  # prime the baseline; don't nudge on first sighting
            if prev == hot_set:
                continue  # rotation hasn't shifted materially
            # Dedupe: at most one rebalance nudge per basket per ~6 days.
            last = bk.get('last_rebalance_nudge')
            if last:
                try:
                    if (now - datetime.datetime.fromisoformat(str(last).replace('Z', ''))).days < 6:
                        continue
                except Exception:  # noqa
                    pass
            came_in = ', '.join(sorted(hot_set - prev)) or '—'
            cooled = ', '.join(sorted(prev - hot_set)) or '—'
            hot_now = ', '.join(hot_sorted[:3]) or 'n/a'
            sym0 = (bk.get('legs') or [{}])[0].get('symbol', 'BTC')
            push_alert('strategy', 'info',
                       f"Rebalance check: {bk.get('title', 'Strategy')}",
                       (f"Sector rotation shifted this week (now leading: {hot_now}; rotating in: {came_in}; "
                        f"cooling: {cooled}). Open Trading Strategies → Rebalance to realign "
                        f"'{bk.get('title', 'your strategy')}'."),
                       f"basket-rebalnudge-{bk['id']}-{today}", sym0, owner=bk.get('owner'),
                       extra={'action': 'basket_rebalance', 'basket_id': bk['id'],
                              'basket_title': bk.get('title')})
            strategies_col.update_one({'id': bk['id']}, {'$set': {'last_rebalance_nudge': now_iso}})
        except Exception:  # noqa
            traceback.print_exc()






@app.post('/api/v1/albert/strategy')
def albert_strategy_activate(payload: dict = Body(...)):
    """Activate (save) a strategy for a coin. Closes any existing active strategy for
    that coin (one active per coin). Logs the paper entry at the current price."""
    draft = payload.get('draft') or payload
    pid = (str(payload.get('pid') or draft.get('pid') or '')).strip()[:80]
    symbol = (draft.get('symbol') or 'BTC').upper()
    spot = _spot_price(symbol)
    if not spot:
        return JSONResponse({'status': 'error', 'message': 'No live price available for this coin yet.'}, status_code=400)
    now = datetime.datetime.utcnow()
    try:
        prev = strategies_col.find_one({'symbol': symbol, 'status': 'active', 'owner': pid}, {'_id': 0})
        if prev:
            prev_spot = _spot_price(symbol) or spot
            _strat_event(prev, 'superseded', 'Replaced by a newer strategy.', prev_spot)
            _close_strategy(prev, 'superseded', prev_spot)
            _persist_strategy(prev)
    except Exception:  # noqa
        traceback.print_exc()
    norm = _normalize_strategy_draft(draft, symbol, spot)
    horizon = norm['horizon_days']
    for r in norm['rules']:
        if r['kind'] == 'time':
            r['by'] = (now + datetime.timedelta(days=r.get('by_days', horizon))).isoformat()
    strat = {
        'id': uuid.uuid4().hex,
        'owner': pid,
        **norm,
        'status': 'active',
        'entry_price': round(spot, 2),
        'position': norm['position'],
        'size_usd': norm.get('size_usd', 1000),
        'remaining_pct': 100,
        'realized_pnl_usd': 0.0,
        'created_at': now.isoformat(),
        'expires_at': (now + datetime.timedelta(days=horizon)).isoformat(),
        'events': [],
    }
    _strat_event(strat, 'opened', f"Opened {strat['position'].upper()} paper trade at ${spot:,.0f}. Albert is now tracking it.", spot)
    _persist_strategy(strat)
    push_alert('strategy', 'info', f"{symbol} strategy activated",
               f"Albert is now tracking '{strat['title']}' — you'll get a nudge when it's time to act.",
               f"{strat['id']}-open", symbol)
    out = {**strat}
    out['perf'] = _strategy_perf(strat, spot)
    return {'status': 'ready', 'strategy': out}


@app.get('/api/v1/albert/strategy')
def albert_strategy_active(symbol: str = 'BTC', pid: str = ''):
    """The current ACTIVE strategy for a coin (evaluated live), or status 'none'."""
    symbol = (symbol or 'BTC').upper()
    pid = (pid or '').strip()[:80]
    strat = strategies_col.find_one({'symbol': symbol, 'status': 'active', 'owner': pid}, {'_id': 0})
    if not strat:
        return {'status': 'none', 'symbol': symbol}
    spot = _spot_price(symbol)
    try:
        alerts = _evaluate_strategy(strat, spot)
        _persist_strategy(strat)
        for (title, message, sev) in alerts:
            push_alert('strategy', sev, title, message, f"{strat['id']}-{len(strat.get('events', []))}", symbol)
    except Exception:  # noqa
        traceback.print_exc()
    fresh = strategies_col.find_one({'id': strat['id']}, {'_id': 0}) or strat
    if fresh.get('status') != 'active':
        return {'status': 'none', 'symbol': symbol, 'just_closed': {**fresh, 'perf': _strategy_perf(fresh)}}
    fresh['perf'] = _strategy_perf(fresh, spot)
    return {'status': 'ready', 'strategy': fresh}


@app.get('/api/v1/albert/strategies')
def albert_strategies_list(symbol: str = 'BTC', pid: str = ''):
    """Active + past strategies for a coin (scoped to the signed-in user), each with performance."""
    symbol = (symbol or 'BTC').upper()
    pid = (pid or '').strip()[:80]
    try:
        rows = list(strategies_col.find({'symbol': symbol, 'owner': pid}, {'_id': 0}).sort('created_at', -1))
    except Exception:  # noqa
        rows = []
    active = None
    history = []
    for r in rows:
        r['perf'] = _strategy_perf(r)
        if r.get('status') == 'active' and active is None:
            active = r
        else:
            history.append(r)
    closed = [h for h in history if h.get('status') in ('closed', 'expired')]
    wins = sum(1 for c in closed if (c.get('final_pnl_usd', 0) or 0) >= 0)
    stats = {'total': len(closed), 'wins': wins, 'losses': len(closed) - wins,
             'win_rate': round(wins / len(closed) * 100) if closed else None,
             'avg_pnl_pct': round(sum((c.get('final_pnl_pct', 0) or 0) for c in closed) / len(closed), 2) if closed else None}
    return {'status': 'ready', 'symbol': symbol, 'active': active, 'history': history, 'stats': stats}


@app.get('/api/v1/albert/strategy/{sid}')
def albert_strategy_get(sid: str):
    strat = strategies_col.find_one({'id': sid}, {'_id': 0})
    if not strat:
        return JSONResponse({'status': 'none'}, status_code=404)
    strat['perf'] = _strategy_perf(strat)
    return {'status': 'ready', 'strategy': strat}


@app.post('/api/v1/albert/strategy/{sid}/close')
def albert_strategy_close(sid: str, payload: dict = Body(default={})):
    strat = strategies_col.find_one({'id': sid}, {'_id': 0})
    if not strat:
        return JSONResponse({'status': 'none'}, status_code=404)
    if strat.get('status') != 'active':
        strat['perf'] = _strategy_perf(strat)
        return {'status': 'ready', 'strategy': strat}
    spot = _spot_price(strat['symbol']) or strat.get('entry_price')
    reason = (payload.get('reason') or 'manual')[:40]
    _strat_event(strat, 'closed', f"You closed this strategy manually at ${spot:,.0f}.", spot)
    _close_strategy(strat, reason, spot)
    _persist_strategy(strat)
    strat['perf'] = _strategy_perf(strat, spot)
    return {'status': 'ready', 'strategy': strat}


# ============================================================================
# ALERT ENGINE — daily (1D) technical signal detectors + context filters.
# Signals: GMMA trend crossover, trend pullback/dip-buy, Bollinger squeeze,
# RSI exhaustion (+ a volume-spike confirmation filter). Context filters:
# funding rate, BTC exchange netflow, and Fear & Greed can suppress LONG signals.
# In-app delivery via push_alert. Signals are structured so they can later plug
# straight into the strategy engine as triggers.
# ============================================================================
import time as _time_mod

alert_engine_col = db['alert_engine']

GMMA_FAST = [3, 5, 8, 10, 12, 15]
GMMA_SLOW = [30, 35, 40, 45, 50, 60]

ALERT_COIN_PAIRS = {
    'BTC': [('kraken', 'BTC/USD'), ('coinbase', 'BTC/USD')],
    'ETH': [('kraken', 'ETH/USD'), ('coinbase', 'ETH/USD')],
    'SOL': [('kraken', 'SOL/USD'), ('coinbase', 'SOL/USD')],
    'XRP': [('kraken', 'XRP/USD'), ('coinbase', 'XRP/USD')],
    'ADA': [('kraken', 'ADA/USD'), ('coinbase', 'ADA/USD')],
    'DOGE': [('kraken', 'DOGE/USD'), ('coinbase', 'DOGE/USD')],
    'AVAX': [('kraken', 'AVAX/USD'), ('coinbase', 'AVAX/USD')],
    'LINK': [('kraken', 'LINK/USD'), ('coinbase', 'LINK/USD')],
    'DOT': [('kraken', 'DOT/USD'), ('coinbase', 'DOT/USD')],
    'LTC': [('kraken', 'LTC/USD'), ('coinbase', 'LTC/USD')],
    'MATIC': [('kraken', 'MATIC/USD'), ('coinbase', 'MATIC/USD')],
    'ATOM': [('kraken', 'ATOM/USD'), ('coinbase', 'ATOM/USD')],
    'BCH': [('kraken', 'BCH/USD'), ('coinbase', 'BCH/USD')],
    'XLM': [('kraken', 'XLM/USD'), ('coinbase', 'XLM/USD')],
    'ETC': [('kraken', 'ETC/USD'), ('coinbase', 'ETC/USD')],
    'UNI': [('kraken', 'UNI/USD'), ('coinbase', 'UNI/USD')],
    'AAVE': [('kraken', 'AAVE/USD'), ('coinbase', 'AAVE/USD')],
    'FIL': [('kraken', 'FIL/USD'), ('coinbase', 'FIL/USD')],
    'NEAR': [('kraken', 'NEAR/USD'), ('coinbase', 'NEAR/USD')],
    'APT': [('kraken', 'APT/USD'), ('coinbase', 'APT/USD')],
}
ALERT_COIN_NAMES = {
    'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'SOL': 'Solana', 'XRP': 'XRP', 'ADA': 'Cardano',
    'DOGE': 'Dogecoin', 'AVAX': 'Avalanche', 'LINK': 'Chainlink', 'DOT': 'Polkadot', 'LTC': 'Litecoin',
    'MATIC': 'Polygon', 'ATOM': 'Cosmos', 'BCH': 'Bitcoin Cash', 'XLM': 'Stellar', 'ETC': 'Ethereum Classic',
    'UNI': 'Uniswap', 'AAVE': 'Aave', 'FIL': 'Filecoin', 'NEAR': 'NEAR', 'APT': 'Aptos',
}
ALERT_COINS = list(ALERT_COIN_PAIRS.keys())

ALERT_ENGINE_DEFAULTS = {
    'enabled': True,
    'timeframe': '1D',
    'signals': {'gmma_crossover': True, 'dip_buy': True, 'squeeze': True, 'rsi_exhaustion': True},
    'filters': {'volume': True, 'funding': True, 'netflow': True, 'fng': True, 'btc_rs': True, 'sector': True, 'unlock': True},
    'volume_mult': 1.5,
    'rsi_low': 30, 'rsi_high': 80,
    'funding_threshold': 0.05,   # % per interval — above this, suppress longs
    'greed_threshold': 78, 'fear_threshold': 22,
    'squeeze_lookback': 30,
    'btc_rs_days': 7,            # [ALT]/BTC relative-strength lookback
    'corr_cap': 3,              # max simultaneous ALT long signals per day
    'expiry_candles': 2,        # alert perishability — valid for N daily closes
    'friction_bps': 10,        # round-trip fees+slippage used in backtest R:R
    'auto_prioritise': True,    # annotate/boost alerts by historical detector edge
    'suppress_negative_edge': False,  # block signals whose backtested edge is clearly negative
    'unlock_days': 14,         # suppress alt longs if a big unlock lands within N days
    'unlock_pct': 1.0,         # ... and it is >= this % of max supply
    'watchlist': ALERT_COINS[:],
}

_OHLCV_CACHE = {}   # sym -> (ts, df)
_OHLCV_TTL = 3 * 3600


def _get_alert_settings():
    try:
        doc = insights_col.find_one({'_id': 'cfg:alert_engine'}, {'_id': 0}) or {}
    except Exception:
        doc = {}
    st = json.loads(json.dumps(ALERT_ENGINE_DEFAULTS))
    for k, v in (doc.get('settings') or {}).items():
        if isinstance(v, dict) and isinstance(st.get(k), dict):
            st[k].update(v)
        else:
            st[k] = v
    # sanitise watchlist to known coins
    st['watchlist'] = [c for c in (st.get('watchlist') or ALERT_COINS) if c in ALERT_COIN_PAIRS] or ALERT_COINS[:]
    return st


def _save_alert_settings(patch):
    st = _get_alert_settings()
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(st.get(k), dict):
            st[k].update(v)
        else:
            st[k] = v
    st['watchlist'] = [c for c in (st.get('watchlist') or ALERT_COINS) if c in ALERT_COIN_PAIRS] or ALERT_COINS[:]
    insights_col.update_one({'_id': 'cfg:alert_engine'},
                            {'$set': {'_id': 'cfg:alert_engine', 'kind': 'config', 'settings': st,
                                      'updated_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
    return st


def _trim_forming(df):
    """Look-ahead prevention: drop the still-forming (today, UTC) daily candle so all
    signals/backtests use only CLOSED candles."""
    try:
        if len(df) and df['timestamp'].iloc[-1].date() >= datetime.datetime.utcnow().date():
            df = df.iloc[:-1].reset_index(drop=True)
    except Exception:  # noqa
        pass
    return df


def _daily_ohlcv(symbol, limit=720):
    sym = (symbol or 'BTC').upper()
    now = _time_mod.time()
    c = _OHLCV_CACHE.get(sym)
    if c and (now - c[0]) < _OHLCV_TTL:
        return c[1]
    if sym == 'BTC':
        try:
            df, _src = fetch_ohlcv()
            df = _trim_forming(df.tail(limit + 1).reset_index(drop=True))
            _OHLCV_CACHE[sym] = (now, df)
            return df
        except Exception:  # noqa
            pass
    for name, pair in ALERT_COIN_PAIRS.get(sym, []):
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            bars = ex.fetch_ohlcv(pair, timeframe='1d', limit=limit + 1)
            if bars and len(bars) > 80:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = _trim_forming(df.sort_values('timestamp').reset_index(drop=True))
                _OHLCV_CACHE[sym] = (now, df)
                return df
        except Exception:  # noqa
            continue
    return None


def _bollinger_width(close, n=20, k=2):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = mid + k * std
    lower = mid - k * std
    return ((upper - lower) / mid.replace(0, np.nan)) * 100.0  # width as % of mid


def compute_alert_signals(symbol, settings=None):
    """Compute daily technical readings + which signal detectors are active on the last close."""
    st = settings or _get_alert_settings()
    df = _daily_ohlcv(symbol)
    if df is None or len(df) < 70:
        return None
    close = df['close']
    fast_e = {s: _ema(close, s) for s in GMMA_FAST}
    slow_e = {s: _ema(close, s) for s in GMMA_SLOW}

    def gmma_state(i):
        fvals = [fast_e[s].iloc[i] for s in GMMA_FAST]
        svals = [slow_e[s].iloc[i] for s in GMMA_SLOW]
        if min(fvals) > max(svals):
            return 'bull'
        if max(fvals) < min(svals):
            return 'bear'
        return 'mixed'

    state = gmma_state(-1)
    prev = gmma_state(-2)
    crossover = None
    if state == 'bull' and prev != 'bull':
        crossover = 'bullish'
    elif state == 'bear' and prev != 'bear':
        crossover = 'bearish'

    price = float(close.iloc[-1])
    slow_top = max(slow_e[s].iloc[-1] for s in GMMA_SLOW)
    slow_bot = min(slow_e[s].iloc[-1] for s in GMMA_SLOW)
    slow_spread_pct = round((slow_top - slow_bot) / price * 100, 2) if price else 0
    expanded_bull = bool(state == 'bull' and slow_e[60].iloc[-1] > slow_e[60].iloc[-6])

    last = df.iloc[-1]
    green = bool(last['close'] > last['open'])
    touched = bool(last['low'] <= slow_top * 1.01)
    recovered = bool(last['close'] > slow_top)
    dip_buy = bool(expanded_bull and touched and green and recovered)

    bbw = _bollinger_width(close, 20, 2)
    cur_bbw = float(bbw.iloc[-1])
    lookback = int(st.get('squeeze_lookback', 30))
    recent = bbw.iloc[-lookback:]
    squeeze = bool(cur_bbw <= float(recent.min()) * 1.03)
    bbw_pct = round(float((recent < cur_bbw).mean()) * 100, 0)

    rsi = _rsi(close, 14)
    rsi_v = round(float(rsi.iloc[-1]), 1)
    rsi_low = st.get('rsi_low', 30)
    rsi_high = st.get('rsi_high', 80)
    rsi_oversold = bool(rsi_v < rsi_low)
    rsi_overbought = bool(rsi_v > rsi_high)

    vol = df['volume']
    vma = vol.rolling(20).mean()
    vol_ratio = None
    try:
        if vma.iloc[-1] and vma.iloc[-1] > 0:
            vol_ratio = round(float(vol.iloc[-1] / vma.iloc[-1]), 2)
    except Exception:
        vol_ratio = None

    candle_date = df['timestamp'].iloc[-1].strftime('%Y-%m-%d')
    return {
        'symbol': (symbol or 'BTC').upper(), 'price': round(price, 4), 'candle_date': candle_date,
        'gmma_state': state, 'gmma_prev': prev, 'crossover': crossover,
        'slow_ribbon_top': round(slow_top, 4), 'slow_ribbon_bot': round(slow_bot, 4),
        'slow_spread_pct': slow_spread_pct, 'expanded_bull': expanded_bull,
        'dip_buy': dip_buy, 'green_candle': green,
        'bb_width_pct': round(cur_bbw, 3), 'bb_width_percentile': bbw_pct, 'squeeze': squeeze,
        'rsi': rsi_v, 'rsi_oversold': rsi_oversold, 'rsi_overbought': rsi_overbought,
        'vol_ratio': vol_ratio,
    }


def _btc_rel_strength(symbol, days=7):
    """Change in the [ALT]/BTC ratio over `days` closed candles. >0 = outperforming BTC."""
    sym = (symbol or '').upper()
    if sym == 'BTC':
        return None
    try:
        a = _daily_ohlcv(sym)
        b = _daily_ohlcv('BTC')
        if a is None or b is None or len(a) <= days or len(b) <= days:
            return None
        ratio_now = float(a['close'].iloc[-1]) / float(b['close'].iloc[-1])
        ratio_then = float(a['close'].iloc[-1 - days]) / float(b['close'].iloc[-1 - days])
        if ratio_then <= 0:
            return None
        return round((ratio_now - ratio_then) / ratio_then * 100, 2)
    except Exception:  # noqa
        return None


def compute_alert_filters(symbol, settings=None):
    st = settings or _get_alert_settings()
    sym = (symbol or 'BTC').upper()
    out = {'funding': None, 'funding_suppress_long': False,
           'fng_value': None, 'fng_label': None, 'fng_suppress_long': False, 'fng_accumulate': False,
           'netflow_available': False, 'netflow_net7d': None, 'netflow_warning': False,
           'btc_rs': None, 'btc_rs_suppress_long': False}
    try:
        fr = _okx('/api/v5/public/funding-rate', {'instId': f'{sym}-USDT-SWAP'})
        if fr:
            rate = float(fr[0]['fundingRate']) * 100
            out['funding'] = round(rate, 4)
            out['funding_suppress_long'] = bool(rate > st.get('funding_threshold', 0.05))
    except Exception:  # noqa
        pass
    try:
        fg = compute_fear_greed()
        if fg:
            out['fng_value'] = fg['value']
            out['fng_label'] = fg['label']
            out['fng_suppress_long'] = bool(fg['value'] >= st.get('greed_threshold', 78))
            out['fng_accumulate'] = bool(fg['value'] <= st.get('fear_threshold', 22))
    except Exception:  # noqa
        pass
    if sym == 'BTC':
        try:
            ef = compute_exchange_flows()
            if ef:
                out['netflow_available'] = True
                out['netflow_net7d'] = ef.get('net_7d')
                out['netflow_warning'] = bool((ef.get('net_7d') or 0) > 200)
        except Exception:  # noqa
            pass
    else:
        rs = _btc_rel_strength(sym, st.get('btc_rs_days', 7))
        out['btc_rs'] = rs
        out['btc_rs_suppress_long'] = bool(rs is not None and rs <= 0)
    return out


def _long_suppression(filters, st):
    reasons = []
    f = st.get('filters', {})
    if f.get('funding') and filters.get('funding_suppress_long'):
        reasons.append(f"funding hot ({filters.get('funding')}%)")
    if f.get('fng') and filters.get('fng_suppress_long'):
        reasons.append(f"extreme greed ({filters.get('fng_value')})")
    if f.get('netflow') and filters.get('netflow_warning'):
        reasons.append(f"BTC exchange inflows (+{filters.get('netflow_net7d')} BTC/7d)")
    if f.get('btc_rs') and filters.get('btc_rs_suppress_long'):
        reasons.append(f"not outperforming BTC ({filters.get('btc_rs')}%/7d)")
    return reasons


def _scan_symbol(symbol, settings=None, fire=False, corr_state=None):
    """Compute signals + filters for a coin, decide which alerts fire, persist readings,
    and (optionally) push in-app alerts. Returns the readings/decision dict."""
    st = settings or _get_alert_settings()
    sym = (symbol or 'BTC').upper()
    sig = compute_alert_signals(sym, st)
    if not sig:
        return {'symbol': sym, 'error': 'no_data'}
    filt = compute_alert_filters(sym, st)
    sigs_on = st.get('signals', {})
    fcfg = st.get('filters', {})
    name = ALERT_COIN_NAMES.get(sym, sym)
    long_block = _long_suppression(filt, st)
    if st.get('filters', {}).get('sector') and sym != 'BTC':
        try:
            sstr = _sector_strength().get(_coin_sector(sym))
            if sstr is not None and sstr <= 0:
                long_block.append(f"sector cold ({_coin_sector(sym)} {sstr}%/7d)")
        except Exception:  # noqa
            pass
    if st.get('filters', {}).get('unlock') and sym != 'BTC':
        try:
            u = _token_unlock(sym, st.get('unlock_days', 14))
            if u and u.get('within') and (u.get('percent_of_supply') or 0) >= st.get('unlock_pct', 1.0):
                long_block.append(f"token unlock {u['percent_of_supply']:.1f}% of supply in {u.get('days_until')}d")
        except Exception:  # noqa
            pass
    fired = []      # alerts that WILL fire
    candidates = [] # everything detected (for UI), incl. suppressed w/ reason

    def add(key, direction, severity, title, message, blocked=None):
        item = {'key': key, 'direction': direction, 'severity': severity, 'title': title,
                'message': message, 'blocked': blocked or []}
        candidates.append(item)
        if not blocked:
            fired.append(item)

    # 1) GMMA crossover
    if sigs_on.get('gmma_crossover') and sig['crossover']:
        vol_ok = (not fcfg.get('volume')) or (sig.get('vol_ratio') is not None and sig['vol_ratio'] >= st.get('volume_mult', 1.5))
        if sig['crossover'] == 'bullish':
            blocked = list(long_block)
            if not vol_ok:
                blocked.append(f"volume unconfirmed ({sig.get('vol_ratio')}x < {st.get('volume_mult',1.5)}x)")
            boost = ' High-conviction: extreme fear.' if filt.get('fng_accumulate') else ''
            add('gmma_crossover', 'long', 'high', f"{sym} · GMMA bullish crossover (Daily)",
                f"{name}'s fast EMA ribbon (3–15) crossed fully ABOVE the slow ribbon (30–60) — a macro shift into expansion. Price ${sig['price']:,.4g}.{boost}", blocked)
        else:
            vol_block = [] if vol_ok else [f"volume unconfirmed ({sig.get('vol_ratio')}x < {st.get('volume_mult',1.5)}x)"]
            add('gmma_crossover', 'short', 'high', f"{sym} · GMMA bearish crossover (Daily)",
                f"{name}'s fast EMA ribbon (3–15) crossed fully BELOW the slow ribbon (30–60) — a macro shift into contraction. Price ${sig['price']:,.4g}.", vol_block)

    # 2) Dip-buy / pullback (long only)
    if sigs_on.get('dip_buy') and sig['dip_buy']:
        boost = ' High-conviction: extreme fear.' if filt.get('fng_accumulate') else ''
        add('dip_buy', 'long', 'medium', f"{sym} · Trend pullback dip-buy (Daily)",
            f"In an expanded bull ribbon, {name} pulled back to the slow investor ribbon (~${sig['slow_ribbon_top']:,.4g}) and printed a green recovery candle — a high-probability continuation entry.{boost}", list(long_block))

    # 3) Bollinger squeeze (neutral / volatility warning)
    if sigs_on.get('squeeze') and sig['squeeze']:
        add('squeeze', 'neutral', 'medium', f"{sym} · Volatility squeeze (Daily)",
            f"{name}'s Bollinger Bands have compressed to a ~{int(sig['bb_width_pct'] and sig['bb_width_percentile'])}th-percentile multi-week low (width {sig['bb_width_pct']}%). The market is coiling — watch for an impending expansion.")

    # 4) RSI exhaustion
    if sigs_on.get('rsi_exhaustion'):
        if sig['rsi_oversold']:
            boost = ' Extreme fear adds conviction.' if filt.get('fng_accumulate') else ''
            add('rsi_oversold', 'long', 'medium', f"{sym} · RSI oversold (Daily)",
                f"{name}'s 14-day RSI is {sig['rsi']} (< {st.get('rsi_low',30)}) — stretched to the downside; watch for a mean-reversion / capitulation bottom.{boost}", list(long_block))
        elif sig['rsi_overbought']:
            add('rsi_overbought', 'short', 'medium', f"{sym} · RSI overbought (Daily)",
                f"{name}'s 14-day RSI is {sig['rsi']} (> {st.get('rsi_high',80)}) — running too hot; a local top / cooldown is increasingly likely.")

    now = datetime.datetime.utcnow().isoformat()
    doc = alert_engine_col.find_one({'_id': sym}) or {}
    already = set(doc.get('fired_sigs', []))
    pushed = []
    expiry_n = int(st.get('expiry_candles', 2))
    cap = int(st.get('corr_cap', 3))
    edge = _detector_edge(sym) if st.get('auto_prioritise') else {}
    if fire:
        for it in fired:
            sigkey = f"{sym}-{it['key']}-{sig['candle_date']}-{it['direction']}"
            if sigkey in already:
                continue
            # Auto-prioritise by historical detector edge.
            edge_suffix = ''
            e = edge.get(it['key'])
            if e and e.get('avg_10') is not None:
                if st.get('suppress_negative_edge') and e['avg_10'] < 0 and (e.get('win_10') or 0) < 40:
                    continue
                edge_suffix = f" [hist edge: {e.get('win_10')}% win, {'+' if e['avg_10'] > 0 else ''}{e['avg_10']}%/10d]"
                if e['avg_10'] > 0 and (e.get('win_10') or 0) >= 55:
                    it['severity'] = 'high'
            # Correlation / concentration cap: throttle simultaneous ALT longs per day.
            if it['direction'] == 'long' and sym not in ('BTC', 'ETH') and corr_state is not None:
                cnt = corr_state.get(sig['candle_date'], 0)
                if cnt >= cap:
                    it['blocked'] = (it.get('blocked') or []) + [f"correlation cap ({cap} alt longs/day)"]
                    continue
                corr_state[sig['candle_date']] = cnt + 1
            msg = it['message']
            if it['direction'] in ('long', 'short'):
                msg = f"{msg} Setup valid for the next {expiry_n} daily closes."
            msg = f"{msg}{edge_suffix}"
            push_alert('signal', it['severity'], it['title'], msg, sigkey, sym)
            already.add(sigkey)
            pushed.append(sigkey)
    alert_engine_col.update_one({'_id': sym}, {'$set': {
        '_id': sym, 'symbol': sym, 'name': name, 'updated_at': now,
        'readings': sig, 'filters': filt, 'candidates': candidates,
        'fired_sigs': list(already)[-60:],
    }}, upsert=True)
    return {'symbol': sym, 'name': name, 'readings': sig, 'filters': filt,
            'candidates': candidates, 'fired': [f['key'] for f in fired], 'pushed': pushed,
            'long_block': long_block}


def _alert_engine_job():
    st = _get_alert_settings()
    if not st.get('enabled'):
        return
    corr_state = {}
    for sym in st.get('watchlist', []):
        try:
            _scan_symbol(sym, st, fire=True, corr_state=corr_state)
        except Exception:  # noqa
            traceback.print_exc()


def _backtest_detector(df, st):
    """Backtest every detector over ALL closed candles. For each trigger, grade the
    direction-adjusted forward return at +5 and +10 candles, net of friction."""
    close = df['close']; openp = df['open']; high = df['high']; low = df['low']
    n = len(df)
    if n < 80:
        return None
    fast_e = {s: _ema(close, s) for s in GMMA_FAST}
    slow_e = {s: _ema(close, s) for s in GMMA_SLOW}
    fast_min = pd.concat([fast_e[s] for s in GMMA_FAST], axis=1).min(axis=1)
    fast_max = pd.concat([fast_e[s] for s in GMMA_FAST], axis=1).max(axis=1)
    slow_min = pd.concat([slow_e[s] for s in GMMA_SLOW], axis=1).min(axis=1)
    slow_max = pd.concat([slow_e[s] for s in GMMA_SLOW], axis=1).max(axis=1)
    bull = fast_min > slow_max
    bear = fast_max < slow_min
    rsi = _rsi(close, 14)
    bbw = _bollinger_width(close, 20, 2)
    lookback = int(st.get('squeeze_lookback', 30))
    vma = df['volume'].rolling(20).mean()
    friction = float(st.get('friction_bps', 10)) / 100.0  # bps -> %
    rsi_low = st.get('rsi_low', 30); rsi_high = st.get('rsi_high', 80)

    horizons = [5, 10]
    detectors = {k: {'triggers': 0, 'h': {h: [] for h in horizons}} for k in
                 ['gmma_crossover', 'dip_buy', 'squeeze', 'rsi_oversold', 'rsi_overbought']}

    def fwd(i, h, direction):
        j = i + h
        if j >= n:
            return None
        raw = (close.iloc[j] - close.iloc[i]) / close.iloc[i] * 100.0
        r = raw if direction == 'long' else -raw
        return round(r - friction, 3)

    start = 61
    for i in range(start, n - 1):
        # GMMA crossover (state change on closed candles)
        if bull.iloc[i] and not bull.iloc[i - 1]:
            detectors['gmma_crossover']['triggers'] += 1
            for h in horizons:
                v = fwd(i, h, 'long');  detectors['gmma_crossover']['h'][h].append(v) if v is not None else None
        elif bear.iloc[i] and not bear.iloc[i - 1]:
            detectors['gmma_crossover']['triggers'] += 1
            for h in horizons:
                v = fwd(i, h, 'short'); detectors['gmma_crossover']['h'][h].append(v) if v is not None else None
        # Dip-buy
        slow_top_i = slow_max.iloc[i]
        expanded = bull.iloc[i] and slow_e[60].iloc[i] > slow_e[60].iloc[i - 5]
        if expanded and (low.iloc[i] <= slow_top_i * 1.01) and (close.iloc[i] > openp.iloc[i]) and (close.iloc[i] > slow_top_i):
            detectors['dip_buy']['triggers'] += 1
            for h in horizons:
                v = fwd(i, h, 'long'); detectors['dip_buy']['h'][h].append(v) if v is not None else None
        # Squeeze (measure absolute expansion -> treat as long-neutral magnitude)
        recent = bbw.iloc[max(0, i - lookback + 1):i + 1]
        if len(recent) and bbw.iloc[i] <= float(recent.min()) * 1.03:
            detectors['squeeze']['triggers'] += 1
            for h in horizons:
                j = i + h
                if j < n:
                    detectors['squeeze']['h'][h].append(round(abs((close.iloc[j] - close.iloc[i]) / close.iloc[i] * 100.0) - friction, 3))
        # RSI exhaustion
        if rsi.iloc[i] < rsi_low and rsi.iloc[i - 1] >= rsi_low:
            detectors['rsi_oversold']['triggers'] += 1
            for h in horizons:
                v = fwd(i, h, 'long'); detectors['rsi_oversold']['h'][h].append(v) if v is not None else None
        if rsi.iloc[i] > rsi_high and rsi.iloc[i - 1] <= rsi_high:
            detectors['rsi_overbought']['triggers'] += 1
            for h in horizons:
                v = fwd(i, h, 'short'); detectors['rsi_overbought']['h'][h].append(v) if v is not None else None

    out = {}
    for k, d in detectors.items():
        row = {'triggers': d['triggers']}
        for h in horizons:
            arr = [x for x in d['h'][h] if x is not None]
            if arr:
                wins = sum(1 for x in arr if x > 0)
                row[f'win_{h}'] = round(wins / len(arr) * 100)
                row[f'avg_{h}'] = round(sum(arr) / len(arr), 2)
            else:
                row[f'win_{h}'] = None; row[f'avg_{h}'] = None
        out[k] = row
    return out


@app.get('/api/v1/alert-engine/backtest')
def alert_engine_backtest(symbol: str = 'BTC'):
    sym = (symbol or 'BTC').upper()
    if sym not in ALERT_COIN_PAIRS:
        return JSONResponse({'status': 'error', 'message': 'unknown symbol'}, status_code=400)
    df = _daily_ohlcv(sym)
    if df is None or len(df) < 80:
        return {'status': 'error', 'message': 'not enough data'}
    st = _get_alert_settings()
    res = _backtest_detector(df, st)
    return {'status': 'ready', 'symbol': sym, 'candles': int(len(df)),
            'from': df['timestamp'].iloc[0].strftime('%Y-%m-%d'),
            'to': df['timestamp'].iloc[-1].strftime('%Y-%m-%d'),
            'friction_bps': st.get('friction_bps', 10), 'horizons': [5, 10], 'detectors': res}


def _build_digest():
    since = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
    try:
        rows = list(smart_alerts_col.find({'category': 'signal', 'ts': {'$gte': since}}, {'_id': 0}).sort('ts', -1))
    except Exception:  # noqa
        rows = []
    by_coin = {}
    for a in rows:
        by_coin.setdefault(a.get('symbol', '?'), []).append(a)
    return {'count': len(rows), 'coins': len(by_coin), 'by_coin': by_coin, 'alerts': rows}


@app.get('/api/v1/alert-engine/digest')
def alert_engine_digest():
    d = _build_digest()
    return {'status': 'ready', **d}


def _alert_digest_job():
    """Once-a-day consolidated summary of everything the engine fired in the last 24h."""
    try:
        d = _build_digest()
        if d['count'] <= 0:
            push_alert('digest', 'info', 'Daily signal digest',
                       'No technical signals fired across your watchlist in the last 24h — the market stayed quiet.',
                       'digest', 'BTC')
            return
        parts = []
        for sym, als in d['by_coin'].items():
            parts.append(f"{sym}: " + ', '.join(a['title'].split('·')[-1].strip() for a in als[:4]))
        msg = f"{d['count']} signal(s) across {d['coins']} coin(s) in the last 24h — " + ' · '.join(parts[:8])
        push_alert('digest', 'medium', f"Daily signal digest — {d['count']} fired", msg, 'digest', 'BTC')
    except Exception:  # noqa
        traceback.print_exc()


@app.get('/api/v1/alert-engine/config')
def alert_engine_config():
    st = _get_alert_settings()
    coins = [{'symbol': c, 'name': ALERT_COIN_NAMES.get(c, c)} for c in ALERT_COINS]
    return {'status': 'ready', 'settings': st, 'coins': coins,
            'netflow_note': 'Exchange netflow filter is BTC-only until an on-chain (Glassnode) key is added.'}


@app.post('/api/v1/alert-engine/config')
def alert_engine_config_save(payload: dict = Body(...)):
    st = _save_alert_settings(payload.get('settings') or payload)
    return {'status': 'ready', 'settings': st}


@app.get('/api/v1/alert-engine/readings')
def alert_engine_readings(symbol: str = 'BTC'):
    sym = (symbol or 'BTC').upper()
    if sym not in ALERT_COIN_PAIRS:
        return JSONResponse({'status': 'error', 'message': 'unknown symbol'}, status_code=400)
    res = _scan_symbol(sym, fire=False)
    return {'status': 'ready', **res}


@app.post('/api/v1/alert-engine/scan')
def alert_engine_scan(payload: dict = Body(default={})):
    """Manually run a scan now. Optional {symbol} to scan one coin (fires alerts)."""
    st = _get_alert_settings()
    sym = (payload.get('symbol') or '').upper()
    if sym and sym in ALERT_COIN_PAIRS:
        res = _scan_symbol(sym, st, fire=True)
        return {'status': 'ready', 'scanned': [sym], 'result': res}
    scanned = []
    for s in st.get('watchlist', []):
        try:
            _scan_symbol(s, st, fire=True)
            scanned.append(s)
        except Exception:  # noqa
            traceback.print_exc()
    return {'status': 'ready', 'scanned': scanned}


@app.get('/api/v1/alert-engine/recent')
def alert_engine_recent(limit: int = 30):
    try:
        rows = list(smart_alerts_col.find({'category': 'signal'}, {'_id': 0}).sort('ts', -1).limit(int(limit)))
    except Exception:  # noqa
        rows = []
    return {'status': 'ready', 'alerts': rows}


# --- Sector rotation, detector edge ranking, and token-unlock filter --------
ALERT_SECTORS = {
    'BTC': 'Store of Value',
    'ETH': 'Smart-Contract L1', 'SOL': 'Smart-Contract L1', 'ADA': 'Smart-Contract L1',
    'AVAX': 'Smart-Contract L1', 'DOT': 'Smart-Contract L1', 'NEAR': 'Smart-Contract L1',
    'ATOM': 'Smart-Contract L1', 'APT': 'Smart-Contract L1', 'MATIC': 'Smart-Contract L1',
    'XRP': 'Payments', 'XLM': 'Payments', 'LTC': 'Payments', 'BCH': 'Payments', 'DOGE': 'Payments',
    'UNI': 'DeFi', 'AAVE': 'DeFi', 'LINK': 'DeFi',
    'FIL': 'Infrastructure', 'ETC': 'Infrastructure',
}
_SECTOR_CACHE = {'ts': 0, 'data': None}
_EDGE_CACHE = {}   # sym -> (ts, {detector: {...}})
_UNLOCK_CACHE = {}  # sym -> (ts, dict)
TOKENOMIST_API_KEY = os.environ.get('TOKENOMIST_API_KEY', '')
TOKENOMIST_SLUGS = {
    'ETH': 'ethereum', 'SOL': 'solana', 'ADA': 'cardano', 'AVAX': 'avalanche-2', 'DOT': 'polkadot',
    'NEAR': 'near', 'ATOM': 'cosmos', 'APT': 'aptos', 'MATIC': 'matic-network', 'XRP': 'ripple',
    'XLM': 'stellar', 'LTC': 'litecoin', 'BCH': 'bitcoin-cash', 'DOGE': 'dogecoin', 'UNI': 'uniswap',
    'AAVE': 'aave', 'LINK': 'chainlink', 'FIL': 'filecoin', 'ETC': 'ethereum-classic',
}


def _coin_sector(symbol):
    return ALERT_SECTORS.get((symbol or '').upper(), 'Other')


def _sector_strength():
    """Mean [ALT]/BTC 7d relative strength per sector — >0 means capital rotating in."""
    now = _time_mod.time()
    if _SECTOR_CACHE['data'] is not None and (now - _SECTOR_CACHE['ts']) < 3600:
        return _SECTOR_CACHE['data']
    buckets = {}
    for sym, sec in ALERT_SECTORS.items():
        if sym == 'BTC':
            continue
        rs = _btc_rel_strength(sym, 7)
        if rs is None:
            continue
        buckets.setdefault(sec, []).append(rs)
    out = {sec: round(sum(v) / len(v), 2) for sec, v in buckets.items() if v}
    _SECTOR_CACHE['ts'] = now
    _SECTOR_CACHE['data'] = out
    return out


def _detector_edge(symbol):
    """Backtest-derived edge per detector for a coin (cached ~6h)."""
    sym = (symbol or 'BTC').upper()
    now = _time_mod.time()
    c = _EDGE_CACHE.get(sym)
    if c and (now - c[0]) < 6 * 3600:
        return c[1]
    edge = {}
    try:
        df = _daily_ohlcv(sym)
        if df is not None and len(df) >= 80:
            res = _backtest_detector(df, _get_alert_settings()) or {}
            for k, r in res.items():
                score = None
                if r.get('avg_10') is not None:
                    score = round((r.get('avg_10') or 0) * ((r.get('win_10') or 50) / 50.0), 3)
                edge[k] = {'triggers': r.get('triggers'), 'win_10': r.get('win_10'),
                           'avg_10': r.get('avg_10'), 'score': score}
    except Exception:  # noqa
        pass
    _EDGE_CACHE[sym] = (now, edge)
    return edge


def _token_unlock(symbol, days=14):
    """Next token unlock within `days` (Tokenomist, key-gated). Returns None if no key / no event."""
    sym = (symbol or '').upper()
    if not TOKENOMIST_API_KEY or sym not in TOKENOMIST_SLUGS:
        return None
    now = _time_mod.time()
    c = _UNLOCK_CACHE.get(sym)
    if c and (now - c[0]) < 12 * 3600:
        return c[1]
    result = None
    try:
        slug = TOKENOMIST_SLUGS[sym]
        start = datetime.date.today()
        end = start + datetime.timedelta(days=int(days))
        r = requests.get(f'https://api.tokenomist.ai/v5/unlock/events/{slug}',
                         params={'start': start.isoformat(), 'end': end.isoformat(), 'page': 1, 'pageSize': 100},
                         headers={'x-api-key': TOKENOMIST_API_KEY}, timeout=15)
        if r.status_code == 200:
            rows = (r.json() or {}).get('data', []) or []
            rows.sort(key=lambda x: x.get('unlockDate', ''))
            if rows:
                ev = rows[0]
                cliff = ev.get('cliffUnlocks') or {}
                amt = float(cliff.get('cliffAmount') or 0)
                pct = cliff.get('valueToMarketCap')
                try:
                    ud = datetime.datetime.fromisoformat(str(ev.get('unlockDate', '')).replace('Z', ''))
                    days_until = max(0, (ud.date() - start).days)
                except Exception:
                    days_until = None
                result = {'symbol': sym, 'unlock_date': ev.get('unlockDate'), 'amount': amt,
                          'percent_of_supply': round(float(pct), 2) if pct is not None else None,
                          'days_until': days_until, 'within': True, 'source': ev.get('dataSource')}
    except Exception:  # noqa
        result = None
    _UNLOCK_CACHE[sym] = (now, result)
    return result


@app.get('/api/v1/alert-engine/sectors')
def alert_engine_sectors():
    strengths = _sector_strength()
    members = {}
    for sym, sec in ALERT_SECTORS.items():
        members.setdefault(sec, []).append(sym)
    out = [{'sector': sec, 'strength': strengths.get(sec), 'hot': (strengths.get(sec) or 0) > 0,
            'members': members.get(sec, [])} for sec in members if sec != 'Store of Value']
    out.sort(key=lambda x: (x['strength'] if x['strength'] is not None else -999), reverse=True)
    return {'status': 'ready', 'sectors': out}


@app.get('/api/v1/alert-engine/edge')
def alert_engine_edge(symbol: str = 'BTC'):
    sym = (symbol or 'BTC').upper()
    if sym not in ALERT_COIN_PAIRS:
        return JSONResponse({'status': 'error'}, status_code=400)
    edge = _detector_edge(sym)
    ranked = sorted([{'detector': k, **v} for k, v in edge.items() if v.get('score') is not None],
                    key=lambda x: x['score'], reverse=True)
    return {'status': 'ready', 'symbol': sym, 'ranked': ranked, 'best': ranked[0] if ranked else None}


@app.get('/api/v1/alert-engine/edge-board')
def alert_engine_edge_board():
    st = _get_alert_settings()
    board = []
    for sym in st.get('watchlist', []):
        try:
            edge = _detector_edge(sym)
            ranked = sorted([{'detector': k, **v} for k, v in edge.items() if v.get('score') is not None],
                            key=lambda x: x['score'], reverse=True)
            if ranked:
                board.append({'symbol': sym, 'best': ranked[0], 'ranked': ranked})
        except Exception:  # noqa
            continue
    board.sort(key=lambda x: (x['best']['score'] if x['best'] else -999), reverse=True)
    return {'status': 'ready', 'board': board}


@app.get('/api/v1/alert-engine/unlocks')
def alert_engine_unlocks(symbol: str = 'ETH'):
    sym = (symbol or 'ETH').upper()
    if not TOKENOMIST_API_KEY:
        return {'status': 'ready', 'available': False, 'unlock': None,
                'note': 'Add TOKENOMIST_API_KEY to the backend to enable the token-unlock filter.'}
    u = _token_unlock(sym, 30)
    return {'status': 'ready', 'available': True, 'symbol': sym, 'unlock': u}


# =====================================================================
# ALBERT'S ENGINES — compact context so the chat/brief LLM can talk about
# the Alert-Engine edge board, sector rotation, recently fired signals and
# the user's ACTIVE strategies. A background job snapshots the (heavier)
# edge board + sectors so chat reads are instant.
# =====================================================================
def _build_engine_snapshot():
    """Compute the edge board + sector rotation once (used by the warmer job)."""
    snap = {'generated_at': datetime.datetime.utcnow().isoformat()}
    try:
        strengths = _sector_strength()
        members = {}
        for sym, sec in ALERT_SECTORS.items():
            members.setdefault(sec, []).append(sym)
        secs = [{'sector': sec, 'strength': strengths.get(sec),
                 'hot': (strengths.get(sec) or 0) > 0}
                for sec in members if sec != 'Store of Value']
        secs.sort(key=lambda x: (x['strength'] if x['strength'] is not None else -999), reverse=True)
        snap['sectors'] = secs
    except Exception:  # noqa
        snap['sectors'] = []
    try:
        st = _get_alert_settings()
        board = []
        for sym in st.get('watchlist', []):
            try:
                edge = _detector_edge(sym)
                ranked = sorted([{'detector': k, **v} for k, v in edge.items() if v.get('score') is not None],
                                key=lambda x: x['score'], reverse=True)
                if ranked:
                    board.append({'symbol': sym, 'best': ranked[0]})
            except Exception:  # noqa
                continue
        board.sort(key=lambda x: (x['best']['score'] if x['best'] else -999), reverse=True)
        snap['edge_board'] = board[:12]
    except Exception:  # noqa
        snap['edge_board'] = []
    return snap


def _engine_snapshot_job():
    try:
        snap = _build_engine_snapshot()
        misc_col.update_one({'_id': 'albert_engine_snapshot'},
                            {'$set': {'data': snap, 'ts': _time_mod.time()}}, upsert=True)
    except Exception:  # noqa
        traceback.print_exc()


def _albert_engine_context(symbol='BTC', pid=None):
    """Compact, guarded block describing the live engines + user strategies."""
    L = []
    doc = misc_col.find_one({'_id': 'albert_engine_snapshot'}) or {}
    snap = doc.get('data') or {}
    # If the snapshot is missing/stale, warm it in the background (never blocks chat).
    if (not snap) or (_time_mod.time() - (doc.get('ts') or 0)) > 6 * 3600:
        try:
            _LLM_POOL.submit(_engine_snapshot_job)
        except Exception:  # noqa
            pass
    board = snap.get('edge_board') or []
    if board:
        L.append('ALERT ENGINE — highest-edge setups right now (edge score = avg 10-day forward return × '
                 'win-rate factor from the backtest; higher = stronger historical edge):')
        for b in board[:6]:
            be = b.get('best') or {}
            L.append(f"- {b.get('symbol')}: {be.get('detector')} — edge score {be.get('score')}, "
                     f"win rate {be.get('win_10')}%, avg 10d {be.get('avg_10')}% (n={be.get('triggers')} triggers).")
    secs = snap.get('sectors') or []
    if secs:
        hot = [s for s in secs if s.get('hot') and s.get('strength') is not None][:3]
        cold = [s for s in secs if s.get('strength') is not None and not s.get('hot')][-3:]
        if hot:
            L.append('SECTOR ROTATION — capital rotating IN: '
                     + ', '.join(f"{s['sector']} (+{s['strength']}% vs BTC, 7d)" for s in hot) + '.')
        if cold:
            L.append('Rotating OUT: '
                     + ', '.join(f"{s['sector']} ({s['strength']}%)" for s in cold) + '.')
    # Recently fired signals (fast DB read).
    try:
        rows = list(smart_alerts_col.find({'category': 'signal'}, {'_id': 0}).sort('ts', -1).limit(6))
        if rows:
            L.append('RECENT SIGNALS the engine fired (most recent first):')
            for a in rows:
                L.append(f"- {a.get('symbol', '')}: {a.get('title', '')}")
    except Exception:  # noqa
        pass
    # User's ACTIVE tracked strategies (fast DB read).
    try:
        _sq = {'status': 'active', 'kind': {'$ne': 'basket'}}
        if pid:
            _sq['owner'] = (str(pid) or '').strip()[:80]
        strats = list(strategies_col.find(_sq, {'_id': 0}).sort('created_at', -1).limit(8))
        if strats:
            L.append("USER'S ACTIVE STRATEGIES (Albert is tracking these — reference by name):")
            for s in strats:
                try:
                    perf = _strategy_perf(s) or {}
                except Exception:  # noqa
                    perf = {}
                pnl = perf.get('pnl_pct')
                stance = s.get('bias') or s.get('position') or ''
                L.append(f"- {s.get('symbol')}: '{s.get('title')}' [{stance}] — entry ${s.get('entry_price')}, "
                         f"P&L {pnl if pnl is not None else 'n/a'}%, {perf.get('status') or s.get('status')}.")
    except Exception:  # noqa
        pass
    # User's ACTIVE multi-coin baskets — so Albert can answer "how are my baskets doing?"
    # straight from saved baskets (live numbers; he must not invent them).
    try:
        _bq = {'status': 'active', 'kind': 'basket'}
        if pid:
            _bq['owner'] = (str(pid) or '').strip()[:80]
        bks = list(strategies_col.find(_bq, {'_id': 0}).sort('created_at', -1).limit(6))
        if bks:
            L.append("USER'S ACTIVE MULTI-COIN STRATEGIES (Albert tracks these — reference by name; when asked "
                     "'how are my strategies doing' summarise THESE live numbers, do NOT invent any). Call them "
                     "'strategies', never 'baskets':")
            for b in bks:
                try:
                    perf = _basket_perf(b) or {}
                except Exception:  # noqa
                    perf = {}
                legs = perf.get('legs', []) or []
                leg_bits = ', '.join(
                    f"{lg.get('symbol')} {lg.get('position')} {lg.get('weight_pct')}% (P&L {lg.get('pnl_pct')}%)"
                    for lg in legs)
                L.append(f"- '{b.get('title')}' [{len(legs)} legs, {b.get('horizon_days')}d, "
                         f"{perf.get('days_active', 0)}d active] — strategy P&L {perf.get('total_pnl_pct')}% "
                         f"(${perf.get('total_pnl_usd')} on ${b.get('size_usd')}). Legs: {leg_bits}.")
    except Exception:  # noqa
        pass
    return ('\n'.join(L)) if L else ''


@app.get('/api/v1/albert/engine-brief')
def albert_engine_brief(symbol: str = 'BTC', pid: str = ''):
    """Raw engine context block (debug/UX aid)."""
    return {'status': 'ready', 'context': _albert_engine_context(symbol, (pid or '').strip()[:80] or None)}






@app.get('/api/v1/albert/brief')
async def albert_brief(request: Request, refresh: int = 0, mode: str = 'plain', symbol: str = 'BTC'):
    """Albert's Morning Brief — a daily summary, coin-specific. mode='plain' (layman,
    default) or 'technical'; symbol selects the asset (BTC default)."""
    mode = 'technical' if mode == 'technical' else 'plain'
    symbol = (symbol or 'BTC').strip().upper()[:6]
    is_btc = symbol == 'BTC'
    if not is_btc and symbol not in COMPARE_COINS:
        return {'status': 'error', 'reason': 'unsupported_symbol'}
    today = datetime.date.today().isoformat()
    cache_id = f'brief:{today}:{mode}' if is_btc else f'brief:{today}:{mode}:{symbol}'
    if not refresh:
        c = insights_col.find_one({'_id': cache_id}, {'_id': 0})
        if c and c.get('text'):
            return {'status': 'ready', 'cached': True, 'mode': mode, 'symbol': symbol, **c}
    if _rate_limited(request, 'albert_brief', per_min=10, per_day=200):
        return {'status': 'computing', 'reason': 'rate_limited'}
    try:
        if is_btc:
            ctx, as_of = _brief_context()
            coin_name = 'Bitcoin'
            sys_prompt = ALBERT_BRIEF_TECH_SYSTEM if mode == 'technical' else ALBERT_BRIEF_SYSTEM
            sys_msg = sys_prompt.format(ctx=ctx)
        else:
            ctx, coin_name, as_of = _coin_brief_context(symbol)
            sys_prompt = ALBERT_BRIEF_COIN_TECH_SYSTEM if mode == 'technical' else ALBERT_BRIEF_COIN_SYSTEM
            sys_msg = sys_prompt.format(ctx=ctx, coin=coin_name)
        if not ctx.strip():
            return {'status': 'computing'}
        if not (LLM_READY_KEY and _HAS_LLM):
            return {'status': 'ready', 'cached': False, 'mode': mode, 'symbol': symbol, 'text': ctx,
                    'observations': [l for l in ctx.split('\n')][:5], 'take': '', 'as_of': as_of}
        chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'brief-{uuid.uuid4().hex[:10]}',
                        system_message=sys_msg)
                .with_model('gemini', _model_for('brief')).with_params(temperature=0.4, max_tokens=6000))
        reply = await chat.send_message(UserMessage(text=f"Write today's {coin_name} brief now."))
        text = (reply if isinstance(reply, str) else (getattr(reply, 'content', None) or getattr(reply, 'text', None) or '')).strip()
        _bump_usage('llm_brief')
        obs, take = [], ''
        for ln in text.split('\n'):
            ln = ln.strip()
            if ln.upper().startswith('TAKE:'):
                take = ln[5:].strip()
            elif ln.startswith('-'):
                obs.append(ln.lstrip('-').strip())
        now_iso = datetime.datetime.utcnow().isoformat()
        doc = {'text': text, 'observations': obs, 'take': take, 'as_of': as_of,
               'model': CHAT_MODEL, 'generated_at': now_iso, 'mode': mode, 'symbol': symbol, 'coin': coin_name}
        insights_col.update_one({'_id': cache_id}, {'$set': {'_id': cache_id, 'kind': 'brief', **doc}}, upsert=True)
        return {'status': 'ready', 'cached': False, **doc}
    except Exception:  # noqa
        traceback.print_exc()
        return {'status': 'fallback'}




# =====================================================================
# COMPARE COINS  (per-coin quant summary via the same pipeline, cached)
# =====================================================================
COMPARE_COINS = {
    'BTC': {'name': 'Bitcoin', 'pairs': [('kraken', 'BTC/USD'), ('coinbase', 'BTC/USD')]},
    'ETH': {'name': 'Ethereum', 'pairs': [('kraken', 'ETH/USD'), ('coinbase', 'ETH/USD')]},
    'SOL': {'name': 'Solana', 'pairs': [('kraken', 'SOL/USD'), ('coinbase', 'SOL/USD')]},
    'XRP': {'name': 'XRP', 'pairs': [('kraken', 'XRP/USD'), ('coinbase', 'XRP/USD')]},
    'ADA': {'name': 'Cardano', 'pairs': [('kraken', 'ADA/USD'), ('coinbase', 'ADA/USD')]},
    'DOGE': {'name': 'Dogecoin', 'pairs': [('kraken', 'DOGE/USD'), ('coinbase', 'DOGE/USD')]},
    'AVAX': {'name': 'Avalanche', 'pairs': [('kraken', 'AVAX/USD'), ('coinbase', 'AVAX/USD')]},
    'LINK': {'name': 'Chainlink', 'pairs': [('kraken', 'LINK/USD'), ('coinbase', 'LINK/USD')]},
    'DOT': {'name': 'Polkadot', 'pairs': [('kraken', 'DOT/USD'), ('coinbase', 'DOT/USD')]},
    'LTC': {'name': 'Litecoin', 'pairs': [('kraken', 'LTC/USD'), ('coinbase', 'LTC/USD')]},
    'MATIC': {'name': 'Polygon', 'pairs': [('kraken', 'MATIC/USD'), ('coinbase', 'MATIC/USD')]},
    'ATOM': {'name': 'Cosmos', 'pairs': [('kraken', 'ATOM/USD'), ('coinbase', 'ATOM/USD')]},
}


def _fetch_ohlcv_pairs(pairs):
    errors = []
    for name, sym in pairs:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            bars = ex.fetch_ohlcv(sym, timeframe='1d', limit=720)
            if bars and len(bars) > 250:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df.sort_values('timestamp').reset_index(drop=True), name
        except Exception as e:  # noqa
            errors.append(f'{name}: {e}')
    raise RuntimeError('All sources failed: ' + ' | '.join(errors))


def compute_coin_summary(symbol):
    cfg = COMPARE_COINS[symbol]
    df, source = _fetch_ohlcv_pairs(cfg['pairs'])
    df = build_features(df).dropna().reset_index(drop=True)
    feats = df.iloc[-1]
    last_close = float(df['close'].iloc[-1])
    prev_close = float(df['close'].iloc[-2])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)
    ts = df['timestamp'].iloc[-1]
    quant = compute_quant_analysis(df, feats, last_close, ts)
    fc = quant.get('forecasts', []) or []

    def _find(h):
        for f in fc:
            if f.get('horizon') == h:
                return f
        return {}
    f24 = _find('24H') or (fc[0] if fc else {})
    f7 = _find('7D')
    regime = quant.get('regime') or {}
    regime_name = regime.get('regime') if isinstance(regime, dict) else str(regime)
    support = resistance = None
    try:
        chart = compute_chart_intelligence(df)
        for lv in (chart.get('sr_levels') or []):
            if lv['type'] == 'support' and (support is None or lv['price'] > support):
                support = lv['price']  # nearest support below is highest support under price
            if lv['type'] == 'resistance' and (resistance is None or lv['price'] < resistance):
                resistance = lv['price']
    except Exception:  # noqa
        pass
    spark = [round(float(c), 4) for c in df['close'].tail(60).tolist()]
    return {
        'symbol': symbol, 'name': cfg['name'], 'source': source, 'as_of': ts.strftime('%Y-%m-%d'),
        'price': round(last_close, 2), 'day_change_pct': day_change,
        'quant_score': quant['quant_score'], 'quant_label': quant['quant_label'],
        'regime': regime_name,
        'forecast_24h': {'higher': f24.get('higher'), 'confidence': f24.get('confidence'), 'confidence_pct': f24.get('confidence_pct')},
        'forecast_7d': {'higher': f7.get('higher'), 'confidence': f7.get('confidence'), 'confidence_pct': f7.get('confidence_pct')},
        'bullish': (quant['factors']['bullish'] or [])[:2],
        'risk': (quant['factors']['risk'] or [])[:2],
        'support': support, 'resistance': resistance, 'spark': spark,
    }


@app.get('/api/v1/compare/coins')
def compare_coins_list():
    return {'coins': [{'symbol': k, 'name': v['name']} for k, v in COMPARE_COINS.items()]}


@app.get('/api/v1/compare/coin')
def compare_coin(symbol: str = 'BTC', refresh: int = 0):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    if symbol not in COMPARE_COINS:
        return {'status': 'error', 'reason': 'unsupported_symbol'}
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    cache_id = f"{symbol}:{today}"
    if not refresh:
        cached = compare_col.find_one({'_id': cache_id}, {'_id': 0})
        if cached and cached.get('data'):
            return {'status': 'ready', 'cached': True, 'data': cached['data']}
    try:
        data = compute_coin_summary(symbol)
        compare_col.update_one({'_id': cache_id},
                               {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today, 'data': data,
                                         'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        return {'status': 'ready', 'cached': False, 'data': data}
    except Exception as ex:  # noqa
        traceback.print_exc()
        return {'status': 'error', 'reason': str(ex)[:200]}



# =====================================================================
# GLOBAL COIN SWITCH — full per-coin dashboard (altcoins), isolated from
# the Bitcoin pipeline (no persistence, no BTC ledger writes).
# =====================================================================
_coin_dash_state = {}          # symbol -> 'running' | 'done' | 'error'
_coin_dash_lock = threading.Lock()


def compute_coin_dashboard(symbol):
    """Build a full dashboard payload for any supported coin using the same
    price-agnostic quant engine as Bitcoin. BTC-specific engines (halving cycle,
    dominance, policy, news, events, ETF/institutional) are left None because
    those views are hidden for altcoins in the UI."""
    cfg = COMPARE_COINS[symbol]
    df, source = _fetch_ohlcv_pairs(cfg['pairs'])
    df = build_features(df)
    df = df.dropna().reset_index(drop=True)
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)

    live_row = df.iloc[[-1]].copy()
    train_df = df.iloc[:-1].copy()
    X = train_df[FEATURE_COLS]
    y = train_df['Target']

    # TimeSeriesSplit cross validation
    tscv = TimeSeriesSplit(n_splits=5)
    cv_folds = []
    for i, (tr, te) in enumerate(tscv.split(X)):
        m = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr], y.iloc[tr])
        acc = accuracy_score(y.iloc[te], m.predict(X.iloc[te]))
        cv_folds.append({'fold': i + 1, 'accuracy': round(float(acc) * 100, 2), 'testSize': int(len(te))})

    # Walk-forward backtest -> accuracy over time + trade log
    start = 200 if len(X) > 260 else max(30, int(len(X) * 0.4))
    retrain_every = 10
    model = None
    rows = []
    trades = []
    closes_full = df['close'].reset_index(drop=True)
    for i in range(start, len(X)):
        if model is None or (i - start) % retrain_every == 0:
            model = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
            model.fit(X.iloc[:i], y.iloc[:i])
        classes = list(model.classes_)
        pred = int(model.predict(X.iloc[[i]])[0])
        proba = model.predict_proba(X.iloc[[i]])[0]
        conf = float(proba[classes.index(pred)]) * 100 if pred in classes else 50.0
        actual = int(y.iloc[i])
        cur_close = float(closes_full.iloc[i])
        nxt_close = float(closes_full.iloc[i + 1])
        d = train_df['timestamp'].iloc[i]
        rows.append({'date': d, 'correct': 1 if pred == actual else 0, 'close': cur_close})
        trades.append({
            'date': d.strftime('%Y-%m-%d'),
            'signal': 'UP' if pred == 1 else 'DOWN',
            'confidence': round(conf, 1),
            'close': round(cur_close, 2),
            'nextClose': round(nxt_close, 2),
            'actual': 'UP' if actual == 1 else 'DOWN',
            'correct': bool(pred == actual),
        })

    total = len(trades)
    wins = sum(1 for t in trades if t['correct'])
    losses = total - wins
    win_rate = round(wins / total * 100, 1) if total else 0.0
    best = cur = 0
    for t in trades:
        if t['correct']:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    sign = None
    streak_len = 0
    for t in reversed(trades):
        if sign is None:
            sign = t['correct']
            streak_len = 1
        elif t['correct'] == sign:
            streak_len += 1
        else:
            break
    scoreboard = {
        'total': total, 'wins': wins, 'losses': losses, 'winRate': win_rate,
        'bestWinStreak': best, 'currentStreak': (streak_len if sign else -streak_len),
    }
    recent_trades = list(reversed(trades))[:25]

    pser = pd.DataFrame(rows)
    pser['rolling_acc'] = pser['correct'].rolling(30, min_periods=10).mean() * 100
    overall_acc = round(float(pser['correct'].mean()) * 100, 2)
    performance = []
    for _, r in pser.iterrows():
        if pd.isna(r['rolling_acc']):
            continue
        d = r['date']
        performance.append({
            'date': d.strftime('%m/%d'),
            'iso': d.strftime('%Y-%m-%d'),
            'btcPrice': round(float(r['close']), 2),
            'aiAccuracy': round(float(r['rolling_acc']), 2),
        })

    final = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1)
    final.fit(X, y)
    live_X = live_row[FEATURE_COLS]
    pred = int(final.predict(live_X)[0])
    proba = final.predict_proba(live_X)[0]
    classes = list(final.classes_)
    p_up = float(proba[classes.index(1)]) if 1 in classes else 0.0
    p_down = float(proba[classes.index(0)]) if 0 in classes else 0.0
    confidence = round((p_up if pred == 1 else p_down) * 100, 2)

    importances = sorted(
        [{'feature': f, 'label': FEATURE_META[f]['label'], 'category': FEATURE_META[f]['category'],
          'importance': round(float(imp) * 100, 2)} for f, imp in zip(FEATURE_COLS, final.feature_importances_)],
        key=lambda z: -z['importance'],
    )

    feats = live_row.iloc[0]
    feature_snapshot = [
        {'feature': 'RSI', 'label': 'RSI (14)', 'category': 'Momentum', 'value': round(float(feats['RSI']) * 100, 1), 'unit': ''},
        {'feature': 'StochRSI', 'label': 'Stochastic RSI', 'category': 'Momentum', 'value': round(float(feats['StochRSI']) * 100, 1), 'unit': ''},
        {'feature': 'MACD_Hist_Norm', 'label': 'MACD Histogram', 'category': 'Trend', 'value': round(float(feats['MACD_Hist_Norm']) * 100, 3), 'unit': '%'},
        {'feature': 'EMA_Ratio', 'label': 'EMA 9/21 Spread', 'category': 'Trend', 'value': round(float(feats['EMA_Ratio']) * 100, 2), 'unit': '%'},
        {'feature': 'ATR_Pct', 'label': 'ATR %', 'category': 'Volatility', 'value': round(float(feats['ATR_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'BB_Width_Pct', 'label': 'Bollinger Width', 'category': 'Volatility', 'value': round(float(feats['BB_Width_Pct']) * 100, 2), 'unit': '%'},
        {'feature': 'Volume_Z', 'label': 'Volume Z-Score', 'category': 'Volume', 'value': round(float(feats['Volume_Z']), 2), 'unit': 'σ'},
        {'feature': 'Volume_Ratio', 'label': 'Volume Ratio', 'category': 'Volume', 'value': round(float(feats['Volume_Ratio']), 2), 'unit': 'x'},
    ]

    prev_close = float(train_df['close'].iloc[-1])
    last_close = float(live_row['close'].iloc[0])
    day_change = round((last_close - prev_close) / prev_close * 100, 2)
    as_of = live_row['timestamp'].iloc[0].strftime('%Y-%m-%d')
    predict_for = (live_row['timestamp'].iloc[0] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

    quant = compute_quant_analysis(df, feats, last_close, live_row['timestamp'].iloc[0])

    chart = market_intel = decision = risk = alerts = None
    try:
        chart = compute_chart_intelligence(df)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        market_intel = build_market_intel(quant, quant['forecasts'], None, None, chart)
    except Exception:  # noqa
        traceback.print_exc()
    all_outlook = list(quant['forecasts']) + list(quant.get('long_outlook', []))
    try:
        decision = compute_decision_engine(quant, all_outlook, None, None, chart, None, None)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        risk = compute_risk_engine(quant, chart, decision, None, None, last_close, feats)
    except Exception:  # noqa
        traceback.print_exc()
    try:
        alerts = compute_alerts(quant, None, None, chart, None)
    except Exception:  # noqa
        traceback.print_exc()
    dominance = None
    try:
        dominance = compute_coin_dominance(symbol, day_change)
    except Exception:  # noqa
        traceback.print_exc()
    institutional = None
    try:
        institutional = get_onchain_panels(symbol).get('institutional')
    except Exception:  # noqa
        traceback.print_exc()

    doc = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.datetime.utcnow().isoformat(),
        'as_of': as_of,
        'symbol': symbol,
        'coin_name': cfg['name'],
        'data_source': source,
        'pair': f'{symbol}/USD',
        'last_close': round(last_close, 2),
        'day_change_pct': day_change,
        'signal': 'UP' if pred == 1 else 'DOWN',
        'confidence': confidence,
        'prob_up': round(p_up * 100, 2),
        'prob_down': round(p_down * 100, 2),
        'overall_accuracy': overall_acc,
        'cv_folds': cv_folds,
        'cv_mean': round(float(np.mean([f['accuracy'] for f in cv_folds])), 2),
        'importances': importances,
        'performance': performance,
        'features': feature_snapshot,
        'n_samples': int(len(X)),
        'history_days': int((train_df['timestamp'].iloc[-1] - train_df['timestamp'].iloc[0]).days),
        'first_date': train_df['timestamp'].iloc[0].strftime('%Y-%m-%d'),
        'predict_for_date': predict_for,
        'scoreboard': scoreboard,
        'trades': recent_trades,
        'quant_score': quant['quant_score'],
        'quant_label': quant['quant_label'],
        'quant_breakdown': quant['quant_breakdown'],
        'regime': quant['regime'],
        'forecasts': quant['forecasts'],
        'long_outlook': quant.get('long_outlook', []),
        'factors': quant['factors'],
        'decision': decision,
        'risk': risk,
        'chart': chart,
        'market_intel': market_intel,
        'alerts': alerts,
        # BTC-only engines (hidden for altcoins in UI)
        'live_record': None, 'news_forecast_link': None, 'data_health': None,
        'event_calendar': None, 'smart_money': None, 'institutional': institutional,
        'prediction_ledger': None, 'bitmark': None, 'cycle': None, 'dominance': dominance,
        'crossmarket': None, 'policy': None, 'smart_alerts': [],
    }
    return doc


def run_coin_dash_bg(symbol):
    with _coin_dash_lock:
        if _coin_dash_state.get(symbol) == 'running':
            return
        _coin_dash_state[symbol] = 'running'
    try:
        data = compute_coin_dashboard(symbol)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        coin_dash_col.update_one({'_id': cache_id},
                                 {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today, 'data': data,
                                           'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        _coin_dash_state[symbol] = 'done'
    except Exception:  # noqa
        _coin_dash_state[symbol] = 'error'
        traceback.print_exc()


# =====================================================================
# PER-COIN NEWS (altcoins) — same RSS + clustering + Gemini pipeline,
# coin-keyword filtered, cached per coin/day, isolated from BTC news.
# =====================================================================
COIN_NEWS_TERMS = {
    'ETH': ['ethereum', 'ether', 'vitalik', 'layer 2', 'staking', 'erc-20'],
    'SOL': ['solana'],
    'XRP': ['xrp', 'ripple'],
    'ADA': ['cardano'],
    'DOGE': ['dogecoin', 'doge'],
    'AVAX': ['avalanche', 'avax'],
    'LINK': ['chainlink'],
    'DOT': ['polkadot'],
    'LTC': ['litecoin'],
    'MATIC': ['polygon', 'matic'],
    'ATOM': ['cosmos'],
}
COIN_NEWS_SHARED = ['sec', 'etf', 'regulation', 'federal reserve', 'interest rate',
                    'rate cut', 'rate hike', 'inflation', 'cpi', 'stablecoin', 'coinbase',
                    'binance', 'blackrock', 'custody', 'fomc']

_coin_news_state = {}          # symbol -> 'running' | 'done' | 'error'
_coin_news_lock = threading.Lock()


def generate_coin_news_summary(name, headline, text):
    sysmsg = NEWS_SYSTEM.replace('Bitcoin', name)
    chat = (LlmChat(api_key=LLM_READY_KEY, session_id=f'coinnews-{abs(hash(headline)) % 99999}',
                    system_message=sysmsg)
            .with_model('gemini', _model_for('news'))
            .with_params(temperature=0.0, max_tokens=1200))
    reply = asyncio.run(chat.send_message(UserMessage(text=f'Headline: {headline}\n\nArticle:\n{text[:4000]}')))
    raw = (getattr(reply, 'text', None) or str(reply)).strip()
    if '```' in raw:
        raw = re.sub(r'```(?:json)?', '', raw).strip()
    s, e = raw.find('{'), raw.rfind('}')
    obj = json.loads(raw[s:e + 1])
    return obj


def build_coin_news(symbol):
    cfg = COMPARE_COINS[symbol]
    name = cfg['name']
    terms = [name.lower(), symbol.lower()] + COIN_NEWS_TERMS.get(symbol, [])
    match_terms = list(dict.fromkeys(terms + COIN_NEWS_SHARED))

    entries = []
    for sname, url, cred in NEWS_SOURCES:
        try:
            fp = feedparser.parse(url)
            for e in fp.entries[:14]:
                title = e.get('title', '')
                summ = re.sub('<[^>]+>', '', e.get('summary', e.get('description', '')))[:1400]
                blob = (title + ' ' + summ).lower()
                # keep coin-specific stories, plus macro stories from the Fed feed
                if not any(k in blob for k in terms) and not (sname == 'Federal Reserve'):
                    if not any(k in blob for k in match_terms):
                        continue
                entries.append({'source': sname, 'credibility': cred, 'title': title,
                                'summary': summ.strip(), 'link': e.get('link', ''),
                                'published': e.get('published', e.get('updated', ''))})
        except Exception:  # noqa
            traceback.print_exc()

    def _toks(t):
        stop = {'the', 'a', 'an', 'to', 'of', 'in', 'on', 'for', 'and', 'is', 'as', 'at',
                'by', 'it', 'be', 'with', 'from', 'that', 'this', 'its', 'are', 'will', 'has'}
        return set(w for w in re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower()).split()
                   if len(w) > 2 and w not in stop)

    clusters = []
    for e in entries:
        et = _toks(e['title'])
        if not et:
            continue
        placed = False
        for cl in clusters:
            inter = len(et & cl['tokens'])
            union = len(et | cl['tokens']) or 1
            if inter / union >= 0.34 or (inter >= 3 and inter >= 0.6 * min(len(et), len(cl['tokens']))):
                cl['members'].append(e)
                cl['tokens'] |= et
                placed = True
                break
        if not placed:
            clusters.append({'tokens': set(et), 'members': [e]})
    clusters.sort(key=lambda cl: (-len(set(m['source'] for m in cl['members'])),
                                  -max(m['credibility'] for m in cl['members'])))
    clusters = clusters[:6]

    SPEC_WORDS = ('rumor', 'rumour', 'reportedly', 'could ', 'may ', 'might', 'proposal',
                  'proposed', 'unconfirmed', 'alleged', 'speculat', 'plans to', 'considering',
                  'reports', 'said to', 'expected to')
    cards = []
    for cl in clusters:
        members = cl['members']
        rep = max(members, key=lambda m: m['credibility'])
        sources = [{'source': m['source'], 'link': m['link'], 'credibility': m['credibility'],
                    'published': m['published'], 'title': m['title']} for m in members]
        n_src = len(set(m['source'] for m in members))
        ai = None
        if LLM_READY_KEY and _HAS_LLM:
            try:
                ai = generate_coin_news_summary(name, rep['title'], rep['summary'] or rep['title'])
            except Exception:  # noqa
                traceback.print_exc()
        if not ai:
            ai = {'summary': (rep['summary'] or rep['title'])[:220], 'why_it_matters': '',
                  'direction': 'neutral', 'bullish_pct': 40, 'bearish_pct': 30, 'neutral_pct': 30,
                  'impact_score': 40, 'confidence': 0.4,
                  'time_horizons': {'immediate': 'neutral', 'seven_day': 'neutral', 'long_term': 'neutral'},
                  'categories': ['general']}
        try:
            imp = int(round(float(ai.get('impact_score', 40)) * (0.55 + 0.45 * rep['credibility'] / 100)))
        except Exception:  # noqa
            imp = 40
        imp = max(0, min(100, imp))
        imp_label = ('Market Moving' if imp >= 85 else 'High Impact' if imp >= 70 else 'Important'
                     if imp >= 50 else 'Monitor' if imp >= 30 else 'Low Significance')
        blob = (rep['title'] + ' ' + (rep['summary'] or '')).lower()
        speculative = any(w in blob for w in SPEC_WORDS)
        max_cred = max(m['credibility'] for m in members)
        if n_src >= 2 and max_cred >= 65 and not speculative:
            verification = 'Confirmed'
        elif speculative or max_cred < 55:
            verification = 'Unconfirmed'
        else:
            verification = 'Single-source'
        dirn = ai.get('direction', 'neutral')
        sign = 1 if dirn == 'bullish' else -1 if dirn == 'bearish' else 0
        nudge = round(sign * imp / 100 * 3.0, 1)
        forecast_impact = {
            'direction': dirn, 'nudge_pts': nudge,
            'horizons': ['24H', '7D'] if imp >= 50 else ['24H'],
            'note': (f'Nudges near-term higher-odds by {"+" if nudge > 0 else ""}{nudge} pts'
                     if nudge else 'No material push to the near-term odds') + ' (model interpretation).',
        }
        cards.append({**rep, 'ai': ai, 'impact': imp, 'impact_label': imp_label,
                      'sources': sources, 'n_sources': n_src,
                      'verification': verification, 'forecast_impact': forecast_impact})
    cards.sort(key=lambda c: -c['impact'])

    bull = sum(1 for c in cards if c['ai'].get('direction') == 'bullish')
    bear = sum(1 for c in cards if c['ai'].get('direction') == 'bearish')
    bias = 'Moderately Bullish' if bull > bear else 'Moderately Bearish' if bear > bull else 'Mixed / Neutral'
    tail = next((c for c in cards if c['ai'].get('direction') == 'bullish'), None)
    risk = next((c for c in cards if c['ai'].get('direction') == 'bearish'), None)
    briefing = {
        'bias': bias, 'total': len(cards),
        'major_stories': sum(1 for c in cards if c['impact'] >= 70),
        'market_moving': sum(1 for c in cards if c['impact'] >= 85),
        'top_tailwind': (tail['ai'].get('why_it_matters') or tail['title']) if tail else f'No clear {name} tailwind in the current feed.',
        'top_risk': (risk['ai'].get('why_it_matters') or risk['title']) if risk else f'No clear {name} risk in the current feed.',
        'next_event': None,
    }
    doc = {'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
           'symbol': symbol, 'coin_name': name, 'cards': cards, 'briefing': briefing,
           'model': (GEMINI_MODEL if (LLM_READY_KEY and _HAS_LLM) else 'rule-based')}
    return doc


def run_coin_news_bg(symbol):
    with _coin_news_lock:
        if _coin_news_state.get(symbol) == 'running':
            return
        _coin_news_state[symbol] = 'running'
    try:
        doc = build_coin_news(symbol)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{today}'
        coin_news_col.update_one({'_id': cache_id},
                                 {'$set': {'_id': cache_id, 'symbol': symbol, 'day': today,
                                           'doc': doc, 'created_at': datetime.datetime.utcnow().isoformat()}},
                                 upsert=True)
        _coin_news_state[symbol] = 'done'
    except Exception:  # noqa
        _coin_news_state[symbol] = 'error'
        traceback.print_exc()



# =====================================================================
# CROSS-MARKET — selected coin vs traditional markets (keyless, Yahoo Finance).
# =====================================================================
MARKET_INDICES = [
    ('S&P 500', '%5EGSPC'),
    ('Nasdaq 100', '%5ENDX'),
    ('Dow Jones', '%5EDJI'),
    ('Nikkei 225', '%5EN225'),
    ('Euro Stoxx 50', '%5ESTOXX50E'),
    ('FTSE 100', '%5EFTSE'),
    ('DAX', '%5EGDAXI'),
    ('Gold', 'GC=F'),
    ('US Dollar (DXY)', 'DX-Y.NYB'),
]
MARKET_WINDOWS = {'1m': 30, '3m': 91, '6m': 182, 'ytd': None, '1y': 365}
_markets_state = {}
_markets_lock = threading.Lock()


def _yahoo_coin_ticker(symbol):
    return 'BTC-USD' if symbol == 'BTC' else f'{symbol}-USD'


def _ret_over(s, days):
    if s is None or len(s) < 2:
        return None
    last = s.index[-1]
    target = (pd.to_datetime(last) - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
    prior = s[s.index <= target]
    if len(prior) == 0:
        return None
    base = float(prior.iloc[-1])
    if base == 0:
        return None
    return round((float(s.iloc[-1]) / base - 1) * 100, 2)


def _ret_ytd(s):
    if s is None or len(s) < 2:
        return None
    yr = s.index[-1][:4]
    ys = s[s.index >= f'{yr}-01-01']
    if len(ys) < 2:
        return None
    base = float(ys.iloc[0])
    if base == 0:
        return None
    return round((float(s.iloc[-1]) / base - 1) * 100, 2)


def _annual_vol(s, periods_per_year):
    if s is None or len(s) < 20:
        return None
    r = np.log(s / s.shift(1)).dropna().tail(90)
    if len(r) < 10:
        return None
    return round(float(r.std()) * (periods_per_year ** 0.5) * 100, 1)


def compute_markets(symbol, window):
    window = window if window in MARKET_WINDOWS else '1y'
    cfg = COMPARE_COINS.get(symbol, {'name': symbol})
    coin_name = cfg['name']
    coin_s = fetch_yahoo_series(_yahoo_coin_ticker(symbol), '1y')
    coin_ret = np.log(coin_s / coin_s.shift(1))

    raw = {coin_name: coin_s}
    corr_rows = []
    for name, sym in MARKET_INDICES:
        try:
            s = fetch_yahoo_series(sym, '1y')
            raw[name] = s
            r = np.log(s / s.shift(1))
            j = pd.concat([coin_ret, r], axis=1, keys=['b', 'a']).dropna()

            def corr(n):
                x = j.tail(n)
                return round(float(x['b'].corr(x['a'])), 2) if len(x) > 3 else None
            c30 = corr(30)
            beta = None
            x = j.tail(30)
            if len(x) > 3 and x['a'].var() > 0:
                beta = round(float(x['b'].cov(x['a']) / x['a'].var()), 2)
            ar = abs(c30 or 0)
            lab = ('Strong' if ar > 0.6 else 'Moderate' if ar > 0.3 else 'Weak') + (' Positive' if (c30 or 0) >= 0 else ' Negative')
            corr_rows.append({'asset': name, 'corr_30d': c30, 'corr_90d': corr(90), 'beta_30d': beta, 'label': lab})
        except Exception:  # noqa
            traceback.print_exc()

    # returns + volatility table (coin first)
    table = []
    order = [coin_name] + [n for n, _ in MARKET_INDICES]
    for name in order:
        s = raw.get(name)
        if s is None or len(s) < 2:
            continue
        is_coin = (name == coin_name)
        table.append({
            'asset': name, 'is_coin': is_coin,
            'price': round(float(s.iloc[-1]), 2),
            'ret_1w': _ret_over(s, 7), 'ret_1m': _ret_over(s, 30), 'ret_3m': _ret_over(s, 91),
            'ret_6m': _ret_over(s, 182), 'ret_1y': _ret_over(s, 365), 'ret_ytd': _ret_ytd(s),
            'vol_annual': _annual_vol(s, 365 if is_coin else 252),
        })

    # rebased performance chart over the selected window, aligned to coin (continuous) dates
    df = pd.DataFrame(raw).sort_index().ffill()
    last = df.index[-1]
    if window == 'ytd':
        start = f'{last[:4]}-01-01'
        df = df[df.index >= start]
    else:
        days = MARKET_WINDOWS[window]
        start = (pd.to_datetime(last) - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
        df = df[df.index >= start]
    df = df.dropna(how='all')
    series = []
    if len(df) > 0:
        base = df.bfill().iloc[0]
        # downsample to ~120 points max for a light chart
        stepn = max(1, len(df) // 120)
        for i, (dt, row) in enumerate(df.iterrows()):
            if i % stepn != 0 and i != len(df) - 1:
                continue
            pt = {'date': dt}
            for name in order:
                if name in df.columns and pd.notna(row[name]) and pd.notna(base.get(name)) and base[name]:
                    pt[name] = round(float(row[name]) / float(base[name]) * 100, 2)
            series.append(pt)

    # best / worst by the selected-window return
    win_key = {'1m': 'ret_1m', '3m': 'ret_3m', '6m': 'ret_6m', 'ytd': 'ret_ytd', '1y': 'ret_1y'}[window]
    ranked = [t for t in table if t.get(win_key) is not None]
    ranked.sort(key=lambda t: -t[win_key])
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None
    coin_rank = next((i + 1 for i, t in enumerate(ranked) if t['is_coin']), None)

    # rolling 30-day correlation trend vs each benchmark (picker switches instantly, no refetch)
    corr_trend_map = {}
    for name in [n for n, _ in MARKET_INDICES]:
        s = raw.get(name)
        if s is None:
            continue
        try:
            r = np.log(s / s.shift(1))
            j = pd.concat([coin_ret, r], axis=1, keys=['b', 'a']).dropna()
            roll = j['b'].rolling(30).corr(j['a']).dropna().tail(180)
            pts = [{'date': idx, 'corr': round(float(v), 2)} for idx, v in roll.items() if pd.notna(v)]
            if len(pts) > 1:
                corr_trend_map[name] = pts
        except Exception:  # noqa
            traceback.print_exc()
    corr_trend = corr_trend_map.get('S&P 500', [])

    return {
        'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
        'symbol': symbol, 'coin_name': coin_name, 'window': window,
        'as_of': last, 'assets': order,
        'series': series, 'table': table, 'correlations': corr_rows,
        'corr_trend': corr_trend, 'corr_benchmark': 'S&P 500',
        'corr_trend_map': corr_trend_map, 'corr_benchmarks': list(corr_trend_map.keys()),
        'best': best, 'worst': worst, 'coin_rank': coin_rank, 'ranked_count': len(ranked),
    }


def run_markets_bg(symbol, window):
    key = f'{symbol}:{window}'
    with _markets_lock:
        if _markets_state.get(key) == 'running':
            return
        _markets_state[key] = 'running'
    try:
        data = compute_markets(symbol, window)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        cache_id = f'{symbol}:{window}:{today}'
        markets_col.update_one({'_id': cache_id},
                               {'$set': {'_id': cache_id, 'symbol': symbol, 'window': window, 'day': today,
                                         'data': data, 'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        _markets_state[key] = 'done'
    except Exception:  # noqa
        _markets_state[key] = 'error'
        traceback.print_exc()


@app.get('/api/v1/markets')
def markets(symbol: str = 'BTC', window: str = '1y'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    window = window if window in MARKET_WINDOWS else '1y'
    if symbol != 'BTC' and symbol not in COMPARE_COINS:
        return {'status': 'error', 'error': 'unsupported_symbol'}
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    cache_id = f'{symbol}:{window}:{today}'
    cached = markets_col.find_one({'_id': cache_id}, {'_id': 0})
    if cached and cached.get('data'):
        return {'status': 'ready', **cached['data']}
    st = _markets_state.get(f'{symbol}:{window}')
    if st != 'running':
        threading.Thread(target=run_markets_bg, args=(symbol, window), daemon=True).start()
    if st == 'error':
        return {'status': 'error', 'error': 'compute_failed'}
    return {'status': 'computing'}



# =====================================================================
# HAPPENING AGAIN — historical-analog engine (Bitcoin). Auto-detects past
# trend episodes, builds a condition "fingerprint" for each, and matches
# today's conditions against them. Keyless (Yahoo Finance). Cached daily.
# =====================================================================
HALVING_DATES = ['2012-11-28', '2016-07-09', '2020-05-11', '2024-04-20']
CURATED_EVENTS = [
    {'date': '2017-12-17', 'label': '2017 cycle top / futures launch', 'cat': 'Events'},
    {'date': '2020-03-12', 'label': 'COVID crash', 'cat': 'Events'},
    {'date': '2020-05-11', 'label': '3rd halving', 'cat': 'On-chain'},
    {'date': '2021-04-14', 'label': 'Coinbase IPO / cycle top area', 'cat': 'Events'},
    {'date': '2021-11-10', 'label': '2021 all-time high', 'cat': 'Market structure'},
    {'date': '2022-05-09', 'label': 'Terra/LUNA collapse', 'cat': 'Events'},
    {'date': '2022-11-08', 'label': 'FTX collapse', 'cat': 'Events'},
    {'date': '2023-03-10', 'label': 'US bank failures / SVB', 'cat': 'Macro'},
    {'date': '2024-01-11', 'label': 'US spot ETFs approved', 'cat': 'Events'},
    {'date': '2024-04-20', 'label': '4th halving', 'cat': 'On-chain'},
]
ANALOG_SIGNALS = [
    {'key': 'rates_dir', 'label': 'Rates trend (10Y, 90d chg)', 'cat': 'Macro', 'unit': 'pts', 'good_high': False},
    {'key': 'dxy_dir', 'label': 'US Dollar trend (90d %)', 'cat': 'Macro', 'unit': '%', 'good_high': False},
    {'key': 'nasdaq_corr', 'label': 'BTC–Nasdaq correlation (30d)', 'cat': 'Market structure', 'unit': '', 'good_high': None},
    {'key': 'gold_corr', 'label': 'BTC–Gold correlation (30d)', 'cat': 'Market structure', 'unit': '', 'good_high': None},
    {'key': 'vol_regime', 'label': 'Volatility (30d annualized)', 'cat': 'Market structure', 'unit': '%', 'good_high': None},
    {'key': 'drawdown', 'label': 'Drawdown from ATH', 'cat': 'Market structure', 'unit': '%', 'good_high': None},
    {'key': 'momentum', 'label': 'Momentum (90d return)', 'cat': 'Market structure', 'unit': '%', 'good_high': True},
    {'key': 'cycle', 'label': 'Months since halving', 'cat': 'On-chain', 'unit': 'mo', 'good_high': None},
]
ANALOG_KEYS = [s['key'] for s in ANALOG_SIGNALS]
ANALOG_COINS = {  # symbol -> Yahoo ticker for the Happening Again engine
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD', 'XRP': 'XRP-USD',
    'ADA': 'ADA-USD', 'DOGE': 'DOGE-USD', 'AVAX': 'AVAX-USD', 'LINK': 'LINK-USD',
    'DOT': 'DOT-USD', 'LTC': 'LTC-USD', 'ATOM': 'ATOM-USD', 'MATIC': 'MATIC-USD',
}


def analog_signals(sym):
    """Signal definitions for a given coin. Cycle (months since halving) is BTC-only."""
    s = [
        {'key': 'rates_dir', 'label': 'Rates trend (10Y, 90d chg)', 'cat': 'Macro', 'unit': 'pts', 'good_high': False},
        {'key': 'dxy_dir', 'label': 'US Dollar trend (90d %)', 'cat': 'Macro', 'unit': '%', 'good_high': False},
        {'key': 'nasdaq_corr', 'label': f'{sym}–Nasdaq correlation (30d)', 'cat': 'Market structure', 'unit': '', 'good_high': None},
        {'key': 'gold_corr', 'label': f'{sym}–Gold correlation (30d)', 'cat': 'Market structure', 'unit': '', 'good_high': None},
        {'key': 'vol_regime', 'label': 'Volatility (30d annualized)', 'cat': 'Market structure', 'unit': '%', 'good_high': None},
        {'key': 'drawdown', 'label': 'Drawdown from ATH', 'cat': 'Market structure', 'unit': '%', 'good_high': None},
        {'key': 'momentum', 'label': 'Momentum (90d return)', 'cat': 'Market structure', 'unit': '%', 'good_high': True},
    ]
    if sym == 'BTC':
        s.append({'key': 'cycle', 'label': 'Months since halving', 'cat': 'On-chain', 'unit': 'mo', 'good_high': None})
    return s


_analogs_state = {}  # per-symbol status
_analogs_lock = threading.Lock()


def _months_since_halving(d):
    dd = pd.to_datetime(d)
    prev = [h for h in HALVING_DATES if pd.to_datetime(h) <= dd]
    if not prev:
        return None
    return round((dd - pd.to_datetime(prev[-1])).days / 30.44, 1)


def _zigzag(dates, v, pct=0.3):
    piv = []
    trend = 0
    hi_i = lo_i = 0
    for i in range(1, len(v)):
        if v[i] > v[hi_i]:
            hi_i = i
        if v[i] < v[lo_i]:
            lo_i = i
        if trend >= 0 and v[i] <= v[hi_i] * (1 - pct):
            piv.append((dates[hi_i], v[hi_i], 'peak'))
            trend = -1
            lo_i = i
        elif trend <= 0 and v[i] >= v[lo_i] * (1 + pct):
            piv.append((dates[lo_i], v[lo_i], 'trough'))
            trend = 1
            hi_i = i
    return piv


def compute_analogs(symbol='BTC'):
    symbol = (symbol or 'BTC').upper()
    signals = analog_signals(symbol)
    keys = [s['key'] for s in signals]
    ticker = ANALOG_COINS.get(symbol, f'{symbol}-USD')
    btc = fetch_yahoo_series(ticker, '10y')
    ndx = fetch_yahoo_series('%5ENDX', '10y')
    gold = fetch_yahoo_series('GC=F', '10y')
    dxy = fetch_yahoo_series('DX-Y.NYB', '10y')
    tnx = fetch_yahoo_series('%5ETNX', '10y')
    df = pd.DataFrame({'btc': btc}).sort_index()
    df = df[df['btc'] > 0]
    if len(df) < 250:
        return {
            'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
            'symbol': symbol, 'as_of': (list(df.index)[-1] if len(df) else None),
            'history_from': (list(df.index)[0] if len(df) else None),
            'signals': signals, 'norm': {}, 'current': {}, 'episodes': [], 'episode_count': 0,
            'current_path': [], 'day_fingerprints': [], 'insufficient_history': True,
        }
    ret = np.log(df['btc'] / df['btc'].shift(1))

    def align(s):
        return s.reindex(df.index).ffill()
    ndx_r = np.log(align(ndx) / align(ndx).shift(1))
    gold_r = np.log(align(gold) / align(gold).shift(1))
    tnx_a = align(tnx)
    dxy_a = align(dxy)
    df['rates_dir'] = (tnx_a - tnx_a.shift(90)).round(2)
    df['dxy_dir'] = ((dxy_a / dxy_a.shift(90) - 1) * 100).round(2)
    df['nasdaq_corr'] = ret.rolling(30).corr(ndx_r).round(2)
    df['gold_corr'] = ret.rolling(30).corr(gold_r).round(2)
    df['vol_regime'] = (ret.rolling(30).std() * (365 ** 0.5) * 100).round(1)
    df['drawdown'] = ((df['btc'] / df['btc'].cummax() - 1) * 100).round(1)
    df['momentum'] = ((df['btc'] / df['btc'].shift(90) - 1) * 100).round(1)
    if symbol == 'BTC':
        df['cycle'] = [(_months_since_halving(d) or 0) for d in df.index]

    # normalization stats across history
    norm = {}
    for k in keys:
        col = df[k].dropna()
        norm[k] = {'mean': round(float(col.mean()), 3), 'std': round(float(col.std()) or 1.0, 3)}

    def fp_at(date):
        try:
            row = df.loc[date]
        except Exception:  # noqa
            sub = df[df.index <= date]
            if len(sub) == 0:
                return None
            row = sub.iloc[-1]
        return {k: (None if pd.isna(row[k]) else round(float(row[k]), 2)) for k in keys}

    def fwd_ret(start, days):
        target = (pd.to_datetime(start) + pd.Timedelta(days=days)).strftime('%Y-%m-%d')
        after = df[df.index >= target]
        base = df[df.index <= start]
        if len(after) == 0 or len(base) == 0:
            return None
        return round((float(after['btc'].iloc[0]) / float(base['btc'].iloc[-1]) - 1) * 100, 1)

    dates = list(df.index)
    vals = [float(x) for x in df['btc'].values]

    def path_for(start, base_price, lo=-60, hi=180, step=3):
        pts = []
        sd = pd.to_datetime(start)
        for off in range(lo, hi + 1, step):
            td = (sd + pd.Timedelta(days=off)).strftime('%Y-%m-%d')
            if td > dates[-1]:
                break
            sub = df[df.index <= td]
            if len(sub) == 0:
                continue
            pts.append({'off': off, 'v': round(float(sub['btc'].iloc[-1]) / base_price * 100, 1)})
        return pts

    pivots = _zigzag(dates, vals, 0.30)
    episodes = []
    for k in range(len(pivots) - 1):
        (d0, p0, t0) = pivots[k]
        (d1, p1, t1) = pivots[k + 1]
        move = round((p1 / p0 - 1) * 100, 1)
        if abs(move) < 30:
            continue
        up = move > 0
        fp = fp_at(d0)
        if not fp:
            continue
        tags = [e for e in CURATED_EVENTS if d0 <= e['date'] <= d1]
        dur = (pd.to_datetime(d1) - pd.to_datetime(d0)).days
        episodes.append({
            'id': str(uuid.uuid4())[:8],
            'label': f"{d0[:4]} {'rally' if up else 'drawdown'} {move:+.0f}%",
            'type': 'rally' if up else 'drawdown',
            'start': d0, 'end': d1, 'start_price': round(p0, 2), 'end_price': round(p1, 2),
            'move_pct': move, 'duration_days': dur,
            'fingerprint': fp, 'tags': tags,
            'fwd_30': fwd_ret(d0, 30), 'fwd_90': fwd_ret(d0, 90), 'fwd_180': fwd_ret(d0, 180),
            'path': path_for(d0, p0),
        })

    today_price = float(df['btc'].iloc[-1])
    current_path = []
    for off in range(-60, 1, 3):
        td = (pd.to_datetime(dates[-1]) + pd.Timedelta(days=off)).strftime('%Y-%m-%d')
        sub = df[df.index <= td]
        if len(sub) == 0:
            continue
        current_path.append({'off': off, 'v': round(float(sub['btc'].iloc[-1]) / today_price * 100, 1)})

    current = {k: (None if pd.isna(df[k].iloc[-1]) else round(float(df[k].iloc[-1]), 2)) for k in keys}

    def match_score(fp, weights=None):
        tot = 0.0
        wsum = 0.0
        for s in signals:
            k = s['key']
            w = (weights or {}).get(k, 1.0)
            a = fp.get(k)
            b = current.get(k)
            if a is None or b is None:
                continue
            std = norm[k]['std'] or 1.0
            tot += w * ((a - b) / std) ** 2
            wsum += w
        if wsum == 0:
            return 0
        dist = (tot / wsum) ** 0.5
        return round(100.0 / (1.0 + dist), 0)

    for ep in episodes:
        ep['match'] = match_score(ep['fingerprint'])
    ranked = sorted(episodes, key=lambda e: -e['match'])

    # attach a forward price path to every episode so the frontend can overlay the top 2-3
    for ep in ranked:
        if not ep.get('path'):
            ep['path'] = path_for(ep['start'], ep['start_price'])

    # Setup History source: downsampled RESOLVED historical days (need >=90d forward outcome),
    # each with its fingerprint + forward returns. The frontend scores every day against today's
    # setup using the live slider weights and lists all days above the alert threshold with their
    # win/loss outcome — a mini backtest of how the current setup has played out in the past.
    # We also attach a coarse forward price path (rebased to 100 at day 0) so the frontend can
    # build a percentile "confidence band" showing the spread of past outcomes.
    fwd_offsets = list(range(0, 181, 12))
    _date_ts = pd.to_datetime(pd.Index(dates)).values  # sorted ascending datetime64[ns]
    _prices = np.array(vals, dtype=float)
    _last_ts = _date_ts[-1]

    def fwd_path_arr(i):
        base = _prices[i]
        if base <= 0:
            return []
        out = []
        for off in fwd_offsets:
            target = _date_ts[i] + np.timedelta64(int(off), 'D')
            if target > _last_ts:
                out.append({'off': int(off), 'v': None})
                continue
            j = int(np.searchsorted(_date_ts, target, side='right')) - 1
            if j < i:
                j = i
            out.append({'off': int(off), 'v': round(float(_prices[j]) / base * 100, 1)})
        return out

    day_fingerprints = []
    last_dt = pd.to_datetime(dates[-1])
    for i in range(0, len(df), 3):
        d = dates[i]
        if (last_dt - pd.to_datetime(d)).days < 95:
            continue
        fp = {k: (None if pd.isna(df[k].iloc[i]) else round(float(df[k].iloc[i]), 2)) for k in keys}
        if sum(1 for k in keys if fp[k] is not None) < 5:
            continue
        day_fingerprints.append({
            'date': d, 'fp': fp,
            'fwd_30': fwd_ret(d, 30), 'fwd_90': fwd_ret(d, 90), 'fwd_180': fwd_ret(d, 180),
            'fwd_path': fwd_path_arr(i),
        })

    return {
        'id': str(uuid.uuid4()), 'created_at': datetime.datetime.utcnow().isoformat(),
        'symbol': symbol, 'as_of': dates[-1], 'history_from': dates[0],
        'signals': signals, 'norm': norm,
        'current': current, 'episodes': ranked, 'episode_count': len(ranked),
        'current_path': current_path, 'day_fingerprints': day_fingerprints,
    }


def run_analogs_bg(symbol='BTC'):
    symbol = (symbol or 'BTC').upper()
    with _analogs_lock:
        if _analogs_state.get(symbol) == 'running':
            return
        _analogs_state[symbol] = 'running'
    try:
        data = compute_analogs(symbol)
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        key = f'{today}_{symbol}'
        analogs_col.update_one({'_id': key}, {'$set': {'_id': key, 'day': today, 'symbol': symbol, 'data': data,
                               'created_at': datetime.datetime.utcnow().isoformat()}}, upsert=True)
        # Auto-alert: ping the bell once/day when the strongest analog crosses a high threshold.
        try:
            top = (data.get('episodes') or [None])[0]
            if top and top.get('match', 0) >= 70:
                now_iso = datetime.datetime.utcnow().isoformat()
                sev = 'high' if top['match'] >= 80 else 'warning'
                aid = f"analog_{today}_{symbol}_{top['id']}"
                smart_alerts_col.update_one(
                    {'_id': aid},
                    {'$setOnInsert': {
                        '_id': aid, 'id': aid, 'symbol': symbol,
                        'ts': now_iso, 'as_of': data.get('as_of'), 'category': 'Setup', 'severity': sev,
                        'title': f"Strong {symbol} setup forming ({top['match']}% match)",
                        'message': f"Today's {symbol} conditions closely resemble {top['label']} ({top['start']}→{top['end']}), which then moved {top.get('fwd_90')}% over 90 days. Educational pattern-match, not a prediction.",
                        'seen': False, 'impact': int(top['match']),
                    }}, upsert=True)
        except Exception:  # noqa
            traceback.print_exc()
        _analogs_state[symbol] = 'done'
    except Exception:  # noqa
        _analogs_state[symbol] = 'error'
        traceback.print_exc()


@app.get('/api/v1/analogs')
def analogs(symbol: str = 'BTC'):
    symbol = (symbol or 'BTC').strip().upper()[:6]
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    cached = analogs_col.find_one({'_id': f'{today}_{symbol}'}, {'_id': 0})
    if cached and cached.get('data'):
        return {'status': 'ready', **cached['data']}
    if _analogs_state.get(symbol) != 'running':
        threading.Thread(target=run_analogs_bg, args=(symbol,), daemon=True).start()
    if _analogs_state.get(symbol) == 'error':
        return {'status': 'error', 'error': 'compute_failed'}
    return {'status': 'computing'}



# ---- Wire the extracted Albert engine (albert/ package) with runtime helpers ----
# Done at the very end of module import so every helper below is already defined.
_albert_deps.configure(
    daily_ohlcv=_daily_ohlcv,
    spot_price=_spot_price,
    sector_strength=_sector_strength,
    num=_num,
    portfolio_summary=_portfolio_summary,
    get_mandate=_get_mandate,
    mandate_complete=_mandate_complete,
)

