---
phase: 01-data-foundation
plan: 01
subsystem: database
tags: [sqlalchemy, asyncpg, pgvector, fastapi, pydantic, uv, python]

# Dependency graph
requires: []
provides:
  - uv workspace monorepo with api, mcp-server, skill sub-packages
  - SQLAlchemy 2.0 async ORM models for all tables (users, traces, votes, tags, trace_tags)
  - Pydantic BaseSettings config with all env vars including configurable validation_threshold
  - Async SQLAlchemy engine with pgvector registration via event listener
  - Tag normalization service (pure Python, DB-free)
  - FastAPI app factory with health check endpoint
  - FastAPI DbSession dependency alias
affects:
  - 01-02 (Alembic migrations reads Base.metadata and all models)
  - 01-03 (Docker Compose runs FastAPI app with database wiring)
  - 02-data-write-path (all write endpoints import models and DbSession)
  - 03-search (Trace.embedding Vector(1536) column and embedding_model_id/version)
  - 04-reputation (User.reputation_score, Vote model, TraceStatus state machine)

# Tech tracking
tech-stack:
  added:
    - sqlalchemy==2.0.46 (async ORM with Mapped[] type hints)
    - asyncpg==0.31.0 (async PostgreSQL driver)
    - pgvector==0.4.2 (Vector type for SQLAlchemy + asyncpg registration)
    - alembic==1.18.4 (schema migrations, async template)
    - fastapi==0.129.0 (application framework)
    - uvicorn==0.41.0 (ASGI server)
    - pydantic==2.12.5 (schema validation)
    - pydantic-settings==2.13.1 (BaseSettings with env file support)
    - structlog==25.5.0 (structured logging)
    - python-dotenv==1.2.1 (env file loading)
    - uv==0.9.8 (workspace package manager)
  patterns:
    - "DeclarativeBase with NAMING_CONVENTION MetaData (required for Alembic autogenerate)"
    - "AsyncAttrs mixin on Base (prevents lazy-loading errors in async sessions)"
    - "Mapped[] type annotations with mapped_column() (SQLAlchemy 2.0 style)"
    - "String columns for status/vote_type (avoids PostgreSQL enum type management)"
    - "pgvector registered via event.listens_for(engine.sync_engine, 'connect')"
    - "Pure Python service layer for tag normalization (no DB triggers)"
    - "Pydantic BaseSettings with env_file for all config (validation_threshold configurable)"

key-files:
  created:
    - pyproject.toml (uv workspace root)
    - .python-version (3.12)
    - api/pyproject.toml (commontrace-api package with all dependencies)
    - api/app/config.py (Settings with validation_threshold, embedding_dimensions, etc.)
    - api/app/database.py (async engine, pgvector registration, session factory, get_db)
    - api/app/main.py (FastAPI app factory, health check)
    - api/app/dependencies.py (DbSession type alias)
    - api/app/models/base.py (Base with NAMING_CONVENTION)
    - api/app/models/trace.py (Trace, TraceStatus)
    - api/app/models/user.py (User)
    - api/app/models/vote.py (Vote, VoteType with UniqueConstraint)
    - api/app/models/tag.py (Tag, trace_tags join table)
    - api/app/models/__init__.py (re-exports all models for Alembic autogenerate)
    - api/app/services/tags.py (normalize_tag, normalize_tags, validate_tag)
    - mcp-server/pyproject.toml (skeleton for Phase 5)
    - skill/pyproject.toml (skeleton for Phase 6)
  modified: []

key-decisions:
  - "TraceStatus has only pending/validated (two-tier model per user decision — no quarantined)"
  - "validation_threshold stored in Pydantic Settings env var (default=2, not hardcoded)"
  - "String columns for status/vote_type avoids PostgreSQL enum type management in migrations"
  - "trace_tags as Table() join (not ORM class) — no additional metadata needed on join"
  - "Skeleton mcp-server and skill packages use no build-backend (pure project files)"
  - "validate_tag() allows alphanumeric, hyphens, dots, underscores — no spaces or special chars"

patterns-established:
  - "Pattern 1: All models import from app.models (ensures Alembic autogenerate sees all tables)"
  - "Pattern 2: TYPE_CHECKING imports for relationship type hints (avoids circular imports)"
  - "Pattern 3: normalize_tag() called before any Tag create/lookup (service layer, not DB)"
  - "Pattern 4: DbSession = Annotated[AsyncSession, Depends(get_db)] for clean endpoint signatures"

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 1 Plan 01: Project Skeleton and ORM Models Summary

**uv workspace monorepo with SQLAlchemy 2.0 async ORM models (Trace/User/Vote/Tag), pgvector Vector(1536) column, configurable validation threshold, and pure Python tag normalization service**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T04:15:19Z
- **Completed:** 2026-02-20T04:18:52Z
- **Tasks:** 3
- **Files modified:** 16

