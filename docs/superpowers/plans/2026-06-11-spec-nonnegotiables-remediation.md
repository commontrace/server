# Spec §4 Non-Negotiables Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four missing/partial §4 non-negotiables from the 2026-06-10 vision spec: search-miss logging (§6.3 Wanted Board demand signal), ambient presence topic counters (§4.4), assisted-resolution rate end-to-end (§4.3), and contributor provenance surfacing (§4.2).

**Architecture:** One new table (`search_misses`), four nullable counter columns on `trigger_stats`, two new aggregate-only analytics endpoints, and `contributor_name` added to trace/search responses via batched `COALESCE(display_name, 'anon-' || LEFT(id::text, 8))` lookup, surfaced through MCP formatters and skill hooks with sanitization (display names are user-supplied — prompt-injection surface). Rollout-safe in both directions: server deploys before skill push; skill versions < 0.5.2 POST telemetry without counters (NULL rows excluded from rate, never zero-filled); pydantic ignores the extra counter fields if a new skill hits an old server.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (server), FastMCP string formatters (MCP), Python stdlib hooks + sqlite3 + unittest (skill).

**Repos (commits stay local — NO pushes without explicit user confirmation):**
- Server: `/home/denem/commontrace` (monorepo, `api/`), branch main
- MCP: `/tmp/ct-mcp`, branch main
- Skill: `/tmp/ct-skill`, branch main (stacked on unpushed v0.5.1 commits; suite must stay green)

**Verification:**
- Syntax: `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`
- Skill tests: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v`
- E2E (Task 8): `docker compose -f docker-compose.yml -f docker-compose.override.yml -f /tmp/ct-e2e-ports.yml <cmd>` from `/home/denem/commontrace`

---

### Task 1: Search-miss logging (spec §6.3 Wanted Board demand signal)

**Files:**
- Create: `api/app/models/search_miss.py`
- Create: `api/migrations/versions/0021_search_misses.py`
- Modify: `api/app/models/__init__.py` (add import + `__all__` entry)
- Modify: `api/app/services/retrieval.py` (append function at end, after `record_co_retrievals`)
- Modify: `api/app/routers/search.py` (import line 42 + `else` branch on fire-and-forget block lines 443-450)

- [ ] **Step 1: Create the model**

`api/app/models/search_miss.py` (shape mirrors `retrieval_log.py`):

```python
"""Search miss model.

Records zero-result searches — the demand signal for the Wanted Board
(spec §6.3). Aggregate-shape only: the query the agent already sent,
its tags, and coarse context labels (language/framework). Never code,
paths, or repo names.
"""

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SearchMiss(Base):
    __tablename__ = "search_misses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_text: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True
    )
    tags: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    language: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    framework: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Export the model**

In `api/app/models/__init__.py`: after `from .invitation import Invitation` add `from .search_miss import SearchMiss`; in `__all__` after `"Invitation",` add `"SearchMiss",`.

- [ ] **Step 3: Create the migration**

`api/migrations/versions/0021_search_misses.py`:

```python
"""Search misses: zero-result search log (spec §6.3 Wanted Board precursor).

Revision ID: 210a1b2c3d4e
Revises: 200a1b2c3d4e
Create Date: 2026-06-11 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "210a1b2c3d4e"
down_revision: str = "200a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_misses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query_text", sa.String(length=2000), nullable=True),
        sa.Column("tags", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_search_misses_created_at", "search_misses", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_search_misses_created_at", table_name="search_misses")
    op.drop_table("search_misses")
```

- [ ] **Step 4: Add the recording function**

Append to `api/app/services/retrieval.py` (after `record_co_retrievals`; `text`, `async_session_factory`, `log` already imported):

```python
async def record_search_miss(
    query_text: str | None, tags: list[str], context: dict | None
) -> None:
    """Record a zero-result search — the Wanted Board demand signal (spec §6.3).

    Fire-and-forget like the other trackers: opens its own session, never
    raises into the search path. Only stores what the agent already sent
    in the search request (query, tags, coarse context labels).
    """
    try:
        language = None
        framework = None
        if isinstance(context, dict):
            lang_val = context.get("language")
            fw_val = context.get("framework")
            language = str(lang_val)[:50] if lang_val else None
            framework = str(fw_val)[:50] if fw_val else None
        async with async_session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO search_misses "
                    "(id, query_text, tags, language, framework) "
                    "VALUES (gen_random_uuid(), :query_text, :tags, "
                    ":language, :framework)"
                ),
                {
                    "query_text": query_text[:2000] if query_text else None,
                    "tags": ",".join(tags)[:500] if tags else None,
                    "language": language,
                    "framework": framework,
                },
            )
            await session.commit()
    except Exception:
        log.warning("search_miss_tracking_failed", exc_info=True)
```

