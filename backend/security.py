"""Security helpers for the BitMarkAI backend.

Per-client rate limiting (MongoDB-backed so limits are exact across replicas, with an
in-memory fallback if the DB briefly hiccups) and constant-time admin passcode checks.
Extracted from server.py as part of the Option A refactor — no behaviour changes.
"""
import time
import uuid
import hmac
import datetime
import threading

from fastapi.responses import JSONResponse

from config import rate_col, ADMIN_PASSCODE

# ---- Lightweight in-memory per-client rate limiter fallback (cost/DoS guard) ----
_rl_lock = threading.Lock()
_rl_hits = {}  # key -> [timestamps]


def _client_key(request):
    try:
        xff = request.headers.get('x-forwarded-for') or request.headers.get('x-real-ip')
        if xff:
            return xff.split(',')[0].strip()
        return request.client.host if request.client else 'unknown'
    except Exception:  # noqa
        return 'unknown'


def _rate_limited(request, bucket, per_min=15, per_day=300):
    """Return True if this client has exceeded the limit for `bucket`.

    Backed by MongoDB so limits are EXACT across all deployment replicas (each
    request inserts a timestamped hit; we then count hits in the 60s / 24h windows).
    Falls back to a per-process in-memory window if the DB is briefly unavailable.
    """
    now = time.time()
    key = f'{bucket}:{_client_key(request)}'
    try:
        now_dt = datetime.datetime.utcnow()
        rate_col.insert_one({'_id': str(uuid.uuid4()), 'key': key, 'ts': now_dt})
        minute_ago = now_dt - datetime.timedelta(seconds=60)
        day_ago = now_dt - datetime.timedelta(seconds=86400)
        recent = rate_col.count_documents({'key': key, 'ts': {'$gte': minute_ago}})
        if recent > per_min:
            return True
        daily = rate_col.count_documents({'key': key, 'ts': {'$gte': day_ago}})
        return daily > per_day
    except Exception:  # noqa — DB hiccup: degrade to in-memory limiter, never crash the request
        with _rl_lock:
            hits = [t for t in _rl_hits.get(key, []) if now - t < 86400]
            recent = sum(1 for t in hits if now - t < 60)
            if recent >= per_min or len(hits) >= per_day:
                _rl_hits[key] = hits
                return True
            hits.append(now)
            _rl_hits[key] = hits
            return False


def _passcode_ok(supplied):
    """Constant-time admin passcode check. Denies if no passcode is configured."""
    expected = ADMIN_PASSCODE or ''
    supplied = supplied or ''
    if not expected:
        return False
    return hmac.compare_digest(str(supplied), str(expected))


def _retry_after_secs(request, bucket, per_min):
    """Estimate seconds until this client can retry (when enough hits age out of the 60s window)."""
    key = f'{bucket}:{_client_key(request)}'
    try:
        now_dt = datetime.datetime.utcnow()
        minute_ago = now_dt - datetime.timedelta(seconds=60)
        docs = list(rate_col.find({'key': key, 'ts': {'$gte': minute_ago}}, {'ts': 1}).sort('ts', 1))
        n = len(docs)
        if n <= per_min:
            return 1
        # After the oldest (n - per_min) hits age out, the count drops to per_min (allowed).
        idx = n - per_min - 1
        free_at = docs[idx]['ts'] + datetime.timedelta(seconds=60)
        secs = (free_at - now_dt).total_seconds()
        return max(1, min(60, int(secs) + 1))
    except Exception:  # noqa
        return 30


def _too_many(request, bucket, per_min=15, per_day=300):
    """Return a JSONResponse(429) if rate-limited, else None."""
    if _rate_limited(request, bucket, per_min=per_min, per_day=per_day):
        retry = _retry_after_secs(request, bucket, per_min)
        return JSONResponse(
            status_code=429,
            content={'status': 'rate_limited', 'retry_in': retry,
                     'error': 'Too many requests — please slow down and try again shortly.'},
        )
    return None
