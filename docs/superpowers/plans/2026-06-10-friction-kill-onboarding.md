# Friction-Kill Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CommonTrace onboarding zero-decision — `claude plugin add` is the only step; the first session auto-provisions an anonymous account, wires MCP correctly, delivers first search value, and discloses everything it did in one notice.

**Architecture:** All changes land in the existing first-run path of `hooks/session_start.py` — no new modules. `ensure_setup()` loses the dead `consent_given` gate (M21 flipped per approved spec §10 Phase 1) and queues a persistent one-time disclosure flag; `configure_mcp()` embeds the raw key so MCP actually authenticates for auto-provisioned users; `main()` stops exiting silently when provisioning fails and delivers the disclosure notice in the first context-emitting session. README install collapses from four manual steps to one command.

**Tech Stack:** Python 3 stdlib only (no new dependencies), `unittest` + `unittest.mock`, Claude Code hook protocol (`hookSpecificOutput`/`additionalContext` JSON on stdout).

**Repo:** `/tmp/ct-skill` (GitHub `commontrace/skill`), branch `main`. Test command: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`. Syntax check before every commit: `python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"`.

**Execution-order assumption:** This plan is written to execute AFTER Plan B (`docs/superpowers/plans/2026-06-10-viral-artifacts.md`), i.e. on skill v0.4.0 where the full suite is 71 tests and `tests/base.py` already isolates `artifacts.ARTIFACTS_DIR` into the test temp dir. Every `session_start.py` anchor below was chosen from regions Plan B does not touch, so the same `old_string` text matches either way. If executing standalone on v0.3.0 instead: the `SKILL_VERSION` anchor in Task 3 and the version strings in Task 6 read `0.3.0` rather than `0.4.0` (use the line as found, same replacement), and expected full-suite totals are 30 + 9 = 39 instead of 71 + 9 = 80.

**Hard constraints (founder, non-negotiable):**

1. No LLM API calls — structural logic only.
2. Hooks must never block or break session start — every new path degrades to a short notice or silence.
3. H7/H9 file permissions stay: `~/.commontrace` 0700, `config.json` 0600.
4. The M21 flip is deliberate and founder-approved (spec `docs/superpowers/specs/2026-06-10-commontrace-vision-strategy-design.md` §10 Phase 1: "Friction-kill onboarding (plugin install → auto-keygen → first value same session)"). Transparency replaces consent-gating: a one-time disclosure notice tells the user exactly what was provisioned and how to undo it.
5. Anonymous accounts carry no PII: synthetic email `agent-<8 hex chars>@commontrace.auto`, display name "Claude Code Agent". Verified against the API: `require_email` (`api/app/dependencies.py:70` in the monorepo) only rejects `email is None`, and Pydantic `EmailStr` accepts the `.auto` TLD (not on the special-use rejection list) — so auto-provisioned keys can both search and contribute traces.

---

## Current state (why each task exists)

Four defects make the documented 4-step manual install the only working path today:

1. **Dead-code auto-keygen.** `ensure_setup()` returns `None` unless `config.get("consent_given")` is truthy — but nothing in the repo, the README, or any command ever sets `consent_given`. Auto-provisioning is unreachable code. → Task 2
2. **Silent first run.** When `ensure_setup()` returns `None`, `main()` bare-returns. A fresh install produces zero output — the user never learns the skill exists, failed, or needs anything. → Task 3
3. **MCP broken by construction for auto-provisioned keys.** `configure_mcp()` stores the literal header `x-api-key: ${COMMONTRACE_API_KEY}` in the user-scope MCP config. That literal only expands if the user exports the env var before launching Claude Code — but `configure_mcp()` is only ever reached on the provisioning path, where the env var is by definition absent (the env-var branch of `ensure_setup()` returns early before it). Every MCP call from an auto-provisioned install would send the unexpanded literal and 401. The `env["COMMONTRACE_API_KEY"] = api_key` line in the current code only affects the short-lived `claude mcp add` subprocess, not the future MCP connections that need the value. → Task 1
4. **README demands 4 manual steps**, including pasting a raw key into a CLI argument, and its manual-clone alternative copies `skill/.mcp.json` — a file that does not exist in the repo. → Task 5

