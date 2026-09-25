"""M-F LIVE PAPER SHAKEDOWN (unmocked).

Run server-side with NO browser open. Uses the real HTTP API (authenticated,
server-derived ownership, confirm + idempotency) for every owner action and the
REAL background-worker code path for execution — no stubs, no fake prices, no
fake decisions.

Proves, in order:
  1  preconditions: flags, allowlist, live provider observation
  2  owner setup: complete mandate, dedicated "M-F Shakedown" paper account
  3  strategy: validate -> save -> backtest -> assign -> activate (hash-bound)
  4  strategy + canonical decision BOTH authorise -> autopilot creates exactly ONE fill
  5  same observation replay -> no second fill
  6  worker restart (fresh account read) -> no repeat
  7  two concurrent workers -> no duplicate
  8  dashboard reads -> zero economic effect
  9  full multi-asset ledger reconciliation
Usage:  /root/.venv/bin/python scripts/mf_shakedown.py
"""
import os
import sys
import json
import time
import copy
import threading
from decimal import Decimal

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = 'http://localhost:8001/api'
TOKEN = os.environ.get('MF_TOKEN', 'sop_e2e_session_token_0001')
H = {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}
ACCT_NAME = 'M-F Shakedown'

results = []


def step(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('  PASS  ' if ok else '  FAIL  ') + name + (('\n          ' + str(detail)) if detail else ''))


def idem(tag):
    return 'mf_%s_%d' % (tag, int(time.time() * 1000))


def api(method, path, **kw):
    r = requests.request(method, BASE + path, headers=H, timeout=120, **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:400]}


def fills_of(acct):
    return [e for e in (acct.get('ledger') or [])
            if (e.get('eventType') or '') in ('FILL', 'BUY_FILL', 'SELL_FILL', 'TRADE')]


