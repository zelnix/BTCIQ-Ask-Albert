"""Ask-Albert remediation — Milestone 2 (Trustworthy Paper Core) acceptance tests.

Two layers:
  * CORE (isolated, no HTTP): exercises the fully-functional — but deployment-OFF —
    execution/accounting via `albert.paper.core` against a disposable Mongo
    collection. This is the "isolated test configuration" the remediation permits.
  * HTTP (live :8001, execution flag OFF): proves the deployed boundary — AUTOPILOT
    and approval EXECUTION are refused, modes are limited, expired proposals reject.

Run:  cd /app/backend && python -m pytest tests/test_m2_paper_core.py -v
"""
import os
import sys
import uuid
import datetime
import threading
from decimal import Decimal

import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from albert.paper import core  # noqa: E402

BASE = os.environ.get('M1_TEST_BASE', 'http://localhost:8001')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'btciq')

_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]


# =============================== fixtures ==================================== #
@pytest.fixture()
def col():
    c = _db['test_m2_paper_' + uuid.uuid4().hex[:8]]
    yield c
    c.drop()


def make_acct(starting='100000', reserve_pct='0', pid='u_m2', mode='APPROVAL_REQUIRED', hwm=None):
    econ = core.new_account_economics(Decimal(starting), Decimal(reserve_pct))
    acct = {'paperAccountId': 'pa_' + uuid.uuid4().hex[:12], 'ownerId': pid,
            'runtimeState': 'RUNNING', 'archivedAt': None, 'version': 0,
            'baseCurrency': 'USDC', 'mode': mode, **econ}
    if hwm is not None:
        acct['highWaterEquity'] = core.to128(Decimal(hwm))
    return acct


def canonical_buy(price='60000', inv='54000', deploy='40000', snap='snap1', **over):
    base = {'asset': 'BTC', 'action': 'BUY', 'actionable': True, 'decisionSnapshotId': snap,
            'decisionId': 'd1', 'decisionInputsHash': 'h1', 'engineVersion': 'albert-decide-v2',
            'mandateVersion': 'mv1', 'invalidationPrice': inv, 'currentPrice': price,
            'mandateChecks': {'excluded': False, 'inApprovedUniverse': True, 'withinCap': True,
                              'withinRiskBudget': True, 'mandateComplete': True},
            'eligible': True, 'recommendedDeployNowUsd': deploy, 'fresh': True, 'sellPlan': None}
    base.update(over)
    return base


MANDATE = {'max_alloc_pct': {'BTC': 50}, 'max_trade_risk_pct': '2',
           'max_drawdown_pct': '20', 'reserve_pct': '0'}


def _eq(acct, px='60000', fresh=True):
    return core.compute_equity(acct, Decimal(px) if px else None, fresh)


# ============================ 1. canonical binding ========================== #
def test_market_driver_cannot_manufacture_actions():
    src = open(os.path.join(os.path.dirname(core.__file__), 'core.py')).read()
    for banned in ('marketPosture', '_md_cached', 'market_driver', 'marketDriver', 'driverChainId'):
        assert banned not in src, 'core must not consult market-driver: %s' % banned


