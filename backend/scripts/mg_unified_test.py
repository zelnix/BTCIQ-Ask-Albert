"""M-G shakedown: unified Strategy <-> Paper journey (live, unmocked).

Verifies: build/save -> start paper (explicit) -> per-strategy status/approval/activity/
performance -> switch approval mode -> stop -> restart -> aggregate overview.
Per-strategy isolation: each strategy gets its OWN wallet and its own balance.
"""
import json
import os
import sys
import uuid

import requests

BASE = os.environ.get('MG_BASE', 'http://localhost:8001/api')
TOKEN = os.environ.get('MG_TOKEN', 'sop_e2e_session_token_0001')
S = requests.Session()
S.headers.update({'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})

PASS, FAIL = [], []


def chk(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' :: ' + str(extra)[:300]) if extra and not cond else ''))


def post(path, body=None):
    r = S.post(BASE + path, data=json.dumps(body or {}), timeout=90)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:300]}


def get(path):
    r = S.get(BASE + path, timeout=90)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:300]}


def k():
    return 'mg_' + uuid.uuid4().hex[:12]


print('== M-G unified journey shakedown ==')

# ---- 1. Save a fresh strategy (build -> save) --------------------------------
draft = {'name': 'M-G Unified Test', 'timeframe': 'swing',
         'assets': [{'symbol': 'BTC', 'weightPct': 60}, {'symbol': 'ETH', 'weightPct': 40}],
         'entryRules': 'Buy pullbacks to the 20-day average.',
         'exitRules': 'Exit on trend invalidation.', 'profitTaking': 'Scale out at +15%.',
         'invalidation': 'Close below the 50-day average.', 'reservePct': 20,
         'riskLimits': {'maxPositions': 2, 'maxTradeRiskPct': 2}}
sc, val = post('/v1/albert/studio/validate', {'draft': draft})
chk('validate returns a hash', sc == 200 and val.get('contractHash'), val)
sc, saved = post('/v1/albert/studio/save',
                 {'draft': draft, 'name': draft['name'], 'confirm': True,
                  'idempotencyKey': k(), 'expectedHash': val.get('contractHash')})
chk('save creates a strategy', sc == 200 and saved.get('strategyId'), saved)
SID = saved.get('strategyId')
if not SID:
    print('cannot continue without a strategy'); sys.exit(1)
chk('saved strategy is NOT trading (explicit start required)',
    saved.get('lifecycleState') == 'REVIEWED', saved.get('lifecycleState'))

sc, panel = get(f'/v1/albert/studio/strategies/{SID}/paper')
chk('new strategy paperStatus=SAVED', panel.get('paperStatus') == 'SAVED', panel)
chk('no wallet before start', panel.get('paperAccountId') is None, panel)

# ---- 2. Observe mode must be impossible -------------------------------------
sc, r = post(f'/v1/albert/studio/strategies/{SID}/start-paper',
             {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'OBSERVE'})
chk('OBSERVE is rejected (mode retired)', sc == 422, (sc, r))

# ---- 3. Guards --------------------------------------------------------------
sc, r = post(f'/v1/albert/studio/strategies/{SID}/start-paper', {'idempotencyKey': k()})
chk('start requires explicit confirmation', sc == 428, (sc, r))
sc, r = post(f'/v1/albert/studio/strategies/{SID}/start-paper', {'confirm': True})
chk('start requires idempotencyKey', sc == 422, (sc, r))
sc, r = post(f'/v1/albert/studio/strategies/{SID}/approval-mode',
             {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'AUTOPILOT'})
chk('cannot set approval before starting', sc == 409, (sc, r))

# ---- 4. Start paper trading (default REVIEW) --------------------------------
START_KEY = k()
sc, started = post(f'/v1/albert/studio/strategies/{SID}/start-paper',
                   {'confirm': True, 'idempotencyKey': START_KEY, 'approvalMode': 'REVIEW',
                    'expectedVersion': saved.get('version')})
chk('start-paper succeeds', sc == 200 and started.get('paperStatus') == 'LIVE', (sc, started))
chk('trade approval defaults to Review and approve',
    started.get('approvalMode') == 'REVIEW', started.get('approvalMode'))
ACCT = started.get('paperAccountId')
chk('a dedicated wallet was created', bool(ACCT), started)

sc, replay = post(f'/v1/albert/studio/strategies/{SID}/start-paper',
                  {'confirm': True, 'idempotencyKey': START_KEY, 'approvalMode': 'REVIEW'})
chk('start is idempotent (replay returns the same result)',
    sc == 200 and replay.get('paperAccountId') == ACCT, (sc, replay))

# ---- 5. Per-strategy panel carries status/approval/activity/performance -----
sc, panel = get(f'/v1/albert/studio/strategies/{SID}/paper')
chk('panel: status LIVE', panel.get('paperStatus') == 'LIVE', panel.get('paperStatus'))
chk('panel: approval REVIEW', panel.get('approvalMode') == 'REVIEW', panel.get('approvalMode'))
perf = panel.get('performance') or {}
chk('panel: performance has its own value', perf.get('value') is not None, perf)
chk('panel: own starting balance is $100,000 (isolated)',
    str(perf.get('startingCash')) == '100000.00', perf.get('startingCash'))
