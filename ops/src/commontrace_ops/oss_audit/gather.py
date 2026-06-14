"""Collect OSS-health facts per repo from GitHub."""
from __future__ import annotations


def gather_repo(gh, repo: str) -> dict:
    meta = gh.repo(repo)
    branch = meta.get("default_branch", "main")
    profile = gh.community_profile(repo)
    run = gh.latest_run(repo, branch)
    pulls = gh.open_pulls(repo)
    release = gh.latest_release(repo)

    files = (profile.get("files") or {})
    present = {name: bool(files.get(name)) for name in (
        "readme", "license", "contributing", "code_of_conduct",
        "issue_template", "pull_request_template",
    )}

    return {
        "repo": repo,
        "description": meta.get("description"),
        "topics": meta.get("topics", []),
        "archived": meta.get("archived", False),
        "default_branch": branch,
        "license": (meta.get("license") or {}).get("spdx_id"),
        "pushed_at": meta.get("pushed_at"),
        "open_issues_count": meta.get("open_issues_count"),
        "open_pull_count": len(pulls),
        "community_health_percentage": profile.get("health_percentage"),
        "community_files": present,
        "ci_conclusion": (run or {}).get("conclusion"),
        "ci_run_at": (run or {}).get("created_at"),
        "latest_release": (release or {}).get("tag_name"),
        "latest_release_at": (release or {}).get("published_at"),
    }


def gather_all(gh, repos: list[str]) -> dict:
    return {repo: gather_repo(gh, repo) for repo in repos}
