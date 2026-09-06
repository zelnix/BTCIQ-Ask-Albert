"""Paper ledger + portfolio projection + reconciliation (Phase E).

Boundary is frozen: order/fill code ONLY appends immutable ledger entries. A
separate materialize() step derives the paper portfolio (baseline + ledger) that
the decision engine consumes. Nothing mutates the manual baseline (portfolio_col).
"""
import datetime
import uuid

from config import order_ledger_col, paper_portfolio_col, portfolio_col

_EPS = 1e-9


def append_fill(pid, account_id, order_intent_id, asset, side, quantity, price):
    """Append one immutable paper fill to the ledger."""
    entry = {'_id': str(uuid.uuid4()), 'pid': pid, 'accountId': account_id,
             'orderIntentId': order_intent_id, 'asset': asset, 'side': side,
             'quantity': float(quantity), 'price': float(price),
             'usd': round(float(quantity) * float(price), 2),
             'ts': datetime.datetime.utcnow().isoformat()}
    order_ledger_col.insert_one(dict(entry))
    return entry


def _derive_from_ledger(pid, account_id):
    """Authoritatively recompute holdings + cash from baseline + ALL ledger fills."""
    base = portfolio_col.find_one({'_id': pid}) or {}
    usdc = float(base.get('usdc') or 0.0)
    pos = {}
    for p in (base.get('positions') or []):
        a = str(p.get('asset', '')).upper()[:8]
        if not a:
            continue
        pos[a] = {'asset': a, 'size': float(p.get('size') or 0), 'avg_entry': float(p.get('avg_entry') or 0) or None}
    fills = list(order_ledger_col.find({'pid': pid, 'accountId': account_id}).sort('ts', 1))
    for f in fills:
        a = f['asset']; q = float(f['quantity']); pr = float(f['price']); usd = float(f['usd'])
        cur = pos.get(a) or {'asset': a, 'size': 0.0, 'avg_entry': None}
        if f['side'] == 'BUY':
            old_sz = cur['size']; new_sz = old_sz + q
            oe = cur['avg_entry'] or pr
            cur['avg_entry'] = ((old_sz * oe) + (q * pr)) / new_sz if new_sz > _EPS else pr
            cur['size'] = new_sz
            usdc -= usd
        else:  # SELL
            cur['size'] = max(0.0, cur['size'] - q)
            usdc += usd
        pos[a] = cur
    positions = [{'asset': v['asset'], 'size': round(v['size'], 10), 'avg_entry': v['avg_entry']}
                 for v in pos.values() if v['size'] > _EPS]
    return {'usdc': round(usdc, 2), 'positions': positions, 'fillCount': len(fills)}


def materialize(pid, account_id):
    """Recompute the paper portfolio from baseline + ledger and store it (the engine
    reads paper_portfolio_col when present). Idempotent."""
    derived = _derive_from_ledger(pid, account_id)
    paper_portfolio_col.update_one({'_id': pid}, {'$set': {
        '_id': pid, 'pid': pid, 'accountId': account_id,
        'usdc': derived['usdc'], 'positions': derived['positions'],
        'materializedAt': datetime.datetime.utcnow().isoformat(),
        'fillCount': derived['fillCount']}}, upsert=True)
    return derived


def reconcile(pid, account_id):
    """Independently re-derive from the ledger and compare to the stored paper
    portfolio. Surfaces divergence — NEVER silently fixes it."""
    stored = paper_portfolio_col.find_one({'_id': pid}) or {}
    stored_map = {p['asset']: float(p['size']) for p in (stored.get('positions') or [])}
    derived = _derive_from_ledger(pid, account_id)
    derived_map = {p['asset']: float(p['size']) for p in derived['positions']}
    diffs = []
    for a in set(stored_map) | set(derived_map):
        sv = stored_map.get(a, 0.0); dv = derived_map.get(a, 0.0)
        if abs(sv - dv) > 1e-6:
            diffs.append({'asset': a, 'projected': round(sv, 10), 'ledgerDerived': round(dv, 10)})
    cash_ok = abs(float(stored.get('usdc') or 0.0) - derived['usdc']) <= 0.01
    if not cash_ok:
        diffs.append({'asset': 'USDC', 'projected': stored.get('usdc'), 'ledgerDerived': derived['usdc']})
    return {'ok': len(diffs) == 0, 'diffs': diffs, 'ledgerDerived': derived}


def reset(pid, account_id):
    order_ledger_col.delete_many({'pid': pid, 'accountId': account_id})
    paper_portfolio_col.delete_one({'_id': pid})