**"First value same session" needs no new code beyond these fixes:** `main()` already proceeds from `ensure_setup()` straight into context detection and `search_commontrace()` in the same invocation — once provisioning actually runs, search results inject in session 1. (MCP tools register via `claude mcp add -s user` and load on the NEXT session start; the disclosure notice says so explicitly.)

**Key-read fallback is already consistent** — `stop.py:98`, `stop.py:815-823`, and `post_tool_use.py:92-99` all fall back between config.json and the env var. No unification work needed; auto-provisioned keys reach every hook.

## File map

| File | Change |
|---|---|
| `/tmp/ct-skill/hooks/session_start.py` | module docstring; 2 notice constants; `configure_mcp` raw-key fix; `ensure_setup` M21 flip + notice flag; new `_emit_setup_notice`; 2 small `main()` edits; SKILL_VERSION bump |
| `/tmp/ct-skill/tests/test_onboarding.py` | NEW — 9 tests across 4 classes, one shared base class |
| `/tmp/ct-skill/README.md` | Install section → one command; new Uninstall section; config table row; drop phantom `.mcp.json` reference; one "What It Does" bullet |
| `/tmp/ct-skill/.claude-plugin/plugin.json` | `version` → `0.5.0` |
| `/tmp/ct-skill/skills/commontrace/SKILL.md` | frontmatter `version` → `0.5.0` (note: Plan B does not bump this file — it still reads `0.3.0` even after Plan B) |

---

### Task 1: configure_mcp — embed the raw key so MCP authenticates

**Files:**
- Create: `/tmp/ct-skill/tests/test_onboarding.py`
- Modify: `/tmp/ct-skill/hooks/session_start.py` (the `configure_mcp` function, currently lines 127–148)

**Security note (record in the code, not just here):** This supersedes H8 for this one call site. H8 ("key via env var, not CLI arg") assumed the env var would exist at MCP-connect time to expand the stored `${COMMONTRACE_API_KEY}` literal. On the only path that reaches `configure_mcp()` — fresh auto-provisioning — it never does, so the H8 pattern here produces a permanently broken MCP config. The accepted tradeoff: the key is an anonymous, low-value credential, and the argv exposure window is the few seconds the `claude mcp add` subprocess runs. Manual installs that export the env var never reach this code path and keep full H8 indirection (README Task 5 documents that pattern).

- [ ] **Step 1: Write the failing tests**

Create `/tmp/ct-skill/tests/test_onboarding.py` with exactly:

```python
"""Zero-decision onboarding: auto-provisioning, MCP wiring, first-run notices."""

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from unittest import mock

from base import HookTestCase

import session_start
import session_state


class OnboardingTestCase(HookTestCase):
    """Adds session_start config isolation on top of HookTestCase."""

    def setUp(self):
        super().setUp()
        for target, attr, value in [
            (session_start, "CONFIG_DIR", self.tmp_path),
            (session_start, "CONFIG_FILE", self.tmp_path / "config.json"),
            (session_start, "PENDING_DIR", self.tmp_path / "pending"),
            (session_start, "PING_MARKER", self.tmp_path / "last_ping_date"),
            (session_state, "STATE_ROOT", self.tmp_path / "state"),
        ]:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class TestConfigureMcp(OnboardingTestCase):
    def test_embeds_raw_key_in_header(self):
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with mock.patch.object(session_start.subprocess, "run", fake_run):
            ok = session_start.configure_mcp("ct_raw_key_123")

        self.assertTrue(ok)
        self.assertIn("x-api-key: ct_raw_key_123", captured["argv"])
        joined = " ".join(captured["argv"])
        self.assertNotIn("${COMMONTRACE_API_KEY}", joined)

    def test_missing_claude_cli_returns_false(self):
        with mock.patch.object(
                session_start.subprocess, "run",
                side_effect=FileNotFoundError("claude not found")):
            self.assertFalse(session_start.configure_mcp("k"))
```

- [ ] **Step 2: Run tests to verify the new behavior fails**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: `test_embeds_raw_key_in_header` FAILS (`AssertionError: 'x-api-key: ct_raw_key_123' not found in [...]` — current code passes the `${COMMONTRACE_API_KEY}` literal). `test_missing_claude_cli_returns_false` PASSES already (regression guard — `FileNotFoundError` is an `OSError` subclass and the current code catches it; keep the test).

