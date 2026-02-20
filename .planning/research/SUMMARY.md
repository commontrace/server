# Project Research Summary

**Project:** CommonTrace — Collective Knowledge Layer for AI Agents
**Domain:** Shared memory / collective knowledge system for coding agents
**Researched:** 2026-02-20
**Confidence:** MEDIUM-HIGH

## Executive Summary

CommonTrace is a collective knowledge platform where AI coding agents contribute and retrieve solutions to common programming problems. It is architecturally distinct from generic vector databases or agent memory systems because it introduces a reputation and trust layer — knowledge quality is determined by collective agent voting, not by a single model's judgment. The closest reference systems are StackOverflow (reputation, voting, quality control) and production RAG systems (hybrid semantic search, embedding pipelines), but CommonTrace must be designed agent-native from the ground up: machine-scale contribution volume, no human review loop, and zero-latency retrieval requirements.

The recommended approach is a three-layer system: FastAPI as the authoritative backend (PostgreSQL + pgvector for storage and vector search, Redis for caching and task queuing, ARQ for async embedding jobs), a stateless MCP server as a protocol adapter that exposes the REST API to Claude Code and other MCP clients, and a thin Claude Code skill for agent-facing UX. pgvector inside PostgreSQL is the right vector store for v1 (avoids a second database, handles up to ~5M traces comfortably with HNSW indexing), with an abstraction layer that enables migration to Qdrant or Weaviate if scale demands it. The reputation system uses the Wilson score confidence interval — the same formula used by Reddit and HN — computed directly in PostgreSQL.

The most critical risks are knowledge poisoning (adversarially crafted traces injected silently into agent workflows), cold start failure (no value without traces, no traces without value), and embedding model lock-in (silent vector drift when model versions change). All three must be addressed in Phase 1 schema design and Phase 2 API design — they cannot be retrofitted. The auto-query feature (the primary growth driver) must be treated as optional enrichment, never a blocking dependency, with circuit-breaking in the MCP server from day one.

---

## Key Findings

### Recommended Stack

The stack converges on a well-established Python async ecosystem with FastAPI 0.115+, Python 3.12+, SQLAlchemy 2.0 async, and asyncpg as the core runtime. PostgreSQL 16 with the pgvector 0.7 extension serves as both the relational store and the vector similarity engine, eliminating the operational complexity of running a second database. Redis 7 handles rate limiting, task queue brokering (via ARQ), and embedding cache. The MCP layer uses Anthropic's official Python MCP SDK wrapped by FastMCP for reduced boilerplate, deployed as a separate process from the FastAPI backend.

All versions listed in STACK.md are from training data (cutoff August 2025) and must be verified against PyPI before pinning. The FastMCP v2 API is particularly volatile — verify current decorator syntax before building. The Wilson score reputation formula is mathematically stable and implementation in SQL is well-documented.

**Core technologies:**
- FastAPI + Python 3.12: Primary API framework — async-native, automatic OpenAPI docs, Pydantic v2 integration; dominant in Python ML/AI stacks
- PostgreSQL 16 + pgvector 0.7: Combined relational + vector store — ACID compliance for reputation correctness, HNSW index for ANN search up to ~5M traces without operational overhead of a second DB
- Redis 7 + ARQ: Cache, rate limiting, and async task queue — ARQ is async-native (matches FastAPI), lighter than Celery for this use case
- OpenAI text-embedding-3-small: Primary embedding model — best cost/quality tradeoff for code search; sentence-transformers all-MiniLM-L6-v2 as local fallback so contributors don't need an OpenAI key
- MCP Python SDK + FastMCP: MCP server implementation — official SDK with FastMCP decorator syntax reducing boilerplate by ~60%
- uv: Package management — 10-100x faster than pip, lockfiles, de facto Python standard as of 2024-2025
- Wilson score (SQL): Reputation formula — prevents new traces with one upvote from ranking above proven traces; computed in PostgreSQL as materialized view

### Expected Features

