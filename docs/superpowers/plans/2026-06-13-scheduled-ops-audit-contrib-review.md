# Scheduled Ops: OSS-Health Audit + Contribution Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `ops/` package (`commontrace_ops`) with two Railway cron jobs — `oss_audit` (weekly OSS-health audit → GitHub issue) and `contrib_review` (weekly contribution triage digest → email) — using OpenAI (gpt-5.5) for judgment, GitHub REST for facts, read-only Postgres for contributions, Resend for email, and a failure-alerting wrapper.

**Architecture:** One Docker image, two Railway cron services selected by `railwayConfigPath` (different `startCommand` + `cronSchedule`). Each entrypoint runs `gather → judge/triage → emit (issue or email)` wrapped in `run_with_alerting`, which emails `tools@denemlabs.com` on any unhandled exception then re-raises (non-zero exit → Railway native cron-failure notification as backstop). Config fails fast on missing secrets. All external services (OpenAI, GitHub, Resend, DB) are injectable for unit testing — no live calls in CI.

**Tech Stack:** Python 3.12, httpx (GitHub + Resend), openai SDK (Chat Completions JSON mode), asyncpg (read-only DB), hatchling build, pytest + pytest-asyncio (`asyncio_mode=auto`), Docker (python:3.12-slim), Railway cron.

---

## File Structure

```
ops/
  Dockerfile                          # one image, both entrypoints
  pyproject.toml                      # hatchling, deps, pytest config
  railway.audit.toml                  # cron "0 8 * * 1", start = python -m commontrace_ops.oss_audit
  railway.review.toml                 # cron "0 9 * * 1", start = python -m commontrace_ops.contrib_review
  src/commontrace_ops/
    __init__.py
    common/
      __init__.py
      config.py        # Config dataclass + load_config() — fail fast on missing secret
      emailer.py       # send_email() — Resend HTTP POST
      alerting.py      # run_with_alerting(job, name, cfg) — exception -> failure email -> re-raise
      llm.py           # judge_json() — OpenAI Chat Completions JSON-mode wrapper
      github.py        # GitHub class — REST via httpx, bounded retry
      db.py            # query_review_data(conn) + fetch_review_data(url) — read-only asyncpg
      render.py        # render_audit_issue(), render_review_digest()
    oss_audit/
      __init__.py
      gather.py        # gather_repo(gh, repo) -> facts dict; gather_all(gh, repos)
      judge.py         # AUDIT_SYSTEM_PROMPT, judge_audit(cfg, facts)
      __main__.py      # run(cfg, *, dry_run) -> file/update issue; main()
    contrib_review/
      __init__.py
      gather.py        # gather_prs(gh, repos), gather_all(gh, cfg)
      triage.py        # TRIAGE_SYSTEM_PROMPT, triage(cfg, data)
      __main__.py      # run(cfg, *, dry_run) -> email digest; main()
  tests/
    __init__.py
    conftest.py        # shared fakes (FakeResponse, fake clients)
    test_config.py
    test_emailer.py
    test_alerting.py
    test_llm.py
    test_render.py
    test_github.py
    test_db.py
    test_oss_audit.py
    test_contrib_review.py
```

---

## Task 1: Scaffold package, build, Docker, Railway configs

**Files:**
- Create: `ops/pyproject.toml`
- Create: `ops/Dockerfile`
- Create: `ops/railway.audit.toml`
- Create: `ops/railway.review.toml`
- Create: `ops/src/commontrace_ops/__init__.py`
- Create: `ops/src/commontrace_ops/common/__init__.py`
- Create: `ops/src/commontrace_ops/oss_audit/__init__.py`
- Create: `ops/src/commontrace_ops/contrib_review/__init__.py`
- Create: `ops/tests/__init__.py`
- Create: `ops/tests/conftest.py`

- [ ] **Step 1: Create `ops/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "commontrace-ops"
version = "0.1.0"
description = "CommonTrace scheduled ops: OSS-health audit + contribution review"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "openai>=1.0",
    "asyncpg>=0.29",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[tool.hatch.build.targets.wheel]
packages = ["src/commontrace_ops"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package `__init__.py` files**

`ops/src/commontrace_ops/__init__.py`:

```python
"""CommonTrace scheduled ops tooling."""
```

`ops/src/commontrace_ops/common/__init__.py`:

```python
```

`ops/src/commontrace_ops/oss_audit/__init__.py`:

```python
```

`ops/src/commontrace_ops/contrib_review/__init__.py`:

```python
```

`ops/tests/__init__.py`:

```python
```

- [ ] **Step 3: Create `ops/tests/conftest.py`** (shared test fakes)

```python
"""Shared test fakes — no live network/DB calls in CI."""
import json


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or json.dumps(self._json)

    def json(self):
        return self._json


class FakeHTTPClient:
    """Records POSTs; returns a queued FakeResponse."""

    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response
