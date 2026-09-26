"""Sector leadership - breadth first, single winners last.

A sector label is only useful if it survives the obvious objection: "is that the sector,
or is that one token?" So every sector here reports member participation and turnover
concentration alongside its strength, and a sector carried by one constituent is labelled
CONCENTRATED rather than allowed to masquerade as broad leadership.

The taxonomy is versioned and single-label (each asset belongs to exactly one sector),
which makes the buckets mutually exclusive - but it covers only the mapped assets, never
the whole market, and that gap is disclosed rather than hidden.
"""
from albert.market import meta as M

SECTOR_TAXONOMY_VERSION = 'alert-sectors-v1'
CONCENTRATION_LIMIT = 0.60      # one member holding more than this of sector turnover
MIN_MEMBERS_WITH_DATA = 2
EMERGING_STRENGTH = 1.5
FADING_STRENGTH = -1.5


def _label(strength, participation, concentrated, members_with_data):
    if strength is None or members_with_data < MIN_MEMBERS_WITH_DATA:
        return 'UNKNOWN'
    if concentrated:
        return 'CONCENTRATED'
    if strength >= EMERGING_STRENGTH and participation is not None and participation >= 0.6:
        return 'EMERGING'
    if strength > 0:
        return 'STRENGTHENING'
    if strength <= FADING_STRENGTH:
        return 'FADING'
    return 'MIXED'


def assess(strengths, members_by_sector, universe_rows, *, exclude=('Store of Value',)):
    """`strengths` maps sector -> a strength number from the existing sector engine.
    `universe_rows` supplies per-symbol turnover and returns for the breadth measures."""
    if not strengths and not members_by_sector:
        return {'ruleVersion': SECTOR_TAXONOMY_VERSION, 'status': M.MISSING,
                'reasonCode': 'NO_SECTOR_ENGINE_OUTPUT', 'sectors': [],
                'limitations': ['The sector strength engine returned nothing.']}
    by_sym = {(r.get('symbol') or '').upper(): r for r in (universe_rows or [])}
    out = []
    for sector, members in (members_by_sector or {}).items():
        if sector in (exclude or ()):
            continue
        rows = [by_sym[m.upper()] for m in members if m.upper() in by_sym]
        vols = [(r['symbol'], r.get('volume24hUsd') or 0.0) for r in rows]
        rets = [r.get('change7dPct') for r in rows if r.get('change7dPct') is not None]
        total_vol = sum(v for _s, v in vols)
        top_sym, top_vol = (max(vols, key=lambda kv: kv[1]) if vols else (None, 0.0))
        concentration = (top_vol / total_vol) if total_vol > 0 else None
        concentrated = bool(concentration is not None and concentration > CONCENTRATION_LIMIT)
        participation = (len([r for r in rets if r > 0]) / float(len(rets))) if rets else None
        strength = strengths.get(sector)
        out.append({
            'sector': sector, 'strength': strength,
            'label': _label(strength, participation, concentrated, len(rows)),
            'memberCount': len(members or []), 'membersWithData': len(rows),
            'membersWith7dReturn': len(rets),
            'participation': M.dec_str(participation, 4),
            'turnoverConcentration': M.dec_str(concentration, 4),
            'largestMember': top_sym,
            'concentrated': concentrated,
            'members': sorted(members or []),
            'evidenceRefs': [M.evidence_ref('sector', SECTOR_TAXONOMY_VERSION, sector, strength)],
            'limitation': (('Turnover is %.1f%% concentrated in %s, so this is not evidence '
                            'of broad sector leadership.' % ((concentration or 0) * 100, top_sym))
                           if concentrated else
                           ('Only %d of %d members have usable data.' % (len(rows), len(members or []))
                            if len(rows) < len(members or []) else None)),
        })
    out.sort(key=lambda s: (s['strength'] if s['strength'] is not None else -999), reverse=True)
    covered = len([s for s in out if s['membersWithData'] >= MIN_MEMBERS_WITH_DATA])
    return {'ruleVersion': SECTOR_TAXONOMY_VERSION,
            'status': M.FRESH if covered == len(out) and out else (M.PARTIAL if out else M.MISSING),
            'reasonCode': None if covered == len(out) else 'THIN_SECTOR_COVERAGE',
            'sectorsAssessed': len(out), 'sectorsWithBreadth': covered,
            'sectors': out,
            'limitations': [
                'Categories are single-label and therefore mutually exclusive, but the '
                'taxonomy (%s) covers only mapped assets - it is not the whole market, so '
                'sector figures do not add up to it.' % SECTOR_TAXONOMY_VERSION,
                'Strength is a relative-performance reading from the existing sector '
                'engine; a short-lived surge is not promoted to an established trend.',
                'Breadth and concentration are measured over the documented market '
                'universe only.']}