- [ ] **Step 3: Replace configure_mcp**

In `/tmp/ct-skill/hooks/session_start.py`, replace the entire `configure_mcp` function:

```python
def configure_mcp(api_key: str) -> bool:
    """Run `claude mcp add` to register the MCP server with the API key.

    H8: API key passed via environment variable, not CLI argument,
    to avoid exposure in process listing (ps aux / /proc/pid/cmdline).
    """
    try:
        env = os.environ.copy()
        env["COMMONTRACE_API_KEY"] = api_key
        result = subprocess.run(
            [
                "claude", "mcp", "add", "commontrace",
                "--transport", "http",
                MCP_URL,
                "-H", "x-api-key: ${COMMONTRACE_API_KEY}",
                "-s", "user",
            ],
            capture_output=True, text=True, timeout=10, env=env,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
```

with:

```python
def configure_mcp(api_key: str) -> bool:
    """Run `claude mcp add` to register the MCP server with the API key.

    The raw key is embedded in the stored MCP config deliberately. This
    function only runs right after auto-provisioning, when no
    COMMONTRACE_API_KEY env var exists for `${...}` expansion at MCP
    connect time — env-var indirection here would 401 on every MCP call.
    Accepted tradeoff (supersedes H8 for this call site): the key is an
    anonymous, low-value credential, and the argv exposure window is the
    few seconds `claude mcp add` runs. Manual installs that export the
    env var never reach this code path.
    """
    try:
        result = subprocess.run(
            [
                "claude", "mcp", "add", "commontrace",
                "--transport", "http",
                MCP_URL,
                "-H", f"x-api-key: {api_key}",
                "-s", "user",
            ],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: 2 tests PASS

- [ ] **Step 5: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 73 tests PASS (71 existing + 2 new; standalone: 32)

- [ ] **Step 6: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add hooks/session_start.py tests/test_onboarding.py
git commit -m "fix(onboarding): embed raw key in MCP config so auto-provisioned installs authenticate"
```

---

### Task 2: ensure_setup — flip M21, queue the disclosure flag

**Files:**
- Modify: `/tmp/ct-skill/hooks/session_start.py` (the `ensure_setup` function, currently lines 151–191)
- Modify: `/tmp/ct-skill/tests/test_onboarding.py` (append one helper + one class)

- [ ] **Step 1: Write the failing tests**

Append to the end of `/tmp/ct-skill/tests/test_onboarding.py`:

```python
def _provision_forbidden():
    raise AssertionError("provision_api_key must not be called")


class TestEnsureSetup(OnboardingTestCase):
    def test_first_run_auto_provisions_anonymous_key(self):
        mcp_calls = []
        with mock.patch.object(session_start, "provision_api_key",
                               return_value="ct_live_abc"), \
             mock.patch.object(session_start, "configure_mcp",
                               side_effect=lambda k: mcp_calls.append(k) or True), \
             mock.patch.object(session_start, "report_install"):
            key = session_start.ensure_setup()

        self.assertEqual(key, "ct_live_abc")
        self.assertEqual(mcp_calls, ["ct_live_abc"])
        saved = json.loads(
            session_start.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["api_key"], "ct_live_abc")
        self.assertTrue(saved["pending_first_run_notice"])
        mode = session_start.CONFIG_FILE.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_env_var_short_circuits_provisioning(self):
        os.environ["COMMONTRACE_API_KEY"] = "env_key"
        self.addCleanup(os.environ.pop, "COMMONTRACE_API_KEY", None)
        with mock.patch.object(session_start, "provision_api_key",
                               side_effect=_provision_forbidden):
            key = session_start.ensure_setup()
        self.assertEqual(key, "env_key")
        saved = json.loads(
            session_start.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["api_key"], "env_key")
        self.assertNotIn("pending_first_run_notice", saved)

    def test_stored_key_short_circuits_provisioning(self):
        session_start.save_config({"api_key": "stored_key"})
        with mock.patch.object(session_start, "provision_api_key",
                               side_effect=_provision_forbidden):
            self.assertEqual(session_start.ensure_setup(), "stored_key")

    def test_provision_failure_returns_none_and_leaves_no_key(self):
        with mock.patch.object(session_start, "provision_api_key",
                               return_value=None):
            self.assertIsNone(session_start.ensure_setup())
        if session_start.CONFIG_FILE.exists():
            saved = json.loads(
                session_start.CONFIG_FILE.read_text(encoding="utf-8"))
            self.assertNotIn("api_key", saved)
```

