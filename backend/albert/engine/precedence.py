"""Decision precedence resolution (Phase D1).

The single source of truth for ordering is PRECEDENCE_ORDER in constants.py.
This module resolves a set of fired signals into the ONE winning call so a high
opportunity score can never overpower a risk exit.
"""
from albert.engine.constants import PRECEDENCE_ORDER


def rank(reason_code):
    """Lower number = higher precedence."""
    return PRECEDENCE_ORDER.get(reason_code, 999)


def resolve(signals):
    """Given a list of signal dicts each with a 'reasonCode', return the single
    highest-precedence signal (or None). Deterministic: ties broken by input
    order, but reason codes are unique per class so ties are effectively by
    severity only."""
    if not signals:
        return None
    return sorted(signals, key=lambda s: rank(s.get('reasonCode')))[0]
