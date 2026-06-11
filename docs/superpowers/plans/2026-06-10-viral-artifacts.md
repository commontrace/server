# Viral Artifacts (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the five Phase-1 viral artifacts from spec §5 — brain graph, struggle grid, Resolved-with trailer, README badge, monthly Compiled recap — all generated locally from `local.db` v3, working at N=1 users.

**Architecture:** One new module `hooks/artifacts.py` holds all pure rendering/derivation logic (no network, no LLM, stdlib only) plus a tiny CLI. Three thin integration points wire it into the existing hook pipeline: `stop.py` emits the struggle grid when a trace is contributed, `post_tool_use.py` suggests the Resolved-with trailer when a commons trace contributed to a fix, and `session_start.py` drops the monthly Compiled recap on the first session of each month. A new `/trace brain` command renders the brain graph on demand.

**Tech Stack:** Python 3 stdlib only (sqlite3, math, calendar, time, xml for test validation). Tests: stdlib `unittest`, run via `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`.

---

## Context for the implementer

**Repo:** `/tmp/ct-skill` (clone of public GitHub `commontrace/skill`), branch `main` at `574dfc4` (skill v0.3.0, Plan A shipped). Work directly on `main` (Plan A precedent); push only after the final review passes.

**Hard constraints (founder requirements — violations are plan failures):**

1. **No LLM API calls.** All intelligence is structural. `artifacts.py` makes **zero network calls** of any kind.
2. **Aggregate shapes only.** No code, no prompts, no repo names, no error text, no file names, no filesystem paths may appear in ANY artifact — including local-only HTML (screenshots travel). Artifacts carry only: counts, timestamps/derived numbers, language/framework labels, and trace IDs.
3. **H9 permissions:** artifact directory `0o700`, artifact files `0o600`.
4. **Trailer is a disclosure register** — citation, not co-authorship. Informational suggestion to the agent, never imperative, never auto-applied. Opt-out config key, with the opt-out line surfaced exactly once ever.
5. **Compiled recap is the user's own numbers** — never AI interpretation, no identity claims.
6. **No leaderboards, no streaks** (streaks-with-auto-freeze is Phase 2; not here).
7. Hooks must never crash the session: every integration point wraps in `try/except` and degrades to a no-op.

**Out of scope (documented Phase-2 dependencies — do NOT build):**

- The `https://commontrace.org/t/<trace_id>` route does not exist on the frontend yet (frontend renders only seed traces at `/trace/<slug>/`). Plan B emits the canonical `/t/<trace_id>` URL per spec; links 404 until the frontend ships that route. Accepted.
- Hosted share page (URL-payload decode) and live hosted badge endpoint — frontend/backend work, Phase 2.
- Spec §5 artifacts 4 (plaques/genealogy) and 5 (auto-kudos) — Phase 2/3.

**local.db v3 schema (exact, from `hooks/local_store.py` `_SCHEMA`) — what tests may seed directly:**

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    started_at REAL NOT NULL,
    ended_at REAL,
    error_count INTEGER DEFAULT 0,
    resolution_count INTEGER DEFAULT 0,
    contribution_count INTEGER DEFAULT 0,
    top_pattern TEXT,
    importance_score REAL DEFAULT 0.0
);
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
CREATE TABLE IF NOT EXISTS trigger_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    trigger_name TEXT NOT NULL,
    triggered_at REAL NOT NULL,
    trace_consumed_id TEXT,
    consumed_at REAL
);
```

**Key facts:**

- `local_store._get_conn()` returns a connection with `sqlite3.Row` row factory — code accesses columns by name (`row["seen_count"]`).
- `local_store.ensure_project(conn, cwd, language=None, framework=None) -> int` registers a project and returns its id.
- `session_state.append_event(state_dir, filename, payload)` setdefaults a `"t"` timestamp; an explicit `"t"` in the payload is preserved.
- `tests/base.py` `HookTestCase` patches `local_store.DB_PATH`, `post_tool_use.COOLDOWN_DIR`, `post_tool_use.CONFIG_FILE` to a temp dir and pops `COMMONTRACE_API_KEY` (offline guarantee). It provides `self.tmp_path`, `self.state_dir`, `get_conn()`, `write_project_bridge(conn)`.
- `somatic_intensity` and `memory_temperature` exist **only server-side**. This plan derives local proxies (Task 1) — that is intentional, not a gap.
- The injection trigger recorded by `_check_error_recurrence` is named `error_recurrence` (post_tool_use.py:545) — the Compiled recap's "killed by memory" count queries that name.
- Hook stdout contracts: PostToolUse and SessionStart hooks emit `{"hookSpecificOutput": {"hookEventName": "<Name>", "additionalContext": "..."}}`. Stop hooks may emit `{"systemMessage": "..."}` (a common field across hook types; harmless no-op on clients that ignore it).
- 30 existing tests must stay green throughout. Expected end state: ~71 tests (30 existing + ~41 new; exact count may drift by one or two — the invariant is all green).
- Syntax-check before every commit: `python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"` (adjust filename per task).

---

### Task 1: artifacts.py foundations — temperature/intensity proxies + month_range, test scaffold

**Files:**
- Create: `/tmp/ct-skill/hooks/artifacts.py`
- Create: `/tmp/ct-skill/tests/test_artifacts.py`
- Modify: `/tmp/ct-skill/tests/base.py`

- [ ] **Step 1: Write the failing tests**

Create `/tmp/ct-skill/tests/test_artifacts.py`:

```python
"""Tests for hooks/artifacts.py — local-first viral artifacts.

Pure-function tests use fixed timestamps (no wall-clock dependence).
DB-backed tests use HookTestCase isolation. Privacy tests seed worst-case
PII and assert none of it reaches any artifact.
"""

import contextlib
import io
import json
import time
import unittest
import xml.etree.ElementTree

from base import HookTestCase

import artifacts
import local_store

DAY = 86400.0


def seed_sensitive_project(conn):
    """Worst-case PII rows: tests assert none of this text reaches artifacts."""
    pid = local_store.ensure_project(
        conn, "/home/secretuser/topsecret-repo",
        language="python", framework="fastapi")
    now = time.time()
    conn.execute(
        "INSERT INTO error_signatures (project_id, signature, created_at, "
        "last_seen_at, seen_count, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "ModuleNotFoundError: secret_module in /home/secretuser/app.py",
         now - 3 * DAY, now - DAY, 3, now - DAY))
    conn.execute(
        "INSERT INTO error_signatures (project_id, signature, created_at, "
        "last_seen_at, seen_count, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "TypeError: secret_func() broke in /home/secretuser/lib.py",
         now - 100 * DAY, now - 95 * DAY, 1, None))
    conn.commit()
    return pid


class TestTemperature(unittest.TestCase):
    def test_hot_warm_cool_cold_frozen_bounds(self):
        now = 1_750_000_000.0
        self.assertEqual(artifacts.temperature(now - 1 * DAY, now), "hot")
        self.assertEqual(artifacts.temperature(now - 8 * DAY, now), "warm")
        self.assertEqual(artifacts.temperature(now - 31 * DAY, now), "cool")
        self.assertEqual(artifacts.temperature(now - 91 * DAY, now), "cold")
        self.assertEqual(artifacts.temperature(now - 181 * DAY, now), "frozen")

    def test_future_timestamp_clamps_to_hot(self):
        now = 1_750_000_000.0
        self.assertEqual(artifacts.temperature(now + DAY, now), "hot")


class TestIntensity(unittest.TestCase):
    def test_single_hit_instant_fix_is_base(self):
        t = 1_750_000_000.0
        self.assertEqual(artifacts.intensity(1, t, t), 0.25)

    def test_repeats_raise_intensity(self):
        t = 1_750_000_000.0
        self.assertEqual(artifacts.intensity(3, t, t), 0.55)

    def test_repeat_contribution_caps_at_four(self):
        t = 1_750_000_000.0
        self.assertEqual(artifacts.intensity(99, t, t), 0.85)

    def test_long_fight_caps_at_one(self):
        t = 1_750_000_000.0
        self.assertEqual(artifacts.intensity(99, t, t + 30 * DAY), 1.0)

    def test_unresolved_has_no_latency_term(self):
        t = 1_750_000_000.0
        self.assertEqual(artifacts.intensity(1, t, None), 0.25)


class TestMonthRange(unittest.TestCase):
    def test_range_covers_whole_month(self):
        start, end = artifacts.month_range(2026, 5)
        self.assertEqual(time.localtime(start)[:5], (2026, 5, 1, 0, 0))
        self.assertEqual(time.localtime(end)[:4], (2026, 5, 31, 23))

    def test_february_leap_year(self):
        start, end = artifacts.month_range(2024, 2)
        self.assertEqual(time.localtime(end)[:3], (2024, 2, 29))
```

