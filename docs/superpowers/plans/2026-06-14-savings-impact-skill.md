# Savings & Impact (Skill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Give CommonTrace users a quiet, honest, measured sense of what the commons saved *them* — a token-counting instrument, a local `savings_events` ledger, a session-start recap line, and an `artifacts.py` breakdown — all from real measured token counts and one published price constant, never asked of a model.

**Architecture:** A new pure-local `hooks/savings.py` reads the Stop hook's `transcript_path` JSONL and sums `message.usage` (input + output + cache tokens) inside the already-computed first-error→resolved time window — every savings number is therefore a **measured token count** multiplied by a **published `$/Mtok` price constant**, with **no LLM call** anywhere in the path. The Stop hook records `tokens_to_resolution` into the contribution `metadata_json` (so the count rides with the trace) and books a MEASURED INBOUND saving into a new SQLite `savings_events` table (schema v4, additive migration) whenever a previously-resolved, trace-linked error signature recurred this session. `session_start.py` emits one opt-outable recap line from local rollups; `artifacts.py recap` gains a savings line and a `savings` subcommand. Everything is best-effort and wrapped so a failure never crashes a hook.

**Tech Stack:** Python 3 (stdlib only — `sqlite3`, `json`, `datetime`, `time`, `pathlib`); SQLite at `~/.commontrace/local.db` (WAL, `sqlite3.Row` factory, `PRAGMA user_version` migration gate); stdlib `unittest` test runner (no pip on target machines), `tests/base.py::HookTestCase` temp-dir isolation.

**NO-LLM constraint (load-bearing):** Money is always `tokens / 1_000_000 * price_per_mtok`. `tokens` is a real summed `message.usage` count from the transcript (or, only for pre-instrument legacy traces, a conservative `(error_count + iteration_count) * TOKENS_PER_TURN_EST` floor). `price_per_mtok` is a single published constant (`DEFAULT_PRICE_PER_MTOK = 3.0`, config-overridable). No model is ever asked "how much did this save." This plan implements **measured inbound only** (spec phases 1–3); estimated/cross-user proxy savings, the outbound "your traces saved others" clause, and the anonymized server increment are explicitly deferred to the server plan.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `/tmp/ct-skill/hooks/savings.py` | **Create** | Pure-local token-window helper + money/format pure functions. `sum_usage`, `money_usd`, `format_recap_line`, `_epoch`, `_hm`, and the constants `DEFAULT_PRICE_PER_MTOK`, `TOKEN_CAP`, `TOKENS_PER_TURN_EST`, `_USAGE_KEYS`. No network, no LLM, never raises in `sum_usage`. |
| `/tmp/ct-skill/hooks/local_store.py` | **Modify** | Bump `CURRENT_SCHEMA_VERSION` to 4; add `savings_events` table + index to `_SCHEMA`; add `_migrate_to_v4` (additive); add `book_session_saving`, `savings_totals`, `prev_session_started_at`. |
| `/tmp/ct-skill/hooks/stop.py` | **Modify** | Add `transcript_path` param to `_build_candidate`, compute `tokens_to_resolution` and append it to `metadata_parts` + `metadata_json`; pass `transcript_path` at the call site; add `_book_savings` and call it in `main()` after `_persist_session`. |
| `/tmp/ct-skill/hooks/session_start.py` | **Modify** | Init `savings_recap = ""`; inside Step 2b (conn open) build the recap line from `savings_totals` + `prev_session_started_at`, gated by config `savings_recap`; append it to `additional_context`. |
| `/tmp/ct-skill/hooks/artifacts.py` | **Modify** | Add a this-month savings line to `compiled_recap`; add a `savings` subcommand to `main`; update the Usage string. |
| `/tmp/ct-skill/tests/test_savings.py` | **Create (test)** | `TestSumUsage`, `TestMoney`, `TestRecapLine` — fixture-transcript parse, money math, recap formatting. |
| `/tmp/ct-skill/tests/test_savings_ledger.py` | **Create (test)** | `TestSavingsSchema`, `TestLedgerHelpers`, `TestBookSavings`, `TestTokensInMetadata` — v4 migration, ledger helpers, booking logic, metadata instrumentation. |
| `/tmp/ct-skill/tests/test_artifacts.py` | **Modify (test)** | Add `TestCompiledRecapSavings` — recap shows/omits the savings line. |

**Verified anchors (re-confirmed against current code at plan time):**
- `local_store.py`: `CURRENT_SCHEMA_VERSION = 3` at line 23; `_SCHEMA` lines 25–87; `_apply_migrations` lines 90–100 (`if version < 2 … if version < 3 …` then `PRAGMA user_version`); `_get_conn` at 216 (sets `row_factory = sqlite3.Row` at 248, calls `_apply_migrations` 249 then `conn.executescript(_SCHEMA)` 250).
- `stop.py`: `_build_candidate(score, top_pattern, evidence, state_dir)` def at line 598; `max_iterations = max(file_counts.values()) if file_counts else 0` at line 714; `metadata_parts = [` at 731; `metadata_json: dict = {` at 792; `IMPORTANCE_THRESHOLD = 4.0` at line 51; `main()` at 951; `_persist_session(data, state_dir)` call at 965; `_report_trigger_stats(data, state_dir)` call at 968; sole `candidate = _build_candidate(score, top_pattern, top_evidence, state_dir)` call at 1016; the project_id-bridge reader pattern lives in `_report_trigger_stats` at lines 905–909 (`project_id_path = state_dir / "project_id"` … `int(project_id_path.read_text(encoding="utf-8").strip())`); `sys.path.insert(0, str(Path(__file__).parent))` at line 42.
- `session_start.py`: `contribution_recall = ""` at line 597; `session_id = data.get("session_id") or f"unknown-{uuid.uuid4().hex[:12]}"` at line 596; Step 2b conn block 598–639 (`conn.close()` at 639); `_compiled_drop(config)` block 698–703; output `print(json.dumps(output))` 705–711; `load_config()` defined at 76, first called in `main()` at 667; `sys.path.insert(0, str(Path(__file__).parent))` at line 476.
- `artifacts.py`: `compiled_recap(conn, year, month)` at line 308 (its `start, end = month_range(year, month)` at 314; contributions block + `return "\n".join(lines)` ends at 366); `main(argv)` at 382; unknown-command Usage print at 422–423; `KNOWN_PATTERNS` frozenset at line 29; `sys.path.insert(0, str(Path(__file__).parent))` at line 21.
- `session_state.py`: `read_events(state_dir, filename) -> list[dict]` at line 71; every event dict carries `"t"` (epoch float). Files: `errors.jsonl`, `resolutions.jsonl`, `changes.jsonl`, `research.jsonl`, `contributions.jsonl`.
- `tests/base.py`: `HookTestCase` patches `local_store.DB_PATH`, `artifacts.ARTIFACTS_DIR`, `post_tool_use.COOLDOWN_DIR/CONFIG_FILE`; provides `self.state_dir`, `get_conn()`, `write_project_bridge(conn, state_dir=None)`; re-exports `append_event`, `read_events`.

**Test runner (used verbatim throughout):**
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest discover -s tests
```
Single test:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_X.TestClass.test_method -v
```
Syntax-check gate before every commit (project rule):
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/FILE.py', doraise=True)"
```

---

## Task 1 — `savings.py`: token-window sum + money + recap formatting (pure functions)

**Files:**
- Create: `/tmp/ct-skill/hooks/savings.py`
- Test: `/tmp/ct-skill/tests/test_savings.py`

This task builds the whole pure-function core: `sum_usage` (transcript parsing, in-window inclusion, cap, never-raises), `money_usd` (token×price), `_hm` (minutes→"~Xm"/"~Yh"), and `format_recap_line` (the inbound-only recap string). No DB, no network.

### Step 1: Write the failing test

- [ ] Create `/tmp/ct-skill/tests/test_savings.py` with this FULL content:

```python
"""Tests for hooks/savings.py — token-window sum, money, recap formatting.

Pure-function tests with a hand-built fixture transcript JSONL. No DB,
no network. sum_usage must NEVER raise — it returns 0 on any failure.
"""

import json
import unittest

from base import HookTestCase  # noqa: F401  (path bootstrap inserts hooks/)

import savings


def _line(ts, inp=0, out=0, cc=0, cr=0, typ="assistant"):
    """One transcript JSONL object: top-level ISO timestamp + message.usage."""
    return json.dumps({
        "timestamp": ts,
        "type": typ,
        "message": {"usage": {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_creation_input_tokens": cc,
            "cache_read_input_tokens": cr,
        }},
    })


