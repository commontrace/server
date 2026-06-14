"""Failure alerting wrapper — email on any unhandled exception, then re-raise."""
from __future__ import annotations

import traceback

from .config import Config
from .emailer import send_email


def run_with_alerting(job, name: str, cfg: Config, *, emailer=send_email):
    """Run job(). On exception: best-effort failure email, then re-raise the
    ORIGINAL exception (never mask it with an emailer error)."""
    try:
        return job()
    except Exception:
        tb = traceback.format_exc()
        try:
            emailer(
                cfg,
                subject=f"[CommonTrace ops] FAILED: {name}",
                body=f"Job '{name}' raised an unhandled exception.\n\n{tb}",
            )
        except Exception:
            # Resend itself may be down; Railway native cron-failure notification
            # is the backstop. Do not let this swallow the original error.
            pass
        raise
