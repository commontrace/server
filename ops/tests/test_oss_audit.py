from commontrace_ops.common.config import Config
from commontrace_ops.oss_audit import __main__ as audit_main
from commontrace_ops.oss_audit.gather import gather_repo
from commontrace_ops.oss_audit.judge import AUDIT_SYSTEM_PROMPT


def make_cfg(**over):
    base = dict(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="a@x.com", alert_to="b@x.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo="commontrace/server",
    )
    base.update(over)
    return Config(**base)


class FakeGH:
    def __init__(self):
        self.created = []
        self.updated = []

    def repo(self, repo):
        return {"description": "API", "archived": False, "default_branch": "main",
                "open_issues_count": 4, "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-06-10T00:00:00Z", "topics": ["ai"]}

    def community_profile(self, repo):
        return {"health_percentage": 71,
                "files": {"readme": {"url": "x"}, "license": {"url": "y"},
                          "contributing": None, "code_of_conduct": None}}

    def latest_run(self, repo, branch):
        return {"conclusion": "success", "created_at": "2026-06-10T00:00:00Z"}

    def open_pulls(self, repo):
        return [{"number": 1, "created_at": "2026-06-01T00:00:00Z"}]

    def latest_release(self, repo):
        return {"tag_name": "v0.5.2", "published_at": "2026-05-01T00:00:00Z"}

    def find_issue(self, repo, title, *, label):
        return None

    def create_issue(self, repo, *, title, body, labels):
        self.created.append({"repo": repo, "title": title, "body": body, "labels": labels})
        return {"number": 42}

    def update_issue(self, repo, number, *, body):
        self.updated.append({"repo": repo, "number": number, "body": body})
        return {"number": number}


def test_gather_repo_shapes_facts():
    facts = gather_repo(FakeGH(), "commontrace/server")
    assert facts["repo"] == "commontrace/server"
    assert facts["default_branch"] == "main"
    assert facts["ci_conclusion"] == "success"
    assert facts["open_pull_count"] == 1
    assert facts["latest_release"] == "v0.5.2"
    assert facts["community_health_percentage"] == 71


def test_audit_system_prompt_mentions_rubric_and_json():
    assert "json" in AUDIT_SYSTEM_PROMPT.lower()
    assert "suggestion" in AUDIT_SYSTEM_PROMPT.lower()


def test_run_dry_run_files_nothing():
    gh = FakeGH()
    result = {"overall_grade": "B", "summary": "ok", "repos": [], "suggestions": []}
    audit_main.run(
        make_cfg(), dry_run=True, gh=gh,
        judge=lambda cfg, facts: result, week="2026-W24",
    )
    assert gh.created == [] and gh.updated == []


def test_run_creates_issue_when_absent():
    gh = FakeGH()
    result = {"overall_grade": "B", "summary": "ok", "repos": [], "suggestions": []}
    audit_main.run(
        make_cfg(), dry_run=False, gh=gh,
        judge=lambda cfg, facts: result, week="2026-W24",
    )
    assert len(gh.created) == 1
    assert gh.created[0]["title"] == "OSS Health Audit — 2026-W24"
    assert "audit" in gh.created[0]["labels"]


def test_run_updates_issue_when_present():
    gh = FakeGH()
    gh.find_issue = lambda repo, title, *, label: {"number": 9}
    result = {"overall_grade": "A", "summary": "ok", "repos": [], "suggestions": []}
    audit_main.run(
        make_cfg(), dry_run=False, gh=gh,
        judge=lambda cfg, facts: result, week="2026-W24",
    )
    assert gh.updated and gh.updated[0]["number"] == 9
    assert gh.created == []