```

- [ ] **Step 4: Create `ops/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
# startCommand is supplied per-service by railway.*.toml
CMD ["python", "-m", "commontrace_ops.oss_audit"]
```

- [ ] **Step 5: Create `ops/railway.audit.toml`**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "python -m commontrace_ops.oss_audit"
restartPolicyType = "NEVER"
cronSchedule = "0 8 * * 1"
```

- [ ] **Step 6: Create `ops/railway.review.toml`**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "python -m commontrace_ops.contrib_review"
restartPolicyType = "NEVER"
cronSchedule = "0 9 * * 1"
```

- [ ] **Step 7: Verify the package imports and pytest collects**

Run: `cd ops && pip install -e ".[dev]" && python -c "import commontrace_ops" && pytest -q`
Expected: install succeeds, import works, pytest reports "no tests ran" (0 collected, exit 5) — acceptable at this stage.

- [ ] **Step 8: Commit**

```bash
git add ops/pyproject.toml ops/Dockerfile ops/railway.audit.toml ops/railway.review.toml ops/src/commontrace_ops/__init__.py ops/src/commontrace_ops/common/__init__.py ops/src/commontrace_ops/oss_audit/__init__.py ops/src/commontrace_ops/contrib_review/__init__.py ops/tests/__init__.py ops/tests/conftest.py
git commit -m "feat(ops): scaffold commontrace_ops package, Docker, Railway cron configs"
```

---

## Task 2: `config.py` — env loading + fail-fast validation

**Files:**
- Create: `ops/src/commontrace_ops/common/config.py`
- Test: `ops/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_config.py`:

```python
import pytest

from commontrace_ops.common.config import Config, ConfigError, load_config

BASE_ENV = {
    "OPENAI_API_KEY": "sk-test",
    "RESEND_API_KEY": "re-test",
    "GITHUB_TOKEN": "ghp-test",
    "ALERT_EMAIL_FROM": "alerts@denemlabs.com",
    "ALERT_EMAIL_TO": "tools@denemlabs.com",
    "REPOS": "commontrace/server,commontrace/mcp",
}


def test_load_config_parses_repos_and_defaults_model():
    cfg = load_config(env=BASE_ENV)
    assert isinstance(cfg, Config)
    assert cfg.repos == ["commontrace/server", "commontrace/mcp"]
    assert cfg.model == "gpt-5.5"
    assert cfg.alert_to == "tools@denemlabs.com"


def test_model_override():
    cfg = load_config(env={**BASE_ENV, "CT_MODEL": "gpt-5.5-mini"})
    assert cfg.model == "gpt-5.5-mini"


def test_missing_required_raises_config_error():
    env = dict(BASE_ENV)
    del env["OPENAI_API_KEY"]
    with pytest.raises(ConfigError) as exc:
        load_config(env=env)
    assert "OPENAI_API_KEY" in str(exc.value)


def test_require_db_demands_database_url():
    with pytest.raises(ConfigError) as exc:
        load_config(env=BASE_ENV, require_db=True)
    assert "DATABASE_URL" in str(exc.value)


def test_require_issue_repo_demands_audit_issue_repo():
    with pytest.raises(ConfigError) as exc:
        load_config(env=BASE_ENV, require_issue_repo=True)
    assert "AUDIT_ISSUE_REPO" in str(exc.value)


def test_db_url_normalizes_asyncpg_scheme():
    env = {**BASE_ENV, "DATABASE_URL": "postgresql+asyncpg://u:p@h/db"}
    cfg = load_config(env=env, require_db=True)
    assert cfg.database_url == "postgresql://u:p@h/db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.config'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/config.py`:

```python
"""Environment configuration with fail-fast validation."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    resend_api_key: str
    github_token: str
    alert_from: str
    alert_to: str
    repos: list[str]
    model: str
    database_url: str | None
    audit_issue_repo: str | None


REQUIRED = [
    "OPENAI_API_KEY",
    "RESEND_API_KEY",
    "GITHUB_TOKEN",
    "ALERT_EMAIL_FROM",
    "ALERT_EMAIL_TO",
    "REPOS",
]


def _normalize_db_url(url: str) -> str:
    # asyncpg.connect() does not accept the SQLAlchemy "+asyncpg" dialect suffix.
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def load_config(
    *,
    env: dict | None = None,
    require_db: bool = False,
    require_issue_repo: bool = False,
) -> Config:
    env = dict(os.environ if env is None else env)

    missing = [k for k in REQUIRED if not env.get(k)]
    if require_db and not env.get("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if require_issue_repo and not env.get("AUDIT_ISSUE_REPO"):
        missing.append("AUDIT_ISSUE_REPO")
    if missing:
        raise ConfigError(f"missing required env: {', '.join(missing)}")

    repos = [r.strip() for r in env["REPOS"].split(",") if r.strip()]
    if not repos:
        raise ConfigError("REPOS is empty after parsing")

    db_url = env.get("DATABASE_URL")
    return Config(
        openai_api_key=env["OPENAI_API_KEY"],
        resend_api_key=env["RESEND_API_KEY"],
        github_token=env["GITHUB_TOKEN"],
        alert_from=env["ALERT_EMAIL_FROM"],
        alert_to=env["ALERT_EMAIL_TO"],
        repos=repos,
        model=env.get("CT_MODEL", "gpt-5.5"),
        database_url=_normalize_db_url(db_url) if db_url else None,
        audit_issue_repo=env.get("AUDIT_ISSUE_REPO"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_config.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/config.py ops/tests/test_config.py
git commit -m "feat(ops): config loader with fail-fast secret validation"
```