def test_only_canonical_buy_passes_entry_gates():
    acct = make_acct()
    ei = _eq(acct)
    ok = core.run_entry_gates(acct=acct, canonical=canonical_buy(), mark_px=Decimal('60000'),
                              mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert ok['reject'] is None and ok['qty'] > 0


@pytest.mark.parametrize('action', ['WAIT', 'HOLD', 'SELL'])
def test_wait_hold_sell_cannot_create_buy_entry(action):
    acct = make_acct()
    ei = _eq(acct)
    can = canonical_buy(action=action, actionable=(action == 'SELL'))
    res = core.run_entry_gates(acct=acct, canonical=can, mark_px=Decimal('60000'),
                               mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert res['reject'] == 'NO_ACTIONABLE_DECISION'


# ============================ 2. gates reject correctly ===================== #
def test_excluded_rejected():
    acct = make_acct(); ei = _eq(acct)
    can = canonical_buy(); can['mandateChecks']['excluded'] = True
    assert core.run_entry_gates(acct=acct, canonical=can, mark_px=Decimal('60000'),
                                mark_fresh=True, mandate=MANDATE, equity_info=ei)['reject'] == 'NOT_APPROVED'


def test_incomplete_mandate_rejected():
    acct = make_acct(); ei = _eq(acct)
    can = canonical_buy(); can['mandateChecks']['mandateComplete'] = False
    assert core.run_entry_gates(acct=acct, canonical=can, mark_px=Decimal('60000'),
                                mark_fresh=True, mandate=MANDATE, equity_info=ei)['reject'] == 'MANDATE_INCOMPLETE'


def test_reserve_preserved_blocks_when_no_deployable():
    acct = make_acct(reserve_pct='100'); ei = _eq(acct)
    r = core.run_entry_gates(acct=acct, canonical=canonical_buy(), mark_px=Decimal('60000'),
                             mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert r['reject'] == 'INSUFFICIENT_DEPLOYABLE'


def test_allocation_cap_zero_rejects():
    acct = make_acct(); ei = _eq(acct)
    m = dict(MANDATE); m['max_alloc_pct'] = {'BTC': 0}
    r = core.run_entry_gates(acct=acct, canonical=canonical_buy(), mark_px=Decimal('60000'),
                             mark_fresh=True, mandate=m, equity_info=ei)
    assert r['reject'] == 'BELOW_MIN_NOTIONAL'


def test_drawdown_breaker_rejects():
    # hwm 200k, flat equity 100k -> drawdown -50% < -20% limit
    acct = make_acct(hwm='200000'); ei = _eq(acct)
    assert ei['drawdownPct'] < Decimal('-20')
    r = core.run_entry_gates(acct=acct, canonical=canonical_buy(), mark_px=Decimal('60000'),
                             mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert r['reject'] == 'DRAWDOWN_BREAKER'


def test_stale_market_rejects():
    acct = make_acct(); ei = core.compute_equity(acct, Decimal('60000'), True)
    r = core.run_entry_gates(acct=acct, canonical=canonical_buy(), mark_px=Decimal('60000'),
                             mark_fresh=False, mandate=MANDATE, equity_info=ei)
    assert r['reject'] == 'STALE'


# ============================ 3. sizing reduces never enlarges ============== #
def test_sizing_only_reduces():
    acct = make_acct(starting='100000'); ei = _eq(acct)
    can = canonical_buy(deploy='999999999')  # absurdly large canonical amount
    r = core.run_entry_gates(acct=acct, canonical=can, mark_px=Decimal('60000'),
                             mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert r['reject'] is None
    # never exceeds deployable, allocation room, or the canonical amount
    assert r['notional'] <= ei['deployableCash']
    assert r['notional'] <= Decimal('50000')      # 50% alloc cap of 100k equity
    assert r['notional'] <= Decimal('999999999')


# ============================ 4. exact decimal accounting =================== #
def test_no_float_drift_over_many_fills(col):
    acct = make_acct(starting='100000'); col.insert_one(dict(acct))
    aid, pid = acct['paperAccountId'], acct['ownerId']
    can = canonical_buy(deploy='10000')
    total_notional = Decimal('0')
    for i in range(5):
        a = col.find_one({'paperAccountId': aid})
        ei = _eq(a)
        sizing = core.run_entry_gates(acct=a, canonical=can, mark_px=Decimal('60000'),
                                      mark_fresh=True, mandate=MANDATE, equity_info=ei)
        assert sizing['reject'] is None
        res, err, code = core.apply_buy_atomic(col, aid, pid, a['version'], 'k%d' % i, 'p%d' % i, sizing, can)
        assert err is None, err
        total_notional += Decimal(res['notional'])
    a = col.find_one({'paperAccountId': aid})
    cash = core.D(a['cash'])
    lot = core._btc_lot(a)
    # cash + costBasis must reconcile EXACTLY to starting capital (fees are inside notional/costBasis)
    assert cash + core.D(lot['costBasis']) == Decimal('100000.00')
    assert cash == (Decimal('100000.00') - total_notional)
    # ledger has exactly 5 economic FILLs
    fills = [e for e in a['ledger'] if e.get('eventType') == 'FILL']
    assert len(fills) == 5


# ============================ 5. equity / drawdown truth ==================== #
def test_missing_price_never_zero_equity(col):
    acct = make_acct(starting='50000'); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    sizing = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='10000'),
                                  mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                                  equity_info=_eq(acct))
    core.apply_buy_atomic(col, aid, pid, 0, 'k', 'p', sizing, canonical_buy())
    a = col.find_one({'paperAccountId': aid})
    # No price for a held position -> UNAVAILABLE, NOT zero.
    ei = core.compute_equity(a, None, False)
    assert ei['available'] is False and ei['equity'] is None and ei['markStatus'] == 'UNAVAILABLE'
    assert ei['drawdownPct'] is None
    # Stale price for a held position -> STALE, not a fabricated value.
    ei2 = core.compute_equity(a, Decimal('60000'), False)
    assert ei2['available'] is False and ei2['markStatus'] == 'STALE'


def test_high_water_survives_reload_and_never_resets(col):
    acct = make_acct(starting='50000', hwm='120000')
    # give it a lot worth ~60k so equity = 50k cash? Use cash 50k + 1 BTC.
    acct['lots'] = [{'lotId': 'pp_x', 'asset': 'BTC', 'status': 'OPEN', 'qty': core.to128(Decimal('1')),
                     'avgEntry': core.to128(Decimal('50000')), 'costBasis': core.to128(Decimal('50000')),
                     'positionVersion': 1}]
    aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    a = col.find_one({'paperAccountId': aid})
    ei = core.compute_equity(a, Decimal('60000'), True)     # equity 110k < hwm 120k
    assert ei['highWater'] == Decimal('120000')
    assert ei['drawdownPct'] < 0
    core.update_high_water(col, aid, pid, ei['equity'])       # 110k must NOT lower the 120k HWM
    a2 = col.find_one({'paperAccountId': aid})               # simulate reload
    assert core.D(a2['highWaterEquity']) == Decimal('120000')
    ei2 = core.compute_equity(a2, Decimal('40000'), True)    # deeper drop
    assert ei2['highWater'] == Decimal('120000')             # still anchored to stored HWM


# ============================ 6. atomic + idempotency ======================= #
def test_atomic_buy_applies_once_balanced(col):
    acct = make_acct(starting='100000'); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    sizing = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='10000'),
                                  mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                                  equity_info=_eq(acct))
    res, err, code = core.apply_buy_atomic(col, aid, pid, 0, 'key1', 'prop1', sizing, canonical_buy())
    assert err is None and res['side'] == 'BUY'
    a = col.find_one({'paperAccountId': aid})
    assert a['version'] == 1 and a['accountSequence'] == 1
    assert 'prop1' in a['consumedProposals'] and 'key1' in a['idemKeys']


def test_idempotent_retry_same_key_no_duplicate(col):
    acct = make_acct(); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    sizing = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='10000'),
                                  mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                                  equity_info=_eq(acct))
    r1, e1, _ = core.apply_buy_atomic(col, aid, pid, 0, 'dupkey', 'prop1', sizing, canonical_buy())
    a1 = col.find_one({'paperAccountId': aid})
    r2, e2, code2 = core.apply_buy_atomic(col, aid, pid, a1['version'], 'dupkey', 'prop1', sizing, canonical_buy())
    a2 = col.find_one({'paperAccountId': aid})
    assert e1 is None and e2 is None and r1 == r2
    assert a2['version'] == a1['version']  # no second economic effect
    assert len([e for e in a2['ledger'] if e.get('eventType') == 'FILL']) == 1


