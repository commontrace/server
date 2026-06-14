"""Entrypoint: gather PRs+DB -> triage -> email digest (always, heartbeat).

The weekly digest goes to email (authoritative — a send failure fails the job and
trips the failure alert) and, if DISCORD_WEBHOOK_URL is set, also to Discord
(best-effort — a Discord hiccup never fails the job)."""
from __future__ import annotations

import datetime as _dt
import sys

from ..common.alerting import run_with_alerting
from ..common.config import load_config
from ..common.discord import send_discord
from ..common.emailer import send_email
from ..common.github import GitHub
from ..common.render import render_review_digest
from .gather import gather_all
from .triage import triage as triage_fn


def _iso_week(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run(cfg, *, dry_run=False, gather=None, triage=None, emailer=None, discord_send=None, week=None):
    gather = gather or (lambda c: gather_all(GitHub(c.github_token), c))
    triage = triage or triage_fn
    emailer = emailer or send_email
    discord_send = discord_send or send_discord
    week = week or _iso_week()

    data = gather(cfg)
    result = triage(cfg, data)

    subject = f"CommonTrace contribution review — {week}"
    text, html = render_review_digest(subject, data, result)

    if dry_run:
        print(text)
        return

    # Always send — empty queue is a heartbeat that the job ran.
    emailer(cfg, subject=subject, body=text, html=html)

    if cfg.discord_webhook_url:
        try:
            discord_send(cfg.discord_webhook_url, f"📋 **{subject}**\n{text}")
        except Exception as exc:  # best-effort; email already delivered
            print(f"discord digest send failed: {exc}", file=sys.stderr)


def main():
    dry = "--dry-run" in sys.argv
    cfg = load_config(require_db=True)
    run_with_alerting(lambda: run(cfg, dry_run=dry), "contrib-review", cfg)


if __name__ == "__main__":
    main()
