---
phase: 03-search-discovery
plan: 01
subsystem: api
tags: [openai, pgvector, embeddings, worker, asyncio, sentence-transformers, prometheus-client]

# Dependency graph
requires:
  - phase: 01-data-foundation
    provides: Trace model with embedding Vector(1536), embedding_model_id, embedding_model_version columns
  - phase: 02-core-api
    provides: async_session_factory, Settings class, structlog configured

provides:
  - EmbeddingService with AsyncOpenAI text-embedding-3-small integration and graceful skip on missing key
  - Async polling worker loop claiming batches via FOR UPDATE SKIP LOCKED
  - Docker-compose worker service running real embedding worker (not placeholder)
  - Phase 3 Python dependencies installed: openai, sentence-transformers, prometheus-client

affects:
  - 03-search-discovery (Plan 02 needs embeddings in DB to query against)
  - 04-reputation-engine (Prometheus metrics available for future use)

# Tech tracking
tech-stack:
  added:
    - openai>=1.0 (AsyncOpenAI client)
    - sentence-transformers>=3.0 (available for future use)
    - prometheus-client>=0.20 (available for future use)
  patterns:
    - FOR UPDATE SKIP LOCKED for safe multi-worker batch claiming
    - Lazy-init AsyncOpenAI client (created only on first embed() call)
    - EmbeddingSkippedError for graceful degradation without API key
    - Worker runs alembic upgrade head before starting (idempotent migration check)

key-files:
  created:
    - api/app/services/embedding.py
    - api/app/worker/__init__.py
    - api/app/worker/embedding_worker.py
  modified:
    - api/app/config.py (added openai_api_key setting)
    - api/pyproject.toml (added Phase 3 dependencies)
    - docker-compose.yml (worker command replaced with real embedding_worker)

key-decisions:
  - "No sentence-transformers local fallback: when no API key, EmbeddingSkippedError is raised and traces stay NULL"
  - "Lazy-init AsyncOpenAI client: only created on first embed() call to avoid startup errors"
  - "Worker depends only on postgres+redis in docker-compose (not api service — worker needs DB not API)"
  - "alembic upgrade head runs before worker start to handle migration race vs api container"

patterns-established:
  - "Graceful degradation via skip flag: service checks config at init, raises typed error on call"
  - "SKIP LOCKED batch claiming: safe for N worker instances without coordinator"

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 3 Plan 01: Embedding Worker and EmbeddingService Summary

**Async embedding worker with OpenAI text-embedding-3-small integration: polls every 5s, claims batches via FOR UPDATE SKIP LOCKED, stores 1536-dimensional vectors; gracefully skips when OPENAI_API_KEY absent**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T06:04:11Z
- **Completed:** 2026-02-20T06:07:24Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- EmbeddingService with AsyncOpenAI lazy-init client, raises EmbeddingSkippedError when no API key configured
- process_batch uses SELECT FOR UPDATE SKIP LOCKED — safe for multiple concurrent workers
- run_worker polls every 5 seconds with outer error catch ensuring the loop never dies
- Docker-compose worker service now runs real embedding worker with pre-flight alembic migration
- All Phase 3 Python dependencies installed (openai, sentence-transformers, prometheus-client)

## Task Commits

Each task was committed atomically:

1. **Task 1: EmbeddingService and worker config** - `f0da9d5` (feat)
2. **Task 2: Embedding worker polling loop and docker-compose wiring** - `ef59f89` (feat)

## Files Created/Modified
- `api/app/services/embedding.py` - EmbeddingService class with AsyncOpenAI, EmbeddingSkippedError, OPENAI_MODEL/OPENAI_DIMENSIONS constants
- `api/app/worker/__init__.py` - Package marker (empty)
- `api/app/worker/embedding_worker.py` - process_batch (SKIP LOCKED claim + embed + store) and run_worker (infinite poll loop)
- `api/app/config.py` - Added `openai_api_key: str = ""` to Settings class
- `api/pyproject.toml` - Added openai>=1.0, sentence-transformers>=3.0, prometheus-client>=0.20
- `docker-compose.yml` - Worker command changed from placeholder sleep to `alembic upgrade head && python -m app.worker.embedding_worker`

## Decisions Made
- No local sentence-transformers fallback wired in this plan: per research open question #1, simplest correct behavior is to skip embedding without API key. Sentence-transformers is installed for potential future use but not used.
- Lazy-init AsyncOpenAI client: the client is only instantiated on the first `embed()` call, not at construction, to avoid errors when API key is present but the constructor runs at import time.
- Worker docker-compose depends only on postgres and redis, not the api service — the worker only needs the database to function.
- `alembic upgrade head` runs in worker entrypoint to handle the race where worker starts before the API container has applied migrations.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - installation and implementation went smoothly.

## User Setup Required

**OPENAI_API_KEY is required** for embeddings to be generated. Without it, the worker will log a warning and skip all traces (traces remain with `embedding=NULL`).

To enable embeddings, add to your `.env` file:
```
OPENAI_API_KEY=sk-...
```

## Next Phase Readiness
- EmbeddingService ready for use by Plan 03-02 (semantic search endpoint)
- Embedding worker will process existing unembedded traces as soon as OPENAI_API_KEY is set
- HNSW index from Phase 1 migrations is already in place for ANN queries
- prometheus-client installed and ready for metrics instrumentation

---
*Phase: 03-search-discovery*
*Completed: 2026-02-20*
