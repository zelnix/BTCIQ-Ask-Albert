"""Ask-Albert remediation — Milestone 1 (Safety Containment) acceptance tests.

Covers the P0 properties for M1 ONLY:
  * Every user-owned new route requires a valid server session (401 without one).
  * Identity is server-derived; a client-supplied pid/ownerId cannot change the owner.
  * Cross-user access/mutation is impossible (404, existence not revealed).
  * Guessing object IDs does not bypass ownership.
  * Expired sessions immediately lose access.
  * Diagnostics report only evidence actually collected (no fabricated PASS;
    unsupported checks are NOT_TESTABLE; every check carries source + redaction_count).
  * Diagnostics never claims "Everything checks out" when a check is NOT_TESTABLE.
  * Support-report notes are sanitised (secrets/emails/URLs redacted).
  * Simulated paper EXECUTION is disabled by feature flag (approve/close -> 503).
  * Paper dashboard integrity is never labelled HEALTHY and lastReconciledAt is null.

Run:  cd /app/backend && python -m pytest tests/test_m1_containment.py -v
These tests hit the live uvicorn instance on :8001 and seed disposable accounts.
"""
import os
import uuid
import datetime

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get('M1_TEST_BASE', 'http://localhost:8001')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'btciq')

_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]
users_col = _db['users']
sessions_col = _db['auth_sessions']
paper_accounts_col = _db['albert_paper_accounts']
paper_proposals_col = _db['albert_paper_proposals']
paper_positions_col = _db['albert_paper_positions']

_TAG = 'm1test_' + uuid.uuid4().hex[:8]


def _make_user():
    uid = str(uuid.uuid4())
    users_col.insert_one({'_id': uid, 'google_sub': f'{_TAG}_{uid}',
                          'email': f'{uid}@example.test', 'name': 'M1 Test'})
    token = uuid.uuid4().hex + uuid.uuid4().hex
    sessions_col.insert_one({'_id': str(uuid.uuid4()), 'token': token, 'user_id': uid,
                             'created_at': datetime.datetime.utcnow(),
                             'expires_at': datetime.datetime.utcnow() + datetime.timedelta(days=1)})
    return uid, token, f'u_{uid}'


def _expired_token(uid):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    sessions_col.insert_one({'_id': str(uuid.uuid4()), 'token': token, 'user_id': uid,
                             'created_at': datetime.datetime.utcnow() - datetime.timedelta(days=2),
                             'expires_at': datetime.datetime.utcnow() - datetime.timedelta(days=1)})
    return token


@pytest.fixture(scope='module')
def users():
    a = _make_user()
    b = _make_user()
    exp = _expired_token(a[0])
    yield {'A': a, 'B': b, 'expired': exp}
    # Cleanup disposable data.
    for uid, _, pid in (a, b):
        users_col.delete_one({'_id': uid})
        sessions_col.delete_many({'user_id': uid})
        accts = list(paper_accounts_col.find({'ownerId': pid}))
        ids = [x['paperAccountId'] for x in accts]
        paper_accounts_col.delete_many({'ownerId': pid})
        paper_proposals_col.delete_many({'paperAccountId': {'$in': ids}})
        paper_positions_col.delete_many({'paperAccountId': {'$in': ids}})


def _h(token):
    return {'Authorization': f'Bearer {token}'}


# --------------------------------------------------------------------------- #
# 1. Authentication required (401) on every protected route                    #
# --------------------------------------------------------------------------- #
PROTECTED = [
    ('GET', '/api/v1/albert/paper/accounts'),
    ('GET', '/api/v1/albert/equity-history'),
    ('GET', '/api/v1/albert/driver-alerts/subs'),
    ('GET', '/api/v1/albert/trader-home'),
    ('GET', '/api/v1/albert/performance'),
    ('GET', '/api/v1/albert/paper-portfolio'),
    ('POST', '/api/v1/albert/diagnostics/checkups'),
    ('POST', '/api/v1/albert/driver-alerts/subs'),
]


@pytest.mark.parametrize('method,path', PROTECTED)
def test_unauthenticated_returns_401(method, path):
    r = requests.request(method, BASE + path, json={})
    assert r.status_code == 401, f'{method} {path} -> {r.status_code}'


def test_expired_session_returns_401(users):
    r = requests.get(BASE + '/api/v1/albert/paper/accounts', headers=_h(users['expired']))
    assert r.status_code == 401


