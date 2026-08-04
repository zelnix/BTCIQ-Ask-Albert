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
import uuid
import math
import threading
import datetime
import traceback

import ccxt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv('/app/.env')

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'your_database_name')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
runs_col = db['btc_runs']
signals_col = db['live_signals']

# in-memory ticker cache (avoid hammering the exchange on every poll)
_ticker_cache = {'data': None, 'ts': 0.0}


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

_state = {'status': 'idle', 'error': None, 'started_at': None}
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


def _horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts):
    """Train a horizon-specific RandomForest and project bull/base/bear ranges."""
    n = len(Xfull)
    y_h = (close.shift(-h) > close).astype(int)
    Xv = Xfull.iloc[:n - h]
    yv = y_h.iloc[:n - h]
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
    # final model -> live probability
    fm = RandomForestClassifier(n_estimators=150, max_depth=5, random_state=42, n_jobs=-1)
    fm.fit(Xv, yv)
    cl = list(fm.classes_)
    pr = fm.predict_proba(live_X)[0]
    p_up = float(pr[cl.index(1)]) if 1 in cl else 0.0
    higher = round(p_up * 100, 1)
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
    label = {1: '24H', 7: '7D', 30: '30D'}.get(h, f'{h}D')
    return {
        'horizon': label, 'days': h,
        'higher': higher, 'lower': lower,
        'expected_low': round(exp_low, 0), 'expected_high': round(exp_high, 0),
        'bull': round(bull, 0), 'base': round(base, 0), 'bear': round(bear, 0),
        'confidence': conf_label, 'confidence_pct': round(conf_val * 100, 0),
        'accuracy': round(acc * 100, 1),
        'invalidation': round(invalidation, 0),
        'invalidation_dir': 'below' if bullish_lean else 'above',
        'lean': 'UP' if bullish_lean else 'DOWN',
        'expiry': (as_of_ts + pd.Timedelta(days=h)).strftime('%Y-%m-%d'),
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
    Xfull = df[FEATURE_COLS]
    live_X = Xfull.iloc[[-1]]
    forecasts = []
    for h in [1, 7, 30]:
        try:
            forecasts.append(_horizon_forecast(Xfull, close, live_X, h, price, mu, sigma, as_of_ts))
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
        'factors': {'bullish': bulls, 'risk': risks},
    }



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
        'factors': quant['factors'],
    }

    to_store = dict(doc)
    to_store['_id'] = doc['id']
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
    try:
        scheduler = BackgroundScheduler(timezone='UTC')
        scheduler.add_job(run_compute_bg, 'cron', hour=0, minute=5, id='daily_refresh')
        scheduler.start()
    except Exception:  # noqa
        traceback.print_exc()
    if runs_col.count_documents({}) == 0:
        threading.Thread(target=run_compute_bg, daemon=True).start()


@app.get('/api/v1/health')
def health():
    return {'status': 'ok', 'compute_status': _state['status'], 'error': _state['error'],
            'runs': runs_col.count_documents({})}


@app.get('/api/v1/ticker')
def ticker():
    import time
    now = time.time()
    if _ticker_cache['data'] and (now - _ticker_cache['ts']) < 8:
        return _ticker_cache['data']
    for name in ['kraken', 'coinbase']:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            t = ex.fetch_ticker('BTC/USD')
            last = float(t['last'])
            pct = t.get('percentage')
            if pct is None and t.get('open'):
                pct = (last - float(t['open'])) / float(t['open']) * 100
            data = {
                'price': round(last, 2),
                'change24h': round(float(pct), 2) if pct is not None else 0.0,
                'high': round(float(t.get('high') or last), 2),
                'low': round(float(t.get('low') or last), 2),
                'source': name,
                'ts': datetime.datetime.utcnow().isoformat(),
            }
            _ticker_cache['data'] = data
            _ticker_cache['ts'] = now
            return data
        except Exception:  # noqa
            continue
    return {'price': None, 'error': 'ticker unavailable'}


@app.get('/api/v1/dashboard')
def dashboard():
    doc = runs_col.find_one(sort=[('created_at', -1)], projection={'_id': 0})
    if not doc:
        st = _state['status']
        return {'status': 'error' if st == 'error' else 'computing', 'error': _state['error']}
    return {'status': 'ready', 'compute_status': _state['status'], **doc}


@app.post('/api/v1/refresh')
def refresh():
    threading.Thread(target=run_compute_bg, daemon=True).start()
    return {'status': 'started'}
