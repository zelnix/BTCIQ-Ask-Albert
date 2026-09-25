"""Trustworthy paper-trading core — exact accounting, canonical binding, ordered
mandate/risk gates, single-document atomic approval + idempotency, and honest
equity/drawdown truth.

DESIGN NOTES
------------
* MONEY IS EXACT. Every monetary/quantity value uses `decimal.Decimal` in
  calculations and `bson.Decimal128` in MongoDB. Binary floats are NEVER used
  for cash, quantity, price, fees, cost basis, P&L, reserve, allocation or
  drawdown. Values cross the API boundary as decimal STRINGS.

* SINGLE-DOCUMENT ATOMICITY. All economic effects for one paper account (cash,
  the BTC lot, fees, realised P&L, the append-only ledger, the account sequence,
  the proposal-consumption marker and the idempotency record) live INSIDE the
  account document and commit in ONE conditional `find_one_and_update`. A CAS on
  `version` + guards on `idemKeys`/`consumedProposals` guarantee that concurrent
  approvals, retries and redelivery produce EXACTLY ONE economic effect. This is
  a real transactional boundary on standalone MongoDB (not a store limitation).

* CANONICAL DECISIONS ONLY. Actions come solely from an immutable canonical
  decision snapshot. Market Driver Intelligence is evidence only and can never
  manufacture a BUY/SELL. WAIT/HOLD never create entries. Anything unknown,
  mutable, incomplete or stale fails CLOSED.

* SIZING REDUCES, NEVER ENLARGES the canonical amount.
"""
import datetime
import uuid
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, getcontext, InvalidOperation

from bson.decimal128 import Decimal128

getcontext().prec = 34

# --- precision / rounding rules ------------------------------------------------
CASH_Q = Decimal('0.01')          # money quantised to cents (ROUND_HALF_UP)
PRICE_Q = Decimal('0.01')         # BTC/USD price tick
QTY_Q = Decimal('0.00000001')     # 8dp (satoshi) — buys/sells ROUND_DOWN (never over-fill)
PCT_Q = Decimal('0.01')
MIN_NOTIONAL = Decimal('10')      # minimum simulated order notional

SUPPORTED_ENGINE_VERSIONS = {'albert-decide-v2'}
DECISION_TTL_MIN = 30
PROPOSAL_TTL_MIN = 30

# Conservative deterministic execution profile (all Decimal bps).
EXEC_PROFILE = {'executionProfileId': 'ep_conservative_v1', 'feeBps': Decimal('40'),
                'spreadBps': Decimal('5'), 'slippageBps': Decimal('8'), 'model': 'conservative'}
BPS = Decimal('10000')


# ============================ Decimal helpers ================================ #
def D(x):
    """Coerce a Decimal128 / float / int / str / Decimal / None -> Decimal|None.
    Floats are stringified first so we never inherit binary-float error."""
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, Decimal128):
        return x.to_decimal()
    try:
        if isinstance(x, float):
            return Decimal(repr(x))
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def q_cash(x):
    d = D(x)
    return None if d is None else d.quantize(CASH_Q, rounding=ROUND_HALF_UP)


def q_price(x):
    d = D(x)
    return None if d is None else d.quantize(PRICE_Q, rounding=ROUND_HALF_UP)


def q_qty(x):
    """Quantities always ROUND_DOWN — we never fabricate fractions of BTC."""
    d = D(x)
    return None if d is None else d.quantize(QTY_Q, rounding=ROUND_DOWN)


def to128(x):
    """Store as Decimal128 (quantised to cents for money-like magnitudes is left
    to callers; here we store the exact Decimal)."""
    d = D(x)
    return None if d is None else Decimal128(d)


def dstr(x, q=CASH_Q):
    d = D(x)
    if d is None:
        return None
    return str(d.quantize(q, rounding=ROUND_HALF_UP))


def qty_dstr(x):
    d = D(x)
    if d is None:
        return None
    return str(d.quantize(QTY_Q, rounding=ROUND_DOWN))


def sim_fill(side, ref_px, notional):
    """Deterministic conservative fill. Returns (fill_px: Decimal, fee: Decimal)."""
    ref_px = D(ref_px)
    notional = D(notional) or Decimal('0')
    slip = (EXEC_PROFILE['spreadBps'] + EXEC_PROFILE['slippageBps']) / BPS
    if side == 'BUY':
        fill_px = ref_px * (Decimal('1') + slip)
    else:
        fill_px = ref_px * (Decimal('1') - slip)
    fee = (notional * EXEC_PROFILE['feeBps'] / BPS)
    return q_price(fill_px), q_cash(fee)