- [ ] **Step 2: Run tests to verify the new behavior fails**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: `test_first_run_auto_provisions_anonymous_key` FAILS (`AssertionError: None != 'ct_live_abc'` — the `consent_given` gate returns `None` before provisioning). The other 3 PASS already (regression guards for the env-var, stored-key, and failure paths; keep them — `test_provision_failure_...` currently passes for the wrong reason and pins the right one after Step 3).

- [ ] **Step 3: Replace ensure_setup**

In `/tmp/ct-skill/hooks/session_start.py`, replace the entire `ensure_setup` function:

```python
def ensure_setup() -> str | None:
    """Ensure API key exists and MCP is configured. Returns api_key or None."""
    config = load_config()

    # Check env var first (user override)
    api_key = os.environ.get("COMMONTRACE_API_KEY", "")
    if api_key:
        if not config.get("api_key"):
            config["api_key"] = api_key
            save_config(config)
        return api_key

    # Check stored config
    api_key = config.get("api_key", "")
    if api_key:
        return api_key

    # M21: Check if user has explicitly opted in before auto-provisioning
    if not config.get("consent_given"):
        # First run — don't auto-provision without consent.
        # User must set COMMONTRACE_API_KEY env var or run setup manually.
        return None

    # Provision with consent
    api_key = provision_api_key()
    if not api_key:
        return None

    config["api_key"] = api_key
    save_config(config)

    # Configure MCP server for future sessions
    configure_mcp(api_key)

    # Fire-and-forget install beacon (silent on failure)
    try:
        report_install(api_key)
    except Exception:
        pass

    return api_key
```

with:

```python
def ensure_setup() -> str | None:
    """Ensure API key exists and MCP is configured. Returns api_key or None.

    Zero-decision onboarding (spec 2026-06-10 §10 Phase 1): installing the
    plugin IS the opt-in, so the first run auto-provisions an anonymous
    account (random ID, no PII) and queues a one-time disclosure notice
    (pending_first_run_notice) that main() delivers and clears. A failed
    provisioning attempt stores nothing, so every later session start
    retries until it succeeds.
    """
    config = load_config()

    # Check env var first (user override)
    api_key = os.environ.get("COMMONTRACE_API_KEY", "")
    if api_key:
        if not config.get("api_key"):
            config["api_key"] = api_key
            save_config(config)
        return api_key

    # Check stored config
    api_key = config.get("api_key", "")
    if api_key:
        return api_key

    # First run: auto-provision an anonymous account.
    api_key = provision_api_key()
    if not api_key:
        return None

    config["api_key"] = api_key
    config["pending_first_run_notice"] = True
    save_config(config)

    # Configure MCP server for future sessions
    configure_mcp(api_key)

    # Fire-and-forget install beacon (silent on failure)
    try:
        report_install(api_key)
    except Exception:
        pass

    return api_key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: 6 tests PASS

- [ ] **Step 5: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 75 tests PASS (standalone: 34)

- [ ] **Step 6: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add hooks/session_start.py tests/test_onboarding.py
git commit -m "feat(onboarding): zero-decision auto-provisioning — plugin install is the opt-in (M21 flip per spec)"
```

---

### Task 3: setup-failure notice — kill the silent first run

**Files:**
- Modify: `/tmp/ct-skill/hooks/session_start.py` (module docstring; new constant after `SKILL_VERSION`; new `_emit_setup_notice` function before `main`; one edit inside `main`)
- Modify: `/tmp/ct-skill/tests/test_onboarding.py` (append one class)

- [ ] **Step 1: Write the failing test**

Append to the end of `/tmp/ct-skill/tests/test_onboarding.py`:

```python
class TestSetupFailedNotice(OnboardingTestCase):
    def _run_main(self):
        out = io.StringIO()
        with mock.patch.object(session_start, "provision_api_key",
                               return_value=None), \
             mock.patch.object(sys, "stdin", io.StringIO("{}")), \
             redirect_stdout(out):
            session_start.main()
        return out.getvalue()

    def test_failure_emits_notice_once_then_silent(self):
        first = self._run_main()
        payload = json.loads(first)
        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("CommonTrace setup could not complete", ctx)

        second = self._run_main()
        self.assertEqual(second, "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding.TestSetupFailedNotice -v`
Expected: ERROR with `json.decoder.JSONDecodeError` (main currently bare-returns on a failed setup, so stdout is empty).

- [ ] **Step 3: Update the module docstring**

In `/tmp/ct-skill/hooks/session_start.py`, replace lines 1–9:

```python
#!/usr/bin/env python3
"""
CommonTrace SessionStart hook.

On first run: auto-generates an API key, stores it, and configures the MCP server.
On every run: detects coding context, queries CommonTrace, injects relevant traces.

Exits 0 silently on any error — never blocks session start.
"""
```

with:

```python
#!/usr/bin/env python3
"""
CommonTrace SessionStart hook.

First run: auto-provisions an anonymous API key (zero-decision onboarding),
stores it in ~/.commontrace/config.json, registers the MCP server, and
queues a one-time disclosure notice. If provisioning fails, a one-time
setup notice is emitted and provisioning retries silently on later sessions.
Every run: detects coding context, queries CommonTrace, injects relevant traces.

Never blocks session start — failures degrade to a short notice or silence.
"""
```

- [ ] **Step 4: Add the notice constant**

In `/tmp/ct-skill/hooks/session_start.py`, replace the line:

```python
SKILL_VERSION = "0.4.0"
```

(standalone execution: the line reads `"0.3.0"` — keep whatever value is present, only append the constant) with:

```python
SKILL_VERSION = "0.4.0"

SETUP_FAILED_NOTICE = (
    "CommonTrace setup could not complete (API unreachable). The skill will "
    "retry automatically next session; local knowledge tracking works in the "
    "meantime. To configure manually, set the COMMONTRACE_API_KEY environment "
    "variable — see https://github.com/commontrace/skill#install. Mention "
    "this to the user only if they ask about CommonTrace."
)
```

- [ ] **Step 5: Add _emit_setup_notice**

In `/tmp/ct-skill/hooks/session_start.py`, the `format_result` function ends and `main` begins:

```python
    if trace_id:
        parts.append(f"(trace ID: {trace_id})")
    return " ".join(parts)


def main() -> None:
```

Insert the new function between them, so the code reads:

```python
    if trace_id:
        parts.append(f"(trace ID: {trace_id})")
    return " ".join(parts)


def _emit_setup_notice() -> None:
    """One-time notice when provisioning failed — replaces the old silent exit.

    Shown once ever (setup_notice_shown flag); provisioning itself still
    retries silently on every later session start.
    """
    config = load_config()
    if config.get("setup_notice_shown"):
        return
    config["setup_notice_shown"] = True
    try:
        save_config(config)
    except OSError:
        pass
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": SETUP_FAILED_NOTICE,
        }
    }))


def main() -> None:
```

- [ ] **Step 6: Call it from main**

In `/tmp/ct-skill/hooks/session_start.py` `main()`, replace:

```python
    # Step 1: Ensure API key + MCP configured (auto-provisions on first run)
    api_key = ensure_setup()
    if not api_key:
        return
```

with:

```python
    # Step 1: Ensure API key + MCP configured (auto-provisions on first run)
    api_key = ensure_setup()
    if not api_key:
        _emit_setup_notice()
        return
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: 7 tests PASS

- [ ] **Step 8: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 76 tests PASS (standalone: 35)

- [ ] **Step 9: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add hooks/session_start.py tests/test_onboarding.py
git commit -m "feat(onboarding): one-time setup notice replaces silent exit when provisioning fails"
```

---

### Task 4: first-run disclosure — deliver and clear the queued notice

**Files:**
- Modify: `/tmp/ct-skill/hooks/session_start.py` (new constant after `SETUP_FAILED_NOTICE`; one edit inside `main`)
- Modify: `/tmp/ct-skill/tests/test_onboarding.py` (append one class)

