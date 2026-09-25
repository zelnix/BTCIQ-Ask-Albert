"""Ask-Albert remediation — Milestone 4 (Background Paper Autopilot) tests.

Drives the REAL background worker code path (server._autopilot_process_account)
with the canonical decision + market mark monkeypatched, so nothing depends on a
browser/dashboard. Proves the tested behaviours from the M4 spec.

Run:  cd /app/backend && python -m pytest tests/test_m4_autopilot.py -v
"""
import os
import sys
import uuid
import datetime
from decimal import Decimal

import pytest

# Flags ON for the isolated acceptance config (matches deployed .env for M4).
os.environ['PAPER_EXECUTION_ENABLED'] = 'true'
os.environ['PAPER_AUTOPILOT_ENABLED'] = 'true'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from albert.paper import core  # noqa: E402

PA = server.paper_accounts_col
LED = lambda a: [e for e in (a.get('ledger') or []) if e.get('side')]  # noqa: E731


def _mk_account(mode='PAPER_AUTOPILOT', state='RUNNING', reserve='0', lot=None):
    econ = core.new_account_economics(Decimal('100000'), Decimal(reserve))
    a = {'paperAccountId': 'pa_m4_' + uuid.uuid4().hex[:10], 'ownerId': 'u_m4_' + uuid.uuid4().hex[:6],
         'name': 'm4', 'baseCurrency': 'USDC', 'mode': mode, 'runtimeState': state,
         'mandateVersion': 0, 'version': 0, 'archivedAt': None,
         'createdAt': datetime.datetime.utcnow().isoformat(), **econ}
    if lot:
        a['lots'] = [lot]
    PA.insert_one(dict(a))
    return PA.find_one({'paperAccountId': a['paperAccountId']})


def _canon(action='BUY', snap=None, deploy='20000', fresh=True, minutes_ago=2, sell=None):
    dt = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {'asset': 'BTC', 'action': action, 'actionable': action in ('BUY', 'SELL'),
            'decisionSnapshotId': snap or ('s_' + uuid.uuid4().hex[:8]), 'decisionId': 'd',
            'decisionInputsHash': 'h', 'engineVersion': 'albert-decide-v2', 'mandateVersion': 'mv',
            'invalidationPrice': '54000', 'currentPrice': '60000',
            'mandateChecks': {'excluded': False, 'inApprovedUniverse': True, 'withinCap': True,
                              'withinRiskBudget': True, 'mandateComplete': True},
            'eligible': True, 'recommendedDeployNowUsd': deploy, 'fresh': fresh, 'sellPlan': sell,
            'decisionTime': dt}


MANDATE = {'max_alloc_pct': {'BTC': 90}, 'max_trade_risk_pct': '5', 'max_drawdown_pct': '30'}


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    # Fresh mark observed AFTER the decision (independent observation).
    mark_ts = datetime.datetime.utcnow().isoformat()
    monkeypatch.setattr(server, '_paper_btc_mark', lambda: (Decimal('60000'), True, mark_ts))
    monkeypatch.setattr(server._albert_deps, 'get_mandate', lambda pid: dict(MANDATE))
    yield


def _cleanup(a):
    PA.delete_one({'paperAccountId': a['paperAccountId']})
    server.paper_notif_col.delete_many({'paperAccountId': a['paperAccountId']})


def test_autopilot_trades_with_dashboard_closed(monkeypatch):
    a = _mk_account()
    c = _canon('BUY')
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)                 # worker only — no dashboard call
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 1 and core.account_position_qty(a2) > 0
    assert a2['lastProcessedDecisionSnapshotId'] == c['decisionSnapshotId']
    assert a2['marketObservationCursor'] is not None
    _cleanup(a)


def test_one_decision_at_most_one_effect_and_restart_no_repeat(monkeypatch):
    a = _mk_account()
    c = _canon('BUY')
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)
    # "restart": re-read persisted account and process again -> already consumed.
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    server._autopilot_process_account(a2)
    a3 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a3)) == 1                              # exactly one economic effect
    _cleanup(a)


