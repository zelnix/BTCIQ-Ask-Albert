"""ResultMeta / Claim primitives - the single shape for provenance across both streams.

The dashboard spec is strict about one thing above all: a number is worthless without
its period, its source time, its coverage and its limitations. Everything in the market
package returns one of these envelopes, so the UI can never render a figure without
being able to say where it came from.
"""
import datetime
import hashlib
import uuid

MARKET_CONTRACT_VERSION = 'market-contracts-v1'

# DataStatus - what the caller is actually looking at.
FRESH = 'FRESH'            # measured, complete and inside its freshness budget
STALE = 'STALE'            # measured, but older than its freshness budget
PARTIAL = 'PARTIAL'        # measured over incomplete coverage (say how incomplete)
MISSING = 'MISSING'        # the inputs exist in principle but are not available now
UNSUPPORTED = 'UNSUPPORTED'  # this system cannot compute it at all yet
ERROR = 'ERROR'            # computation failed

# DataOrigin
OBSERVED = 'OBSERVED'
SIMULATED = 'SIMULATED'
DEMO = 'DEMO'              # never allowed in production responses

# MarketPhase
BTC_LED = 'BTC_LED'
ALTCOIN_LED = 'ALTCOIN_LED'
MIXED = 'MIXED'
UNKNOWN = 'UNKNOWN'

# Knowledge kinds - deliberately NOT collapsible into one confidence score.
OBSERVED_FACT = 'OBSERVED_FACT'
REPORTED_FACT = 'REPORTED_FACT'
SYSTEM_ASSESSMENT = 'SYSTEM_ASSESSMENT'
ALBERT_INTERPRETATION = 'ALBERT_INTERPRETATION'
WHAT_IF_ASSUMPTION = 'WHAT_IF_ASSUMPTION'
UNKNOWN_KIND = 'UNKNOWN'


def now_iso():
    return datetime.datetime.utcnow().isoformat()


def evidence_ref(kind, *parts):
    """A stable, opaque evidence reference. Stable means the same inputs always produce
    the same ref, so a claim can be re-opened later and resolved to the same record."""
    raw = '|'.join(str(p) for p in parts if p is not None)
    h = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
    return 'ev_%s_%s' % (kind, h)


def meta(section, *, status, origin=OBSERVED, as_of=None, available_at=None,
         evidence_refs=None, limitations=None, reason_code=None, rule_version=None,
         coverage=None):
    """Build a ResultMeta. `as_of` is the SOURCE time of the underlying evidence, which
    is not the same thing as when we generated the response - conflating the two is how
    stale data starts looking live."""
    return {
        'id': '%s_%s' % (section, uuid.uuid4().hex[:10]),
        'section': section,
        'generatedAt': now_iso(),
        'asOf': as_of,
        'availableAt': available_at or as_of,
        'status': status,
        'origin': origin,
        'ruleVersion': rule_version,
        'coverage': coverage,
        'evidenceRefs': list(evidence_refs or []),
        'limitations': list(limitations or []),
        'reasonCode': reason_code,
        'contractVersion': MARKET_CONTRACT_VERSION,
    }


def unsupported(section, reason_code, limitation, *, rule_version=None):
    """The honest empty answer. Used wherever the data or the model genuinely is not
    there - it is always preferable to a plausible-looking fabrication."""
    return meta(section, status=UNSUPPORTED, reason_code=reason_code,
                limitations=[limitation], rule_version=rule_version)


def claim(claim_id, text, kind, *, evidence_refs=None, affected=None,
          invalidation=None, deep_link=None):
    """One material statement, bound to its evidence and to what would falsify it."""
    return {'claimId': claim_id, 'text': text, 'kind': kind,
            'evidenceRefs': list(evidence_refs or []),
            'affectedEntities': list(affected or []),
            'invalidation': invalidation, 'deepLink': deep_link}


def dec_str(v, places=6):
    """Ratios and proportions travel as decimal strings in 0..1 - never as floats, and
    never pre-multiplied into display percentages."""
    if v is None:
        return None
    try:
        from decimal import Decimal, ROUND_HALF_UP
        q = Decimal(1).scaleb(-places)
        return str(Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP))
    except Exception:  # noqa
        return None
