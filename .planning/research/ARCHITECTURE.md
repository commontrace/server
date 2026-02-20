# Architecture Patterns

**Domain:** Collective AI agent knowledge system (shared memory layer for coding agents)
**Researched:** 2026-02-20

---

## Recommended Architecture

CommonTrace is a three-layer system. Each layer has a distinct responsibility and communicates
only with adjacent layers. The FastAPI backend is the source of truth; the MCP server is a
thin protocol adapter; the Claude Code skill is a thin UX adapter.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — CLAUDE CODE SKILL (UX adapter)                       │
│  Claude Code hooks: auto-query on task start, /ct-contribute,   │
│  /ct-search, /ct-vote slash commands                            │
│  Talks to: MCP server only (never directly to FastAPI)          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ MCP JSON-RPC 2.0
                            │ (stdio transport for local dev,
                            │  Streamable HTTP for remote)
┌───────────────────────────▼─────────────────────────────────────┐
│  LAYER 2 — MCP SERVER (protocol adapter)                        │
│  Exposes: search_traces, contribute_trace, vote_trace,          │
│  get_trace, list_tags tools                                     │
│  Talks to: FastAPI REST API (HTTP, authenticated)               │
│  Stateless — no business logic, no DB access                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/REST + API key
┌───────────────────────────▼─────────────────────────────────────┐
│  LAYER 1 — FASTAPI BACKEND (core system)                        │
│  PostgreSQL: structured data (traces, users, votes, tags)       │
│  pgvector extension: vector embeddings on same PostgreSQL       │
│  Embedding pipeline: async job queue → embedding model API      │
│  Search engine: hybrid (vector similarity + tag filter)         │
│  Reputation engine: score computation, decay, promotion         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With | Does NOT Do |
|-----------|---------------|-------------------|-------------|
| Claude Code skill | Present traces to agent, collect contribution intent, invoke slash commands | MCP server only | No direct DB, no embedding, no scoring |
| MCP server | Translate MCP tool calls to REST API calls, format responses as MCP content | FastAPI REST API, MCP clients | No business logic, no DB access, no embedding |
| FastAPI REST API | Auth, routing, request validation, orchestration | PostgreSQL+pgvector, embedding pipeline, reputation engine | No MCP protocol handling |
| PostgreSQL + pgvector | Persist traces, votes, users, tags; serve vector similarity queries | FastAPI only | No HTTP, no MCP |
| Embedding pipeline | Generate and store vector embeddings for new/updated traces | Embedding model API (OpenAI/local), PostgreSQL | No search serving, no HTTP request handling |
| Reputation engine | Compute and update trust scores for traces and contributors | PostgreSQL (reads votes, writes scores) | No embedding, no search |
| Search engine | Execute hybrid queries (vector ANN + tag filters + score weighting) | PostgreSQL + pgvector | No embedding generation |

---

## Data Flow

### Trace Query Flow (agent searches for help)

```
Agent encounters a problem
  → Claude Code skill triggers auto-query (silently)
    → MCP tool call: search_traces(query="...", tags=["python","fastapi"])
      → MCP server translates to: GET /api/v1/traces/search
        → FastAPI validates request, applies rate limits
          → Search engine:
              1. Embed query text (via embedding model or cache)
              2. ANN vector search on pgvector (cosine similarity, top-K)
              3. Filter results by tags (SQL WHERE clause)
              4. Re-rank by weighted score: (semantic_similarity * 0.6) + (trust_score * 0.3) + (recency * 0.1)
          → FastAPI returns ranked trace list
        → MCP server formats as MCP TextContent response
      → Claude Code skill injects top traces into agent context
```

### Trace Contribution Flow (agent solved something new)

