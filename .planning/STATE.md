# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** When an agent encounters a problem, it should instantly benefit from every other agent that has solved that problem before — and when it solves something new, that knowledge should flow back to all future agents automatically.
**Current focus:** Phase 3 in progress — Plan 01 complete (embedding worker)

## Current Position

Phase: 3 of 7 (Search Discovery) — IN PROGRESS
Plan: 1 of 3 in current phase — complete
Status: Phase 3 Plan 01 complete — EmbeddingService and worker loop built and committed
Last activity: 2026-02-20 — Phase 3 Plan 01 executed

Progress: [████░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: ~4 min
- Total execution time: ~30 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3 | 14 min | ~5 min |
| 02-core-api | 4 | 16 min | ~4 min |
| 03-search-discovery | 1/3 | 3 min | ~3 min |

**Recent Trend:**
- Last 5 plans: 3 min, 4 min, 8 min, 3 min, 3 min
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Three-layer architecture (FastAPI → MCP → Skill) — strict dependency chain
- [Roadmap]: Reputation engine ships in Phase 4, before MCP/Skill
- [Roadmap]: PII scanning and trust model enforcement in Phase 2 (write path)
- [Roadmap]: Cold start seeding is Phase 7 deliverable
- [01-01]: TraceStatus has only pending/validated (two-tier model)
- [01-01]: validation_threshold stored in Pydantic Settings env var (default=2)
- [01-01]: String columns for status/vote_type (not PostgreSQL enums)
- [01-02]: Docker Compose uses pgvector/pgvector:pg17
- [01-03]: Manual migrations over autogenerate for HNSW DDL
- [01-03]: Direct trace_tags insert instead of relationship .append() in async context
- [02-01]: API key auth via SHA-256 hash lookup, not JWT
- [02-01]: Lua token-bucket rate limiter with separate read/write limits
- [02-01]: Redis lifespan on app.state, injected via dependency
- [02-01]: redis>=5.0 (redis[asyncio] extra removed in redis 7.x)
- [02-02]: detect-secrets with enable_eager_search=False to avoid false positives
- [02-02]: Staleness detection via PyPI JSON API with 3s timeout
- [02-02]: Trust service: atomic UPDATE col = col + delta, post-update promotion
- [02-03]: Self-vote prevention (403), duplicate vote IntegrityError -> 409
- [02-03]: Trace ORM model updated with is_stale, is_flagged, flagged_at (matching migration 0002)
- [02-04]: Hard-delete for moderation (no soft-delete in v1)
- [02-04]: Any authenticated user can moderate (role-gating deferred)
- [Verification]: CONT-03 moved from Phase 2 to Phase 4 — reputation computation is Phase 4 concern
- [03-01]: No sentence-transformers local fallback — EmbeddingSkippedError raised when no API key; traces stay NULL
- [03-01]: Lazy-init AsyncOpenAI client — created only on first embed() call
- [03-01]: Worker depends only on postgres+redis in docker-compose (not api service)
- [03-01]: alembic upgrade head runs in worker entrypoint to handle migration race

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 5]: FastMCP v2 API was evolving rapidly at research cutoff — verify current syntax before building
- [Phase 6]: Auto-query trigger heuristics have no established prior art — plan for iteration
- [Phase 7]: Freemium tier pricing needs market validation

## Session Continuity

Last session: 2026-02-20
Stopped at: Completed 03-search-discovery 03-01-PLAN.md — ready for Plan 03-02 (semantic search endpoint)
Resume file: None
