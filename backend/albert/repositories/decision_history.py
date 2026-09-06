"""Decision history + immutable-snapshot persistence (Phase D2).

Design:
  * decision_current_col   \u2014 one pointer per (pid, asset): the CURRENT decision
    identity + stable decisionId/snapshotId + a copy of the latest envelope.
  * decision_snapshots_col \u2014 append-only immutable snapshots (written when the
    decision identity CHANGES). Referenced by history events.
  * decision_history_col   \u2014 genuine call-change events ONLY (WAIT->BUY,
    TRIM_10->TRIM_25, eligible->ineligible, ...). Never logs a refresh where only
    an irrelevant score drift occurred (identity unchanged).

History events REFERENCE snapshots by id (previous/new decisionId + snapshotId)
rather than duplicating them, giving a clean audit chain.
"""
import datetime
import uuid

from config import (
    decision_history_col, decision_snapshots_col, decision_current_col,
)
from albert.engine.constants import DECISION_SNAPSHOT_RETENTION, DECISION_HISTORY_DEFAULT_LIMIT


def _identity(d):
    """The decision IDENTITY tuple. A change in ANY element is a genuine
    transition; an isolated score/price drift (identity unchanged) is not."""
    sell = d.get('sellPlan') or {}
    deploy_tier = 'DEPLOY' if (d.get('recommendedDeployNowUsd') or 0) > 0 else 'NONE'
    return [d.get('action'), d.get('reasonCode'), bool(d.get('eligible')),
            d.get('ineligibilityReason'), sell.get('action'), deploy_tier]


def _plain(env):
    """Human label for a decision, e.g. 'Buy', 'Hold', 'Trim 25%', 'Exit 100%'."""
    a = (env or {}).get('action')
    if a == 'SELL':
        sp = (env or {}).get('sellPlan') or {}
        act = sp.get('action') or 'SELL'
        if act == 'EXIT_100':
            return 'Exit 100%'
        if act.startswith('TRIM_'):
            return 'Trim ' + act.split('_')[1] + '%'
        return 'Sell'
    return (a or '').title() or 'Wait'


def _change_type(prev_id, new_id):
    """Compact machine label for the transition."""
    if prev_id[0] != new_id[0]:
        return '%s->%s' % (prev_id[0], new_id[0])            # call change
    if prev_id[1] != new_id[1]:
        return '%s->%s' % (prev_id[1], new_id[1])            # reasonCode change
    if prev_id[4] != new_id[4]:
        return '%s->%s' % (prev_id[4], new_id[4])            # sell action change
    if prev_id[2] != new_id[2]:
        return ('eligible->ineligible' if prev_id[2] else 'ineligible->eligible')
    if prev_id[5] != new_id[5]:
        return 'DEPLOY_%s->%s' % (prev_id[5], new_id[5])
    return 'CHANGED'


def _change_reasons(prev_env, new_env):
    reasons = []
    pi, ni = _identity(prev_env), _identity(new_env)
    if pi[0] != ni[0]:
        reasons.append('Call %s -> %s' % (pi[0], ni[0]))
    if pi[1] != ni[1]:
        reasons.append('Reason %s -> %s' % (pi[1], ni[1]))
    if pi[4] != ni[4]:
        reasons.append('Sell action %s -> %s' % (pi[4], ni[4]))
    if pi[2] != ni[2]:
        reasons.append('Eligibility %s -> %s' % ('eligible' if pi[2] else 'ineligible',
                                                 'eligible' if ni[2] else 'ineligible'))
    if pi[5] != ni[5]:
        reasons.append('Deployment %s -> %s' % (pi[5], ni[5]))
    ps, ns = prev_env.get('opportunityScore'), new_env.get('opportunityScore')
    if ps is not None and ns is not None and round(ps) != round(ns):
        reasons.append('Score %.0f -> %.0f' % (ps, ns))
    return reasons or ['Decision inputs changed']


def _trim(pid, asset):
    try:
        ids = [r['_id'] for r in decision_snapshots_col.find(
            {'pid': pid, 'asset': asset}, {'_id': 1}).sort('createdAt', -1).skip(DECISION_SNAPSHOT_RETENTION)]
        if ids:
            decision_snapshots_col.delete_many({'_id': {'$in': ids}})
    except Exception:  # noqa
        pass