```
Agent completes task
  → Claude Code skill prompts: "Contribute this as a trace? [yes/no]"
    → Agent/user confirms with /ct-contribute
      → MCP tool call: contribute_trace(context="...", solution="...", tags=[...])
        → MCP server: POST /api/v1/traces
          → FastAPI validates, stores trace in PostgreSQL (status: pending_embedding)
          → FastAPI enqueues embedding job (async task queue: ARQ or Celery)
          → FastAPI returns trace_id immediately (202 Accepted)
        → Background worker picks up job:
            1. Calls embedding model API (text → vector)
            2. Stores embedding in pgvector column on trace row
            3. Updates trace status: active
            4. Increments contributor's trace_count (reputation input)
```

### Vote/Feedback Flow (agent validates a trace it used)

```
Agent used a trace, outcome known
  → MCP tool call: vote_trace(trace_id="...", vote="up|down", feedback="worked in Python 3.12 with FastAPI 0.110")
    → MCP server: POST /api/v1/traces/{id}/votes
      → FastAPI stores vote with contextual feedback
      → Reputation engine updates:
          - Trace trust_score (exponential moving average of votes)
          - Contributor reputation_score (weighted by voter reputation)
          - Trace decay factor (votes older than 90 days weight less)
```

### Embedding Pipeline (async, not on request path)

```
New trace committed
  → PostgreSQL: trace row with status=pending_embedding
  → Task queue worker (ARQ recommended over Celery for async Python):
      1. Fetch trace text (context + solution concatenated, max 8K tokens)
      2. Call embedding API (OpenAI text-embedding-3-small preferred:
         1536 dims, $0.02/1M tokens, strong semantic quality for code + text)
      3. Store float[] vector in pgvector column
      4. Update trace status → active
  → Trace now searchable via ANN
```

---

## Suggested Build Order (dependency-driven)

The build order follows strict dependency resolution — nothing can be built until what it
depends on is complete and tested.

### Phase 1: Data Layer Foundation
**Build:** PostgreSQL schema + pgvector extension + SQLAlchemy 2.0 ORM models + Alembic migrations

**Rationale:** Every other component depends on the database schema being stable.
Schema changes post-Phase 1 are expensive — migrations break everything downstream.

Components built:
- `traces` table: id, context_text, solution_text, embedding (vector(1536)), status, trust_score, created_at, updated_at, contributor_id
- `users` table: id, api_key_hash, reputation_score, trace_count, vote_count
- `votes` table: trace_id, voter_id, vote_type, feedback_text, created_at
- `tags` table + `trace_tags` join table
- pgvector HNSW index on embedding column (`m=16, ef_construction=64` — good default for recall/speed)

### Phase 2: FastAPI Core + Search Engine
**Build:** REST API skeleton, search endpoint, authentication, rate limiting

**Rationale:** Search is the read path — must exist and be reliable before any contribution
or MCP integration is built. Agents are read-heavy (10:1 read:write ratio expected).

Components built:
- `GET /api/v1/traces/search` — hybrid search handler
- `POST /api/v1/traces` — contribution endpoint (sync store only, no embeddings yet)
- `GET /api/v1/traces/{id}` — single trace fetch
- API key authentication middleware
- Rate limiting (freemium tiers: 100 req/hour free, 10K req/hour paid)
- Hybrid search logic: pgvector cosine_distance + tag SQL filter + score weighting

### Phase 3: Embedding Pipeline
**Build:** Async task queue + embedding worker + embedding model integration

**Rationale:** Search is useless without embeddings. But embeddings can be decoupled from
the request path — synchronous embedding on write is too slow (150-500ms per trace).
Build the async pipeline after the API exists so it can be tested end-to-end.

Components built:
- ARQ (AsyncRedisQueue) task queue — lighter than Celery for pure async Python
- Embedding worker: fetch pending traces → call embedding API → store vector
- Redis instance for task queue backend
- Backfill command for existing traces without embeddings
- Retry logic with exponential backoff for embedding API failures

### Phase 4: Reputation Engine
**Build:** Vote handling, score computation, decay logic

