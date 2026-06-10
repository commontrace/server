# Error-Time Injection Hardening + Death-Spiral Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an agent hits an error it has hit before in this project, inject the known fix at the moment of failure — and prove it worked via assisted-resolution telemetry. Plus: make trigger suppression non-permanent (epsilon-greedy exploration floor).

**Architecture:** All changes live in the skill repo (`/tmp/ct-skill`, pushes to `commontrace/skill`). The local SQLite store (`~/.commontrace/local.db`) gets a v3 migration that turns `error_signatures` from an append-only log into a deduplicated table with a resolution payload (fix command, fix files, trace ID). The PostToolUse hook then closes the loop: error → look up known fix → inject via `additionalContext`; success → pair the fix back to the signature. Assisted resolutions flow through the existing `trigger_feedback` table and the existing telemetry endpoint — **zero server changes**.

**Tech Stack:** Python 3 stdlib only (the skill has no dependencies — keep it that way). Tests use stdlib `unittest` (pytest is NOT installed on this machine: no pip, externally-managed Python 3.12). SQLite via `sqlite3`.

---

## Context for the implementer (read this first)

**Spec:** `/home/denem/commontrace/docs/superpowers/specs/2026-06-10-commontrace-vision-strategy-design.md` §10 Phase 1: "Error-time injection path hardened first — error_signature recurrence → relevant trace injected at the moment of failure, proven by assisted-resolution telemetry (§4.3)". §4.1: "search rate must never decay to zero on a thin corpus, or the skill teaches itself to stop searching."