- [ ] **Step 5: Wire into search**

In `api/app/routers/search.py` line 42, change:

```python
from app.services.retrieval import record_co_retrievals, record_retrieval_logs, record_retrievals
```

to:

```python
from app.services.retrieval import (
    record_co_retrievals,
    record_retrieval_logs,
    record_retrievals,
    record_search_miss,
)
```

Then extend the fire-and-forget block (currently lines 443-450) with an `else` branch:

```python
    # Fire-and-forget: record retrievals + co-retrieval patterns
    # Tasks are tracked in _background_tasks set to prevent GC before completion
    if results:
        trace_ids = [r.id for r in results]
        search_session_id = str(uuid_mod.uuid4())
        _track_task(record_retrievals(trace_ids))
        _track_task(record_retrieval_logs(trace_ids, search_session_id))
        _track_task(record_co_retrievals(trace_ids))
    else:
        # Zero-result search = Wanted Board demand signal (spec §6.3)
        _track_task(record_search_miss(body.q, normalized_tags, searcher_fp))
```

- [ ] **Step 6: Syntax-check all five files**

```bash
cd /home/denem/commontrace && for f in api/app/models/search_miss.py api/app/models/__init__.py api/migrations/versions/0021_search_misses.py api/app/services/retrieval.py api/app/routers/search.py; do python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" || echo "FAIL $f"; done
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add api/app/models/search_miss.py api/app/models/__init__.py api/migrations/versions/0021_search_misses.py api/app/services/retrieval.py api/app/routers/search.py
git commit -m "feat(search): log zero-result searches as Wanted Board demand signal (spec §6.3)"
```

---

### Task 2: Ambient presence topic counters (spec §4.4)

**Files:**
- Modify: `api/app/routers/analytics.py` (docstring lines 7-16 + append endpoint after `get_triggers`, line 346)

- [ ] **Step 1: Add docstring line**

In the module docstring endpoint list, after `  GET /api/v1/analytics/triggers` add `  GET /api/v1/analytics/topics?limit=20`.

- [ ] **Step 2: Append the endpoint**

After `get_triggers` (file end). `text`, `Query`, `timedelta`, `_utcnow` already available:

```python
@router.get("/topics")
async def get_topics(db: DbSession, limit: int = Query(20, ge=1, le=50)) -> dict:
    """Ambient presence: per-tag activity counters, trailing 7 days (spec §4.4).

    Aggregate-only — tag names and counts, nothing user-identifying.
    """
    since = _utcnow() - timedelta(days=7)

    retrieval_sql = text(
        "SELECT tg.name, COUNT(*) AS retrievals "
        "FROM retrieval_logs rl "
        "JOIN trace_tags tt ON tt.trace_id = rl.trace_id "
        "JOIN tags tg ON tg.id = tt.tag_id "
        "WHERE rl.retrieved_at >= :since "
        "GROUP BY tg.name"
    )
    new_traces_sql = text(
        "SELECT tg.name, COUNT(DISTINCT t.id) AS new_traces "
        "FROM traces t "
        "JOIN trace_tags tt ON tt.trace_id = t.id "
        "JOIN tags tg ON tg.id = tt.tag_id "
        "WHERE t.created_at >= :since "
        "GROUP BY tg.name"
    )
    retrieval_rows = (await db.execute(retrieval_sql, {"since": since})).fetchall()
    new_trace_rows = (await db.execute(new_traces_sql, {"since": since})).fetchall()
    retrievals = {r[0]: int(r[1]) for r in retrieval_rows}
    new_traces = {r[0]: int(r[1]) for r in new_trace_rows}

    topics = [
        {
            "tag": tag,
            "retrievals_7d": retrievals.get(tag, 0),
            "new_traces_7d": new_traces.get(tag, 0),
        }
        for tag in set(retrievals) | set(new_traces)
    ]
    topics.sort(key=lambda x: (-x["retrievals_7d"], -x["new_traces_7d"], x["tag"]))
    return {"window_days": 7, "topics": topics[:limit]}
```

