"""Transactional email via Resend."""
from __future__ import annotations

import httpx

from .config import Config

RESEND_URL = "https://api.resend.com/emails"


def send_email(cfg: Config, *, subject: str, body: str, html: str | None = None, client=None):
    """POST one email to Resend. Raises RuntimeError on non-2xx."""
    payload = {
        "from": cfg.alert_from,
        "to": [cfg.alert_to],
        "subject": subject,
        "text": body,
    }
    if html is not None:
        payload["html"] = html

    headers = {
        "Authorization": f"Bearer {cfg.resend_api_key}",
        "Content-Type": "application/json",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.post(RESEND_URL, headers=headers, json=payload)
    finally:
        if owns_client:
            client.close()

    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"Resend send failed: {resp.status_code} {resp.text}")
    return resp.json()