class TestSumUsage(HookTestCase):
    def _write_transcript(self, lines):
        path = self.tmp_path / "transcript.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_sums_usage_inside_window(self):
        # Two messages at 12:00:00Z and 12:05:00Z; window covers both.
        path = self._write_transcript([
            _line("2026-06-14T12:00:00Z", inp=100, out=50),
            _line("2026-06-14T12:05:00Z", inp=200, out=80, cr=20),
        ])
        start = savings._epoch("2026-06-14T11:59:00Z")
        end = savings._epoch("2026-06-14T12:06:00Z")
        # 100+50 + 200+80+20 = 450
        self.assertEqual(savings.sum_usage(path, start, end), 450)

    def test_excludes_messages_outside_window(self):
        path = self._write_transcript([
            _line("2026-06-14T11:00:00Z", inp=1000, out=1000),   # before
            _line("2026-06-14T12:00:00Z", inp=100, out=50),       # in
            _line("2026-06-14T13:00:00Z", inp=2000, out=2000),    # after
        ])
        start = savings._epoch("2026-06-14T11:59:00Z")
        end = savings._epoch("2026-06-14T12:06:00Z")
        self.assertEqual(savings.sum_usage(path, start, end), 150)

    def test_caps_at_token_cap(self):
        path = self._write_transcript([
            _line("2026-06-14T12:00:00Z", inp=savings.TOKEN_CAP + 5_000_000),
        ])
        start = savings._epoch("2026-06-14T11:00:00Z")
        end = savings._epoch("2026-06-14T13:00:00Z")
        self.assertEqual(savings.sum_usage(path, start, end), savings.TOKEN_CAP)

    def test_missing_file_returns_zero(self):
        self.assertEqual(
            savings.sum_usage(str(self.tmp_path / "nope.jsonl"), 0.0, 9e9), 0)

    def test_empty_path_returns_zero(self):
        self.assertEqual(savings.sum_usage("", 0.0, 9e9), 0)

    def test_bad_json_lines_skipped_not_raised(self):
        path = self.tmp_path / "mixed.jsonl"
        path.write_text(
            _line("2026-06-14T12:00:00Z", inp=100) + "\n"
            "{ this is not json\n"
            + _line("2026-06-14T12:01:00Z", out=40) + "\n",
            encoding="utf-8")
        start = savings._epoch("2026-06-14T11:00:00Z")
        end = savings._epoch("2026-06-14T13:00:00Z")
        self.assertEqual(savings.sum_usage(str(path), start, end), 140)

    def test_non_int_usage_values_ignored(self):
        path = self.tmp_path / "weird.jsonl"
        bad = json.dumps({
            "timestamp": "2026-06-14T12:00:00Z",
            "message": {"usage": {"input_tokens": "lots", "output_tokens": 30}},
        })
        path.write_text(bad + "\n", encoding="utf-8")
        start = savings._epoch("2026-06-14T11:00:00Z")
        end = savings._epoch("2026-06-14T13:00:00Z")
        self.assertEqual(savings.sum_usage(str(path), start, end), 30)


class TestMoney(unittest.TestCase):
    def test_default_price_is_three(self):
        self.assertEqual(savings.DEFAULT_PRICE_PER_MTOK, 3.0)

    def test_one_million_tokens_at_default(self):
        self.assertEqual(savings.money_usd(1_000_000), 3.0)

    def test_half_million_tokens(self):
        self.assertEqual(savings.money_usd(500_000), 1.5)

    def test_zero_tokens(self):
        self.assertEqual(savings.money_usd(0), 0.0)

    def test_price_override(self):
        self.assertEqual(savings.money_usd(1_000_000, price_per_mtok=5.0), 5.0)

    def test_rounds_to_cents(self):
        # 333_333 / 1e6 * 3 = 0.999999 -> 1.0
        self.assertEqual(savings.money_usd(333_333), 1.0)


class TestHm(unittest.TestCase):
    def test_minutes_under_an_hour(self):
        self.assertEqual(savings._hm(2), "~2m")
        self.assertEqual(savings._hm(2.4), "~2m")
        self.assertEqual(savings._hm(59), "~59m")

    def test_exactly_one_hour_drops_trailing_zero(self):
        self.assertEqual(savings._hm(60), "~1h")

    def test_ninety_minutes_is_one_point_five_hours(self):
        self.assertEqual(savings._hm(90), "~1.5h")


class TestRecapLine(unittest.TestCase):
    def test_delta_and_lifetime(self):
        life = {"minutes": 540.0, "tokens": 4_000_000, "events": 9}
        delta = {"minutes": 30.0, "tokens": 1_000_000}
        line = savings.format_recap_line(life, delta)
        self.assertTrue(line.startswith("CommonTrace: "))
        self.assertIn("saved you ~30m ~$3.0 since last session", line)
        self.assertIn("lifetime ~9h/~$12.0", line)
        self.assertIn(" · ", line)
        # Inbound only — no outbound clause leaks in at phases 1-3.
        self.assertNotIn("saved others", line)

    def test_lifetime_only_when_no_delta(self):
        life = {"minutes": 120.0, "tokens": 2_000_000, "events": 3}
        line = savings.format_recap_line(life, None)
        self.assertEqual(line, "CommonTrace: lifetime ~2h/~$6.0")

    def test_empty_returns_empty_string(self):
        life = {"minutes": 0.0, "tokens": 0, "events": 0}
        self.assertEqual(savings.format_recap_line(life, None), "")

    def test_zero_delta_falls_back_to_lifetime_only(self):
        life = {"minutes": 120.0, "tokens": 2_000_000, "events": 3}
        delta = {"minutes": 0.0, "tokens": 0}
        line = savings.format_recap_line(life, delta)
        self.assertEqual(line, "CommonTrace: lifetime ~2h/~$6.0")

    def test_price_override_flows_into_money(self):
        life = {"minutes": 60.0, "tokens": 1_000_000, "events": 1}
        line = savings.format_recap_line(life, None, price_per_mtok=10.0)
        self.assertIn("~$10.0", line)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run the test — expect FAIL (module does not exist)

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings -v
```
Expected: collection error / failure with `ModuleNotFoundError: No module named 'savings'` (the `import savings` at the top of the test file fails because `hooks/savings.py` does not yet exist).

### Step 3: Write the minimal implementation

- [ ] Create `/tmp/ct-skill/hooks/savings.py` with this FULL content:

```python
"""Pure-local savings instrument — no network, no LLM, never asks a model.

Every money number here is a MEASURED token count multiplied by one
published price constant. Tokens come from the Stop hook's transcript
(message.usage) summed over a time window; the price is DEFAULT_PRICE_PER_MTOK
(config-overridable). sum_usage must NEVER raise — it returns 0 on any
failure (no path, missing file, bad JSON, bad usage values).

Phases 1-3 = MEASURED INBOUND ONLY. No "your traces saved others" clause
is emitted here; that outbound view is the server plan's job.
"""

import json
from datetime import datetime, timezone

# Blended placeholder price ($ per 1M tokens). Overridable via config key
# "price_per_mtok". FLAGGED for user confirmation before release.
DEFAULT_PRICE_PER_MTOK = 3.0

# A single wall-clock window can span breaks/overnight; cap the per-window
# token sum so one event cannot inflate the total.
TOKEN_CAP = 2_000_000

# Legacy fallback only (pre-instrument traces lacking a measured count):
# conservative tokens-per-turn estimate. New traces are always measured.
TOKENS_PER_TURN_EST = 1500

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _epoch(ts: str) -> float:
    """ISO-8601 (trailing 'Z') -> UTC epoch float, comparable to event 't'."""
    return (datetime.fromisoformat(ts.replace("Z", "+00:00"))
            .astimezone(timezone.utc).timestamp())


def sum_usage(transcript_path: str, start_t: float, end_t: float) -> int:
    """Sum message.usage tokens for transcript lines inside [start_t, end_t].

    Returns min(total, TOKEN_CAP). Returns 0 on ANY failure and never raises.
    """
    if not transcript_path:
        return 0
    total = 0
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                ts = obj.get("timestamp")
                if not isinstance(ts, str):
                    continue
                try:
                    epoch = _epoch(ts)
                except (ValueError, TypeError):
                    continue
                if not (start_t <= epoch <= end_t):
                    continue
                usage = (obj.get("message") or {}).get("usage") or {}
                for key in _USAGE_KEYS:
                    val = usage.get(key)
                    if isinstance(val, int) and not isinstance(val, bool):
                        total += val
    except (OSError, ValueError):
        return 0
    return min(total, TOKEN_CAP)


def money_usd(tokens: int, price_per_mtok: float = None) -> float:
    """Money saved = tokens / 1M * price. Price is the only chosen constant."""
    price = price_per_mtok if price_per_mtok is not None else DEFAULT_PRICE_PER_MTOK
    return round(tokens / 1_000_000 * price, 2)


def _hm(minutes: float) -> str:
    """Compact duration: '~Xm' under an hour, '~Yh' (no trailing .0) above."""
    if minutes >= 60:
        hours = round(minutes / 60, 1)
        text = str(hours)
        if text.endswith(".0"):
            text = text[:-2]
        return "~" + text + "h"
    return "~" + str(int(round(minutes))) + "m"