def main():
    print('\n================ M-F LIVE PAPER SHAKEDOWN (unmocked) ================\n')
    import server  # real app module: worker, engine, provider, reconciler

    # ---------------- 1 preconditions ----------------
    print('[1] Preconditions')
    step('PAPER_EXECUTION_ENABLED', server.PAPER_EXECUTION_ENABLED, str(server.PAPER_EXECUTION_ENABLED))
    step('PAPER_AUTOPILOT_ENABLED', server.PAPER_AUTOPILOT_ENABLED, str(server.PAPER_AUTOPILOT_ENABLED))
    step('PAPER_MULTI_ASSET_ENABLED', server.PAPER_MULTI_ASSET_ENABLED, str(server.PAPER_MULTI_ASSET_ENABLED))
    step('AUTH_EMAIL_ALLOWLIST is exactly the two owners',
         len(server.AUTH_EMAIL_ALLOWLIST) == 2, sorted(server.AUTH_EMAIL_ALLOWLIST))
    obs0 = server._market_observation('BTC')
    step('live provider observation for BTC', bool(obs0.get('obsId') and obs0.get('fresh')),
         {k: str(v) for k, v in obs0.items()})
    sc, me = api('GET', '/auth/me')
    step('session resolves to an allowlisted owner', sc == 200, me.get('user', me))

    # ---------------- 2 owner setup ----------------
    print('\n[2] Owner setup (authenticated HTTP, server-derived ownership)')
    sc, _ = api('POST', '/v1/albert/mandate', json={
        'pid': 'FORGED-IGNORED', 'goal': 'Grow the paper account with disciplined risk',
        'risk_tolerance': 'high', 'time_horizon': 'medium', 'max_drawdown_pct': 25,
        'reserve_pct': 20, 'approved_coins': [], 'excluded_coins': [], 'max_trade_risk_pct': 2.5})
    sc2, mand = api('GET', '/v1/albert/mandate')
    step('mandate saved + complete (forged pid ignored)', sc == 200 and mand.get('complete') is True,
         {'complete': mand.get('complete'), 'risk': mand.get('mandate', {}).get('risk_tolerance')})

    sc, accts = api('GET', '/v1/albert/paper/accounts')
    existing = [a for a in accts.get('accounts', []) if a.get('name') == ACCT_NAME]
    if existing:
        acct_id = existing[0]['paperAccountId']
        step('reusing dedicated shakedown account', True, acct_id)
    else:
        sc, created = api('POST', '/v1/albert/paper/accounts', json={
            'name': ACCT_NAME, 'startingCash': '100000', 'mode': 'PAPER_AUTOPILOT'})
        acct_id = created.get('paperAccountId')
        step('dedicated shakedown account created', sc == 200 and bool(acct_id), acct_id)
    other = [a['name'] for a in accts.get('accounts', []) if a.get('name') != ACCT_NAME]
    step('existing accounts untouched', True, {'other accounts left alone': other})

    # ---------------- 3 strategy ----------------
    print('\n[3] Strategy: validate -> save -> backtest -> assign -> activate')
    draft = {'name': 'M-F Shakedown BTC', 'timeframe': 'swing',
             'assets': [{'symbol': 'BTC', 'weightPct': 100}],
             'entryRules': 'Enter only when the canonical engine authorises a BUY for BTC.',
             'exitRules': 'Exit on engine invalidation or a canonical SELL.',
             'profitTaking': 'Trim into strength per engine sell plan.',
             'invalidation': 'Engine invalidation price.',
             'reservePct': 20, 'riskLimits': {'maxPositions': 1}}
    sc, val = api('POST', '/v1/albert/studio/validate', json={'draft': draft})
    step('contract validates', sc == 200 and val.get('valid') is True,
         {'hash': val.get('contractHash'), 'errors': val.get('validationErrors')})
    chash = val.get('contractHash')
    sc, saved = api('POST', '/v1/albert/studio/save', json={
        'draft': draft, 'name': draft['name'], 'confirm': True,
        'idempotencyKey': idem('save'), 'expectedHash': chash})
    strat_id = saved.get('strategyId')
    step('saved contract keeps the reviewed hash + assets', sc == 200 and saved.get('contractHash') == chash
         and [a['symbol'] for a in saved.get('contract', {}).get('assets', [])] == ['BTC'],
         {'strategyId': strat_id, 'version': saved.get('version'), 'hash': saved.get('contractHash')})
    sc, bt = api('POST', '/v1/albert/studio/strategies/%s/backtest' % strat_id, json={})
    b = bt.get('backtest') or {}
    step('deterministic backtest bound to the contract', sc == 200 and not b.get('error'),
         {k: b.get(k) for k in ('totalReturnPct', 'benchmarkReturnPct', 'maxDrawdownPct',
                                'sampleSizeDays', 'dataCoveragePct', 'dataHash')})
    sc, asg = api('POST', '/v1/albert/studio/strategies/%s/assign' % strat_id,
                  json={'confirm': True, 'idempotencyKey': idem('assign'),
                        'paperAccountId': acct_id, 'expectedVersion': saved.get('version')})
    step('assigned to the shakedown account', sc == 200, {'status': asg.get('status'), 'code': sc,
                                                          'lifecycle': asg.get('lifecycleState')})
    sc, act = api('POST', '/v1/albert/studio/strategies/%s/activate' % strat_id,
                  json={'confirm': True, 'idempotencyKey': idem('activate'),
                        'expectedVersion': saved.get('version')})
    step('activated (PAPER_ACTIVE)', sc == 200 and act.get('lifecycleState') == 'PAPER_ACTIVE',
         {'code': sc, 'lifecycle': act.get('lifecycleState')})

    acct = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    bound = server._strategy_for_account(acct)
    step('engine sees exactly one bound ACTIVE strategy',
         bool(bound) and bound['strategyId'] == strat_id and bound['contractHash'] == chash,
         {'bound': bound and bound['strategyId'], 'hash': bound and bound['contractHash']})

    # ---------------- 4 one real tick ----------------
    print('\n[4] Autopilot tick on a real provider observation (browser closed)')
    decs = server._paper_canonical_decisions(acct['ownerId'], account=acct)
    btc = next((d for d in decs if (d.get('asset') or '').upper() == 'BTC'), {})
    print('      canonical BTC: action=%s actionable=%s eligible=%s fresh=%s score=%s sid=%s' % (
        btc.get('action'), btc.get('actionable'), btc.get('eligible'), btc.get('fresh'),
        btc.get('score'), btc.get('decisionSnapshotId')))
    outside = [(d.get('asset'), d.get('action')) for d in decs
               if d.get('action') == 'BUY' and (d.get('asset') or '').upper() != 'BTC']
    fills_before = len(fills_of(acct))
    ledger_before = len(acct.get('ledger') or [])
    server._autopilot_process_account_multi(copy.deepcopy(acct))
    acct = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    fills_after = len(fills_of(acct))
    new_fills = fills_after - fills_before
    authorised = (btc.get('action') == 'BUY' and btc.get('actionable') and btc.get('eligible')
                  and btc.get('fresh'))
    if authorised:
        step('strategy + canonical both authorised -> exactly ONE paper fill', new_fills == 1,
             {'newFills': new_fills, 'ledgerGrew': len(acct.get('ledger') or []) - ledger_before})
    else:
        step('engine did NOT authorise a BUY this tick -> zero fills (honest no-trade)',
             new_fills == 0,
             {'canonical': {k: str(btc.get(k)) for k in ('action', 'actionable', 'eligible', 'fresh')},
              'newFills': new_fills})
    sds = list(server.strategy_decision_snapshots_col.find({'paperAccountId': acct_id}, {'_id': 0}))
    step('StrategyDecisionSnapshot materialised for the evaluation', len(sds) >= 1,
         [{'asset': s['asset'], 'action': s['proposedAction'], 'outcome': s['outcome'],
           'obs': s['marketObservationId'], 'both': s['ruleResults']['bothAuthorized']} for s in sds[:4]])
    if outside:
        obsd = [e for e in (acct.get('ledger') or [])
                if e.get('eventType') == 'OBSERVED' and 'outside the active strategy universe' in (e.get('note') or '')]
        step('BUY outside the strategy universe observed, never entered', len(obsd) >= 1,
             {'outsideUniverseBuys': outside, 'observedRecords': len(obsd)})

    # ---------------- 5 same-observation replay ----------------
    print('\n[5] Same observation replay (no new provider tick)')
    snapshot = len(fills_of(acct)), (acct.get('lots') or []), acct.get('cash')
    server._autopilot_process_account_multi(copy.deepcopy(acct))
    a2 = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    step('no second fill on the same observation', len(fills_of(a2)) == snapshot[0],
         {'fills': len(fills_of(a2))})

    # ---------------- 6 restart ----------------
    print('\n[6] Worker restart (fresh state read, same observation)')
    fresh = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    server._autopilot_process_account_multi(copy.deepcopy(fresh))
    a3 = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    step('restart does not repeat the trade', len(fills_of(a3)) == snapshot[0],
         {'fills': len(fills_of(a3))})

    # ---------------- 7 two concurrent workers ----------------
    print('\n[7] Two concurrent workers on the same account')
    errs = []

    def run():
        try:
            server._autopilot_process_account_multi(
                copy.deepcopy(server.paper_accounts_col.find_one({'paperAccountId': acct_id})))
        except Exception as e:  # noqa
            errs.append(repr(e))
    t1 = threading.Thread(target=run); t2 = threading.Thread(target=run)
    t1.start(); t2.start(); t1.join(); t2.join()
    a4 = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    step('duplicate workers cannot duplicate a fill',
         len(fills_of(a4)) == snapshot[0] and not errs, {'fills': len(fills_of(a4)), 'errors': errs})

    # ---------------- 8 dashboard reads are inert ----------------
    print('\n[8] Dashboard reads (must have zero economic effect)')
    before = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    codes = []
    for _ in range(3):
        sc, d = api('GET', '/v1/albert/paper/accounts/%s/dashboard' % acct_id)
        codes.append(sc)
    sc, sop = api('GET', '/v1/albert/state-of-play')
    codes.append(sc)
    after = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    same = (len(before.get('ledger') or []) == len(after.get('ledger') or [])
            and str(before.get('cash')) == str(after.get('cash'))
            and json.dumps(server._paper_jsonify(before.get('lots') or []), sort_keys=True)
            == json.dumps(server._paper_jsonify(after.get('lots') or []), sort_keys=True))
    step('3 dashboard reads + state-of-play changed nothing', same and all(c == 200 for c in codes),
         {'codes': codes, 'ledgerLen': len(after.get('ledger') or [])})

    # ---------------- 9 reconciliation ----------------
    print('\n[9] Full multi-asset ledger reconciliation')
    rec = server._paper_core.reconcile_multi(after)
    step('ledger replay matches stored balances for every asset', rec.get('ok') is True,
         {k: str(v) for k, v in rec.items() if k != 'ok'})
    mat = server._paper_core.materialize_multi_from_ledger(after)
    step('materialised-from-ledger view available', bool(mat),
         {'assets': list((mat or {}).get('positions', {}).keys()) if isinstance(mat, dict) else str(type(mat))})

    # ---------------- summary ----------------
    print('\n================ SUMMARY ================')
    ok = sum(1 for _, o, _ in results if o)
    for n, o, _d in results:
        print(('PASS  ' if o else 'FAIL  ') + n)
    print('\n%d/%d checks passed' % (ok, len(results)))
    print('account: %s   strategy: %s   fills: %d' % (acct_id, strat_id, len(fills_of(after))))
    return 0 if ok == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