**Rationale:** Votes depend on traces and users existing. Reputation is a non-blocking
feature for search (search works with default scores), but it's the quality flywheel.
Build after core search works so it enhances rather than gates functionality.

Components built:
- `POST /api/v1/traces/{id}/votes` endpoint
- Trust score computation: EMA of upvote ratio, weighted by voter reputation
- Reputation score computation: aggregate trace trust contributed by user
- Score decay: votes older than 90 days weight 50% less (simple time-decay factor)
- `GET /api/v1/users/{id}/reputation` endpoint

### Phase 5: MCP Server
**Build:** Python MCP server using FastMCP (from `mcp[cli]` package), tool definitions, transport configuration

**Rationale:** The MCP server is a protocol adapter. It has no business logic of its own.
It can only be built after the REST API exists because it calls the REST API for everything.
Use Streamable HTTP transport for the remote server (multiple concurrent agents connecting);
stdio transport for local dev/testing.

Components built:
- `search_traces(query: str, tags: list[str], limit: int) → list[Trace]` tool
- `contribute_trace(context: str, solution: str, tags: list[str]) → TraceId` tool
- `vote_trace(trace_id: str, vote: str, feedback: str) → VoteResult` tool
- `get_trace(trace_id: str) → Trace` tool
- FastMCP server with Streamable HTTP transport
- API key injection from MCP client config (not in tool params — security)

### Phase 6: Claude Code Skill
**Build:** CLAUDE.md skill file, slash commands, auto-query hook

**Rationale:** The skill is the final UX layer. It integrates with MCP (which must exist)
and provides the Claude Code-specific experience. Build last.

Components built:
- CLAUDE.md skill definition with tool descriptions
- `/ct-search [query]` slash command (explicit search)
- `/ct-contribute` slash command (structured contribution flow)
- `/ct-vote [trace_id] [up|down]` slash command
- Auto-query trigger: hook on session start, inject top 3 traces silently into context

---

## Patterns to Follow

### Pattern 1: Thin MCP Server, Fat FastAPI

The MCP server must contain zero business logic. Every tool handler is a REST API call.
This ensures the MCP server is swappable, that the API is independently testable, and
that non-MCP clients (web app, CLI, other agent platforms) can call the same endpoints.

```python
# CORRECT: MCP tool is a thin HTTP proxy
@mcp.tool()
async def search_traces(query: str, tags: list[str] = [], limit: int = 5) -> str:
    """Search CommonTrace for relevant traces matching your context."""
    resp = await http_client.get(
        f"{API_BASE}/api/v1/traces/search",
        params={"q": query, "tags": ",".join(tags), "limit": limit},
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    traces = resp.json()["traces"]
    return format_traces_for_context(traces)

# WRONG: MCP tool with business logic
@mcp.tool()
async def search_traces(query: str) -> str:
    embedding = await embed(query)            # NO — business logic in MCP layer
    results = await pgvector_search(embedding) # NO — direct DB in MCP layer
    return results
```

### Pattern 2: Async-First for Embedding Pipeline

Embedding generation (150-500ms per trace) must never block the HTTP response. Use ARQ
(AsyncRedisQueue) because it is native async Python and integrates cleanly with FastAPI's
async event loop. Celery works but requires synchronous workers or awkward async bridging.

```python
# FastAPI endpoint — returns immediately, queues background work
@router.post("/traces", status_code=202)
async def create_trace(trace_in: TraceCreate, db: AsyncSession = Depends(get_db)):
    trace = Trace(**trace_in.model_dump(), status="pending_embedding")
    db.add(trace)
    await db.commit()
    await arq_pool.enqueue_job("embed_trace", trace.id)  # fire and forget
    return {"trace_id": str(trace.id), "status": "pending_embedding"}

# ARQ worker — runs separately
async def embed_trace(ctx: dict, trace_id: UUID):
    async with get_db_session() as db:
        trace = await db.get(Trace, trace_id)
        embedding = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=f"{trace.context_text}\n\n{trace.solution_text}"
        )
        trace.embedding = embedding.data[0].embedding
        trace.status = "active"
        await db.commit()
```

