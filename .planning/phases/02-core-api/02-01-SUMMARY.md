---
phase: 02-core-api
plan: "01"
subsystem: auth
tags: [redis, api-key, sha256, token-bucket, rate-limiting, fastapi, sqlalchemy, alembic, lua]

# Dependency graph
requires:
  - phase: 01-data-foundation
    provides: User model with api_key_hash column, async SQLAlchemy engine and session factory

provides:
  - API key authentication dependency (CurrentUser) — SHA-256 hash lookup against users.api_key_hash
  - Redis client dependency (RedisClient) — injected from app.state via lifespan
  - Token bucket rate limiter (ReadRateLimit, WriteRateLimit) — Lua-atomic per-user per-bucket-type
  - Amendment ORM model with FKs to traces and users
  - Alembic migration 0002 — amendments table + is_stale/is_flagged/flagged_at on traces
  - Extended Settings with rate_limit_read_per_minute=60, rate_limit_write_per_minute=20

affects:
  - 02-02-PLAN (write endpoints: POST /traces, POST /votes — use CurrentUser, WriteRateLimit)
  - 02-03-PLAN (router registration and app wiring)
  - 03-semantic-search (read endpoints — use CurrentUser, ReadRateLimit)
  - 04-reputation (amendment queries — Amendment model)

# Tech tracking
tech-stack:
  added:
    - redis>=5.0 (async Redis client — redis.asyncio submodule, asyncio extra deprecated in 7.x)
    - detect-secrets>=1.5.0 (PII/secrets scanning, used in write path plans)
    - packaging>=23.0 (PEP 440 version parsing for staleness checks)
    - httpx>=0.27 (moved from dev to main dependencies — needed for PyPI staleness check)
  patterns:
    - lifespan context manager for async resource management (Redis connection lifecycle)
    - Annotated type aliases for FastAPI dependencies (CurrentUser, RedisClient, ReadRateLimit, WriteRateLimit)
    - APIKeyHeader with Security() for OpenAPI schema registration
    - Lua script atomicity for rate limiting (prevents TOCTOU race conditions)
    - lazy="raise" on ORM relationships prevents accidental N+1 queries at import time
    - Named FK constraints on all new ForeignKey columns (matches existing migration pattern)

key-files:
  created:
    - api/app/models/amendment.py — Amendment ORM model (UUID PK, FK traces+users, lazy="raise")
    - api/migrations/versions/0002_amendments_and_staleness.py — manual Alembic migration
    - api/app/middleware/__init__.py — package root
    - api/app/middleware/rate_limiter.py — RATE_LIMIT_LUA token bucket, check_rate_limit(), type aliases
  modified:
    - api/app/config.py — added rate_limit_read_per_minute, rate_limit_write_per_minute, api_key_header_name
    - api/app/main.py — rewritten with asynccontextmanager lifespan (Redis on app.state)
    - api/app/dependencies.py — added get_redis, get_current_user, CurrentUser, RedisClient
    - api/app/models/__init__.py — exported Amendment
    - api/pyproject.toml — added 4 new main dependencies

key-decisions:
  - "redis[asyncio] extra does not exist in redis>=7.x — asyncio support is built-in; use redis>=5.0 without extra"
  - "No distinction between missing vs invalid API key in 401 response — prevents key enumeration attacks"
  - "Token bucket refill rate = max_tokens / 60.0 tokens/second — full refill in 60s matches per-minute capacity"
  - "Lua script TTL set to 120s (2x refill window) — ensures stale keys are cleaned up without premature expiry"
  - "require_read_limit() / require_write_limit() are factories returning callables — enables separate bucket DI per endpoint"

patterns-established:
  - "Rate limit key format: rl:{user.id}:{bucket_type} — namespaced by user and read/write type"
  - "All auth dependencies use SHA-256 hash comparison — raw key never stored"
  - "Middleware package for cross-cutting concerns (rate limiting, future: request logging, PII scanning)"

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 2 Plan 01: Auth, Rate Limiting, and Schema Infrastructure Summary

