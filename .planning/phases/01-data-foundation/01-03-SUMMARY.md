---
phase: 01-data-foundation
plan: 03
subsystem: database
tags: [alembic, pgvector, hnsw, migrations, fixtures, asyncpg]

requires:
  - phase: 01-data-foundation/01-01
    provides: SQLAlchemy ORM models, config, database.py, tag normalization
  - phase: 01-data-foundation/01-02
    provides: Docker Compose postgres/pgvector, redis, env config
provides:
  - Alembic async migration pipeline (env.py + 2 migrations)
  - pgvector extension enabled as first migration
  - Full schema migration with HNSW index (m=16, ef_construction=64)
  - 12 sample traces with 28 normalized tags as seed data
  - Idempotent seed script for fixture loading
affects: [phase-02-core-api, phase-03-search]

tech-stack:
  added: [alembic]
  patterns: [async-alembic-migrations, manual-migration-for-pgvector, direct-join-table-insert]

key-files:
  created:
    - api/migrations/env.py
    - api/migrations/versions/0000_enable_pgvector.py
    - api/migrations/versions/0001_initial_schema.py
    - api/fixtures/sample_traces.json
    - api/fixtures/seed_fixtures.py
  modified:
    - api/alembic.ini

key-decisions:
  - "Manual migrations over autogenerate — autogenerate can't handle HNSW index DDL or Vector column type comparison"
  - "Direct trace_tags insert instead of relationship .append() — avoids async lazy-load MissingGreenlet error"
  - "Docker postgres mapped to 5433 during validation (5432 occupied by host postgres) — docker-compose.yml remains at 5432 as default"

patterns-established:
  - "Async Alembic: asyncio.run(run_async_migrations()) with NullPool, override URL from settings"
  - "pgvector extension as first migration (0000) before any Vector column migration"
  - "Seed fixtures: idempotent check via seed user email, auto-validated with status=validated and is_seed=True"
  - "Join table inserts: use trace_tags.insert().values() instead of relationship.append() in async context"

duration: 8min
completed: 2026-02-20
---

# Plan 01-03: Alembic Migrations + Fixtures Summary

**Async Alembic migrations creating 5 tables with pgvector HNSW index, 12 seed traces with 28 normalized tags loaded via idempotent script**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20
- **Completed:** 2026-02-20
- **Tasks:** 3 (2 code + 1 e2e validation)
- **Files created:** 6

## Accomplishments
- Alembic async env.py configured with all model imports and settings override
- Migration 0000: pgvector extension enabled (must be first)
- Migration 0001: All 5 tables + HNSW index (vector_cosine_ops, m=16, ef_construction=64) + B-tree indexes
- 12 realistic sample traces covering FastAPI, Docker, pgvector, Alembic, Redis, JWT, Pydantic, React, PostgreSQL patterns
- All 5 phase success criteria verified against running Docker postgres

## Task Commits

1. **Task 1: Alembic async setup and migrations** - `bf8ed46` (feat)
2. **Task 2: Fixture data and seed script** - `573a9e8` (feat)
3. **Task 2 fix: Async lazy-load fix** - `0812415` (fix)

## Files Created/Modified
- `api/alembic.ini` - Alembic config pointing to async migrations/env.py
- `api/migrations/env.py` - Async Alembic env with all model imports, settings URL override
- `api/migrations/script.py.mako` - Standard revision template
- `api/migrations/versions/0000_enable_pgvector.py` - CREATE EXTENSION IF NOT EXISTS vector
- `api/migrations/versions/0001_initial_schema.py` - All tables + HNSW index + B-tree indexes
- `api/fixtures/sample_traces.json` - 12 realistic traces with tags
- `api/fixtures/seed_fixtures.py` - Idempotent async seed script

## Decisions Made
- Manual migrations over autogenerate — Alembic can't generate HNSW index DDL or compare Vector types
- Direct join table insert (`trace_tags.insert().values()`) instead of ORM relationship `.append()` — required for async context (avoids MissingGreenlet error)

## Deviations from Plan

### Auto-fixed Issues

**1. Async lazy-load MissingGreenlet error in seed script**
- **Found during:** Task 2 verification
- **Issue:** `trace.tags.append(tag)` triggers synchronous lazy-load on the `tags` relationship, which fails with asyncpg (MissingGreenlet)
- **Fix:** Changed to direct `trace_tags.insert().values(trace_id=trace.id, tag_id=tag.id)` insert
- **Files modified:** api/fixtures/seed_fixtures.py
- **Verification:** Seed script loads 12 traces with 28 tags successfully
- **Committed in:** `0812415`

---

**Total deviations:** 1 auto-fixed
**Impact on plan:** Essential fix for async SQLAlchemy correctness. No scope creep.

## Issues Encountered
- Host PostgreSQL on port 5432 required Docker postgres to temporarily use port 5433 for validation. docker-compose.yml restored to 5432 as the default.

## Self-Check: PASSED

All 5 phase success criteria verified:
- SC-1: 17 trace columns present (title, context_text, solution_text, embedding, etc.)
- SC-2: embedding_model_id and embedding_model_version queryable
- SC-3: All 28 tags lowercase and normalized
- SC-4: New traces default to pending; validation_threshold=2 configurable
- SC-5: 6 tables exist (users, traces, votes, tags, trace_tags, alembic_version)

## Next Phase Readiness
- Schema is complete and migration-ready
- Fixture data provides immediate test queries
- Phase 2 can build API endpoints on top of this foundation

---
*Phase: 01-data-foundation*
*Completed: 2026-02-20*
