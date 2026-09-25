"""Milestone A — Albert state-of-play aggregate.

Verifies the single authenticated, owner-scoped aggregate that powers Albert Home
and Ask Albert:
  * the response carries the required top-level contract keys,
  * the portfolio is sourced from THIS owner's selected paper account,
  * a second owner cannot see the first owner's account (owner isolation),
  * account selection is honoured only for an owner-owned account.

Run:  cd /app/backend && python -m pytest tests/test_mA_state_of_play.py -v
"""
import os
import sys
import uuid
import datetime
from decimal import Decimal

os.environ['PAPER_MULTI_ASSET_ENABLED'] = 'true'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from albert.paper import core  # noqa: E402

PA = server.paper_accounts_col


def _mk_account(owner_uid, cash='100000', name='sop'):
    econ = core.new_account_economics(Decimal(cash), Decimal('0'))
    a = {'paperAccountId': 'pa_a_' + uuid.uuid4().hex[:10], 'ownerId': 'u_' + owner_uid,
         'name': name, 'baseCurrency': 'USDC', 'mode': 'OBSERVE', 'runtimeState': 'RUNNING',
         'version': 0, 'archivedAt': None, 'lots': [],
         'createdAt': datetime.datetime.utcnow().isoformat(), **econ}
    PA.insert_one(dict(a))
    return a


def _user(uid):
    return {'_id': uid, 'email': f'{uid}@example.com', 'name': uid}


def test_state_of_play_contract_and_portfolio_source():
    uid = 'sopA_' + uuid.uuid4().hex[:6]
    acct = _mk_account(uid, name='Owner A account')
    state = server._sop_build(_user(uid))
    # required contract keys (spec §5.1)
    for k in ('stateId', 'generatedAt', 'user', 'market', 'portfolio', 'strategies',
              'paper', 'attention', 'changesSinceLastVisit', 'dataQuality',
              'evidenceIndex', 'deepLinks'):
        assert k in state, f'missing {k}'
    # portfolio is sourced from THIS owner's paper account
    assert state['portfolio'] is not None
    assert state['portfolio']['source'] == 'PAPER_ACCOUNT'
    assert state['portfolio']['paperAccountId'] == acct['paperAccountId']
    assert state['portfolio']['totalValue'] == '100000.00'
    assert state['paper']['mode'] == 'OBSERVE'
    assert state['paperOnly'] is True


def test_owner_isolation():
    uidA = 'isoA_' + uuid.uuid4().hex[:6]
    uidB = 'isoB_' + uuid.uuid4().hex[:6]
    acctA = _mk_account(uidA, name='A only')
    acctB = _mk_account(uidB, name='B only')
    sA = server._sop_build(_user(uidA))
    sB = server._sop_build(_user(uidB))
    assert sA['portfolio']['paperAccountId'] == acctA['paperAccountId']
    assert sB['portfolio']['paperAccountId'] == acctB['paperAccountId']
    # A's aggregate never references B's account id, anywhere it is selected
    assert sA['paper']['selectedAccount']['paperAccountId'] == acctA['paperAccountId']
    assert acctB['paperAccountId'] != acctA['paperAccountId']


def test_select_account_is_owner_scoped():
    uidA = 'selA_' + uuid.uuid4().hex[:6]
    uidB = 'selB_' + uuid.uuid4().hex[:6]
    _mk_account(uidA, name='A default')
    acctA2 = _mk_account(uidA, name='A second')
    acctB = _mk_account(uidB, name='B account')
    pidA = 'u_' + uidA
    # requesting an owned account is honoured
    picked = server._sop_select_account(pidA, requested=acctA2['paperAccountId'])
    assert picked['paperAccountId'] == acctA2['paperAccountId']
    # requesting ANOTHER owner's account is ignored -> falls back to an owned account
    picked2 = server._sop_select_account(pidA, requested=acctB['paperAccountId'])
    assert picked2 is not None
    assert picked2['ownerId'] == pidA
    assert picked2['paperAccountId'] != acctB['paperAccountId']


def test_endpoint_wrapper_returns_ready():
    uid = 'epA_' + uuid.uuid4().hex[:6]
    _mk_account(uid)
    out = server.albert_state_of_play(account='', user=_user(uid))
    assert out['status'] == 'ready'
    assert out['owner']['id'] == uid