chk('panel: activity ledger present', isinstance(panel.get('activity'), list) and panel['activity'], panel.get('activity'))
chk('panel: pendingApprovals is a list', isinstance(panel.get('pendingApprovals'), list), panel)

# ---- 6. Switch to Autopilot and back ---------------------------------------
sc, r = post(f'/v1/albert/studio/strategies/{SID}/approval-mode',
             {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'AUTOPILOT'})
chk('switch to Autopilot', sc == 200 and r.get('approvalMode') == 'AUTOPILOT', (sc, r))
sc, r = post(f'/v1/albert/studio/strategies/{SID}/approval-mode',
             {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'REVIEW'})
chk('switch back to Review and approve', sc == 200 and r.get('approvalMode') == 'REVIEW', (sc, r))

# ---- 7. Isolation: a second strategy gets its OWN wallet -------------------
d2 = dict(draft, name='M-G Isolation Test', assets=[{'symbol': 'SOL', 'weightPct': 100}],
          riskLimits={'maxPositions': 1, 'maxTradeRiskPct': 2})
sc, v2 = post('/v1/albert/studio/validate', {'draft': d2})
sc, s2 = post('/v1/albert/studio/save', {'draft': d2, 'name': d2['name'], 'confirm': True,
                                         'idempotencyKey': k(), 'expectedHash': v2.get('contractHash')})
SID2 = s2.get('strategyId')
sc, st2 = post(f'/v1/albert/studio/strategies/{SID2}/start-paper',
               {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'AUTOPILOT'})
chk('second strategy starts independently', sc == 200 and st2.get('paperStatus') == 'LIVE', (sc, st2))
chk('second strategy has a DIFFERENT wallet (per-strategy balance)',
    st2.get('paperAccountId') and st2.get('paperAccountId') != ACCT,
    (ACCT, st2.get('paperAccountId')))

# ---- 8. Stop / restart ------------------------------------------------------
sc, r = post(f'/v1/albert/studio/strategies/{SID2}/stop-paper', {'confirm': True, 'idempotencyKey': k()})
chk('stop-paper succeeds', sc == 200 and r.get('paperStatus') == 'STOPPED', (sc, r))
sc, p2 = get(f'/v1/albert/studio/strategies/{SID2}/paper')
chk('stopped strategy keeps its wallet + history',
    p2.get('paperAccountId') == st2.get('paperAccountId') and (p2.get('performance') or {}).get('value') is not None,
    p2)
sc, r = post(f'/v1/albert/studio/strategies/{SID2}/start-paper',
             {'confirm': True, 'idempotencyKey': k(), 'approvalMode': 'REVIEW'})
chk('restart reuses the SAME wallet (no reset)',
    sc == 200 and r.get('paperAccountId') == st2.get('paperAccountId'), (sc, r))

# ---- 9. Strategy list carries paper status inline --------------------------
sc, lst = get('/v1/albert/studio/strategies')
rows = {s['strategyId']: s for s in (lst.get('strategies') or [])}
chk('list includes paperStatus per strategy',
    rows.get(SID, {}).get('paperStatus') == 'LIVE', rows.get(SID))
chk('list includes approvalMode per strategy',
    rows.get(SID, {}).get('approvalMode') == 'REVIEW', rows.get(SID))

# ---- 10. Aggregate Paper Trading view --------------------------------------
sc, ov = get('/v1/albert/paper/overview')
chk('overview returns ready', sc == 200 and ov.get('status') == 'ready', (sc, ov))
tot = ov.get('totals') or {}
names = [s['strategyId'] for s in (ov.get('strategies') or [])]
chk('overview lists both new strategies', SID in names and SID2 in names, names)
chk('overview aggregates live strategies', (tot.get('liveStrategies') or 0) >= 2, tot)
chk('overview aggregates combined value', tot.get('value') is not None, tot)
chk('overview aggregates combined P&L', tot.get('pnlUsd') is not None, tot)
chk('overview carries combined activity', isinstance(ov.get('activity'), list) and ov['activity'], len(ov.get('activity') or []))
chk('overview has NO account-creation surface (review only)',
    'mode' not in ov and 'setup' not in ov, list(ov.keys()))

# ---- 11. Cleanup: stop + archive the test strategies ------------------------
for s in (SID, SID2):
    post(f'/v1/albert/studio/strategies/{s}/stop-paper', {'confirm': True, 'idempotencyKey': k()})
    post(f'/v1/albert/studio/strategies/{s}/unassign', {'confirm': True, 'idempotencyKey': k()})
    post(f'/v1/albert/studio/strategies/{s}/archive', {'confirm': True, 'idempotencyKey': k()})
sc, ov2 = get('/v1/albert/paper/overview')
left = [s['strategyId'] for s in (ov2.get('strategies') or [])]
chk('archived test strategies drop out of the overview',
    SID not in left and SID2 not in left, left)

print('\n== %d passed, %d failed ==' % (len(PASS), len(FAIL)))
if FAIL:
    print('FAILED: ' + ', '.join(FAIL))
sys.exit(1 if FAIL else 0)
