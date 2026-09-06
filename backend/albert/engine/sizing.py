"""Deterministic SELL sizing helpers (Phase D1).

Maps a *required* sell fraction onto the permitted action framework and computes
the exact USD / quantity deltas. Reason codes are never bound to a fixed trim
percentage — severity chooses the fraction, this module rounds it into a
permitted action.
"""
from albert.engine.constants import SELL_PERMITTED_FRACTIONS


def round_up_fraction(f):
    """Round a required fraction UP to the nearest permitted SELL action so a
    compliance target is actually met (e.g. an 8%% overshoot -> a 10%% trim, not
    an arbitrary 50%% cut). Anything above the largest tier -> full exit."""
    try:
        f = float(f)
    except Exception:  # noqa
        return SELL_PERMITTED_FRACTIONS[0]
    if f <= 0:
        return SELL_PERMITTED_FRACTIONS[0]
    for tier in SELL_PERMITTED_FRACTIONS:
        if f <= tier + 1e-9:
            return tier
    return 1.0


def action_label(fraction):
    """Canonical action label for a permitted sell fraction."""
    if fraction >= 1.0 - 1e-9:
        return 'EXIT_100'
    return 'TRIM_%d' % int(round(fraction * 100))


def build_sell_plan(reason_code, fraction, position_value, position_size, current_pct,
                    current_price=None, note='', all_signals=None):
    """Return an immutable-friendly sell plan dict with exact deltas."""
    fraction = float(fraction)
    sell_usd = round((position_value or 0.0) * fraction, 2)
    sell_qty = round((position_size or 0.0) * fraction, 8) if position_size else None
    after_val = round((position_value or 0.0) * (1.0 - fraction), 2)
    after_pct = round((current_pct or 0.0) * (1.0 - fraction), 2)
    after_size = round((position_size or 0.0) * (1.0 - fraction), 8) if position_size else None
    return {
        'reasonCode': reason_code,
        'action': action_label(fraction),
        'fraction': round(fraction, 4),
        'sellUsd': sell_usd,
        'sellQty': sell_qty,
        'currentPrice': current_price,
        'positionBefore': {'valueUsd': round(position_value or 0.0, 2), 'pct': round(current_pct or 0.0, 2),
                           'size': round(position_size, 8) if position_size else None},
        'positionAfter': {'valueUsd': after_val, 'pct': after_pct, 'size': after_size},
        'recommendedDeltaUsd': -sell_usd,
        'note': note,
        'allSignals': list(all_signals or []),
    }
