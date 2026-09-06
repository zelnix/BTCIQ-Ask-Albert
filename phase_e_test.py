"""Phase E — Execution Safety Layer acceptance tests.
Run: python /app/phase_e_test.py"""
import sys, uuid, datetime
sys.path.insert(0, '/app/backend')
import requests, config
from albert.execution import ledger as L

B = 'http://localhost:8001'
P = Fa = 0
def ck(n, c, got=''):
    global P, Fa
    if c: P += 1; print('  PASS', n)
    else: Fa += 1; print('  FAIL', n, '::', got)

def setm(pid, m): requests.post(B+'/api/v1/albert/mandate', json={'pid': pid, 'mandate': m})
def setp(pid, usdc, pos): requests.post(B+'/api/v1/portfolio', json={'pid': pid, 'usdc': usdc, 'positions': pos})
def dec(pid): return requests.get(B+'/api/v1/albert/decisions', params={'pid': pid}).json()
def create(pid, asset, key, bps=None): return requests.post(B+'/api/v1/albert/order/create', json={'pid': pid, 'asset': asset, 'idempotencyKey': key, 'slippageBps': bps}).json()
def confirm(oid): return requests.post(B+f'/api/v1/albert/order/{oid}/confirm').json()
def execute(oid, q=None): return requests.post(B+f'/api/v1/albert/order/{oid}/execute', json=({'simulateFillQty': q} if q is not None else {})).json()
def cancel(oid): return requests.post(B+f'/api/v1/albert/order/{oid}/cancel').json()
def geto(oid): return requests.get(B+f'/api/v1/albert/order/{oid}').json()

def clean(pid):
    for c in (config.mandate_col, config.portfolio_col): c.delete_one({'_id': pid})
    for c in (config.decision_current_col, config.decision_snapshots_col, config.decision_history_col, config.order_intents_col, config.order_ledger_col, config.order_audit_col):
        c.delete_many({'pid': pid})
    config.paper_portfolio_col.delete_one({'_id': pid})

MAND = lambda: {'risk_tolerance': 'moderate', 'reserve_pct': 25, 'approved_coins': ['BTC', 'ETH', 'SOL'], 'max_alloc_pct': {'BTC': 40, 'ETH': 30, 'SOL': 20}, 'max_trade_risk_pct': 2}
def buy_asset(pid):
    d = dec(pid)
    return next((x['symbol'] for x in d['decisions'] if x['action'] == 'BUY'), None)

print('=== A: happy full fill -> reconcile -> portfolio view ===')
A = 'u_E_A'; clean(A); setm(A, MAND()); setp(A, 50000, [])
sym = buy_asset(A)
ck('A found a BUY asset', bool(sym), sym)
r = create(A, sym, 'k1'); oid = r['intent']['orderIntentId']
ck('A create -> PENDING_CONFIRMATION', r['intent']['state'] == 'PENDING_CONFIRMATION', r['intent']['state'])
ck('A intent frozen fields', all(r['intent'].get(k) for k in ('decisionInputsHash', 'engineVersion', 'referencePrice', 'maxBuyPrice', 'expiresAt')))
ck('A execute on PENDING is ILLEGAL', execute(oid).get('error') == 'ILLEGAL_STATE')
ck('A confirm -> CONFIRMED', confirm(oid)['intent']['state'] == 'CONFIRMED')
e = execute(oid)
ck('A execute -> FILLED', e.get('status') == 'filled' and e['intent']['state'] == 'FILLED', e.get('status'))
ck('A fill facts complete', all(k in e['fill'] for k in ('decisionPrice', 'executionSpot', 'actualSlippageBps', 'fillQuantity', 'fillUsd', 'remainingQuantity')))
pp = requests.get(B+'/api/v1/albert/paper-portfolio', params={'pid': A}).json()
held = {p['asset'] for p in pp['paperPortfolio']['positions']}
ck('A fill materialized into paper portfolio', sym in held, held)
ck('A reconciliation ok', pp['reconciliation']['ok'], pp['reconciliation'])
ps = requests.get(B+'/api/v1/albert/portfolio-summary', params={'pid': A}).json()
ck('A fill changed Albert next portfolio view', any(h['asset'] == sym for h in ps['holdings']), [h['asset'] for h in ps['holdings']])
ck('A FILLED is terminal: confirm rejected', confirm(oid).get('error') == 'TERMINAL_STATE')
ck('A FILLED is terminal: cancel rejected', cancel(oid).get('error') == 'TERMINAL_STATE')
ck('A FILLED is terminal: execute rejected (no double-fill)', execute(oid).get('error') == 'TERMINAL_STATE')
ck('A ledger has exactly 1 fill', config.order_ledger_col.count_documents({'pid': A}) == 1, config.order_ledger_col.count_documents({'pid': A}))

