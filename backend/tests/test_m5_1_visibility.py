"""Ask-Albert remediation — Milestone 5.1 (visibility + live-data) tests.

Covers the two NEW behaviours introduced in M5.1:
  * LIVE market-cap RANK resolution + honest freshness fallback (never a silent
    static rank: unavailable/stale => conservative SPEC tier + available=False).
  * ROTATION AUDIT RECORDS: a reduce-first / buy-after-cash capital rotation is
    recorded and later completed, with full provenance.

Run:  cd /app/backend && python -m pytest tests/test_m5_1_visibility.py -v
"""
import os
import sys
import uuid
import datetime
from decimal import Decimal

import pytest

os.environ['PAPER_EXECUTION_ENABLED'] = 'true'
os.environ['PAPER_AUTOPILOT_ENABLED'] = 'true'
os.environ['PAPER_MULTI_ASSET_ENABLED'] = 'true'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from albert.paper import core  # noqa: E402

PA = server.paper_accounts_col
ROT = server.paper_rotations_col
LED = lambda a: [e for e in (a.get('ledger') or []) if e.get('side')]  # noqa: E731

MANDATE = {'max_alloc_pct': {}, 'max_trade_risk_pct': '3', 'max_drawdown_pct': '30',
           'approved_coins': [], 'excluded_coins': []}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(server._albert_deps, 'get_mandate', lambda pid: dict(MANDATE))
    yield


# ============================ live-rank freshness =========================== #
def test_rank_resolution_fresh_available():
    ranks = {'ETH': {'rank': 2, 'source': 'coingecko', 'snapshotId': 'snap1',
                     'observedAt': 't0', 'fresh': True}}
    meta = {'available': True, 'snapshotId': 'snap1', 'source': 'coingecko', 'observedAt': 't0', 'fresh': True}
    rank, tier, rm = server._paper_rank_for('ETH', ranks, meta)
    assert rank == 2 and tier == 'LARGE'
    assert rm['available'] is True and rm['source'] == 'coingecko' and rm['snapshotId'] == 'snap1'
    assert rm['appliedTier'] == 'LARGE'


def test_rank_unavailable_falls_back_to_conservative_spec():
    rank, tier, rm = server._paper_rank_for('ETH', {}, {'available': False, 'fresh': False,
                                                        'snapshotId': None, 'source': None, 'observedAt': None})
    assert rank is None and tier == 'SPEC'           # conservative, never a silent static rank
    assert rm['available'] is False and rm['appliedTier'] == 'SPEC'


def test_rank_stale_falls_back_to_conservative_spec():
    ranks = {'SOL': {'rank': 5, 'source': 'coingecko', 'snapshotId': 's', 'observedAt': 't', 'fresh': False}}
    meta = {'available': True, 'fresh': False, 'snapshotId': 's', 'source': 'coingecko', 'observedAt': 't'}
    rank, tier, rm = server._paper_rank_for('SOL', ranks, meta)
    assert tier == 'SPEC' and rm['available'] is False and rm['rank'] == 5   # rank shown, but not applied


def test_btc_keeps_its_tier_regardless_of_rank_feed():
    rank, tier, rm = server._paper_rank_for('BTC', {}, {'available': False, 'fresh': False})
    assert tier == 'BTC'


def test_live_ranks_helper_returns_meta_shape():
    ranks, meta = server._paper_live_ranks()
    assert set(meta.keys()) >= {'available', 'snapshotId', 'source', 'observedAt', 'fresh'}


# ============================ rotation records ============================== #
def _acct(cash, lots):
    econ = core.new_account_economics(Decimal(cash), Decimal('0'))
    a = {'paperAccountId': 'pa_m51_' + uuid.uuid4().hex[:10], 'ownerId': 'u_m51_' + uuid.uuid4().hex[:6],
         'name': 'm51', 'baseCurrency': 'USDC', 'mode': 'PAPER_AUTOPILOT', 'runtimeState': 'RUNNING',
         'version': 0, 'archivedAt': None, 'createdAt': datetime.datetime.utcnow().isoformat(), **econ}
    a['lots'] = lots
    PA.insert_one(dict(a))
    return PA.find_one({'paperAccountId': a['paperAccountId']})


def _lot(sym, qty, avg):
    return {'lotId': 'pp_' + uuid.uuid4().hex[:8], 'asset': sym, 'status': 'OPEN',
            'qty': core.to128(Decimal(qty)), 'avgEntry': core.to128(Decimal(avg)),
            'costBasis': core.to128(Decimal(qty) * Decimal(avg)), 'positionVersion': 1,
            'invalidationPrice': None}