def test_concurrent_double_tap_one_effect(col):
    acct = make_acct(); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    sizing = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='10000'),
                                  mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                                  equity_info=_eq(acct))
    results = []

    def worker():
        results.append(core.apply_buy_atomic(col, aid, pid, 0, 'samekey', 'prop1', sizing, canonical_buy()))

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    a = col.find_one({'paperAccountId': aid})
    assert len([e for e in a['ledger'] if e.get('eventType') == 'FILL']) == 1, 'exactly one economic effect'
    assert a['version'] == 1
    assert all(e is None for _, e, _ in results)  # both callers see success (one applied, one idempotent)


def test_different_keys_same_proposal_second_conflicts(col):
    acct = make_acct(); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    sizing = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='10000'),
                                  mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                                  equity_info=_eq(acct))
    r1, e1, _ = core.apply_buy_atomic(col, aid, pid, 0, 'keyA', 'prop1', sizing, canonical_buy())
    a1 = col.find_one({'paperAccountId': aid})
    r2, e2, code2 = core.apply_buy_atomic(col, aid, pid, a1['version'], 'keyB', 'prop1', sizing, canonical_buy())
    assert e1 is None and e2 == 'ALREADY_CONSUMED' and code2 == 409
    a2 = col.find_one({'paperAccountId': aid})
    assert len([e for e in a2['ledger'] if e.get('eventType') == 'FILL']) == 1


