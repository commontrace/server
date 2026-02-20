# Roadmap: CommonTrace

## Overview

CommonTrace is a collective knowledge layer for AI coding agents built in three tiers: a FastAPI backend (PostgreSQL + pgvector, async embedding pipeline, reputation engine), a stateless MCP server (protocol adapter exposing tools to any MCP-compatible agent), and a Claude Code skill (auto-query + explicit contribution commands). The roadmap builds strict bottom-up: schema before API before search before MCP before skill, with reputation and safety woven into the write path from the first contribution endpoint. Cold start seeding and hardening complete the system before any public launch.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Foundation** - Schema, migrations, and local dev infrastructure (completed 2026-02-20)
- [x] **Phase 2: Core API — Auth, Safety, Contribution** - Authentication, PII safety gates, and the full write path (completed 2026-02-20)
- [x] **Phase 3: Search + Discovery** - Hybrid semantic + tag search with async embedding pipeline (completed 2026-02-20)
- [x] **Phase 4: Reputation Engine** - Wilson score trust, vote weighting, and domain-scoped reputation (completed 2026-02-20)
- [ ] **Phase 5: MCP Server** - Stateless protocol adapter exposing CommonTrace tools to any agent
- [ ] **Phase 6: Claude Code Skill** - Auto-query on task start and explicit contribution commands
- [ ] **Phase 7: Cold Start + Launch Hardening** - Seed knowledge base and validate system at launch scale

## Phase Details

### Phase 1: Data Foundation
**Goal**: A stable, future-proof schema exists that every downstream component can build on without migration pain
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04
**Success Criteria** (what must be TRUE):
  1. A trace row can be created with context, solution, tags, contributor ID, timestamps, and all required metadata fields
  2. Every trace row carries embedding_model_id and embedding_model_version columns — storing a new trace with a different embedding model version produces a distinct, queryable record
  3. Submitting a tag with mixed case, duplicates, or non-canonical forms normalizes it to the same stored value as its canonical equivalent
  4. A newly created trace is in "pending" state and transitions to "validated" only after the threshold number of independent confirmations are recorded
  5. Alembic migrations run cleanly on a fresh database; Docker Compose brings up postgres/pgvector, redis, api, and worker services in one command
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Project skeleton, uv workspace, SQLAlchemy ORM models, database config, tag normalization
- [x] 01-02-PLAN.md — Docker Compose environment (postgres/pgvector, redis, api, worker), Dockerfile, env config
- [x] 01-03-PLAN.md — Alembic async migrations, pgvector HNSW index, fixture data seeding, end-to-end validation

### Phase 2: Core API — Auth, Safety, Contribution
**Goal**: Agents can authenticate, submit traces, amend traces, and vote — with PII scanning, content moderation, and staleness detection enforced at the write path before anything touches the database
**Depends on**: Phase 1
**Requirements**: API-01, API-02, SAFE-01, SAFE-02, SAFE-03, SAFE-04, CONT-01, CONT-02, CONT-03, CONT-04
**Success Criteria** (what must be TRUE):
  1. An API request without a valid API key is rejected with 401; a valid key grants access to endpoints within its permission scope
  2. Submitting a trace containing an API key, password, or credential token is rejected before storage — the trace is never written to the database
  3. An agent can submit a new trace (context, solution, tags) and receive a 202 Accepted response; the trace appears in the database in "pending" state
  4. An agent can upvote or downvote a trace; downvotes require a contextual tag (e.g., outdated, wrong, security_concern); the vote is recorded and associated with the voter's identity
  5. An agent can submit an amendment to an existing trace with an improved solution and explanation; the amendment is stored and linked to the original trace
  6. A trace flagged by any agent as harmful or spam is queryable by a moderator and can be removed; a trace whose referenced library/API version is outdated is automatically flagged as potentially stale
**Plans:** 4 plans

Plans:
- [x] 02-01-PLAN.md — Auth dependency (API key + SHA-256 hash), Redis lifespan, token-bucket rate limiter, Amendment model, Alembic migration 0002
- [x] 02-02-PLAN.md — PII/secrets scanner (detect-secrets), staleness checker (PyPI), trust service (vote + promotion), all Pydantic schemas
- [x] 02-03-PLAN.md — POST /api/v1/traces, POST /traces/{id}/votes, POST /traces/{id}/amendments, POST /keys (key generation), GET /traces/{id}
- [x] 02-04-PLAN.md — Content moderation: POST /traces/{id}/flag, GET /moderation/flagged, DELETE /moderation/traces/{id}

### Phase 3: Search + Discovery
**Goal**: An agent can instantly find relevant traces using natural language, structured tags, or both — with results ranked by relevance weighted against trust score
**Depends on**: Phase 2
**Requirements**: SRCH-01, SRCH-02, SRCH-03, SRCH-04
**Success Criteria** (what must be TRUE):
  1. An agent can query traces with a natural language description and receive semantically relevant results — results reflect meaning, not just keyword overlap
  2. An agent can filter traces by one or more structured tags (language, framework, API, task type) and receive only traces matching all specified tags
  3. A single hybrid search query combining natural language and tag filters returns results that satisfy both the semantic match and the tag constraints simultaneously
  4. Search results are ordered so that a trace with high semantic relevance and high trust score ranks above a trace with identical semantic relevance but low trust score
  5. A newly contributed trace (with embedding generated) appears in search results within seconds of embedding completion — no restart or manual index refresh required
**Plans:** 3 plans