# ============================ account state ================================== #
def new_account_economics(starting_cash, reserve_pct):
    """Initial embedded economic sub-document (all money as Decimal128)."""
    sc = q_cash(starting_cash) or Decimal('100000.00')
    return {
        'cash': to128(sc), 'startingCash': to128(sc),
        'realizedPnl': to128(Decimal('0')), 'feesPaid': to128(Decimal('0')),
        'reservePct': to128(D(reserve_pct) or Decimal('0')),
        'highWaterEquity': to128(sc),  # HWM starts at opening equity (fully in cash)
        'lots': [], 'closedLots': [], 'ledger': [], 'idemKeys': [],
        'consumedProposals': [], 'appliedApprovals': [], 'accountSequence': 0,
    }


def _btc_lot(acct):
    for lot in (acct.get('lots') or []):
        if lot.get('asset') == 'BTC':
            return lot
    return None


def account_position_qty(acct):
    lot = _btc_lot(acct)
    return D((lot or {}).get('qty')) or Decimal('0')


# ============================ equity / drawdown ============================== #
def compute_equity(acct, mark_px, mark_fresh):
    """HONEST valuation. A missing/stale BTC price for a HELD position yields an
    explicitly UNAVAILABLE/STALE equity — never a zero and never a silent 0 mark.
    A missing valuation must NOT move the high-water mark or reduce drawdown."""
    cash = D(acct.get('cash')) or Decimal('0')
    qty = account_position_qty(acct)
    lot = _btc_lot(acct)
    stored_hwm = D(acct.get('highWaterEquity'))
    realized = D(acct.get('realizedPnl')) or Decimal('0')
    fees = D(acct.get('feesPaid')) or Decimal('0')
    reserve_pct = D(acct.get('reservePct')) or Decimal('0')

    if qty > 0:
        if mark_px is None or not mark_fresh:
            status = 'STALE' if mark_px is not None else 'UNAVAILABLE'
            return {'available': False, 'markStatus': status, 'equity': None,
                    'equityStr': None, 'cash': cash, 'positionQty': qty,
                    'unrealized': None, 'drawdownPct': None, 'highWater': stored_hwm,
                    'protectedReserve': None, 'deployableCash': None,
                    'realizedPnl': realized, 'fees': fees, 'markPx': mark_px}
        mark_px = D(mark_px)
        pos_val = (qty * mark_px)
        equity = cash + pos_val
        avg = D((lot or {}).get('avgEntry')) or Decimal('0')
        unreal = qty * (mark_px - avg)
        mark_status = 'CURRENT'
    else:
        # Flat: equity is exactly cash — known even when price is stale.
        equity = cash
        unreal = Decimal('0')
        mark_status = 'CURRENT' if (mark_px is not None and mark_fresh) else 'FLAT_PRICE_UNVERIFIED'

    hwm = stored_hwm if stored_hwm is not None else equity
    if equity > hwm:
        hwm = equity
    dd = ((equity / hwm) - Decimal('1')) * Decimal('100') if hwm and hwm > 0 else Decimal('0')
    if dd > 0:
        dd = Decimal('0')
    reserve = (equity * reserve_pct / Decimal('100'))
    deployable = cash - reserve
    if deployable < 0:
        deployable = Decimal('0')
    return {'available': True, 'markStatus': mark_status, 'equity': equity,
            'equityStr': dstr(equity), 'cash': cash, 'positionQty': qty,
            'unrealized': unreal, 'drawdownPct': dd.quantize(PCT_Q, ROUND_HALF_UP),
            'highWater': hwm, 'protectedReserve': reserve, 'deployableCash': deployable,
            'realizedPnl': realized, 'fees': fees, 'markPx': mark_px}


# ============================ ordered gates ================================== #
def _rej(code, msg, trace):
    return {'reject': code, 'message': msg, 'trace': trace}