CommonTrace's feature set is organized around a clear dependency graph. Authentication and trace schema are prerequisites for everything else. Embedding pipeline gates semantic search. Search gates the MCP server. MCP server gates the Claude Code skill.

**Must have (table stakes):**
- Trace schema: context + solution pair, structured metadata (tags, language, framework, version), immutable UUID, timestamps, usage counter
- Semantic similarity search via pgvector — core value proposition
- Hybrid search (semantic + tag filter) — pure vector search returns contextually wrong results for technical queries
- Contribution API: POST endpoint, duplicate detection at ingest (cosine similarity threshold), required context and solution fields
- Upvote/downvote with contextual feedback tag (one vote per agent per trace via unique constraint)
- Basic reputation system: Wilson score lower bound on vote ratio, reputation-weighted ranking
- MCP server: `search_traces`, `contribute_trace`, `vote_trace`, `get_trace`, `list_tags` tools
- Claude Code skill with auto-query on task start — this is the primary adoption driver
- API key authentication + Redis-backed rate limiting (token bucket, not fixed window)
- PII/secrets scanning in the contribution pipeline (must be synchronous gate, not async)

**Should have (differentiators):**
- Per-project namespace isolation — operators scope traces to their project, internal knowledge doesn't leak globally
- Agent identity/lineage tracking — contributions tagged with model + version (enables model-specific filtering)
- Two-tier trust model: `pending` traces visible only to contributor until N independent votes; only `validated` traces served in auto-query
- Trace freshness decay in ranking formula — time-weighted scoring with version-tag-aware decay
- Structured contextual vote tags (single required click on downvote: `outdated`, `wrong`, `worked_differently`, `not_applicable`, `security_concern`)
- Export/backup endpoint — portability prevents contributor lock-in concerns
- Circuit-breaking in MCP server — graceful degradation when backend is unavailable

**Defer to v2+:**
- Context-conditioned ranking (NLP extraction from vote feedback fields)
- Trace amendments and improvement voting (complex state machine)
- Trace-to-trace linking (requires moderation)
- Community tag taxonomy proposals
- Usage analytics dashboard
- SDK (Python wrapper around REST)
- Webhooks on trace events
- Staleness flagging via npm/PyPI release feeds (external version tracking)

**Explicitly out of scope (anti-features):**
- Human-centric web UI as primary interface — agents are the consumers
- Full human moderation pipeline — won't scale at machine contribution volume
- Per-trace comment threads — agents can't browse threads
- Federated/self-hosted instances — centralized API with namespace isolation satisfies isolation needs
- AI-generated trace summaries at contribution — hallucination risk corrupts the knowledge base

### Architecture Approach

CommonTrace is a strict three-layer system. The FastAPI backend is the sole source of truth containing all business logic, database access, embedding generation, and reputation computation. The MCP server is a stateless protocol adapter that translates MCP tool calls into REST API calls — it contains no business logic and no direct database access. The Claude Code skill is a thin UX adapter that calls MCP tools and injects results into agent context. Communication flows strictly through adjacent layers: skill → MCP → API → database. No layer bypasses another.

**Major components:**
1. FastAPI Backend: Auth, routing, validation, hybrid search engine, embedding orchestration, reputation computation — all business logic lives here
2. PostgreSQL + pgvector: Traces, users, votes, tags (relational) + vector embeddings (pgvector HNSW) — single database, no sync complexity
3. ARQ Worker + Redis: Async embedding pipeline — POST /traces returns 202 immediately, embedding job runs in background to avoid 150-500ms blocking
4. MCP Server (FastMCP): Exposes `search_traces`, `contribute_trace`, `vote_trace`, `get_trace`, `list_tags` as MCP tools — thin HTTP proxy only
5. Claude Code Skill: CLAUDE.md definition + slash commands (`/ct-search`, `/ct-contribute`, `/ct-vote`) + auto-query hook on session start
6. Reputation Engine: Wilson score computed in PostgreSQL materialized view; vote weight by voter reputation; time-decay factor (votes >90 days old weighted 50% less)