print('=== A2: divergence surfaced (not silently fixed) ===')
config.paper_portfolio_col.update_one({'_id': A}, {'$set': {'positions': [{'asset': sym, 'size': 999.0, 'avg_entry': 1}]}})
recon = L.reconcile(A, 'paper')
ck('A2 divergence detected', recon['ok'] is False and any(df['asset'] == sym for df in recon['diffs']), recon)

print('=== B: idempotency (no double intent/fill) ===')
Bp = 'u_E_B'; clean(Bp); setm(Bp, MAND()); setp(Bp, 50000, []); symb = buy_asset(Bp)
r1 = create(Bp, symb, 'dup'); r2 = create(Bp, symb, 'dup')
ck('B duplicate idempotencyKey -> same intent', r2.get('status') == 'exists' and r2['intent']['orderIntentId'] == r1['intent']['orderIntentId'])
ck('B only one intent stored', config.order_intents_col.count_documents({'pid': Bp}) == 1)

print('=== C: staleness at CONFIRM (independent) ===')
C = 'u_E_C'; clean(C); setm(C, MAND()); setp(C, 50000, []); symc = buy_asset(C)
rc = create(C, symc, 'kc'); oidc = rc['intent']['orderIntentId']
setp(C, 90000, [{'asset': 'BTC', 'size': 0.3, 'avg_entry': 40000}])  # change inputs -> hash moves
ck('C confirm rejects STALE_DECISION', confirm(oidc).get('reason') == 'STALE_DECISION', confirm(oidc) if False else 'n/a')
ck('C stale intent is REJECTED (terminal)', geto(oidc)['intent']['state'] == 'REJECTED')

print('=== D: staleness at EXECUTE (independent of confirm) ===')
Dp = 'u_E_D'; clean(Dp); setm(Dp, MAND()); setp(Dp, 50000, []); symd = buy_asset(Dp)
rd = create(Dp, symd, 'kd'); oidd = rd['intent']['orderIntentId']
ck('D confirm ok first', confirm(oidd)['intent']['state'] == 'CONFIRMED')
setp(Dp, 88000, [{'asset': 'ETH', 'size': 4, 'avg_entry': 2000}])  # move inputs after confirm
ck('D execute rejects STALE_DECISION', execute(oidd).get('reason') == 'STALE_DECISION')

print('=== E: expiry cannot be revived ===')
Ep = 'u_E_E'; clean(Ep); setm(Ep, MAND()); setp(Ep, 50000, []); syme = buy_asset(Ep)
re = create(Ep, syme, 'ke'); oide = re['intent']['orderIntentId']
confirm(oide)
config.order_intents_col.update_one({'_id': oide}, {'$set': {'expiresAt': (datetime.datetime.utcnow() - datetime.timedelta(minutes=1)).isoformat()}})
ck('E execute on expired -> EXPIRED', execute(oide).get('status') == 'expired')
ck('E EXPIRED terminal', geto(oide)['intent']['state'] == 'EXPIRED')
ck('E cannot revive (confirm rejected)', confirm(oide).get('error') == 'TERMINAL_STATE')