- [ ] **Step 3: Syntax-check + commit**

```bash
python3 -c "import py_compile; py_compile.compile('api/app/routers/analytics.py', doraise=True)"
git add api/app/routers/analytics.py
git commit -m "feat(analytics): ambient presence topic counters (spec §4.4)"
```

---

### Task 3: Assisted-resolution north-star — server half (spec §4.3)

**Files:**
- Create: `api/migrations/versions/0022_assisted_resolution_telemetry.py`
- Modify: `api/app/models/trigger_stats.py` (add `Optional` import + 4 columns)
- Modify: `api/app/routers/telemetry.py` (`TriggerStatsBody` lines 29-31, constructor lines 46-49)
- Modify: `api/app/routers/analytics.py` (docstring + append endpoint)

- [ ] **Step 1: Create the migration**

`api/migrations/versions/0022_assisted_resolution_telemetry.py`:

```python
"""Assisted-resolution counters on trigger_stats (spec §4.3 north-star).

Revision ID: 220a1b2c3d4e
Revises: 210a1b2c3d4e
Create Date: 2026-06-11 12:00:00.000000

Nullable on purpose: skill versions before 0.5.2 post telemetry without
these counters; NULL rows are excluded from the assisted-resolution rate
rather than zero-filled.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "220a1b2c3d4e"
down_revision: str = "210a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trigger_stats", sa.Column("searches_fired", sa.Integer(), nullable=True)
    )
    op.add_column(
        "trigger_stats", sa.Column("traces_consumed", sa.Integer(), nullable=True)
    )
    op.add_column(
        "trigger_stats", sa.Column("resolutions_total", sa.Integer(), nullable=True)
    )
    op.add_column(
        "trigger_stats",
        sa.Column("resolutions_assisted", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trigger_stats", "resolutions_assisted")
    op.drop_column("trigger_stats", "resolutions_total")
    op.drop_column("trigger_stats", "traces_consumed")
    op.drop_column("trigger_stats", "searches_fired")
```

- [ ] **Step 2: Extend the model**

In `api/app/models/trigger_stats.py`: after `from datetime import datetime` add `from typing import Optional`; after the `stats_json` column add:

```python
    # Assisted-resolution counters (spec §4.3 north-star).
    # Nullable: skill versions before 0.5.2 don't report them.
    searches_fired: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    traces_consumed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolutions_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolutions_assisted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 3: Extend the telemetry body + constructor**

In `api/app/routers/telemetry.py` (`Optional` and `Field` already imported):

```python
class TriggerStatsBody(BaseModel):
    session_id: str
    trigger_stats: dict
    # Assisted-resolution counters (spec §4.3) — absent from skill < 0.5.2
    searches_fired: Optional[int] = Field(default=None, ge=0)
    traces_consumed: Optional[int] = Field(default=None, ge=0)
    resolutions_total: Optional[int] = Field(default=None, ge=0)
    resolutions_assisted: Optional[int] = Field(default=None, ge=0)
```

```python
    record = TriggerStats(
        session_id=body.session_id,
        stats_json=body.trigger_stats,
        searches_fired=body.searches_fired,
        traces_consumed=body.traces_consumed,
        resolutions_total=body.resolutions_total,
        resolutions_assisted=body.resolutions_assisted,
    )
```

- [ ] **Step 4: Add the endpoint**

In `api/app/routers/analytics.py`: docstring gets `  GET /api/v1/analytics/assisted-resolution`; append after `get_topics`:

```python
@router.get("/assisted-resolution")
async def get_assisted_resolution(db: DbSession) -> dict:
    """North-star metric: % of searches where a retrieved trace contributed
    to the fix (spec §4.3).

    Only counts sessions from skill versions that report the counters
    (searches_fired IS NOT NULL) — older clients are excluded, not
    zero-filled.
    """
    sql = text(
        "SELECT COUNT(*) AS sessions, "
        "COALESCE(SUM(searches_fired), 0) AS searches, "
        "COALESCE(SUM(traces_consumed), 0) AS consumed, "
        "COALESCE(SUM(resolutions_total), 0) AS resolutions, "
        "COALESCE(SUM(resolutions_assisted), 0) AS assisted "
        "FROM trigger_stats "
        "WHERE reported_at >= NOW() - INTERVAL '30 days' "
        "AND searches_fired IS NOT NULL"
    )
    row = (await db.execute(sql)).one()
    searches = int(row.searches)
    consumed = int(row.consumed)
    resolutions = int(row.resolutions)
    assisted = int(row.assisted)
    return {
        "window_days": 30,
        "sessions_reporting": int(row.sessions),
        "searches_fired": searches,
        "traces_consumed": consumed,
        "resolutions_total": resolutions,
        "resolutions_assisted": assisted,
        "assisted_resolution_rate": round(assisted / searches, 3)
        if searches > 0
        else 0.0,
        "assist_share_of_resolutions": round(assisted / resolutions, 3)
        if resolutions > 0
        else 0.0,
    }