**Design note:** the flag persists in config.json rather than being passed in-process because `main()` has early returns for non-git / non-source directories that emit nothing. If the provisioning session happens in such a directory, the notice survives and delivers in the first session that actually emits context. Prepending (not appending) keeps the disclosure ahead of search results in the injected context.

- [ ] **Step 1: Write the failing tests**

Append to the end of `/tmp/ct-skill/tests/test_onboarding.py`:

```python
class TestFirstRunNotice(OnboardingTestCase):
    def _project_dir(self):
        proj = self.tmp_path / "proj"
        (proj / ".git").mkdir(parents=True, exist_ok=True)
        (proj / "app.py").write_text("x = 1\n", encoding="utf-8")
        return proj

    def _run_main(self, cwd):
        stdin_data = json.dumps(
            {"cwd": str(cwd), "session_id": "s-onboard"})
        out = io.StringIO()
        with mock.patch.object(session_start, "maybe_ping"), \
             mock.patch.object(session_start, "search_commontrace",
                               return_value=[]), \
             mock.patch.object(sys, "stdin", io.StringIO(stdin_data)), \
             redirect_stdout(out):
            session_start.main()
        return out.getvalue()

    def test_notice_prepended_once_then_cleared(self):
        session_start.save_config(
            {"api_key": "k", "pending_first_run_notice": True})
        output = self._run_main(self._project_dir())
        payload = json.loads(output)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("CommonTrace first-run notice"))
        saved = json.loads(
            session_start.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("pending_first_run_notice", saved)

        # Second session: notice must not repeat
        output2 = self._run_main(self._project_dir())
        ctx2 = json.loads(output2)["hookSpecificOutput"]["additionalContext"]
        self.assertFalse(ctx2.startswith("CommonTrace first-run notice"))

    def test_notice_deferred_until_a_session_emits_context(self):
        session_start.save_config(
            {"api_key": "k", "pending_first_run_notice": True})
        bare = self.tmp_path / "bare"
        bare.mkdir()
        # no .git → main returns before emitting anything
        output = self._run_main(bare)
        self.assertEqual(output, "")
        saved = json.loads(
            session_start.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertTrue(saved["pending_first_run_notice"])
```

- [ ] **Step 2: Run tests to verify the new behavior fails**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding.TestFirstRunNotice -v`
Expected: `test_notice_prepended_once_then_cleared` FAILS (`AssertionError: False is not true` — nothing prepends the notice yet). `test_notice_deferred_until_a_session_emits_context` PASSES already (regression guard pinning the early-return behavior; keep it).

- [ ] **Step 3: Add the notice constant**

In `/tmp/ct-skill/hooks/session_start.py`, replace:

```python
    "this to the user only if they ask about CommonTrace."
)
```

with:

```python
    "this to the user only if they ask about CommonTrace."
)

FIRST_RUN_NOTICE = (
    "CommonTrace first-run notice — relay this to the user in one short "
    "paragraph at the start of your reply: CommonTrace is now connected. An "
    "anonymous account was created automatically (random ID, no personal "
    "data) and the API key is stored at ~/.commontrace/config.json. Sessions "
    "now search a shared knowledge base of coding fixes, and solved problems "
    "are auto-contributed back in anonymized, secret-redacted form (set "
    "auto_contribute to false in ~/.commontrace/config.json to review before "
    "anything is shared). To use a personal account: set the "
    "COMMONTRACE_API_KEY environment variable. To disconnect entirely: "
    "delete ~/.commontrace and run 'claude mcp remove commontrace'. MCP "
    "tools (search_traces, contribute_trace) load from the next session "
    "onward."
)
```

- [ ] **Step 4: Deliver the notice in main**

In `/tmp/ct-skill/hooks/session_start.py` `main()`, replace the pending-hint block:

```python
    # Pending traces hint (manual mode only — auto mode submits live).
    config = load_config()
    if not config.get("auto_contribute", True):
        pending_n = count_pending_traces()
        if pending_n > 0:
            additional_context += (
                f"\n\n{pending_n} pending CommonTrace contribution(s) await user "
                f"review. The user can run /trace contribute when they want to "
                f"review them. Do not proactively prompt — only mention if the "
                f"user asks about CommonTrace."
            )
