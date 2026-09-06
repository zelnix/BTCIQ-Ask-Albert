"""Engine constants for the deterministic Albert decision engine.

These are versioned WITH the engine: any change to a threshold, ceiling, or the
universe should bump ALBERT_ENGINE_VERSION so that immutable decision snapshots
remain reproducible.
"""

ALBERT_ENGINE_VERSION = 'albert-decide-v1'

# Regime-sensitive BUY entry thresholds (opportunity score must be >= this).
REGIME_BUY_THRESHOLD = {'BULL': 72, 'RANGE': 78, 'BEAR': 85}

# Fraction of *deployable* USDC the engine is willing to put to work in a regime.
REGIME_DEPLOY_CEILING = {'BULL': 0.60, 'RANGE': 0.35, 'BEAR': 0.15}

# Liquid v1 discovery universe (held coins are always evaluated too).
ALBERT_UNIVERSE = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOGE', 'LINK', 'DOT', 'LTC', 'TRX']

# Stablecoins are never scored as opportunities.
STABLES = {'USDC', 'USDT', 'DAI', 'USD', 'TUSD', 'FDUSD', 'BUSD'}

# ---------------------------------------------------------------------------
# Phase D1: SELL engine + decision precedence
# ---------------------------------------------------------------------------
# BUY hysteresis bands (versioned WITH the engine). Enter BUY at the regime
# threshold; a held/last BUY position REMAINS a BUY down to the lower band, and
# only loses BUY status below it (or on an explicit risk/invalidation trigger).
# This prevents Albert bouncing between BUY and WAIT on a 71.9 -> 72.1 wobble.
REGIME_BUY_ENTER = dict(REGIME_BUY_THRESHOLD)                 # {'BULL':72,'RANGE':78,'BEAR':85}
REGIME_BUY_REMAIN = {'BULL': 68, 'RANGE': 74, 'BEAR': 81}    # enter - 4 (hysteresis floor)

# Canonical SELL reason codes (five classes) — ordered by severity elsewhere.
SELL_REASON_CODES = ('EMERGENCY_EXIT', 'THESIS_INVALIDATION', 'RISK_REDUCTION', 'REBALANCE', 'PROFIT_TAKE')

# The ONLY permitted SELL actions. Deterministic severity chooses among them;
# a reason code is never hard-bound to a single fixed percentage.
SELL_PERMITTED_FRACTIONS = (0.10, 0.25, 0.50, 1.00)

# EMERGENCY: a held position down worse than this (unrealized %) is a full exit.
EMERGENCY_LOSS_PCT = 35.0

# RISK_REDUCTION: trim only when a position's risk-at-stop exceeds this multiple
# of the mandated per-trade risk budget (avoids trimming on every wobble).
RISK_BREACH_MULT = 1.5

# REBALANCE: ignore tiny allocation overshoots below this many percentage points.
REBALANCE_TOL_PCT = 2.0

# PROFIT_TAKE ladder: (unrealized-gain%% >= threshold) -> trim fraction. Highest
# qualifying tier wins. Staged 10 / 25 / 50 per the spec.
PROFIT_LADDER = ((200.0, 0.50), (100.0, 0.25), (50.0, 0.10))

# Full deterministic decision precedence (1 = highest). A high opportunity score
# can NEVER overpower a risk exit: every SELL class outranks BUY/HOLD/WAIT, and a
# genuine risk breach (RISK_REDUCTION) outranks ordinary REBALANCE.
PRECEDENCE_ORDER = {
    'EMERGENCY_EXIT': 1,
    'THESIS_INVALIDATION': 2,
    'RISK_REDUCTION': 3,
    'REBALANCE': 4,
    'PROFIT_TAKE': 5,
    'BUY': 6,
    'HOLD': 7,
    'WAIT': 8,
}