print('=== F: directional slippage ===')
Fp = 'u_E_F'; clean(Fp); setm(Fp, MAND()); setp(Fp, 50000, []); symf = buy_asset(Fp)
rf = create(Fp, symf, 'kf'); oidf = rf['intent']['orderIntentId']; confirm(oidf)
config.order_intents_col.update_one({'_id': oidf}, {'$set': {'maxBuyPrice': 1.0}})  # force spot > maxBuy
ck('F BUY slippage rejects when spot>maxBuyPrice', execute(oidf).get('reason') == 'SLIPPAGE_EXCEEDED')
# SELL slippage
Fs = 'u_E_FS'; clean(Fs)
setm(Fs, {'risk_tolerance': 'moderate', 'reserve_pct': 20, 'approved_coins': ['ETH'], 'excluded_coins': ['DOGE'], 'max_alloc_pct': {'BTC': 40}, 'max_trade_risk_pct': 2})
setp(Fs, 20000, [{'asset': 'DOGE', 'size': 5000, 'avg_entry': 0.1}])
rs = create(Fs, 'DOGE', 'ks')
ck('FS created a SELL intent', rs['intent']['side'] == 'SELL', rs.get('intent', {}).get('side'))
oids = rs['intent']['orderIntentId']; confirm(oids)
config.order_intents_col.update_one({'_id': oids}, {'$set': {'minSellPrice': 1e12}})  # force spot < minSell
ck('FS SELL slippage rejects when spot<minSellPrice', execute(oids).get('reason') == 'SLIPPAGE_EXCEEDED')

print('=== G: partial fill -> PARTIALLY_FILLED -> FILLED + cancel from approved states ===')
G = 'u_E_G'; clean(G); setm(G, MAND()); setp(G, 50000, []); symg = buy_asset(G)
rg = create(G, symg, 'kg'); oidg = rg['intent']['orderIntentId']; confirm(oidg)
totq = rg['intent']['quantity']
e1 = execute(oidg, q=round(totq * 0.4, 8))
ck('G partial -> PARTIALLY_FILLED', e1.get('status') == 'partially_filled' and e1['intent']['state'] == 'PARTIALLY_FILLED', e1.get('status'))
ck('G remaining tracked', e1['intent']['remainingQuantity'] > 0)
e2 = execute(oidg)  # fill the rest (continuation, no staleness)
ck('G continuation -> FILLED', e2.get('status') == 'filled' and e2['intent']['state'] == 'FILLED')
ck('G two ledger fills', config.order_ledger_col.count_documents({'pid': G, 'orderIntentId': oidg}) == 2)
# cancel from PENDING
c1 = create(G, symg, 'kg_pending'); ck('G cancel from PENDING', cancel(c1['intent']['orderIntentId'])['intent']['state'] == 'CANCELLED')
# cancel from CONFIRMED
c2 = create(G, symg, 'kg_conf'); confirm(c2['intent']['orderIntentId']); ck('G cancel from CONFIRMED', cancel(c2['intent']['orderIntentId'])['intent']['state'] == 'CANCELLED')
# cancel from PARTIALLY_FILLED
c3 = create(G, symg, 'kg_part'); oid3 = c3['intent']['orderIntentId']; confirm(oid3); execute(oid3, q=round(c3['intent']['quantity'] * 0.3, 8))
ck('G cancel from PARTIALLY_FILLED', cancel(oid3)['intent']['state'] == 'CANCELLED')

print('=== H: explain-order-intent is read-only ===')
ex = requests.post(B+'/api/v1/albert/explain-order-intent', json={'pid': A, 'orderIntentId': oid, 'question': 'Why was this order created and what would make it stale?'}, timeout=90).json()
ck('H explain returns intent UNCHANGED', ex.get('intent', {}).get('orderIntentId') == oid and ex['intent']['state'] == 'FILLED' and ex['intent']['amountUsd'] == r['intent']['amountUsd'], ex.get('status'))
print('   explanation sample:', (ex.get('explanation') or '')[:150].replace(chr(10), ' '))

for pid in ['u_E_A', 'u_E_B', 'u_E_C', 'u_E_D', 'u_E_E', 'u_E_F', 'u_E_FS', 'u_E_G']:
    clean(pid)
print()
print('PHASE E RESULT: %d passed, %d failed' % (P, Fa))
sys.exit(1 if Fa else 0)