```

with the same block plus the delivery logic:

```python
    # Pending traces hint (manual mode only — auto mode submits live).
    config = load_config()
    if not config.get("auto_contribute", True):
        pending_n = count_pending_traces()
        if pending_n > 0:
            additional_context += (
                f"\n\n{pending_n} pending CommonTrace contribution(s) await user "
                f"review. The user can run /trace contribute when they want to "
                f"review them. Do not proactively prompt — only mention if the "
                f"user asks about CommonTrace."
            )

    # First-run disclosure (M21 zero-decision transparency) — queued by
    # ensure_setup at provisioning time, delivered once in the first
    # session that actually emits context, then cleared.
    if config.get("pending_first_run_notice"):
        additional_context = f"{FIRST_RUN_NOTICE}\n\n{additional_context}"
        config.pop("pending_first_run_notice", None)
        try:
            save_config(config)
        except OSError:
            pass
```

(After Plan B, this lands between the pending-hint block and Plan B's monthly-Compiled block — the shared `config` dict is later re-saved by `_compiled_drop`, which preserves the pop because both operate on the same dict. Standalone, it lands directly before `output = {`. Both are correct.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_onboarding -v`
Expected: 9 tests PASS

- [ ] **Step 6: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 80 tests PASS (standalone: 39)

- [ ] **Step 7: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add hooks/session_start.py tests/test_onboarding.py
git commit -m "feat(onboarding): one-time first-run disclosure notice, deferred until a context-emitting session"
```

---

### Task 5: README — one-command install, uninstall section, honest config table

**Files:**
- Modify: `/tmp/ct-skill/README.md`

No tests — verify with the grep checks in Step 4.

- [ ] **Step 1: Replace the Install section**

In `/tmp/ct-skill/README.md`, replace the entire Install section (Plan B does not modify it — this text is present verbatim either way):

````markdown
## Install

### 1. Get an API key

```bash
curl -s -X POST https://api.commontrace.org/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "display_name": "Your Name"}' | python3 -m json.tool
```

Save the `api_key` from the response — it cannot be retrieved again.

### 2. Set your API key

```bash
export COMMONTRACE_API_KEY=your-api-key
```

### 3. Add the MCP server to Claude Code

```bash
claude mcp add commontrace --transport http https://mcp.commontrace.org/mcp -H "x-api-key: YOUR_API_KEY"
```

### 4. Install the plugin

```bash
claude plugin add commontrace@commontrace/skill
```

Or manually clone and copy:

```bash
git clone https://github.com/commontrace/skill.git
cp -r skill/.claude-plugin skill/.mcp.json skill/hooks skill/skills /your/project/
```
````

with:

````markdown
## Install

```bash
claude plugin add commontrace@commontrace/skill
```

That's it. Your next Claude Code session sets everything up automatically:

1. Creates an anonymous account (random ID, no personal data) and stores the API key at `~/.commontrace/config.json` (mode 0600)
2. Registers the MCP server (`claude mcp add commontrace`, user scope)
3. Runs the first knowledge-base search for your project
4. Relays a one-time notice describing exactly what was set up and how to undo it

No account, no email, no environment variables, no decisions.

### Use your own account instead (optional)

Anonymous accounts are fully functional — search and contribution included. Register with a real email only if you want a stable identity across machines:

```bash
curl -s -X POST https://api.commontrace.org/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "display_name": "Your Name"}' | python3 -m json.tool
```

Save the `api_key` from the response — it cannot be retrieved again. Export it before launching Claude Code (the environment variable always takes precedence over a stored anonymous key), and register the MCP server with the same indirection so the raw key never lands in the stored config:

```bash
export COMMONTRACE_API_KEY=your-api-key
claude mcp add commontrace --transport http https://mcp.commontrace.org/mcp -H 'x-api-key: ${COMMONTRACE_API_KEY}'
```

## Uninstall

```bash
claude plugin remove commontrace
claude mcp remove commontrace
rm -rf ~/.commontrace
```
````

- [ ] **Step 2: Add the zero-config bullet to "What It Does"**

In `/tmp/ct-skill/README.md`, replace:

```markdown
- **Auto-searches** CommonTrace at session start based on project context
```

with:

```markdown
- **Zero-config onboarding** — install the plugin, start a session; an anonymous account is provisioned automatically
- **Auto-searches** CommonTrace at session start based on project context
```

- [ ] **Step 3: Fix the configuration table row**

In `/tmp/ct-skill/README.md`, replace:

```markdown
| `COMMONTRACE_API_KEY` | (required) | Your API key from step 1 |
```

with:

```markdown
| `COMMONTRACE_API_KEY` | (auto-provisioned) | Optional override — set it to use your own account instead of the auto-provisioned anonymous one |
```

- [ ] **Step 4: Verify**

Run: `grep -n "mcp.json" /tmp/ct-skill/README.md`
Expected: no output (the phantom `.mcp.json` reference is gone)

Run: `grep -n "YOUR_API_KEY" /tmp/ct-skill/README.md`
Expected: no output (no raw-key-in-CLI-arg instruction remains)

Run: `grep -cn "consent" /tmp/ct-skill/hooks/session_start.py`
Expected: `0` (confirms Task 2 removed the M21 gate; no doc references it either)

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
git add README.md
git commit -m "docs: one-command install, uninstall section, drop phantom .mcp.json reference"
```

---

### Task 6: Version 0.5.0 + full suite

**Files:**
- Modify: `/tmp/ct-skill/.claude-plugin/plugin.json`
- Modify: `/tmp/ct-skill/skills/commontrace/SKILL.md`
- Modify: `/tmp/ct-skill/hooks/session_start.py` (SKILL_VERSION)

Standalone execution note: after Plan B these read `0.4.0` / `0.3.0` / `0.4.0` respectively; standalone they read `0.3.0` / `0.3.0` / `0.3.0`. Replace whatever value is present with `0.5.0`.

- [ ] **Step 1: plugin.json**

In `/tmp/ct-skill/.claude-plugin/plugin.json`, change:

```json
  "version": "0.4.0",
```

to:

```json
  "version": "0.5.0",
```

- [ ] **Step 2: SKILL.md frontmatter**

In `/tmp/ct-skill/skills/commontrace/SKILL.md`, change (Plan B does not bump this file — it reads `0.3.0` even after Plan B):

```yaml
version: 0.3.0
```

to:

```yaml
version: 0.5.0
```

- [ ] **Step 3: SKILL_VERSION**

In `/tmp/ct-skill/hooks/session_start.py`, change:

```python
SKILL_VERSION = "0.4.0"
```

to:

```python
SKILL_VERSION = "0.5.0"
```

- [ ] **Step 4: Full suite green + JSON validity**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 80 tests PASS (standalone: 39)

Run: `cd /tmp/ct-skill && python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add .claude-plugin/plugin.json skills/commontrace/SKILL.md hooks/session_start.py
git commit -m "chore: bump to 0.5.0 — zero-decision onboarding"
```

---

## After all tasks

1. Dispatch the final code reviewer over the Plan C diff only: find the Plan B final commit with `cd /tmp/ct-skill && git log --oneline | head -20` (message `docs: /trace brain command, artifacts README; bump to 0.4.0`; standalone baseline is `574dfc4` instead) and review `git diff <that-sha>..HEAD`. Check specifically: the five hard constraints in the header, that the disclosure/setup notices contain no untrue claims (MCP loads next session, retry-on-failure, env-var precedence, uninstall commands), that `configure_mcp`'s docstring documents the H8 supersession rationale, and that all tests pass offline (`COMMONTRACE_API_KEY` unset).
2. Push to `commontrace/skill` `main` **only after** the final review verdict is clean. Railway is not involved (skill repo deploys via user `git pull` / plugin update).
3. Founder follow-ups recorded, not built:
   - No live installs are broken today (auto-provisioning was dead code; env-var users are unaffected), so no migration/repair path is included. If a future change rotates MCP wiring, add a repair step then.
   - `auto_contribute` defaults to `true`, so zero-decision installs publish detected knowledge automatically. The disclosure notice states this and how to switch to review mode; revisit the default if users push back.
   - Frontend "delete my anonymous account" self-serve flow (today: delete local files; the server-side user row persists).
