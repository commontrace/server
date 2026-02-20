---
phase: 07-cold-start-launch-hardening
plan: 02
subsystem: testing
tags: [locust, asyncpg, pgvector, hnsw, rate-limiter, faker, numpy, load-testing, capacity]

# Dependency graph
requires:
  - phase: 03-search-discovery
    provides: POST /api/v1/traces/search endpoint with HNSW pgvector search
  - phase: 02-core-api
    provides: Token-bucket rate limiter (Redis Lua), POST /api/v1/keys endpoint
  - phase: 01-data-foundation
    provides: traces table with pgvector embedding column and HNSW index

provides:
  - Load test infrastructure to validate 100K HNSW p99 latency target (<50ms)
  - Data generation script to populate 100K synthetic traces with embeddings
  - Rate limiter burst test to validate token-bucket correctness under agent workloads
  - Docker Compose override with tuned PostgreSQL memory for capacity testing

affects:
  - 07-cold-start-launch-hardening (launch readiness verification)

# Tech tracking
tech-stack:
  added: [locust 2.43.3, faker]
  patterns: [tiled-vectors-with-noise for realistic ANN benchmarking, catch_response for expected 429 handling]

key-files:
  created:
    - api/scripts/generate_capacity_data.py
    - tests/load/locustfile_capacity.py
    - tests/load/locustfile_rate_limit.py
    - docker-compose.capacity.yml
    - tests/load/__init__.py
  modified:
    - api/pyproject.toml
    - uv.lock

key-decisions:
  - "Random tiled vectors (numpy) not OpenAI API — avoids $1.20+ cost, sufficient for HNSW latency benchmarking"
  - "Tiled vectors with noise (sigma=0.05) create clusters — more realistic ANN behavior than purely random"
  - "BurstAgent marks 429 as resp.success() — 429 is expected behavior, not a test failure"
  - "REINDEX CONCURRENTLY after bulk insert ensures optimal HNSW graph quality"
  - "RATE_LIMIT_READ_PER_MINUTE=10000 env override required for capacity test (default 60/min causes 429 within 6s)"

patterns-established:
  - "catch_response=True + resp.success() for expected HTTP error codes in Locust"
  - "asyncpg direct connection for bulk insert bypassing ORM"
  - "Faker seed=42 + numpy seed=42 for deterministic synthetic test data"

# Metrics
duration: 2min
completed: 2026-02-20
---

# Phase 07 Plan 02: Capacity + Rate Limit Validation Infrastructure Summary

**Locust load tests + asyncpg data generator for 100K HNSW p99 latency and token-bucket rate limiter burst validation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-20T22:49:58Z
- **Completed:** 2026-02-20T22:52:25Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Data generation script inserts 100K synthetic traces with 1536-dim tiled random vectors (asyncpg bulk insert, batches of 1000, REINDEX after)
- Locust capacity test measures HNSW p99 search latency with 10 diverse queries at 10 RPS per user across 20 concurrent users
- Locust rate limit test validates token-bucket behavior: BurstAgent fires at max rate (expects 429 after ~60 requests), RealisticAgent sends 10-15/30s (expects 100% success)
- Docker Compose override tunes PostgreSQL to fit 600MB HNSW index in shared_buffers (2GB)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create capacity test infrastructure (data generator + Compose override)** - `5c295c4` (feat)
2. **Task 2: Create Locust load test files for capacity and rate limit validation** - `f0452fe` (feat)

**Plan metadata:** `[pending]` (docs: complete plan)

## Files Created/Modified

- `api/scripts/generate_capacity_data.py` - asyncpg bulk insert of 100K traces with tiled random 1536-dim vectors, faker metadata, REINDEX after insert
- `tests/load/locustfile_capacity.py` - SearchLoadUser: 10 diverse queries at 10 RPS, measures HNSW search p99 latency
- `tests/load/locustfile_rate_limit.py` - BurstAgent (pure burst, accepts 429) + RealisticAgent (10-15/30s, expects all succeed)
- `docker-compose.capacity.yml` - PostgreSQL override: shared_buffers=2GB, effective_cache_size=4GB, maintenance_work_mem=1GB, work_mem=64MB
- `tests/load/__init__.py` - Created load test directory
- `api/pyproject.toml` - Added locust and faker as dev dependencies
- `uv.lock` - Updated lockfile with locust 2.43.3 and faker

## Decisions Made

- **No OpenAI API calls in data generator**: Random normalized vectors (numpy seed=42) are sufficient for HNSW latency benchmarking — tests index traversal mechanics, not semantic quality. Avoids $1.20+ API cost and rate limiting delays.
- **Tiled vectors with noise**: Using 1000 base vectors + Gaussian noise (sigma=0.05) creates realistic cluster structure, more representative of real ANN search patterns than purely random vectors.
- **BurstAgent marks 429 as success**: `catch_response=True` + `resp.success()` on 429 — rate limiting is expected behavior under burst, not a test failure. Locust would otherwise count 429s as failures and pollute the stats.
- **REINDEX CONCURRENTLY after bulk insert**: Ensures optimal HNSW graph quality after 100K row batch insert.
- **RATE_LIMIT_READ_PER_MINUTE=10000 override documented**: Default 60/min rate limit would cause 429s within 6 seconds per user at 10 RPS — capacity test must override this env var.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **uv.lock location**: Lock file is at project root `/commontrace/uv.lock`, not inside `api/`. Resolved by staging `uv.lock` from project root instead of `api/uv.lock`.

## User Setup Required

None - no external service configuration required. Run commands are documented in script file headers.

## Next Phase Readiness

- All capacity test infrastructure is ready to run
- Prerequisites to execute tests: start tuned stack (`docker compose -f docker-compose.yml -f docker-compose.capacity.yml up`), populate data (`python api/scripts/generate_capacity_data.py`), then run locust tests
- Rate limiter validation will confirm Phase 2 token-bucket correctness at agent-realistic burst rates

---
*Phase: 07-cold-start-launch-hardening*
*Completed: 2026-02-20*

## Self-Check: PASSED

All files verified present, both task commits confirmed in git log.
