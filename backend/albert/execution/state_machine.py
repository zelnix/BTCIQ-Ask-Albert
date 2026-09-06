"""Order lifecycle state machine (Phase E). Terminal states are immutable — no
resurrection, amendment, or retry of the same intent after a terminal state."""

DRAFT = 'DRAFT'
PENDING_CONFIRMATION = 'PENDING_CONFIRMATION'
CONFIRMED = 'CONFIRMED'
WORKING = 'WORKING'
PARTIALLY_FILLED = 'PARTIALLY_FILLED'
FILLED = 'FILLED'
CANCELLED = 'CANCELLED'
REJECTED = 'REJECTED'
EXPIRED = 'EXPIRED'

TERMINAL = frozenset({FILLED, CANCELLED, REJECTED, EXPIRED})

LEGAL = {
    DRAFT: {PENDING_CONFIRMATION},
    PENDING_CONFIRMATION: {CONFIRMED, CANCELLED, EXPIRED, REJECTED},
    CONFIRMED: {WORKING, CANCELLED, EXPIRED, REJECTED},
    WORKING: {PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED},
    PARTIALLY_FILLED: {PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED},
    FILLED: set(),
    CANCELLED: set(),
    REJECTED: set(),
    EXPIRED: set(),
}


class IllegalTransition(Exception):
    pass


def is_terminal(state):
    return state in TERMINAL


def can_transition(frm, to):
    return to in LEGAL.get(frm, set())


def assert_transition(frm, to):
    if not can_transition(frm, to):
        raise IllegalTransition('Illegal transition %s -> %s' % (frm, to))