```

- [ ] **Step 5: Syntax-check all four files + commit**

```bash
for f in api/migrations/versions/0022_assisted_resolution_telemetry.py api/app/models/trigger_stats.py api/app/routers/telemetry.py api/app/routers/analytics.py; do python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" || echo "FAIL $f"; done
git add api/migrations/versions/0022_assisted_resolution_telemetry.py api/app/models/trigger_stats.py api/app/routers/telemetry.py api/app/routers/analytics.py
git commit -m "feat(telemetry): assisted-resolution north-star counters + endpoint (spec §4.3)"
```

---

### Task 4: Contributor provenance — server half (spec §4.2)

**Files:**
- Modify: `api/app/schemas/trace.py` (`TraceResponse`, after `contributor_id` line 60)
- Modify: `api/app/schemas/search.py` (`TraceSearchResult`, after `contributor_id` line 32)
- Modify: `api/app/routers/traces.py` (`get_trace`, after `tag_names` line 180 + constructor)
- Modify: `api/app/routers/search.py` (after related-traces block, before Step H — NOTE: line numbers shifted by Task 1's else-branch; anchor on code, not line numbers)

- [ ] **Step 1: Extend both schemas**

In both `TraceResponse` and `TraceSearchResult`, directly after `contributor_id: uuid.UUID` add:

```python
    contributor_name: Optional[str] = None
```

(`Optional` already imported in both files.)

- [ ] **Step 2: Single lookup in get_trace**

In `api/app/routers/traces.py`, after `tag_names = [tag.name for tag in trace.tags]`:

```python
    # Contributor provenance (spec §4.2): display name or stable anon handle
    name_result = await db.execute(
        text(
            "SELECT COALESCE(display_name, 'anon-' || LEFT(id::text, 8)) "
            "FROM users WHERE id = :uid"
        ),
        {"uid": str(trace.contributor_id)},
    )
    contributor_name = name_result.scalar_one_or_none()
```

And in the `TraceResponse(...)` constructor, after `contributor_id=trace.contributor_id,` add `contributor_name=contributor_name,`.

- [ ] **Step 3: Batched lookup in search**

In `api/app/routers/search.py`, after the related-traces block (ends `r.related_traces = related_by_source.get(str(r.id), [])`), before `# Step H: Search metrics instrumentation`:

```python
    # Contributor provenance (spec §4.2): batched display-name lookup
    if results:
        contributor_ids = list({r.contributor_id for r in results})
        name_rows = await db.execute(
            text(
                "SELECT id, COALESCE(display_name, 'anon-' || LEFT(id::text, 8)) "
                "AS name FROM users WHERE id = ANY(:ids)"
            ),
            {"ids": contributor_ids},
        )
        names_by_id = {row.id: row.name for row in name_rows}
        for r in results:
            r.contributor_name = names_by_id.get(r.contributor_id)
```

(Same `= ANY(:ids)` + UUID-objects pattern as the related-traces query above it. Covers all three construction sites — semantic, tag-only, spreading-activation — because the Pydantic field defaults to None.)

- [ ] **Step 4: Syntax-check all four files + commit**

```bash
for f in api/app/schemas/trace.py api/app/schemas/search.py api/app/routers/traces.py api/app/routers/search.py; do python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" || echo "FAIL $f"; done
git add api/app/schemas/trace.py api/app/schemas/search.py api/app/routers/traces.py api/app/routers/search.py
git commit -m "feat(traces): contributor provenance on trace + search responses (spec §4.2)"
```

---