def test_sell_reduce_only_realized(col):
    acct = make_acct(starting='100000'); aid, pid = acct['paperAccountId'], acct['ownerId']
    col.insert_one(dict(acct))
    buy = core.run_entry_gates(acct=acct, canonical=canonical_buy(deploy='30000'),
                               mark_px=Decimal('60000'), mark_fresh=True, mandate=MANDATE,
                               equity_info=_eq(acct))
    core.apply_buy_atomic(col, aid, pid, 0, 'kb', 'pb', buy, canonical_buy())
    a = col.find_one({'paperAccountId': aid})
    ex = core.run_exit_gates(acct=a, mark_px=Decimal('66000'), mark_fresh=True, full=True)
    assert ex['reject'] is None
    res, err, code = core.apply_sell_atomic(col, aid, pid, ex, source='manual_close', idem_key='ks')
    assert err is None and res['side'] == 'SELL'
    a2 = col.find_one({'paperAccountId': aid})
    assert core._btc_lot(a2) is None                     # fully closed (reduce-only to zero)
    assert len(a2['closedLots']) == 1
    assert core.D(a2['realizedPnl']) == Decimal(res['realized'])


# ============================ 7. revalidation ============================== #
def test_revalidate_ok_predicate():
    can = canonical_buy(snap='S1')
    assert core.revalidate_ok(can, 'BUY', 'S1') is True
    assert core.revalidate_ok(can, 'BUY', 'S2') is False        # mandate change -> new snapshot
    assert core.revalidate_ok(canonical_buy(snap='S1', fresh=False), 'BUY', 'S1') is False
    assert core.revalidate_ok(canonical_buy(snap='S1', action='SELL', actionable=True), 'BUY', 'S1') is False
    assert core.revalidate_ok(None, 'BUY', 'S1') is False


# ================= HTTP boundary (deployment: execution OFF) ================ #
def _seed_user():
    uid = str(uuid.uuid4())
    _db['users'].insert_one({'_id': uid, 'google_sub': 'm2_' + uid, 'email': 'roger.parenzee@gmail.com', 'name': 'M2'})
    tok = uuid.uuid4().hex + uuid.uuid4().hex
    _db['auth_sessions'].insert_one({'_id': str(uuid.uuid4()), 'token': tok, 'user_id': uid,
                                     'created_at': datetime.datetime.utcnow(),
                                     'expires_at': datetime.datetime.utcnow() + datetime.timedelta(days=1)})
    return uid, tok, 'u_' + uid


@pytest.fixture(scope='module')
def http_user():
    uid, tok, pid = _seed_user()
    yield {'uid': uid, 'tok': tok, 'pid': pid}
    _db['users'].delete_one({'_id': uid})
    _db['auth_sessions'].delete_many({'user_id': uid})
    ids = [a['paperAccountId'] for a in _db['albert_paper_accounts'].find({'ownerId': pid})]
    _db['albert_paper_accounts'].delete_many({'ownerId': pid})
    _db['albert_paper_proposals'].delete_many({'paperAccountId': {'$in': ids}})


def _h(tok):
    return {'Authorization': 'Bearer ' + tok}