def format_recap_line(life: dict, delta: dict = None,
                      price_per_mtok: float = None) -> str:
    """Build the one-line session-start recap. INBOUND ONLY.

    life  = {"minutes": float, "tokens": int, "events": int} lifetime totals.
    delta = {"minutes": float, "tokens": int} since last session, or None.
    Returns "" when there is nothing to say.
    """
    parts = []
    if delta and (delta.get("minutes", 0) > 0 or delta.get("tokens", 0) > 0):
        parts.append(
            "saved you " + _hm(delta.get("minutes", 0)) + " ~$"
            + str(money_usd(delta.get("tokens", 0), price_per_mtok))
            + " since last session")
    if life.get("minutes", 0) > 0 or life.get("tokens", 0) > 0:
        parts.append(
            "lifetime " + _hm(life.get("minutes", 0)) + "/~$"
            + str(money_usd(life.get("tokens", 0), price_per_mtok)))
    if not parts:
        return ""
    return "CommonTrace: " + " · ".join(parts)
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings -v
```
Expected: `OK` — all of `TestSumUsage` (7), `TestMoney` (6), `TestHm` (3), `TestRecapLine` (5) pass.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/savings.py', doraise=True)" && git add hooks/savings.py tests/test_savings.py && git commit -m "feat(savings): add pure-local token-window + money + recap helpers

sum_usage sums message.usage over a transcript time window (measured tokens,
never raises, capped). money_usd = tokens x published price constant. _hm and
format_recap_line render the inbound-only recap. No network, no LLM.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2 — `local_store.py`: schema v4 + `savings_events` table + migration

**Files:**
- Modify: `/tmp/ct-skill/hooks/local_store.py:23` (`CURRENT_SCHEMA_VERSION`), `:25-87` (`_SCHEMA`), `:90-100` (`_apply_migrations`)
- Test: `/tmp/ct-skill/tests/test_savings_ledger.py` (new — `TestSavingsSchema` only in this task)

Bump the schema version, add the `savings_events` table to the idempotent `_SCHEMA` (so fresh DBs get it via `executescript`), and add an additive `_migrate_to_v4` (so existing v3 DBs gain the table without a rebuild).

### Step 1: Write the failing test

- [ ] Create `/tmp/ct-skill/tests/test_savings_ledger.py` with this FULL content (this task adds only `TestSavingsSchema`; later tasks append more classes to this same file):

```python
"""Tests for the savings ledger: schema v4, ledger helpers, booking, metadata.

Uses HookTestCase isolation (temp local.db). The v4 migration test hand-builds
a real v3 database file, then opens it through _get_conn() and asserts the
additive migration ran (savings_events present, user_version == 4).
"""

import json
import sqlite3
import time
import unittest

from base import HookTestCase, append_event  # noqa: F401

import local_store


DAY = 86400.0


