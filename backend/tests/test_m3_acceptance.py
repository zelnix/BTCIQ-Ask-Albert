"""Ask-Albert remediation — Milestone 3 (lean acceptance) tests.

Adds the two acceptance proofs requested for a personal, paper-only tool:
  * LEDGER REPLAY: the stored projection equals a pure replay of the accepted
    append-only economic events (cash, BTC qty, cost basis, fees, realised P&L,
    account sequence, proposal-consumption).
  * APPROVAL RETRY / RESTART: a retry after an uncertain response (and a simulated
    process restart / duplicate delivery) produces exactly ONE economic effect.

Run:  cd /app/backend && python -m pytest tests/test_m3_acceptance.py -v
"""
import os
import sys
import uuid
from decimal import Decimal

import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from albert.paper import core  # noqa: E402

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'btciq')
_db = MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture()
def col():
    c = _db['test_m3_' + uuid.uuid4().hex[:8]]
    yield c
    c.drop()


def _acct(col, starting='100000'):
    econ = core.new_account_economics(Decimal(starting), Decimal('0'))
    a = {'paperAccountId': 'pa_' + uuid.uuid4().hex[:12], 'ownerId': 'u_m3',
         'runtimeState': 'RUNNING', 'archivedAt': None, 'version': 0, 'baseCurrency': 'USDC',
         'mode': 'APPROVAL_REQUIRED', **econ}
    col.insert_one(dict(a))
    return a


def _canon(deploy='10000', snap='s'):
    return {'asset': 'BTC', 'action': 'BUY', 'actionable': True, 'decisionSnapshotId': snap,
            'decisionId': 'd', 'decisionInputsHash': 'h', 'engineVersion': 'albert-decide-v2',
            'mandateVersion': 'mv', 'invalidationPrice': '54000', 'currentPrice': '60000',
            'mandateChecks': {'excluded': False, 'inApprovedUniverse': True, 'withinCap': True,
                              'withinRiskBudget': True, 'mandateComplete': True},
            'eligible': True, 'recommendedDeployNowUsd': deploy, 'fresh': True, 'sellPlan': None}


MANDATE = {'max_alloc_pct': {'BTC': 90}, 'max_trade_risk_pct': '5', 'max_drawdown_pct': '30'}


def _buy(col, a, key, prop, deploy='10000', px='60000'):
    a = col.find_one({'paperAccountId': a['paperAccountId']})
    ei = core.compute_equity(a, Decimal(px), True)
    sizing = core.run_entry_gates(acct=a, canonical=_canon(deploy), mark_px=Decimal(px),
                                  mark_fresh=True, mandate=MANDATE, equity_info=ei)
    assert sizing['reject'] is None, sizing
    return core.apply_buy_atomic(col, a['paperAccountId'], a['ownerId'], a['version'],
                                 key, prop, sizing, _canon(deploy))


def test_ledger_replay_matches_projection(col):
    a = _acct(col, '100000')
    _buy(col, a, 'k1', 'p1', deploy='20000')
    _buy(col, a, 'k2', 'p2', deploy='15000')
    # partial sell
    a2 = col.find_one({'paperAccountId': a['paperAccountId']})
    ex = core.run_exit_gates(acct=a2, mark_px=Decimal('66000'), mark_fresh=True, full=True)
    core.apply_sell_atomic(col, a['paperAccountId'], a['ownerId'], ex, source='manual_close', idem_key='ks')

    a3 = col.find_one({'paperAccountId': a['paperAccountId']})
    recon = core.reconcile(a3)
    assert recon['ok'] is True, recon['checks']
    rep = recon['replay']
    lot = core._btc_lot(a3)
    assert (core.D(a3['cash'])) == rep['cash']
    assert (core.D((lot or {}).get('qty')) or Decimal('0')) == rep['qty']
    assert (core.D(a3['feesPaid'])) == rep['fees']
    assert (core.D(a3['realizedPnl'])) == rep['realizedPnl']
    assert a3['accountSequence'] >= rep['accountSequence']
    # consumption state replayed
    assert set(rep['consumedProposals']) <= set(a3['consumedProposals'])


def test_retry_after_uncertain_response_no_duplicate(col):
    a = _acct(col, '100000')
    r1, e1, _ = _buy(col, a, 'retrykey', 'p1', deploy='20000')
    assert e1 is None
    after = col.find_one({'paperAccountId': a['paperAccountId']})
    v_after = after['version']
    cash_after = core.D(after['cash'])
    # Client never received the response -> retries with the SAME idempotency key.
    r2, e2, code2 = core.apply_buy_atomic(col, a['paperAccountId'], a['ownerId'], v_after,
                                          'retrykey', 'p1', {'notional': Decimal('20000'),
                                          'fillPx': Decimal('60050'), 'fee': Decimal('80'),
                                          'qty': Decimal('0.33')}, _canon('20000'))
    a2 = col.find_one({'paperAccountId': a['paperAccountId']})
    assert e2 is None and r1 == r2           # same stored result returned
    assert a2['version'] == v_after           # NO second economic effect
    assert core.D(a2['cash']) == cash_after
    assert len([e for e in a2['ledger'] if e.get('side')]) == 1


def test_restart_after_consumption_then_duplicate_delivery(col):
    a = _acct(col, '100000')
    _buy(col, a, 'k1', 'p1', deploy='20000')
    # "restart": drop all in-memory state, re-read the persisted account fresh.
    reloaded = col.find_one({'paperAccountId': a['paperAccountId']})
    assert 'p1' in reloaded['consumedProposals']
    # duplicate delivery of the SAME proposal with a NEW key -> refused (already consumed)
    r, e, code = core.apply_buy_atomic(col, a['paperAccountId'], a['ownerId'], reloaded['version'],
                                       'k1b', 'p1', {'notional': Decimal('20000'), 'fillPx': Decimal('60050'),
                                       'fee': Decimal('80'), 'qty': Decimal('0.33')}, _canon('20000'))
    assert e == 'ALREADY_CONSUMED' and code == 409
    a2 = col.find_one({'paperAccountId': a['paperAccountId']})
    assert len([x for x in a2['ledger'] if x.get('side')]) == 1  # still exactly one effect


def test_out_of_order_sequences_monotonic(col):
    a = _acct(col, '100000')
    _buy(col, a, 'k1', 'p1', deploy='10000')
    _buy(col, a, 'k2', 'p2', deploy='10000')
    a2 = col.find_one({'paperAccountId': a['paperAccountId']})
    seqs = [e['accountSequence'] for e in a2['ledger'] if e.get('side')]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # strictly increasing, unique