**FastAPI lifespan-managed Redis connection, SHA-256 API key auth dependency, Lua token-bucket rate limiter with separate read/write capacities, Amendment ORM model, and Alembic migration 0002**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-20T05:01:21Z
- **Completed:** 2026-02-20T05:04:32Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Authentication foundation: `get_current_user` dependency computes SHA-256 of X-API-Key header, queries `users.api_key_hash`, returns authenticated User or 401
- Rate limiting: Lua token bucket runs atomically on Redis server; separate read (60/min) and write (20/min) buckets per user, exposed as `ReadRateLimit`/`WriteRateLimit` Annotated type aliases
- Schema expansion: Amendment model and migration 0002 add amendments table plus `is_stale`, `is_flagged`, `flagged_at` columns to traces table

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies, extend config, add Amendment model and migration** - `e294af5` (feat)
2. **Task 2: Redis lifespan, auth dependency, and rate limiter** - `c74a230` (feat)

## Files Created/Modified

- `api/app/models/amendment.py` — Amendment model: UUID PK, FK to traces (fk_amendments_original_trace_id_traces), FK to users (fk_amendments_submitter_id_users), lazy="raise" relationships
- `api/migrations/versions/0002_amendments_and_staleness.py` — Manual migration c3d4e5f6a7b8 revising b2c3d4e5f6a7; adds 3 traces columns + amendments table with 2 indexes each
- `api/app/middleware/__init__.py` — Empty package root
- `api/app/middleware/rate_limiter.py` — RATE_LIMIT_LUA Lua script (973 chars), check_rate_limit(), require_read_limit(), require_write_limit(), ReadRateLimit, WriteRateLimit
- `api/app/main.py` — Rewritten with asynccontextmanager lifespan; Redis stored on app.state.redis
- `api/app/dependencies.py` — get_redis(), get_current_user() with SHA-256, CurrentUser and RedisClient aliases
- `api/app/config.py` — rate_limit_read_per_minute=60, rate_limit_write_per_minute=20, api_key_header_name="X-API-Key"
- `api/app/models/__init__.py` — Amendment added to exports
- `api/pyproject.toml` — Added redis>=5.0, detect-secrets>=1.5.0, packaging>=23.0, httpx>=0.27 (moved from dev)

## Decisions Made

- `redis[asyncio]` extra does not exist in redis 7.x (asyncio support is built-in) — dependency specified as `redis>=5.0` without extra
- No distinction between missing vs invalid API key in 401 — prevents enumeration of valid keys
- Token bucket TTL = 120s (2x 60s window) — avoids premature expiry while cleaning up stale keys

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] redis[asyncio] extra invalid in redis 7.x**

- **Found during:** Task 1 (dependency installation)
- **Issue:** uv sync warned "package redis==7.2.0 does not have an extra named asyncio" and failed to install redis; asyncio support is built-in as of redis 7.x
- **Fix:** Changed `redis[asyncio]>=5.0` to `redis>=5.0` in pyproject.toml — asyncio submodule (redis.asyncio) is always available without the extra
- **Files modified:** api/pyproject.toml
- **Verification:** `import redis.asyncio` succeeds; redis 7.2.0 installed
- **Committed in:** e294af5 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking install issue)
**Impact on plan:** Trivial fix — async Redis functionality is identical; the `asyncio` extra was removed from redis-py in 5.x when they merged aioredis. No scope creep.

## Issues Encountered

None beyond the redis extra deviation documented above.

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness

- `CurrentUser`, `RedisClient`, `ReadRateLimit`, `WriteRateLimit` dependencies are ready for Plan 02-02 (write endpoints)
- Amendment model and migration 0002 ready — run `alembic upgrade head` to apply
- Rate limiter requires Redis to be running (Docker Compose redis service handles this in dev)
- No blockers for Plan 02-02

## Self-Check: PASSED

All 8 files verified present on disk.
All 2 task commits (e294af5, c74a230) verified in git log.

---
*Phase: 02-core-api*
*Completed: 2026-02-20*