def test_http_autopilot_mode_allowed_on_create(http_user):
    # M4 restored Autopilot as a selectable mode.
    r = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                      json={'mode': 'PAPER_AUTOPILOT', 'name': 'auto'})
    assert r.status_code == 200 and r.json()['mode'] == 'PAPER_AUTOPILOT'


def test_http_autopilot_allowed_on_set_mode(http_user):
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                         json={'name': 'modeacct'}).json()
    r = requests.patch(BASE + '/api/v1/albert/paper/accounts/%s/mode' % acct['paperAccountId'],
                       headers=_h(http_user['tok']),
                       json={'mode': 'PAPER_AUTOPILOT', 'confirm': True, 'idempotencyKey': 'm2mode1'})
    assert r.status_code == 200

    r2 = requests.patch(BASE + '/api/v1/albert/paper/accounts/%s/mode' % acct['paperAccountId'],
                        headers=_h(http_user['tok']),
                        json={'mode': 'NONSENSE', 'confirm': True, 'idempotencyKey': 'm2mode2'})
    assert r2.status_code == 422


def test_http_dashboard_execution_flag(http_user):
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                         json={'name': 'dashacct'}).json()
    d = requests.get(BASE + '/api/v1/albert/paper/accounts/%s/dashboard' % acct['paperAccountId'],
                     headers=_h(http_user['tok'])).json()
    exec_on = os.environ.get('PAPER_EXECUTION_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    auto_on = os.environ.get('PAPER_AUTOPILOT_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    assert d['integrity']['executionEnabled'] is exec_on
    assert d['integrity']['autopilotEnabled'] is auto_on


def _seed_proposal(acct_id, pid, expires_delta_min=30, snap='snapX'):
    prop_id = 'prop_' + uuid.uuid4().hex[:12]
    _db['albert_paper_proposals'].insert_one({
        'proposalId': prop_id, 'paperAccountId': acct_id, 'ownerId': pid, 'asset': 'BTC', 'side': 'BUY',
        'orderType': 'MARKET', 'decisionSnapshotId': snap, 'version': 0,
        'notionalValue': '1000.00', 'referencePrice': '60000.00', 'status': 'CREATED',
        'createdAt': datetime.datetime.utcnow().isoformat(),
        'expiresAt': (datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta_min)).isoformat(),
        'paperOnly': True})
    return prop_id


def test_http_approve_requires_body_fields(http_user):
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                         json={'name': 'a1'}).json()
    pid = _seed_proposal(acct['paperAccountId'], http_user['pid'])
    r = requests.post(BASE + '/api/v1/albert/paper/proposals/%s/approve' % pid,
                      headers=_h(http_user['tok']), json={})
    assert r.status_code == 422


def test_http_approve_blocked_or_revalidated(http_user):
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                         json={'name': 'a2'}).json()
    pid = _seed_proposal(acct['paperAccountId'], http_user['pid'], snap='snapX')
    r = requests.post(BASE + '/api/v1/albert/paper/proposals/%s/approve' % pid,
                      headers=_h(http_user['tok']),
                      json={'expectedProposalVersion': 0, 'decisionSnapshotId': 'snapX',
                            'idempotencyKey': 'k1', 'quantity': 999, 'price': 1})  # client economic fields ignored
    exec_on = os.environ.get('PAPER_EXECUTION_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    if exec_on:
        # execution ON: fake snapshot never matches current canonical -> rejected on revalidation
        assert r.status_code in (200, 409), r.text
        if r.status_code == 200:
            assert r.json().get('proposalStatus') == 'REJECTED_ON_REVALIDATION'
    else:
        assert r.status_code == 503


def test_http_expired_proposal_rejected(http_user):
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(http_user['tok']),
                         json={'name': 'a3'}).json()
    pid = _seed_proposal(acct['paperAccountId'], http_user['pid'], expires_delta_min=-5)
    r = requests.post(BASE + '/api/v1/albert/paper/proposals/%s/approve' % pid,
                      headers=_h(http_user['tok']),
                      json={'expectedProposalVersion': 0, 'decisionSnapshotId': 'snapX', 'idempotencyKey': 'k2'})
    assert r.status_code == 409
