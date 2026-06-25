# Savings & Impact (Server) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the server-side surface for the Savings & Impact system — an append-only anonymized `savings_ledger`, `POST /telemetry/savings` (identity/content-free ingest), `GET /analytics/savings` (global sums for the frontend counter), `tokens_to_resolution` passthrough into trace `metadata_json` at contribution time, and an owner-scoped outbound-impact query.

**Architecture:** A new append-only `savings_ledger` table stores only anonymized rows `(id, minutes_saved, tokens_saved, event_type, created_at)` — no user id, no trace id, no content. The ingest endpoint is authenticated by API key **for rate-limiting only** (mirroring `telemetry.py`); the authenticated user is never written to the row. The analytics endpoint extends the existing aggregate-only `analytics.py` surface with `SUM/SUM/COUNT`. `tokens_to_resolution` rides into the existing `metadata_json` JSON column via the contribution path (no DB schema change). The outbound-impact query sums `tokens_to_resolution * retrieval_count` (and the time equivalent) **only over the caller's own traces**, returned only for that authenticated key. Every savings figure is a **measured token count** (carried from the contributor's transcript, or summed from anonymized client increments) or a **published price constant on the frontend** — **no LLM is ever asked "how much did this save"** (the product's structural-intelligence rule). The server stores and sums raw token/minute integers; it neither generates nor multiplies by any model.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async (asyncpg), Alembic, PostgreSQL, Pydantic v2, pytest + pytest-asyncio (`asyncio_mode = "auto"`), Alembic `op` offline DDL emission for migration tests.

---

## Test strategy (CI-compatible — read before writing any test)

The CI job runs `pytest tests/ -q` inside `api/` with only `pip install -e ".[dev]"` and **no database** (`.github/workflows/ci.yml`; the `DATABASE_URL` is a dummy that only satisfies `Settings`, the workflow comment states "Pure-unit tests don't connect"). The only existing test, `api/tests/test_wilson_score.py`, is a pure-unit test with no DB and no async.

Therefore **every test in this plan must run without a live DB**, mirroring the sibling `ops/` suite (`ops/tests/test_db.py`, `ops/tests/conftest.py`), which is the repo's established async-DB-test pattern:

1. **`asyncio_mode = "auto"`** is added to `api/pyproject.toml` so `async def test_*` functions run without per-test decorators (exactly as `ops/pyproject.toml` does). Today `api/` has no such config, so async tests would be skipped/errored — Task 0 fixes this first.
2. **Fake session, not a real engine.** A `FakeDbSession` (a hand-written stand-in for `AsyncSession` exposing `execute()` / `add()` / `commit()`) feeds canned result rows and records what was added — the same shape as `ops`' `FakeConn`. We assert on the SQL/values built and the response dict shaped, never on a real Postgres round-trip. This keeps pgvector/JSONB out of CI (the `traces` table has `Vector(1536)` columns that cannot be created on SQLite).
3. **Anonymization is proven by object inspection.** A pure helper `build_ledger_row(body) -> SavingsLedger` is the unit under test; we assert the constructed ORM object exposes only `minutes_saved`, `tokens_saved`, `event_type` (plus server-assigned `id`/`created_at`) and carries **no** `contributor_id` / `user_id` / `session_id` / text attribute — the privacy guarantee is structural and testable with zero DB.
4. **Migration up/down is proven offline.** Alembic `op` is bound to a SQL-emitting `MigrationContext` (`as_sql=True`, Postgres dialect, no connection) and the emitted DDL string is asserted to create/drop the table and its exact columns — no DB needed.

This plan does **not** introduce SQLite/aiosqlite (the ORM's `Vector`/`JSONB`/`postgresql.UUID` columns make a full metadata `create_all` non-portable, and the fake-session pattern is already what the repo uses for `ops`).

## Existing patterns you must reuse (do not reinvent)

- **Anonymized telemetry ingest shape:** `api/app/routers/telemetry.py:42-60` (`report_trigger_stats`) — `body: <Model>`, `user: CurrentUser`, `db: DbSession`, `_rate: WriteRateLimit`; build a model, `db.add(record)`, `await db.commit()`. The `user` is consumed **only** for auth/rate-limit; it is never written into the row. `POST /telemetry/savings` mirrors this exactly.
- **Aggregate-only analytics:** `api/app/routers/analytics.py` — unauthenticated, returns dicts of integers. The existing total-retrievals aggregate at `analytics.py:106-110` (`select(func.coalesce(func.sum(Trace.retrieval_count), 0))`) is the template for the global savings sums.
- **`CurrentUser` / `DbSession` / `WriteRateLimit` aliases:** `api/app/dependencies.py:66`, `:31`, and `api/app/middleware/rate_limiter.py:139`.
- **Pydantic request model with bounded ints:** `api/app/routers/telemetry.py:29-35` (`Field(default=None, ge=0)`).
- **ORM model for an anonymized telemetry table:** `api/app/models/trigger_stats.py` — `UUID(as_uuid=True)` pk with `default=uuid.uuid4`, `DateTime(timezone=True)` with `server_default=func.now()`.
- **Migration style:** `api/app/migrations/versions/0021_search_misses.py` (`op.create_table` + `op.create_index`, matching `downgrade`). The naming convention (`base.py:5-11`) means the new index name will be `ix_savings_ledger_created_at`.
- **Models registry:** `api/app/models/__init__.py` — import + add to `__all__`.
- **Metadata passthrough at contribution:** `api/app/routers/traces.py:96-99` — `auto_enrich_metadata(body.metadata_json, body.solution_text)` then `trace.metadata_json = enriched`. `tokens_to_resolution` flows through this dict; the enrichment helper must preserve it (it already copies the dict via `dict(metadata)` at `enrichment.py:230`, so a passthrough test pins that behavior).

## Migration chain head (verified)

The current Alembic head is **`220a1b2c3d4e`** (`0022_assisted_resolution_telemetry.py:21`). Nothing revises it (`grep` for `down_revision.*220a1b2c3d4e` returns nothing). The new migration `0023_savings_ledger.py` uses `revision = "230a1b2c3d4e"`, `down_revision = "220a1b2c3d4e"`, following the established `NN0a1b2c3d4e` id scheme.

## Scope notes

- **Work directly on `main`** in `/home/denem/commontrace` (user-approved for this repo per the prior contribution-gate plan). One commit per task. **NEVER `git push`** — production auto-deploys from `origin/main`.
- Out of scope (other phases / repos): skill-side token-window instrument and `savings_events` local table (spec phases 1-3, commontrace/skill), the frontend counter + i18n (spec phase 5, commontrace/frontend), MCP changes. This plan is **spec phase 4** plus the server passthrough that phase-1 skill work depends on.
- Always syntax-check before committing: `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.

---

## File Structure

| File | Create/Modify/Test | Responsibility |
|------|--------------------|----------------|
| `api/pyproject.toml` | Modify | Add `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` so async tests run in CI. |
| `api/app/models/savings_ledger.py` | Create | `SavingsLedger` ORM model — append-only anonymized row (id, minutes_saved, tokens_saved, event_type, created_at). |
| `api/app/models/__init__.py` | Modify | Register `SavingsLedger` in imports + `__all__`. |
| `api/migrations/versions/0023_savings_ledger.py` | Create | Alembic migration: create/drop `savings_ledger` + `ix_savings_ledger_created_at`; chains `220a1b2c3d4e`. |
| `api/app/schemas/savings.py` | Create | `SavingsIngest` request schema (`extra="forbid"`, bounded ints) + `build_ledger_row` pure helper + `OutboundImpactResponse` response schema. |
| `api/app/routers/telemetry.py` | Modify | Add `POST /telemetry/savings` — auth for rate-limit only, persists anonymized row. |
| `api/app/routers/analytics.py` | Modify | Add `GET /analytics/savings` — global `SUM(minutes)`, `SUM(tokens)`, `COUNT(*)`. |
| `api/app/schemas/trace.py` | Modify | Add optional `tokens_to_resolution` to `TraceCreate` (kept inside `metadata_json` passthrough; no new DB column). |
| `api/app/services/enrichment.py` | Modify | `auto_enrich_metadata` preserves a caller-supplied `tokens_to_resolution`; add `coerce_tokens_to_resolution` helper used by the contribution router. |
| `api/app/routers/traces.py` | Modify | Fold `body.tokens_to_resolution` into `metadata_json` before enrichment so the measured count rides with the trace. |
| `api/app/services/outbound_impact.py` | Create | `compute_outbound_impact(db, contributor_id) -> dict` — owner-scoped `SUM(tokens_to_resolution * retrieval_count)` + time equivalent. |
| `api/app/routers/analytics.py` | Modify | Add `GET /traces/impact/outbound` (authenticated, owner-only) calling `compute_outbound_impact`. *(Lives on the search/traces auth surface — see Task 7 for exact router choice.)* |
| `api/tests/conftest.py` | Create | `FakeDbSession`, `FakeResult`, and a `make_user()` factory — the no-DB async test harness mirroring `ops/tests/conftest.py`. |
| `api/tests/test_savings_ledger_model.py` | Test | `SavingsLedger` columns + `build_ledger_row` carries no identity/content. |
| `api/tests/test_migration_0023_savings_ledger.py` | Test | Revision chain + offline up/down DDL creates/drops the right table & columns. |
| `api/tests/test_telemetry_savings.py` | Test | `POST /telemetry/savings` persists an anonymized row (no identity/content) and returns `{"status": "ok"}`. |
| `api/tests/test_analytics_savings.py` | Test | `GET /analytics/savings` returns the global `{minutes_saved, tokens_saved, events}` shape. |
| `api/tests/test_trace_tokens_to_resolution.py` | Test | `tokens_to_resolution` is accepted into `metadata_json` and preserved through enrichment. |
| `api/tests/test_outbound_impact.py` | Test | Outbound query shape + that it filters by `contributor_id` (owner-only scoping). |

---

### Task 0: Enable async tests in CI (`asyncio_mode = "auto"`)

**Files:**
- Modify: `api/pyproject.toml` (append a new `[tool.pytest.ini_options]` table)
- Test: `api/tests/test_asyncio_mode_enabled.py` (Create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_asyncio_mode_enabled.py`:

```python
"""Guards that async tests actually run in CI.

Without `asyncio_mode = "auto"` in pyproject, an `async def test_*`
is collected but not awaited (pytest-asyncio default is "strict"),
so its body never executes and false-passes. This test fails loudly
unless auto mode is configured.
"""

import asyncio


async def test_event_loop_is_running():
    # Only true if pytest-asyncio actually drove this coroutine.
    loop = asyncio.get_running_loop()
    assert loop.is_running()
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_asyncio_mode_enabled.py -q
```

Expected failure (strict mode, the default when no config is present): pytest-asyncio reports the coroutine was never awaited, e.g.

```
async def functions are not natively supported.
You need to install a suitable plugin for your async framework, for example:
  - anyio
  - pytest-asyncio
...
1 error in ...
```

(If pytest-asyncio is installed but in `strict` mode, the error is `async def function and no "asyncio" marker` / "coroutine ... was never awaited" — either way it does not PASS.)

- [ ] **Step 3: Add the config**

Append to `api/pyproject.toml` (after the existing `[tool.hatch.build.targets.wheel]` table, end of file):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_asyncio_mode_enabled.py tests/test_wilson_score.py -q
```

Expected: `2 passed` (the new async test passes and the existing sync unit test still passes).

- [ ] **Step 5: Commit**

```
git add api/pyproject.toml api/tests/test_asyncio_mode_enabled.py && git commit -m "test(api): enable pytest-asyncio auto mode for async server tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 1: No-DB async test harness (`conftest.py`)

**Files:**
- Create: `api/tests/conftest.py`
- Test: `api/tests/test_conftest_fakes.py` (Create — self-test of the fakes)

This harness mirrors `ops/tests/conftest.py` (`FakeConn`/`FakeResponse`). It provides a fake SQLAlchemy async session and result object so endpoint and query tests run with **no database**. Every later task imports from here.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_conftest_fakes.py`:

```python
"""Self-test for the no-DB fake session harness."""

import uuid

from tests.conftest import FakeDbSession, FakeResult, make_user


async def test_fake_result_scalar_and_fetchone():
    res = FakeResult(scalar_value=7, rows=[(1, 2, 3)])
    assert res.scalar() == 7
    assert res.scalar_one() == 7
    assert res.fetchone() == (1, 2, 3)


async def test_fake_session_records_added_objects_and_commits():
    db = FakeDbSession(results=[FakeResult(scalar_value=0)])
    sentinel = object()
    db.add(sentinel)
    await db.execute("SELECT 1")
    await db.commit()
    assert db.added == [sentinel]
    assert db.commits == 1
    assert db.executed[0][0] == "SELECT 1"


def test_make_user_has_id_and_no_secrets_leaked():
    u = make_user()
    assert isinstance(u.id, uuid.UUID)
    assert u.can_contribute is True
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_conftest_fakes.py -q
```

Expected failure: `ModuleNotFoundError: No module named 'tests.conftest'` has the symbols — actually `ImportError: cannot import name 'FakeDbSession' from 'tests.conftest'` (the file does not yet define them).

- [ ] **Step 3: Write the harness**

Create `api/tests/conftest.py`:

```python
"""No-DB async test harness for the API.

CI runs `pytest tests/ -q` with no database (see .github/workflows/ci.yml).
These fakes stand in for SQLAlchemy's AsyncSession / Result so router and
query logic can be tested by feeding canned rows and inspecting what was
built — the same approach as ops/tests/conftest.py (FakeConn/FakeResponse).
"""

import uuid
from types import SimpleNamespace
from typing import Any, Optional


class FakeResult:
    """Stand-in for a SQLAlchemy Result / Row collection.

    Supports the access shapes used by the routers under test:
      - .scalar() / .scalar_one() / .scalar_one_or_none() -> scalar_value
      - .fetchone() -> first row (or None)
      - .fetchall() -> all rows
      - .all() -> all rows
    """

    def __init__(self, scalar_value: Any = None, rows: Optional[list] = None):
        self._scalar = scalar_value
        self._rows = list(rows) if rows is not None else []

    def scalar(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def all(self):
        return list(self._rows)


class FakeDbSession:
    """Stand-in for AsyncSession.

    `results` is a FIFO queue: each `await execute(...)` pops the next
    FakeResult. `add()` appends to `.added`; `commit()` increments `.commits`.
    Every executed statement (and its params) is recorded in `.executed`.
    """

    def __init__(self, results: Optional[list] = None):
        self._results = list(results) if results is not None else []
        self.added: list = []
        self.executed: list = []
        self.commits: int = 0
        self.refreshed: list = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, statement, params=None):
        self.executed.append((statement, params))
        if self._results:
            return self._results.pop(0)
        return FakeResult()

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    async def refresh(self, obj):
        self.refreshed.append(obj)


def make_user(can_contribute: bool = True, email: str = "tester@example.com"):
    """Minimal stand-in for a User row (only the attributes routers read)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        can_contribute=can_contribute,
        display_name=None,
        country_code=None,
    )
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_conftest_fakes.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add api/tests/conftest.py api/tests/test_conftest_fakes.py && git commit -m "test(api): no-DB async fake session harness for server tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `SavingsLedger` model + `build_ledger_row` (anonymized, no identity/content)

**Files:**
- Create: `api/app/models/savings_ledger.py`
- Modify: `api/app/models/__init__.py` (imports + `__all__`)
- Create (the helper lives in the schema module, written here so the model test can import it): `api/app/schemas/savings.py`
- Test: `api/tests/test_savings_ledger_model.py` (Create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_savings_ledger_model.py`:

```python
"""SavingsLedger is append-only and anonymized.

The privacy guarantee (docs/privacy-what-is-shared.md): the server stores
only (minutes, tokens, event_type, created_at) — never identity or content.
We prove it structurally by inspecting the ORM column set and by building a
row from a request body and asserting no identity/content attribute exists.
"""

from app.models.savings_ledger import SavingsLedger
from app.schemas.savings import SavingsIngest, build_ledger_row

ALLOWED_COLUMNS = {"id", "minutes_saved", "tokens_saved", "event_type", "created_at"}
FORBIDDEN_COLUMNS = {
    "contributor_id", "user_id", "session_id", "trace_id", "signature",
    "title", "context_text", "solution_text", "api_key_hash", "email",
}


def test_table_name_is_savings_ledger():
    assert SavingsLedger.__tablename__ == "savings_ledger"


def test_columns_are_exactly_the_anonymized_set():
    cols = {c.name for c in SavingsLedger.__table__.columns}
    assert cols == ALLOWED_COLUMNS


def test_no_identity_or_content_columns():
    cols = {c.name for c in SavingsLedger.__table__.columns}
    assert cols & FORBIDDEN_COLUMNS == set()


def test_build_ledger_row_copies_only_allowed_fields():
    body = SavingsIngest(minutes_saved=12, tokens_saved=3400, event_type="measured_recurrence")
    row = build_ledger_row(body)
    assert isinstance(row, SavingsLedger)
    assert row.minutes_saved == 12
    assert row.tokens_saved == 3400
    assert row.event_type == "measured_recurrence"
    # No identity/content was attached, even if a malicious extra slipped through.
    for forbidden in FORBIDDEN_COLUMNS:
        assert getattr(row, forbidden, None) is None
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_savings_ledger_model.py -q
```

Expected failure: `ModuleNotFoundError: No module named 'app.models.savings_ledger'`.

- [ ] **Step 3: Write the model + schema helper**

Create `api/app/models/savings_ledger.py`:

```python
"""Savings ledger model — append-only, anonymized.

Each row is one booked saving increment reported by a skill client:
minutes and tokens saved, plus a coarse event_type label. It carries
NO user id, NO trace id, NO content — only the anonymized aggregate the
frontend counter sums. This mirrors the privacy envelope already used by
trigger_stats (anonymized telemetry) and matches docs/privacy-what-is-shared.md
("usage telemetry is anonymized aggregate counts only").
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SavingsLedger(Base):
    __tablename__ = "savings_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    minutes_saved: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    tokens_saved: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Create `api/app/schemas/savings.py`:

```python
"""Schemas + pure builders for the savings surface.

`SavingsIngest` is the anonymized increment a skill client POSTs. It is
`extra="forbid"` so a client cannot smuggle identity/content fields into
the request — they are rejected at validation, never persisted.

`build_ledger_row` is a pure function (no DB) that maps the validated body
to a SavingsLedger ORM object, copying ONLY the three anonymized fields.
This is the unit the privacy test inspects.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.savings_ledger import SavingsLedger

# Coarse, closed set of event labels the skill books savings under.
# Validated as plain strings (bounded) — no free-form content.
ALLOWED_EVENT_TYPES = {
    "measured_recurrence",
    "proxy_consumption",
}


class SavingsIngest(BaseModel):
    """Anonymized savings increment from a skill client."""

    model_config = ConfigDict(extra="forbid")

    minutes_saved: int = Field(ge=0, le=120)
    tokens_saved: int = Field(ge=0, le=5_000_000)
    event_type: str = Field(min_length=1, max_length=40)


class SavingsIngestResponse(BaseModel):
    status: str = "ok"


class OutboundImpactResponse(BaseModel):
    """What the caller's own traces saved everyone else (contributor side).

    Owner-scoped: returned only for the authenticated caller's traces.
    """

    tokens_saved_for_others: int = 0
    minutes_saved_for_others: int = 0
    trace_count: int = 0


def build_ledger_row(body: SavingsIngest) -> SavingsLedger:
    """Map a validated increment to an anonymized ledger row.

    Copies ONLY minutes_saved, tokens_saved, event_type. No identity or
    content is read or attached — the privacy guarantee is enforced here.
    """
    return SavingsLedger(
        minutes_saved=body.minutes_saved,
        tokens_saved=body.tokens_saved,
        event_type=body.event_type,
    )
```

Modify `api/app/models/__init__.py` — add the import after the `SearchMiss` import (line 15) and the name to `__all__` (after `"SearchMiss",` at line 36):

```python
from .search_miss import SearchMiss
from .savings_ledger import SavingsLedger
```

and in `__all__`:

```python
    "SearchMiss",
    "SavingsLedger",
]
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('app/models/savings_ledger.py', doraise=True); py_compile.compile('app/schemas/savings.py', doraise=True); py_compile.compile('app/models/__init__.py', doraise=True)" && python -m pytest tests/test_savings_ledger_model.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add api/app/models/savings_ledger.py api/app/schemas/savings.py api/app/models/__init__.py api/tests/test_savings_ledger_model.py && git commit -m "feat(api): SavingsLedger model + anonymized ingest schema/builder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Alembic migration `0023_savings_ledger` (upgrade + downgrade, offline-tested)

**Files:**
- Create: `api/migrations/versions/0023_savings_ledger.py`
- Test: `api/tests/test_migration_0023_savings_ledger.py` (Create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_migration_0023_savings_ledger.py`:

```python
"""Migration 0023 chains the real head and creates/drops savings_ledger.

No DB: we (a) assert the revision chain, and (b) run upgrade()/downgrade()
against Alembic's OFFLINE SQL-emitting context (Postgres dialect, no
connection) and assert the emitted DDL touches the right table & columns.
"""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "0023_savings_ledger.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0023", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load_migration()
    assert mod.revision == "230a1b2c3d4e"
    assert mod.down_revision == "220a1b2c3d4e"


def _emit(direction: str) -> str:
    """Run upgrade()/downgrade() in offline mode, capturing emitted SQL."""
    mod = _load_migration()
    buf: list[str] = []

    ctx = MigrationContext.configure(
        dialect_name="postgresql",
        opts={
            "as_sql": True,
            "output_buffer": type(
                "W", (), {"write": lambda self, s: buf.append(s)}
            )(),
        },
    )
    ops = Operations(ctx)
    # alembic.op proxies the module-global Operations; bind ours for the call.
    import alembic.op as alembic_op
    token = alembic_op._proxy  # save
    try:
        alembic_op._proxy = ops
        getattr(mod, direction)()
    finally:
        alembic_op._proxy = token
    return "\n".join(buf).lower()


def test_upgrade_creates_table_and_columns():
    sql = _emit("upgrade")
    assert "create table" in sql
    assert "savings_ledger" in sql
    assert "minutes_saved" in sql
    assert "tokens_saved" in sql
    assert "event_type" in sql
    assert "created_at" in sql
    assert "ix_savings_ledger_created_at" in sql


def test_downgrade_drops_table_and_index():
    sql = _emit("downgrade")
    assert "drop" in sql
    assert "savings_ledger" in sql
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_migration_0023_savings_ledger.py -q
```

Expected failure: `FileNotFoundError` / the `spec.loader.exec_module` raises because `migrations/versions/0023_savings_ledger.py` does not exist yet (collection error on `test_revision_chain`).

- [ ] **Step 3: Write the migration**

Create `api/migrations/versions/0023_savings_ledger.py`:

```python
"""Create savings_ledger table.

Append-only, anonymized savings increments from skill clients (Savings &
Impact system, spec phase 4). Each row: minutes_saved, tokens_saved,
event_type, created_at. NO user, NO trace, NO content — matches the
anonymized-telemetry privacy envelope (docs/privacy-what-is-shared.md).

Revision ID: 230a1b2c3d4e
Revises: 220a1b2c3d4e
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "230a1b2c3d4e"
down_revision: str = "220a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("minutes_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_saved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_savings_ledger_created_at", "savings_ledger", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_savings_ledger_created_at", table_name="savings_ledger")
    op.drop_table("savings_ledger")
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('migrations/versions/0023_savings_ledger.py', doraise=True)" && python -m pytest tests/test_migration_0023_savings_ledger.py -q
```

Expected: `3 passed`.

> Note for the implementer: if `alembic.op._proxy` is not the attribute name in the installed Alembic version, the offline-emit fallback is `op._install_proxy(ops)` / `op._remove_proxy()`. Confirm with `python -c "import alembic.op as o; print([a for a in dir(o) if 'proxy' in a.lower()])"` and adjust the two `_proxy` lines accordingly before Step 4. The DDL assertions do not change.

- [ ] **Step 5: Commit**

```
git add api/migrations/versions/0023_savings_ledger.py api/tests/test_migration_0023_savings_ledger.py && git commit -m "feat(api): migration 0023 — append-only savings_ledger table

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `POST /telemetry/savings` (auth for rate-limit only; no identity/content persisted)

**Files:**
- Modify: `api/app/routers/telemetry.py` (add endpoint + imports at the end of the file)
- Test: `api/tests/test_telemetry_savings.py` (Create)

The endpoint mirrors `report_trigger_stats` (`telemetry.py:42-60`): `user: CurrentUser` is present **only** for auth + rate-limit; the row is built by `build_ledger_row(body)` and contains nothing from `user`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_telemetry_savings.py`:

```python
"""POST /telemetry/savings persists an anonymized row only.

We call the endpoint coroutine directly with a FakeDbSession and a fake
user, then assert: (1) exactly one row added, (2) it is a SavingsLedger
carrying only minutes/tokens/event_type, (3) NOTHING from the user
(id/email) was written, (4) commit happened, (5) response is {"status":"ok"}.
"""

from app.models.savings_ledger import SavingsLedger
from app.routers.telemetry import report_savings
from app.schemas.savings import SavingsIngest
from tests.conftest import FakeDbSession, make_user


async def test_persists_anonymized_row_and_returns_ok():
    db = FakeDbSession()
    user = make_user()
    body = SavingsIngest(minutes_saved=9, tokens_saved=2100, event_type="proxy_consumption")

    resp = await report_savings(body=body, user=user, db=db, _rate=None)

    assert db.commits == 1
    assert len(db.added) == 1
    row = db.added[0]
    assert isinstance(row, SavingsLedger)
    assert (row.minutes_saved, row.tokens_saved, row.event_type) == (9, 2100, "proxy_consumption")
    assert resp.status == "ok"


async def test_user_identity_is_never_written_to_the_row():
    db = FakeDbSession()
    user = make_user(email="someone@real.example")
    body = SavingsIngest(minutes_saved=1, tokens_saved=10, event_type="measured_recurrence")

    await report_savings(body=body, user=user, db=db, _rate=None)

    row = db.added[0]
    # No attribute equals the user's id or email.
    leaked = [
        name for name in vars(row)
        if getattr(row, name, None) in {user.id, user.email}
    ]
    assert leaked == []
    # And the canonical identity column names simply do not exist on the row.
    for forbidden in ("contributor_id", "user_id", "session_id", "email"):
        assert getattr(row, forbidden, None) is None


def test_request_schema_rejects_smuggled_identity_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SavingsIngest(
            minutes_saved=1, tokens_saved=10, event_type="measured_recurrence",
            contributor_id="00000000-0000-0000-0000-000000000000",  # extra="forbid"
        )
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_telemetry_savings.py -q
```

Expected failure: `ImportError: cannot import name 'report_savings' from 'app.routers.telemetry'`.

- [ ] **Step 3: Add the endpoint**

In `api/app/routers/telemetry.py`, extend the import block (the existing line `from app.models.trigger_stats import TriggerStats` at line 18) by adding below it:

```python
from app.schemas.savings import (
    SavingsIngest,
    SavingsIngestResponse,
    build_ledger_row,
)
```

Then append at the end of the file (after the `ping` handler):

```python
# ---------------------------------------------------------------------------
# Savings ledger (anonymized increments — Savings & Impact, spec phase 4)
# ---------------------------------------------------------------------------


@router.post("/savings", response_model=SavingsIngestResponse, status_code=201)
async def report_savings(
    body: SavingsIngest,
    user: CurrentUser,
    db: DbSession,
    _rate: WriteRateLimit,
) -> SavingsIngestResponse:
    """Accept one anonymized savings increment from a skill client.

    Authenticated by API key for rate-limiting only — the user is NEVER
    written to the row. Persists exactly (minutes_saved, tokens_saved,
    event_type); no identity, no trace linkage, no content. Mirrors the
    anonymized-telemetry envelope of report_trigger_stats.
    """
    db.add(build_ledger_row(body))
    await db.commit()
    return SavingsIngestResponse()
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('app/routers/telemetry.py', doraise=True)" && python -m pytest tests/test_telemetry_savings.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add api/app/routers/telemetry.py api/tests/test_telemetry_savings.py && git commit -m "feat(api): POST /telemetry/savings — anonymized savings ingest

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `GET /analytics/savings` (global SUM/SUM/COUNT for the frontend counter)

**Files:**
- Modify: `api/app/routers/analytics.py` (add endpoint + import; reuse `func`, `select` already imported at line 23)
- Test: `api/tests/test_analytics_savings.py` (Create)

This extends the aggregate-only surface. It mirrors the existing total-retrievals aggregate (`analytics.py:106-110`) but over `SavingsLedger`. Three values: `SUM(minutes_saved)`, `SUM(tokens_saved)`, `COUNT(*)`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_analytics_savings.py`:

```python
"""GET /analytics/savings returns the global savings shape.

No DB: feed three FakeResults (minutes sum, tokens sum, count) in the order
the handler queries them, and assert the response dict shape + values. The
endpoint is aggregate-only and unauthenticated (it takes only `db`).
"""

from app.routers.analytics import get_savings
from tests.conftest import FakeDbSession, FakeResult


async def test_returns_global_minutes_tokens_events():
    db = FakeDbSession(results=[
        FakeResult(scalar_value=540),      # SUM(minutes_saved)
        FakeResult(scalar_value=128_000),  # SUM(tokens_saved)
        FakeResult(scalar_value=37),       # COUNT(*)
    ])

    out = await get_savings(db=db)

    assert out == {
        "minutes_saved": 540,
        "tokens_saved": 128_000,
        "events": 37,
    }


async def test_empty_ledger_returns_zeros():
    db = FakeDbSession(results=[
        FakeResult(scalar_value=None),  # COALESCE handles NULL -> 0 in prod;
        FakeResult(scalar_value=None),  # the handler must also int(None or 0).
        FakeResult(scalar_value=0),
    ])

    out = await get_savings(db=db)

    assert out == {"minutes_saved": 0, "tokens_saved": 0, "events": 0}
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_analytics_savings.py -q
```

Expected failure: `ImportError: cannot import name 'get_savings' from 'app.routers.analytics'`.

- [ ] **Step 3: Add the endpoint**

In `api/app/routers/analytics.py`, add to the model imports (after `from app.models.vote import Vote` at line 30):

```python
from app.models.savings_ledger import SavingsLedger
```

Then append at the end of the file (after `get_assisted_resolution`):

```python
@router.get("/savings")
async def get_savings(db: DbSession) -> dict:
    """Global savings totals for the frontend counter (Savings & Impact).

    Aggregate-only, unauthenticated — sums anonymized ledger rows. No identity
    or content is touched; the rows have none.
    """
    minutes_result = await db.execute(
        select(func.coalesce(func.sum(SavingsLedger.minutes_saved), 0))
    )
    tokens_result = await db.execute(
        select(func.coalesce(func.sum(SavingsLedger.tokens_saved), 0))
    )
    count_result = await db.execute(
        select(func.count()).select_from(SavingsLedger)
    )
    return {
        "minutes_saved": int(minutes_result.scalar() or 0),
        "tokens_saved": int(tokens_result.scalar() or 0),
        "events": int(count_result.scalar() or 0),
    }
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('app/routers/analytics.py', doraise=True)" && python -m pytest tests/test_analytics_savings.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add api/app/routers/analytics.py api/tests/test_analytics_savings.py && git commit -m "feat(api): GET /analytics/savings — global savings counter aggregate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Accept + persist `tokens_to_resolution` into `metadata_json` at contribution

**Files:**
- Modify: `api/app/schemas/trace.py` (add `tokens_to_resolution` to `TraceCreate`)
- Modify: `api/app/services/enrichment.py` (add `coerce_tokens_to_resolution`; confirm `auto_enrich_metadata` preserves it)
- Modify: `api/app/routers/traces.py` (fold the field into `metadata_json` before enrichment)
- Test: `api/tests/test_trace_tokens_to_resolution.py` (Create)

No DB schema change — `metadata_json` is the existing JSON column (`models/trace.py:56`). The skill sends `tokens_to_resolution` either nested in `metadata_json` (preferred) or as a top-level convenience field; both must end up inside the persisted `metadata_json` so the cross-user proxy number is the contributor's real measured count.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_trace_tokens_to_resolution.py`:

```python
"""tokens_to_resolution rides into metadata_json at contribution time.

Two ingress shapes must both land in the persisted metadata dict:
  (a) top-level body field `tokens_to_resolution`
  (b) already nested inside `metadata_json`
And enrichment must not drop it.
"""

from app.schemas.trace import TraceCreate
from app.services.enrichment import auto_enrich_metadata, coerce_tokens_to_resolution


def test_schema_accepts_top_level_tokens_to_resolution():
    body = TraceCreate(
        title="x", context_text="c", solution_text="s",
        tokens_to_resolution=4200,
    )
    assert body.tokens_to_resolution == 4200


def test_coerce_folds_top_level_field_into_metadata():
    meta = coerce_tokens_to_resolution({"language": "python"}, 4200)
    assert meta["tokens_to_resolution"] == 4200
    assert meta["language"] == "python"


def test_coerce_preserves_already_nested_value_when_no_top_level():
    meta = coerce_tokens_to_resolution({"tokens_to_resolution": 999}, None)
    assert meta["tokens_to_resolution"] == 999


def test_coerce_top_level_takes_precedence_and_handles_none_meta():
    meta = coerce_tokens_to_resolution(None, 1234)
    assert meta == {"tokens_to_resolution": 1234}


def test_enrichment_preserves_tokens_to_resolution():
    enriched = auto_enrich_metadata({"tokens_to_resolution": 4200}, "print('hi')")
    assert enriched["tokens_to_resolution"] == 4200


def test_negative_tokens_rejected_by_schema():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TraceCreate(title="x", context_text="c", solution_text="s", tokens_to_resolution=-1)
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_trace_tokens_to_resolution.py -q
```

Expected failure: `ImportError: cannot import name 'coerce_tokens_to_resolution' from 'app.services.enrichment'` (and `TraceCreate` has no `tokens_to_resolution`).

- [ ] **Step 3: Implement**

In `api/app/schemas/trace.py`, add the field to `TraceCreate` (after `watch_condition` at line 23):

```python
    tokens_to_resolution: Optional[int] = Field(default=None, ge=0, le=50_000_000)
```

In `api/app/services/enrichment.py`, add this helper (place it directly above `auto_enrich_metadata` at line 224):

```python
def coerce_tokens_to_resolution(
    metadata: Optional[dict], top_level: Optional[int]
) -> dict:
    """Fold a measured tokens_to_resolution count into the metadata dict.

    The skill may send the count as a top-level body field or already nested
    in metadata_json. A top-level value (when present) takes precedence so the
    contributor's real measured token count rides with the trace. Returns a new
    dict; never mutates the input.
    """
    meta = dict(metadata) if metadata else {}
    if top_level is not None:
        meta["tokens_to_resolution"] = top_level
    return meta
```

`auto_enrich_metadata` already preserves arbitrary keys because it starts from `dict(metadata)` (`enrichment.py:230`) and only *adds* language/framework — so `tokens_to_resolution` survives unchanged. No edit needed there; the passthrough test (`test_enrichment_preserves_tokens_to_resolution`) pins this so a future refactor can't silently drop it.

In `api/app/routers/traces.py`, fold the field in **before** enrichment. Add the import to the enrichment import line (line 21):

```python
from app.services.enrichment import auto_enrich_metadata, coerce_tokens_to_resolution, compute_depth_score, compute_impact_level, compute_somatic_intensity
```

Then change the metadata-build sequence. Replace lines 97-99:

```python
    tag_names = [normalize_tag(t) for t in body.tags if validate_tag(normalize_tag(t))]
    enriched = auto_enrich_metadata(body.metadata_json, body.solution_text)
    trace.metadata_json = enriched
```

with:

```python
    tag_names = [normalize_tag(t) for t in body.tags if validate_tag(normalize_tag(t))]
    base_meta = coerce_tokens_to_resolution(body.metadata_json, body.tokens_to_resolution)
    enriched = auto_enrich_metadata(base_meta, body.solution_text)
    trace.metadata_json = enriched
```

(The earlier `Trace(... metadata_json=body.metadata_json ...)` at line 62 is harmless — it is overwritten by `trace.metadata_json = enriched` before commit. Leave it as-is to minimize the diff; the persisted value is `enriched`.)

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('app/schemas/trace.py', doraise=True); py_compile.compile('app/services/enrichment.py', doraise=True); py_compile.compile('app/routers/traces.py', doraise=True)" && python -m pytest tests/test_trace_tokens_to_resolution.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```
git add api/app/schemas/trace.py api/app/services/enrichment.py api/app/routers/traces.py api/tests/test_trace_tokens_to_resolution.py && git commit -m "feat(api): carry tokens_to_resolution into trace metadata_json

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Owner-scoped outbound-impact query + endpoint

**Files:**
- Create: `api/app/services/outbound_impact.py`
- Modify: `api/app/routers/analytics.py` (add the authenticated, owner-only endpoint + imports)
- Test: `api/tests/test_outbound_impact.py` (Create)

**Where the endpoint lives:** `analytics.py` already imports `Trace`, `func`, `select`, `text` and is where retrieval aggregates live. The new endpoint is the **only authenticated, owner-scoped** route in that file, so it takes `user: CurrentUser` and a read rate limit, unlike the public analytics routes. It is mounted at `GET /api/v1/analytics/impact/outbound` (the `analytics` router prefix is `/api/v1/analytics`). The service function does the SQL; the endpoint passes `user.id` so the scope key is the authenticated caller and **never** another user's id.

`tokens_to_resolution` lives in the JSON `metadata_json` column. Postgres reads it via `(metadata_json ->> 'tokens_to_resolution')::bigint`. The query sums `that * retrieval_count` and the time equivalent `(metadata_json ->> 'time_to_resolution_minutes')::numeric * retrieval_count`, both filtered `WHERE contributor_id = :cid`, NULL-safe via `COALESCE`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_outbound_impact.py`:

```python
"""Outbound impact is owner-scoped and correctly shaped.

No DB: a FakeDbSession returns one aggregate row; we assert (1) the SQL is
filtered by contributor_id and references both metadata keys + retrieval_count,
(2) the bound param is the caller's id (owner-only), (3) the response shape.
"""

import uuid

from app.services.outbound_impact import compute_outbound_impact
from app.routers.analytics import get_outbound_impact
from tests.conftest import FakeDbSession, FakeResult, make_user


async def test_query_is_owner_scoped_and_shaped():
    cid = uuid.uuid4()
    # Aggregate row: (tokens_for_others, minutes_for_others, trace_count)
    db = FakeDbSession(results=[FakeResult(rows=[(54000, 320, 7)])])

    out = await compute_outbound_impact(db, cid)

    assert out == {
        "tokens_saved_for_others": 54000,
        "minutes_saved_for_others": 320,
        "trace_count": 7,
    }
    # The one statement executed must be filtered by the caller's id.
    stmt, params = db.executed[0]
    sql = str(stmt).lower()
    assert "contributor_id" in sql
    assert "retrieval_count" in sql
    assert "tokens_to_resolution" in sql
    assert "time_to_resolution_minutes" in sql
    assert params["cid"] == str(cid)


async def test_endpoint_passes_only_the_callers_own_id():
    db = FakeDbSession(results=[FakeResult(rows=[(0, 0, 0)])])
    user = make_user()

    resp = await get_outbound_impact(user=user, db=db, _rate=None)

    # The bound id is the authenticated caller's — never an arbitrary input.
    _, params = db.executed[0]
    assert params["cid"] == str(user.id)
    assert resp.tokens_saved_for_others == 0
    assert resp.minutes_saved_for_others == 0
    assert resp.trace_count == 0


async def test_null_aggregate_row_yields_zeros():
    db = FakeDbSession(results=[FakeResult(rows=[(None, None, 0)])])
    out = await compute_outbound_impact(db, uuid.uuid4())
    assert out == {
        "tokens_saved_for_others": 0,
        "minutes_saved_for_others": 0,
        "trace_count": 0,
    }
```

- [ ] **Step 2: Run the test — expect FAIL**

```
cd /home/denem/commontrace/api && python -m pytest tests/test_outbound_impact.py -q
```

Expected failure: `ModuleNotFoundError: No module named 'app.services.outbound_impact'`.

- [ ] **Step 3: Implement service + endpoint**

Create `api/app/services/outbound_impact.py`:

```python
"""Outbound-impact query — what the caller's OWN traces saved others.

Contributor side of the Savings & Impact system (spec phase 4). Sums, over
the caller's traces only:
  tokens_saved_for_others  = Σ( tokens_to_resolution * retrieval_count )
  minutes_saved_for_others = Σ( time_to_resolution_minutes * retrieval_count )
Both effort fields live in the JSON metadata_json column. The result is
returned ONLY for the authenticated caller's contributor_id — never another
user's (privacy: docs/privacy-what-is-shared.md). No content, no per-trace
who-helped-whom linkage leaves the query; only the caller's own rollup.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Read effort fields from metadata_json, multiply by retrieval_count, sum.
# COALESCE + NULLIF guards: missing/blank JSON keys contribute 0, never error.
_OUTBOUND_SQL = text(
    "SELECT "
    "  COALESCE(SUM("
    "    COALESCE(NULLIF(metadata_json ->> 'tokens_to_resolution', '')::bigint, 0)"
    "    * retrieval_count"
    "  ), 0) AS tokens_for_others, "
    "  COALESCE(SUM("
    "    COALESCE(NULLIF(metadata_json ->> 'time_to_resolution_minutes', '')::numeric, 0)"
    "    * retrieval_count"
    "  ), 0) AS minutes_for_others, "
    "  COUNT(*) AS trace_count "
    "FROM traces "
    "WHERE contributor_id = :cid"
)


async def compute_outbound_impact(
    db: AsyncSession, contributor_id: uuid.UUID
) -> dict:
    """Compute the owner-scoped outbound rollup for one contributor."""
    result = await db.execute(_OUTBOUND_SQL, {"cid": str(contributor_id)})
    row = result.fetchone()
    if row is None:
        return {
            "tokens_saved_for_others": 0,
            "minutes_saved_for_others": 0,
            "trace_count": 0,
        }
    tokens = int(row[0] or 0)
    minutes = int(row[1] or 0)
    count = int(row[2] or 0)
    return {
        "tokens_saved_for_others": tokens,
        "minutes_saved_for_others": minutes,
        "trace_count": count,
    }
```

In `api/app/routers/analytics.py`, add imports (after the `SavingsLedger` import added in Task 5):

```python
from app.dependencies import CurrentUser
from app.middleware.rate_limiter import ReadRateLimit
from app.schemas.savings import OutboundImpactResponse
from app.services.outbound_impact import compute_outbound_impact
```

Then append at the end of the file:

```python
@router.get("/impact/outbound", response_model=OutboundImpactResponse)
async def get_outbound_impact(
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> OutboundImpactResponse:
    """What the authenticated caller's OWN traces saved everyone else.

    Owner-scoped: the contributor_id is taken from the authenticated user —
    a caller can never query another user's outbound impact.
    """
    data = await compute_outbound_impact(db, user.id)
    return OutboundImpactResponse(
        tokens_saved_for_others=data["tokens_saved_for_others"],
        minutes_saved_for_others=data["minutes_saved_for_others"],
        trace_count=data["trace_count"],
    )
```

- [ ] **Step 4: Run the test — expect PASS**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile; py_compile.compile('app/services/outbound_impact.py', doraise=True); py_compile.compile('app/routers/analytics.py', doraise=True)" && python -m pytest tests/test_outbound_impact.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add api/app/services/outbound_impact.py api/app/routers/analytics.py api/tests/test_outbound_impact.py && git commit -m "feat(api): owner-scoped outbound-impact query + endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Full suite green + privacy doc cross-check

**Files:**
- Test: all of `api/tests/`
- Modify (docs only, if needed): `docs/privacy-what-is-shared.md` — verify the new surface is consistent; add a one-line code-map row only if it clarifies (no behavioral change).

- [ ] **Step 1: Run the whole API test suite**

```
cd /home/denem/commontrace/api && python -m pytest tests/ -q
```

Expected: all tests pass (existing `test_wilson_score.py` plus every test added in Tasks 0-7). Approximate count: 1 (wilson) + 1 (asyncio mode) + 3 (conftest) + 4 (model) + 3 (migration) + 3 (telemetry) + 2 (analytics) + 6 (tokens) + 3 (outbound) = **26 passed**.

- [ ] **Step 2: Confirm the CI invocation matches**

```
cd /home/denem/commontrace/api && DATABASE_URL=postgresql+asyncpg://test:test@localhost/test pytest tests/ -q
```

Expected: identical green result (this is the exact env + command `.github/workflows/ci.yml` runs; proves no test needs a live DB).

- [ ] **Step 3: Privacy-doc cross-check (read-only verification)**

Re-read `docs/privacy-what-is-shared.md` "What is NEVER shared publicly" section. Confirm the new endpoints do not contradict it:
- `savings_ledger` rows contain no identity/content (proved by `test_savings_ledger_model.py`).
- `/telemetry/savings` writes nothing from the user (proved by `test_telemetry_savings.py`).
- `/analytics/impact/outbound` returns only the caller's own rollup (proved by `test_outbound_impact.py`).

If — and only if — a clarifying line helps, add one row to the code-map table at the end of the doc:

```
| Anonymized savings telemetry + owner-only impact | `api/app/routers/telemetry.py` (`report_savings`), `api/app/routers/analytics.py` (`get_savings`, `get_outbound_impact`) |
```

- [ ] **Step 4: Final syntax sweep**

```
cd /home/denem/commontrace/api && python3 -c "import py_compile, glob; [py_compile.compile(f, doraise=True) for f in ['app/models/savings_ledger.py','app/schemas/savings.py','app/routers/telemetry.py','app/routers/analytics.py','app/schemas/trace.py','app/services/enrichment.py','app/routers/traces.py','app/services/outbound_impact.py','migrations/versions/0023_savings_ledger.py']]; print('all compile OK')"
```

Expected: `all compile OK`.

- [ ] **Step 5: Commit (docs only, if a line was added)**

```
git add docs/privacy-what-is-shared.md && git commit -m "docs(privacy): note anonymized savings telemetry + owner-only impact

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

If no doc line was added, skip this commit.

---

## Self-Review

### (a) Spec-coverage checklist

Mapping each server-scoped requirement from `docs/superpowers/specs/2026-06-14-savings-impact-system-design.md` (and the task brief) to a task:

| Spec requirement | Where in spec | Task |
|------------------|---------------|------|
| Append-only `savings_ledger` (id, minutes_saved, tokens_saved, event_type, created_at); anonymized rows only, no user/content/trace linkage | §"Components → Server" bullet 1; §"Storage & data flow"; brief item 1 | Task 2 (model) + Task 3 (migration) |
| Migration chains the real current head, with upgrade AND downgrade | brief item 1 | Task 3 (`revision 230a1b2c3d4e`, `down_revision 220a1b2c3d4e`; both `upgrade`+`downgrade`) |
| `POST /telemetry/savings` accepts `{minutes_saved, tokens_saved, event_type}`; authed by API key for rate-limiting only; persists without identity or content; mirrors telemetry.py anonymization | §"Components → Server" bullet 2; §"Storage & data flow" POST line; brief item 2 | Task 4 |
| `GET /analytics/savings` global `SUM(minutes)`, `SUM(tokens)`, `COUNT(*)` for the frontend counter; extends analytics.py | §"Surfaces" bullet 3; §"Components → Server" bullet 3; brief item 3 | Task 5 |
| Accept + persist `tokens_to_resolution` into trace `metadata_json` at contribution (no DB schema change; passthrough/enrichment) | §"Token instrument"; §"Components → Server" bullet 4; brief item 4 | Task 6 |
| Outbound-impact query for the authenticated caller only: `Σ(tokens_to_resolution × retrieval_count)` + time equivalent `Σ(time_to_resolution_minutes × retrieval_count)`; returned only for that key | §"Two directions of value → Outbound"; §"Components → Server" bullet 5; brief item 5 | Task 7 |
| Tests: `/telemetry/savings` stores no content/identity | §"Testing → Server"; brief | Task 4 (`test_user_identity_is_never_written_to_the_row`, schema `extra="forbid"`) + Task 2 (column-set proof) |
| Tests: global aggregate shape | §"Testing → Server" | Task 5 |
| Tests: `tokens_to_resolution` accepted into `metadata_json` | §"Testing → Server" | Task 6 |
| Tests: outbound query shape + owner-only scoping | §"Testing → Server" | Task 7 (`test_query_is_owner_scoped_and_shaped`, `test_endpoint_passes_only_the_callers_own_id`) |
| Tests: migration up/down | §"Testing → Server" | Task 3 |
| Privacy: server sees only anonymized aggregate (minutes, tokens, event_type), never "trace X helped user Y"; outbound returned only to the trace owner; must not contradict privacy doc | §"Privacy consistency"; brief | Tasks 2/4 (no-identity rows), Task 7 (owner scope), Task 8 (doc cross-check) |
| NO-LLM constraint: every savings number is a measured token count or a published price constant, never asked of a model | §"Core constraint"; brief | Stated in Architecture; enforced structurally — server only stores/sums integers (Tasks 4/5) and reads the contributor's measured `tokens_to_resolution` (Tasks 6/7). No model call anywhere; the price multiplier is a frontend constant (out of scope here). |

Items intentionally **out of scope** for this server plan (other spec phases/repos): skill token-window instrument + `savings_events` local table + session-start recap + `artifacts.py` breakdown (phases 1-3, commontrace/skill); frontend counter + i18n (phase 5, commontrace/frontend). These are named in Scope notes.

### (b) Placeholder scan result

Searched the plan for banned tokens: `TBD`, `TODO`, `implement later`, `add error handling`, `add validation`, `handle edge cases`, `write tests for the above`, `similar to Task N`, `...` as elision in code. **None present.** Every code step shows complete code; every test step shows the exact command and the expected FAIL/PASS line. The only `pass` is a real no-op method body (`FakeDbSession.flush`). The two `...`-free "Note for the implementer" blocks (Task 3 proxy-attr, Task 6 line-62 remark) are guidance, not placeholders, and the code they annotate is fully written.

### (c) Type / name consistency check

Every symbol referenced in a later task is defined earlier with a matching signature:
- `FakeDbSession`, `FakeResult`, `make_user` — defined Task 1 (`conftest.py`); used Tasks 4, 5, 7.
- `SavingsLedger` — defined Task 2 (`models/savings_ledger.py`); used Tasks 2, 4, 5 (analytics import), and the migration (Task 3) creates the matching table/columns (`minutes_saved` Integer, `tokens_saved` BigInteger, `event_type` String(40), `created_at` DateTime, `id` UUID) — model and DDL agree exactly.
- `SavingsIngest`, `SavingsIngestResponse`, `OutboundImpactResponse`, `build_ledger_row` — defined Task 2 (`schemas/savings.py`); `SavingsIngest`/`SavingsIngestResponse`/`build_ledger_row` used Task 4; `OutboundImpactResponse` used Task 7.
- `report_savings(body, user, db, _rate)` — defined Task 4; called directly in its test with `_rate=None`.
- `get_savings(db)` — defined Task 5; called in its test.
- `coerce_tokens_to_resolution(metadata, top_level)` — defined Task 6 (`enrichment.py`); used Task 6 router edit and tested in Task 6.
- `TraceCreate.tokens_to_resolution` — added Task 6; consumed by the router edit in the same task.
- `compute_outbound_impact(db, contributor_id)` — defined Task 7 (`outbound_impact.py`); used by `get_outbound_impact(user, db, _rate)` (also Task 7) and tested directly.
- Revision ids: `230a1b2c3d4e` / `220a1b2c3d4e` consistent between the migration (Task 3) and its test.
- Reused existing symbols verified against source: `CurrentUser` (`dependencies.py:66`), `DbSession` (`dependencies.py:31`), `WriteRateLimit`/`ReadRateLimit` (`rate_limiter.py:138-139`), `func`/`select` already imported in `analytics.py:23`, `auto_enrich_metadata` (`enrichment.py:224`), `Trace.retrieval_count` (`models/trace.py:69`), `Trace.metadata_json` (`models/trace.py:56`), `Trace.contributor_id` (`models/trace.py:47`).

Response-shape consistency: `get_savings` returns `{minutes_saved, tokens_saved, events}` (Task 5 tests assert this exact dict). `compute_outbound_impact` returns `{tokens_saved_for_others, minutes_saved_for_others, trace_count}` and `OutboundImpactResponse` has those three fields (Task 7) — names match.

### (d) Decisions flagged for the user

1. **Test approach = fake-session, no DB (not SQLite, not testcontainers).** Forced by CI: `.github/workflows/ci.yml` runs `pytest tests/ -q` with no database and the repo's own pattern for async-DB tests is the `FakeConn` style in `ops/tests/`. The `traces` table has `Vector(1536)`/`JSONB` columns that can't be created on SQLite, so a real-engine integration harness was rejected. Consequence: the outbound query's raw SQL (`metadata_json ->> ...::bigint`) is validated for *shape and scoping* but not executed against Postgres in CI. If you want a real round-trip test, that needs a Postgres service added to the CI workflow (a separate infra decision) — flagged, not assumed.

2. **Outbound endpoint path = `GET /api/v1/analytics/impact/outbound`, mounted in `analytics.py`.** The spec says "server query over the caller's own traces, returned only for that authenticated key" but does not fix a path. I put it on the `analytics` router (which already owns retrieval aggregates and imports `Trace`), making it the one authenticated route there. Alternative homes were `traces.py` (`GET /api/v1/traces/impact/outbound`) or `search.py`. If you prefer it under `/traces`, only the router file and prefix change — the service function and tests are unaffected.

3. **`event_type` is a bounded free string, with a documented allowed set (`measured_recurrence`, `proxy_consumption`) but not DB-enforced as an enum.** The spec's `event_type` values come from the skill's booking logic (phase 2), which isn't finalized in this repo. I kept the column a `String(40)` (forward-compatible with new labels) and documented the known set in `ALLOWED_EVENT_TYPES` without rejecting unknowns at ingest, so a skill update introducing a new label is never dropped on the floor. If you'd rather hard-reject unknown labels now, add `event_type` to a Pydantic validator against `ALLOWED_EVENT_TYPES` in Task 2 — flagged as a deliberate looseness, reversible in one line.

4. **`tokens_saved` is `BigInteger`; `minutes_saved` capped at 120 in the schema.** Tokens can be large (sums of cache + input + output across a window), so the column is `BigInteger` and the per-request ingest cap is 5,000,000 tokens. `minutes_saved` mirrors the spec's 120-min per-event cap. These caps live in the Pydantic `SavingsIngest` (Task 2). If the per-event token cap should differ, it is a single `le=` change.