(`contextlib`, `io`, `json`, `xml.etree.ElementTree`, `seed_sensitive_project`, and `HookTestCase` are used by tests added in Tasks 3–6 — leave the imports and helper in place now.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'artifacts'`

- [ ] **Step 3: Write the implementation**

Create `/tmp/ct-skill/hooks/artifacts.py`:

```python
"""Local-first viral artifacts: brain graph, struggle grid, monthly recap.

Everything here renders from local.db v3 — no network, no LLM calls, and
no text from the database ever reaches an artifact: only counts,
timestamps-derived numbers, language/framework labels, and trace IDs.
Share artifacts are aggregate shapes.

Server-side somatic_intensity / memory_temperature do not exist locally,
so this module derives local proxies from error_signatures:
- intensity: repeat-count + resolution latency (how hard the fight was)
- temperature: recency of last_seen_at (hot → frozen)
"""

import calendar
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ARTIFACTS_DIR = Path.home() / ".commontrace" / "artifacts"
TRACE_URL = "https://commontrace.org/t/{}"

_TEMP_BOUNDS = [(7, "hot"), (30, "warm"), (90, "cool"), (180, "cold")]
TEMP_COLORS = {"hot": "#e25822", "warm": "#e8a33d", "cool": "#4f86c6",
               "cold": "#7a8b99", "frozen": "#b9c4cc"}


def temperature(last_seen_at, now=None):
    """Memory temperature from recency — local proxy for the server's
    activity-based temperature."""
    now = now if now is not None else time.time()
    age_days = max(0.0, (now - last_seen_at) / 86400)
    for bound, label in _TEMP_BOUNDS:
        if age_days < bound:
            return label
    return "frozen"


def intensity(seen_count, created_at, resolved_at):
    """Somatic-intensity proxy: how hard this knowledge was won.

    0.25 base + up to 0.6 for repeat encounters + up to 0.3 for a fight
    that took days to resolve. Capped at 1.0.
    """
    base = 0.25
    repeat = 0.15 * max(0, min(seen_count - 1, 4))
    latency = 0.0
    if resolved_at and resolved_at > created_at:
        latency_days = (resolved_at - created_at) / 86400
        latency = 0.3 * min(latency_days, 7.0) / 7.0
    return round(min(1.0, base + repeat + latency), 3)


def month_range(year, month):
    """(start, end) epoch seconds covering a local-time calendar month."""
    start = time.mktime((year, month, 1, 0, 0, 0, 0, 0, -1))
    last_day = calendar.monthrange(year, month)[1]
    end = time.mktime((year, month, last_day, 23, 59, 59, 0, 0, -1))
    return start, end
```

(`math` and `os` are used by Tasks 4 and 6 in this same file — leave the imports in place now.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 9 tests PASS

- [ ] **Step 5: Wire artifacts into the test isolation scaffold**

Modify `/tmp/ct-skill/tests/base.py`. Change the docstring line:

```python
Patches the module-level path constants in local_store and post_tool_use
```

to:

```python
Patches the module-level path constants in artifacts, local_store, and
post_tool_use
```

Change the import block:

```python
import local_store  # noqa: E402
import post_tool_use  # noqa: E402
```

to:

```python
import artifacts  # noqa: E402
import local_store  # noqa: E402
import post_tool_use  # noqa: E402
```

Change the patch list:

```python
        for target, attr, value in [
            (local_store, "DB_PATH", self.tmp_path / "local.db"),
            (post_tool_use, "COOLDOWN_DIR", self.tmp_path / "cooldowns"),
            (post_tool_use, "CONFIG_FILE", self.tmp_path / "no-config.json"),
        ]:
```

to:

```python
        for target, attr, value in [
            (artifacts, "ARTIFACTS_DIR", self.tmp_path / "artifacts"),
            (local_store, "DB_PATH", self.tmp_path / "local.db"),
            (post_tool_use, "COOLDOWN_DIR", self.tmp_path / "cooldowns"),
            (post_tool_use, "CONFIG_FILE", self.tmp_path / "no-config.json"),
        ]:
```

- [ ] **Step 6: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 39 tests PASS (30 existing + 9 new)

- [ ] **Step 7: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py tests/base.py
git commit -m "feat: artifacts foundations — temperature/intensity proxies + month_range"
```

---

### Task 2: Struggle grid + share line

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py` (append)
- Modify: `/tmp/ct-skill/tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_artifacts.py`:

```python
class TestStruggleGrid(unittest.TestCase):
    def test_empty_session_resolved_is_single_green(self):
        self.assertEqual(artifacts.struggle_grid([], [], resolved=True), "🟩")

    def test_empty_session_unresolved_is_single_idle(self):
        self.assertEqual(artifacts.struggle_grid([], [], resolved=False), "⬜")

    def test_grid_is_ten_cells_and_ends_green_when_resolved(self):
        t0 = 1_750_000_000.0
        errors = [t0, t0 + 60, t0 + 120]
        changes = [t0 + 300, t0 + 600]
        grid = artifacts.struggle_grid(errors, changes, resolved=True)
        cells = list(grid)
        self.assertEqual(len(cells), 10)
        self.assertEqual(cells[-1], "🟩")
        self.assertEqual(cells[0], "🟥")

    def test_error_wins_over_change_in_same_bucket(self):
        t0 = 1_750_000_000.0
        grid = artifacts.struggle_grid([t0, t0 + 1000], [t0 + 1],
                                       resolved=False)
        self.assertEqual(grid[0], "🟥")

    def test_zero_timestamps_filtered(self):
        self.assertEqual(artifacts.struggle_grid([0, 0], [0], resolved=True),
                         "🟩")


class TestStruggleLine(unittest.TestCase):
    def test_line_format_with_trace(self):
        line = artifacts.struggle_line("🟥🟩", 47.4, 8, trace_id="a3f9")
        self.assertEqual(
            line,
            "🟥🟩 47min · 8 errors · solved → https://commontrace.org/t/a3f9")

    def test_singular_error_no_trace(self):
        self.assertEqual(artifacts.struggle_line("🟩", 2, 1),
                         "🟩 2min · 1 error · solved")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 7 new tests ERROR with `AttributeError: module 'artifacts' has no attribute 'struggle_grid'`

- [ ] **Step 3: Write the implementation**

Append to `/tmp/ct-skill/hooks/artifacts.py`:

```python
GRID_CELLS = 10
CELL_ERROR, CELL_WORK, CELL_IDLE, CELL_SOLVED = "🟥", "🟨", "⬜", "🟩"


def struggle_grid(error_ts, change_ts, resolved=True):
    """Wordle-style struggle shape: the session timeline in 10 emoji cells.

    Spoiler-free by construction — built from event timestamps only, never
    from error text or file names. Red = errors, yellow = work, white =
    idle; the last cell turns green when the fight was won.
    """
    stamps = sorted(t for t in list(error_ts) + list(change_ts) if t)
    if not stamps:
        return CELL_SOLVED if resolved else CELL_IDLE
    start = stamps[0]
    span = max(stamps[-1] - start, 1.0)

    def bucket(t):
        return min(int((t - start) / span * GRID_CELLS), GRID_CELLS - 1)

    err_buckets = {bucket(t) for t in error_ts if t}
    chg_buckets = {bucket(t) for t in change_ts if t}
    cells = []
    for i in range(GRID_CELLS):
        if i in err_buckets:
            cells.append(CELL_ERROR)
        elif i in chg_buckets:
            cells.append(CELL_WORK)
        else:
            cells.append(CELL_IDLE)
    if resolved:
        cells[-1] = CELL_SOLVED
    return "".join(cells)


def struggle_line(grid, duration_min, error_count, trace_id=""):
    """The paste-anywhere share line under the grid."""
    duration = int(round(duration_min))
    plural = "s" if error_count != 1 else ""
    line = f"{grid} {duration}min · {error_count} error{plural} · solved"
    if trace_id:
        line += f" → {TRACE_URL.format(trace_id)}"
    return line
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 16 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py
git commit -m "feat: struggle grid + share line renderer"
```

---

### Task 3: Brain graph data loader (numbers and labels only)

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py` (append)
- Modify: `/tmp/ct-skill/tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_artifacts.py` (uses the module-level `seed_sensitive_project` helper from Task 1):

```python
class TestLoadBrainData(HookTestCase):
    def test_counts_and_label(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        data = artifacts.load_brain_data(conn)
        self.assertEqual(data["solved"], 1)
        self.assertEqual(data["open"], 1)
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["label"], "python/fastapi")
        self.assertEqual(len(data["projects"][0]["nodes"]), 2)

    def test_nodes_carry_no_text_from_db(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        blob = json.dumps(artifacts.load_brain_data(conn))
        for leak in ("secretuser", "topsecret", "secret_module",
                     "secret_func", "app.py", "lib.py", "/home"):
            self.assertNotIn(leak, blob)

    def test_node_shape(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        node = artifacts.load_brain_data(conn)["projects"][0]["nodes"][0]
        self.assertEqual(set(node), {"intensity", "temperature", "resolved",
                                     "age_days", "opacity"})

    def test_empty_db(self):
        conn = self.get_conn()
        data = artifacts.load_brain_data(conn)
        self.assertEqual(data["projects"], [])
        self.assertEqual(data["solved"], 0)
        self.assertEqual(data["open"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 4 new tests ERROR with `AttributeError: module 'artifacts' has no attribute 'load_brain_data'`

- [ ] **Step 3: Write the implementation**

Append to `/tmp/ct-skill/hooks/artifacts.py`:

```python
def load_brain_data(conn):
    """Brain-graph dataset. No text leaves the rows: nodes carry only
    numbers; project hubs carry only language/framework labels (never
    paths). Caps: 12 most-recent projects × 60 most-recent signatures."""
    now = time.time()
    projects = []
    solved = 0
    open_count = 0
    rows = conn.execute(
        "SELECT p.id, p.language, p.framework FROM projects p "
        "ORDER BY p.last_seen_at DESC LIMIT 12").fetchall()
    for p in rows:
        label = "/".join(x for x in (p["language"], p["framework"]) if x) \
            or "project"
        sigs = conn.execute(
            "SELECT seen_count, created_at, last_seen_at, resolved_at "
            "FROM error_signatures WHERE project_id = ? "
            "ORDER BY last_seen_at DESC LIMIT 60", (p["id"],)).fetchall()
        nodes = []
        for s in sigs:
            resolved = s["resolved_at"] is not None
            age_days = max(0.0, (now - s["last_seen_at"]) / 86400)
            nodes.append({
                "intensity": intensity(s["seen_count"], s["created_at"],
                                       s["resolved_at"]),
                "temperature": temperature(s["last_seen_at"], now),
                "resolved": resolved,
                "age_days": round(age_days, 1),
                "opacity": round(1.0 - 0.6 * min(age_days / 365.0, 1.0), 2),
            })
            if resolved:
                solved += 1
            else:
                open_count += 1
        if nodes:
            projects.append({"label": label, "nodes": nodes})
    return {"projects": projects, "solved": solved, "open": open_count,
            "now": now}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 20 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py
git commit -m "feat: brain graph data loader (numbers + labels only)"
```

---

### Task 4: Brain SVG / HTML / badge renderers

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py` (append)
- Modify: `/tmp/ct-skill/tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_artifacts.py`:

```python
class TestRenderers(HookTestCase):
    def test_svgs_parse_and_have_no_leaks(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        data = artifacts.load_brain_data(conn)
        for render in (artifacts.render_brain_svg, artifacts.render_badge_svg):
            out = render(data)
            xml.etree.ElementTree.fromstring(out)  # must be well-formed
            for leak in ("secretuser", "topsecret", "secret_module",
                         "app.py", "/home"):
                self.assertNotIn(leak, out)

    def test_html_is_self_contained_and_clean(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        data = artifacts.load_brain_data(conn)
        html = artifacts.render_brain_html(data)
        self.assertIn("<svg", html)
        self.assertIn("My agent's brain", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("src=", html)
        for leak in ("secretuser", "topsecret", "secret_module",
                     "app.py", "/home"):
            self.assertNotIn(leak, html)

    def test_empty_state_svg(self):
        out = artifacts.render_brain_svg(
            {"projects": [], "solved": 0, "open": 0, "now": 0.0})
        xml.etree.ElementTree.fromstring(out)
        self.assertIn("No knowledge captured yet", out)

    def test_badge_shows_solved_count(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        data = artifacts.load_brain_data(conn)
        self.assertIn("1 solved", artifacts.render_badge_svg(data))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 4 new tests ERROR with `AttributeError: module 'artifacts' has no attribute 'render_brain_svg'`

- [ ] **Step 3: Write the implementation**

Append to `/tmp/ct-skill/hooks/artifacts.py`:

```python
GOLDEN_ANGLE = 2.399963229728653


def _node_positions(n, cx, cy, spread):
    """Golden-angle spiral: organic, deterministic, no collisions at small n."""
    positions = []
    for i in range(n):
        r = spread * math.sqrt(i + 1)
        a = i * GOLDEN_ANGLE
        positions.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return positions


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_brain_svg(data, width=760, height=520):
    """Brain graph: one hub per project, error-signature nodes on a
    golden-angle spiral around it. Node size = intensity, color =
    temperature, fade = decay; resolved nodes are filled, open nodes
    hollow. Only numbers and language/framework labels are rendered.
    Hub orbits can overlap at high project counts — accepted as organic."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" fill="#fcfcf9"/>',
    ]
    projects = data.get("projects", [])
    if not projects:
        parts.append(
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" '
            f'font-family="Georgia, serif" font-size="16" fill="#777">'
            f'No knowledge captured yet — keep coding.</text>')
        parts.append("</svg>")
        return "".join(parts)
    n = len(projects)
    orbit = min(width, height) * 0.30 if n > 1 else 0.0
    for j, project in enumerate(projects):
        angle = j * (2 * math.pi / n) - math.pi / 2
        hx = width / 2 + orbit * math.cos(angle)
        hy = height / 2 + orbit * math.sin(angle)
        nodes = project["nodes"]
        positions = _node_positions(len(nodes), hx, hy, 11.0)
        for node, (x, y) in zip(nodes, positions):
            color = TEMP_COLORS[node["temperature"]]
            radius = 3.0 + 8.0 * node["intensity"]
            if node["resolved"]:
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
                    f'fill="{color}" opacity="{node["opacity"]}"/>')
            else:
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
                    f'fill="none" stroke="{color}" stroke-width="1.5" '
                    f'opacity="{node["opacity"]}"/>')
        label_y = hy + 11.0 * math.sqrt(len(nodes) + 1) + 18
        parts.append(
            f'<text x="{hx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
            f'font-family="Georgia, serif" font-size="13" fill="#444">'
            f'{_esc(project["label"])}</text>')
    stats = (f'{data["solved"]} solved · {data["open"]} open · '
             f'{n} project{"s" if n != 1 else ""}')
    parts.append(
        f'<text x="{width / 2}" y="{height - 16}" text-anchor="middle" '
        f'font-family="Georgia, serif" font-size="13" fill="#555">'
        f'{_esc(stats)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_brain_html(data):
    """Self-contained share page: inline SVG, inline styles, no JS, no
    external assets. Safe to screenshot — aggregate shapes only."""
    svg = render_brain_svg(data)
    date_str = time.strftime(
        "%B %Y", time.localtime(data.get("now") or time.time()))
    legend = "".join(
        f'<span style="white-space:nowrap"><span style="display:inline-block;'
        f'width:10px;height:10px;border-radius:50%;background:{color};'
        f'margin:0 4px 0 12px"></span>{label}</span>'
        for label, color in TEMP_COLORS.items())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My agent's brain — CommonTrace</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; background: #fcfcf9;
         color: #202122; max-width: 820px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-weight: normal; border-bottom: 1px solid #a2a9b1;
       padding-bottom: 0.3rem; }}
  figure {{ margin: 1.5rem 0; }}
  .legend {{ font-size: 0.85rem; color: #555; }}
  footer {{ margin-top: 2rem; font-size: 0.8rem; color: #72777d;
           border-top: 1px solid #eaecf0; padding-top: 0.7rem; }}
</style>
</head>
<body>
<h1>My agent's brain</h1>
<p>Every dot is an error signature my coding agent fought and remembered.
Size is how hard the fight was, color is how recently the knowledge was
used, fade is decay. Filled dots are solved; hollow dots are still open.</p>
<figure>{svg}</figure>
<p class="legend">Temperature:{legend}</p>
<footer>Generated locally by CommonTrace on {date_str} — your agent's
memory, on your machine. Aggregate shapes only: no code, no error text,
no file names ever leave local.db.</footer>
</body>
</html>
"""


def render_badge_svg(data, width=360, height=72):
    """README-embeddable badge: solved count + a dot-strip of the most
    recent nodes (≤20, truncated to fit)."""
    nodes = [n for p in data.get("projects", []) for n in p["nodes"]][:20]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="8" fill="#fcfcf9" stroke="#a2a9b1"/>',
        f'<text x="16" y="28" font-family="Georgia, serif" font-size="14" '
        f'fill="#222">CommonTrace brain</text>',
        f'<text x="{width - 16}" y="28" text-anchor="end" '
        f'font-family="Georgia, serif" font-size="14" font-weight="bold" '
        f'fill="#2e7d32">{data.get("solved", 0)} solved</text>',
    ]
    x = 16.0
    for node in nodes:
        radius = 3.0 + 4.0 * node["intensity"]
        if x + 2 * radius > width - 24:
            break
        color = TEMP_COLORS[node["temperature"]]
        if node["resolved"]:
            parts.append(
                f'<circle cx="{x + radius:.1f}" cy="50" r="{radius:.1f}" '
                f'fill="{color}" opacity="{node["opacity"]}"/>')
        else:
            parts.append(
                f'<circle cx="{x + radius:.1f}" cy="50" r="{radius:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="1.5" '
                f'opacity="{node["opacity"]}"/>')
        x += 2 * radius + 5
    parts.append("</svg>")
    return "".join(parts)
```

Note: nested same-type quotes inside f-strings (e.g. `f'...{node["opacity"]}...'`) use double quotes inside single-quoted f-strings — valid on all supported Python 3 versions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 24 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py
git commit -m "feat: brain SVG/HTML + README badge renderers"
```

---

### Task 5: Monthly Compiled recap query

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py` (append)
- Modify: `/tmp/ct-skill/tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_artifacts.py`:

```python
class TestCompiledRecap(HookTestCase):
    def _seed_month(self, conn, year=2026, month=5):
        pid = local_store.ensure_project(conn, "/test-project")
        start, _ = artifacts.month_range(year, month)
        mid = start + 10 * DAY
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at, error_count, "
            "resolution_count, contribution_count, top_pattern) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s1", pid, mid, 12, 5, 1, "error_resolution"))
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at, error_count, "
            "resolution_count, contribution_count, top_pattern) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s2", pid, mid + DAY, 3, 2, 0, "error_resolution"))
        conn.execute(
            "INSERT INTO error_signatures (project_id, signature, created_at, "
            "last_seen_at, seen_count, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, "sig-a", mid - DAY, mid, 4, mid))
        conn.commit()

    def test_recap_contains_own_numbers(self):
        conn = self.get_conn()
        self._seed_month(conn)
        text = artifacts.compiled_recap(conn, 2026, 5)
        self.assertIn("CommonTrace Compiled — May 2026", text)
        self.assertIn("2 sessions", text)
        self.assertIn("15 errors hit · 7 resolutions", text)
        self.assertIn("1 error signature solved for good", text)
        self.assertIn("hardest fight: one error took 4 hits", text)
        self.assertIn("signature move: error resolution", text)
        self.assertIn("1 trace contributed to the commons", text)

    def test_empty_month_returns_none(self):
        conn = self.get_conn()
        self.assertIsNone(artifacts.compiled_recap(conn, 2026, 4))

    def test_no_text_from_db_in_recap(self):
        conn = self.get_conn()
        self._seed_month(conn)
        text = artifacts.compiled_recap(conn, 2026, 5)
        self.assertNotIn("sig-a", text)
        self.assertNotIn("/test-project", text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 3 new tests ERROR with `AttributeError: module 'artifacts' has no attribute 'compiled_recap'`

- [ ] **Step 3: Write the implementation**

Append to `/tmp/ct-skill/hooks/artifacts.py`:

```python
def compiled_recap(conn, year, month):
    """Monthly Compiled — the user's own numbers, never an interpretation.

    Returns the recap text, or None when the month had no sessions.
    Counts only; no signature text, paths, or titles ever appear here.
    """
    start, end = month_range(year, month)
    sess = conn.execute(
        "SELECT COUNT(*) AS n, SUM(error_count) AS errs, "
        "SUM(resolution_count) AS fixes, "
        "SUM(contribution_count) AS contribs "
        "FROM sessions WHERE started_at BETWEEN ? AND ?",
        (start, end)).fetchone()
    if not sess or not sess["n"]:
        return None
    solved = conn.execute(
        "SELECT COUNT(*) AS n, MAX(seen_count) AS worst "
        "FROM error_signatures WHERE resolved_at BETWEEN ? AND ?",
        (start, end)).fetchone()
    assisted = conn.execute(
        "SELECT COUNT(*) AS n FROM trigger_feedback "
        "WHERE trigger_name = 'error_recurrence' "
        "AND trace_consumed_id IS NOT NULL "
        "AND consumed_at BETWEEN ? AND ?", (start, end)).fetchone()
    top = conn.execute(
        "SELECT top_pattern, COUNT(*) AS n FROM sessions "
        "WHERE started_at BETWEEN ? AND ? AND top_pattern IS NOT NULL "
        "GROUP BY top_pattern ORDER BY n DESC LIMIT 1",
        (start, end)).fetchone()
    label = calendar.month_name[month]
    lines = [
        f"CommonTrace Compiled — {label} {year}",
        "",
        f"  {sess['n']} session{'s' if sess['n'] != 1 else ''}",
        f"  {sess['errs'] or 0} errors hit · {sess['fixes'] or 0} resolutions",
        f"  {solved['n'] or 0} error signature"
        f"{'s' if (solved['n'] or 0) != 1 else ''} solved for good",
    ]
    if assisted and assisted["n"]:
        lines.append(
            f"  {assisted['n']} repeat error"
            f"{'s' if assisted['n'] != 1 else ''} killed by memory — "
            f"knowledge that bit back")
    if solved and solved["worst"] and solved["worst"] > 1:
        lines.append(
            f"  hardest fight: one error took {solved['worst']} hits "
            f"before it fell")
    if top and top["top_pattern"]:
        lines.append(
            f"  signature move: {top['top_pattern'].replace('_', ' ')}")
    if sess["contribs"]:
        lines.append(
            f"  {sess['contribs']} trace{'s' if sess['contribs'] != 1 else ''} "
            f"contributed to the commons")
    lines.append("")
    lines.append("  Your agent's own numbers, from your machine. "
                 "— commontrace.org")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 27 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py
git commit -m "feat: monthly Compiled recap query"
```

---

### Task 6: Artifact writer (H9 perms) + CLI

**Files:**
- Modify: `/tmp/ct-skill/hooks/artifacts.py` (append)
- Modify: `/tmp/ct-skill/tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `/tmp/ct-skill/tests/test_artifacts.py`:

```python
class TestWriteArtifactAndCLI(HookTestCase):
    def test_write_artifact_perms(self):
        path = artifacts.write_artifact("probe.txt", "hello\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")
        self.assertEqual(path.parent, artifacts.ARTIFACTS_DIR)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_cli_brain_writes_three_files(self):
        conn = self.get_conn()
        seed_sensitive_project(conn)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "brain"])
        self.assertEqual(rc, 0)
        for name in ("brain.html", "brain.svg", "badge.svg"):
            self.assertTrue((artifacts.ARTIFACTS_DIR / name).exists())
        self.assertIn("1 solved", buf.getvalue())

    def test_cli_recap_empty_month(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "recap", "2026-04"])
        self.assertEqual(rc, 0)
        self.assertIn("No activity recorded for 2026-04", buf.getvalue())

    def test_cli_unknown_command(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = artifacts.main(["artifacts.py", "bogus"])
        self.assertEqual(rc, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 4 new tests ERROR with `AttributeError: module 'artifacts' has no attribute 'write_artifact'`

- [ ] **Step 3: Write the implementation**

Append to `/tmp/ct-skill/hooks/artifacts.py`:

```python
def write_artifact(name, content):
    """Write an artifact under ARTIFACTS_DIR with H9 perms (0700/0600)."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = ARTIFACTS_DIR / name
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "brain"
    from local_store import _get_conn
    conn = _get_conn()
    try:
        if cmd == "brain":
            data = load_brain_data(conn)
            html = write_artifact("brain.html", render_brain_html(data))
            svg = write_artifact("brain.svg", render_brain_svg(data))
            badge = write_artifact("badge.svg", render_badge_svg(data))
            print(f"brain page  : {html}")
            print(f"brain svg   : {svg}")
            print(f"readme badge: {badge}")
            print(f"{data['solved']} solved · {data['open']} open · "
                  f"{len(data['projects'])} projects")
            return 0
        if cmd == "recap":
            if len(argv) > 2:
                year, month = (int(x) for x in argv[2].split("-"))
            else:
                t = time.localtime()
                year, month = ((t.tm_year, t.tm_mon - 1) if t.tm_mon > 1
                               else (t.tm_year - 1, 12))
            text = compiled_recap(conn, year, month)
            if text:
                print(text)
                return 0
            print(f"No activity recorded for {year}-{month:02d}.")
            return 0
        print(f"Unknown command: {cmd}. "
              f"Usage: artifacts.py [brain|recap [YYYY-MM]]")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_artifacts -v`
Expected: 31 tests PASS

- [ ] **Step 5: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 61 tests PASS (30 existing + 31 new)

- [ ] **Step 6: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/artifacts.py', doraise=True)"
git add hooks/artifacts.py tests/test_artifacts.py
git commit -m "feat: artifacts CLI + 0600/0700 artifact writer"
```

---

### Task 7: Struggle grid on contribution (stop.py)

**Files:**
- Modify: `/tmp/ct-skill/hooks/stop.py`
- Create: `/tmp/ct-skill/tests/test_struggle_artifact.py`

- [ ] **Step 1: Write the failing tests**

Create `/tmp/ct-skill/tests/test_struggle_artifact.py`:

```python
"""Struggle-grid share line emitted by the Stop hook on contribution."""

from base import HookTestCase, append_event

import artifacts
import stop


class TestStruggleArtifact(HookTestCase):
    def _candidate(self):
        return {"metadata_json": {"time_to_resolution_minutes": 47,
                                  "error_count": 8}}

    def test_writes_artifact_and_returns_line(self):
        t0 = 1_750_000_000.0
        for i in range(3):
            append_event(self.state_dir, "errors.jsonl", {"t": t0 + i * 60})
        append_event(self.state_dir, "changes.jsonl", {"t": t0 + 300})
        line = stop._struggle_artifact(self._candidate(), self.state_dir,
                                       "abc123")
        self.assertIn("47min · 8 errors · solved", line)
        self.assertIn("https://commontrace.org/t/abc123", line)
        saved = (artifacts.ARTIFACTS_DIR / "last-struggle.txt").read_text(
            encoding="utf-8")
        self.assertEqual(saved, line + "\n")

    def test_no_trace_id_omits_url(self):
        line = stop._struggle_artifact(self._candidate(), self.state_dir)
        self.assertNotIn("commontrace.org", line)

    def test_never_raises_on_bad_candidate(self):
        self.assertIsNone(stop._struggle_artifact(None, self.state_dir))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_struggle_artifact -v`
Expected: ERROR with `AttributeError: module 'stop' has no attribute '_struggle_artifact'`

- [ ] **Step 3: Add the helper to stop.py**

In `/tmp/ct-skill/hooks/stop.py`, insert this function immediately after the `_append_auto_log` function definition:

```python
def _struggle_artifact(candidate, state_dir, trace_id=""):
    """Write the Wordle-style struggle line for this session's knowledge.

    Aggregate shape only — built from event timestamps and counts, never
    from error text or file names. Never raises (artifacts must not be
    able to break the Stop hook).
    """
    try:
        from artifacts import struggle_grid, struggle_line, write_artifact
        errors = read_events(state_dir, "errors.jsonl")
        changes = read_events(state_dir, "changes.jsonl")
        meta = candidate.get("metadata_json") or {}
        grid = struggle_grid([e.get("t", 0) for e in errors],
                             [c.get("t", 0) for c in changes], resolved=True)
        line = struggle_line(grid, meta.get("time_to_resolution_minutes", 0),
                             meta.get("error_count", 0), trace_id=trace_id)
        write_artifact("last-struggle.txt", line + "\n")
        return line
    except Exception:
        return None
```

(`read_events` is already imported at the top of stop.py; `from artifacts import ...` resolves because hooks/ is the script directory at runtime and `tests/base.py` puts it on `sys.path` in tests.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_struggle_artifact -v`
Expected: 3 tests PASS

- [ ] **Step 5: Wire into main() — auto and manual paths**

In `/tmp/ct-skill/hooks/stop.py` `main()`, replace this exact block (currently lines 914–934):

```python
    if auto_mode:
        trace_id = _auto_submit(candidate)
        if trace_id:
            _append_auto_log({
                "trace_id": trace_id,
                "session_id": data.get("session_id", ""),
                "cwd": data.get("cwd", ""),
                "title": candidate.get("title", ""),
                "score": candidate.get("score", 0),
                "top_pattern": candidate.get("top_pattern", ""),
                "tags": candidate.get("suggested_tags", []),
            })
            return
        # API failure: fall through to pending so nothing is lost

    _write_pending(session_key, {
        "kind": "score",
        "session_id": data.get("session_id", ""),
        "cwd": data.get("cwd", ""),
        **candidate,
    })
```

with:

```python
    if auto_mode:
        trace_id = _auto_submit(candidate)
        if trace_id:
            _append_auto_log({
                "trace_id": trace_id,
                "session_id": data.get("session_id", ""),
                "cwd": data.get("cwd", ""),
                "title": candidate.get("title", ""),
                "score": candidate.get("score", 0),
                "top_pattern": candidate.get("top_pattern", ""),
                "tags": candidate.get("suggested_tags", []),
            })
            line = _struggle_artifact(candidate, state_dir, trace_id)
            if line:
                print(json.dumps({"systemMessage": (
                    "CommonTrace captured this fight:\n" + line +
                    "\n(saved to ~/.commontrace/artifacts/"
                    "last-struggle.txt — paste it anywhere)")}))
            return
        # API failure: fall through to pending so nothing is lost

    line = _struggle_artifact(candidate, state_dir)
    _write_pending(session_key, {
        "kind": "score",
        "session_id": data.get("session_id", ""),
        "cwd": data.get("cwd", ""),
        **({"struggle_grid": line} if line else {}),
        **candidate,
    })
```

- [ ] **Step 6: Verify the wiring and run the full suite**

Run: `cd /tmp/ct-skill && grep -n "_struggle_artifact" hooks/stop.py`
Expected: the def plus exactly two call sites (auto path with trace_id, manual path without).

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 64 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/stop.py', doraise=True)"
git add hooks/stop.py tests/test_struggle_artifact.py
git commit -m "feat(stop): struggle-grid share line on contribution"
```

---

### Task 8: Resolved-with disclosure trailer (post_tool_use.py)

**Files:**
- Modify: `/tmp/ct-skill/hooks/post_tool_use.py`
- Create: `/tmp/ct-skill/tests/test_resolved_with_trailer.py`

**Design recap:** `_pair_resolution` already looks up the most recent commons trace consumed since the error (the `trigger_feedback` query). When that trace is a real server trace (not a `"local:"` self-reference marker), the agent should be reminded — once per (session, trace) — that a disclosure trailer exists. The trailer is a citation register: informational, never imperative. Config gate `resolved_with_trailer` (default on); the one-line opt-out is surfaced exactly once ever via `trailer_notice_shown` persisted to config.

- [ ] **Step 1: Write the failing tests**

Create `/tmp/ct-skill/tests/test_resolved_with_trailer.py`:

```python
"""Resolved-with trailer: disclosure suggestion after commons-assisted fixes."""

import json
import time

from base import HookTestCase

import post_tool_use


def _error_event(t, sig="E: ModuleNotFoundError boom", command="pytest"):
    return {"source": "bash", "sig": sig, "command": command, "t": t}


class TestSuggestTrailer(HookTestCase):
    def _seed_consumed(self, conn, trace_id, base_t):
        conn.execute(
            "INSERT INTO trigger_feedback (session_id, trigger_name, "
            "triggered_at, trace_consumed_id, consumed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.state_dir.name, "error_search", base_t - 5, trace_id,
             base_t + 10))
        conn.commit()

    def test_server_trace_fires_trailer_with_first_use_notice(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        err_t = time.time() - 60
        self._seed_consumed(conn, "tr_42", err_t)
        out = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t)])
        self.assertIsNotNone(out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Resolved-with: CommonTrace "
                      "https://commontrace.org/t/tr_42", ctx)
        self.assertIn("Citation, not co-authorship", ctx)
        self.assertIn("resolved_with_trailer", ctx)  # opt-out, first use
        config = json.loads(
            post_tool_use.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertTrue(config["trailer_notice_shown"])

    def test_once_per_session_per_trace(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        err_t = time.time() - 60
        self._seed_consumed(conn, "tr_42", err_t)
        first = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t)])
        self.assertIsNotNone(first)
        second = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t)])
        self.assertIsNone(second)

    def test_opt_out_line_shown_only_first_time_ever(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        err_t = time.time() - 60
        self._seed_consumed(conn, "tr_1", err_t)
        first = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t, sig="E: one")])
        self.assertIn("One-line opt-out",
                      first["hookSpecificOutput"]["additionalContext"])
        # later consumption of a different trace wins the latest-consumed
        # lookup; the notice must not repeat
        self._seed_consumed(conn, "tr_2", err_t + 20)
        second = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t, sig="E: two")])
        ctx = second["hookSpecificOutput"]["additionalContext"]
        self.assertIn("tr_2", ctx)
        self.assertNotIn("One-line opt-out", ctx)

    def test_local_trace_never_fires(self):
        conn = self.get_conn()
        self.write_project_bridge(conn)
        err_t = time.time() - 60
        self._seed_consumed(conn, "local:abc123", err_t)
        out = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t)])
        self.assertIsNone(out)

    def test_config_opt_out_disables_trailer(self):
        post_tool_use.CONFIG_FILE.write_text(
            json.dumps({"resolved_with_trailer": False}), encoding="utf-8")
        conn = self.get_conn()
        self.write_project_bridge(conn)
        err_t = time.time() - 60
        self._seed_consumed(conn, "tr_42", err_t)
        out = post_tool_use._pair_resolution(
            self.state_dir, "pytest", [_error_event(err_t)])
        self.assertIsNone(out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_resolved_with_trailer -v`
Expected: FAIL — `_pair_resolution` currently returns `None` in every case, so the three fire-expecting tests fail on `assertIsNotNone`.

- [ ] **Step 3: Replace `_pair_resolution` and add `_suggest_trailer`**

In `/tmp/ct-skill/hooks/post_tool_use.py`, replace the entire `_pair_resolution` function (currently lines 440–511) with:

```python
def _pair_resolution(state_dir: Path, command: str,
                     previous_errors: list[dict]) -> dict | None:
    """Pair a succeeding command with a prior error of the same command head.

    Structural signal: the command that failed now succeeds. Stores the fix
    (verification command + basenames of files changed since the error +
    any commons trace consumed since the error) on the signature row —
    the payload _check_error_recurrence injects when the signature recurs.
    If this signature's fix was injected earlier this session, the
    resolution is recorded as a consumed trigger (assisted resolution),
    which feeds the error_recurrence rate in the existing M22-gated
    telemetry. When a commons (non-"local:") trace contributed to the
    fix, returns a Resolved-with disclosure suggestion for the agent.
    Never raises.
    """
    try:
        head = _command_head(command)
        if not head:
            return None
        match = None
        for entry in reversed(previous_errors):
            if entry.get("source") != "bash" or not entry.get("sig"):
                continue
            if _command_head(entry.get("command", "")) == head:
                match = entry
                break
        if match is None:
            return None
        project_id = _read_project_id(state_dir)
        if project_id is None:
            return None
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

        # Disclosure trailer: only for commons traces, never local markers
        trailer_output = None
        if trace_id and not str(trace_id).startswith("local:"):
            trailer_output = _suggest_trailer(state_dir, trace_id)
        conn.close()
        return trailer_output
    except Exception:
        return None


def _suggest_trailer(state_dir: Path, trace_id: str) -> dict | None:
    """Resolved-with disclosure trailer — citation, not co-authorship.

    Fires once per (session, trace). Config gate: "resolved_with_trailer"
    (default on). The one-line opt-out is surfaced exactly once ever, on
    first use ("trailer_notice_shown" persisted to config).
    """
    try:
        config = {}
        if CONFIG_FILE.exists():
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        config = {}
    if not config.get("resolved_with_trailer", True):
        return None
    suggested = {e.get("trace_id") for e in
                 read_events(state_dir, "trailer_suggested.jsonl")}
    if trace_id in suggested:
        return None
    append_event(state_dir, "trailer_suggested.jsonl", {"trace_id": trace_id})
    parts = [
        f"CommonTrace: trace {trace_id} contributed to this fix. "
        f"If a commit comes out of it, the disclosure trailer is:\n"
        f"Resolved-with: CommonTrace https://commontrace.org/t/{trace_id}\n"
        f"(Citation, not co-authorship — add it at the end of the commit "
        f"message if the user is fine with it.)"]
    if not config.get("trailer_notice_shown"):
        parts.append('One-line opt-out: set "resolved_with_trailer": false '
                     "in ~/.commontrace/config.json.")
        config["trailer_notice_shown"] = True
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            CONFIG_FILE.write_text(json.dumps(config, indent=2),
                                   encoding="utf-8")
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": " ".join(parts)}}
```

(All names used — `json`, `os`, `CONFIG_FILE`, `read_events`, `append_event`, `redact_command`, `error_hash` — are already imported/defined in post_tool_use.py.)

- [ ] **Step 4: Propagate the trailer through handle_bash**

In `/tmp/ct-skill/hooks/post_tool_use.py` `handle_bash`, change the success branch (inside the `else:` block ending around line 345):

```python
            _pair_resolution(state_dir, command, previous_errors)

    return None
```

to:

```python
            return _pair_resolution(state_dir, command, previous_errors)

    return None
```

- [ ] **Step 5: Run the new tests**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_resolved_with_trailer -v`
Expected: 5 tests PASS

- [ ] **Step 6: Run the full suite — adjudicate pre-existing pairing tests**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 69 tests PASS.

If any test in `tests/test_resolution_pairing.py` or `tests/test_integration_loop.py` fails because `_pair_resolution` (or `handle_bash`) now returns a trailer dict where the old code returned `None`: that return-type change is **intentional** — update only the failing assertion to accept the new return value (e.g. assert the db side effects as before, and assert the returned dict's `additionalContext` contains the consumed trace id). Do not weaken any other assertion.

- [ ] **Step 7: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/post_tool_use.py', doraise=True)"
git add hooks/post_tool_use.py tests/test_resolved_with_trailer.py
git commit -m "feat(post_tool_use): Resolved-with disclosure trailer"
```

(Include `tests/test_resolution_pairing.py` / `tests/test_integration_loop.py` in the `git add` if Step 6 required assertion updates.)

---

### Task 9: Monthly Compiled drop (session_start.py)

**Files:**
- Modify: `/tmp/ct-skill/hooks/session_start.py`
- Create: `/tmp/ct-skill/tests/test_compiled_drop.py`

**Design recap:** Fires once on the first session of each calendar month, covering the previous month. The marker `last_compiled_month` ("YYYY-MM") is set even when the month was empty, so the db is queried at most once per month. On first install the check fires immediately, finds an empty db, sets the marker, and stays silent. Known accepted limitation: `main()` has early returns for non-git/non-source projects, so the recap only delivers in git+source projects.

- [ ] **Step 1: Write the failing tests**

Create `/tmp/ct-skill/tests/test_compiled_drop.py`:

```python
"""Monthly Compiled drop from session_start."""

import json
import time
from unittest import mock

from base import HookTestCase

import artifacts
import local_store
import session_start

DAY = 86400.0


def _prev_month():
    t = time.localtime()
    if t.tm_mon > 1:
        return t.tm_year, t.tm_mon - 1
    return t.tm_year - 1, 12


class TestCompiledDrop(HookTestCase):
    def setUp(self):
        super().setUp()
        for target, attr, value in [
            (session_start, "CONFIG_DIR", self.tmp_path),
            (session_start, "CONFIG_FILE", self.tmp_path / "config.json"),
        ]:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_drops_recap_for_previous_month_and_saves_artifact(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        year, month = _prev_month()
        start, _ = artifacts.month_range(year, month)
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at, error_count, "
            "resolution_count, contribution_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("s1", pid, start + DAY, 5, 2, 0))
        conn.commit()
        config = {}
        note = session_start._compiled_drop(config)
        self.assertIsNotNone(note)
        self.assertIn("CommonTrace Compiled", note)
        self.assertIn("5 errors hit", note)
        files = list(artifacts.ARTIFACTS_DIR.glob("compiled-*.txt"))
        self.assertEqual(len(files), 1)
        t = time.localtime()
        self.assertEqual(config["last_compiled_month"],
                         f"{t.tm_year}-{t.tm_mon:02d}")

    def test_marker_blocks_repeat_even_on_empty_month(self):
        config = {}
        self.assertIsNone(session_start._compiled_drop(config))
        t = time.localtime()
        current = f"{t.tm_year}-{t.tm_mon:02d}"
        self.assertEqual(config["last_compiled_month"], current)
        saved = json.loads(
            session_start.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["last_compiled_month"], current)
        # second call: marker short-circuits before any db work
        self.assertIsNone(session_start._compiled_drop(config))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_compiled_drop -v`
Expected: ERROR with `AttributeError: module 'session_start' has no attribute '_compiled_drop'`

- [ ] **Step 3: Add `_compiled_drop` to session_start.py**

In `/tmp/ct-skill/hooks/session_start.py`, insert this function immediately after the `count_pending_traces` function definition (`sys` and `Path` are already imported at the top of the file):

```python
def _compiled_drop(config):
    """Monthly Compiled recap — fires once on the first session of each
    month, covering the previous month. The user's own numbers, generated
    locally; never an interpretation.

    The "last_compiled_month" marker is set even when the month was empty
    (one db query per month, then silence). Returns additionalContext
    text, or None.
    """
    import time as _time
    t = _time.localtime()
    current = f"{t.tm_year}-{t.tm_mon:02d}"
    if config.get("last_compiled_month") == current:
        return None
    if t.tm_mon > 1:
        year, month = t.tm_year, t.tm_mon - 1
    else:
        year, month = t.tm_year - 1, 12
    text = None
    path = None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from artifacts import compiled_recap, write_artifact
        from local_store import _get_conn
        conn = _get_conn()
        try:
            text = compiled_recap(conn, year, month)
        finally:
            conn.close()
        if text:
            path = write_artifact(f"compiled-{year}-{month:02d}.txt", text)
    except Exception:
        return None
    config["last_compiled_month"] = current
    try:
        save_config(config)
    except OSError:
        pass
    if not text:
        return None
    return (f"CommonTrace monthly Compiled recap is ready "
            f"(saved to {path}):\n\n{text}\n\n"
            f"Mention it to the user at a natural moment — it is their "
            f"own data, generated locally.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ct-skill && python3 -m unittest tests.test_compiled_drop -v`
Expected: 2 tests PASS

- [ ] **Step 5: Wire into main()**

In `/tmp/ct-skill/hooks/session_start.py` `main()`, the pending-hint block currently ends and the output dict begins (lines 440–442):

```python
            )

    output = {
```

Insert the compiled-drop block between them, so the code reads:

```python
            )

    # Monthly Compiled drop (first session of a new month → previous
    # month's numbers). Local-only; must never block session start.
    try:
        recap_note = _compiled_drop(config)
        if recap_note:
            additional_context += f"\n\n{recap_note}"
    except Exception:
        pass

    output = {
```

(`config` is already loaded a few lines above via `config = load_config()`.)

- [ ] **Step 6: Run the full suite**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 71 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add hooks/session_start.py tests/test_compiled_drop.py
git commit -m "feat(session_start): monthly Compiled drop"
```

---

### Task 10: /trace brain command, docs, version 0.4.0

**Files:**
- Create: `/tmp/ct-skill/commands/trace/brain.md`
- Modify: `/tmp/ct-skill/commands/trace/contribute.md`
- Modify: `/tmp/ct-skill/README.md`
- Modify: `/tmp/ct-skill/.claude-plugin/plugin.json`
- Modify: `/tmp/ct-skill/hooks/session_start.py` (SKILL_VERSION)

- [ ] **Step 1: Create the /trace brain command**

Create `/tmp/ct-skill/commands/trace/brain.md`:

````markdown
---
description: Render your agent's brain — local knowledge graph from local.db
allowed-tools: ["Bash", "Read"]
---

You are generating the user's local CommonTrace brain artifacts.

## Step 1 — Generate

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/artifacts.py brain
```

## Step 2 — Report

Report the printed file paths and the stats line (N solved · M open · K projects). Tell the user:

- Open `~/.commontrace/artifacts/brain.html` in a browser to see the full page.
- To embed the badge in a README, copy `~/.commontrace/artifacts/badge.svg` into the repo and add: `![CommonTrace brain](./badge.svg)`

If the user asks for the monthly recap instead, run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/artifacts.py recap` (optionally `recap YYYY-MM`).

## Rules

- Everything is generated locally from `~/.commontrace/local.db` — no network calls, aggregate shapes only (no code, no error text, no file names).
- If the command fails, report the error and stop — do not retry in a loop.
````

- [ ] **Step 2: Surface the struggle grid in /trace contribute**

In `/tmp/ct-skill/commands/trace/contribute.md`, after the line:

```markdown
- `metadata_json` — detection metadata (pass through verbatim on submit)
```

add:

```markdown
- `struggle_grid` — optional share line (emoji struggle grid + stats); not submitted, used for display after a successful contribution
```

And change the Step 3 "Yes" flow line:

```markdown
After successful submit, delete the candidate's line from the pending file (use `sed` or rewrite the file without that line). Report the new trace ID.
```

to:

```markdown
After successful submit, delete the candidate's line from the pending file (use `sed` or rewrite the file without that line). Report the new trace ID. If the candidate has `struggle_grid`, show it to the user with ` → https://commontrace.org/t/<new-trace-id>` appended — it is a paste-anywhere share line.
```

- [ ] **Step 3: README — Artifacts section, command, config keys**

In `/tmp/ct-skill/README.md`:

(a) In the "What It Does" list, after the line `- **Contribution prompts** on session end when a problem was solved`, add:

```markdown
- **Local-first artifacts** — brain graph, struggle grid, monthly recap; aggregate shapes only, generated on your machine
```

(b) In the "Slash Commands" section, after the `### /commontrace [query]` entry, add:

```markdown
### `/trace brain`

Render local brain artifacts (`brain.html`, `brain.svg`, `badge.svg`) from `~/.commontrace/local.db`.
```

(c) After the "## Hooks" section (before "## Available MCP Tools"), add:

```markdown
## Artifacts (local-first)

Everything below is generated locally from `~/.commontrace/local.db`. Aggregate shapes only — no code, no error text, no file names.

- **Brain graph** — `/trace brain` renders `~/.commontrace/artifacts/brain.html` + `brain.svg`: your agent's knowledge graph. Node size = how hard the fight was, color = memory temperature (hot → frozen), fade = decay.
- **README badge** — the same command also writes `badge.svg`. Copy it into a repo and embed: `![CommonTrace brain](./badge.svg)`
- **Struggle grid** — after a knowledge-worthy session, a Wordle-style share line lands in `~/.commontrace/artifacts/last-struggle.txt`: `🟥🟥🟨🟨🟩 47min · 8 errors · solved → commontrace.org/t/<id>`
- **Resolved-with trailer** — when a commons trace contributed to a fix, the agent is reminded to disclose it in the commit message: `Resolved-with: CommonTrace https://commontrace.org/t/<id>` (citation, not co-authorship).
- **Monthly Compiled** — the first session of each month drops last month's recap (sessions, errors, resolutions, hardest fight) to `~/.commontrace/artifacts/compiled-YYYY-MM.txt`. Your own numbers, never AI interpretation.
```

(d) In the "## Configuration" section, after the existing env-var table, add:

```markdown
### `~/.commontrace/config.json` keys

| Key | Default | Description |
|-----|---------|-------------|
| `auto_contribute` | `true` | Submit detected knowledge automatically; set `false` to review via `/trace contribute` |
| `resolved_with_trailer` | `true` | Suggest the `Resolved-with:` disclosure trailer after commons-assisted fixes |
```

- [ ] **Step 4: Version bump to 0.4.0**

In `/tmp/ct-skill/.claude-plugin/plugin.json`, change:

```json
  "version": "0.3.0",
```

to:

```json
  "version": "0.4.0",
```

In `/tmp/ct-skill/hooks/session_start.py` (line 26), change:

```python
SKILL_VERSION = "0.3.0"
```

to:

```python
SKILL_VERSION = "0.4.0"
```

- [ ] **Step 5: Full suite green + JSON validity**

Run: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
Expected: 71 tests PASS

Run: `cd /tmp/ct-skill && python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /tmp/ct-skill
python3 -c "import py_compile; py_compile.compile('hooks/session_start.py', doraise=True)"
git add commands/trace/brain.md commands/trace/contribute.md README.md .claude-plugin/plugin.json hooks/session_start.py
git commit -m "docs: /trace brain command, artifacts README; bump to 0.4.0"
```

---

## After all tasks

1. Dispatch the final code reviewer over the whole diff (`git diff 574dfc4..HEAD`), checking specifically: the seven hard constraints in the header, privacy-by-construction (grep all artifact-producing code paths for anything that could carry signature text, paths, or file names into output), and that all 71 tests pass offline (`COMMONTRACE_API_KEY` unset).
2. Push to `commontrace/skill` `main` **only after** the final review verdict is clean.
3. Founder follow-ups recorded, not built: frontend `/t/<trace_id>` route; hosted share page; live badge endpoint.
