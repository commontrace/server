# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** When an agent encounters a problem, it should instantly benefit from every other agent that has solved that problem before — and when it solves something new, that knowledge should flow back to all future agents automatically.
**Current focus:** Phase 2, Plans 01, 02, and 03 complete — all write-path HTTP endpoints wired with auth, rate limiting, and PII scanning

## Current Position

Phase: 2 of 7 (Core API) — IN PROGRESS
Plan: 3 of 4 in current phase — complete
Status: Plan 02-03 complete (2 tasks, 2 commits, all write-path endpoints wired)
Last activity: 2026-02-20 — Plan 02-03 executed and committed

Progress: [█████░░░░░] 36%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: ~4 min
- Total execution time: ~29 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3 | 14 min | ~5 min |
| 02-core-api | 3 | 15 min | ~5 min |

**Recent Trend:**
- Last 5 plans: 3 min, 8 min, 3 min, 4 min
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Three-layer architecture (FastAPI → MCP → Skill) — strict dependency chain, no layer bypasses another
- [Roadmap]: Reputation engine ships in Phase 4, before MCP/Skill — Sybil attacks possible the moment voting is live
- [Roadmap]: PII scanning and trust model enforcement in Phase 2 (write path) — cannot be retrofitted after contributions begin
- [Roadmap]: Cold start seeding is Phase 7 deliverable — must complete before any public announcement
- [01-01]: TraceStatus has only pending/validated (two-tier model per user decision — no quarantined)
- [01-01]: validation_threshold stored in Pydantic Settings env var (default=2, not hardcoded)
- [01-01]: String columns for status/vote_type avoids PostgreSQL enum type management in migrations
- [01-01]: Skeleton mcp-server and skill packages use no build-backend (pure project files, hatchling fails on empty packages list)
- [01-02]: Docker Compose uses pgvector/pgvector:pg17 for postgres with pgvector pre-installed
- [01-02]: .env uses Docker-internal hostnames (postgres, redis); .env.example uses localhost for outside-Docker dev
- [01-02]: VALIDATION_THRESHOLD is env var (default: 2) not hardcoded per user decision
- [01-02]: docker-compose.override.yml auto-merged for dev; base compose has prod-ready commands without --reload
- [01-03]: Manual migrations over autogenerate — Alembic can't handle HNSW DDL or Vector type comparison
- [01-03]: Direct trace_tags insert instead of relationship .append() in async context (MissingGreenlet fix)
- [01-03]: 12 seed traces covering common coding patterns, auto-validated with is_seed=True
- [02-01]: redis[asyncio] extra does not exist in redis>=7.x — asyncio built-in; use redis>=5.0 without extra
- [02-01]: No distinction between missing vs invalid API key in 401 — prevents key enumeration attacks
- [02-01]: Token bucket refill rate = max_tokens/60 tokens/second; TTL = 120s (2x 60s window) for cleanup without premature expiry
- [02-01]: require_read_limit()/require_write_limit() are factories returning callables — enables separate bucket DI per endpoint
- [02-02]: detect-secrets enable_eager_search=False: use _scan_line directly to avoid bare-word false positives; only quoted strings and specific patterns (AWS keys, JWTs) trigger scanner
- [02-02]: All three trace fields (title, context_text, solution_text) scanned with same detector set — simpler and more conservative; false positives better than missed leaks
- [02-02]: Staleness comparison is major.minor only — patch releases backwards-compatible and don't invalidate trace advice
- [02-02]: apply_vote_to_trace uses atomic column-expression UPDATE then separate SELECT for promotion check — safe under one-vote-per-trace unique DB constraint
- [02-02]: VoteResponse.feedback_tag Optional[str]=None even though Vote model stores this in context_json — endpoint layer (02-03) handles the mapping
- [02-03]: vote_weight = max(user.reputation_score, 1.0) for new users — prevents zero-weight votes while reputation engine ships in Phase 4
- [02-03]: Direct insert into trace_tags join table (not relationship.append) — consistent with seed fixture pattern, avoids MissingGreenlet in async context
- [02-03]: feedback_tag stored in Vote.context_json, deserialized at endpoint layer — VoteResponse.feedback_tag populated without ORM schema change
- [02-03]: ORM model Trace was missing is_stale, is_flagged, flagged_at columns despite migration 0002 adding them — added to model (Rule 1 auto-fix)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 5]: FastMCP v2 API was evolving rapidly at research cutoff — verify current decorator syntax, Streamable HTTP transport, and tool registration patterns against live docs before building Phase 5
- [Phase 6]: Auto-query trigger heuristics (context detection signals, injection threshold) have no established prior art — plan for iteration; consider running /gsd:research-phase before Phase 6
- [Phase 7]: Freemium tier pricing and rate limit numbers need market validation — consider /gsd:research-phase before finalizing tier structure

## Session Continuity

Last session: 2026-02-20
Stopped at: Plan 02-03 complete — all write-path HTTP endpoints wired (auth, traces, votes, amendments); routers registered in main.py; ready for 02-04 moderation (parallel) or Phase 3
Resume file: None