### Pattern 3: Hybrid Search (Not Pure Vector)

Pure vector search misses exact tag/language filters. Pure SQL misses semantic similarity.
Hybrid approach: pgvector ANN for candidate retrieval, SQL for filtering, score for ranking.

```python
async def search_traces(query: str, tags: list[str], limit: int, db: AsyncSession):
    query_embedding = await get_embedding(query)

    # Step 1: ANN candidate fetch (top 50, wider than needed)
    # Step 2: Tag filter (SQL WHERE)
    # Step 3: Score re-ranking (Python, not SQL, for flexibility)
    stmt = (
        select(Trace)
        .where(Trace.status == "active")
        .where(Trace.tags.any(Tag.name.in_(tags)) if tags else True)
        .order_by(Trace.embedding.cosine_distance(query_embedding))
        .limit(50)  # fetch more than needed for re-ranking
    )
    candidates = (await db.execute(stmt)).scalars().all()

    # Re-rank: weighted blend
    results = sorted(candidates, key=lambda t: (
        0.6 * cosine_similarity(query_embedding, t.embedding) +
        0.3 * t.trust_score +
        0.1 * recency_score(t.created_at)
    ), reverse=True)

    return results[:limit]
```

### Pattern 4: API Key per Agent Session (not per user)

For freemium metering, API keys should be per-agent-installation, not per-human-user.
This enables per-agent rate limiting and usage tracking without requiring human auth
from the agent. The MCP client config holds the API key; tool call parameters never
contain it (avoids leaking keys into trace content or logs).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous Embedding on Write
**What:** Call embedding API inline during `POST /traces`, block until complete, return.
**Why bad:** Embedding API calls take 150-500ms under load. Under burst contribution,
request queues back up, timeouts spike, contributors see failures.
**Instead:** Return 202 Accepted immediately, queue embedding as background job.

### Anti-Pattern 2: Direct DB Access from MCP Server
**What:** MCP server imports SQLAlchemy models, opens DB connections, runs queries.
**Why bad:** Couples MCP server to DB schema. Prevents independent deployment. Makes
MCP server stateful and hard to scale. Breaks the layered architecture.
**Instead:** MCP server calls REST API only. All DB logic lives in FastAPI.

### Anti-Pattern 3: Separate Vector DB (Pinecone, Weaviate, Qdrant)
**What:** Separate vector database alongside PostgreSQL for embeddings.
**Why bad:** Two sources of truth for traces. Sync complexity is significant — a trace
exists in PG but embedding is in Pinecone; delete from one, orphan in the other.
Adds operational overhead (second database to manage, monitor, pay for).
**Instead:** pgvector extension on the same PostgreSQL. HNSW index gives good ANN
performance up to ~10M vectors. Only migrate to a dedicated vector DB if pgvector
becomes the proven bottleneck at scale.

### Anti-Pattern 4: Auto-Contributing Every Agent Action
**What:** Skill automatically contributes a trace for every completed task.
**Why bad:** Knowledge base floods with low-quality, duplicate, or trivial traces.
Reputation signal degrades. Search result quality degrades.
**Instead:** Contribution is always user/agent-confirmed (explicit intent). Auto-query
on task start is fine (read-only, no quality risk). Contribution requires explicit command.

### Anti-Pattern 5: Global Trust Score Without Context
**What:** Single numeric trust score, averaged across all votes from all contexts.
**Why bad:** "Works in Python 3.9" trace gets downvoted by Python 3.12 agent, score drops.
The trace was correct in its original context.
**Instead:** Store votes with contextual metadata (language version, framework version,
OS). Surface context in search results. Future scoring can be context-aware.
This is complex — start with simple global scores, structure data to enable context-aware
scoring later.

---