def test_client_pid_ignored_query_does_not_bypass(users):
    # Even passing a legacy ?pid= must not authenticate.
    r = requests.get(BASE + '/api/v1/albert/paper/accounts?pid=' + users['A'][2])
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 2. Client-supplied pid/ownerId cannot change the resolved owner              #
# --------------------------------------------------------------------------- #
def test_client_pid_override_cannot_set_owner(users):
    a_uid, a_tok, a_pid = users['A']
    b_uid, b_tok, b_pid = users['B']
    # A creates an account but LIES that owner is B.
    r = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(a_tok),
                      json={'pid': b_pid, 'ownerId': b_pid, 'name': 'override-attempt'})
    assert r.status_code == 200, r.text
    acct = r.json()
    assert acct['ownerId'] == a_pid, 'owner must be derived from session, not client body'
    # B must NOT see A's account.
    rb = requests.get(BASE + '/api/v1/albert/paper/accounts', headers=_h(b_tok))
    ids_b = [x['paperAccountId'] for x in rb.json().get('accounts', [])]
    assert acct['paperAccountId'] not in ids_b
    # A DOES see it.
    ra = requests.get(BASE + '/api/v1/albert/paper/accounts', headers=_h(a_tok))
    ids_a = [x['paperAccountId'] for x in ra.json().get('accounts', [])]
    assert acct['paperAccountId'] in ids_a


# --------------------------------------------------------------------------- #
# 3. Cross-user access / mutation is impossible (404)                          #
# --------------------------------------------------------------------------- #
def test_cross_user_cannot_access_account(users):
    a_uid, a_tok, a_pid = users['A']
    b_uid, b_tok, b_pid = users['B']
    r = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(a_tok),
                      json={'name': 'A private'})
    acct_id = r.json()['paperAccountId']
    # B tries to read A's dashboard / trade-log / change mode / lifecycle.
    assert requests.get(BASE + f'/api/v1/albert/paper/accounts/{acct_id}/dashboard',
                        headers=_h(b_tok)).status_code == 404
    assert requests.get(BASE + f'/api/v1/albert/paper/accounts/{acct_id}/trade-log',
                        headers=_h(b_tok)).status_code == 404
    assert requests.patch(BASE + f'/api/v1/albert/paper/accounts/{acct_id}/mode',
                          headers=_h(b_tok), json={'mode': 'OBSERVE'}).status_code == 404
    assert requests.post(BASE + f'/api/v1/albert/paper/accounts/{acct_id}/pause',
                         headers=_h(b_tok), json={}).status_code == 404
    # A can read its own dashboard.
    assert requests.get(BASE + f'/api/v1/albert/paper/accounts/{acct_id}/dashboard',
                        headers=_h(a_tok)).status_code == 200


def test_guessing_ids_returns_404(users):
    a_tok = users['A'][1]
    assert requests.get(BASE + '/api/v1/albert/paper/accounts/pa_deadbeef/dashboard',
                        headers=_h(a_tok)).status_code == 404
    assert requests.get(BASE + '/api/v1/albert/diagnostics/runs/diag_nope',
                        headers=_h(a_tok)).status_code == 404
    assert requests.post(BASE + '/api/v1/albert/paper/proposals/prop_nope/approve',
                         headers=_h(a_tok), json={}).status_code == 404


# --------------------------------------------------------------------------- #
# 4. Diagnostics honesty                                                       #
# --------------------------------------------------------------------------- #
def test_diagnostics_no_fabricated_pass(users):
    a_tok = users['A'][1]
    r = requests.post(BASE + '/api/v1/albert/diagnostics/checkups', headers=_h(a_tok),
                      json={'client': {'app_version': '1.0.0'}})
    assert r.status_code == 200, r.text
    body = r.json()
    checks = {c['check_id']: c for c in body['technical_details']['checks']}
    # Device/client-owned + non-observable checks must be NOT_TESTABLE, not PASS.
    for cid in ('app.version.compatibility', 'app.runtime.integrity', 'app.cache.integrity',
                'network.internet.reachability', 'network.btciq.tls', 'engine.health'):
        assert checks[cid]['result'] == 'NOT_TESTABLE', f'{cid} was {checks[cid]["result"]}'
    # Auth is derived from the (valid) session -> PASS with SESSION_VALID evidence.
    assert checks['auth.session.validity']['result'] == 'PASS'
    assert checks['auth.session.validity']['evidence_code'] == 'SESSION_VALID'
    # Every check carries source + redaction_count.
    for cid, c in checks.items():
        assert 'source' in c and c['source'] in ('SERVER_OBSERVED', 'CLIENT_REPORTED'), cid
        assert 'redaction_count' in c, cid
    # Run envelope totals redactions + surfaces incomplete-checks honesty.
    assert 'not_testable_count' in body['summary']
    assert body['summary']['not_testable_count'] > 0
    assert body['summary']['checks_incomplete'] is True
    assert body['summary']['title'] != 'Everything checks out'