def test_two_workers_cannot_duplicate(monkeypatch):
    a = _mk_account()
    c = _canon('BUY')
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    # Both "workers" read the SAME stale account (neither has consumed the snapshot),
    # then both apply — the auto:<acct>:<sid> idempotency key collapses to one effect.
    stale = PA.find_one({'paperAccountId': a['paperAccountId']})
    server._autopilot_process_account(dict(stale))
    server._autopilot_process_account(dict(stale))
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 1
    _cleanup(a)


def test_wait_and_hold_never_trade(monkeypatch):
    for action in ('WAIT', 'HOLD'):
        a = _mk_account()
        c = _canon(action)
        monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
        server._autopilot_process_account(a)
        a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
        assert len(LED(a2)) == 0
        assert a2['lastProcessedDecisionSnapshotId'] == c['decisionSnapshotId']  # recorded, not traded
        _cleanup(a)


def test_stale_decision_or_price_never_trades(monkeypatch):
    # stale decision
    a = _mk_account()
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: _canon('BUY', fresh=False))
    server._autopilot_process_account(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 0 and a2.get('lastProcessedDecisionSnapshotId') is None  # retry later
    _cleanup(a)
    # stale price
    b = _mk_account()
    stale_ts = datetime.datetime.utcnow().isoformat()
    monkeypatch.setattr(server, '_paper_btc_mark', lambda: (Decimal('60000'), False, stale_ts))
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: _canon('BUY'))
    server._autopilot_process_account(b)
    b2 = PA.find_one({'paperAccountId': b['paperAccountId']})
    assert len(LED(b2)) == 0
    _cleanup(b)


def test_independent_observation_required(monkeypatch):
    a = _mk_account()
    # Mark timestamp EQUAL to the decision time (not strictly after) -> must not trade.
    dt = (datetime.datetime.utcnow() - datetime.timedelta(minutes=1)).isoformat()
    c = _canon('BUY'); c['decisionTime'] = dt
    monkeypatch.setattr(server, '_paper_btc_mark', lambda: (Decimal('60000'), True, dt))
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 0                              # waits for a later observation
    _cleanup(a)


def test_mandate_reserve_rejects_entry(monkeypatch):
    a = _mk_account(reserve='100')                       # 100% reserve -> nothing deployable
    c = _canon('BUY')
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 0
    assert any(e.get('eventType') == 'AUTO_SKIPPED' for e in (a2.get('ledger') or []))
    _cleanup(a)


def test_pause_stops_new_entries(monkeypatch):
    a = _mk_account(state='PAUSED_BY_USER')
    c = _canon('BUY')
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a2)) == 0
    assert a2.get('lastProcessedDecisionSnapshotId') is None  # snapshot left for resume
    _cleanup(a)


def test_sell_reduces_automatically(monkeypatch):
    lot = {'lotId': 'pp_m4', 'asset': 'BTC', 'status': 'OPEN', 'qty': core.to128(Decimal('1')),
           'avgEntry': core.to128(Decimal('50000')), 'costBasis': core.to128(Decimal('50000')),
           'positionVersion': 1, 'invalidationPrice': core.to128(Decimal('40000'))}
    a = _mk_account(lot=lot)
    c = _canon('SELL', sell={'recommendedDeltaUsd': '-30000', 'action': 'TRIM_50'})
    monkeypatch.setattr(server, '_paper_canonical_decision', lambda pid: c)
    server._autopilot_process_account(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    sells = [e for e in LED(a2) if e.get('side') == 'SELL']
    assert len(sells) == 1 and core.account_position_qty(a2) < Decimal('1')  # reduced
    _cleanup(a)


def test_dashboard_read_creates_no_economic_events(monkeypatch):
    a = _mk_account()
    v0 = a['version']; n0 = len(a.get('ledger') or [])
    # Simulate repeated dashboard reads (read-only equity + reconcile).
    for _ in range(3):
        server._paper_equity(a, persist=False)
        core.reconcile(a)
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert a2['version'] == v0 and len(a2.get('ledger') or []) == n0
    _cleanup(a)