def run_entry_gates(*, acct, canonical, mark_px, mark_fresh, mandate, equity_info,
                    has_open_intent=False):
    """Ordered mandate + risk gates for a paper BUY. Returns a dict with either
    'reject' set (with the failing gate in 'trace') or a sizing result. Sizing can
    only REDUCE the canonical amount."""
    trace = []

    def g(name, ok, detail=''):
        trace.append({'gate': name, 'ok': bool(ok), 'detail': str(detail)})
        return bool(ok)

    # 1. authenticated owner + active paper account (owner already verified upstream)
    if not g('active_account', acct.get('runtimeState') == 'RUNNING' and not acct.get('archivedAt'),
             acct.get('runtimeState')):
        return _rej('ACCOUNT_NOT_ACTIVE', 'Account is not active.', trace)
    # 2. BTC spot capability
    if not g('btc_spot_capability', canonical.get('asset') == 'BTC'):
        return _rej('UNSUPPORTED_ASSET', 'Only BTC spot is supported.', trace)
    # 3. current, supported canonical decision
    if not g('canonical_decision',
             canonical.get('actionable') and canonical.get('action') == 'BUY'
             and canonical.get('engineVersion') in SUPPORTED_ENGINE_VERSIONS):
        return _rej('NO_ACTIONABLE_DECISION', 'No current BUY decision to act on.', trace)
    # 4. fresh decision + market evidence
    if not g('freshness', canonical.get('fresh') and mark_fresh and mark_px is not None):
        return _rej('STALE', 'Decision or market data is stale.', trace)
    # 5. BTC approved and not excluded
    mc = canonical.get('mandateChecks') or {}
    if not g('approved_not_excluded', (not mc.get('excluded')) and mc.get('inApprovedUniverse')):
        return _rej('NOT_APPROVED', 'BTC is excluded or not in the approved universe.', trace)
    # 6. complete current Trading Mandate
    if not g('mandate_complete', mc.get('mandateComplete')):
        return _rej('MANDATE_INCOMPLETE', 'Trading Mandate is incomplete.', trace)
    # 7. duplicate / open-intent protection
    if not g('no_duplicate_intent', not has_open_intent):
        return _rej('DUPLICATE_INTENT', 'An open intent already exists for this decision.', trace)

    mark_px = D(mark_px)
    equity = equity_info.get('equity')
    if equity is None or not equity_info.get('available'):
        return _rej('EQUITY_UNAVAILABLE', 'Equity could not be verified.', trace)
    cash = equity_info['cash']
    reserve = equity_info['protectedReserve']
    deployable = equity_info['deployableCash']

    # 8. virtual cash available  &  9. protected reserve preserved
    if not g('cash_and_reserve', deployable >= MIN_NOTIONAL,
             'deployable=%s reserve=%s' % (deployable, reserve)):
        return _rej('INSUFFICIENT_DEPLOYABLE', 'No deployable cash after preserving the reserve.', trace)

    # Canonical recommended amount is the STARTING notional; sizing may only shrink it.
    rec = D(canonical.get('recommendedDeployNowUsd')) or Decimal('0')
    if not g('canonical_amount', rec > 0, 'rec=%s' % rec):
        return _rej('NO_DEPLOY_AMOUNT', 'Canonical decision recommends no deployment now.', trace)
    notional = rec
    notional = min(notional, deployable)

    # 10. maximum allocation
    cap_pct = D((mandate.get('max_alloc_pct') or {}).get('BTC', 100))
    if cap_pct is None:
        cap_pct = Decimal('100')
    max_pos_val = equity * cap_pct / Decimal('100')
    cur_pos_val = equity_info['positionQty'] * mark_px
    alloc_room = max_pos_val - cur_pos_val
    if alloc_room < 0:
        alloc_room = Decimal('0')
    notional = min(notional, alloc_room)
    g('max_allocation', True, 'capPct=%s room=%s' % (cap_pct, alloc_room))

    # 11. maximum trade risk at invalidation
    inv = D(canonical.get('invalidationPrice'))
    mtr = D(mandate.get('max_trade_risk_pct'))
    if mtr is None:
        mtr = Decimal('2')
    risk_budget = equity * mtr / Decimal('100')
    if inv is not None and inv > 0 and inv < mark_px:
        stop_dist = (mark_px - inv) / mark_px
        if stop_dist > 0:
            max_by_risk = risk_budget / stop_dist
            notional = min(notional, max_by_risk)
    g('max_trade_risk', True, 'budget=%s inv=%s' % (risk_budget, inv))

    # 12. drawdown breaker
    dd = equity_info['drawdownPct']
    max_dd = D(mandate.get('max_drawdown_pct'))
    if max_dd is not None and not g('drawdown_breaker', dd > (-max_dd), 'dd=%s limit=-%s' % (dd, max_dd)):
        return _rej('DRAWDOWN_BREAKER', 'Drawdown breaker is tripped — entries paused.', trace)
    else:
        g('drawdown_breaker', True, 'dd=%s' % dd)

    # 13. quantity / price / minimum-notional precision
    notional = q_cash(notional)
    if not g('min_notional', notional is not None and notional >= MIN_NOTIONAL, 'notional=%s' % notional):
        return _rej('BELOW_MIN_NOTIONAL', 'Sized notional is below the minimum.', trace)
    fill_px, fee = sim_fill('BUY', mark_px, notional)
    qty = q_qty((notional - fee) / fill_px)
    if not g('positive_qty', qty is not None and qty > 0, 'qty=%s' % qty):
        return _rej('BELOW_MIN_NOTIONAL', 'Sized quantity rounds to zero.', trace)
    return {'reject': None, 'trace': trace, 'side': 'BUY',
            'notional': notional, 'fillPx': fill_px, 'fee': fee, 'qty': qty}