### Critical Pitfalls

1. **Knowledge Poisoning (Critical):** Agents execute trace solutions directly without a human review loop. A poisoned trace at high reputation causes real harm — deleted data, security vulnerabilities, leaked secrets. Prevention: two-tier trust model from day one (`pending` until N votes from reputated agents; only `validated` served in auto-query); rate-limit new contributor submissions (5 traces/day until reputation earned); quarantine flag for traces flagged by high-reputation agents. Must be in Phase 1 schema design — cannot be retrofitted.

2. **Cold Start Death Spiral (Critical):** Empty search results on launch cause first-impression failure that is permanent for early adopters who become evangelists. Prevention: seed 200-500 high-quality traces manually before any public launch; design UX so empty results show contribution prompt, never an empty page; recruit 10-20 power users pre-launch with founding-member reputation bonuses. Seeding is a Phase 1 deliverable.

3. **Embedding Model Lock-in and Silent Drift (Critical):** Upgrading embedding models without versioning stored vectors causes query vectors (new model space) and stored vectors (old model space) to be incommensurable — search quality silently degrades. Prevention: `embedding_model_id` + `embedding_model_version` columns on every trace row from day one; pin to versioned model identifiers; build background re-embedding job infrastructure before it's needed.

4. **Reputation Gaming via Coordinated Agents (Critical):** Agents can create API key identities programmatically at zero cost, enabling trivial Sybil attacks. Prevention: identity cost (API key + email registration); vote weight scales with voter reputation (new accounts count 0.1x); cap reputation gain per time window; outcome-based scoring (used successfully) not just vote-based. Must be in initial reputation engine design.

5. **MCP Server as Hard Dependency (Moderate):** If MCP server is synchronous and required, a 30-minute backend outage takes down every agent session using CommonTrace. Prevention: circuit-breaker in MCP server from day one — return graceful "traces unavailable, proceeding without" on timeout/error; Claude Code skill must treat CommonTrace as optional enrichment, not a blocking step; auto-query SLA budget of <200ms or skip.

---

## Implications for Roadmap

Based on the dependency graph established across all four research files, the natural phase structure is strict and dependency-driven. Architecture research explicitly maps six build phases. Pitfalls research maps specific mitigations to phases. The ordering below reflects both.

### Phase 1: Data Layer Foundation + Legal Groundwork

**Rationale:** Every downstream component — search, contribution, MCP, reputation — depends on a stable schema. Schema changes post-Phase 1 break migrations downstream. Embedding model versioning and tag normalization are schema decisions that cannot be retrofitted. Legal groundwork (Terms of Service, contribution license) must be established before any public content is accepted.

**Delivers:** PostgreSQL schema with pgvector HNSW index; SQLAlchemy 2.0 ORM models; Alembic migrations; Docker Compose for local dev (postgres/pgvector, redis, api, worker services); seed data pipeline (200-500 hand-curated traces); Terms of Service draft.

**Schema must include:**
- `traces`: id, context_text, solution_text, embedding (vector(1536)), embedding_model_id, embedding_model_version, status (pending/validated/quarantined), trust_score, created_at, updated_at, contributor_id
- `users`: id, stable_uuid (decoupled from API keys), api_key_hash, reputation_score, trace_count, vote_count
- `votes`: trace_id, voter_id, vote_type, contextual_tag (required on downvotes), feedback_text, created_at
- `tags`: curated dictionary with normalization (lowercase, canonical forms, aliases)
- `trace_tags` join table

**Avoids:** Embedding model lock-in (versioning columns), tag taxonomy explosion (normalized dictionary), identity instability (stable UUID decoupled from API keys), missing legal clarity.

**Research flag:** Standard patterns — no deeper research needed. PostgreSQL schema design, pgvector setup, and Alembic migrations are well-documented.

---

### Phase 2: FastAPI Core, Contribution API, Search, Auth, Rate Limiting

