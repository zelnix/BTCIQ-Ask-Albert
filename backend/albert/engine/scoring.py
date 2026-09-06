"""Transparent 0-100 opportunity score + confidence.

Exact port of server.py `_score_asset` / `_rsi` (Phase C). No behaviour change.
Data is fetched via the injected `albert.deps.daily_ohlcv` / `deps.spot_price`.
"""
import numpy as np

from albert import deps


def rsi(series, n=14):
    d = series.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs))


def score_asset(symbol, regime):
    """Transparent 0-100 opportunity score with retained components. Returns an
    `ok: False` dict on stale/insufficient data so the caller can force WAIT."""
    df = deps.daily_ohlcv(symbol, 400)
    if df is None or len(df) < 60:
        return {'ok': False, 'reason': 'stale_or_insufficient_data', 'currentPrice': deps.spot_price(symbol) or None}
    close = df['close'].astype(float)
    vol = df['volume'].astype(float)
    price = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50
    rsi_v = float(rsi(close).iloc[-1]) if len(close) > 20 else 50.0
    roc30 = (price - float(close.iloc[-30])) / float(close.iloc[-30]) * 100 if len(close) > 30 else 0.0
    hi1y = float(close.tail(365).max())
    dd = (price - hi1y) / hi1y * 100 if hi1y else 0.0  # negative = below high
    ret = close.pct_change().dropna()
    realized_vol = float(ret.tail(30).std() * (365 ** 0.5) * 100) if len(ret) > 30 else 60.0
    avg_usd_vol = float((vol.tail(30) * close.tail(30)).mean()) if len(vol) > 30 else 0.0

    # Components (each capped to its weight)
    trend = 0.0
    if price > sma50:
        trend += 13
    if price > sma200:
        trend += 12
    trend = min(25.0, trend)
    momentum = max(0.0, min(15.0, 7.5 + roc30 / 4.0))
    if rsi_v > 78:
        momentum = min(momentum, 8.0)  # overextended penalty
    valuation = max(0.0, min(15.0, (-dd) / 4.0))  # deeper below high => more attractive
    volatility = max(0.0, min(10.0, 10.0 - abs(realized_vol - 60.0) / 12.0))
    liquidity = min(10.0, (avg_usd_vol / 5e7) * 10.0) if avg_usd_vol else (10.0 if symbol in ('BTC', 'ETH') else 3.0)
    if regime == 'BULL':
        regime_fit = 15.0 if price > sma200 else 7.0
    elif regime == 'BEAR':
        regime_fit = 4.0 if price < sma200 else 8.0
    else:
        regime_fit = 9.0
    comps = {'trend': round(trend, 1), 'momentum': round(momentum, 1), 'valuation': round(valuation, 1),
             'volatility': round(volatility, 1), 'liquidity': round(liquidity, 1),
             'regimeFit': round(regime_fit, 1), 'portfolioFit': 10.0}  # portfolioFit finalised later
    score = sum(comps.values())
    # confidence from data completeness + liquidity + signal agreement
    completeness = min(1.0, len(close) / 365.0)
    agree = 1.0 if (trend >= 13 and momentum >= 7.5) or (trend < 13 and momentum < 7.5) else 0.6
    confidence = int(min(96, 40 + completeness * 30 + (liquidity / 10) * 20 + agree * 10))
    invalidation = round(min(float(close.tail(20).min()), sma50) * 0.98, 6)  # long invalidation
    reasons = []
    if price > sma200:
        reasons.append('above the 200-day trend')
    else:
        reasons.append('below the 200-day trend')
    reasons.append('RSI %.0f' % rsi_v + (' (overbought)' if rsi_v > 70 else ' (oversold)' if rsi_v < 30 else ''))
    reasons.append('%.0f%% from 1y high' % dd)
    return {'ok': True, 'symbol': symbol, 'currentPrice': price, 'score': round(score, 1), 'components': comps,
            'confidence': confidence, 'invalidation': invalidation, 'realized_vol': round(realized_vol, 1),
            'rsi': round(rsi_v, 1), 'reasons': reasons}