## Accomplishments

- uv workspace with api, mcp-server, skill sub-packages — all 30 production dependencies resolved and installed
- SQLAlchemy 2.0 async ORM models for all 5 tables (users, traces, votes, tags, trace_tags) with full DATA-02, DATA-03, DATA-04 compliance
- Tag normalization service (normalize_tag, normalize_tags, validate_tag) — pure Python, zero DB dependency, fully testable in isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Project skeleton and uv workspace** - `08570dc` (feat)
2. **Task 2: SQLAlchemy ORM models for all tables** - `9fab7c8` (feat)
3. **Task 3: Tag normalization service** - `b4aea58` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `pyproject.toml` - uv workspace root declaring api, mcp-server, skill members
- `.python-version` - Python 3.12 pin for uv
- `api/pyproject.toml` - commontrace-api package with all production + dev dependencies
- `api/app/config.py` - Pydantic BaseSettings with database_url, redis_url, validation_threshold (default 2), embedding_dimensions (1536), debug
- `api/app/database.py` - Async engine with pgvector event listener, async_session_factory, get_db dependency
- `api/app/main.py` - FastAPI app factory with GET /health endpoint
- `api/app/dependencies.py` - DbSession type alias for clean endpoint signatures
- `api/app/models/base.py` - DeclarativeBase + AsyncAttrs + NAMING_CONVENTION MetaData
- `api/app/models/trace.py` - Trace model with all columns, TraceStatus enum (pending/validated)
- `api/app/models/user.py` - User model with reputation_score and is_seed flag
- `api/app/models/vote.py` - Vote model with VoteType enum, UniqueConstraint(trace_id, voter_id)
- `api/app/models/tag.py` - Tag model with is_curated flag, trace_tags join table with composite PK
- `api/app/models/__init__.py` - Re-exports all models (ensures Alembic autogenerate sees them)
- `api/app/services/tags.py` - normalize_tag, normalize_tags, validate_tag (pure Python)
- `mcp-server/pyproject.toml` - commontrace-mcp skeleton package (Phase 5)
- `skill/pyproject.toml` - commontrace-skill skeleton package (Phase 6)

## Decisions Made

- **TraceStatus two-tier model:** Plan specified pending/validated only — removed quarantined status present in RESEARCH.md code example (user decision: two-tier model)
- **String columns for status/vote_type:** Avoids PostgreSQL enum type management complexity in Alembic migrations — Python enums used only for defaults and application-level validation
- **validate_tag() character set:** Allows alphanumeric, hyphens, dots, underscores — covers common tag formats like "fastapi", "python-3.12", "v1.0", "my_tag"
- **Skeleton packages without build-backend:** mcp-server and skill packages have no source code yet; omitting hatchling build-backend avoids "Unable to determine which files to ship" error from hatchling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed skeleton packages failing hatchling build**
- **Found during:** Task 1 (uv sync --all-packages)
- **Issue:** mcp-server and skill pyproject.toml files specified `[tool.hatch.build.targets.wheel] packages = []` but hatchling requires at least one package directory to build a wheel — empty packages list causes "Unable to determine which files to ship" error
- **Fix:** Removed build-system and hatchling config from mcp-server and skill pyproject.toml files; uv workspace members without build-backend are treated as pure project files and sync correctly
- **Files modified:** mcp-server/pyproject.toml, skill/pyproject.toml
- **Verification:** `uv sync --all-packages` succeeded, all 30 packages installed
- **Committed in:** 08570dc (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix necessary for workspace to resolve. Skeleton packages have no source code yet; this is the correct configuration.

## Issues Encountered

None — beyond the hatchling skeleton package issue auto-fixed above.

## User Setup Required

None — no external service configuration required for this plan. Database and Redis configuration is prepared but services are provisioned in Plan 01-03 (Docker Compose).

## Next Phase Readiness

- Plan 01-02 (Alembic migrations): `Base.metadata` contains all 5 tables with named constraints; all models importable from `app.models`; async engine is configured with correct DB URL from settings
- Plan 01-03 (Docker Compose): FastAPI app factory at `app.main:app` is ready; `get_db` dependency wired; settings read from `.env` file
- Phase 2 (write path API endpoints): All models importable; `DbSession` type alias ready; tag service callable
- Phase 3 (search): `Trace.embedding` is `Vector(1536)` nullable; `embedding_model_id` and `embedding_model_version` columns exist (DATA-02)

---
*Phase: 01-data-foundation*
*Completed: 2026-02-20*

## Self-Check: PASSED

All 17 created files confirmed present on disk. All 3 task commits confirmed in git log (08570dc, 9fab7c8, b4aea58).
