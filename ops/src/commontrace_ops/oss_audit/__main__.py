"""Entrypoint: gather GitHub facts -> judge -> file/update GitHub issue."""
from __future__ import annotations

import datetime as _dt

from ..common.alerting import run_with_alerting
from ..common.config import load_config
from ..common.github import GitHub
from ..common.render import render_audit_issue
from .gather import gather_all
from .judge import judge_audit

LABEL = "audit"


def _iso_week(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run(cfg, *, dry_run=False, gh=None, judge=None, week=None):
    gh = gh or GitHub(cfg.github_token)
    judge = judge or judge_audit
    week = week or _iso_week()

    facts = gather_all(gh, cfg.repos)
    result = judge(cfg, facts)

    title = f"OSS Health Audit — {week}"
    body = render_audit_issue(title, result, facts)

    if dry_run:
        print(body)
        return

    existing = gh.find_issue(cfg.audit_issue_repo, title, label=LABEL)
    if existing:
        gh.update_issue(cfg.audit_issue_repo, existing["number"], body=body)
    else:
        gh.create_issue(cfg.audit_issue_repo, title=title, body=body, labels=[LABEL])


def main():
    import sys

    dry = "--dry-run" in sys.argv
    cfg = load_config(require_issue_repo=True)
    run_with_alerting(lambda: run(cfg, dry_run=dry), "oss-audit", cfg)


if __name__ == "__main__":
    main()
