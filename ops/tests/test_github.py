import pytest

from commontrace_ops.common.github import GitHub
from tests.conftest import FakeResponse


class RoutedClient:
    """httpx-like client that maps url-suffix -> queued FakeResponse(s).

    A list value pops one response per call (to simulate retry-then-success)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _resolve(self, method, url):
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                if isinstance(resp, list):
                    return resp.pop(0)
                return resp
        return FakeResponse(404, {"message": "not found"})

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        return self._resolve("GET", url)

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        return self._resolve("POST", url)

    def patch(self, url, **kw):
        self.calls.append(("PATCH", url))
        return self._resolve("PATCH", url)


def make_gh(routes):
    gh = GitHub(token="ghp-test", client=RoutedClient(routes))
    gh._sleep = lambda s: None
    return gh


def test_get_repo_returns_meta():
    gh = make_gh({"/repos/commontrace/server": FakeResponse(
        200, {"description": "API", "archived": False, "default_branch": "main",
              "open_issues_count": 4, "license": {"spdx_id": "MIT"}})})
    repo = gh.repo("commontrace/server")
    assert repo["default_branch"] == "main"
    assert repo["license"]["spdx_id"] == "MIT"


def test_retry_on_503_then_success():
    routes = {"/repos/commontrace/server": [
        FakeResponse(503, {}, text="unavailable"),
        FakeResponse(200, {"default_branch": "main"}),
    ]}
    gh = make_gh(routes)
    repo = gh.repo("commontrace/server")
    assert repo["default_branch"] == "main"


def test_raises_after_exhausting_retries():
    routes = {"/repos/commontrace/server": [
        FakeResponse(502, {}, text="bad gateway") for _ in range(5)
    ]}
    gh = make_gh(routes)
    with pytest.raises(RuntimeError) as exc:
        gh.repo("commontrace/server")
    assert "502" in str(exc.value)


def test_open_pulls_lists_prs():
    gh = make_gh({"/repos/commontrace/mcp/pulls?state=open&per_page=100": FakeResponse(
        200, [{"number": 7, "title": "Fix", "user": {"login": "alice"},
               "draft": False, "created_at": "2026-06-01T00:00:00Z"}])})
    pulls = gh.open_pulls("commontrace/mcp")
    assert pulls[0]["number"] == 7


def test_find_issue_matches_title():
    gh = make_gh({"/repos/commontrace/server/issues?state=open&labels=audit&per_page=100":
                  FakeResponse(200, [{"number": 3, "title": "OSS Health Audit — 2026-W24"}])})
    issue = gh.find_issue("commontrace/server", "OSS Health Audit — 2026-W24", label="audit")
    assert issue["number"] == 3


def test_find_issue_returns_none_when_absent():
    gh = make_gh({"/repos/commontrace/server/issues?state=open&labels=audit&per_page=100":
                  FakeResponse(200, [{"number": 3, "title": "something else"}])})
    assert gh.find_issue("commontrace/server", "OSS Health Audit — 2026-W24", label="audit") is None