def test_diagnostics_report_sanitises_secrets(users):
    a_tok = users['A'][1]
    run = requests.post(BASE + '/api/v1/albert/diagnostics/checkups', headers=_h(a_tok),
                        json={}).json()
    run_id = run['run_id']
    dirty = ('please help. my token is Bearer abc123xyz and email me at me@example.com '
             'see http://evil.example.com/?token=leak')
    r = requests.post(BASE + f'/api/v1/albert/diagnostics/runs/{run_id}/reports',
                      headers=_h(a_tok), json={'user_note': dirty})
    assert r.status_code == 200, r.text
    assert r.json()['redactionCount'] >= 3


def test_diagnostics_report_cross_user_404(users):
    a_tok = users['A'][1]
    b_tok = users['B'][1]
    run = requests.post(BASE + '/api/v1/albert/diagnostics/checkups', headers=_h(a_tok),
                        json={}).json()
    run_id = run['run_id']
    # B cannot read or report on A's run.
    assert requests.get(BASE + f'/api/v1/albert/diagnostics/runs/{run_id}',
                        headers=_h(b_tok)).status_code == 404
    assert requests.post(BASE + f'/api/v1/albert/diagnostics/runs/{run_id}/reports',
                         headers=_h(b_tok), json={'user_note': 'x'}).status_code == 404


# --------------------------------------------------------------------------- #
# 5. Paper execution is disabled by feature flag                               #
# --------------------------------------------------------------------------- #
def test_paper_dashboard_integrity_not_healthy(users):
    a_tok = users['A'][1]
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(a_tok),
                         json={'name': 'integrity-check'}).json()
    d = requests.get(BASE + f"/api/v1/albert/paper/accounts/{acct['paperAccountId']}/dashboard",
                     headers=_h(a_tok)).json()
    integ = d['integrity']
    assert integ['status'] != 'HEALTHY'
    assert integ['executionWorker'] == 'NONE'
    assert integ['reconciliation'] == 'NONE'
    assert integ['lastReconciledAt'] is None
    assert integ['executionEnabled'] is False
    assert integ['autopilotEnabled'] is False


def test_approve_blocked_while_execution_disabled(users):
    a_uid, a_tok, a_pid = users['A']
    acct = requests.post(BASE + '/api/v1/albert/paper/accounts', headers=_h(a_tok),
                         json={'name': 'exec-flag'}).json()
    acct_id = acct['paperAccountId']
    # Seed an open proposal directly (a durable proposal that a user could approve).
    prop_id = 'prop_' + uuid.uuid4().hex[:12]
    paper_proposals_col.insert_one({
        'proposalId': prop_id, 'paperAccountId': acct_id, 'ownerId': a_pid, 'asset': 'BTC', 'side': 'BUY',
        'orderType': 'MARKET', 'notionalValue': '1000.00', 'referencePrice': '60000.00',
        'decisionSnapshotId': 'snapM1', 'version': 0,
        'status': 'CREATED', 'createdAt': datetime.datetime.utcnow().isoformat(),
        'expiresAt': (datetime.datetime.utcnow() + datetime.timedelta(minutes=30)).isoformat(),
        'paperOnly': True})
    # Approving must be refused with 503 because execution is disabled (M2 contract:
    # the required approval fields are supplied so we reach the execution-flag gate).
    r = requests.post(BASE + f'/api/v1/albert/paper/proposals/{prop_id}/approve',
                      headers=_h(a_tok),
                      json={'expectedProposalVersion': 0, 'decisionSnapshotId': 'snapM1',
                            'idempotencyKey': 'm1key'})
    assert r.status_code == 503, r.text
    # Cancelling (no economic effect) is still allowed.
    rc = requests.post(BASE + f'/api/v1/albert/paper/proposals/{prop_id}/cancel',
                       headers=_h(a_tok), json={})
    assert rc.status_code == 200, rc.text


# --------------------------------------------------------------------------- #
# 6. Driver-alert subs: auth + owner-scope + 422 on bad input                  #
# --------------------------------------------------------------------------- #
def test_driver_alert_subs_validation_and_scope(users):
    a_tok = users['A'][1]
    assert requests.post(BASE + '/api/v1/albert/driver-alerts/subs', headers=_h(a_tok),
                         json={'horizon': 'NONSENSE', 'enabled': True}).status_code == 422
    ok = requests.post(BASE + '/api/v1/albert/driver-alerts/subs', headers=_h(a_tok),
                       json={'horizon': 'SWING', 'enabled': True})
    assert ok.status_code == 200, ok.text
    subs = requests.get(BASE + '/api/v1/albert/driver-alerts/subs', headers=_h(a_tok)).json()
    assert subs['subscriptions'].get('SWING') is True