def run_exit_gates(*, acct, mark_px, mark_fresh, canonical=None, full=False):
    """Reduce-only paper SELL. `full`=True is a safe user-initiated exit that does
    not require a canonical SELL; otherwise a canonical SELL decision drives it."""
    trace = []

    def g(name, ok, detail=''):
        trace.append({'gate': name, 'ok': bool(ok), 'detail': str(detail)})
        return bool(ok)

    if not g('active_account', acct.get('runtimeState') in ('RUNNING', 'PAUSED_BY_USER',
                                                            'PAUSED_RISK_BREAKER') and not acct.get('archivedAt')):
        return _rej('ACCOUNT_NOT_ACTIVE', 'Account is not active.', trace)
    qty_held = account_position_qty(acct)
    if not g('has_position', qty_held > 0, 'held=%s' % qty_held):
        return _rej('NO_POSITION', 'No open BTC position to reduce.', trace)
    if not g('freshness', mark_fresh and mark_px is not None):
        return _rej('STALE', 'Market data is stale — cannot value the exit.', trace)
    mark_px = D(mark_px)
    if full or canonical is None:
        sell_qty = qty_held
    else:
        if not g('canonical_sell', canonical.get('actionable') and canonical.get('action') == 'SELL'):
            return _rej('NO_ACTIONABLE_DECISION', 'No current SELL decision.', trace)
        sp = canonical.get('sellPlan') or {}
        delta = D(sp.get('recommendedDeltaUsd'))
        sell_usd = abs(delta) if delta is not None else (qty_held * mark_px)
        sell_qty = q_qty(min(qty_held, sell_usd / mark_px))
    sell_qty = q_qty(min(qty_held, sell_qty))
    if not g('positive_qty', sell_qty is not None and sell_qty > 0):
        return _rej('BELOW_MIN_NOTIONAL', 'Nothing to sell.', trace)
    gross = sell_qty * mark_px
    fill_px, fee = sim_fill('SELL', mark_px, gross)
    return {'reject': None, 'trace': trace, 'side': 'SELL',
            'qty': sell_qty, 'fillPx': fill_px, 'fee': fee}


# ==================== single-document atomic execution ======================= #
def _ledger_entry(seq, event_type, entity_id, amount, note):
    now = datetime.datetime.utcnow().isoformat()
    return {'ledgerEventId': 'ple_' + uuid.uuid4().hex[:14], 'accountSequence': seq,
            'eventType': event_type, 'entityId': entity_id,
            'amount': to128(amount) if amount is not None else None,
            'note': note, 'effectiveAt': now, 'recordedAt': now}