---

## Task 3: `emailer.py` — Resend HTTP wrapper

**Files:**
- Create: `ops/src/commontrace_ops/common/emailer.py`
- Test: `ops/tests/test_emailer.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_emailer.py`:

```python
import pytest

from commontrace_ops.common.config import Config
from commontrace_ops.common.emailer import send_email
from tests.conftest import FakeHTTPClient, FakeResponse


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re-key", github_token="gh",
        alert_from="alerts@denemlabs.com", alert_to="tools@denemlabs.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


def test_send_email_posts_to_resend_with_auth_and_payload():
    client = FakeHTTPClient(FakeResponse(200, {"id": "email_123"}))
    cfg = make_cfg()
    send_email(cfg, subject="Hi", body="plain text", client=client)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re-key"
    payload = call["json"]
    assert payload["from"] == "alerts@denemlabs.com"
    assert payload["to"] == ["tools@denemlabs.com"]
    assert payload["subject"] == "Hi"
    assert payload["text"] == "plain text"
    assert "html" not in payload


def test_send_email_includes_html_when_provided():
    client = FakeHTTPClient(FakeResponse(200, {"id": "x"}))
    send_email(make_cfg(), subject="S", body="t", html="<p>t</p>", client=client)
    assert client.calls[0]["json"]["html"] == "<p>t</p>"


def test_send_email_raises_on_non_2xx():
    client = FakeHTTPClient(FakeResponse(422, {"error": "bad"}, text="bad"))
    with pytest.raises(RuntimeError) as exc:
        send_email(make_cfg(), subject="S", body="t", client=client)
    assert "422" in str(exc.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_emailer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.emailer'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/emailer.py`:

```python
"""Transactional email via Resend."""
from __future__ import annotations

import httpx

from .config import Config

RESEND_URL = "https://api.resend.com/emails"


def send_email(cfg: Config, *, subject: str, body: str, html: str | None = None, client=None):
    """POST one email to Resend. Raises RuntimeError on non-2xx."""
    payload = {
        "from": cfg.alert_from,
        "to": [cfg.alert_to],
        "subject": subject,
        "text": body,
    }
    if html is not None:
        payload["html"] = html

    headers = {
        "Authorization": f"Bearer {cfg.resend_api_key}",
        "Content-Type": "application/json",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.post(RESEND_URL, headers=headers, json=payload)
    finally:
        if owns_client:
            client.close()

    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"Resend send failed: {resp.status_code} {resp.text}")
    return resp.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_emailer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/emailer.py ops/tests/test_emailer.py
git commit -m "feat(ops): Resend email wrapper"
```

---

## Task 4: `alerting.py` — run_with_alerting wrapper

**Files:**
- Create: `ops/src/commontrace_ops/common/alerting.py`
- Test: `ops/tests/test_alerting.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_alerting.py`:

```python
import pytest

from commontrace_ops.common.alerting import run_with_alerting
from commontrace_ops.common.config import Config


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="alerts@denemlabs.com", alert_to="tools@denemlabs.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


def test_success_path_does_not_email():
    sent = []
    run_with_alerting(lambda: "ok", "test-job", make_cfg(),
                      emailer=lambda cfg, **kw: sent.append(kw))
    assert sent == []


def test_failure_sends_email_then_reraises():
    sent = []

    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        run_with_alerting(boom, "oss-audit", make_cfg(),
                          emailer=lambda cfg, **kw: sent.append(kw))

    assert len(sent) == 1
    assert "oss-audit" in sent[0]["subject"]
    assert "kaboom" in sent[0]["body"]
    assert "ValueError" in sent[0]["body"]


def test_emailer_failure_does_not_mask_original():
    def boom():
        raise ValueError("original")

    def broken_emailer(cfg, **kw):
        raise RuntimeError("resend down")

    # Original error must surface, not the emailer error.
    with pytest.raises(ValueError, match="original"):
        run_with_alerting(boom, "job", make_cfg(), emailer=broken_emailer)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_alerting.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.alerting'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/alerting.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_alerting.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/alerting.py ops/tests/test_alerting.py
git commit -m "feat(ops): run_with_alerting failure-email wrapper"
```

---

## Task 5: `llm.py` — OpenAI Chat Completions JSON wrapper

**Files:**
- Create: `ops/src/commontrace_ops/common/llm.py`
- Test: `ops/tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_llm.py`:

```python
import json

import pytest

from commontrace_ops.common.config import Config
from commontrace_ops.common.llm import judge_json


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="a@x.com", alert_to="b@x.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class FakeOpenAI:
    """Mimics openai.OpenAI().chat.completions.create()."""

    def __init__(self, content):
        self._content = content
        self.last_kwargs = None

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                return _FakeCompletion(outer._content)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_judge_json_parses_model_json_and_passes_model_and_messages():
    client = FakeOpenAI(json.dumps({"grade": "B", "items": [1, 2]}))
    out = judge_json(make_cfg(), "system rubric", {"facts": 1}, client=client)

    assert out == {"grade": "B", "items": [1, 2]}
    assert client.last_kwargs["model"] == "gpt-5.5"
    assert client.last_kwargs["response_format"] == {"type": "json_object"}
    msgs = client.last_kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "system rubric"
    assert msgs[1]["role"] == "user"
    assert json.loads(msgs[1]["content"]) == {"facts": 1}


def test_judge_json_raises_on_unparseable_content():
    client = FakeOpenAI("not json")
    with pytest.raises(ValueError):
        judge_json(make_cfg(), "sys", {"x": 1}, client=client)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.llm'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/llm.py`:

```python
"""OpenAI Chat Completions JSON-mode wrapper. Ops tooling only — not product."""
from __future__ import annotations

import json

from .config import Config


def _make_client(cfg: Config):
    from openai import OpenAI

    return OpenAI(api_key=cfg.openai_api_key)


def judge_json(cfg: Config, system_prompt: str, user_payload: dict, *, client=None) -> dict:
    """One JSON-mode completion. Returns parsed dict. Raises ValueError if the
    model returns non-JSON."""
    client = client or _make_client(cfg)
    resp = client.chat.completions.create(
        model=cfg.model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"model returned non-JSON content: {content!r}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_llm.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/llm.py ops/tests/test_llm.py
git commit -m "feat(ops): OpenAI JSON-mode judge wrapper"
```

---

## Task 6: `render.py` — markdown rendering helpers

**Files:**
- Create: `ops/src/commontrace_ops/common/render.py`
- Test: `ops/tests/test_render.py`

The model returns structured JSON. `render.py` turns it into the human-facing GitHub issue body (Job A) and email digest (Job B). Rendering is pure (no I/O), so it is fully unit-testable.

**Audit result shape** (from judge): `{"overall_grade": "B", "summary": "...", "repos": [{"repo": "...", "assessment": "...", "scores": {"documentation": 4, ...}}], "suggestions": [{"priority": 1, "title": "...", "detail": "..."}]}`

**Review result shape** (from triage): `{"prs": [{"repo": "...", "number": 12, "title": "...", "recommendation": "merge", "reason": "..."}], "traces": [{"id": "...", "title": "...", "recommendation": "keep", "reason": "..."}], "amendments": [{"id": "...", "recommendation": "needs-work", "reason": "..."}]}`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_render.py`:

```python
from commontrace_ops.common.render import render_audit_issue, render_review_digest


def test_render_audit_issue_includes_grade_suggestions_and_facts_footer():
    result = {
        "overall_grade": "B",
        "summary": "Solid but docs thin.",
        "repos": [
            {"repo": "commontrace/server", "assessment": "Good CI.",
             "scores": {"documentation": 3, "ci_tests": 5}},
        ],
        "suggestions": [
            {"priority": 1, "title": "Add SECURITY.md", "detail": "No disclosure policy."},
            {"priority": 2, "title": "Add CONTRIBUTING", "detail": "Onboarding unclear."},
        ],
    }
    facts = {"commontrace/server": {"open_issues": 4}}
    body = render_audit_issue("OSS Health Audit — 2026-W24", result, facts)

    assert "OSS Health Audit — 2026-W24" in body
    assert "**Overall grade:** B" in body
    assert "Add SECURITY.md" in body
    assert "Add CONTRIBUTING" in body
    assert "commontrace/server" in body
    # Suggestions ordered by priority.
    assert body.index("Add SECURITY.md") < body.index("Add CONTRIBUTING")
    # Raw facts available for audit trail.
    assert "open_issues" in body


def test_render_review_digest_priority_prs_first_and_returns_text_and_html():
    data = {
        "prs": [{"repo": "commontrace/mcp", "number": 7, "title": "Fix proxy",
                 "author": "alice", "age_days": 9, "draft": False}],
        "pending_traces": [{"id": "t1", "title": "Redis tip", "contributor": "bob",
                            "age_days": 3}],
        "flagged_traces": [],
        "amendments": [],
    }
    result = {
        "prs": [{"repo": "commontrace/mcp", "number": 7,
                 "recommendation": "review-needed", "reason": "CI red."}],
        "traces": [{"id": "t1", "recommendation": "keep", "reason": "Useful."}],
        "amendments": [],
    }
    text, html = render_review_digest("CommonTrace contribution review — 2026-W24", data, result)

    assert "CommonTrace contribution review — 2026-W24" in text
    # PRs are the priority section — appear before traces.
    assert text.index("Pull Requests") < text.index("Pending Traces")
    assert "#7" in text
    assert "review-needed" in text
    assert "<html" in html.lower() or "<table" in html.lower()
    assert "#7" in html