### Task 5: Contributor provenance — MCP formatters (repo: /tmp/ct-mcp)

**Files:**
- Modify: `/tmp/ct-mcp/app/formatters.py` (no `import re` currently — add it)

- [ ] **Step 1: Add sanitizer**

At top of `formatters.py`, after the module docstring:

```python
import re


def _safe_name(name) -> str:
    """Sanitize a contributor display name for inline display.

    Display names are user-supplied — strip everything except word chars,
    spaces, dots, and hyphens, and cap at 40 chars (injection surface).
    """
    if not name:
        return ""
    return re.sub(r"[^\w\s.\-]", "", str(name))[:40].strip()
```

- [ ] **Step 2: Surface in format_search_results**

Before the `entry = (` assignment add `contributor = _safe_name(r.get("contributor_name"))` and `by_str = f" | by {contributor}" if contributor else ""`; change the ID line inside `entry` from `f"   ID: {r.get('id', 'unknown')}\n"` to `f"   ID: {r.get('id', 'unknown')}{by_str}\n"`.

- [ ] **Step 3: Surface in format_trace**

After `trust = data.get("trust_score", 0.0)` add:

```python
    contributor = _safe_name(data.get("contributor_name"))
    by_str = f" | By: {contributor}" if contributor else ""
```

Change the status line from `f"Status: {status} | Trust: {trust:.1f} | Tags: {tags_str}{temp_str}\n"` to `f"Status: {status} | Trust: {trust:.1f} | Tags: {tags_str}{temp_str}{by_str}\n"`.

- [ ] **Step 4: Syntax-check + commit (in /tmp/ct-mcp)**

```bash
cd /tmp/ct-mcp && python3 -c "import py_compile; py_compile.compile('app/formatters.py', doraise=True)"
git add app/formatters.py
git commit -m "feat(formatters): surface contributor provenance, sanitized (spec §4.2)"
```

---

### Task 6: Skill v0.5.2 — session counters + provenance display (repo: /tmp/ct-skill, TDD)

**Files:**
- Create: `/tmp/ct-skill/tests/test_session_counters.py`
- Modify: `/tmp/ct-skill/hooks/stop.py` (new `_session_counters` above `_report_trigger_stats` line 805 + wiring inside it)
- Modify: `/tmp/ct-skill/hooks/post_tool_use.py` (`format_results` lines 216-223; `import re` already present)
- Modify: `/tmp/ct-skill/hooks/session_start.py` (`format_result` lines 506-519; ADD `import re` to stdlib imports; bump `SKILL_VERSION` line 31)
- Modify: `/tmp/ct-skill/.claude-plugin/plugin.json` (version line 3) + `/tmp/ct-skill/skills/commontrace/SKILL.md` (frontmatter `version:` line 8)

- [ ] **Step 1: Write the failing tests**

`/tmp/ct-skill/tests/test_session_counters.py`:

```python
"""Session counters (v0.5.2): assisted-resolution telemetry + provenance.

Counter tests drive stop._session_counters — per-session aggregates sent
to /api/v1/telemetry/triggers (spec §4.3 north-star). Counters are scoped
by trigger_feedback.session_id = state_dir.name (NOT the sessions table).
Formatter tests pin contributor provenance display (spec §4.2) with
sanitization — display names are user-supplied (injection surface).
"""

import time
import unittest

from tests.base import HookTestCase, append_event, local_store, post_tool_use
import session_start
import stop


class TestSessionCounters(HookTestCase):
    def _write_resolutions(self, n, t0=None):
        t0 = time.time() if t0 is None else t0
        for i in range(n):
            append_event(self.state_dir, "resolutions.jsonl",
                         {"source": "bash", "t": t0 + i})

    def test_empty_session_returns_zeros(self):
        conn = self.get_conn()
        self.assertEqual(
            stop._session_counters(conn, self.state_dir, None),
            {"searches_fired": 0, "traces_consumed": 0,
             "resolutions_total": 0, "resolutions_assisted": 0})

    def test_fired_and_consumed_scoped_to_this_session(self):
        conn = self.get_conn()
        sid = self.state_dir.name
        for _ in range(3):
            local_store.record_trigger(conn, sid, "bash_error")
        local_store.record_trace_consumed(conn, sid, "trace-1")
        local_store.record_trigger(conn, "other-session", "bash_error")
        local_store.record_trigger(conn, "other-session", "bash_error")
        counters = stop._session_counters(conn, self.state_dir, None)
        self.assertEqual(counters["searches_fired"], 3)
        self.assertEqual(counters["traces_consumed"], 1)

    def test_assisted_counts_attributed_resolutions_in_window(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        now = time.time()
        # Commons-attributed + local-attributed land in trace_id alike
        local_store.record_error_signature(conn, pid, "sig-commons")
        local_store.record_resolution(conn, pid, "sig-commons",
                                      trace_id="abc-123")
        local_store.record_error_signature(conn, pid, "sig-local")
        local_store.record_resolution(conn, pid, "sig-local",
                                      trace_id="local:deadbeef")
        # Unattributed resolution: trace_id stays NULL
        local_store.record_error_signature(conn, pid, "sig-unattributed")
        local_store.record_resolution(conn, pid, "sig-unattributed")
        # Attributed but resolved long before this session's window
        local_store.record_error_signature(conn, pid, "sig-old")
        local_store.record_resolution(conn, pid, "sig-old",
                                      trace_id="old-999")
        conn.execute(
            "UPDATE error_signatures SET resolved_at = ? WHERE signature = ?",
            (now - 99999, "sig-old"))
        conn.commit()
        self._write_resolutions(3, t0=now)
        counters = stop._session_counters(conn, self.state_dir, pid)
        self.assertEqual(counters["resolutions_total"], 3)
        self.assertEqual(counters["resolutions_assisted"], 2)

    def test_assisted_capped_at_resolutions_total(self):
        conn = self.get_conn()
        pid = local_store.ensure_project(conn, "/test-project")
        for i in range(3):
            sig = f"sig-{i}"
            local_store.record_error_signature(conn, pid, sig)
            local_store.record_resolution(conn, pid, sig,
                                          trace_id=f"trace-{i}")
        self._write_resolutions(1)
        counters = stop._session_counters(conn, self.state_dir, pid)
        self.assertEqual(counters["resolutions_total"], 1)
        self.assertEqual(counters["resolutions_assisted"], 1)

    def test_no_project_id_keeps_totals_but_zero_assisted(self):
        conn = self.get_conn()
        self._write_resolutions(2)
        counters = stop._session_counters(conn, self.state_dir, None)
        self.assertEqual(counters["resolutions_total"], 2)
        self.assertEqual(counters["resolutions_assisted"], 0)


class TestProvenanceFormatting(unittest.TestCase):
    def test_search_results_show_sanitized_contributor(self):
        out = post_tool_use.format_results([{
            "title": "T", "solution_text": "S", "id": "tid-1",
            "contributor_name": "alice<script>!",
        }])
        self.assertIn("by alicescript", out)
        self.assertNotIn("<script>", out)

    def test_session_start_result_shows_contributor(self):
        out = session_start.format_result({
            "title": "T", "context_text": "c", "solution_text": "s",
            "id": "tid-2", "contributor_name": "bob",
        })
        self.assertIn("by bob", out)

    def test_missing_contributor_name_omits_by(self):
        self.assertNotIn(" by ", post_tool_use.format_results(
            [{"title": "T", "solution_text": "S", "id": "tid-3"}]))
        self.assertNotIn(" by ", session_start.format_result(
            {"title": "T", "id": "tid-4"}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run new tests — verify they FAIL**

```bash
cd /tmp/ct-skill && python3 -m unittest tests.test_session_counters -v
```

Expected: AttributeError (`stop` has no `_session_counters`) and formatting assertion failures.

- [ ] **Step 3: Implement `_session_counters` in stop.py**

Insert directly above `_report_trigger_stats` (line 805). `read_events` and `Path` already imported at top:

```python
def _session_counters(conn, state_dir: Path, project_id) -> dict:
    """Per-session aggregates for the assisted-resolution north-star (§4.3).

    Scoped to THIS session: trigger_feedback rows keyed by state_dir.name,
    resolution events from resolutions.jsonl, and assisted resolutions =
    error signatures resolved with an attributed trace (commons ID or
    local: marker — record_resolution COALESCEs both into trace_id) since
    this session's first resolution event minus 5s grace. Capped at
    resolutions_total so a recurring signature never overcounts.
    """
    counters = {"searches_fired": 0, "traces_consumed": 0,
                "resolutions_total": 0, "resolutions_assisted": 0}
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS fired, "
            "SUM(CASE WHEN trace_consumed_id IS NOT NULL THEN 1 ELSE 0 END) "
            "AS consumed "
            "FROM trigger_feedback WHERE session_id = ?",
            (state_dir.name,)).fetchone()
        if row:
            counters["searches_fired"] = int(row["fired"] or 0)
            counters["traces_consumed"] = int(row["consumed"] or 0)
    except Exception:
        pass
    try:
        resolutions = read_events(state_dir, "resolutions.jsonl")
        counters["resolutions_total"] = len(resolutions)
        if resolutions and project_id is not None:
            floor = min(e.get("t", 0) for e in resolutions) - 5.0
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM error_signatures "
                "WHERE project_id = ? AND trace_id IS NOT NULL "
                "AND resolved_at >= ?",
                (project_id, floor)).fetchone()
            if row:
                counters["resolutions_assisted"] = min(
                    int(row["n"] or 0), counters["resolutions_total"])
    except Exception:
        pass
    return counters