def apply_buy_atomic(col, acct_id, pid, expected_version, idem_key, proposal_id,
                     sizing, canonical, base_currency='USDC'):
    """Apply a BUY as ONE conditional update. Idempotent + concurrency-safe.
    Returns (result_dict, error_code, http_status)."""
    for _ in range(5):
        acct = col.find_one({'paperAccountId': acct_id, 'ownerId': pid})
        if not acct:
            return None, 'NOT_FOUND', 404
        # Idempotent replay?
        for ap in (acct.get('appliedApprovals') or []):
            if ap.get('idemKey') == idem_key:
                return ap.get('result'), None, 200
        if proposal_id in (acct.get('consumedProposals') or []):
            return None, 'ALREADY_CONSUMED', 409
        if acct.get('version') != expected_version:
            expected_version = acct.get('version')
            # fall through & retry with the current version

        cash = D(acct.get('cash')) or Decimal('0')
        fees = D(acct.get('feesPaid')) or Decimal('0')
        notional, fill_px, fee, qty = sizing['notional'], sizing['fillPx'], sizing['fee'], sizing['qty']
        new_cash = q_cash(cash - notional)
        new_fees = q_cash(fees + fee)
        lot = _btc_lot(acct)
        lots = list(acct.get('lots') or [])
        if lot:
            oq = D(lot.get('qty')); ocb = D(lot.get('costBasis'))
            nq = q_qty(oq + qty); ncb = q_cash(ocb + notional)
            navg = q_price(ncb / nq) if nq > 0 else Decimal('0')
            for l in lots:
                if l.get('asset') == 'BTC':
                    l['qty'] = to128(nq); l['costBasis'] = to128(ncb); l['avgEntry'] = to128(navg)
                    l['positionVersion'] = (l.get('positionVersion') or 0) + 1
            lot_id = lot.get('lotId')
        else:
            lot_id = 'pp_' + uuid.uuid4().hex[:12]
            lots.append({'lotId': lot_id, 'asset': 'BTC', 'status': 'OPEN',
                         'qty': to128(qty), 'avgEntry': to128(fill_px), 'costBasis': to128(notional),
                         'realizedPnl': to128(Decimal('0')), 'feesPaid': to128(fee),
                         'openedAt': datetime.datetime.utcnow().isoformat(),
                         'entryDecisionSnapshotId': canonical.get('decisionSnapshotId'),
                         'entryDecisionId': canonical.get('decisionId'),
                         'invalidationPrice': to128(q_price(canonical.get('invalidationPrice'))) if canonical.get('invalidationPrice') else None,
                         'positionVersion': 1})
        seq = (acct.get('accountSequence') or 0) + 1
        led = _ledger_entry(seq, 'FILL', lot_id, -notional,
                            'BUY %s BTC @ %s (fee %s) · approval' % (qty_dstr(qty), dstr(fill_px), dstr(fee)))
        result = {'side': 'BUY', 'qty': qty_dstr(qty), 'fillPrice': dstr(fill_px),
                  'fee': dstr(fee), 'notional': dstr(notional), 'positionId': lot_id,
                  'decisionSnapshotId': canonical.get('decisionSnapshotId'), 'paperOnly': True}
        applied = {'idemKey': idem_key, 'proposalId': proposal_id, 'result': result,
                   'at': datetime.datetime.utcnow().isoformat()}
        upd = col.find_one_and_update(
            {'paperAccountId': acct_id, 'ownerId': pid, 'version': expected_version,
             'idemKeys': {'$ne': idem_key}, 'consumedProposals': {'$ne': proposal_id}},
            {'$set': {'cash': to128(new_cash), 'feesPaid': to128(new_fees), 'lots': lots},
             '$push': {'ledger': led, 'idemKeys': idem_key,
                       'consumedProposals': proposal_id, 'appliedApprovals': applied},
             '$inc': {'version': 1, 'accountSequence': 1}})
        if upd is not None:
            return result, None, 200
        # CAS miss: loop re-reads (idempotent replay / already-consumed handled at top).
    return None, 'CONCURRENCY_RETRY_EXHAUSTED', 409