## Scalability Considerations

| Concern | At 1K DAA (daily active agents) | At 100K DAA | At 1M DAA |
|---------|----------------------------------|-------------|-----------|
| Search latency | Single PostgreSQL + pgvector, HNSW index. <50ms p99. Fine. | Add read replicas. pgvector HNSW handles ~1M vectors well. | Consider pgvector sharding or Qdrant/Weaviate migration. |
| Embedding throughput | Single ARQ worker, OpenAI API rate limits. Batch up to 100 traces/req. Fine. | Multiple workers, Redis cluster. Embed in batches of 100. | Self-hosted embedding model (e.g., text-embedding-3-small via vLLM) for cost control. |
| Write throughput | Single PostgreSQL primary. Fine up to ~5K writes/sec. | PgBouncer connection pooling. | Partition traces table by month. |
| Reputation computation | Compute on vote event (synchronous, fast). Fine. | Queue reputation recomputation as async job. | Batch reputation jobs, approximate scoring. |
| API rate limiting | Redis-backed sliding window per API key. | Same, Redis cluster for HA. | Same. |
| MCP server | Single process, Streamable HTTP transport, async. | Horizontal scale (stateless). | Same — stateless scales trivially. |

**Key insight:** pgvector with HNSW is adequate for the first 1-2 years at realistic trace
volumes (100K-1M traces). Separation of concerns (thin MCP server, stateless workers)
means horizontal scaling is straightforward. Do not over-engineer for 1M DAA on day one.

---

## Concrete Directory Structure

```
commontrace/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── trace.py
│   │   │   ├── user.py
│   │   │   ├── vote.py
│   │   │   └── tag.py
│   │   ├── routers/            # FastAPI APIRouter modules
│   │   │   ├── traces.py       # CRUD + search
│   │   │   ├── votes.py
│   │   │   └── users.py
│   │   ├── services/           # Business logic
│   │   │   ├── search.py       # Hybrid search logic
│   │   │   ├── reputation.py   # Score computation
│   │   │   └── embedding.py    # Embedding client wrapper
│   │   ├── workers/            # ARQ async workers
│   │   │   └── embed_worker.py
│   │   └── dependencies.py     # FastAPI DI: db session, auth
│   ├── migrations/             # Alembic migrations
│   └── tests/
│
├── mcp-server/                 # MCP server (Python, FastMCP)
│   ├── server.py               # Tool definitions, FastMCP instance
│   ├── client.py               # HTTP client to FastAPI
│   └── formatters.py           # MCP content formatting
│
├── skill/                      # Claude Code skill
│   ├── CLAUDE.md               # Skill definition (loaded by Claude Code)
│   └── commands/               # Slash command definitions
│       ├── ct-search.md
│       ├── ct-contribute.md
│       └── ct-vote.md
│
└── docker-compose.yml          # PostgreSQL, Redis, backend, worker
```

---

## Sources

- MCP Architecture (HIGH confidence — official spec, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/architecture
- MCP Tools protocol (HIGH confidence — official spec, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/tools
- MCP Transports — Streamable HTTP and stdio (HIGH confidence — official spec, verified 2026-02-20): https://modelcontextprotocol.io/docs/concepts/transports
- MCP Server build guide — FastMCP Python pattern (HIGH confidence — official doc, verified 2026-02-20): https://modelcontextprotocol.io/docs/develop/build-server
- FastAPI modular architecture (HIGH confidence — official doc, verified 2026-02-20): https://fastapi.tiangolo.com/tutorial/bigger-applications/
- pgvector HNSW index capabilities (MEDIUM confidence — official GitHub README, training data corroborated): https://github.com/pgvector/pgvector
- OpenAI text-embedding-3-small model (MEDIUM confidence — training data, release announcement verified): dimensions=1536, strong multilingual + code performance
- ARQ async task queue vs Celery for async Python (MEDIUM confidence — community consensus, training data)