def test_render_review_digest_empty_queue_is_heartbeat():
    data = {"prs": [], "pending_traces": [], "flagged_traces": [], "amendments": []}
    result = {"prs": [], "traces": [], "amendments": []}
    text, html = render_review_digest("subj", data, result)
    assert "nothing pending" in text.lower() or "all clear" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.render'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/render.py`:

```python
"""Pure markdown / HTML rendering for the audit issue and review digest."""
from __future__ import annotations

import json


def render_audit_issue(title: str, result: dict, facts: dict) -> str:
    lines = [f"# {title}", ""]
    grade = result.get("overall_grade", "?")
    lines.append(f"**Overall grade:** {grade}")
    lines.append("")
    if result.get("summary"):
        lines.append(result["summary"])
        lines.append("")

    lines.append("## Prioritized suggestions")
    lines.append("")
    suggestions = sorted(result.get("suggestions", []), key=lambda s: s.get("priority", 99))
    for s in suggestions:
        lines.append(f"### {s.get('priority', '?')}. {s.get('title', 'Untitled')}")
        lines.append(s.get("detail", ""))
        lines.append("")

    lines.append("## Per-repo assessment")
    lines.append("")
    for r in result.get("repos", []):
        lines.append(f"### {r.get('repo', '?')}")
        lines.append(r.get("assessment", ""))
        scores = r.get("scores", {})
        if scores:
            lines.append("")
            for dim, val in scores.items():
                lines.append(f"- {dim}: {val}/5")
        lines.append("")

    lines.append("---")
    lines.append("<details><summary>Raw gathered facts</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(facts, indent=2, default=str))
    lines.append("```")
    lines.append("</details>")
    return "\n".join(lines)


def _section(title: str, rows: list[str]) -> list[str]:
    out = [f"## {title}", ""]
    if not rows:
        out.append("_none_")
    else:
        out.extend(rows)
    out.append("")
    return out


def render_review_digest(subject: str, data: dict, result: dict) -> tuple[str, str]:
    prs = data.get("prs", [])
    pending = data.get("pending_traces", [])
    flagged = data.get("flagged_traces", [])
    amendments = data.get("amendments", [])

    rec_by = {
        "prs": {(r.get("repo"), r.get("number")): r for r in result.get("prs", [])},
        "traces": {r.get("id"): r for r in result.get("traces", [])},
        "amendments": {r.get("id"): r for r in result.get("amendments", [])},
    }

    total = len(prs) + len(pending) + len(flagged) + len(amendments)

    text_lines = [subject, "=" * len(subject), ""]
    if total == 0:
        text_lines.append("All clear — nothing pending this week. (heartbeat: job ran OK)")
    else:
        text_lines.append(f"{total} item(s) awaiting attention.")
    text_lines.append("")

    pr_rows = []
    for p in sorted(prs, key=lambda x: x.get("age_days", 0), reverse=True):
        rec = rec_by["prs"].get((p.get("repo"), p.get("number")), {})
        draft = " [draft]" if p.get("draft") else ""
        pr_rows.append(
            f"- **{p.get('repo')} #{p.get('number')}**{draft} {p.get('title', '')} "
            f"— {p.get('author', '?')}, {p.get('age_days', '?')}d old "
            f"→ **{rec.get('recommendation', '?')}**: {rec.get('reason', '')}"
        )
    text_lines += _section("Pull Requests (priority)", pr_rows)

    trace_rows = []
    for t in sorted(pending, key=lambda x: x.get("age_days", 0), reverse=True):
        rec = rec_by["traces"].get(t.get("id"), {})
        trace_rows.append(
            f"- **{t.get('title', t.get('id'))}** — {t.get('contributor', '?')}, "
            f"{t.get('age_days', '?')}d → **{rec.get('recommendation', '?')}**: "
            f"{rec.get('reason', '')}"
        )
    text_lines += _section("Pending Traces", trace_rows)

    flagged_rows = [
        f"- **{f.get('title', f.get('id'))}** — flagged {f.get('flagged_at', '?')}"
        for f in flagged
    ]
    text_lines += _section("Flagged Traces", flagged_rows)

    amend_rows = []
    for a in amendments:
        rec = rec_by["amendments"].get(a.get("id"), {})
        amend_rows.append(
            f"- amendment on trace {a.get('original_trace_id', '?')} "
            f"by {a.get('submitter', '?')} → **{rec.get('recommendation', '?')}**: "
            f"{rec.get('reason', '')}"
        )
    text_lines += _section("Amendments", amend_rows)

    text = "\n".join(text_lines)
    html = "<html><body><pre>" + _escape(text) + "</pre></body></html>"
    return text, html


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/render.py ops/tests/test_render.py
git commit -m "feat(ops): markdown/HTML rendering for audit issue + review digest"
```

---

## Task 7: `github.py` — GitHub REST client with bounded retry

**Files:**
- Create: `ops/src/commontrace_ops/common/github.py`
- Test: `ops/tests/test_github.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_github.py`:

```python
import pytest

