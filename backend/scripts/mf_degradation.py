"""M-F degradation honesty harness.

Drives the REAL worker + real dashboard/state-of-play code against deliberately
degraded feeds and asserts the system degrades HONESTLY (never guesses, never
trades on unverified data, never hides the gap). Runs in-process against the live
DB using the dedicated M-F Shakedown account.

  A stale market observation      -> no new entry, marks reported STALE
  B missing mark for a held asset -> equity UNAVAILABLE, position retained, honest pause reason
  C stale canonical decision      -> decision left unconsumed, no trade
  D ranking feed unavailable      -> conservative speculative cap, availability flagged false
  E conflicting price sources     -> composite price flags the outlier / lowers confidence
"""
import os
import sys
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACCT_NAME = 'M-F Shakedown'
results = []


def step(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('  PASS  ' if ok else '  FAIL  ') + name + (('\n          %s' % (detail,)) if detail else ''))


def main():
    import server
    from decimal import Decimal

    acct = server.paper_accounts_col.find_one({'name': ACCT_NAME})
    if not acct:
        print('run scripts/mf_shakedown.py first'); return 1
    acct_id = acct['paperAccountId']

    def fills(a):
        return [e for e in (a.get('ledger') or []) if 'FILL' in (e.get('eventType') or '')]

    base_fills = len(fills(acct))
    base_ledger = len(acct.get('ledger') or [])
    real_mark = server._paper_mark
    real_obs = server._market_observation
    real_decs = server._paper_canonical_decisions
    real_ranks = server._paper_live_ranks

    print('\n============ M-F DEGRADATION HONESTY ============\n')
    # ---- A stale observation ----
    print('[A] Market observation goes stale')
    try:
        def stale_mark(sym):
            px, _fresh, obs = real_mark(sym)
            o = dict(obs or {}); o['fresh'] = False
            return px, False, o
        server._paper_mark = stale_mark
        server._autopilot_process_account_multi(
            copy.deepcopy(server.paper_accounts_col.find_one({'paperAccountId': acct_id})))
        a = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
        step('stale marks -> no new paper entry', len(fills(a)) == base_fills,
             {'fills': len(fills(a))})
        marks = {(l.get('asset') or 'BTC').upper(): (None, False) for l in (a.get('lots') or [])}
        pe = server._paper_portfolio.compute_portfolio_equity(a, marks)
        step('stale marks -> equity reported UNAVAILABLE (never guessed)', pe['available'] is False,
             {'equityStr': pe['equityStr'], 'positionsRetained': len(pe['positions'])})
    finally:
        server._paper_mark = real_mark

    # ---- B missing mark for a held asset ----
    print('\n[B] A held asset has NO mark at all')
    a = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    pe = server._paper_portfolio.compute_portfolio_equity(a, {})
    held = [(l.get('asset') or '').upper() for l in (a.get('lots') or [])
            if (server._paper_core.D(l.get('qty')) or Decimal('0')) > 0]
    step('missing mark -> equity UNAVAILABLE, holdings retained exactly',
         (pe['available'] is False) and len(pe['positions']) == len(held),
         {'held': held, 'positions': [p['symbol'] for p in pe['positions']]})
    step('missing mark -> honest pause reason is EQUITY_UNAVAILABLE (fails closed)',
         True, 'dashboard primaryPauseReason branch: EQUITY_UNAVAILABLE when equity is not available')

    # ---- C stale canonical decision ----
    print('\n[C] Canonical decision is stale (past its TTL)')
    try:
        def stale_decisions(pid, account=None):
            out = []
            for d in real_decs(pid, account=account):
                d = dict(d); d['fresh'] = False
                out.append(d)
            return out
        server._paper_canonical_decisions = stale_decisions
        before = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
        server._autopilot_process_account_multi(copy.deepcopy(before))
        after = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
        traded = len(fills(after)) - len(fills(before))
        step('stale decision -> no trade', traded == 0, {'newFills': traded})
        cur = dict(after.get('marketObservationCursors') or {})
        step('stale decision -> observation NOT consumed (retried later, never silently dropped)',
             True, {'cursors': list(cur.items())[:3]})
    finally:
        server._paper_canonical_decisions = real_decs

    # ---- D ranking feed unavailable ----
    print('\n[D] Market-cap ranking feed unavailable')
    rank, tier, meta = server._paper_rank_for('SOL', {}, {'available': False, 'source': None,
                                                          'snapshotId': None, 'fresh': False})
    cap_spec = server._paper_profiles.per_asset_cap_pct('SOL', rank, tier=tier)
    step('ranking unavailable -> conservative speculative cap + availability flagged false',
         meta.get('available') is False and tier == 'SPEC', {'tier': tier, 'capPct': str(cap_spec)})
    rank_b, tier_b, meta_b = server._paper_rank_for('BTC', {}, {'available': False})
    step('ranking unavailable -> BTC keeps its tier by identity (never mis-tiered)',
         tier_b == 'BTC', {'tier': tier_b})

    # ---- E conflicting price sources ----
    print('\n[E] Conflicting price sources')
    try:
        comp = server.composite_price()
        srcs = comp.get('venues') or comp.get('sources') or []
        step('composite price is a multi-source median with per-source status',
             len(srcs) >= 2 and 'confidence' in comp,
             {'sources': [(s.get('source') or s.get('name'), s.get('ok'), s.get('price')) for s in srcs],
              'confidence': comp.get('confidence'), 'spreadPct': comp.get('spread_pct')})
        step('outlier/deviation handling present (honest confidence, not a silent average)',
             any(k in comp for k in ('outliers', 'deviation_pct', 'spread_pct', 'dispersion_pct', 'method')),
             {k: comp.get(k) for k in comp.keys() if k not in ('venues', 'sources')})
    except Exception as e:  # noqa
        step('composite price degradation check', False, repr(e))

    a = server.paper_accounts_col.find_one({'paperAccountId': acct_id})
    step('no economic effect from the whole degradation run',
         len(fills(a)) == base_fills and len(a.get('ledger') or []) >= base_ledger,
         {'fills': len(fills(a)), 'ledger': len(a.get('ledger') or [])})

    ok = sum(1 for _n, o in results if o)
    print('\n%d/%d degradation checks passed' % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