def _canon(sym, action, score, deploy='20000', price='100', inv='90', minutes_ago=2):
    dt = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {'asset': sym, 'action': action, 'actionable': action in ('BUY', 'SELL'),
            'decisionSnapshotId': 's_' + sym + '_' + uuid.uuid4().hex[:6], 'decisionId': 'd_' + sym,
            'decisionInputsHash': 'h', 'engineVersion': 'albert-decide-v2', 'mandateVersion': 'mv',
            'regime': 'BULL', 'score': score, 'confidence': '80', 'rank': None,
            'currentPrice': price, 'invalidationPrice': inv,
            'mandateChecks': {'excluded': False, 'inApprovedUniverse': True, 'withinCap': True,
                              'withinRiskBudget': True, 'mandateComplete': True},
            'eligible': True, 'recommendedDeployNowUsd': deploy, 'sellPlan': None,
            'fresh': True, 'decisionTime': dt}


def test_rotation_reduce_then_buy_produces_completed_record(monkeypatch):
    # Altcoin exposure is maxed by a weak ADA holding (70% of a 100k equity); a much
    # stronger ETH BUY is blocked by the altcoin ceiling -> deterministic rotation.
    a = _acct('30000', [_lot('ADA', '70000', '1')])
    ROT.delete_many({'paperAccountId': a['paperAccountId']})
    ranks = {'ETH': {'rank': 2, 'source': 'coingecko', 'snapshotId': 'snapZ', 'observedAt': 't', 'fresh': True},
             'ADA': {'rank': 9, 'source': 'coingecko', 'snapshotId': 'snapZ', 'observedAt': 't', 'fresh': True}}
    meta = {'available': True, 'snapshotId': 'snapZ', 'source': 'coingecko', 'observedAt': 't', 'fresh': True}
    monkeypatch.setattr(server, '_paper_live_ranks', lambda: (ranks, meta))
    decisions = [_canon('ETH', 'BUY', score='95', deploy='20000', price='3000', inv='2700'),
                 _canon('ADA', 'HOLD', score='60', deploy='0', price='1', inv='0.9')]
    monkeypatch.setattr(server, '_paper_canonical_decisions', lambda pid: decisions)
    mts = datetime.datetime.utcnow().isoformat()
    marks = {'ETH': (Decimal('3000'), True), 'ADA': (Decimal('1'), True)}
    monkeypatch.setattr(server, '_paper_mark', lambda s: (marks.get(s.upper(), (None, False))[0],
                                                          marks.get(s.upper(), (None, False))[1], mts))

    # ---- Tick 1: reduce the laggard (ADA), record REDUCED, ETH not yet bought ----
    server._autopilot_process_account_multi(PA.find_one({'paperAccountId': a['paperAccountId']}))
    rec = ROT.find_one({'paperAccountId': a['paperAccountId']})
    assert rec is not None
    assert rec['reducedAsset'] == 'ADA' and rec['targetAsset'] == 'ETH'
    assert rec['status'] == 'REDUCED' and rec['allocationMovedUsd'] is None
    for k in ('reducedScore', 'targetScore', 'regime', 'reducedSnapshotId', 'targetSnapshotId',
              'rankingSnapshotId', 'primaryReason'):
        assert k in rec
    assert rec['rankingSnapshotId'] == 'snapZ'
    a1 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert core.position_qty(a1, 'ADA') == 0            # ADA exited (freed capital)
    assert core.position_qty(a1, 'ETH') == 0            # ETH NOT bought on the reduce tick

    # ---- Tick 2: capital is now free -> ETH buys, rotation record COMPLETED ----
    mts2 = (datetime.datetime.utcnow() + datetime.timedelta(seconds=5)).isoformat()
    monkeypatch.setattr(server, '_paper_mark', lambda s: (marks.get(s.upper(), (None, False))[0],
                                                          marks.get(s.upper(), (None, False))[1], mts2))
    server._autopilot_process_account_multi(PA.find_one({'paperAccountId': a['paperAccountId']}))
    a2 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert core.position_qty(a2, 'ETH') > 0             # stronger opportunity now funded
    rec2 = ROT.find_one({'_id': rec['_id']})
    assert rec2['status'] == 'COMPLETED' and rec2['allocationMovedUsd'] is not None
    assert rec2['completedAt'] is not None
    # rotation only ever SELLS then BUYS later -> never exceeds cash
    assert core.D(a2['cash']) >= 0
    ROT.delete_many({'paperAccountId': a['paperAccountId']})
    PA.delete_one({'paperAccountId': a['paperAccountId']})
    server.paper_notif_col.delete_many({'paperAccountId': a['paperAccountId']})
