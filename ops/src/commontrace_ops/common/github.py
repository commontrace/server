"""GitHub REST client (httpx) with bounded retry on transient failures."""
from __future__ import annotations

import time

import httpx

API = "https://api.github.com"
RETRY_STATUS = {502, 503, 504}
MAX_RETRIES = 4


class GitHub:
    def __init__(self, token: str, *, client=None):
        self.token = token
        self._client = client or httpx.Client(timeout=30)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._sleep = time.sleep

    def _request(self, method: str, path: str, **kw):
        url = path if path.startswith("http") else f"{API}{path}"
        last = None
        for attempt in range(MAX_RETRIES + 1):
            fn = getattr(self._client, method.lower())
            resp = fn(url, headers=self._headers, **kw)
            last = resp
            transient = resp.status_code in RETRY_STATUS or (
                resp.status_code == 403
                and "rate limit" in (resp.text or "").lower()
            )
            if not transient:
                if not (200 <= resp.status_code < 300):
                    raise RuntimeError(f"GitHub {method} {path} -> {resp.status_code} {resp.text}")
                return resp.json()
            if attempt < MAX_RETRIES:
                self._sleep(2 ** attempt)
        raise RuntimeError(
            f"GitHub {method} {path} failed after retries -> {last.status_code} {last.text}"
        )

    def _get(self, path: str):
        return self._request("GET", path)

    # ---- read ----
    def repo(self, repo: str) -> dict:
        return self._get(f"/repos/{repo}")

    def community_profile(self, repo: str) -> dict:
        try:
            return self._get(f"/repos/{repo}/community/profile")
        except RuntimeError:
            return {}

    def latest_run(self, repo: str, branch: str) -> dict | None:
        data = self._get(f"/repos/{repo}/actions/runs?branch={branch}&per_page=1")
        runs = data.get("workflow_runs", [])
        return runs[0] if runs else None

    def open_pulls(self, repo: str) -> list[dict]:
        return self._get(f"/repos/{repo}/pulls?state=open&per_page=100")

    def pull_detail(self, repo: str, number: int) -> dict:
        return self._get(f"/repos/{repo}/pulls/{number}")

    def pull_files(self, repo: str, number: int) -> list[dict]:
        return self._get(f"/repos/{repo}/pulls/{number}/files?per_page=100")

    def latest_release(self, repo: str) -> dict | None:
        try:
            return self._get(f"/repos/{repo}/releases/latest")
        except RuntimeError:
            return None

    def find_issue(self, repo: str, title: str, *, label: str) -> dict | None:
        issues = self._get(f"/repos/{repo}/issues?state=open&labels={label}&per_page=100")
        for issue in issues:
            if issue.get("title") == title and "pull_request" not in issue:
                return issue
        return None

    # ---- write ----
    def create_issue(self, repo: str, *, title: str, body: str, labels: list[str]) -> dict:
        return self._request(
            "POST", f"/repos/{repo}/issues",
            json={"title": title, "body": body, "labels": labels},
        )

    def update_issue(self, repo: str, number: int, *, body: str) -> dict:
        return self._request(
            "PATCH", f"/repos/{repo}/issues/{number}", json={"body": body},
        )
