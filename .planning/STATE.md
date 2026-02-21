# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** When an agent encounters a problem, it should instantly benefit from every other agent that has solved that problem before — and when it solves something new, that knowledge should flow back to all future agents automatically.
**Current focus:** All 7 phases complete — milestone ready for completion

## Current Position

Phase: 7 of 7 (Cold Start + Launch Hardening) — COMPLETE
Plan: 2/2 in current phase — all plans complete
Status: All phases complete. Verified 7/7 must-haves. 3 items need human verification (live stack testing).
Last activity: 2026-02-21 — Phase 7 complete (200 seed traces, import pipeline, 100K capacity test, Locust load tests, rate limiter validation)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 17
- Average duration: ~6 min
- Total execution time: ~100 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3 | 14 min | ~5 min |
| 02-core-api | 4 | 16 min | ~4 min |
| 03-search-discovery | 3/3 | 6 min | ~2 min |
| 04-reputation-engine | 2/3 | 11 min | ~5.5 min |
| 05-mcp-server | 2/2 | 11 min | ~5.5 min |
| 06-claude-code-skill | 2/3 | 4 min | ~2 min |

**Recent Trend:**
- Last 5 plans: 3 min, 3 min, 8 min, 3 min, 2 min
- Trend: Stable

*Updated after each plan completion*

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 07-cold-start-launch-hardening | 2/2 | 40 min | ~20 min |

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
- [03-02]: SEARCH_LIMIT_ANN=100 over-fetch before trust re-ranking to avoid cutting off good semantic matches
- [03-02]: GROUP BY uses full cosine_distance expression not alias (PostgreSQL requires expression, not SELECT alias)
- [03-02]: Tag-only search sets similarity_score=0.0, combined_score=trust_score — no semantic ranking
- [03-02]: 503 only in semantic mode when OPENAI_API_KEY absent; tag-only never 503s
- [03-03]: Search metrics kept in routers/search.py (Plan 03-02) — not moved to metrics.py to avoid prometheus_client duplicate registration errors
- [03-03]: configure_logging() called independently in API lifespan and worker run_worker() — each process configures structlog separately
- [03-03]: Drift detection runs once at worker startup via single GROUP BY query, not per-batch
- [04-01]: Wilson score uses z=1.9600 (95% CI) — returns 0.0 for total_votes==0, float in [0,1] otherwise
- [04-01]: CDR_UNIQUE_CONSTRAINT constant at module level for safe ON CONFLICT DO UPDATE in plan 04-02
- [04-01]: lazy='raise' on ContributorDomainReputation.contributor — prevents implicit async loading
- [04-01]: RequireEmail raises 403 (not 401) — user is authenticated but lacks identity cost (email)
- [04-01]: email-validator installed as direct uv dependency (not optional) — required for Pydantic EmailStr
- [04-02]: get_vote_weight_for_trace uses max() across matching domain scores — best domain score wins for voter, not average
- [04-02]: Untagged traces fall back to users.reputation_score (global Wilson score) — domain-agnostic
- [04-02]: update_contributor_domain_reputation is no-op when domain_tags empty — no phantom rows for untagged traces
- [04-02]: Reputation read endpoint uses CurrentUser not RequireEmail — reading is informational, not a contribution
- [04-02]: users.reputation_score recomputed via SUM aggregation in same transaction as domain upsert — always consistent
- [05-01]: FastMCP 3.0.0 CurrentHeaders() is in fastmcp.dependencies — verified before implementation
- [05-01]: MCP tools return str not dict — format_* functions convert JSON to agent-readable strings
- [05-01]: GET /api/v1/tags uses CurrentUser not RequireEmail — read operation, no identity cost required
- [05-01]: docker-compose uses service_started not service_healthy for api dependency — circuit breaker handles backend unavailability
- [05-02]: CircuitBreaker custom async implementation using asyncio.wait_for — no third-party library needed
- [05-02]: 4xx errors do NOT trip circuit — check status_code >= 500 outside circuit, call _on_failure() manually for server errors
- [05-02]: half-open state allows exactly one probe; _on_success() resets to closed, _on_failure() re-opens
- [05-02]: Read tool degradation: "Continuing without results" — write tool degradation: "Please try again later"
- [Phase 06-01]: Plugin name and .mcp.json server key both 'commontrace' — consistency required for correct MCP tool prefix mcp__plugin_commontrace_commontrace__*
- [Phase 06-01]: HTTP transport in .mcp.json targeting deployed MCP server on port 8080 — no stdio; COMMONTRACE_API_KEY has no default (API keys require explicit env var)
- [Phase 06-01]: /trace:contribute enforces preview-then-confirm flow — no trace submits without explicit yes (SKIL-04 requirement)
- [Phase 06-02]: SessionStart hook uses direct HTTP (urllib.request) not MCP — hooks are shell commands, MCP tools unavailable from subprocess context
- [Phase 06-02]: matcher=startup on SessionStart — prevents re-injection on resume/clear/compact
- [Phase 06-02]: Stop hook uses stop_hook_active (within-cycle) + flag file at /tmp/commontrace-prompted-{session_key} (cross-response) for dual loop prevention
- [Phase 06-02]: Session key uses session_id from payload or os.getppid() fallback — never os.getpid() (new PID per invocation)
- [Phase 07-02]: Random tiled vectors (numpy) not OpenAI API for data generation — avoids cost, sufficient for HNSW latency benchmarking
- [Phase 07-02]: BurstAgent marks 429 as resp.success() — 429 is expected token-bucket exhaustion, not a test failure
- [Phase 07-01]: import_seeds.py uses standalone create_async_engine (not app.database) — runs independently without FastAPI app
- [Phase 07-01]: Seed user email seeds@commontrace.internal (distinct from seed@commontrace.dev used by seed_fixtures.py)
- [Phase 07-01]: Idempotency check: title + is_seed IS TRUE — avoids false match against real user's trace with same title

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 6]: Auto-query trigger heuristics have no established prior art — plan for iteration
- [Phase 7]: Freemium tier pricing needs market validation

## Session Continuity

Last session: 2026-02-21
Stopped at: All 7 phases complete — milestone ready for /gsd:complete-milestone
Resume file: None