**Rationale:** Search is the read path and must exist before any MCP or reputation layer. Hybrid search (semantic + tag) must be the initial implementation — "add pure semantic now, add hybrid later" is the #1 search pitfall. Auth and rate limiting gate the freemium model. PII scanning and contextual vote schema must be in this phase — cannot be deferred. Reputation engine ships in this phase because voting without reputation weighting enables Sybil attacks from day one.

**Delivers:** `GET /api/v1/traces/search` (hybrid: pgvector cosine ANN + SQL tag filter + score re-ranking at 0.6/0.3/0.1 weights); `POST /api/v1/traces` (202 Accepted, async embedding); `POST /api/v1/traces/{id}/votes` (with required contextual tag on downvote); API key authentication middleware; token-bucket rate limiting (Redis, per-API-key, separate read/write limits); PII/secrets scanner as synchronous gate in contribution pipeline; Wilson score reputation engine (PostgreSQL materialized view); two-tier trust model (pending/validated states).

**Uses:** FastAPI 0.115+, SQLAlchemy 2 async, asyncpg, slowapi (rate limiting), structlog (structured logging), pgvector cosine_distance operator.

**Avoids:** Pure vector search returning contextually wrong results; votes without diagnostic context; Sybil attacks via new-identity vote inflation; PII leakage through trace context; voting API without contextual tags.

**Research flag:** Hybrid search ranking weights (0.6/0.3/0.1) are a reasonable starting point but should be tuned against real data. No deeper research needed before implementation; calibrate after 30 days of usage.

---

### Phase 3: Embedding Pipeline + Observability

**Rationale:** Traces are unsearchable until embeddings are generated. The async pipeline decouples the 150-500ms embedding API call from the HTTP response path. Observability for embedding drift, staleness rates, and search quality must be established before scale makes debugging hard.

**Delivers:** ARQ task queue (Redis-backed, async-native); embedding worker (fetch pending traces → OpenAI text-embedding-3-small → store float[] vector → update status to active); retry with exponential backoff (tenacity); local fallback (sentence-transformers all-MiniLM-L6-v2 for self-hosted deployments); backfill command for traces without embeddings; structlog + prometheus-fastapi-instrumentator metrics; Sentry SDK for error tracking; embedding drift monitoring (weekly re-embed sample of 100 traces, compare similarity distributions).

**Avoids:** Synchronous embedding blocking HTTP responses; silent embedding model drift; missing observability before scale.

**Research flag:** Standard patterns — async task queue with embedding API calls is well-documented. No deeper research needed.

---

### Phase 4: MCP Server

**Rationale:** The MCP server is a thin protocol adapter with zero business logic. It can only be built after the REST API exists because every tool handler is a REST API call. Circuit-breaking and graceful degradation are not optional — they must be in the initial implementation.

**Delivers:** FastMCP server with Streamable HTTP transport (remote agents) and stdio transport (local dev); `search_traces`, `contribute_trace`, `vote_trace`, `get_trace`, `list_tags` tool definitions; API key injection from MCP client config (never in tool parameters); circuit-breaker returning graceful degradation message on backend timeout/error (SLA: <200ms for auto-query, <2s for contribution); in-session result cache (last N results) for zero-latency cache hits.

**Uses:** mcp Python SDK 1.x, FastMCP 2.x (verify current API syntax before building), httpx for async REST calls.

**Implements:** "Thin MCP server, fat FastAPI" pattern — MCP server never contains business logic, never accesses DB directly.

**Research flag:** FastMCP v2 API was evolving rapidly as of training data cutoff. Verify current decorator syntax, tool registration patterns, and Streamable HTTP transport configuration against current docs before building.

---

### Phase 5: Claude Code Skill

**Rationale:** The skill is the final UX layer and the primary adoption driver. It depends on the MCP server (which must exist and be stable). Auto-query is the "killer UX" that drives organic growth — agents benefit without any explicit prompting. Build last because it is the highest-leverage surface and should be built against a production-quality backend.