```

- [ ] **Step 4: Wire into `_report_trigger_stats`**

Change:

```python
        conn = _get_conn()
        stats = get_trigger_effectiveness(conn, project_id)
        conn.close()

        if not stats:
            return
```

to:

```python
        conn = _get_conn()
        stats = get_trigger_effectiveness(conn, project_id)
        counters = _session_counters(conn, state_dir, project_id)
        conn.close()

        if not stats and not any(counters.values()):
            return
```

And change:

```python
        payload = json.dumps({
            "trigger_stats": stats,
            "session_id": session_id,
        }).encode("utf-8")
```

to:

```python
        body = {"trigger_stats": stats, "session_id": session_id}
        body.update(counters)
        payload = json.dumps(body).encode("utf-8")
```

- [ ] **Step 5: Provenance in post_tool_use.format_results**

Replace the function body (lines 216-223; `import re` already present at line 24):

```python
def format_results(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        solution = r.get("solution_text", "")[:200]
        trace_id = r.get("id", "")
        # Contributor names are user-supplied — sanitize before display
        contributor = re.sub(
            r"[^\w\s.\-]", "", str(r.get("contributor_name") or ""))[:40].strip()
        by = f" by {contributor}" if contributor else ""
        lines.append(f"{i}. [{title}] — {solution}... (ID: {trace_id}{by})")
    return "\n".join(lines)
```

- [ ] **Step 6: Provenance in session_start.format_result**

Add `import re` to session_start.py stdlib imports (alphabetical: between `import os` and `import subprocess`). Replace `format_result` (lines 506-519):

```python
def format_result(result: dict) -> str:
    title = result.get("title", "Untitled")
    context_text = result.get("context_text", "")[:100]
    solution_text = result.get("solution_text", "")[:150]
    trace_id = result.get("id", "")
    # Contributor names are user-supplied — sanitize before display
    contributor = re.sub(
        r"[^\w\s.\-]", "",
        str(result.get("contributor_name") or ""))[:40].strip()

    parts = [f"[{title}]"]
    if context_text:
        parts.append(f"— {context_text}...")
    if solution_text:
        parts.append(f"Solution: {solution_text}...")
    if trace_id:
        parts.append(f"(trace ID: {trace_id})")
    if contributor:
        parts.append(f"by {contributor}")
    return " ".join(parts)
```

- [ ] **Step 7: Version bumps**

- `hooks/session_start.py` line 31: `SKILL_VERSION = "0.5.1"` → `"0.5.2"`
- `.claude-plugin/plugin.json` line 3: `"version": "0.5.1"` → `"0.5.2"`
- `skills/commontrace/SKILL.md` line 8: `version: 0.5.1` → `version: 0.5.2`

- [ ] **Step 8: Run new tests, then FULL suite**

```bash
cd /tmp/ct-skill && python3 -m unittest tests.test_session_counters -v && python3 -m unittest discover -s tests
```

Expected: 8 new tests pass; full suite `OK` with ≥ 104 tests (96 existing + 8 new).

- [ ] **Step 9: Commit (in /tmp/ct-skill)**

```bash
git add tests/test_session_counters.py hooks/stop.py hooks/post_tool_use.py hooks/session_start.py .claude-plugin/plugin.json skills/commontrace/SKILL.md
git commit -m "feat: v0.5.2 — assisted-resolution session counters + contributor provenance

Session-scoped counters (searches_fired, traces_consumed,
resolutions_total, resolutions_assisted) ride the existing M22-gated
telemetry POST — the skill half of the spec §4.3 north-star metric.
Assisted = error signatures resolved with an attributed trace (commons
ID or local: marker) within this session's resolution window, capped at
resolutions_total. Search results now show sanitized contributor
provenance (spec §4.2)."
```

---

### Task 7: Spec §6.4 amendment — controller-direct

**Files:**
- Modify: `docs/superpowers/specs/2026-06-10-commontrace-vision-strategy-design.md` line 126

- [ ] **Step 1: Verify the shipped mechanism before amending**

```bash
grep -n "_write_pending\|pending" /tmp/ct-skill/hooks/stop.py | head
```

Confirm the pending-queue mechanism exists; if its name differs, describe what actually ships.

- [ ] **Step 2: Replace line 126**

Old line claims `(`local_knowledge` table exists)` — that table never existed. New line:

```
- **Local-first capture is the funnel-saver:** uninvited users' agents still record everything locally — error signatures with resolution payloads in `local.db`, plus a pending-submission queue (`~/.commontrace/pending/`) that preserves contribution drafts when publishing is unavailable. Nothing is lost mid-session. Invitation unlocks *publishing*, not capturing — "You've been invited. N traces ready to share." Instant corpus contribution + instant status moment. *(Amended 2026-06-11: original text claimed a `local_knowledge` table that never existed; corrected to the shipped mechanism.)*
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-10-commontrace-vision-strategy-design.md
git commit -m "docs(spec): fix §6.4 funnel-saver wording — no local_knowledge table exists"
```

---

### Task 8: End-to-end verification — controller-direct

- [ ] **Step 1: Bring up the stack**

```bash
cd /home/denem/commontrace && docker compose -f docker-compose.yml -f docker-compose.override.yml -f /tmp/ct-e2e-ports.yml up -d --build
```

Wait for API healthy on localhost:8000. Then `alembic current` inside the api container → expect `220a1b2c3d4e (head)`.

- [ ] **Step 2: Search-miss logging**

Register a key (`POST /api/v1/keys`), search `{"tags": ["zzz-no-such-tag"], "context": {"language": "python", "framework": "fastapi"}}` → `total: 0`; then `SELECT query_text, tags, language, framework FROM search_misses` in psql → one row with tags `zzz-no-such-tag`, language `python`, framework `fastapi`.

- [ ] **Step 3: Topic counters**

Make the user a contributor (admin mint + redeem, or direct `UPDATE users SET can_contribute = true`), add email, submit a tagged trace, search for it, then `GET /api/v1/analytics/topics` → the tag appears with `new_traces_7d >= 1` (and `retrievals_7d >= 1` if the search returned it).

- [ ] **Step 4: Assisted-resolution telemetry**

POST counters-bearing payload:

```json
{"session_id": "e2e-test", "trigger_stats": {"error_search": {"fired": 4, "consumed": 2}}, "searches_fired": 4, "traces_consumed": 2, "resolutions_total": 3, "resolutions_assisted": 2}
```

→ 201. `GET /api/v1/analytics/assisted-resolution` → `sessions_reporting: 1`, `assisted_resolution_rate: 0.5`. Then rollout safety: old-style POST without counters → 201, and the rate endpoint still reports `sessions_reporting: 1` (NULL row excluded).

- [ ] **Step 5: Provenance**

`GET /api/v1/traces/{id}` and search both return `contributor_name` = `anon-<8hex>` (no display_name set on test users).

- [ ] **Step 6: Teardown**

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml -f /tmp/ct-e2e-ports.yml down -v
```

---

## Out of scope (sequenced per spec §10, not skipped)

Phase 2/3 items stay sequenced: auto-kudos, identity claim/handles, amendments accept/reject UI, Wanted Board UI (the table shipped here is its data source), user pages, Discussions, manifesto page, trace genealogy. §4.1's epsilon exploration floor already shipped (post_tool_use.py:125-176). Known pre-existing quirk, not fixed here: `/analytics/triggers` sums cumulative per-project trigger stats across sessions (double-counts); the new counters are session-scoped by design and don't inherit that flaw.
