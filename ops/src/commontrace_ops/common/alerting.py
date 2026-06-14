"""Failure alerting wrapper — email + optional Discord on any unhandled
exception, then re-raise."""
from __future__ import annotations

import traceback

from .config import Config
from .discord import send_discord
from .emailer import send_email


def run_with_alerting(job, name: str, cfg: Config, *, emailer=send_email, discord_send=send_discord):
    """Run job(). On exception: best-effort failure notifications (email, then
    Discord if configured), then re-raise the ORIGINAL exception (never mask it
    with a notifier error)."""
    try:
        return job()
    except Exception:
        tb = traceback.format_exc()
        subject = f"[CommonTrace ops] FAILED: {name}"
        body = f"Job '{name}' raised an unhandled exception.\n\n{tb}"
        try:
            emailer(cfg, subject=subject, body=body)
        except Exception:
            # Resend may be down; other channels + Railway native notification
            # are the backstop. Do not let this swallow the original error.
            pass
        if cfg.discord_webhook_url:
            try:
                discord_send(cfg.discord_webhook_url, f"🔴 **{subject}**\n```\n{tb}\n```")
            except Exception:
                pass
        raise