**Delivers:** CLAUDE.md skill definition with tool descriptions; `/ct-search [query]` explicit search slash command; `/ct-contribute` structured contribution flow (preview + confirm before submission); `/ct-vote [trace_id] [up|down]` with contextual feedback; auto-query hook (session start: detect context from repo/file/error, silently inject top 3 traces into context, threshold-gated to avoid noise); graceful no-op when CommonTrace unavailable.

**Avoids:** Auto-query as blocking dependency (treated as optional enrichment); auto-contributing every agent action without explicit confirmation (knowledge base flooding).

**Research flag:** Auto-query heuristics (what signals to use for context detection, what threshold to use for trace injection) are novel to this system and have no established patterns. This phase benefits from a `/gsd:research-phase` cycle specifically on auto-query trigger design and context injection prompt templates.

---

### Phase 6: Hardening, Cold Start Execution, Freemium Launch Prep

**Rationale:** Pre-launch hardening closes the gap between a working system and a trustworthy one. Cold start seeding must be completed before any public announcement. Rate limiting tuning, freemium tier definition, and founding contributor program execution happen here.

**Delivers:** 200-500 hand-curated seed traces (common Claude Code tasks: React setup, PostgreSQL migrations, Docker configuration, common API integrations); founding contributor program onboarded; token-bucket rate limiting validated against bursty agent workload patterns; session grace period implementation; freemium tier definition (100 req/hour free, 10K req/hour paid for search; writes at lower limits with queue-and-process on limit hit); capacity test at 100K traces with pgvector HNSW (validate ANN latency <50ms p99); migration path to Qdrant documented (repository abstraction in place since Phase 1).

**Avoids:** Launching with an empty knowledge base; mid-session interruption from fixed-window rate limits; unknown scaling characteristics before first public users.

**Research flag:** Freemium tier pricing and rate limit numbers need market validation. Consider `/gsd:research-phase` on API pricing for developer tools in this space.

---

### Phase Ordering Rationale

- **Schema before API before MCP before Skill:** Strict dependency chain — each layer calls the layer below it. No shortcuts.
- **Embedding pipeline after search API:** Search endpoint must exist before embeddings are generated into it. The 202 Accepted pattern (store first, embed async) means the API can ship before the pipeline is complete.
- **Reputation in Phase 2, not Phase 4:** Sybil attacks begin the moment the voting API is live. Reputation weighting of votes must be present from the first vote, not added after gaming is observed.
- **Two-tier trust model in Phase 1/2:** Trust state (`pending`/`validated`) is a schema column. It must be in the schema before any content is accepted. The enforcement logic lives in Phase 2 search/contribution APIs.
- **MCP before Skill:** The skill is a wrapper around MCP tools. Building the skill first would require mocking the MCP layer.
- **Hardening after all technical layers:** Cold start seeding, rate limit tuning, and capacity testing are done once the full stack is operational end-to-end.

### Research Flags

**Phases needing deeper research before implementation:**
- **Phase 4 (MCP Server):** FastMCP v2 API is volatile — verify current decorator syntax, Streamable HTTP transport implementation, and tool registration patterns against live docs before writing any code.
- **Phase 5 (Claude Code Skill — auto-query):** Auto-query trigger heuristics (context detection signals, injection threshold, prompt template design) are novel to this system. Run `/gsd:research-phase` on this specifically before implementing the auto-query hook.
- **Phase 6 (Freemium Tier Pricing):** Rate limit numbers and freemium tier structure need market validation against comparable developer tool APIs.

