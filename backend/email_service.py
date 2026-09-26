"""Resend transactional email (REST via `requests` — no extra dependency).

Used by the daily Alert Digest and the Settings "send test" action. The API key lives in
/app/.env as RESEND_API_KEY and is NEVER exposed to the browser (all sends are backend-side).
"""
import logging

import requests

from config import RESEND_API_KEY, RESEND_FROM

logger = logging.getLogger("askalbert.email")
RESEND_URL = "https://api.resend.com/emails"


def resend_configured():
    return bool(RESEND_API_KEY)


def send_email(to, subject, html, text=None, reply_to=None, headers=None):
    """Send an email via Resend. `to` may be a str or a list of addresses.

    Returns {"ok": True, "id": <resend_id>} on success, or {"ok": False, "error": <msg>}.
    The Resend error message is surfaced (e.g. domain-not-verified) WITHOUT leaking the key.
    """
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY is not configured on the server."}

    recipients = [to] if isinstance(to, str) else list(to or [])
    recipients = [r for r in recipients if r]
    if not recipients:
        return {"ok": False, "error": "No recipients."}

    payload = {"from": RESEND_FROM, "to": recipients, "subject": subject, "html": html}
    if text:
        payload["text"] = text
    if reply_to:
        payload["reply_to"] = reply_to
    if headers:
        payload["headers"] = headers

    try:
        r = requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or r.text
            except Exception:  # noqa
                msg = r.text
            logger.error("Resend send failed %s: %s", r.status_code, msg)
            return {"ok": False, "error": f"Resend {r.status_code}: {msg}"}
        try:
            eid = r.json().get("id")
        except Exception:  # noqa
            eid = None
        return {"ok": True, "id": eid}
    except Exception as e:  # noqa
        logger.exception("Resend request error")
        return {"ok": False, "error": str(e)}