**Working directory for ALL implementation tasks: `/tmp/ct-skill`** (a clone of https://github.com/commontrace/skill.git, branch `main`). Commit there. The plan document itself lives in the main repo; don't touch the main repo during execution.

**How the hooks work:** Claude Code invokes `hooks/post_tool_use.py` after every Bash/Write/Edit tool call, passing JSON on stdin (`tool_name`, `tool_input`, `tool_response`, `session_id`). If the hook prints `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}`, that text is injected into the agent's context. Session state lives in `~/.commontrace/sessions/{session_id}/` as JSONL files. Cross-session state lives in SQLite at `~/.commontrace/local.db` (module `hooks/local_store.py`). A bridge file `{state_dir}/project_id` (written by `session_start.py`) carries the project's DB id to the per-tool hooks.

**The two bugs being fixed:**

1. `_check_error_recurrence()` (`hooks/post_tool_use.py:388-407`) only *records* error signatures — it never looks up past fixes and always returns `None`. The injection path is scaffolding with no payload. Additionally, the `error_signatures` table (v2 schema) has no columns to store a fix even if we wanted to: just `(id, project_id, signature, created_at)`, one duplicate row per occurrence.
2. `_get_adaptive_cooldown()` (`hooks/post_tool_use.py:124-148`) has two defects: (a) it reads `trigger_data.get("total")` but the stats writer `get_trigger_effectiveness()` emits the key `"fired"` — so the suppression arm (`total >= 20 and rate < 0.05 → 3x cooldown`) is dead code today; (b) once the key is fixed, suppression would be *permanent* — there is no recovery path. The spec mandates an epsilon-greedy exploration floor. **Both must land in the same commit**: fixing the key without the floor activates the death spiral.

**Security invariants to preserve (markers appear in code comments):**
- M19/M20: redact secrets (`redact.py: redact_text / redact_command`) before anything is stored in SQLite or sent over the network. New rule introduced by this plan: error signatures are computed from *redacted* text (the current code computes them from raw text — fix that in passing).
- M22: telemetry consent — `stop.py:_report_trigger_stats` only sends if `config.telemetry == true`. We change nothing there; new trigger stats ride the existing pipe.
- Never auto-execute trace content: injected text is informational ("it was fixed and verified with: `cmd`"), never an instruction to run something.
- Provenance always-on: every injection names its source ("this project's local CommonTrace history").
- Privacy: store fix file *basenames* only (full paths can contain usernames). Nothing new leaves the machine — signatures and fix payloads stay in local.db; only trigger names/rates go to telemetry (M22-gated, unchanged).

**Verified facts** (don't re-derive): the server endpoint `POST /api/v1/telemetry/triggers` (`api/app/routers/telemetry.py:29-52` in the main repo) accepts `trigger_stats` as an arbitrary dict → new trigger names need no server change. `stop.py` reads JSONL events with `.get()` → adding a `"sig"` key to `errors.jsonl` entries is additive-safe. `post_tool_failure.py` writes `errors.jsonl` entries with `source: "tool_failure"` and no `sig`/`command` — pairing logic must skip those.

## File map

| File | Action | Responsibility |
|---|---|---|
| `tests/__init__.py` | Create | empty — makes `tests` a package for unittest discovery |
| `tests/base.py` | Create | `HookTestCase`: temp-dir isolation for DB/cooldowns/config, offline guarantee |
| `tests/test_local_store_v3.py` | Create | v3 migration, signature upsert, resolution storage, pruning |
| `tests/test_error_recurrence.py` | Create | injection decision logic in `_check_error_recurrence` |
| `tests/test_resolution_pairing.py` | Create | `_command_head`, `_pair_resolution`, assisted-resolution marking |
| `tests/test_adaptive_cooldown.py` | Create | fired-key fix + epsilon-greedy floor |
| `tests/test_integration_loop.py` | Create | full two-session loop through `handle_bash` |
| `hooks/local_store.py` | Modify | v3 schema + migration; `record_error_signature` upsert returning recurrence info; new `record_resolution`; prune update |
| `hooks/post_tool_use.py` | Modify | signature in `errors.jsonl`; `_check_error_recurrence` rewrite (inject known fix); `_command_head` + `_pair_resolution` on success path; `_get_adaptive_cooldown` epsilon floor |
| `hooks/session_start.py` | Modify | `SKILL_VERSION` bump only |
| `.claude-plugin/plugin.json` | Modify | version bump only |

Data flow after this plan:

```
error (session 1) ──> sig stored in errors.jsonl + upserted in error_signatures
fix + same command succeeds ──> _pair_resolution: fix_command/fix_files/trace_id
                                 written onto the signature row
error recurs (session 2) ──> _check_error_recurrence: row is resolved ──>
  additionalContext injection ("seen N times, fixed with `cmd`...") +
  trigger_feedback row (error_recurrence) + recurrence_injected.jsonl
fix lands again (session 2) ──> _pair_resolution sees sig in
  recurrence_injected.jsonl ──> record_trace_consumed("local:<hash>") ──>
  error_recurrence consumed/fired rate == assisted-resolution rate ──>
  reported by existing stop.py telemetry (M22-gated), zero server changes
```

---

### Task 1: Test scaffold

**Files:**
- Create: `/tmp/ct-skill/tests/__init__.py`
- Create: `/tmp/ct-skill/tests/base.py`

- [ ] **Step 1: Create the package marker**

Write `/tmp/ct-skill/tests/__init__.py` with exactly this content (a single comment line, no code):

```python
# CommonTrace skill test suite — stdlib unittest only (no pip on target machines).
```

- [ ] **Step 2: Write the shared test base**

Write `/tmp/ct-skill/tests/base.py`:

```python
"""Shared test base: isolates every test from the real ~/.commontrace.

Patches the module-level path constants in local_store and post_tool_use
so tests never touch the developer's real local.db, cooldowns, or config,
and never make network calls (no API key resolvable).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import local_store  # noqa: E402
import post_tool_use  # noqa: E402
from session_state import append_event, read_events  # noqa: E402,F401


class HookTestCase(unittest.TestCase):
    """Temp-dir isolation + offline guarantee for hook tests."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

        for target, attr, value in [
            (local_store, "DB_PATH", self.tmp_path / "local.db"),
            (post_tool_use, "COOLDOWN_DIR", self.tmp_path / "cooldowns"),
            (post_tool_use, "CONFIG_FILE", self.tmp_path / "no-config.json"),
        ]:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # Offline guarantee: no API key from the environment either
        env_patcher = mock.patch.dict(os.environ)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        os.environ.pop("COMMONTRACE_API_KEY", None)

        self.state_dir = self.tmp_path / "session-test"
        self.state_dir.mkdir()

    def get_conn(self):
        conn = local_store._get_conn()
        self.addCleanup(conn.close)
        return conn

    def write_project_bridge(self, conn, state_dir=None):
        """Register a project and write the project_id bridge file."""
        pid = local_store.ensure_project(conn, "/test-project")
        ((state_dir or self.state_dir) / "project_id").write_text(
            str(pid), encoding="utf-8")
        return pid
```

- [ ] **Step 3: Verify the scaffold imports and discovery runs**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -v 2>&1 | tail -3`
Expected: `Ran 0 tests` ... `OK` (or "NO TESTS RAN" — either is fine; what matters is no ImportError).

- [ ] **Step 4: Commit**

```bash
cd /tmp/ct-skill && git add tests/__init__.py tests/base.py && git commit -m "test: add stdlib unittest scaffold with temp-dir isolation"
```

---

### Task 2: local_store v3 migration — error_signatures gains a resolution payload

**Files:**
- Modify: `/tmp/ct-skill/hooks/local_store.py` (lines 23, 73-80, 83-91, new `_migrate_to_v3` after `_migrate_to_v2`)
- Test: `/tmp/ct-skill/tests/test_local_store_v3.py`

- [ ] **Step 1: Write the failing migration tests**

Write `/tmp/ct-skill/tests/test_local_store_v3.py`:

```python
"""v3 schema: deduplicated error_signatures with resolution payload."""

import json
import sqlite3
import time
import unittest

from tests.base import HookTestCase, local_store


def _make_v2_db(path):
    """Build a real v2 database file with duplicate signature rows."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            language TEXT, framework TEXT,
            first_seen_at REAL NOT NULL, last_seen_at REAL NOT NULL,
            session_count INTEGER DEFAULT 1
        );
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            started_at REAL NOT NULL, ended_at REAL,
            error_count INTEGER DEFAULT 0, resolution_count INTEGER DEFAULT 0,
            contribution_count INTEGER DEFAULT 0,
            top_pattern TEXT, importance_score REAL DEFAULT 0.0
        );
        CREATE TABLE trace_cache (
            trace_id TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'search',
            first_seen_at REAL NOT NULL, last_seen_at REAL NOT NULL,
            use_count INTEGER DEFAULT 0, vote TEXT,
            PRIMARY KEY (trace_id, project_id)
        );
        CREATE TABLE trigger_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, trigger_name TEXT NOT NULL,
            triggered_at REAL NOT NULL,
            trace_consumed_id TEXT, consumed_at REAL
        );
        CREATE TABLE error_signatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            signature TEXT NOT NULL,
            created_at REAL NOT NULL
        );
    """)
    now = time.time()
    conn.execute(
        "INSERT INTO projects (path, first_seen_at, last_seen_at) "
        "VALUES ('/p', ?, ?)", (now, now))
    for i in range(3):
        conn.execute(
            "INSERT INTO error_signatures (project_id, signature, created_at) "
            "VALUES (1, 'sig-a', ?)", (now + i,))
    conn.execute(
        "INSERT INTO error_signatures (project_id, signature, created_at) "
        "VALUES (1, 'sig-b', ?)", (now,))
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


class TestV3Migration(HookTestCase):
    def test_v2_db_dedupes_into_seen_counts(self):
        _make_v2_db(local_store.DB_PATH)
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT signature, seen_count FROM error_signatures "
            "ORDER BY signature").fetchall()
        self.assertEqual(
            [(r["signature"], r["seen_count"]) for r in rows],
            [("sig-a", 3), ("sig-b", 1)])
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_fresh_db_has_v3_columns(self):
        conn = self.get_conn()
        cols = {row[1] for row in
                conn.execute("PRAGMA table_info(error_signatures)")}
        self.assertLessEqual(
            {"seen_count", "last_seen_at", "resolved_at",
             "fix_command", "fix_files", "trace_id"}, cols)

    def test_migration_is_idempotent(self):
        _make_v2_db(local_store.DB_PATH)
        self.get_conn().close()
        conn = self.get_conn()  # second open must not break or re-migrate
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM error_signatures").fetchone()
        self.assertEqual(rows["n"], 2)