def reconcile(pid, snap):
    """Reconcile a freshly built snapshot against stored state. Mutates each
    decision to carry a STABLE decisionId/snapshotId (reused while the identity
    is unchanged; freshly minted on a genuine transition) and appends immutable
    snapshots + history events for real transitions only. Returns list of events.
    """
    pass_ts = snap.get('marketDataTimestamp') or datetime.datetime.utcnow().isoformat()
    events = []
    for d in snap.get('decisions', []):
        asset = d['symbol']
        ident = _identity(d)
        key = '%s:%s' % (pid, asset)
        cur = decision_current_col.find_one({'_id': key})

        if cur and cur.get('identity') == ident:
            # unchanged identity -> reuse stable ids + original establish time
            d['decisionId'] = cur['decisionId']
            d['snapshotId'] = cur['snapshotId']
            d['marketDataTimestamp'] = cur.get('establishedAt', pass_ts)
            decision_current_col.update_one({'_id': key}, {'$set': {
                'envelope': d, 'decisionInputsHash': d.get('decisionInputsHash'),
                'lastSeenAt': pass_ts}})
            continue

        # transition (or first-ever sighting) -> mint fresh ids + persist immutable
        new_did = str(uuid.uuid4())
        new_sid = str(uuid.uuid4())
        d['decisionId'] = new_did
        d['snapshotId'] = new_sid
        d['marketDataTimestamp'] = pass_ts
        try:
            decision_snapshots_col.insert_one({
                '_id': new_did, 'decisionId': new_did, 'snapshotId': new_sid,
                'pid': pid, 'asset': asset, 'decisionInputsHash': d.get('decisionInputsHash'),
                'identity': ident, 'envelope': d, 'createdAt': pass_ts})
        except Exception:  # noqa
            pass

        if cur:  # genuine transition (not the very first record)
            from_label = _plain(cur.get('envelope', {}))
            to_label = _plain(d)
            ev = {'_id': str(uuid.uuid4()), 'pid': pid, 'asset': asset,
                  'previousDecisionId': cur['decisionId'], 'newDecisionId': new_did,
                  'previousSnapshotId': cur['snapshotId'], 'newSnapshotId': new_sid,
                  'changedAt': pass_ts, 'changeType': _change_type(cur['identity'], ident),
                  'fromLabel': from_label, 'toLabel': to_label,
                  'headline': '%s \u2192 %s' % (from_label, to_label),
                  'changeReason': _change_reasons(cur.get('envelope', {}), d)}
            try:
                decision_history_col.insert_one(ev)
                events.append({k: v for k, v in ev.items() if k != '_id'})
            except Exception:  # noqa
                pass

        decision_current_col.update_one({'_id': key}, {'$set': {
            '_id': key, 'pid': pid, 'asset': asset, 'identity': ident,
            'decisionId': new_did, 'snapshotId': new_sid, 'establishedAt': pass_ts,
            'lastSeenAt': pass_ts, 'decisionInputsHash': d.get('decisionInputsHash'),
            'envelope': d}}, upsert=True)
        _trim(pid, asset)

    return events


def get_snapshot(pid, decision_id):
    """Fetch an immutable decision snapshot envelope by decisionId (authoritative)."""
    doc = decision_snapshots_col.find_one({'decisionId': decision_id, 'pid': pid})
    if doc:
        return doc.get('envelope')
    cur = decision_current_col.find_one({'pid': pid, 'decisionId': decision_id})
    if cur:
        return cur.get('envelope')
    return None


def get_current(pid, asset):
    cur = decision_current_col.find_one({'_id': '%s:%s' % (pid, asset)})
    return cur.get('envelope') if cur else None


def list_history(pid, asset=None, limit=DECISION_HISTORY_DEFAULT_LIMIT):
    q = {'pid': pid}
    if asset:
        q['asset'] = str(asset).upper()[:8]
    limit = max(1, min(500, int(limit or DECISION_HISTORY_DEFAULT_LIMIT)))
    rows = list(decision_history_col.find(q, {'_id': 0}).sort('changedAt', -1).limit(limit))
    return rows