from commontrace_ops.common.github import GitHub
from tests.conftest import FakeResponse


class RoutedClient:
    """httpx-like client that maps (method, url-suffix) -> queued FakeResponse(s).

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
    gh._sleep = lambda s: None  # no real backoff in tests
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_github.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.github'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/github.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_github.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/github.py ops/tests/test_github.py
git commit -m "feat(ops): GitHub REST client with bounded retry"
```

---

## Task 8: `db.py` — read-only contribution queries

**Files:**
- Create: `ops/src/commontrace_ops/common/db.py`
- Test: `ops/tests/test_db.py`

Columns confirmed from `api/app/models/`: `traces(id, title, context_text, solution_text, status, confirmation_count, contributor_id, is_flagged, flagged_at, created_at, metadata_json)`; `amendments(id, original_trace_id, submitter_id, improved_solution, explanation, created_at)`; `users(id, email, display_name)`.

- [ ] **Step 1: Write the failing test**

`ops/tests/test_db.py`:

```python
import pytest

from commontrace_ops.common.db import query_review_data


class FakeConn:
    """Returns queued rows per fetch() call, in order. Rows are dicts (asyncpg
    Records behave like mappings)."""

    def __init__(self, batches):
        self._batches = list(batches)
        self.queries = []

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        return self._batches.pop(0)


async def test_query_review_data_returns_three_buckets():
    pending = [{"id": "t1", "title": "Redis", "context_text": "c",
                "solution_text": "s", "confirmation_count": 0,
                "created_at": "2026-06-01T00:00:00Z", "contributor": "bob"}]
    flagged = [{"id": "t2", "title": "Bad", "flagged_at": "2026-06-05T00:00:00Z",
                "metadata_json": {"flags": ["spam"]}}]
    amendments = [{"id": "a1", "original_trace_id": "t9", "improved_solution": "x",
                   "explanation": "y", "created_at": "2026-06-02T00:00:00Z",
                   "submitter": "carol"}]
    conn = FakeConn([pending, flagged, amendments])

    data = await query_review_data(conn)

    assert len(conn.queries) == 3
    assert data["pending_traces"][0]["id"] == "t1"
    assert data["flagged_traces"][0]["id"] == "t2"
    assert data["amendments"][0]["id"] == "a1"
    # Queries select the documented status / flag predicates.
    assert "status" in conn.queries[0].lower()
    assert "is_flagged" in conn.queries[1].lower()
    assert "amendments" in conn.queries[2].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.common.db'`

- [ ] **Step 3: Write minimal implementation**

`ops/src/commontrace_ops/common/db.py`:

```python
"""Read-only access to the CommonTrace Postgres for the contribution digest.

Only stable columns are selected. All SQL is isolated here so schema coupling
has one place to change (see design 'Known tradeoff')."""
from __future__ import annotations

PENDING_SQL = """
    SELECT t.id, t.title, t.context_text, t.solution_text,
           t.confirmation_count, t.created_at,
           COALESCE(u.display_name, u.email, 'unknown') AS contributor
    FROM traces t
    LEFT JOIN users u ON u.id = t.contributor_id
    WHERE t.status = 'pending'
    ORDER BY t.created_at ASC
    LIMIT 200
"""

FLAGGED_SQL = """
    SELECT t.id, t.title, t.flagged_at, t.metadata_json
    FROM traces t
    WHERE t.is_flagged = true
    ORDER BY t.flagged_at ASC
    LIMIT 200
"""

AMENDMENTS_SQL = """
    SELECT a.id, a.original_trace_id, a.improved_solution, a.explanation,
           a.created_at,
           COALESCE(u.display_name, u.email, 'unknown') AS submitter
    FROM amendments a
    LEFT JOIN users u ON u.id = a.submitter_id
    ORDER BY a.created_at ASC
    LIMIT 200
"""


async def query_review_data(conn) -> dict:
    """Run the three read-only queries against an open connection (injectable)."""
    pending = await conn.fetch(PENDING_SQL)
    flagged = await conn.fetch(FLAGGED_SQL)
    amendments = await conn.fetch(AMENDMENTS_SQL)
    return {
        "pending_traces": [dict(r) for r in pending],
        "flagged_traces": [dict(r) for r in flagged],
        "amendments": [dict(r) for r in amendments],
    }


async def fetch_review_data(database_url: str) -> dict:
    """Connect (read-only intent), query, close. Thin asyncpg shell around
    query_review_data so the query logic stays unit-testable without a DB."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        return await query_review_data(conn)
    finally:
        await conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ops && pytest tests/test_db.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/common/db.py ops/tests/test_db.py
git commit -m "feat(ops): read-only contribution queries (pending/flagged/amendments)"
```

---

## Task 9: `oss_audit` — gather, judge, entrypoint

**Files:**
- Create: `ops/src/commontrace_ops/oss_audit/gather.py`
- Create: `ops/src/commontrace_ops/oss_audit/judge.py`
- Create: `ops/src/commontrace_ops/oss_audit/__main__.py`
- Test: `ops/tests/test_oss_audit.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_oss_audit.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_oss_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.oss_audit.gather'`

