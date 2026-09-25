"""Ask-Albert remediation — Milestone 5 (Expert Multi-Asset Trader) tests.

Two layers:
  * PURE UNIT (no HTTP, no browser): profiles + portfolio allocation/ranking/rotation
    exercised directly on Decimals. Guarantees determinism + limit enforcement.
  * WORKER: drives the REAL background code path
    (server._autopilot_process_account_multi) with canonical decisions + per-asset
    marks monkeypatched, proving multi-asset autopilot behaviour with no dashboard.

Run:  cd /app/backend && python -m pytest tests/test_m5_multiasset.py -v
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
from albert.paper import portfolio as pf  # noqa: E402
from albert.paper import profiles as P  # noqa: E402

PA = server.paper_accounts_col
LED = lambda a: [e for e in (a.get('ledger') or []) if e.get('side')]  # noqa: E731


# ================================ helpers =================================== #
def _acct(cash='100000', reserve='0', lots=None, mode='PAPER_AUTOPILOT', state='RUNNING'):
    econ = core.new_account_economics(Decimal(cash), Decimal(reserve))
    a = {'paperAccountId': 'pa_m5_' + uuid.uuid4().hex[:10], 'ownerId': 'u_m5_' + uuid.uuid4().hex[:6],
         'name': 'm5', 'baseCurrency': 'USDC', 'mode': mode, 'runtimeState': state,
         'version': 0, 'archivedAt': None, 'createdAt': datetime.datetime.utcnow().isoformat(), **econ}
    if lots:
        a['lots'] = lots
    return a


def _lot(sym, qty, avg, inv=None):
    return {'lotId': 'pp_' + uuid.uuid4().hex[:8], 'asset': sym, 'status': 'OPEN',
            'qty': core.to128(Decimal(qty)), 'avgEntry': core.to128(Decimal(avg)),
            'costBasis': core.to128(Decimal(qty) * Decimal(avg)), 'positionVersion': 1,
            'invalidationPrice': core.to128(Decimal(inv)) if inv else None}


def _canon(sym, action='BUY', score='80', conf='70', deploy='20000', price='100',
           inv='90', rank=None, regime='BULL', eligible=True, fresh=True, minutes_ago=2, sell=None):
    dt = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {'asset': sym, 'action': action, 'actionable': action in ('BUY', 'SELL'),
            'decisionSnapshotId': 's_' + uuid.uuid4().hex[:8], 'decisionId': 'd_' + sym,
            'decisionInputsHash': 'h', 'engineVersion': 'albert-decide-v2', 'mandateVersion': 'mv',
            'regime': regime, 'score': score, 'confidence': conf, 'rank': rank,
            'currentPrice': price, 'invalidationPrice': inv,
            'mandateChecks': {'excluded': False, 'inApprovedUniverse': True, 'withinCap': True,
                              'withinRiskBudget': True, 'mandateComplete': True},
            'eligible': eligible, 'recommendedDeployNowUsd': deploy, 'sellPlan': sell,
            'fresh': fresh, 'decisionTime': dt}


def _marks(**kw):
    """kw: SYM='price' -> {SYM: (Decimal(price), True)}."""
    return {k: (Decimal(v), True) for k, v in kw.items()}


MANDATE = {'max_alloc_pct': {}, 'max_trade_risk_pct': '3', 'max_drawdown_pct': '30',
           'approved_coins': [], 'excluded_coins': []}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(server._albert_deps, 'get_mandate', lambda pid: dict(MANDATE))
    # _drive() reassigns these module globals directly; snapshot + restore so we never
    # leak a stubbed _paper_mark/_paper_canonical_decisions into other test modules.
    _orig_mark = server._paper_mark
    _orig_dec = server._paper_canonical_decisions
    _orig_gm = server._albert_deps.get_mandate
    try:
        yield
    finally:
        server._paper_mark = _orig_mark
        server._paper_canonical_decisions = _orig_dec
        server._albert_deps.get_mandate = _orig_gm


def _cleanup(a):
    PA.delete_one({'paperAccountId': a['paperAccountId']})
    server.paper_notif_col.delete_many({'paperAccountId': a['paperAccountId']})
    server.paper_proposals_col.delete_many({'paperAccountId': a['paperAccountId']})


def _drive(a, decisions, marks, mandate=None):
    """Insert account, monkeypatch canonical + marks, run one multi tick."""
    PA.insert_one(dict(a))
    server._paper_canonical_decisions = lambda pid, account=None: decisions
    mark_ts = datetime.datetime.utcnow().isoformat()

    def _mk(sym):
        v = marks.get(sym.upper(), (None, False))
        obs = {'price': v[0], 'ts': mark_ts, 'fresh': bool(v[1]), 'source': 'test',
               'obsId': ('obs:%s:%s' % (sym.upper(), mark_ts)) if v[1] else None}
        return v[0], v[1], obs
    server._paper_mark = _mk
    if mandate is not None:
        server._albert_deps.get_mandate = lambda pid: dict(mandate)
    fresh = PA.find_one({'paperAccountId': a['paperAccountId']})
    server._autopilot_process_account_multi(fresh)
    return PA.find_one({'paperAccountId': a['paperAccountId']})


# ======================= PROOF 4: deterministic ranking ===================== #
def test_ranking_is_deterministic_and_order_independent():
    cands = [{'symbol': 'ETH', 'score': '80', 'confidence': '70'},
             {'symbol': 'SOL', 'score': '80', 'confidence': '90'},
             {'symbol': 'BTC', 'score': '88', 'confidence': '60'},
             {'symbol': 'ADA', 'score': '80', 'confidence': '70'}]
    order1 = [c['symbol'] for c in pf.rank_opportunities(list(cands))]
    order2 = [c['symbol'] for c in pf.rank_opportunities(list(reversed(cands)))]
    assert order1 == order2                      # order-independent
    assert order1[0] == 'BTC'                    # highest score first
    assert order1[1] == 'SOL'                    # tie on score -> higher confidence
    assert order1[2:] == ['ADA', 'ETH']          # final tie -> symbol asc


# ======================= PROOF 5: stronger over weaker ====================== #
def test_stronger_opportunity_selected_over_weaker_when_one_slot():
    prof = dict(P.AGGRESSIVE_EXPERIENCED_V1); prof['maxConcurrentPositions'] = 1
    a = _acct()
    ei = pf.compute_portfolio_equity(a, {})
    cands = [_canon('BTC', score='90', deploy='20000', price='60000', inv='54000'),
             _canon('ETH', score='75', deploy='20000', price='3000', inv='2700')]
    out = pf.allocate(acct=a, equity_info=ei,
                      candidates=[{**c, 'symbol': c['asset']} for c in cands],
                      regime='BULL', marks=_marks(BTC='60000', ETH='3000'), profile=prof)
    buys = [i for i in out['intents'] if i['action'] in ('BUY', 'ADD')]
    assert len(buys) == 1 and buys[0]['symbol'] == 'BTC'   # stronger wins the only slot


# =============== PROOF 6: volatile / illiquid -> smaller allocation ========= #
def test_illiquid_speculative_gets_smaller_allocation_than_large_cap():
    a = _acct(cash='1000000')
    ei = pf.compute_portfolio_equity(a, {})
    # same score + same generous rec; ETH is LARGE (rank 2), a SPEC coin is rank 80.
    large = {'symbol': 'ETH', 'action': 'BUY', 'score': '80', 'confidence': '70',
             'recommendedDeployNowUsd': '100000', 'invalidationPrice': '2700', 'rank': 2}
    spec = {'symbol': 'FOO', 'action': 'BUY', 'score': '80', 'confidence': '70',
            'recommendedDeployNowUsd': '100000', 'invalidationPrice': '90', 'rank': 80}
    out = pf.allocate(acct=a, equity_info=ei, candidates=[large, spec], regime='BULL',
                      marks={'ETH': (Decimal('3000'), True), 'FOO': (Decimal('100'), True)})
    by = {i['symbol']: i['notional'] for i in out['intents'] if i['action'] == 'BUY'}
    assert by['FOO'] < by['ETH']                  # illiquid/speculative smaller


# =============== PROOF 7: total + altcoin exposure limits enforced ========== #
def test_altcoin_and_total_exposure_limits_enforced():
    a = _acct(cash='100000')
    ei = pf.compute_portfolio_equity(a, {})
    equity = Decimal('100000')
    cands = [{'symbol': s, 'action': 'BUY', 'score': '85', 'confidence': '80',
              'recommendedDeployNowUsd': '90000', 'invalidationPrice': '90', 'rank': r}
             for s, r in [('ETH', 2), ('SOL', 5), ('ADA', 9), ('AVAX', 12), ('LINK', 15)]]
    out = pf.allocate(acct=a, equity_info=ei, candidates=cands, regime='BULL',
                      marks={s: (Decimal('100'), True) for s in ('ETH', 'SOL', 'ADA', 'AVAX', 'LINK')})
    buys = [i for i in out['intents'] if i['action'] == 'BUY']
    total_alt = sum(i['notional'] for i in buys)
    band = P.regime_band('BULL')
    assert total_alt <= equity * band['altCeilingPct'] / Decimal('100') + Decimal('0.01')
    assert total_alt <= equity * band['maxDeployPct'] / Decimal('100') + Decimal('0.01')


# =============== PROOF 8: aggressive profile changes deployment ============= #
def test_aggressive_profile_deploys_more_than_conservative():
    a = _acct(cash='100000')
    ei = pf.compute_portfolio_equity(a, {})
    cands = [{'symbol': 'BTC', 'action': 'BUY', 'score': '90', 'confidence': '80',
              'recommendedDeployNowUsd': '90000', 'invalidationPrice': '54000', 'rank': 1}]
    aggr = pf.allocate(acct=a, equity_info=ei, candidates=list(cands), regime='BULL',
                       marks=_marks(BTC='60000'))
    cons = dict(P.AGGRESSIVE_EXPERIENCED_V1)
    cons.update({'maxDeployedEquityPct': Decimal('30'), 'normalRiskPct': Decimal('0.5'),
                 'highConvictionRiskPct': Decimal('0.5'), 'maxSingleTradeRiskPct': Decimal('0.5'),
                 'btcAllocPct': Decimal('10')})
    conservative = pf.allocate(acct=a, equity_info=ei, candidates=list(cands), regime='RANGE',
                               marks=_marks(BTC='60000'), profile=cons)
    an = sum(i['notional'] for i in aggr['intents'] if i['action'] == 'BUY')
    cn = sum(i['notional'] for i in conservative['intents'] if i['action'] == 'BUY')
    assert an > cn


# =============== PROOF 9: rotation never exceeds cash / risk ================ #
def test_rotation_only_frees_capital_and_respects_cash():
    prof = dict(P.AGGRESSIVE_EXPERIENCED_V1); prof['maxConcurrentPositions'] = 1
    # Hold a weak ADA position; a much stronger BTC BUY is blocked by the 1-slot cap.
    a = _acct(cash='5000', lots=[_lot('ADA', '10000', '1', inv='0.9')])
    marks = {'ADA': (Decimal('1'), True), 'BTC': (Decimal('60000'), True)}
    ei = pf.compute_portfolio_equity(a, marks)
    cands = [_canon('BTC', score='95', deploy='20000', price='60000', inv='54000'),
             {'symbol': 'ADA', 'action': 'HOLD', 'score': '60'}]
    cands = [{**c, 'symbol': c.get('asset', c.get('symbol'))} for c in cands]
    out = pf.allocate(acct=a, equity_info=ei, candidates=cands, regime='BULL',
                      marks=marks, profile=prof)
    exits = [i for i in out['intents'] if i['action'] in ('EXIT', 'TRIM')]
    buys = [i for i in out['intents'] if i['action'] in ('BUY', 'ADD')]
    assert any(i['symbol'] == 'ADA' and i['reason'] == 'ROTATION' for i in exits)  # weakest freed
    # rotation only SELLS; freed cash is used next tick, so no buy exceeds current cash
    assert sum(i['notional'] for i in buys) <= (ei['deployableCash'] or Decimal('0'))


# =============== PROOF: honest multi-asset valuation ======================== #
def test_missing_mark_makes_equity_unavailable_but_keeps_positions():
    a = _acct(cash='50000', lots=[_lot('ETH', '10', '3000'), _lot('SOL', '100', '100')])
    ei = pf.compute_portfolio_equity(a, {'ETH': (Decimal('3200'), True)})  # SOL missing
    assert ei['available'] is False and ei['equity'] is None
    assert any(p['symbol'] == 'SOL' and p['markFresh'] is False for p in ei['positions'])
    ei2 = pf.compute_portfolio_equity(a, {'ETH': (Decimal('3200'), True), 'SOL': (Decimal('120'), True)})
    assert ei2['available'] is True and ei2['equity'] == Decimal('50000') + Decimal('32000') + Decimal('12000')


# ======================= PROOF 1: BTC + altcoin trade ======================= #
def test_btc_and_altcoin_trade_automatically():
    a = _acct(cash='100000')
    decisions = [_canon('BTC', score='90', deploy='20000', price='60000', inv='54000'),
                 _canon('ETH', score='82', deploy='15000', price='3000', inv='2700')]
    a2 = _drive(a, decisions, _marks(BTC='60000', ETH='3000'))
    assets = {(l.get('asset') or '').upper() for l in (a2.get('lots') or [])
              if (core.D(l.get('qty')) or Decimal('0')) > 0}
    assert 'BTC' in assets and 'ETH' in assets
    assert len(LED(a2)) == 2
    _cleanup(a)


# ================= PROOF 2: excluded / unsupported cannot trade ============= #
def test_excluded_and_unsupported_assets_cannot_trade():
    m = dict(MANDATE); m['excluded_coins'] = ['ETH']
    a = _acct(cash='100000')
    decisions = [_canon('BTC', score='90', deploy='20000', price='60000', inv='54000'),
                 _canon('ETH', score='95', deploy='20000', price='3000', inv='2700'),  # excluded
                 _canon('WBTC', score='95', deploy='20000', price='60000', inv='54000')]  # wrapped
    a2 = _drive(a, decisions, _marks(BTC='60000', ETH='3000', WBTC='60000'), mandate=m)
    traded = {(l.get('asset') or '').upper() for l in (a2.get('lots') or [])
              if (core.D(l.get('qty')) or Decimal('0')) > 0}
    assert traded == {'BTC'}                       # ETH excluded, WBTC wrapped -> only BTC
    _cleanup(a)


def test_stablecoin_wrapped_leveraged_eligibility():
    assert P.eligible_for_trading('USDT')[1] == 'STABLECOIN'
    assert P.eligible_for_trading('WETH')[1] == 'WRAPPED_DUPLICATE'
    assert P.eligible_for_trading('BTC3L')[1] == 'LEVERAGED_TOKEN'
    assert P.eligible_for_trading('ETHUP')[1] == 'LEVERAGED_TOKEN'
    assert P.eligible_for_trading('SOL', excluded={'SOL'})[1] == 'EXCLUDED_BY_MANDATE'
    assert P.eligible_for_trading('SOL', approved={'BTC'})[1] == 'NOT_IN_APPROVED_UNIVERSE'
    assert P.eligible_for_trading('SOL')[0] is True


# ============ PROOF 3: discovery/score alone never manufactures a trade ===== #
def test_high_score_but_not_actionable_never_trades():
    a = _acct(cash='100000')
    # WAIT with a very high score must NOT create any position.
    decisions = [_canon('ETH', action='WAIT', score='99', deploy='0', price='3000', inv='2700')]
    a2 = _drive(a, decisions, _marks(ETH='3000'))
    assert len(LED(a2)) == 0
    _cleanup(a)


def test_actionable_but_ineligible_never_trades():
    a = _acct(cash='100000')
    decisions = [_canon('ETH', action='BUY', score='99', deploy='20000', price='3000',
                        inv='2700', eligible=False)]
    a2 = _drive(a, decisions, _marks(ETH='3000'))
    assert len(LED(a2)) == 0
    _cleanup(a)


# ============ PROOF 10: restart / two workers cannot duplicate ============== #
def test_restart_and_two_workers_cannot_duplicate_asset_trade():
    a = _acct(cash='100000')
    decisions = [_canon('BTC', score='90', deploy='20000', price='60000', inv='54000'),
                 _canon('ETH', score='82', deploy='15000', price='3000', inv='2700')]
    a2 = _drive(a, decisions, _marks(BTC='60000', ETH='3000'))
    n1 = len(LED(a2))
    # "restart": process the SAME canonical decisions again on the persisted account.
    stale = PA.find_one({'paperAccountId': a['paperAccountId']})
    server._autopilot_process_account_multi(dict(stale))     # duplicate worker, stale read
    a3 = PA.find_one({'paperAccountId': a['paperAccountId']})
    assert len(LED(a3)) == n1                                 # no duplicate fills
    _cleanup(a)


# ============ PROOF 12: entirely virtual (no exchange / real-money path) ==== #
def test_engine_has_no_exchange_or_real_money_path():
    for mod in (pf, P, core):
        src = open(mod.__file__).read()
        for banned in ('ccxt', 'api_key', 'apiKey', 'private_key', 'create_order',
                       'place_order', 'withdraw', 'secret'):
            assert banned not in src, '%s must have no live-exchange path: %s' % (mod.__name__, banned)


# ============ per-trade + combined-open-risk sizing reduces, never enlarges = #
def test_sizing_reduces_to_risk_and_never_enlarges():
    a = _acct(cash='100000')
    ei = pf.compute_portfolio_equity(a, {})
    # absurd rec; tight stop -> risk gate must shrink the notional well below rec
    c = {'symbol': 'BTC', 'action': 'BUY', 'score': '80', 'confidence': '70',
         'recommendedDeployNowUsd': '99999999', 'invalidationPrice': '59000', 'rank': 1}
    out = pf.allocate(acct=a, equity_info=ei, candidates=[c], regime='BULL', marks=_marks(BTC='60000'))
    buy = next(i for i in out['intents'] if i['action'] == 'BUY')
    equity = Decimal('100000')
    # never exceeds BTC cap (50%), deploy band (90%), or deployable after 10% protected
    assert buy['notional'] <= equity * Decimal('50') / Decimal('100')
    assert buy['notional'] <= Decimal('90000')