def _make_v3_db(path):
    """Build a real v3 database file (5 tables, user_version=3, no savings)."""
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
            created_at REAL NOT NULL, last_seen_at REAL NOT NULL,
            seen_count INTEGER DEFAULT 1,
            resolved_at REAL, fix_command TEXT, fix_files TEXT, trace_id TEXT,
            UNIQUE(project_id, signature)
        );
    """)
    conn.execute(
        "INSERT INTO projects (path, first_seen_at, last_seen_at) "
        "VALUES ('/p', ?, ?)", (time.time(), time.time()))
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()


class TestSavingsSchema(HookTestCase):
    def test_current_schema_version_is_four(self):
        self.assertEqual(local_store.CURRENT_SCHEMA_VERSION, 4)

    def test_fresh_db_has_savings_events_table(self):
        conn = self.get_conn()
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("savings_events", tables)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_savings_events_columns(self):
        conn = self.get_conn()
        cols = {row[1] for row in
                conn.execute("PRAGMA table_info(savings_events)")}
        self.assertLessEqual(
            {"id", "project_id", "session_id", "event_type", "minutes_saved",
             "tokens_saved", "source_label", "trace_id", "signature",
             "created_at"}, cols)

    def test_v3_db_migrates_to_v4_additively(self):
        _make_v3_db(local_store.DB_PATH)
        conn = self.get_conn()  # opening triggers _apply_migrations
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("savings_events", tables)
        # Pre-existing v3 data survived (additive migration, no rebuild).
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_v4_migration_is_idempotent(self):
        _make_v3_db(local_store.DB_PATH)
        self.get_conn().close()
        conn = self.get_conn()  # second open must not break
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("savings_events", tables)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run the test — expect FAIL

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestSavingsSchema -v
```
Expected: failures — `test_current_schema_version_is_four` fails with `4 != 3`, and the table/migration tests fail with `AssertionError: 'savings_events' not found in {...}` (the table does not exist yet).

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/local_store.py` line 23, change the version constant:

```python
CURRENT_SCHEMA_VERSION = 4
```

- [ ] Edit `/tmp/ct-skill/hooks/local_store.py` `_SCHEMA` — append the `savings_events` table and its index immediately before the closing `"""` of `_SCHEMA` (i.e. right after the `idx_error_sig_project` index line at 86, before line 87's `"""`). Add:

```python
CREATE TABLE IF NOT EXISTS savings_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT,
    event_type TEXT NOT NULL,
    minutes_saved REAL DEFAULT 0,
    tokens_saved INTEGER DEFAULT 0,
    source_label TEXT,
    trace_id TEXT,
    signature TEXT NOT NULL DEFAULT '*session*',
    created_at REAL NOT NULL,
    UNIQUE(session_id, event_type, signature)
);
CREATE INDEX IF NOT EXISTS idx_savings_created ON savings_events(project_id, created_at DESC);
```

- [ ] Edit `/tmp/ct-skill/hooks/local_store.py` `_apply_migrations` — insert the v4 step between the `if version < 3:` line (98) and the `PRAGMA user_version` line (99). The block becomes:

```python
    if version < 2:
        _migrate_to_v2(conn)
    if version < 3:
        _migrate_to_v3(conn)
    if version < 4:
        _migrate_to_v4(conn)
    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    conn.commit()
```

- [ ] Add the `_migrate_to_v4` function. Insert it immediately after the end of `_migrate_to_v3` (after its closing block at line 213, before `def _get_conn`):

```python
def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    """Migrate v3 -> v4: add the savings_events ledger. Additive only.

    No table rebuild — just create the new table + index if absent. Existing
    rows in every other table are untouched.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS savings_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            session_id TEXT,
            event_type TEXT NOT NULL,
            minutes_saved REAL DEFAULT 0,
            tokens_saved INTEGER DEFAULT 0,
            source_label TEXT,
            trace_id TEXT,
            signature TEXT NOT NULL DEFAULT '*session*',
            created_at REAL NOT NULL,
            UNIQUE(session_id, event_type, signature)
        );
        CREATE INDEX IF NOT EXISTS idx_savings_created
            ON savings_events(project_id, created_at DESC);
    """)
    conn.commit()
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestSavingsSchema -v
```
Expected: `OK` — all 5 `TestSavingsSchema` tests pass.

- [ ] Run the existing migration suite to confirm no regression on the v2/v3 path:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_local_store_v3 -v
```
Expected: `OK` — the existing v3 tests (`test_v2_db_dedupes_into_seen_counts` asserting `user_version == 3`) still pass, because `_make_v2_db` stamps `user_version = 2` and migrates straight through v3 then v4 to **4**; note `test_local_store_v3.py::test_v2_db_dedupes_into_seen_counts` asserts `== 3` on a DB that now ends at 4. **If that assertion fails (`4 != 3`)**, it is a stale expectation in the pre-existing test: update that one assertion in `tests/test_local_store_v3.py` from `3` to `4` (the dedupe behavior under test is unchanged; only the terminal version moved). Re-run until `OK`.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/local_store.py', doraise=True)" && git add hooks/local_store.py tests/test_savings_ledger.py tests/test_local_store_v3.py && git commit -m "feat(local_store): schema v4 — savings_events ledger + additive migration

Adds savings_events (per-session inbound savings) to _SCHEMA and an additive
_migrate_to_v4 (no rebuild). Bumps CURRENT_SCHEMA_VERSION to 4. UNIQUE(session,
event_type, signature) enforces the once-per-(session,signature) booking guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3 — `local_store.py`: ledger helpers (`book_session_saving`, `savings_totals`, `prev_session_started_at`)

**Files:**
- Modify: `/tmp/ct-skill/hooks/local_store.py` (add three functions after `record_resolution`, before the `# Trigger feedback` section at line 404)
- Test: `/tmp/ct-skill/tests/test_savings_ledger.py` (append `TestLedgerHelpers`)

These three helpers are the entire DB-write/read surface for inbound savings: `book_session_saving` (guarded INSERT OR IGNORE), `savings_totals` (rollup, optional `since`), `prev_session_started_at` (the delta window source).

### Step 1: Write the failing test

- [ ] Append this class to `/tmp/ct-skill/tests/test_savings_ledger.py` (after `TestSavingsSchema`, before the `if __name__` block):

```python
class TestLedgerHelpers(HookTestCase):
    def test_book_inserts_a_row(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        ok = local_store.book_session_saving(
            conn, pid, "sess-1", minutes=12.5, tokens=300_000)
        self.assertTrue(ok)
        row = conn.execute(
            "SELECT minutes_saved, tokens_saved, event_type, source_label, "
            "signature FROM savings_events").fetchone()
        self.assertAlmostEqual(row["minutes_saved"], 12.5)
        self.assertEqual(row["tokens_saved"], 300_000)
        self.assertEqual(row["event_type"], "measured_recurrence")
        self.assertEqual(row["source_label"], "measured")
        self.assertEqual(row["signature"], "*session*")

    def test_book_is_noop_on_zero_zero(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        self.assertFalse(
            local_store.book_session_saving(conn, pid, "sess-1", 0, 0))
        n = conn.execute("SELECT COUNT(*) FROM savings_events").fetchone()[0]
        self.assertEqual(n, 0)

    def test_book_books_when_only_minutes_positive(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        self.assertTrue(
            local_store.book_session_saving(conn, pid, "sess-1", 5.0, 0))

    def test_book_dedups_same_session_event_signature(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        self.assertTrue(
            local_store.book_session_saving(conn, pid, "sess-1", 10, 100))
        # Same (session, event_type, default signature) -> INSERT OR IGNORE drops it.
        self.assertFalse(
            local_store.book_session_saving(conn, pid, "sess-1", 99, 999))
        n = conn.execute("SELECT COUNT(*) FROM savings_events").fetchone()[0]
        self.assertEqual(n, 1)

    def test_book_different_session_counts_again(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        local_store.book_session_saving(conn, pid, "sess-1", 10, 100)
        self.assertTrue(
            local_store.book_session_saving(conn, pid, "sess-2", 10, 100))
        n = conn.execute("SELECT COUNT(*) FROM savings_events").fetchone()[0]
        self.assertEqual(n, 2)

    def test_savings_totals_sums_all(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        local_store.book_session_saving(conn, pid, "s1", 10.0, 100_000)
        local_store.book_session_saving(conn, pid, "s2", 20.0, 200_000)
        totals = local_store.savings_totals(conn)
        self.assertAlmostEqual(totals["minutes"], 30.0)
        self.assertEqual(totals["tokens"], 300_000)
        self.assertEqual(totals["events"], 2)

    def test_savings_totals_empty_is_zeroed(self):
        conn = self.get_conn()
        totals = local_store.savings_totals(conn)
        self.assertEqual(totals, {"minutes": 0.0, "tokens": 0, "events": 0})

    def test_savings_totals_since_filters_by_created_at(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        now = time.time()
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "old", "measured_recurrence", 5.0, 50, now - 10 * DAY))
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "new", "measured_recurrence", 7.0, 70, now - 1 * DAY))
        conn.commit()
        totals = local_store.savings_totals(conn, since=now - 5 * DAY)
        self.assertAlmostEqual(totals["minutes"], 7.0)
        self.assertEqual(totals["tokens"], 70)
        self.assertEqual(totals["events"], 1)

    def test_prev_session_started_at_picks_most_recent_other(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        now = time.time()
        for sid, started in [("a", now - 3 * DAY), ("b", now - 1 * DAY),
                             ("current", now)]:
            conn.execute(
                "INSERT INTO sessions (id, project_id, started_at) "
                "VALUES (?, ?, ?)", (sid, pid, started))
        conn.commit()
        prev = local_store.prev_session_started_at(conn, "current")
        self.assertAlmostEqual(prev, now - 1 * DAY)

    def test_prev_session_started_at_none_when_alone(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at) "
            "VALUES ('only', ?, ?)", (pid, time.time()))
        conn.commit()
        self.assertIsNone(
            local_store.prev_session_started_at(conn, "only"))
```

### Step 2: Run the test — expect FAIL

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestLedgerHelpers -v
```
Expected: failures with `AttributeError: module 'local_store' has no attribute 'book_session_saving'` (and likewise for `savings_totals`, `prev_session_started_at`).

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/local_store.py` — insert these three functions immediately after `record_resolution` ends (after its `return cur.rowcount > 0` at line 401), before the `# Trigger feedback` divider comment at line 404:

```python
# ---------------------------------------------------------------------------
# Savings ledger (inbound — what the commons saved you)
# ---------------------------------------------------------------------------

def book_session_saving(conn: sqlite3.Connection, project_id: int,
                        session_id: str, minutes: float, tokens: int,
                        event_type: str = "measured_recurrence",
                        source_label: str = "measured",
                        trace_id: str = None) -> bool:
    """Book one inbound saving for this session. Guarded + idempotent.

    Returns False (and writes nothing) when both minutes and tokens are
    non-positive. The signature column defaults to '*session*' so the
    UNIQUE(session_id, event_type, signature) constraint enforces one
    booking per (session, event_type) — INSERT OR IGNORE drops a repeat.
    Returns True only when a new row was actually inserted.
    """
    if minutes <= 0 and tokens <= 0:
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO savings_events "
        "(project_id, session_id, event_type, minutes_saved, tokens_saved, "
        "source_label, trace_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, event_type, minutes, tokens,
         source_label, trace_id, time.time()),
    )
    conn.commit()
    return cur.rowcount > 0


def savings_totals(conn: sqlite3.Connection, since: float = None) -> dict:
    """Roll up the savings ledger.

    Returns {"minutes": float, "tokens": int, "events": int}. When `since`
    is given, only rows with created_at >= since are counted.
    """
    if since is None:
        row = conn.execute(
            "SELECT COALESCE(SUM(minutes_saved), 0), "
            "COALESCE(SUM(tokens_saved), 0), COUNT(*) FROM savings_events"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(minutes_saved), 0), "
            "COALESCE(SUM(tokens_saved), 0), COUNT(*) FROM savings_events "
            "WHERE created_at >= ?", (since,)
        ).fetchone()
    return {"minutes": float(row[0]), "tokens": int(row[1]),
            "events": int(row[2])}


def prev_session_started_at(conn: sqlite3.Connection,
                            current_session_id: str) -> float | None:
    """Started-at of the most recent session OTHER than the current one.

    Used as the lower bound for the 'since last session' delta. Returns None
    when no other session exists.
    """
    row = conn.execute(
        "SELECT MAX(started_at) FROM sessions WHERE id != ?",
        (current_session_id,),
    ).fetchone()
    return row[0] if row and row[0] is not None else None
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestLedgerHelpers -v
```
Expected: `OK` — all 10 `TestLedgerHelpers` tests pass.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/local_store.py', doraise=True)" && git add hooks/local_store.py tests/test_savings_ledger.py && git commit -m "feat(local_store): savings ledger helpers — book/totals/prev-session

book_session_saving (guarded, INSERT OR IGNORE once-per-session), savings_totals
(rollup with optional since), prev_session_started_at (delta window bound).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4 — `stop.py`: instrument `tokens_to_resolution` into contribution metadata

**Files:**
- Modify: `/tmp/ct-skill/hooks/stop.py:598` (`_build_candidate` signature), `:714+` (compute tokens after `max_iterations`), `:731-737` (`metadata_parts`), `:792-798` (`metadata_json`), `:1016` (call site)
- Test: `/tmp/ct-skill/tests/test_savings_ledger.py` (append `TestTokensInMetadata`)

The Stop hook already computes the first-error→resolved window (`timestamps`, lines 706–708). Sum `message.usage` over that same window and record `tokens_to_resolution` in both the human metadata hint (`metadata_parts`) and the structured `metadata_json`, so the measured count rides with the contributed trace. Falls back to a conservative `(error_count + iteration_count) * TOKENS_PER_TURN_EST` only when no measured tokens are found.

### Step 1: Write the failing test

- [ ] Append this class to `/tmp/ct-skill/tests/test_savings_ledger.py` (after `TestLedgerHelpers`, before the `if __name__` block). It imports `stop` and drives `_build_candidate` directly by seeding state-dir events and a fixture transcript:

```python
class TestTokensInMetadata(HookTestCase):
    def setUp(self):
        super().setUp()
        import stop  # local import: base.py has already inserted hooks/ on path
        self.stop = stop

    def _transcript(self, lines):
        path = self.tmp_path / "t.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_measured_tokens_in_metadata_json(self):
        t0 = 1_750_000_000.0  # epoch the events use
        # Map t0 to a matching ISO timestamp for the transcript line.
        from datetime import datetime, timezone
        iso0 = datetime.fromtimestamp(t0, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        iso1 = datetime.fromtimestamp(t0 + 120, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        append_event(self.state_dir, "errors.jsonl", {"t": t0})
        append_event(self.state_dir, "changes.jsonl",
                     {"t": t0 + 120, "file": "app.py"})
        transcript = self._transcript([
            json.dumps({"timestamp": iso0,
                        "message": {"usage": {"input_tokens": 400,
                                              "output_tokens": 100}}}),
            json.dumps({"timestamp": iso1,
                        "message": {"usage": {"input_tokens": 200,
                                              "output_tokens": 50}}}),
        ])
        cand = self.stop._build_candidate(
            5.0, "error_resolution", {"errors": 1, "changes": 1},
            self.state_dir, transcript_path=transcript)
        self.assertEqual(cand["metadata_json"]["tokens_to_resolution"], 750)
        self.assertIn('"tokens_to_resolution": 750',
                      cand["human_prompt"])

    def test_fallback_estimate_when_no_transcript(self):
        t0 = 1_750_000_000.0
        # 2 errors + 1 edit on the same file (iteration_count == 1).
        append_event(self.state_dir, "errors.jsonl", {"t": t0})
        append_event(self.state_dir, "errors.jsonl", {"t": t0 + 30})
        append_event(self.state_dir, "changes.jsonl",
                     {"t": t0 + 60, "file": "app.py"})
        cand = self.stop._build_candidate(
            5.0, "error_resolution", {"errors": 2, "changes": 1},
            self.state_dir, transcript_path="")
        # (error_count 2 + iteration_count 1) * TOKENS_PER_TURN_EST(1500) = 4500
        self.assertEqual(
            cand["metadata_json"]["tokens_to_resolution"], 4500)

    def test_default_transcript_path_arg_is_optional(self):
        # Calling without the new kwarg must still work (default "").
        t0 = 1_750_000_000.0
        append_event(self.state_dir, "errors.jsonl", {"t": t0})
        append_event(self.state_dir, "changes.jsonl",
                     {"t": t0 + 10, "file": "x.py"})
        cand = self.stop._build_candidate(
            5.0, "error_resolution", {"errors": 1, "changes": 1},
            self.state_dir)
        self.assertIn("tokens_to_resolution", cand["metadata_json"])
```

### Step 2: Run the test — expect FAIL

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestTokensInMetadata -v
```
Expected: failures — `test_default_transcript_path_arg_is_optional` and the others fail with `TypeError: _build_candidate() got an unexpected keyword argument 'transcript_path'` (the param does not exist yet); even the no-kwarg test fails its assertion because `tokens_to_resolution` is not in `metadata_json`.

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` line 598–599 — change the `_build_candidate` signature to add the optional `transcript_path` param:

```python
def _build_candidate(score: float, top_pattern: str, evidence: dict,
                     state_dir: Path, transcript_path: str = "") -> dict:
```

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` — immediately after `max_iterations = max(file_counts.values()) if file_counts else 0` (line 714), insert the token computation. The local error list is named `errors` (read at line 703 via `errors = read_events(state_dir, "errors.jsonl")`), and `timestamps` is the window list from line 706:

```python
    # Measured token cost of the resolution window (rides with the trace).
    # No LLM — a real sum of message.usage over the first-error->resolved span.
    from savings import sum_usage, TOKENS_PER_TURN_EST
    if timestamps:
        tokens_to_resolution = sum_usage(
            transcript_path, min(timestamps), max(timestamps))
    else:
        tokens_to_resolution = 0
    if tokens_to_resolution <= 0:
        # Conservative legacy floor when the window has no measurable usage.
        tokens_to_resolution = (len(errors) + max_iterations) * TOKENS_PER_TURN_EST
```

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` `metadata_parts` list (lines 731–737) — append the `tokens_to_resolution` entry after the `user_emphasis` line:

```python
    metadata_parts = [
        f'"detection_pattern": "{top_pattern}"',
        f'"error_count": {len(errors)}',
        f'"time_to_resolution_minutes": {duration_min}',
        f'"iteration_count": {max_iterations}',
        f'"user_emphasis": {peak_emphasis}',
        f'"tokens_to_resolution": {tokens_to_resolution}',
    ]
```

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` `metadata_json` dict (lines 792–798) — add the `tokens_to_resolution` key after `user_emphasis`:

```python
    metadata_json: dict = {
        "detection_pattern": top_pattern,
        "error_count": len(errors),
        "time_to_resolution_minutes": duration_min,
        "iteration_count": max_iterations,
        "user_emphasis": peak_emphasis,
        "tokens_to_resolution": tokens_to_resolution,
    }
```

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` line 1016 — pass `transcript_path` at the sole call site:

```python
    candidate = _build_candidate(score, top_pattern, top_evidence, state_dir,
                                 transcript_path=data.get("transcript_path", ""))
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestTokensInMetadata -v
```
Expected: `OK` — all 3 `TestTokensInMetadata` tests pass.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/stop.py', doraise=True)" && git add hooks/stop.py tests/test_savings_ledger.py && git commit -m "feat(stop): record measured tokens_to_resolution in contribution metadata

_build_candidate sums message.usage over the existing first-error->resolved
window (measured, never raises) and records tokens_to_resolution in both the
metadata hint and metadata_json. Conservative (errors+iterations)*EST floor
only when the window has no measurable usage. No LLM.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5 — `stop.py`: `_book_savings` — book measured-recurrence inbound savings

**Files:**
- Modify: `/tmp/ct-skill/hooks/stop.py` (add `_book_savings`, e.g. after `_persist_session` ends at line 842; wire its call in `main()` after the `_persist_session(data, state_dir)` call at line 965)
- Test: `/tmp/ct-skill/tests/test_savings_ledger.py` (append `TestBookSavings`)

At Stop, if any error signature for this project was resolved with an attributed `trace_id` within this session's window, book a MEASURED INBOUND saving: `minutes` = summed `(resolved_at − created_at)` capped at 120 min/event, `tokens` = `sum_usage` over the session window. Whole body wrapped in try/except so it can never crash the hook. Reads the `project_id` bridge exactly the way `_report_trigger_stats` does (lines 905–909).

### Step 1: Write the failing test

- [ ] Append this class to `/tmp/ct-skill/tests/test_savings_ledger.py` (after `TestTokensInMetadata`, before the `if __name__` block):

```python
class TestBookSavings(HookTestCase):
    def setUp(self):
        super().setUp()
        import stop
        self.stop = stop

    def _seed_resolved_signature(self, conn, pid, created, resolved,
                                 trace_id="t-1", signature="sig-a"):
        conn.execute(
            "INSERT INTO error_signatures (project_id, signature, created_at, "
            "last_seen_at, seen_count, resolved_at, trace_id) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (pid, signature, created, resolved, resolved, trace_id))
        conn.commit()

    def test_books_row_for_resolved_trace_linked_signature(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        t0 = time.time()
        # Resolved this session: created 6 min before, resolved at t0.
        self._seed_resolved_signature(conn, pid, t0 - 360, t0)
        conn.close()
        # Session window events bracket the resolution.
        append_event(self.state_dir, "errors.jsonl", {"t": t0 - 360})
        append_event(self.state_dir, "resolutions.jsonl", {"t": t0})
        data = {"session_id": "sess-book", "transcript_path": ""}
        self.stop._book_savings(data, self.state_dir)
        conn2 = local_store._get_conn()
        self.addCleanup(conn2.close)
        row = conn2.execute(
            "SELECT minutes_saved, event_type, source_label "
            "FROM savings_events").fetchone()
        self.assertIsNotNone(row)
        # 360s / 60 = 6.0 minutes (under the 120-min cap).
        self.assertAlmostEqual(row["minutes_saved"], 6.0)
        self.assertEqual(row["event_type"], "measured_recurrence")

    def test_minutes_capped_at_120_per_event(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        t0 = time.time()
        # 10-hour span would be 600 min uncapped; cap is 120.
        self._seed_resolved_signature(conn, pid, t0 - 36000, t0)
        conn.close()
        append_event(self.state_dir, "errors.jsonl", {"t": t0 - 36000})
        append_event(self.state_dir, "resolutions.jsonl", {"t": t0})
        self.stop._book_savings(
            {"session_id": "sess-cap", "transcript_path": ""}, self.state_dir)
        conn2 = local_store._get_conn()
        self.addCleanup(conn2.close)
        m = conn2.execute(
            "SELECT minutes_saved FROM savings_events").fetchone()["minutes_saved"]
        self.assertAlmostEqual(m, 120.0)

    def test_no_row_when_no_trace_linked_resolution(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        t0 = time.time()
        # Resolved but NO trace_id attributed -> not a commons-credited saving.
        conn.execute(
            "INSERT INTO error_signatures (project_id, signature, created_at, "
            "last_seen_at, seen_count, resolved_at, trace_id) "
            "VALUES (?, 'sig-x', ?, ?, 1, ?, NULL)",
            (pid, t0 - 100, t0, t0))
        conn.commit()
        conn.close()
        append_event(self.state_dir, "resolutions.jsonl", {"t": t0})
        self.stop._book_savings(
            {"session_id": "sess-none", "transcript_path": ""}, self.state_dir)
        conn2 = local_store._get_conn()
        self.addCleanup(conn2.close)
        n = conn2.execute("SELECT COUNT(*) FROM savings_events").fetchone()[0]
        self.assertEqual(n, 0)

    def test_no_row_when_no_session_timestamps(self):
        conn = self.get_conn()
        pid = self.write_project_bridge(conn)
        t0 = time.time()
        self._seed_resolved_signature(conn, pid, t0 - 360, t0)
        conn.close()
        # No errors.jsonl / resolutions.jsonl events -> no window -> no booking.
        self.stop._book_savings(
            {"session_id": "sess-empty", "transcript_path": ""}, self.state_dir)
        conn2 = local_store._get_conn()
        self.addCleanup(conn2.close)
        n = conn2.execute("SELECT COUNT(*) FROM savings_events").fetchone()[0]
        self.assertEqual(n, 0)

    def test_corrupt_state_does_not_raise(self):
        # No project bridge file, garbage data -> must return quietly.
        try:
            self.stop._book_savings({"session_id": "x"}, self.state_dir)
        except Exception as exc:  # pragma: no cover
            self.fail(f"_book_savings raised: {exc!r}")
```

### Step 2: Run the test — expect FAIL

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestBookSavings -v
```
Expected: failures with `AttributeError: module 'stop' has no attribute '_book_savings'`.

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` — insert the `_book_savings` function immediately after `_persist_session` ends (after its closing `except Exception: pass` at line 842), before `def _session_counters` at line 845:

```python
def _book_savings(data: dict, state_dir: Path) -> None:
    """Book measured-inbound savings for trace-attributed recurrences.

    INBOUND ONLY (what the commons saved you). For each error signature in
    THIS project that resolved with an attributed trace_id since this
    session's window floor, credit:
      minutes = sum of (resolved_at - created_at), capped 120 min/event
      tokens  = measured message.usage over the session window
    Wrapped end-to-end so it can never crash the Stop hook. No LLM.
    """
    try:
        from savings import sum_usage
        import local_store

        project_id_path = state_dir / "project_id"
        if not project_id_path.exists():
            return
        project_id = int(project_id_path.read_text(encoding="utf-8").strip())

        times = [e["t"] for e in
                 read_events(state_dir, "resolutions.jsonl")
                 + read_events(state_dir, "errors.jsonl")
                 if "t" in e]
        if not times:
            return
        floor = min(times) - 5

        conn = local_store._get_conn()
        try:
            rows = conn.execute(
                "SELECT created_at, resolved_at FROM error_signatures "
                "WHERE project_id = ? AND trace_id IS NOT NULL "
                "AND resolved_at IS NOT NULL AND resolved_at >= ?",
                (project_id, floor),
            ).fetchall()
            if not rows:
                return
            minutes = sum(
                min(max(r["resolved_at"] - r["created_at"], 0) / 60.0, 120.0)
                for r in rows)
            tokens = sum_usage(
                data.get("transcript_path", ""), min(times) - 5, max(times) + 5)
            local_store.book_session_saving(
                conn, project_id, data.get("session_id", ""), minutes, tokens)
        finally:
            conn.close()
    except Exception:
        pass
```

- [ ] Edit `/tmp/ct-skill/hooks/stop.py` `main()` — wire the call right after `_persist_session(data, state_dir)` (line 965), before the `# Report trigger stats` comment at line 967:

```python
    # Persist session data to SQLite
    _persist_session(data, state_dir)

    # Book measured-inbound savings (best-effort; never crashes the hook)
    _book_savings(data, state_dir)

    # Report trigger stats (best-effort)
    _report_trigger_stats(data, state_dir)
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestBookSavings -v
```
Expected: `OK` — all 5 `TestBookSavings` tests pass.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/stop.py', doraise=True)" && git add hooks/stop.py tests/test_savings_ledger.py && git commit -m "feat(stop): book measured-inbound savings on trace-attributed recurrence

_book_savings credits minutes (resolved_at-created_at, capped 120/event) and
measured tokens (message.usage over the session window) for each trace-linked
resolved signature this session. Wired after _persist_session; fully guarded.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6 — `session_start.py`: session-start recap line

**Files:**
- Modify: `/tmp/ct-skill/hooks/session_start.py:597` (init `savings_recap`), Step 2b block (~598–639, build recap while conn open), and after the `_compiled_drop` block (~703, append to `additional_context`)
- Test: `/tmp/ct-skill/tests/test_savings_ledger.py` (append `TestSessionStartRecap`)

Emit one quiet recap line at session start when savings accrued, opt-outable via config `savings_recap` (default on). Built inside Step 2b while the conn is open. Because `config` is not loaded until line 667 in `main()` (after Step 2b's conn closes), load it via `load_config()` at the top of the Step 2b try-block.

### Step 1: Write the failing test

- [ ] Append this class to `/tmp/ct-skill/tests/test_savings_ledger.py` (after `TestBookSavings`, before the `if __name__` block). It calls the pure recap formatter via the same helpers `session_start` will use, then asserts `session_start`'s wiring through a focused unit on the formatter + config gate. Since `session_start.main()` does heavy I/O (network search, cwd scan), this test exercises the **recap-building seam** directly — the exact `savings_totals`/`prev_session_started_at`/`format_recap_line` composition that `main()` performs — plus the config opt-out:

```python
class TestSessionStartRecap(HookTestCase):
    def _seed_two_sessions_with_savings(self, conn):
        pid = local_store.ensure_project(conn, "/p")
        now = time.time()
        # A previous session and the current one.
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at) "
            "VALUES ('prev', ?, ?)", (pid, now - 2 * DAY))
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at) "
            "VALUES ('cur', ?, ?)", (pid, now))
        # Lifetime savings: one old (before prev), one new (after prev).
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "old", "measured_recurrence", 60.0, 1_000_000, now - 3 * DAY))
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "prev", "measured_recurrence", 30.0, 1_000_000, now - DAY))
        conn.commit()
        return pid

    def test_recap_composition_matches_main_logic(self):
        from savings import format_recap_line
        conn = self.get_conn()
        self._seed_two_sessions_with_savings(conn)
        life = local_store.savings_totals(conn)
        prev = local_store.prev_session_started_at(conn, "cur")
        delta = local_store.savings_totals(conn, since=prev) if prev else None
        line = format_recap_line(life, delta, price_per_mtok=None)
        # Lifetime = 90 min / 2M tokens; delta since prev (now-2d) = the
        # now-1d row only = 30 min / 1M tokens.
        self.assertIn("lifetime ~1.5h/~$6.0", line)
        self.assertIn("saved you ~30m ~$3.0 since last session", line)

    def test_recap_empty_when_no_savings(self):
        from savings import format_recap_line
        conn = self.get_conn()
        local_store.ensure_project(conn, "/p")
        life = local_store.savings_totals(conn)
        self.assertEqual(format_recap_line(life, None), "")

    def test_config_opt_out_default_on(self):
        # Mirrors the gate session_start uses: config.get("savings_recap", True).
        self.assertTrue({}.get("savings_recap", True))
        self.assertFalse({"savings_recap": False}.get("savings_recap", True))
```

### Step 2: Run the test — expect PASS-then-extend rationale, but first FAIL the integration import

This task's unit assertions (Step 1) target already-shipped helpers (`format_recap_line`, `savings_totals`, `prev_session_started_at` from Tasks 1+3) and so will pass immediately — they pin the **exact composition** `session_start` must implement. The behavioral change in `session_start.py` itself is verified by the full-suite run in Step 4 plus a direct import/compile check.

- [ ] Run the new class to confirm the composition contract holds:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestSessionStartRecap -v
```
Expected: `OK` (3 tests) — these lock the composition `main()` must reproduce. (They do not yet prove `session_start.py` is wired; Step 3 wires it, Step 4 proves the module still imports and the whole suite is green.)

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/session_start.py` line 597 — add the `savings_recap` initializer right after `contribution_recall = ""`:

```python
    contribution_recall = ""
    savings_recap = ""
```

- [ ] Edit `/tmp/ct-skill/hooks/session_start.py` Step 2b — inside the `try:` block, after the `contribution_recall` block (after line 621, before the `# Write bridge files` comment at line 623) while `conn` is still open, build the recap. Load config here (it is not loaded in `main()` until line 667):

```python
        # Savings recap (inbound only) — built while conn is open. Opt-out via
        # config "savings_recap" (default on). No LLM: measured tokens x price.
        cfg = load_config()
        if cfg.get("savings_recap", True):
            from savings import format_recap_line
            life = local_store.savings_totals(conn)
            prev = local_store.prev_session_started_at(conn, session_id)
            delta = (local_store.savings_totals(conn, since=prev)
                     if prev else None)
            savings_recap = format_recap_line(
                life, delta, price_per_mtok=cfg.get("price_per_mtok"))
```

  Note: the Step 2b import line (598–602) does **not** currently import `savings_totals`/`prev_session_started_at` from `local_store`; the code above references them as `local_store.savings_totals(...)` / `local_store.prev_session_started_at(...)`. For that you need the `local_store` module object in scope. Step 2b imports specific names via `from local_store import (...)` but does not bind `local_store` itself. Add a module import at the top of the Step 2b try-block. Change the existing import block (lines 599–602) to also bind the module:

```python
        import local_store
        from local_store import (
            _get_conn, ensure_project, start_session, get_project_context,
            get_cached_traces, get_trigger_effectiveness,
        )
```

- [ ] Edit `/tmp/ct-skill/hooks/session_start.py` — after the `_compiled_drop` block (after line 703's closing `except Exception: pass`, before the `output = {` at line 705), append the recap to `additional_context`:

```python
    # Append the savings recap line last (quiet, single line, opt-outable).
    if savings_recap:
        additional_context += "\n\n" + savings_recap
```

### Step 4: Run the test — expect PASS (suite + import)

- [ ] Confirm the module still imports cleanly and the whole suite is green:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)" && PYTHONPATH=tests:hooks python3 -c "import session_start; print('import-ok')"
```
Expected: prints `import-ok` (no `ImportError`/`SyntaxError`).

- [ ] Run the focused class and the onboarding suite (covers `session_start` heavily) to confirm no regression:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_savings_ledger.TestSessionStartRecap tests.test_onboarding -v
```
Expected: `OK` — recap composition tests pass and all existing onboarding tests still pass.

### Step 5: Commit

- [ ] Commit:
```
cd /tmp/ct-skill && git add hooks/session_start.py tests/test_savings_ledger.py && git commit -m "feat(session_start): quiet inbound savings recap line

Builds 'CommonTrace: saved you ~Xm ~\$Y since last session · lifetime ...' from
local rollups inside Step 2b (conn open), opt-out via config savings_recap,
appended last to additionalContext. Silent when zero. Measured tokens x price.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7 — `artifacts.py`: savings in `recap` + `savings` subcommand

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py:308` (`compiled_recap` — add this-month savings line before `return`), `:382` (`main` — add `savings` subcommand + update Usage at 422–423)
- Test: `/tmp/ct-skill/tests/test_artifacts.py` (append `TestCompiledRecapSavings` and a CLI savings test)

Add a this-month savings line to `compiled_recap` (reusing its `start, end` month bounds) and a `savings` subcommand that prints the lifetime view. Update the Usage string to list `savings`.

### Step 1: Write the failing test

- [ ] Append these two classes to `/tmp/ct-skill/tests/test_artifacts.py` (after `TestWriteArtifactAndCLI`, before the `if __name__` block). They reuse the file's existing imports (`contextlib`, `io`, `time`, `artifacts`, `local_store`, `HookTestCase`, `DAY`):

```python
class TestCompiledRecapSavings(HookTestCase):
    def _seed_month_session(self, conn, pid, year=2026, month=5):
        start, _ = artifacts.month_range(year, month)
        mid = start + 10 * DAY
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at, error_count, "
            "resolution_count, contribution_count, top_pattern) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s1", pid, mid, 5, 2, 0, "error_resolution"))
        conn.commit()
        return mid

    def test_recap_shows_savings_line_when_present(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        mid = self._seed_month_session(conn, pid)
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "s1", "measured_recurrence", 90.0, 2_000_000, mid))
        conn.commit()
        text = artifacts.compiled_recap(conn, 2026, 5)
        self.assertIn("the commons saved you ~1.5h / ~$6.0 this month", text)

    def test_recap_omits_savings_line_when_zero(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        self._seed_month_session(conn, pid)  # session but no savings_events
        text = artifacts.compiled_recap(conn, 2026, 5)
        self.assertNotIn("the commons saved you", text)

    def test_savings_outside_month_not_counted(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        self._seed_month_session(conn, pid)
        other, _ = artifacts.month_range(2026, 3)  # different month
        conn.execute(
            "INSERT INTO savings_events (project_id, session_id, event_type, "
            "minutes_saved, tokens_saved, created_at) VALUES (?,?,?,?,?,?)",
            (pid, "s1", "measured_recurrence", 90.0, 2_000_000,
             other + 5 * DAY))
        conn.commit()
        text = artifacts.compiled_recap(conn, 2026, 5)
        self.assertNotIn("the commons saved you", text)


class TestCLISavings(HookTestCase):
    def test_cli_savings_prints_lifetime(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/p")
        local_store.book_session_saving(conn, pid, "s1", 90.0, 2_000_000)
        conn.close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "savings"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("~1.5h", out)
        self.assertIn("~$6.0", out)

    def test_cli_savings_empty_is_clean(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "savings"])
        self.assertEqual(rc, 0)

    def test_cli_usage_string_lists_savings(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "bogus"])
        self.assertEqual(rc, 1)
        self.assertIn("savings", buf.getvalue())
```

### Step 2: Run the test — expect FAIL

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_artifacts.TestCompiledRecapSavings tests.test_artifacts.TestCLISavings -v
```
Expected: failures — `TestCompiledRecapSavings::test_recap_shows_savings_line_when_present` fails (`'the commons saved you ...' not found`); `TestCLISavings::test_cli_savings_prints_lifetime` fails because the `savings` command is unknown and returns `1` (and prints the old Usage line, so `test_cli_usage_string_lists_savings` also fails — the word `savings` is not yet in the Usage string).

### Step 3: Write the minimal implementation

- [ ] Edit `/tmp/ct-skill/hooks/artifacts.py` `compiled_recap` — insert the savings line just before `lines.append("")` at line 363 (the blank-line separator before the footer). Reuse the `start, end` already computed at line 314:

```python
    sav = conn.execute(
        "SELECT COALESCE(SUM(minutes_saved), 0), "
        "COALESCE(SUM(tokens_saved), 0) FROM savings_events "
        "WHERE created_at BETWEEN ? AND ?", (start, end)).fetchone()
    if sav and (sav[0] > 0 or sav[1] > 0):
        from savings import money_usd, _hm
        lines.append(
            f"  the commons saved you ~{_hm(sav[0])} / ~${money_usd(sav[1])} "
            f"this month")
```

- [ ] Edit `/tmp/ct-skill/hooks/artifacts.py` `main` — add the `savings` subcommand. Insert it after the `recap` block ends (after line 421's `return 0`) and before the unknown-command print at line 422:

```python
        if cmd == "savings":
            from savings import money_usd, _hm
            from local_store import savings_totals
            totals = savings_totals(conn)
            if totals["events"] == 0:
                print("No savings recorded yet — keep using CommonTrace.")
                return 0
            print("CommonTrace savings (lifetime, inbound)")
            print(f"  time saved   : ~{_hm(totals['minutes'])}")
            print(f"  money saved  : ~${money_usd(totals['tokens'])}")
            print(f"  events       : {totals['events']}")
            print("  Measured from your own resolutions, on your machine. "
                  "— commontrace.org")
            return 0
```

- [ ] Edit `/tmp/ct-skill/hooks/artifacts.py` line 422–423 — update the Usage string to list `savings`:

```python
        print(f"Unknown command: {cmd}. "
              f"Usage: artifacts.py [brain|recap [YYYY-MM]|savings]")
```

### Step 4: Run the test — expect PASS

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_artifacts.TestCompiledRecapSavings tests.test_artifacts.TestCLISavings -v
```
Expected: `OK` — all 3 `TestCompiledRecapSavings` + 3 `TestCLISavings` tests pass.

- [ ] Run the full `test_artifacts` module to confirm no regression to the existing recap/CLI tests (the new savings line must not break `test_recap_contains_own_numbers`, which has no savings rows and therefore must not show the savings line):
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest tests.test_artifacts -v
```
Expected: `OK` — all `test_artifacts` tests pass.

### Step 5: Commit

- [ ] Syntax-check then commit:
```
cd /tmp/ct-skill && python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)" && git add hooks/artifacts.py tests/test_artifacts.py && git commit -m "feat(artifacts): savings line in recap + 'savings' subcommand

compiled_recap appends a this-month 'the commons saved you ~Xh / ~\$Y' line
(reusing the month bounds); main gains a 'savings' lifetime view and the Usage
string lists it. Measured tokens x published price. No LLM, local-only.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8 — Full-suite green + final integration commit

**Files:**
- Test: all of `/tmp/ct-skill/tests/`

Final gate: run the entire suite, confirm every new and pre-existing test is green, and confirm all five modified hook files still byte-compile.

### Step 1: Run the full suite

- [ ] Run:
```
cd /tmp/ct-skill && PYTHONPATH=tests:hooks python3 -m unittest discover -s tests -v 2>&1 | tail -25
```
Expected: `OK` with the total count raised from the pre-change baseline of **119** by the new tests: `TestSumUsage`(7) + `TestMoney`(6) + `TestHm`(3) + `TestRecapLine`(5) = 21 in `test_savings`; `TestSavingsSchema`(5) + `TestLedgerHelpers`(10) + `TestTokensInMetadata`(3) + `TestBookSavings`(5) + `TestSessionStartRecap`(3) = 26 in `test_savings_ledger`; `TestCompiledRecapSavings`(3) + `TestCLISavings`(3) = 6 added to `test_artifacts` — i.e. **119 + 53 = 172 tests**, all passing. (If Task 2 required updating the one `test_local_store_v3` assertion from `3` to `4`, the count is unchanged by that edit.)

### Step 2: Byte-compile every touched hook

- [ ] Run:
```
cd /tmp/ct-skill && for f in savings local_store stop session_start artifacts; do python3 -c "import py_compile; py_compile.compile('hooks/$f.py', doraise=True)" && echo "$f OK"; done
```
Expected: five `OK` lines (`savings OK`, `local_store OK`, `stop OK`, `session_start OK`, `artifacts OK`).

### Step 3: Confirm the working tree is clean (everything already committed)

- [ ] Run:
```
cd /tmp/ct-skill && git status --short
```
Expected: empty output (Tasks 1–7 each committed their own files; nothing should remain unstaged). If anything remains, it is a stray artifact — investigate before proceeding.

### Step 4: (No new code) — verification-only task

- [ ] This task writes no code. It exists to enforce the green-suite gate before the plan is considered done. If Step 1 is not `OK`, return to the failing task and fix it under TDD (write/repair the failing test first), then re-run.

### Step 5: Tag the integration point (optional, only if the team tags milestones)

- [ ] If and only if the repo convention is to tag feature completion (check `git tag --list | tail`), create a lightweight checkpoint; otherwise skip:
```
cd /tmp/ct-skill && git log --oneline -7
```
Expected: the seven feature commits (savings helpers, schema v4, ledger helpers, stop instrument, stop booking, session-start recap, artifacts) visible at the top of the log. No tag is required by this plan.

---

## Self-Review

### (a) Spec-coverage checklist (skill scope = spec phases 1–3, measured inbound only)

| Spec requirement (skill scope) | Where covered |
|---|---|
| **Phase 1 — Token instrument**: read `transcript_path`, sum `message.usage` (input+output+cache) over a time window | `savings.sum_usage` (Task 1); used in `_build_candidate` (Task 4) and `_book_savings` (Task 5) |
| **Phase 1** — record `tokens_to_resolution` in contribution `metadata_json` alongside effort fields | Task 4 — appended to `metadata_parts` (hint) and `metadata_json` (after `user_emphasis`) |
| **Phase 1** — measured count rides with the trace (so cross-user proxy is real later) | Task 4 — `tokens_to_resolution` placed in `metadata_json`; the server plan consumes it (deferred) |
| **Phase 1** — legacy fallback `(error_count + iteration_count) × TOKENS_PER_TURN_EST`, conservative, never inflates | Task 4 — fallback when `tokens_to_resolution <= 0`; `TOKENS_PER_TURN_EST = 1500` in `savings.py` (Task 1) |
| **Phase 1** — transcript unreadable / `usage` absent → skip, never crash | `sum_usage` returns 0 on any failure, never raises (Task 1; tests `test_missing_file_returns_zero`, `test_bad_json_lines_skipped_not_raised`, `test_non_int_usage_values_ignored`) |
| **Phase 2 — `savings_events` table** (id, project_id, session_id, event_type, minutes_saved, tokens_saved, source_label, trace_id, signature, created_at) + schema bump + migration | Task 2 — `_SCHEMA` + `_migrate_to_v4` (additive), `CURRENT_SCHEMA_VERSION = 4` |
| **Phase 2 — lifetime rollup read helpers** | Task 3 — `savings_totals` (with optional `since`); `prev_session_started_at` |
| **Phase 2 — booking logic** at the resolution / error-time-injection site (measured-recurrence) | Task 5 — `_book_savings` wired into `main()` after `_persist_session` |
| **Phase 2 — measured-recurrence model**: `resolved_at − created_at` capped 120 min/event; measured tokens over the window | Task 5 — `minutes = sum(min(max(resolved-created,0)/60, 120))`; `tokens = sum_usage(window)` |
| **Phase 2 — pre-emption only on observable use** (recurrence re-hit with attributed trace) | Task 5 — query filters `trace_id IS NOT NULL AND resolved_at IS NOT NULL` within the session window; pure session-start impressions never book |
| **Phase 2 — money = tokens × canonical published price**, config-overridable | `savings.money_usd`, `DEFAULT_PRICE_PER_MTOK = 3.0`, `price_per_mtok` override (Task 1) |
| **Phase 2 — caps/floors/guards**: per-event 120-min cap, token `TOKEN_CAP`, one booking per `(session, signature/trace)` | 120-min cap (Task 5); `TOKEN_CAP = 2_000_000` in `sum_usage` (Task 1); `UNIQUE(session_id, event_type, signature)` + `book_session_saving` INSERT OR IGNORE (Tasks 2–3) |
| **Phase 2** — same signature in a *different* session counts again | `book_session_saving` keyed by `session_id`; test `test_book_different_session_counts_again` (Task 3) |
| **Phase 3 — session-start recap** `CommonTrace: saved you ~Xh ~$Y since last session · lifetime ~Ah/$B`; silent when zero; opt-out `savings_recap` | Task 6 — `format_recap_line` (Task 1) wired in Step 2b; gate `config.get("savings_recap", True)` |
| **Phase 3 — on-demand breakdown** in `artifacts.py recap` (this-month) + a savings view | Task 7 — savings line in `compiled_recap`; `savings` subcommand for the lifetime view |
| **Core constraint — NO LLM**: every number is a measured token count or a published price constant | Stated in Architecture + the dedicated NO-LLM paragraph; enforced in `savings.py` (no SDK import), `_build_candidate`, `_book_savings`, `compiled_recap` |
| **Privacy** — recap writes nothing to git; no identity leaves the machine | All new surfaces are local-only; no network call added in any task |
| **Error handling** — never crash a hook | `sum_usage` never raises; `_book_savings` wrapped end-to-end; `_persist_session`-style guards mirrored |

**Explicitly deferred to the server plan (NOT in this plan, by instruction):** estimated/cross-user proxy savings (spec "Estimated" source row, `tokens_to_resolution × retrieval_count`); the outbound "your traces saved others ~Ch/$D" recap clause; the anonymized `POST /telemetry/savings` increment and `savings_ledger`; `GET /analytics/savings`; the frontend counter. `format_recap_line` is deliberately inbound-only (test `test_delta_and_lifetime` asserts `"saved others"` is absent), and the server consumes the `tokens_to_resolution` that Task 4 plants.

### (b) Placeholder scan

No banned tokens appear in any task body: no "TBD", "TODO", "implement later", "add error handling", "add validation", "handle edge cases", "write tests for the above", or "similar to Task N". Every code step shows complete code; every test step gives the exact command and the expected FAIL/PASS message. Error handling is shown concretely (the `try/except`-wrapped `_book_savings`, the never-raises `sum_usage`, the `INSERT OR IGNORE` guard), not deferred to a placeholder. The single conditional edit (Task 2 Step 4 / `test_local_store_v3` assertion `3`→`4`) is stated as an exact, bounded one-line change with the precise condition under which it applies.

### (c) Type / name consistency check

Every symbol referenced in a later task is defined earlier with a matching name and signature:
- `savings.DEFAULT_PRICE_PER_MTOK`, `TOKEN_CAP`, `TOKENS_PER_TURN_EST`, `_USAGE_KEYS` — defined Task 1; used Tasks 4, 5, 7.
- `savings._epoch(ts: str) -> float` — Task 1; used in `test_savings` and inside `sum_usage`.
- `savings.sum_usage(transcript_path: str, start_t: float, end_t: float) -> int` — Task 1; called in `_build_candidate` (Task 4) and `_book_savings` (Task 5).
- `savings.money_usd(tokens: int, price_per_mtok=None) -> float` — Task 1; used Tasks 1, 7.
- `savings._hm(minutes: float) -> str` — Task 1; used Tasks 1, 7.
- `savings.format_recap_line(life: dict, delta: dict = None, price_per_mtok=None) -> str` — Task 1; used Task 6.
- `local_store.CURRENT_SCHEMA_VERSION == 4`, `_migrate_to_v4(conn)`, `savings_events` table — Task 2; relied on by Tasks 3, 5, 7.
- `local_store.book_session_saving(conn, project_id, session_id, minutes, tokens, event_type="measured_recurrence", source_label="measured", trace_id=None) -> bool` — Task 3; called in `_book_savings` (Task 5) and tests.
- `local_store.savings_totals(conn, since=None) -> dict` returning `{"minutes": float, "tokens": int, "events": int}` — Task 3; used Tasks 6, 7.
- `local_store.prev_session_started_at(conn, current_session_id) -> float | None` — Task 3; used Task 6.
- `stop._build_candidate(score, top_pattern, evidence, state_dir, transcript_path="") -> dict` — signature changed Task 4; call site updated same task; metadata key `tokens_to_resolution` consumed by tests.
- `stop._book_savings(data, state_dir) -> None` — Task 5; wired in `main()` same task.
- `artifacts.compiled_recap(conn, year, month)` savings line + `artifacts.main(argv)` `savings` branch — Task 7.
- All tests use `from base import HookTestCase, append_event` and `import local_store` / `import savings` / `import stop` / `import artifacts`, matching the established `tests/base.py` seam (which inserts `hooks/` on `sys.path`). The `read_events`/`append_event` event dicts carry `"t"`; the transcript fixture lines carry top-level `"timestamp"` + `message.usage` — both confirmed against `session_state.py` and the transcript-JSONL contract.

Units are consistent throughout: `minutes_saved` is REAL minutes, `tokens_saved` is an INT token count, `created_at`/`started_at`/`resolved_at` are `time.time()` epoch floats, and transcript timestamps are ISO-8601 converted via `_epoch` to the same epoch scale (so window comparisons are valid).

### (d) Decisions flagged for the user

1. **`DEFAULT_PRICE_PER_MTOK = 3.0` is a placeholder blended price — CONFIRM BEFORE RELEASE.** The locked design and spec both call for "one canonical published `$/Mtok`." `3.0` is a stand-in blended rate (input+output+cache mixed). Before shipping, confirm the exact published constant to use (and whether a single blended number is acceptable, or whether distinct input/output/cache rates are wanted — the current `sum_usage` collapses all four usage keys into one token total, which only supports a single blended price). It is overridable via the config key `price_per_mtok`, so a per-user override path exists regardless.
2. **`test_local_store_v3.py::test_v2_db_dedupes_into_seen_counts` asserts `user_version == 3`.** After the v4 bump, a DB stamped at v2 migrates through to **4**. Task 2 Step 4 instructs updating that one assertion from `3` to `4` (the dedupe behavior under test is unchanged). Flagging because it edits a pre-existing test file outside the new feature's own tests.
3. **Recap config is loaded twice in `session_start.main()` after this change** — once as `cfg = load_config()` inside Step 2b (needed because the recap is built while the conn is open, before the existing `config = load_config()` at line 667), and once at line 667. `load_config()` is a cheap, idempotent file read, so this is harmless, but it is a deliberate minor duplication worth noting (an alternative would be to hoist the existing `load_config()` above Step 2b; I kept the existing call site untouched to minimize blast radius).
4. **`_book_savings` credits a saving whenever a trace-attributed signature resolved within the session window**, including a first-time resolution that happened to be trace-assisted (not only a literal recurrence re-hit). This matches the spec's "observable use" rule (a surfaced trace the agent consumed → credited) and the existing `record_resolution` attribution model, but it is slightly broader than the narrowest reading of "demonstrably recurs." Flagging so the user can confirm this is the intended booking trigger; tightening to `seen_count > 1` would be a one-line `AND seen_count > 1` addition to the query if a stricter recurrence-only credit is preferred.