- [ ] **Step 3a: Write `gather.py`**

`ops/src/commontrace_ops/oss_audit/gather.py`:

```python
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
```

- [ ] **Step 3b: Write `judge.py`**

`ops/src/commontrace_ops/oss_audit/judge.py`:

```python
"""OSS-health rubric prompt + judge call."""
from __future__ import annotations

from ..common.llm import judge_json

AUDIT_SYSTEM_PROMPT = """\
You are an open-source health auditor. You receive JSON facts gathered from
GitHub for several repositories of one project (CommonTrace).

Score each repo 0-5 on these dimensions: documentation, licensing & legal,
contribution on-ramp, security policy & disclosure, CI & tests, release hygiene,
issue/PR responsiveness, dependency freshness, project activity.

Then judge the project as a whole and derive a prioritized list of improvement
suggestions, most-impactful first, drawn from the lowest-scoring dimensions.

Respond ONLY with a JSON object of this exact shape:
{
  "overall_grade": "A|B|C|D|F",
  "summary": "2-4 sentence verdict",
  "repos": [
    {"repo": "owner/name", "assessment": "...",
     "scores": {"documentation": 0-5, "licensing_legal": 0-5,
                "contribution_onramp": 0-5, "security_policy": 0-5,
                "ci_tests": 0-5, "release_hygiene": 0-5,
                "issue_pr_responsiveness": 0-5, "dependency_freshness": 0-5,
                "project_activity": 0-5}}
  ],
  "suggestions": [
    {"priority": 1, "title": "short title", "detail": "what + why + where"}
  ]
}
"""


def judge_audit(cfg, facts: dict, *, client=None) -> dict:
    return judge_json(cfg, AUDIT_SYSTEM_PROMPT, {"repos": facts}, client=client)
```

- [ ] **Step 3c: Write `__main__.py`**

`ops/src/commontrace_ops/oss_audit/__main__.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ops && pytest tests/test_oss_audit.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ops/src/commontrace_ops/oss_audit/ ops/tests/test_oss_audit.py
git commit -m "feat(ops): oss_audit job — gather, judge, file/update issue"
```

---

## Task 10: `contrib_review` — gather, triage, entrypoint

**Files:**
- Create: `ops/src/commontrace_ops/contrib_review/gather.py`
- Create: `ops/src/commontrace_ops/contrib_review/triage.py`
- Create: `ops/src/commontrace_ops/contrib_review/__main__.py`
- Test: `ops/tests/test_contrib_review.py`

- [ ] **Step 1: Write the failing test**

`ops/tests/test_contrib_review.py`:

```python
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
    assert sent[0]["html"]  # HTML body present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ops && pytest tests/test_contrib_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commontrace_ops.contrib_review.gather'`

- [ ] **Step 3a: Write `gather.py`**

`ops/src/commontrace_ops/contrib_review/gather.py`:

```python
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
```

- [ ] **Step 3b: Write `triage.py`**

`ops/src/commontrace_ops/contrib_review/triage.py`:

```python
"""Triage prompt + judge call for the contribution review digest."""
from __future__ import annotations

from ..common.llm import judge_json

TRIAGE_SYSTEM_PROMPT = """\
You triage the open contribution queue for CommonTrace. You receive JSON with:
open pull requests (the PRIORITY — they block release), pending traces, flagged
traces, and amendments.

For each PULL REQUEST recommend one of: merge | review-needed | close, with a
one-line reason. Treat PRs as the highest priority and surface the oldest first.
For each TRACE and AMENDMENT recommend one of: keep | reject | needs-work, with a
one-line reason.

Respond ONLY with a JSON object of this exact shape:
{
  "prs": [{"repo": "owner/name", "number": 0,
           "recommendation": "merge|review-needed|close", "reason": "..."}],
  "traces": [{"id": "...", "recommendation": "keep|reject|needs-work", "reason": "..."}],
  "amendments": [{"id": "...", "recommendation": "keep|reject|needs-work", "reason": "..."}]
}
"""


def triage(cfg, data: dict, *, client=None) -> dict:
    return judge_json(cfg, TRIAGE_SYSTEM_PROMPT, data, client=client)
```

- [ ] **Step 3c: Write `__main__.py`**

`ops/src/commontrace_ops/contrib_review/__main__.py`:

