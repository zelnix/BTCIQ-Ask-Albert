"""Dependency-injection container for the Albert engine.

The heavy market-data + portfolio helpers (`_daily_ohlcv`, `_spot_price`,
`_sector_strength`, `_num`, `_portfolio_summary`, `_get_mandate`,
`_mandate_complete`) are defined deep inside server.py. Importing server.py from
the engine would create a circular import, so instead server.py calls
`albert.deps.configure(...)` once at boot to wire the callables in.

Mongo collections come straight from config (no circular dependency).
"""
from config import (  # noqa: F401
    regime_col,
    mandate_col,
    portfolio_col,
    decision_history_col,
)

# --- injected callables (set by server.py via configure()) -------------------
daily_ohlcv = None          # (symbol, limit) -> pandas.DataFrame | None
spot_price = None           # (symbol) -> float | None
sector_strength = None      # () -> dict[str, float|None]
num = None                  # (value) -> float | None
portfolio_summary = None    # (pid) -> dict
get_mandate = None          # (pid) -> dict
mandate_complete = None     # (mandate) -> bool

_KNOWN = {
    'daily_ohlcv', 'spot_price', 'sector_strength', 'num',
    'portfolio_summary', 'get_mandate', 'mandate_complete',
}


def configure(**kwargs):
    """Inject the runtime helpers. Called once from server.py at import time,
    after all helper functions have been defined."""
    g = globals()
    for k, v in kwargs.items():
        if k not in _KNOWN:
            raise KeyError("albert.deps has no dependency named %r" % k)
        g[k] = v


def ready():
    """True once every dependency has been injected."""
    g = globals()
    return all(g.get(k) is not None for k in _KNOWN)
