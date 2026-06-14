import datetime as _dt

from commontrace_ops.common.config import Config
from commontrace_ops.contrib_review import __main__ as review_main
from commontrace_ops.contrib_review.gather import _age_days, gather_prs
from commontrace_ops.contrib_review.triage import TRIAGE_SYSTEM_PROMPT


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="a@x.com", alert_to="b@x.com",
        repos=["commontrace/server", "commontrace/mcp"], model="gpt-5.5",
        database_url="postgresql://u:p@h/db", audit_issue_repo=None,
    )


NOW = _dt.datetime(2026, 6, 13, tzinfo=_dt.timezone.utc)


class FakeGH:
    def open_pulls(self, repo):
        if repo == "commontrace/mcp":
            return [{"number": 7, "title": "Fix proxy", "user": {"login": "alice"},
                     "draft": False, "created_at": "2026-06-04T00:00:00Z"}]
        return []

    def pull_detail(self, repo, number):
        return {"mergeable_state": "clean", "review_comments": 0}

    def pull_files(self, repo, number):
        return [{"filename": "mcp/server.py"}]


def test_age_days_handles_iso_string_and_datetime_and_none():
    assert _age_days("2026-06-04T00:00:00Z", now=NOW) == 9
    assert _age_days(_dt.datetime(2026, 6, 10, tzinfo=_dt.timezone.utc), now=NOW) == 3
    assert _age_days(None, now=NOW) is None


def test_gather_prs_collects_across_repos_with_age():
    prs = gather_prs(FakeGH(), ["commontrace/server", "commontrace/mcp"], now=NOW)
    assert len(prs) == 1
    assert prs[0]["repo"] == "commontrace/mcp"
    assert prs[0]["number"] == 7
    assert prs[0]["age_days"] == 9
    assert prs[0]["changed_files"] == ["mcp/server.py"]


def test_triage_prompt_mentions_prs_priority_and_json():
    low = TRIAGE_SYSTEM_PROMPT.lower()
    assert "json" in low
    assert "pull request" in low or "pr" in low


def test_run_dry_run_prints_and_sends_nothing():
    sent = []
    data = {"prs": [], "pending_traces": [], "flagged_traces": [], "amendments": []}
    review_main.run(
        make_cfg(), dry_run=True,
        gather=lambda cfg: data,
        triage=lambda cfg, d: {"prs": [], "traces": [], "amendments": []},
        emailer=lambda cfg, **kw: sent.append(kw),
        week="2026-W24",
    )
    assert sent == []


def test_run_sends_digest_even_when_empty_heartbeat():
    sent = []
    data = {"prs": [], "pending_traces": [], "flagged_traces": [], "amendments": []}
    review_main.run(
        make_cfg(), dry_run=False,
        gather=lambda cfg: data,
        triage=lambda cfg, d: {"prs": [], "traces": [], "amendments": []},
        emailer=lambda cfg, **kw: sent.append(kw),
        week="2026-W24",
    )
    assert len(sent) == 1
    assert "contribution review" in sent[0]["subject"].lower()
    assert sent[0]["html"]