```python
"""Entrypoint: gather PRs+DB -> triage -> email digest (always, heartbeat)."""
from __future__ import annotations

import datetime as _dt

from ..common.alerting import run_with_alerting
from ..common.config import load_config
from ..common.emailer import send_email
from ..common.github import GitHub
from ..common.render import render_review_digest
from .gather import gather_all
from .triage import triage as triage_fn


def _iso_week(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run(cfg, *, dry_run=False, gather=None, triage=None, emailer=None, week=None):
    gather = gather or (lambda c: gather_all(GitHub(c.github_token), c))
    triage = triage or triage_fn
    emailer = emailer or send_email
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


def main():
    import sys

    dry = "--dry-run" in sys.argv
    cfg = load_config(require_db=True)
    run_with_alerting(lambda: run(cfg, dry_run=dry), "contrib-review", cfg)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ops && pytest tests/test_contrib_review.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite**

Run: `cd ops && pytest -q`
Expected: all tests pass (config, emailer, alerting, llm, render, github, db, oss_audit, contrib_review).

- [ ] **Step 6: Commit**

```bash
git add ops/src/commontrace_ops/contrib_review/ ops/tests/test_contrib_review.py
git commit -m "feat(ops): contrib_review job — gather PRs+DB, triage, email digest"
```

---

## Task 11: CI — add `test-ops` job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the ops test job**

Append a second job to `.github/workflows/ci.yml` (keep the existing `test (api)` job unchanged):

```yaml
  test-ops:
    name: test (ops)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ops
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run tests
        run: pytest -q
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no output (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run ops/ tests in CI"
```

---

## Task 12: Railway wiring + smoke test (manual ops)

This task is operational, not code. Services already created; the 3 secrets
(`OPENAI_API_KEY`, `RESEND_API_KEY`, `GITHUB_TOKEN`) already wired as Railway
Shared Variables. **Prerequisite reminder:** both chat-exposed keys are burned —
rotate them before the first real run.

- [ ] **Step 1: Push the branch and open a PR**

```bash
git push -u origin HEAD
gh pr create --fill
```
Wait for CI (`test (api)` + `test (ops)`) green, then merge to `main`.

- [ ] **Step 2: Attach source to each Railway service**

For BOTH `oss-audit` and `contrib-review`:
- Settings → Source: repo `commontrace/server`, branch `main`, **Root Directory `ops`**.
- Settings → Config-as-code path: `railway.audit.toml` (oss-audit) / `railway.review.toml` (contrib-review).

- [ ] **Step 3: Set per-service non-secret env vars**

Shared across both (Shared Variables already cover the 3 secrets; add these as plain vars or shared):
```
ALERT_EMAIL_FROM=alerts@denemlabs.com
ALERT_EMAIL_TO=tools@denemlabs.com
CT_MODEL=gpt-5.5
REPOS=commontrace/server,commontrace/mcp,commontrace/frontend,commontrace/skill
```
`oss-audit` only: `AUDIT_ISSUE_REPO=commontrace/server`
`contrib-review` only: `DATABASE_URL=${{pgvector.DATABASE_URL}}` (reference var; plain `postgresql://` — config.py strips any `+asyncpg`).

- [ ] **Step 4: Enable native cron-failure notification**

Railway dashboard → each service → Settings → Notifications: enable deploy/cron failure email. This is the backstop behind `run_with_alerting`.

- [ ] **Step 5: Smoke test both jobs manually**

Trigger a one-off run of each service (Railway dashboard → Deploy / Run now), or temporarily set the start command to append `--dry-run` to confirm gather + render without filing/emailing. Confirm:
- `oss-audit --dry-run` prints a rendered issue body, no GitHub write.
- `contrib-review --dry-run` prints a rendered digest, no email.

Then run for real once: confirm the GitHub issue appears in `commontrace/server` and the digest email arrives at `tools@denemlabs.com`.

- [ ] **Step 6: Verify failure alerting**

Temporarily break a secret (e.g. set `OPENAI_API_KEY=bad` on oss-audit), run once, confirm a failure email arrives AND the Railway native cron-failure notification fires. Restore the real secret afterward.

---

## Self-Review Notes

**Spec coverage:** Job A (gather all 4 repos → rubric judge → GitHub issue dedup by title, Task 9). Job B (PRs priority + pending/flagged/amendments → triage digest, always-send heartbeat, Task 10). OpenAI gpt-5.5 via `CT_MODEL` (Task 5, config Task 2). Resend email (Task 3). Failure alerting that never masks the original error (Task 4). Read-only DB with isolated stable-column SQL (Task 8). GitHub bounded retry on 5xx/rate-limit (Task 7). `--dry-run` on both entrypoints (Tasks 9–10). CI runs ops tests (Task 11). Railway two-service cron wiring + native failure backstop (Tasks 1, 12).

**Type consistency:** `Config` fields identical across all test fixtures and `load_config`. Audit result shape (`overall_grade/summary/repos/suggestions`) consistent between `judge.py` prompt, `render_audit_issue`, and `test_oss_audit`. Review result shape (`prs/traces/amendments`) consistent between `triage.py` prompt, `render_review_digest`, and `test_contrib_review`. `_age_days` signature (`ts, *, now=None`) consistent across gather + tests. `GitHub` method names (`repo/community_profile/latest_run/open_pulls/pull_detail/pull_files/latest_release/find_issue/create_issue/update_issue`) used identically in gather + entrypoints + tests.

**No placeholders:** every code step contains complete, runnable code; every run step has an exact command and expected result.