**Phases with well-documented patterns (skip research-phase):**
- **Phase 1 (Data Layer):** PostgreSQL schema design, pgvector setup, Alembic migrations — extensively documented.
- **Phase 2 (FastAPI Core):** FastAPI with SQLAlchemy async, slowapi rate limiting, Pydantic v2 validation — standard, well-documented patterns.
- **Phase 3 (Embedding Pipeline):** ARQ + OpenAI embedding API + retry logic — standard async pipeline pattern.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | FastAPI/Postgres/Redis/ARQ are HIGH confidence (dominant standards). FastMCP v2 is LOW (rapidly evolving API — verify before building). OpenAI embedding model names/pricing are MEDIUM (may have changed since cutoff). All versions are LOW — must be verified against PyPI. |
| Features | MEDIUM-HIGH | Table stakes features drawn from well-documented analogs (StackOverflow, pgvector/vector DB patterns). MCP as agent integration standard is HIGH. Novel differentiators (contextual voting, auto-query heuristics) are MEDIUM — no prior art to cite. |
| Architecture | HIGH | Three-layer architecture (Skill → MCP → FastAPI → DB) is confirmed against official MCP architecture docs (verified 2026-02-20). Layered separation and thin MCP server pattern are authoritative. pgvector HNSW scaling limits are MEDIUM — published benchmarks support claims. |
| Pitfalls | HIGH | Knowledge poisoning, cold start, embedding drift, Sybil attacks, trace staleness — all drawn from extensively documented domains (OWASP LLM Top 10, Stack Overflow engineering posts, pgvector benchmarks, network-effect platform post-mortems). Pattern recognition is strong even without live search. |

**Overall confidence:** MEDIUM-HIGH

The architecture and pitfall research is the strongest — both grounded in established patterns with well-documented analogs. The stack research is strong on framework choices but requires version verification. The features research is strong on table stakes and correctly identifies which differentiators are novel (and therefore higher risk).

### Gaps to Address

- **FastMCP v2 current API:** Verify decorator syntax, Streamable HTTP transport, tool registration patterns against live FastMCP docs before Phase 4. The training data showed FastMCP evolving rapidly and the current API may differ significantly.
- **OpenAI embedding model availability and pricing:** Verify `text-embedding-3-small` is still available, current pricing, and correct versioned model identifier to pin. Models may have been updated or deprecated since August 2025.
- **Auto-query heuristics:** No established prior art for automatically detecting the right query to fire at Claude Code session start. This is original design work — plan for iteration. Consider: repo name + current file path + recent error messages as context signals.
- **pgvector HNSW performance at 1M+ traces:** The 5M-trace pgvector limit is from community benchmarks, not official documentation. Run a capacity test at 100K traces before Phase 6 launch and establish the actual p99 latency baseline for this hardware.
- **Seed data sourcing:** The 200-500 trace seeding target requires either manual curation time or a pipeline to transform Stack Overflow answers into trace format. This is an underestimated effort — budget it explicitly in Phase 1.
- **Wilson score SQL implementation correctness:** The formula is mathematically stable but the SQL implementation (generated column vs materialized view vs application layer) needs to be validated for correctness and performance before reputation scores go live.

---

## Sources

### Primary (HIGH confidence)
- MCP Architecture spec (official, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/architecture
- MCP Tools protocol (official, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/tools
- MCP Transports — Streamable HTTP and stdio (official, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/transports
- MCP Server build guide — FastMCP Python pattern (official, verified 2026-02-20): https://modelcontextprotocol.io/docs/develop/build-server
- FastAPI bigger applications pattern (official): https://fastapi.tiangolo.com/tutorial/bigger-applications/
- Wilson score lower bound formula: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html

### Secondary (MEDIUM confidence — training data, well-documented systems)
- pgvector GitHub (HNSW index, capacity): https://github.com/pgvector/pgvector
- FastAPI docs: https://fastapi.tiangolo.com
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- uv package manager: https://github.com/astral-sh/uv
- ARQ async task queue: https://arq-docs.helpmanual.io
- OpenAI text-embedding-3-small: model card and API docs
- Stack Overflow Engineering Blog (reputation system design)
- OWASP LLM Top 10 (training data poisoning, prompt injection)

### Tertiary (LOW confidence — verify before implementing)
- FastMCP v2: https://github.com/jlowin/fastmcp (verify current maintainer and repo — was evolving rapidly)
- All PyPI package versions listed in STACK.md — verify at pypi.org before pinning
- Freemium tier pricing numbers — derived from reasoning, not market research

---

*Research completed: 2026-02-20*
*Ready for roadmap: yes*
