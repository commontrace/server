"""Discord alerts via incoming webhook — one-way, no bot, no gateway.

A webhook URL is a credential (anyone holding it can post to the channel), so it
lives only in env (DISCORD_WEBHOOK_URL), never in the repo. Sending is optional:
callers skip it when cfg.discord_webhook_url is unset.
"""
from __future__ import annotations

import httpx

# Discord rejects message content longer than 2000 chars.
DISCORD_LIMIT = 2000


def _chunks(content: str, limit: int = DISCORD_LIMIT):
    """Split content into <=limit pieces, preferring newline boundaries."""
    out = []
    while content:
        if len(content) <= limit:
            out.append(content)
            break
        cut = content.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        out.append(content[:cut])
        content = content[cut:].lstrip("\n")
    return out


def send_discord(webhook_url: str, content: str, *, username: str | None = None, client=None):
    """POST content to a Discord webhook, chunked to the 2000-char limit.

    Raises RuntimeError on any non-2xx (Discord returns 204 on success).
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        for chunk in _chunks(content):
            payload = {"content": chunk}
            if username:
                payload["username"] = username
            resp = client.post(webhook_url, json=payload)
            if not (200 <= resp.status_code < 300):
                raise RuntimeError(f"Discord send failed: {resp.status_code} {resp.text}")
    finally:
        if owns_client:
            client.close()