def apply_sell_atomic(col, acct_id, pid, sizing, source='approval', idem_key=None,
                      proposal_id=None, canonical=None, base_currency='USDC'):
    """Apply a reduce-only SELL as ONE conditional update."""
    for _ in range(5):
        acct = col.find_one({'paperAccountId': acct_id, 'ownerId': pid})
        if not acct:
            return None, 'NOT_FOUND', 404
        if idem_key:
            for ap in (acct.get('appliedApprovals') or []):
                if ap.get('idemKey') == idem_key:
                    return ap.get('result'), None, 200
        lot = _btc_lot(acct)
        if not lot or (D(lot.get('qty')) or Decimal('0')) <= 0:
            return None, 'NO_POSITION', 404
        expected_version = acct.get('version')
        cash = D(acct.get('cash')) or Decimal('0')
        fees = D(acct.get('feesPaid')) or Decimal('0')
        realized_acc = D(acct.get('realizedPnl')) or Decimal('0')
        qty = sizing['qty']; fill_px = sizing['fillPx']; fee = sizing['fee']
        oq = D(lot.get('qty')); ocb = D(lot.get('costBasis'))
        qty = q_qty(min(oq, qty))
        proceeds = q_cash(qty * fill_px - fee)
        cost_portion = q_cash(ocb * (qty / oq)) if oq > 0 else Decimal('0')
        realized = q_cash(proceeds - cost_portion)
        new_cash = q_cash(cash + proceeds)
        new_fees = q_cash(fees + fee)
        new_realized = q_cash(realized_acc + realized)
        remaining = q_qty(oq - qty)
        lots = list(acct.get('lots') or [])
        closed = list(acct.get('closedLots') or [])
        if remaining <= 0:
            lots = [l for l in lots if l.get('asset') != 'BTC']
            closed.append({'lotId': lot.get('lotId'), 'asset': 'BTC', 'status': 'CLOSED',
                           'qty': to128(qty), 'avgEntry': lot.get('avgEntry'),
                           'exitPrice': to128(fill_px), 'realizedPnl': to128(realized),
                           'closedAt': datetime.datetime.utcnow().isoformat(),
                           'entryDecisionSnapshotId': lot.get('entryDecisionSnapshotId')})
        else:
            for l in lots:
                if l.get('asset') == 'BTC':
                    l['qty'] = to128(remaining)
                    l['costBasis'] = to128(q_cash(ocb - cost_portion))
                    l['positionVersion'] = (l.get('positionVersion') or 0) + 1
        seq = (acct.get('accountSequence') or 0) + 1
        led = _ledger_entry(seq, 'FILL', lot.get('lotId'), proceeds,
                            'SELL %s BTC @ %s (fee %s, PnL %s) · %s'
                            % (qty_dstr(qty), dstr(fill_px), dstr(fee), dstr(realized), source))
        result = {'side': 'SELL', 'qty': qty_dstr(qty), 'fillPrice': dstr(fill_px),
                  'fee': dstr(fee), 'proceeds': dstr(proceeds), 'realized': dstr(realized),
                  'paperOnly': True}
        push = {'ledger': led}
        setd = {'cash': to128(new_cash), 'feesPaid': to128(new_fees),
                'realizedPnl': to128(new_realized), 'lots': lots, 'closedLots': closed}
        flt = {'paperAccountId': acct_id, 'ownerId': pid, 'version': expected_version}
        if idem_key:
            push['idemKeys'] = idem_key
            push['appliedApprovals'] = {'idemKey': idem_key, 'proposalId': proposal_id,
                                        'result': result, 'at': datetime.datetime.utcnow().isoformat()}
            flt['idemKeys'] = {'$ne': idem_key}
            if proposal_id:
                push['consumedProposals'] = proposal_id
                flt['consumedProposals'] = {'$ne': proposal_id}
        upd = col.find_one_and_update(flt, {'$set': setd, '$push': push, '$inc': {'version': 1, 'accountSequence': 1}})
        if upd is not None:
            return result, None, 200
    return None, 'CONCURRENCY_RETRY_EXHAUSTED', 409


def update_high_water(col, acct_id, pid, equity):
    """Persist the high-water equity with an atomic $max (only ever grows).
    Called ONLY with a complete, verified valuation."""
    if equity is None:
        return
    col.update_one({'paperAccountId': acct_id, 'ownerId': pid},
                   {'$max': {'highWaterEquity': to128(q_cash(equity))}})


def revalidate_ok(canonical, side, snapshot_id):
    """True only if the CURRENT canonical decision still authorises this exact
    proposal (same immutable snapshot id, same actionable side, still fresh).
    A mandate/decision change mints a new snapshot id -> returns False."""
    if not canonical:
        return False
    if canonical.get('decisionSnapshotId') != snapshot_id:
        return False
    if not canonical.get('actionable'):
        return False
    if canonical.get('action') != side:
        return False
    if not canonical.get('fresh'):
        return False
    return True