Plans:
- [x] 03-01-PLAN.md — Async embedding worker (OpenAI text-embedding-3-small) + EmbeddingService + docker-compose worker wiring
- [x] 03-02-PLAN.md — POST /api/v1/traces/search — hybrid query (pgvector cosine ANN + tag pre-filter + trust-weighted re-ranking)
- [x] 03-03-PLAN.md — Observability: structlog JSON logging, Prometheus metrics (/metrics), request middleware, embedding drift detection

### Phase 4: Reputation Engine
**Goal**: Agent contributions earn trust over time, high-reputation votes carry more weight, and reputation is tracked per domain so a Python expert's vote on a Python trace matters more than a stranger's
**Depends on**: Phase 2 (votes must exist before reputation can be computed)
**Requirements**: REPU-01, REPU-02, REPU-03
**Success Criteria** (what must be TRUE):
  1. Each contributor has a trust score computed via Wilson score confidence interval — a trace with one upvote does not outrank a trace with 50 upvotes and 5 downvotes
  2. A new contributor's first vote counts less than a vote from a contributor with established reputation — the weight difference is measurable and documented
  3. Registering with an email address is required to establish a contributor identity — anonymous API key usage without email registration cannot submit contributions
  4. A contributor's reputation is tracked separately by domain context (e.g., Python, JavaScript) — high Python reputation does not automatically grant high JavaScript reputation
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — Wilson score function (TDD), ContributorDomainReputation model + migration, RequireEmail dependency, reputation schemas
- [x] 04-02-PLAN.md — Domain-aware vote weight wiring, per-domain reputation update on vote, RequireEmail on write endpoints, reputation read endpoint

### Phase 5: MCP Server
**Goal**: Any MCP-compatible agent can search, contribute, and vote on CommonTrace traces through a stateless protocol adapter that never blocks an agent session — even when the backend is down
**Depends on**: Phase 3 (search must exist), Phase 4 (reputation must be live)
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04
**Success Criteria** (what must be TRUE):
  1. An MCP-compatible agent configured with the CommonTrace MCP server can call search_traces, contribute_trace, and vote_trace tools and receive structured results
  2. When the CommonTrace backend is unavailable or times out, the MCP server returns a graceful degradation message — the agent session continues without error or hang
  3. The MCP server is accessible via Streamable HTTP transport for remote agents and via stdio transport for local development — both work without code changes to the backend
  4. API key credentials are injected from MCP client configuration — they never appear as tool call parameters visible to agent prompts
**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md — FastMCP 3.0.0 server with 5 tool definitions (search_traces, contribute_trace, vote_trace, get_trace, list_tags), backend HTTP client, response formatters, GET /api/v1/tags endpoint, Docker Compose service
- [ ] 05-02-PLAN.md — Custom circuit breaker (closed/open/half-open), per-operation SLA timeouts (200ms read, 2s write), graceful degradation messages in all tools, API key injection via CurrentHeaders() + env var fallback

### Phase 6: Claude Code Skill
**Goal**: Claude Code agents benefit from CommonTrace automatically during every session and can contribute knowledge explicitly — without CommonTrace ever blocking their work or polluting the knowledge base with unreviewed contributions
**Depends on**: Phase 5
**Requirements**: SKIL-01, SKIL-02, SKIL-03, SKIL-04
**Success Criteria** (what must be TRUE):
  1. A Claude Code agent with the skill installed can run /trace:search [query] and /trace:contribute and receive structured results or initiate a contribution flow
  2. Installing the skill automatically configures the MCP server connection — no manual MCP configuration is required
  3. At the start of a task, the skill silently queries CommonTrace based on detected context (repo, file type, error message) and injects relevant traces into agent context — without user prompting and without blocking task start
  4. After successfully completing a task, the skill prompts the agent to contribute a trace — the agent can preview and confirm before submission; no trace is submitted without explicit confirmation
**Plans**: TBD

Plans:
- [ ] 06-01: CLAUDE.md skill definition; /trace:search and /trace:contribute slash command implementations; MCP auto-configuration on install
- [ ] 06-02: Auto-query hook (context detection heuristics, silent injection, threshold gating); post-task contribution prompt with preview-confirm flow

### Phase 7: Cold Start + Launch Hardening
**Goal**: The knowledge base contains enough high-quality traces to deliver immediate value on first use, and the system is validated at realistic load before any public announcement
**Depends on**: Phase 6 (full stack must be operational end-to-end)
**Requirements**: SEED-01
**Success Criteria** (what must be TRUE):
  1. A new agent connecting to CommonTrace for the first time finds 200+ validated traces covering common coding tasks (React setup, PostgreSQL migrations, Docker configuration, common API integrations) — search returns relevant results on the first query
  2. The system sustains target load with pgvector HNSW delivering under 50ms p99 ANN search latency at 100K traces — validated by a capacity test before launch
  3. Token-bucket rate limiting correctly handles bursty agent workloads — agents are not incorrectly blocked during legitimate burst activity and the freemium tier limits are validated against real request patterns
**Plans**: TBD

Plans:
- [ ] 07-01: 200-500 hand-curated seed traces (common Claude Code tasks); import pipeline to load seeds into production database
- [ ] 07-02: Capacity test at 100K traces (pgvector HNSW p99 latency); rate limit validation under bursty load; freemium tier boundary testing

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 3/3 | Complete | 2026-02-20 |
| 2. Core API — Auth, Safety, Contribution | 4/4 | Complete | 2026-02-20 |
| 3. Search + Discovery | 3/3 | Complete | 2026-02-20 |
| 4. Reputation Engine | 2/2 | Complete | 2026-02-20 |
| 5. MCP Server | 0/2 | Planned | - |
| 6. Claude Code Skill | 0/2 | Not started | - |
| 7. Cold Start + Launch Hardening | 0/2 | Not started | - |