if __name__ == "__main__":
    unittest.main()
```

Note: `self.get_conn().close()` in the idempotency test closes immediately *and* registers a second close via addCleanup — double-close of a sqlite3 connection is a no-op, safe.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_local_store_v3 -v`
Expected: FAIL — `test_fresh_db_has_v3_columns` fails the set-inclusion assert (no `seen_count` column); the v2 tests fail with `no such column: seen_count`.

- [ ] **Step 3: Implement the v3 schema and migration**

In `/tmp/ct-skill/hooks/local_store.py`, make three edits.

Edit 1 — bump the version constant (line 23):

```python
CURRENT_SCHEMA_VERSION = 3
```

Edit 2 — replace the `error_signatures` block inside `_SCHEMA` (currently lines 73-79):

```python
CREATE TABLE IF NOT EXISTS error_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    signature TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    seen_count INTEGER DEFAULT 1,
    resolved_at REAL,
    fix_command TEXT,
    fix_files TEXT,
    trace_id TEXT,
    UNIQUE(project_id, signature)
);
```

(Keep the `CREATE INDEX IF NOT EXISTS idx_error_sig_project ...` line that follows it.)

Edit 3 — update `_apply_migrations` and add `_migrate_to_v3` directly after `_migrate_to_v2`:

```python
def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply schema migrations based on PRAGMA user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= CURRENT_SCHEMA_VERSION:
        return
    if version < 2:
        _migrate_to_v2(conn)
    if version < 3:
        _migrate_to_v3(conn)
    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    conn.commit()
```

```python
def _migrate_to_v3(conn: sqlite3.Connection) -> None:
    """Migrate error_signatures from an append-only occurrence log to a
    deduplicated table with a resolution payload.

    v2 wrote one row per occurrence with no fix information. v3 keeps one
    row per (project_id, signature) carrying seen_count plus the fix that
    resolved it (fix_command, fix_files, trace_id) — the payload that
    error-time injection replays when the same error recurs.
    """
    sig_cols = {row[1] for row in
                conn.execute("PRAGMA table_info(error_signatures)")}
    if not sig_cols or "seen_count" in sig_cols:
        return  # Fresh DB (table created by _SCHEMA) or already migrated
    conn.executescript("""
        BEGIN EXCLUSIVE;
        CREATE TABLE error_signatures_v3 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            signature TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            seen_count INTEGER DEFAULT 1,
            resolved_at REAL,
            fix_command TEXT,
            fix_files TEXT,
            trace_id TEXT,
            UNIQUE(project_id, signature)
        );
        INSERT INTO error_signatures_v3
            (project_id, signature, created_at, last_seen_at, seen_count)
            SELECT project_id, signature, MIN(created_at), MAX(created_at),
                   COUNT(*)
            FROM error_signatures
            GROUP BY project_id, signature;
        DROP TABLE error_signatures;
        ALTER TABLE error_signatures_v3 RENAME TO error_signatures;
        COMMIT;
    """)
```

