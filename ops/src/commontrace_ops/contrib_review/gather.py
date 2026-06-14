"""Collect open PRs (GitHub) and contribution data (DB) for triage."""
from __future__ import annotations

import datetime as _dt


def _parse(ts):
    if ts is None:
        return None
    if isinstance(ts, _dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=_dt.timezone.utc)
    return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _age_days(ts, *, now=None):
    now = now or _dt.datetime.now(_dt.timezone.utc)
    dt = _parse(ts)
    if dt is None:
        return None
    return (now - dt).days


def gather_prs(gh, repos: list[str], *, now=None) -> list[dict]:
    out = []
    for repo in repos:
        for pr in gh.open_pulls(repo):
            number = pr["number"]
            detail = gh.pull_detail(repo, number)
            files = [f.get("filename") for f in gh.pull_files(repo, number)]
            out.append({
                "repo": repo,
                "number": number,
                "title": pr.get("title"),
                "author": (pr.get("user") or {}).get("login"),
                "draft": pr.get("draft", False),
                "age_days": _age_days(pr.get("created_at"), now=now),
                "mergeable_state": detail.get("mergeable_state"),
                "review_comments": detail.get("review_comments"),
                "changed_files": files,
            })
    return out


def gather_all(gh, cfg, *, now=None, db_fetch=None) -> dict:
    """PRs from GitHub + pending/flagged/amendments from DB.

    db_fetch is an async callable(database_url)->dict, injectable for tests."""
    import asyncio

    from ..common.db import fetch_review_data

    db_fetch = db_fetch or fetch_review_data
    prs = gather_prs(gh, cfg.repos, now=now)
    db = asyncio.run(db_fetch(cfg.database_url))

    for t in db.get("pending_traces", []):
        t["age_days"] = _age_days(t.get("created_at"), now=now)
    for a in db.get("amendments", []):
        a["age_days"] = _age_days(a.get("created_at"), now=now)

    return {
        "prs": prs,
        "pending_traces": db.get("pending_traces", []),
        "flagged_traces": db.get("flagged_traces", []),
        "amendments": db.get("amendments", []),
    }