Also update the module docstring's table list (line 9): change `- error_signatures: error fingerprints for recurrence detection` to `- error_signatures: error fingerprints + the fix that resolved them (recurrence detection and error-time injection)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_local_store_v3 -v`
Expected: PASS (3 tests). Then syntax-check: `python3 -c "import py_compile; py_compile.compile('/tmp/ct-skill/hooks/local_store.py', doraise=True)"`

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill && git add hooks/local_store.py tests/test_local_store_v3.py && git commit -m "feat(store): v3 schema — dedupe error_signatures, add resolution payload columns"
```

---

### Task 3: Signature upsert + resolution recording in local_store

**Files:**
- Modify: `/tmp/ct-skill/hooks/local_store.py` (replace `record_error_signature` at lines 276-283; add `record_resolution` after it; update `prune_stale_cache` error_signatures clause at lines 429-432)
- Test: `/tmp/ct-skill/tests/test_local_store_v3.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_local_store_v3.py` (before the `if __name__ == "__main__":` block):

```python
class TestSignatureUpsert(HookTestCase):
    def test_first_occurrence_not_recurrence(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        info = local_store.record_error_signature(conn, pid, "sig-x")
        self.assertEqual(info["recurrence"], False)
        self.assertEqual(info["seen_count"], 1)
        self.assertEqual(info["resolved"], False)

    def test_second_occurrence_is_recurrence(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        local_store.record_error_signature(conn, pid, "sig-x")
        info = local_store.record_error_signature(conn, pid, "sig-x")
        self.assertEqual(info["recurrence"], True)
        self.assertEqual(info["seen_count"], 2)

    def test_same_signature_different_project_is_independent(self):
        conn = self.get_conn()
        pid_a = local_store.ensure_project(conn, "/p-a")
        pid_b = local_store.ensure_project(conn, "/p-b")
        local_store.record_error_signature(conn, pid_a, "sig-x")
        info = local_store.record_error_signature(conn, pid_b, "sig-x")
        self.assertEqual(info["recurrence"], False)

    def test_resolution_roundtrip(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        local_store.record_error_signature(conn, pid, "sig-x")
        updated = local_store.record_resolution(
            conn, pid, "sig-x", fix_command="pytest -x",
            fix_files=["a.py", "b.py"], trace_id="t-123")
        self.assertTrue(updated)
        info = local_store.record_error_signature(conn, pid, "sig-x")
        self.assertEqual(info["resolved"], True)
        self.assertEqual(info["fix_command"], "pytest -x")
        self.assertEqual(info["fix_files"], ["a.py", "b.py"])
        self.assertEqual(info["trace_id"], "t-123")

    def test_resolution_for_unknown_signature_is_noop(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        self.assertFalse(local_store.record_resolution(conn, pid, "nope"))


class TestPruning(HookTestCase):
    def test_prune_keeps_resolved_signatures_longer(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        now = time.time()
        rows = [
            ("old-unresolved", now - 100 * 86400, None),
            ("old-resolved", now - 100 * 86400, now - 100 * 86400),
            ("ancient-resolved", now - 200 * 86400, now - 200 * 86400),
        ]
        for sig, seen, resolved in rows:
            conn.execute(
                "INSERT INTO error_signatures (project_id, signature, "
                "created_at, last_seen_at, seen_count, resolved_at) "
                "VALUES (?, ?, ?, ?, 1, ?)", (pid, sig, seen, seen, resolved))
        conn.commit()
        local_store.prune_stale_cache(conn)
        kept = {r["signature"] for r in conn.execute(
            "SELECT signature FROM error_signatures")}
        self.assertEqual(kept, {"old-resolved"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_local_store_v3 -v`
Expected: FAIL — `record_error_signature` currently returns `None` (`TypeError: 'NoneType' object is not subscriptable`), `record_resolution` doesn't exist (`AttributeError`), pruning test fails (`kept` contains `old-resolved` AND `old-unresolved` is gone but `ancient-resolved` survives — actually with the current 90-day blanket rule all three are deleted, so `kept == set()`).

- [ ] **Step 3: Implement**

In `/tmp/ct-skill/hooks/local_store.py`, replace the whole `record_error_signature` function (lines 276-283) with:

```python
def record_error_signature(conn: sqlite3.Connection, project_id: int,
                           signature: str) -> dict:
    """Upsert an error-signature occurrence and return recurrence info.

    Returns: {recurrence, seen_count, resolved, fix_command, fix_files,
    trace_id, last_seen_at}. The fix payload fields stay None/[] until
    record_resolution() pairs a verified fix to this signature; once set,
    they are what error-time injection replays on recurrence.
    last_seen_at is the PREVIOUS sighting (display: "last hit on <date>").
    """
    now = time.time()
    row = conn.execute(
        "SELECT seen_count, last_seen_at, resolved_at, fix_command, "
        "fix_files, trace_id FROM error_signatures "
        "WHERE project_id = ? AND signature = ?",
        (project_id, signature),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO error_signatures "
            "(project_id, signature, created_at, last_seen_at, seen_count) "
            "VALUES (?, ?, ?, ?, 1)",
            (project_id, signature, now, now),
        )
        conn.commit()
        return {"recurrence": False, "seen_count": 1, "resolved": False,
                "fix_command": None, "fix_files": [], "trace_id": None,
                "last_seen_at": now}
    conn.execute(
        "UPDATE error_signatures SET seen_count = seen_count + 1, "
        "last_seen_at = ? WHERE project_id = ? AND signature = ?",
        (now, project_id, signature),
    )
    conn.commit()
    fix_files = []
    if row["fix_files"]:
        try:
            fix_files = json.loads(row["fix_files"])
        except (json.JSONDecodeError, TypeError):
            fix_files = []
    return {
        "recurrence": True,
        "seen_count": row["seen_count"] + 1,
        "resolved": row["resolved_at"] is not None,
        "fix_command": row["fix_command"],
        "fix_files": fix_files,
        "trace_id": row["trace_id"],
        "last_seen_at": row["last_seen_at"],
    }


def record_resolution(conn: sqlite3.Connection, project_id: int,
                      signature: str, fix_command: str = None,
                      fix_files: list = None, trace_id: str = None) -> bool:
    """Attach a verified fix to an error signature.

    Called when a previously-failing command succeeds. COALESCE keeps an
    earlier non-null payload when a later resolution passes None.
    Returns True if a signature row was updated.
    """
    cur = conn.execute(
        "UPDATE error_signatures SET resolved_at = ?, "
        "fix_command = COALESCE(?, fix_command), "
        "fix_files = COALESCE(?, fix_files), "
        "trace_id = COALESCE(?, trace_id) "
        "WHERE project_id = ? AND signature = ?",
        (time.time(), fix_command,
         json.dumps(fix_files) if fix_files else None,
         trace_id, project_id, signature),
    )
    conn.commit()
    return cur.rowcount > 0
```

Then in `prune_stale_cache`, replace the error_signatures DELETE (currently `DELETE FROM error_signatures WHERE created_at < ?` with `now - 90 * 86400`) with:

```python
    conn.execute(
        "DELETE FROM error_signatures "
        "WHERE resolved_at IS NULL AND last_seen_at < ?",
        (now - 90 * 86400,),
    )
    conn.execute(
        "DELETE FROM error_signatures "
        "WHERE resolved_at IS NOT NULL AND last_seen_at < ?",
        (now - 180 * 86400,),
    )
```

And update the retention-policy docstring line in `prune_stale_cache` from `- error_signatures: 90 days` to `- error_signatures: 90 days unresolved, 180 days resolved (a stored fix is the product — keep it longer)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_local_store_v3 -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill && git add hooks/local_store.py tests/test_local_store_v3.py && git commit -m "feat(store): signature upsert with recurrence info + record_resolution"
```

---

### Task 4: Error-time injection in `_check_error_recurrence`

**Files:**
- Modify: `/tmp/ct-skill/hooks/post_tool_use.py` (imports at line 30-33; `handle_bash` error branch at lines 253-268; replace `_check_error_recurrence` at lines 388-407)
- Test: `/tmp/ct-skill/tests/test_error_recurrence.py`

- [ ] **Step 1: Write the failing tests**

Write `/tmp/ct-skill/tests/test_error_recurrence.py`:

```python
"""Error-time injection: recurrence of a resolved signature injects the fix."""

import unittest

from tests.base import HookTestCase, local_store, post_tool_use


class TestErrorRecurrence(HookTestCase):
    def test_first_error_injects_nothing(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        out = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNone(out)

    def test_unresolved_recurrence_injects_nothing(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        local_store.record_error_signature(conn, pid, "sig-x")
        out = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNone(out)

    def test_resolved_recurrence_injects_fix(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        local_store.record_error_signature(conn, pid, "sig-x")
        local_store.record_resolution(
            conn, pid, "sig-x", fix_command="npm test",
            fix_files=["api.ts"], trace_id="t-9")
        out = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNotNone(out)
        self.assertEqual(
            out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("npm test", ctx)
        self.assertIn("api.ts", ctx)
        self.assertIn("t-9", ctx)
        self.assertIn("local CommonTrace history", ctx)  # provenance always-on

    def test_injection_records_trigger_and_injection_marker(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        local_store.record_error_signature(conn, pid, "sig-x")
        local_store.record_resolution(conn, pid, "sig-x", fix_command="make")
        post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        row = conn.execute(
            "SELECT trigger_name FROM trigger_feedback WHERE session_id = ?",
            (self.state_dir.name,)).fetchone()
        self.assertEqual(row["trigger_name"], "error_recurrence")
        from tests.base import read_events
        injected = read_events(self.state_dir, "recurrence_injected.jsonl")
        self.assertEqual(injected[0]["sig"], "sig-x")

    def test_cooldown_blocks_injection_but_still_records_occurrence(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        local_store.record_error_signature(conn, pid, "sig-x")
        local_store.record_resolution(conn, pid, "sig-x", fix_command="make")
        first = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNotNone(first)
        second = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNone(second)  # 60s cooldown active
        row = conn.execute(
            "SELECT seen_count FROM error_signatures WHERE signature = ?",
            ("sig-x",)).fetchone()
        self.assertEqual(row["seen_count"], 3)  # 1 manual + 2 checks

    def test_no_project_bridge_is_silent(self):
        out = post_tool_use._check_error_recurrence("sig-x", self.state_dir)
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_error_recurrence -v`
Expected: FAIL — `test_resolved_recurrence_injects_fix`, `test_injection_records_trigger_and_injection_marker`, and `test_cooldown_blocks_injection_but_still_records_occurrence` fail (current function always returns `None` and records nothing when on cooldown).

- [ ] **Step 3: Implement**

In `/tmp/ct-skill/hooks/post_tool_use.py`, make three edits.

Edit 1 — extend the session_state import (lines 30-32):

```python
from session_state import (
    get_state_dir, append_event, read_events, is_config_file,
    error_signature, error_hash,
)
```

Edit 2 — in `handle_bash`, replace the error branch's opening (current lines 253-268, from `if is_error:` through `if recurrence_output: return recurrence_output`) with:

```python
    if is_error:
        # M19/M20: Redact secrets before storing or sending
        safe_command = redact_command(command[:200])
        safe_error = redact_text(error_text[:500])
        # M19: signature computed from REDACTED text — it is stored in local.db
        sig = error_signature(redact_text(error_text))

        append_event(state_dir, "errors.jsonl", {
            "source": "bash",
            "command": safe_command,
            "output_tail": safe_error,
            "sig": sig,
        })

        # Error recurrence: record this occurrence and, if this project has
        # already resolved the same signature, inject the known fix now.
        recurrence_output = _check_error_recurrence(sig, state_dir)
        if recurrence_output:
            return recurrence_output
```

(The rest of the error branch — the `bash_error` cooldown/search block — is unchanged.)

Edit 3 — replace the whole `_check_error_recurrence` function (lines 388-407) with:

```python
def _check_error_recurrence(sig: str, state_dir: Path) -> dict | None:
    """Record this error occurrence; on resolved recurrence, inject the fix.

    Recording is exempt from the cooldown so seen_count stays accurate —
    the cooldown gates only the injection. Injection fires when this
    project has already resolved the same signature: the moment a past
    lesson pays off. The injection is informational (never an instruction
    to execute), names its provenance, and is remembered in
    recurrence_injected.jsonl so a subsequent fix counts as an assisted
    resolution (closes the trigger_feedback loop).
    """
    project_id = _read_project_id(state_dir)
    if project_id is None:
        return None

    info = None
    try:
        from local_store import _get_conn, record_error_signature
        conn = _get_conn()
        info = record_error_signature(conn, project_id, sig)
        conn.close()
    except Exception:
        return None

    if not info or not info.get("recurrence") or not info.get("resolved"):
        return None

    if is_on_cooldown("error_recurrence",
                      _get_adaptive_cooldown("error_recurrence", 60, state_dir)):
        return None
    set_cooldown("error_recurrence")
    _record_trigger_safe(state_dir, "error_recurrence")
    append_event(state_dir, "recurrence_injected.jsonl", {"sig": sig})

    when = time.strftime("%Y-%m-%d",
                         time.localtime(info.get("last_seen_at", 0)))
    parts = [
        f"CommonTrace: this error has hit this project before "
        f"(seen {info['seen_count']} times, last {when}) and was solved."
    ]
    if info.get("fix_command"):
        parts.append(f"The fix was verified with: `{info['fix_command']}`.")
    files = info.get("fix_files") or []
    if files:
        parts.append("Files changed for the fix: "
                     + ", ".join(files[:5]) + ".")
    if info.get("trace_id"):
        parts.append(f"Full solution: use get_trace with ID "
                     f"{info['trace_id']}.")
    parts.append("(Source: this project's local CommonTrace history.)")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": " ".join(parts),
        }
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_error_recurrence tests.test_local_store_v3 -v`
Expected: PASS (15 tests). Syntax-check: `python3 -c "import py_compile; py_compile.compile('/tmp/ct-skill/hooks/post_tool_use.py', doraise=True)"`

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill && git add hooks/post_tool_use.py tests/test_error_recurrence.py && git commit -m "feat(hooks): inject known fix at error time on resolved signature recurrence"
```

---

### Task 5: Resolution pairing — success writes the fix onto the signature

**Files:**
- Modify: `/tmp/ct-skill/hooks/post_tool_use.py` (`handle_bash` success branch at lines 295-304; new `_command_head` + `_pair_resolution` after `_read_context_fingerprint`)
- Test: `/tmp/ct-skill/tests/test_resolution_pairing.py`

- [ ] **Step 1: Write the failing tests**

Write `/tmp/ct-skill/tests/test_resolution_pairing.py`:

```python
"""Pairing a succeeding command back to the failed signature it resolves."""

import json
import unittest

from tests.base import (
    HookTestCase, append_event, local_store, post_tool_use, read_events,
)


class TestCommandHead(HookTestCase):
    def test_plain_command(self):
        self.assertEqual(post_tool_use._command_head("pytest tests/ -v"),
                         "pytest")

    def test_skips_env_assignment_prefix(self):
        self.assertEqual(post_tool_use._command_head("FOO=1 BAR=2 pytest -x"),
                         "pytest")

    def test_empty_command(self):
        self.assertEqual(post_tool_use._command_head(""), "")


class TestPairResolution(HookTestCase):
    def _seed_error(self, conn, sig="sig-x", command="pytest tests/"):
        pid = self.write_project_bridge(conn)
        local_store.record_error_signature(conn, pid, sig)
        append_event(self.state_dir, "errors.jsonl", {
            "source": "bash", "command": command, "sig": sig, "t": 100.0})
        return pid

    def test_pairing_stores_fix(self):
        conn = self.get_conn()
        self._seed_error(conn)
        append_event(self.state_dir, "changes.jsonl", {
            "tool": "Edit", "file": "/repo/src/api.py", "t": 150.0})
        post_tool_use._pair_resolution(
            self.state_dir, "pytest tests/ -v",
            read_events(self.state_dir, "errors.jsonl"))
        row = conn.execute(
            "SELECT fix_command, fix_files, resolved_at "
            "FROM error_signatures WHERE signature = 'sig-x'").fetchone()
        self.assertIsNotNone(row["resolved_at"])
        self.assertEqual(row["fix_command"], "pytest tests/ -v")
        self.assertEqual(json.loads(row["fix_files"]), ["api.py"])  # basename only

    def test_pairing_requires_same_command_head(self):
        conn = self.get_conn()
        self._seed_error(conn)
        post_tool_use._pair_resolution(
            self.state_dir, "ls -la",
            read_events(self.state_dir, "errors.jsonl"))
        row = conn.execute(
            "SELECT resolved_at FROM error_signatures "
            "WHERE signature = 'sig-x'").fetchone()
        self.assertIsNone(row["resolved_at"])

    def test_pairing_skips_tool_failure_entries(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        append_event(self.state_dir, "errors.jsonl", {
            "source": "tool_failure", "tool": "Edit", "error": "x", "t": 90.0})
        # Must not raise and must not write anything
        post_tool_use._pair_resolution(
            self.state_dir, "pytest",
            read_events(self.state_dir, "errors.jsonl"))
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM error_signatures "
            "WHERE resolved_at IS NOT NULL").fetchone()["n"]
        self.assertEqual(n, 0)

    def test_consumed_trace_is_attributed_to_fix(self):
        conn = self.get_conn()
        self._seed_error(conn)
        sid = self.state_dir.name
        local_store.record_trigger(conn, sid, "bash_error")
        local_store.record_trace_consumed(conn, sid, "trace-42")
        post_tool_use._pair_resolution(
            self.state_dir, "pytest tests/",
            read_events(self.state_dir, "errors.jsonl"))
        row = conn.execute(
            "SELECT trace_id FROM error_signatures "
            "WHERE signature = 'sig-x'").fetchone()
        self.assertEqual(row["trace_id"], "trace-42")

    def test_assisted_resolution_marks_trigger_consumed(self):
        conn = self.get_conn()
        self._seed_error(conn)
        sid = self.state_dir.name
        local_store.record_trigger(conn, sid, "error_recurrence")
        append_event(self.state_dir, "recurrence_injected.jsonl",
                     {"sig": "sig-x", "t": 101.0})
        post_tool_use._pair_resolution(
            self.state_dir, "pytest tests/",
            read_events(self.state_dir, "errors.jsonl"))
        row = conn.execute(
            "SELECT trace_consumed_id FROM trigger_feedback "
            "WHERE session_id = ?", (sid,)).fetchone()
        self.assertTrue(row["trace_consumed_id"].startswith("local:"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_resolution_pairing -v`
Expected: FAIL — `AttributeError: module 'post_tool_use' has no attribute '_command_head'` (and `_pair_resolution`).

- [ ] **Step 3: Implement**

In `/tmp/ct-skill/hooks/post_tool_use.py`, make two edits.

Edit 1 — in `handle_bash`, the success branch (currently lines 295-304) becomes:

```python
    else:
        # ── Success: check if this resolves a previous error ──
        previous_errors = read_events(state_dir, "errors.jsonl")
        if previous_errors:
            append_event(state_dir, "resolutions.jsonl", {
                "source": "bash",
                "command": redact_command(command[:200]),
                "output_preview": redact_text(output[:200]) if output else "",
                "errors_before": len(previous_errors),
            })
            _pair_resolution(state_dir, command, previous_errors)
```

Edit 2 — add these two functions after `_read_context_fingerprint` (line 386) and before `_check_error_recurrence`:

```python
def _command_head(command: str) -> str:
    """First meaningful token of a shell command, skipping VAR=val prefixes.

    Known limitation (accepted): compound commands ("cd x && pytest") yield
    the first command's head. Pairing is a heuristic, not a proof.
    """
    for tok in command.split():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            continue
        return tok
    return ""


def _pair_resolution(state_dir: Path, command: str,
                     previous_errors: list[dict]) -> None:
    """Pair a succeeding command with a prior error of the same command head.

    Structural signal: the command that failed now succeeds. Stores the fix
    (verification command + basenames of files changed since the error +
    any commons trace consumed since the error) on the signature row —
    the payload _check_error_recurrence injects when the signature recurs.
    If this signature's fix was injected earlier this session, the
    resolution is recorded as a consumed trigger (assisted resolution),
    which feeds the error_recurrence rate in the existing M22-gated
    telemetry. Never raises.
    """
    try:
        head = _command_head(command)
        if not head:
            return
        match = None
        for entry in reversed(previous_errors):
            if entry.get("source") != "bash" or not entry.get("sig"):
                continue
            if _command_head(entry.get("command", "")) == head:
                match = entry
                break
        if match is None:
            return
        project_id = _read_project_id(state_dir)
        if project_id is None:
            return
        err_t = match.get("t", 0)

        # Files changed between the error and this success = the fix.
        # Basenames only — full paths can contain usernames.
        fix_files = []
        for ch in read_events(state_dir, "changes.jsonl"):
            if ch.get("t", 0) >= err_t and ch.get("file"):
                name = Path(ch["file"]).name
                if name not in fix_files:
                    fix_files.append(name)

        from local_store import (
            _get_conn, record_resolution, record_trace_consumed,
        )
        conn = _get_conn()
        # Commons trace consumed since the error → attribute it to the fix
        trace_id = None
        try:
            row = conn.execute(
                "SELECT trace_consumed_id FROM trigger_feedback "
                "WHERE session_id = ? AND trace_consumed_id IS NOT NULL "
                "AND consumed_at >= ? ORDER BY consumed_at DESC LIMIT 1",
                (state_dir.name, err_t),
            ).fetchone()
            if row:
                trace_id = row["trace_consumed_id"]
        except Exception:
            trace_id = None

        record_resolution(conn, project_id, match["sig"],
                          fix_command=redact_command(command[:200]),
                          fix_files=fix_files[:10],
                          trace_id=trace_id)

        # Assisted resolution: fix injected earlier this session → it landed
        injected = {e.get("sig") for e in
                    read_events(state_dir, "recurrence_injected.jsonl")}
        if match["sig"] in injected:
            record_trace_consumed(conn, state_dir.name,
                                  "local:" + error_hash(match["sig"]))
        conn.close()
    except Exception:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_resolution_pairing -v`
Expected: PASS (8 tests: 3 in TestCommandHead + 5 in TestPairResolution).

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill && git add hooks/post_tool_use.py tests/test_resolution_pairing.py && git commit -m "feat(hooks): pair succeeding commands to failed signatures; mark assisted resolutions"
```

---

### Task 6: Death-spiral fix — fired-key bug + epsilon-greedy exploration floor

**Files:**
- Modify: `/tmp/ct-skill/hooks/post_tool_use.py` (replace `_get_adaptive_cooldown` at lines 124-148; add `EXPLORATION_EVERY` constant + `_exploration_due` before it)
- Test: `/tmp/ct-skill/tests/test_adaptive_cooldown.py`

Both fixes MUST land in this single commit: fixing the `"total"`→`"fired"` key without the floor would activate permanent suppression (the death spiral the spec forbids).

- [ ] **Step 1: Write the failing tests**

Write `/tmp/ct-skill/tests/test_adaptive_cooldown.py`:

```python
"""Adaptive cooldown: suppression must read real stats and never be permanent."""

import json
import unittest

from tests.base import HookTestCase, post_tool_use


class TestAdaptiveCooldown(HookTestCase):
    def _write_stats(self, name, fired, rate, key="fired"):
        (self.state_dir / "trigger_stats.json").write_text(json.dumps({
            name: {key: fired, "consumed": int(fired * rate), "rate": rate},
        }), encoding="utf-8")

    def test_ineffective_trigger_is_suppressed(self):
        self._write_stats("bash_error", fired=25, rate=0.0)
        self.assertEqual(
            post_tool_use._get_adaptive_cooldown(
                "bash_error", 30, self.state_dir), 90)

    def test_epsilon_floor_every_tenth_check_explores(self):
        self._write_stats("bash_error", fired=25, rate=0.0)
        values = [post_tool_use._get_adaptive_cooldown(
            "bash_error", 30, self.state_dir) for _ in range(10)]
        self.assertEqual(values[:9], [90] * 9)
        self.assertEqual(values[9], 30)  # exploration fires on the 10th

    def test_effective_trigger_halves_cooldown(self):
        self._write_stats("bash_error", fired=10, rate=0.5)
        self.assertEqual(
            post_tool_use._get_adaptive_cooldown(
                "bash_error", 30, self.state_dir), 15)

    def test_few_firings_no_suppression(self):
        self._write_stats("bash_error", fired=10, rate=0.0)
        self.assertEqual(
            post_tool_use._get_adaptive_cooldown(
                "bash_error", 30, self.state_dir), 30)

    def test_legacy_total_key_still_suppresses(self):
        self._write_stats("bash_error", fired=25, rate=0.0, key="total")
        self.assertEqual(
            post_tool_use._get_adaptive_cooldown(
                "bash_error", 30, self.state_dir), 90)

    def test_no_stats_file_returns_base(self):
        self.assertEqual(
            post_tool_use._get_adaptive_cooldown(
                "bash_error", 30, self.state_dir), 30)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_adaptive_cooldown -v`
Expected: FAIL — `test_ineffective_trigger_is_suppressed` and `test_epsilon_floor_every_tenth_check_explores` get 30 instead of 90 (the `"total"` key bug means suppression never engages on `"fired"` stats).

- [ ] **Step 3: Implement**

In `/tmp/ct-skill/hooks/post_tool_use.py`, replace `_get_adaptive_cooldown` (lines 124-148) with the following (the constant and helper go immediately above it):

```python
EXPLORATION_EVERY = 10  # every Nth suppressed check fires anyway (epsilon floor)


def _exploration_due(trigger_name: str) -> bool:
    """Deterministic epsilon-greedy floor for suppressed triggers.

    Counts suppressed-eligible checks per trigger; every
    EXPLORATION_EVERY-th check is allowed through at the base cooldown.
    Guarantees a suppressed trigger keeps sampling reality and can earn
    its way back when the corpus or the project changes — the search
    rate never decays to zero (spec §4.1).
    """
    COOLDOWN_DIR.mkdir(parents=True, exist_ok=True)
    path = COOLDOWN_DIR / f"{trigger_name}.suppressed"
    try:
        count = int(path.read_text(encoding="utf-8")) if path.exists() else 0
    except (ValueError, OSError):
        count = 0
    count += 1
    try:
        path.write_text(str(count), encoding="utf-8")
    except OSError:
        return False
    return count % EXPLORATION_EVERY == 0


def _get_adaptive_cooldown(trigger_name: str, base_seconds: int,
                           state_dir: Path) -> int:
    """Scale cooldown by trigger conversion rate from trigger_feedback.

    >= 40% rate → 0.5x cooldown (more aggressive — trigger is effective)
    < 5% after 20+ firings → 3x cooldown, with an epsilon-greedy floor:
        every EXPLORATION_EVERY-th suppressed check goes through at the
        base cooldown, so suppression is never permanent.
    Default: no change

    Stats come from trigger_stats.json (written by session_start from
    get_trigger_effectiveness, key "fired"; "total" kept as a legacy
    fallback for old bridge files).
    """
    try:
        stats_path = state_dir / "trigger_stats.json"
        if not stats_path.exists():
            return base_seconds
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        trigger_data = stats.get(trigger_name)
        if not trigger_data:
            return base_seconds
        fired = trigger_data.get("fired", trigger_data.get("total", 0))
        rate = trigger_data.get("rate", 0)
        if fired >= 20 and rate < 0.05:
            if _exploration_due(trigger_name):
                return base_seconds
            return base_seconds * 3
        if rate >= 0.4:
            return max(base_seconds // 2, 5)
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return base_seconds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_adaptive_cooldown -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill && git add hooks/post_tool_use.py tests/test_adaptive_cooldown.py && git commit -m "fix(hooks): adaptive cooldown reads fired key; add epsilon-greedy exploration floor"
```

---

### Task 7: Integration proof, version bump, full suite, push

**Files:**
- Test: `/tmp/ct-skill/tests/test_integration_loop.py`
- Modify: `/tmp/ct-skill/hooks/session_start.py:26`
- Modify: `/tmp/ct-skill/.claude-plugin/plugin.json:3`

- [ ] **Step 1: Write the integration test (the full loop, offline, through `handle_bash`)**

Write `/tmp/ct-skill/tests/test_integration_loop.py`:

```python
"""End-to-end: error → fix → recurrence in a new session → injection →
assisted resolution recorded. Entirely offline (no API key resolvable)."""

import unittest

from tests.base import HookTestCase, append_event, post_tool_use


def _bash_event(command, exit_code, stdout="", stderr=""):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {
            "output": stdout, "stderr": stderr, "exitCode": exit_code,
        },
    }


class TestErrorFixRecurrenceLoop(HookTestCase):
    def test_full_loop(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)

        # ── Session 1: error → edit → same command succeeds ──
        out = post_tool_use.handle_bash(
            _bash_event("pytest tests/", 1,
                        stderr="ImportError: No module named foo"),
            self.state_dir)
        self.assertIsNone(out)  # first encounter: nothing known yet
        append_event(self.state_dir, "changes.jsonl",
                     {"tool": "Edit", "file": "/repo/foo.py"})
        out = post_tool_use.handle_bash(
            _bash_event("pytest tests/", 0, stdout="3 passed"),
            self.state_dir)
        self.assertIsNone(out)
        row = conn.execute(
            "SELECT resolved_at FROM error_signatures").fetchone()
        self.assertIsNotNone(row["resolved_at"])  # fix stored

        # ── Session 2 (fresh state dir, same project): error recurs ──
        s2 = self.tmp_path / "session-2"
        s2.mkdir()
        (s2 / "project_id").write_text(str(pid), encoding="utf-8")
        out = post_tool_use.handle_bash(
            _bash_event("pytest tests/", 1,
                        stderr="ImportError: No module named foo"),
            s2)
        self.assertIsNotNone(out)  # THE injection — the product moment
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("pytest tests/", ctx)
        self.assertIn("foo.py", ctx)
        self.assertIn("local CommonTrace history", ctx)

        # ── Agent applies the known fix; verification passes ──
        append_event(s2, "changes.jsonl",
                     {"tool": "Edit", "file": "/repo/foo.py"})
        post_tool_use.handle_bash(
            _bash_event("pytest tests/", 0, stdout="3 passed"), s2)
        row = conn.execute(
            "SELECT trace_consumed_id FROM trigger_feedback "
            "WHERE session_id = ?", (s2.name,)).fetchone()
        # Assisted resolution recorded — this is the north-star telemetry
        self.assertTrue(row["trace_consumed_id"].startswith("local:"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the integration test**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_integration_loop -v`
Expected: PASS (it composes Tasks 2-6; if it fails, a seam between tasks is broken — fix before proceeding).

- [ ] **Step 3: Bump versions**

In `/tmp/ct-skill/hooks/session_start.py` line 26, change:

```python
SKILL_VERSION = "0.3.0"
```

In `/tmp/ct-skill/.claude-plugin/plugin.json` line 3, change:

```json
  "version": "0.3.0",
```

- [ ] **Step 4: Run the full suite + syntax checks**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -v 2>&1 | tail -5`
Expected: `Ran 30 tests` ... `OK` (9 store + 6 recurrence + 8 pairing + 6 cooldown + 1 integration).

Run: `for f in hooks/local_store.py hooks/post_tool_use.py hooks/session_start.py; do python3 -c "import py_compile; py_compile.compile('/tmp/ct-skill/$f', doraise=True)" && echo "$f OK"; done`
Expected: three `OK` lines.

- [ ] **Step 5: Commit and push**

```bash
cd /tmp/ct-skill && git add tests/test_integration_loop.py hooks/session_start.py .claude-plugin/plugin.json && git commit -m "feat: error-time injection loop proven end-to-end; bump to 0.3.0"
git push origin main
```

(Push only after the full suite is green. Users receive the update on next plugin pull; local.db migrates to v3 automatically and backs itself up to `local.db.bak` first — existing `_get_conn` behavior.)

---

## What this plan deliberately does NOT do (YAGNI)

- No remote search fallback inside `_check_error_recurrence` when a signature recurs unresolved — the existing `bash_error` search trigger already covers that path.
- No fuzzy/partial signature matching (Levenshtein etc.) — `error_signature()` normalization is the fuzziness; exact match on normalized text.
- No new telemetry endpoint or payload — assisted-resolution rate is the `error_recurrence` row in the existing `trigger_stats` dict.
- No changes to `stop.py`, `session_start.py` logic (version string only), `user_prompt.py`, MCP, frontend, or server.

## Verification against the spec (§10 Phase 1, first row + §4.1)

- "error_signature recurrence → relevant trace injected at the moment of failure" → Tasks 2-4.
- "proven by assisted-resolution telemetry (§4.3)" → Task 5 (`local:` consumption marking) + existing M22-gated `stop.py` reporting; Task 7 integration test asserts the telemetry row.
- "All local-first at N=1" → entire loop works offline with zero commons traces (integration test runs with no API key).
