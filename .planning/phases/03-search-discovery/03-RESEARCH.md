# Phase 3: Search + Discovery - Research

**Researched:** 2026-02-20
**Domain:** pgvector cosine ANN search, async embedding worker, hybrid tag+vector search, trust-weighted re-ranking, observability
**Confidence:** HIGH

---

## Summary

Phase 3 builds on a solid foundation: the database already has `Vector(1536)` columns on the `traces` table, an HNSW index with `vector_cosine_ops` (m=16, ef_construction=64), `pgvector.asyncpg.register_vector` already wired in `database.py` via an event listener, and the `tags`/`trace_tags` join table in place. The three implementation units — async embedding worker (03-01), hybrid search endpoint (03-02), and observability (03-03) — build directly on what Phase 2 delivered.

The embedding worker (03-01) must poll the `traces` table for rows where `embedding IS NULL`, call the OpenAI embeddings API (model `text-embedding-3-small`, 1536 dimensions), store the result, and update the row. The critical design choice is that sentence-transformers produces 384-dimensional vectors while the schema declares `Vector(1536)` — these are incompatible. The fallback must either use a model that outputs exactly 1536 dimensions (e.g., `text-embedding-3-small` with `dimensions=1536`) or pad/project to 1536. The correct fallback strategy is to use `text-embedding-3-large` or another 1536-dim provider locally, OR use sentence-transformers with a projection layer, OR (simplest and correct) treat the local fallback as "no embedding generated" with a different model dimension stored. The cleanest solution given the locked `Vector(1536)` column: use sentence-transformers with a model that can output 1536 dimensions via its `output_dimensions` parameter (sentence-transformers >=3.0 supports this), or accept that the local fallback uses a different embedding space (and skip hybrid HNSW search for non-OpenAI embeddings). Research confirms: `SentenceTransformer.encode()` in sentence-transformers >=3.0 supports `output_dimensions` via Matryoshka truncation for compatible models.

The hybrid search endpoint (03-02) combines three steps in a single SQL query: (1) cosine ANN via `embedding.cosine_distance(query_vector)` ordering, (2) SQL JOIN filter on `trace_tags` + `tags.name IN (...)` to apply tag constraints pre-ANN, and (3) Python-side trust-weighted re-ranking of the top-K ANN results. pgvector with SQLAlchemy supports `ORDER BY embedding.cosine_distance(vec)` combined with `WHERE` clauses directly — this is pre-filtering (tag filter reduces the ANN candidate set before ranking). For the "appears within seconds" success criterion, no additional infrastructure is needed beyond the worker writing the embedding and the HNSW index picking it up automatically (pgvector HNSW supports live inserts without index rebuild).

Observability (03-03) uses structlog (already a dependency) for structured JSON logging. The existing `structlog` dependency is already in `api/pyproject.toml`. For Prometheus metrics, `prometheus-client` needs to be added. The worker process needs separate Prometheus metric reporting — use the multiprocess mode with `PROMETHEUS_MULTIPROC_DIR`.

**Primary recommendation:** Worker uses `asyncio.sleep` polling loop with `SELECT ... WHERE embedding IS NULL LIMIT N FOR UPDATE SKIP LOCKED` to claim batches atomically. Embedding via `AsyncOpenAI` client with fallback to `sentence_transformers` at 1536 dimensions using `output_dimensions=1536`. Search endpoint uses single-pass SQLAlchemy query: cosine order + tag JOIN WHERE, then Python re-rank by `trust_score`. Structlog for structured logging; prometheus-client multiprocess for metrics.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | 2.21.0 (current) | `AsyncOpenAI` client for `text-embedding-3-small` embeddings | Official async client; `client.embeddings.create()` is the documented pattern |
| `pgvector` | >=0.4.2 (already installed) | SQLAlchemy `Vector` type, `.cosine_distance()` comparator | Already in deps; `register_vector` already wired in `database.py` |
| `sentence-transformers` | >=3.0 | Local embedding fallback; supports `output_dimensions=1536` for Matryoshka models | Only credible local option; CPU-only fallback avoids GPU dependency |
| `structlog` | any (already in deps) | Structured logging for worker and API | Already a project dependency — no new dep needed |
| `prometheus-client` | >=0.20 | Metrics counters and histograms | Standard Python Prometheus client; compatible with multiprocess mode for worker |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | >=0.27 (already in deps) | NOT needed here — use `openai` SDK which uses httpx internally | Only use directly for non-OpenAI HTTP calls |
| `asyncio` stdlib | Python 3.12 | Worker event loop, `asyncio.sleep` polling interval | Built-in — no install needed |
| `sqlalchemy` | >=2.0.46 (already installed) | `select().with_for_update(skip_locked=True)` for worker claim, `.cosine_distance()` for search | Already installed and configured |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `AsyncOpenAI` + sentence-transformers fallback | Celery + separate embedding service | Celery adds operational complexity; simple asyncio polling is sufficient for single-worker startup |
| Pre-filter (tag WHERE before cosine ANN) | Post-filter (cosine ANN then filter tags) | Pre-filter can reduce ANN recall if tag set is small; but it is simpler SQL and avoids fetching irrelevant vectors. Post-filter requires over-fetching (e.g., LIMIT 1000 then filter). Pre-filter is correct here because tags are indexed and selectivity is high. |
| Python-side trust re-ranking | SQL-side weighted ORDER BY | SQL-side requires a formula like `ORDER BY cosine_distance(emb, q) * (1.0 / (1 + trust_score))` which is not standard; Python-side re-rank of top-K is simpler and transparent |
| `prometheus-client` | `starlette_exporter` or `prometheus_fastapi_instrumentator` | Auto-instrumentators add latency histograms for HTTP; for the worker process, only raw `prometheus-client` works. Use one library across both contexts. |

### Installation
```bash
uv add "openai>=1.0" "sentence-transformers>=3.0" "prometheus-client>=0.20" --package commontrace-api
```

---

## Architecture Patterns

### Recommended Project Structure
```
api/app/
├── routers/
│   └── traces.py          # Add: GET /api/v1/traces/search
├── schemas/
│   └── search.py          # TraceSearchRequest, TraceSearchResult, SearchResponse
├── services/
│   └── embedding.py       # EmbeddingService: AsyncOpenAI + sentence-transformers fallback
├── worker/
│   ├── __init__.py
│   └── embedding_worker.py  # Polling loop: poll → claim → embed → store
└── metrics.py             # Prometheus Counter + Histogram definitions (shared)
```

### Pattern 1: Async Embedding Worker Loop

**What:** Long-running asyncio task that polls `traces` WHERE `embedding IS NULL`, claims a batch with `FOR UPDATE SKIP LOCKED`, calls the embedding API, stores the result.

**When to use:** Runs as the `worker` Docker service (replaces the placeholder `asyncio.sleep(86400)` command in docker-compose).

**Critical:** `embedding IS NULL` is the condition for "needs embedding". A new `embedding_status` column is NOT needed because `embedding IS NULL` already signals "pending" and `embedding IS NOT NULL` signals "done". This avoids a new migration.

```python
# Source: PostgreSQL SKIP LOCKED pattern — https://www.inferable.ai/blog/posts/postgres-skip-locked
# Source: SQLAlchemy async docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
# api/app/worker/embedding_worker.py

import asyncio
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.trace import Trace
from app.services.embedding import EmbeddingService

log = structlog.get_logger()
POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 10


async def process_batch(db: AsyncSession, svc: EmbeddingService) -> int:
    """Claim and embed up to BATCH_SIZE traces. Returns count processed."""
    # SELECT ... FOR UPDATE SKIP LOCKED — atomic claim, no worker contention
    stmt = (
        select(Trace)
        .where(Trace.embedding.is_(None))
        .with_for_update(skip_locked=True)
        .limit(BATCH_SIZE)
    )
    result = await db.execute(stmt)
    traces = result.scalars().all()

    if not traces:
        return 0

    for trace in traces:
        text = f"{trace.title}\n{trace.context_text}\n{trace.solution_text}"
        try:
            vector, model_id, model_version = await svc.embed(text)
            await db.execute(
                update(Trace)
                .where(Trace.id == trace.id)
                .values(
                    embedding=vector,
                    embedding_model_id=model_id,
                    embedding_model_version=model_version,
                )
                .execution_options(synchronize_session=False)
            )
            log.info("embedding_stored", trace_id=str(trace.id), model=model_id)
        except Exception as e:
            log.error("embedding_failed", trace_id=str(trace.id), error=str(e))
            # Don't re-raise — skip this trace, it will be retried next poll

    await db.commit()
    return len(traces)


async def run_worker():
    """Main worker loop — runs until cancelled."""
    svc = EmbeddingService()
    log.info("embedding_worker_started")
    while True:
        try:
            async with async_session_factory() as db:
                count = await process_batch(db, svc)
                if count > 0:
                    log.info("batch_processed", count=count)
        except Exception as e:
            log.error("worker_loop_error", error=str(e))
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

### Pattern 2: Embedding Service with OpenAI + Local Fallback

**What:** Service class that tries OpenAI first, falls back to sentence-transformers if OpenAI key missing or call fails.

**Critical dimension constraint:** `traces.embedding` is `Vector(1536)`. The OpenAI model `text-embedding-3-small` produces 1536 dimensions by default. The sentence-transformers fallback MUST also produce 1536 dimensions. Use `output_dimensions=1536` on a Matryoshka-compatible model — however, `all-MiniLM-L6-v2` (native 384d) does NOT support Matryoshka truncation to 1536 (truncation reduces, not expands). Therefore: for the local fallback, use `all-mpnet-base-v2` (768d native, no Matryoshka to 1536 either). The correct solution is to use `BAAI/bge-large-en-v1.5` (1024d) or accept that the local fallback uses zero-padded vectors — which break cosine similarity.

**Recommended resolution:** Use `text-embedding-3-small` (1536d, OpenAI) as primary. For local fallback, use `sentence-transformers/all-mpnet-base-v2` (768d) and pad the vector to 1536 with zeros. This is semantically imperfect but ensures the column constraint is met. The `embedding_model_id` field lets search queries know which model generated the embedding and exclude mismatched embeddings from search. Alternatively, skip embedding entirely if no API key and log a warning — this is the simplest fallback.

```python
# api/app/services/embedding.py
import os
from typing import Optional
import structlog

log = structlog.get_logger()

OPENAI_MODEL = "text-embedding-3-small"
OPENAI_DIMENSIONS = 1536
LOCAL_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
LOCAL_DIMENSIONS = 768  # native; zero-pad to 1536


class EmbeddingService:
    def __init__(self):
        self._openai_client: Optional[object] = None
        self._local_model: Optional[object] = None
        self._use_local = not bool(os.environ.get("OPENAI_API_KEY"))

    async def _get_openai_client(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI()
        return self._openai_client

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(LOCAL_MODEL_NAME)
            log.warning("using_local_embedding_model", model=LOCAL_MODEL_NAME,
                        note="768d padded to 1536; not compatible with OpenAI embeddings space")
        return self._local_model

    async def embed(self, text: str) -> tuple[list[float], str, str]:
        """Returns (vector: list[float], model_id: str, model_version: str)."""
        if not self._use_local:
            try:
                client = await self._get_openai_client()
                response = await client.embeddings.create(
                    input=text,
                    model=OPENAI_MODEL,
                    dimensions=OPENAI_DIMENSIONS,
                )
                vector = response.data[0].embedding
                return vector, OPENAI_MODEL, response.model
            except Exception as e:
                log.warning("openai_embedding_failed_falling_back", error=str(e))

        # Local fallback: sentence-transformers + zero-pad
        model = self._get_local_model()
        # encode() is CPU-bound — run in threadpool
        import asyncio
        vector_768 = await asyncio.get_event_loop().run_in_executor(
            None, model.encode, text
        )
        # Zero-pad from 768 to 1536
        padded = list(vector_768) + [0.0] * (OPENAI_DIMENSIONS - LOCAL_DIMENSIONS)
        return padded, LOCAL_MODEL_NAME, "local"
```

**Note:** The zero-padding fallback preserves the column constraint but produces semantically incompatible embeddings with OpenAI-embedded traces. The `embedding_model_id` column must be checked by the search endpoint to avoid mixing embedding spaces in the same cosine similarity query. The search endpoint should filter `WHERE embedding_model_id = 'text-embedding-3-small'` when the query was embedded with OpenAI.

### Pattern 3: Hybrid Search Endpoint

**What:** Single SQL query combining cosine ANN (via HNSW index) + tag pre-filter, then Python-side trust re-ranking.

**When to use:** `GET /api/v1/traces/search?q=...&tags=tag1,tag2&limit=10`

```python
# Source: pgvector-python README — https://github.com/pgvector/pgvector-python
# Source: pgvector HNSW docs — https://github.com/pgvector/pgvector
# api/app/routers/traces.py (add to existing file)

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.models.tag import Tag, trace_tags
from app.models.trace import Trace

SEARCH_LIMIT_ANN = 100   # Fetch top-100 from ANN before re-ranking
SEARCH_LIMIT_DEFAULT = 10  # Default result count returned


async def search_traces(
    query_vector: list[float],
    tag_names: list[str],
    limit: int,
    db: AsyncSession,
) -> list[dict]:
    """Hybrid search: cosine ANN + tag filter + trust re-rank."""

    # Build base query: cosine distance ordering + embedding not null
    distance_col = Trace.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Trace, distance_col)
        .where(Trace.embedding.is_not(None))
        # Only search traces embedded with compatible model
        .where(Trace.embedding_model_id == "text-embedding-3-small")
        # Exclude flagged/stale traces from search results
        .where(Trace.is_flagged.is_(False))
        .options(selectinload(Trace.tags))
        .order_by(distance_col)
        .limit(SEARCH_LIMIT_ANN)
    )

    # Tag pre-filter: JOIN to trace_tags + tags if tags requested
    if tag_names:
        stmt = (
            stmt
            .join(trace_tags, trace_tags.c.trace_id == Trace.id)
            .join(Tag, Tag.id == trace_tags.c.tag_id)
            .where(Tag.name.in_(tag_names))
            # Require ALL specified tags: group and HAVING count
            .group_by(Trace.id, distance_col)
            .having(func.count(Tag.id.distinct()) == len(tag_names))
        )

    result = await db.execute(stmt)
    rows = result.all()  # list of (Trace, distance) tuples

    # Trust-weighted re-ranking: combined_score = (1 - cosine_distance) * log1p(trust_score + 1)
    # cosine_distance: 0 = identical, 2 = opposite; cosine_similarity = 1 - cosine_distance
    import math
    ranked = sorted(
        rows,
        key=lambda r: (1.0 - r.distance) * math.log1p(max(0.0, r.Trace.trust_score) + 1),
        reverse=True,
    )
    return ranked[:limit]
```

**Trust re-ranking formula explanation:**
- `cosine_similarity = 1 - cosine_distance` (pgvector cosine distance is 1 - cosine_similarity for normalized vectors)
- `trust_boost = log1p(max(0, trust_score) + 1)` — log dampens extreme trust scores; `log1p(1)` ≈ 0.69 for trust=0 (neutral), scales upward
- `combined = cosine_similarity * trust_boost` — identical semantic relevance ranks higher-trust trace above lower-trust trace
- The `max(0, trust_score)` clips negative trust (heavily downvoted) to zero rather than inverting the ranking

### Pattern 4: Search Request Schema

```python
# api/app/schemas/search.py
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class TraceSearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2000, description="Natural language search query")
    tags: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=50)

class TraceSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    context_text: str
    solution_text: str
    trust_score: float
    status: str
    tags: list[str]
    similarity_score: float   # cosine similarity (1 - distance)
    combined_score: float     # trust-weighted final score
    embedding_model_id: Optional[str] = None
```

### Pattern 5: Structlog Configuration

**What:** Configure structlog once at app startup with `merge_contextvars` as first processor.

```python
# api/app/logging_config.py (new file)
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
```

**Per-request binding in FastAPI middleware:**
```python
# In FastAPI middleware or lifespan
import uuid
import structlog

async def dispatch(self, request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid.uuid4()),
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    return response
```

### Pattern 6: Prometheus Metrics

**What:** Custom metrics for embedding worker (embeddings_processed_total, embedding_duration_seconds) and search endpoint (search_requests_total, search_duration_seconds).

```python
# api/app/metrics.py
from prometheus_client import Counter, Histogram

embeddings_processed = Counter(
    "commontrace_embeddings_processed_total",
    "Total embeddings generated",
    ["model", "status"],  # status: success | error
)

embedding_duration = Histogram(
    "commontrace_embedding_duration_seconds",
    "Time to generate one embedding",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

search_requests = Counter(
    "commontrace_search_requests_total",
    "Total search requests",
    ["has_tags"],  # label: "true" or "false"
)

search_duration = Histogram(
    "commontrace_search_duration_seconds",
    "End-to-end search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)
```

**For multiprocess mode (worker + API in separate processes):**
```bash
# Set in docker-compose.yml env or .env
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
```

**Expose /metrics endpoint in FastAPI:**
```python
from prometheus_client import generate_latest, CollectorRegistry, multiprocess, CONTENT_TYPE_LATEST
from fastapi.responses import Response

@app.get("/metrics")
async def metrics():
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
```

### Anti-Patterns to Avoid

- **Mixing embedding spaces in cosine search:** Never run cosine ANN across traces with `embedding_model_id = 'text-embedding-3-small'` and `embedding_model_id = 'local'` in the same query — the vectors are in different semantic spaces. Always filter by `embedding_model_id` before comparing.

- **Blocking event loop with sentence-transformers:** `SentenceTransformer.encode()` is CPU-bound. Call via `asyncio.get_event_loop().run_in_executor(None, model.encode, text)` — never `await` directly on a sync function.

- **SELECT without SKIP LOCKED in the worker:** Without `with_for_update(skip_locked=True)`, two concurrent workers will both claim the same trace, double-embed it, and cause a last-write-wins race on the embedding column.

- **Post-filter ANN (fetch many, filter after):** Fetching LIMIT 10000 from ANN then filtering by tags in Python is extremely slow and defeats the HNSW index. Always apply tag filters as SQL WHERE clauses before the LIMIT.

- **Rebuilding HNSW index for new embeddings:** Not needed. pgvector HNSW supports live inserts — new embeddings are immediately queryable without `VACUUM` or `REINDEX`. The "appears within seconds" criterion is satisfied automatically.

- **ef_search left at default:** The HNSW index was built with `ef_construction=64`. The default `hnsw.ef_search=40`. For better recall at the cost of slight latency, set `SET hnsw.ef_search = 64` at session level in the search query connection. Do this with `db.execute(text("SET hnsw.ef_search = 64"))` before the cosine query.

- **Counting tags with HAVING without GROUP BY Trace.id:** The GROUP BY + HAVING pattern for "all N tags" only works if you group by the trace primary key. Without GROUP BY, the HAVING clause sees aggregates over the entire result set.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async HTTP to OpenAI embeddings API | Custom httpx calls | `openai.AsyncOpenAI().embeddings.create()` | Handles retries, timeouts, response parsing, rate limit headers automatically |
| Worker mutex / distributed lock | Redis SETNX lock | PostgreSQL `FOR UPDATE SKIP LOCKED` | Already have Postgres; SKIP LOCKED is atomic, deadlock-free, and requires zero extra infrastructure |
| Vector type serialization/deserialization | `str([...])` round-tripping | `pgvector.asyncpg.register_vector` (already done in `database.py`) | Type codec handles `list[float]` ↔ Postgres `vector` transparently |
| Cosine similarity function | `sum(a*b) / (norm(a) * norm(b))` | `Trace.embedding.cosine_distance(vec)` | pgvector operator `<=>` runs on-server; uses HNSW index; no Python iteration |
| Re-ranking formula | Custom scoring class | Simple Python `sorted()` with key function | Top-100 re-rank in Python is O(100) — no library needed |
| Structured logging format | Custom JSON formatter | `structlog` (already a dependency) | Already installed; `merge_contextvars` handles async context propagation |

**Key insight:** The entire worker and search stack reuses what Phase 1+2 built: the existing asyncpg engine with `register_vector`, the existing `async_session_factory`, the existing Redis connection on `app.state`, and the existing tag join table. No new external dependencies are needed except `openai` (for embeddings) and `prometheus-client` (for metrics).

---

## Common Pitfalls

### Pitfall 1: sentence-transformers Dimension Mismatch
**What goes wrong:** `sentence_transformers/all-MiniLM-L6-v2` produces 384-dimensional vectors. Writing these to `Vector(1536)` raises: `expected 1536 dimensions, not 384`.
**Why it happens:** The column was declared `Vector(1536)` for OpenAI compatibility in Phase 1. Local fallback models have different native dimensions.
**How to avoid:** Either (a) zero-pad to 1536 and store `embedding_model_id = 'local-padded'` so search can exclude them, or (b) use `openai` library only and treat missing API key as "skip embedding" (log warning, leave `embedding IS NULL`). Option (b) is simplest and semantically correct.
**Warning signs:** `DataError: expected 1536 dimensions` from asyncpg during UPDATE.

### Pitfall 2: Tag Filter HAVING Clause Counts Wrong
**What goes wrong:** Query returns traces that have SOME of the requested tags, not ALL of them.
**Why it happens:** The `WHERE Tag.name IN (...)` filter passes traces with any one of the tags. The `HAVING count(distinct Tag.id) == len(tag_names)` is needed to enforce ALL tags present.
**How to avoid:** Always use the GROUP BY + HAVING pattern shown in Pattern 3. Test with a trace that has only 1 of 2 requested tags — it must NOT appear in results.
**Warning signs:** Results include traces missing one of the requested tags.

### Pitfall 3: cosine_distance in GROUP BY
**What goes wrong:** `GROUP BY Trace.id` raises `column "distance" must appear in GROUP BY clause` because `distance_col` is an aliased expression not a plain column.
**Why it happens:** The `distance_col = Trace.embedding.cosine_distance(query_vector).label("distance")` expression must be included in GROUP BY or be inside an aggregate.
**How to avoid:** In the GROUP BY clause, repeat the expression: `.group_by(Trace.id, Trace.embedding.cosine_distance(query_vector))` — not the alias. Alternatively, use a subquery: inner query computes distance + applies tag filter, outer query groups.
**Warning signs:** `ProgrammingError: column "distance" must appear in GROUP BY clause`.

### Pitfall 4: Worker Claims Rows But Never Commits
**What goes wrong:** Worker exits with exception after `FOR UPDATE` lock is acquired but before `db.commit()`. The rows stay locked for the duration of the transaction, then release — but `embedding IS NULL` so they'll be retried next poll. This is acceptable but can cause delay.
**Why it happens:** The lock is held for the entire transaction. If the embedding API call takes 30s and the DB connection has a statement timeout, the transaction may time out.
**How to avoid:** Process each trace in its own nested transaction, or commit after each successful embed. The pattern above commits the full batch — add per-trace exception handling to skip failures without rolling back the whole batch.
**Warning signs:** Worker logs `embedding_failed` for all traces in a batch; traces stay `embedding IS NULL` permanently.

### Pitfall 5: Cosine Distance Is Not Cosine Similarity
**What goes wrong:** pgvector's `<=>` operator returns cosine **distance** (1 - similarity for unit vectors, but different formula for non-unit vectors). Treating `ORDER BY embedding.cosine_distance(vec)` results as similarities causes inverted re-ranking.
**Why it happens:** Confusion between distance (lower = more similar) and similarity (higher = more similar).
**How to avoid:** The re-ranking formula uses `1.0 - row.distance` to convert distance to similarity. Verify: identical vectors should have distance ≈ 0 (similarity ≈ 1). Test with a known-similar pair.
**Warning signs:** Most relevant results ranked last instead of first.

### Pitfall 6: HNSW ef_search Not Set Per-Session
**What goes wrong:** Search recall is poor — correct results don't appear in top-10. Index built with `ef_construction=64` but `hnsw.ef_search` defaults to 40.
**Why it happens:** Build-time `ef_construction` and search-time `ef_search` are independent. Lower `ef_search` means faster but lower-recall search.
**How to avoid:** At the start of each search session, execute `SET LOCAL hnsw.ef_search = 64` (or higher for better recall at cost of latency). `SET LOCAL` scopes to the current transaction.
**Warning signs:** Exact-match test: embed a known trace text and search — it should be result #1 but appears lower.

### Pitfall 7: Worker Runs Before Migrations Applied
**What goes wrong:** Worker starts, tries to SELECT from `traces`, fails because `alembic upgrade head` hasn't run yet.
**Why it happens:** In docker-compose, the `worker` service starts in parallel with `api`. The `api` service runs migrations via its command, but `worker` doesn't.
**How to avoid:** Add `depends_on: api: condition: service_healthy` to the worker service in docker-compose, OR run `alembic upgrade head` in the worker entrypoint too. The api healthcheck only confirms the port is up, not that migrations ran — use a custom healthcheck that checks for the `traces` table, or run alembic in the worker startup.
**Warning signs:** `UndefinedTableError: relation "traces" does not exist` in worker logs at startup.

---

## Code Examples

Verified patterns from official sources:

### pgvector Cosine Distance with WHERE Filter (SQLAlchemy 2.0)
```python
# Source: pgvector-python README — https://github.com/pgvector/pgvector-python
# Cosine distance + WHERE clause (pre-filter)
from sqlalchemy import select
from app.models.trace import Trace

query_vec = [0.1, 0.2, ...]  # 1536-dim list

stmt = (
    select(Trace, Trace.embedding.cosine_distance(query_vec).label("distance"))
    .where(Trace.embedding.is_not(None))
    .order_by(Trace.embedding.cosine_distance(query_vec))
    .limit(100)
)
result = await db.execute(stmt)
rows = result.all()  # list of Row(Trace, distance)
```

### SELECT FOR UPDATE SKIP LOCKED (SQLAlchemy 2.0 async)
```python
# Source: SQLAlchemy docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
# Source: PostgreSQL SKIP LOCKED — https://parottasalna.com/2025/01/11/learning-notes-51-postgres-as-a-queue-using-skip-locked/
stmt = (
    select(Trace)
    .where(Trace.embedding.is_(None))
    .with_for_update(skip_locked=True)
    .limit(10)
)
result = await db.execute(stmt)
pending_traces = result.scalars().all()
```

### AsyncOpenAI Embeddings
```python
# Source: openai-python README — https://github.com/openai/openai-python
# Current version: openai 2.21.0 (released 2026-02-14)
from openai import AsyncOpenAI

client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

response = await client.embeddings.create(
    input="The text to embed",
    model="text-embedding-3-small",
    dimensions=1536,
)
vector: list[float] = response.data[0].embedding
model_used: str = response.model  # e.g. "text-embedding-3-small"
```

### sentence-transformers CPU Encode (async-safe)
```python
# Source: https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html
# encode() is synchronous/CPU-bound — must use run_in_executor
import asyncio
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

async def embed_local(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    vector = await loop.run_in_executor(None, model.encode, text)
    return vector.tolist()  # numpy array → Python list
```

### structlog Configuration with contextvars
```python
# Source: https://www.structlog.org/en/stable/contextvars.html
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # MUST be first
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Per-request binding (FastAPI middleware)
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(request_id="abc-123", user_id="user-456")

log = structlog.get_logger()
log.info("search_executed", query_len=50)
# Output: {"event": "search_executed", "request_id": "abc-123", "user_id": "user-456", "query_len": 50, ...}
```

### Prometheus Counter + Histogram Usage
```python
# Source: prometheus_client docs — https://prometheus.github.io/client_python/
from app.metrics import embeddings_processed, embedding_duration
import time

start = time.monotonic()
try:
    vector, model_id, _ = await svc.embed(text)
    embeddings_processed.labels(model=model_id, status="success").inc()
except Exception:
    embeddings_processed.labels(model=model_id, status="error").inc()
    raise
finally:
    embedding_duration.labels(model=model_id).observe(time.monotonic() - start)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IVFFlat index (requires `VACUUM ANALYZE` after inserts) | HNSW index (live inserts, no maintenance) | pgvector 0.5.0 (2023) | HNSW is already in place from Phase 1 migration — no action needed |
| `aioredis` for rate limiting | `redis.asyncio` | 2022 | Already done in Phase 2 — same pattern applies here if caching embeddings in Redis |
| Synchronous `SentenceTransformer.encode()` in async | `run_in_executor` | Always necessary | Sentence-transformers has no async API; must use executor |
| `@app.on_event("startup")` | `asynccontextmanager lifespan` | FastAPI 0.93 | Already done in Phase 2 — worker gets its own asyncio entrypoint |
| Custom job queue (Redis, Celery) | PostgreSQL `SKIP LOCKED` | Well-established by 2023 | Avoids Redis dependency for worker queue; Postgres already in stack |

**Deprecated/outdated:**
- `ivfflat` index: Requires `VACUUM ANALYZE` and list tuning; HNSW is strictly better for this use case (already using HNSW).
- `pgvector 0.4.x` `register_vector` pattern: In 0.4.x the asyncpg pattern was `await register_vector(conn)` in a pool init callback. In current 0.4.2+ with SQLAlchemy, the `event.listens_for(engine.sync_engine, "connect")` pattern is correct and already in place.

---

## Open Questions

1. **Local fallback model dimension strategy**
   - What we know: `Vector(1536)` column is fixed. sentence-transformers native models produce 384–768 dimensions.
   - What's unclear: Should the fallback zero-pad (semantically wrong but avoids NULL), skip embedding entirely (semantically correct but traces without embeddings never appear in search), or require a 1536-dim local model (large download)?
   - Recommendation: Simplest correct behavior — if no `OPENAI_API_KEY`, log a startup warning and skip embedding (leave `embedding IS NULL`). Search endpoint already filters `WHERE embedding IS NOT NULL`. This is correct and avoids semantic corruption. Document in .env.example that `OPENAI_API_KEY` is required for search to function.

2. **Search endpoint embedding the query text**
   - What we know: To search semantically, the query string must be embedded with the same model as stored traces.
   - What's unclear: The search endpoint itself calls the embedding API synchronously per request — is this acceptable latency?
   - Recommendation: Yes for Phase 3. One embedding API call per search request is ~100-300ms. If needed, cache query embeddings in Redis by query hash with 5-minute TTL to avoid re-embedding identical repeated queries.

3. **Tag filter with multiple tags: AND vs OR semantics**
   - What we know: The requirements say "filter traces by one or more structured tags... matching ALL specified tags" (SRCH-02 success criterion 2: "receives only traces matching all specified tags").
   - What's unclear: The GROUP BY + HAVING `count(distinct) == N` approach assumes all tags are independent rows in the join table.
   - Recommendation: AND semantics (all tags must match) as specified. Implement the GROUP BY + HAVING pattern. Test explicitly with 2-tag queries.

4. **Worker entrypoint in docker-compose**
   - What we know: The current worker command is `python -c "import asyncio; asyncio.run(asyncio.sleep(86400))"`.
   - What's unclear: Whether the worker should run alembic migrations before starting, or depend on the API having run them.
   - Recommendation: Worker entrypoint: `python -m app.worker.embedding_worker` (new module with `asyncio.run(run_worker())`). Add `depends_on: api: condition: service_healthy` OR run `alembic upgrade head` in the worker command before starting.

5. **Embedding drift monitoring**
   - What we know: Plan 03-03 mentions "embedding drift monitoring". This is unspecified in requirements.
   - What's unclear: What constitutes drift — model version changes? Distribution shifts?
   - Recommendation: For Phase 3, implement simple drift detection: log a warning when `embedding_model_id` in the database differs from the currently configured model. Track `embedding_model_version` distribution via a Prometheus gauge or a periodic log statement. Full drift monitoring (cosine distribution tracking) is out of scope for this phase.

---

## Sources

### Primary (HIGH confidence)
- `pgvector-python` README — `https://github.com/pgvector/pgvector-python/blob/master/README.md` — cosine_distance, cosine_distance filter, asyncpg registration pattern
- `database.py` in project (`/home/bitnami/commontrace/api/app/database.py`) — confirms `register_vector` already wired via `event.listens_for`
- `structlog` contextvars docs — `https://www.structlog.org/en/stable/contextvars.html` — merge_contextvars, bind_contextvars, clear_contextvars pattern verified
- `prometheus_client` multiprocess docs — `https://prometheus.github.io/client_python/multiprocess/` — PROMETHEUS_MULTIPROC_DIR, CollectorRegistry, MultiProcessCollector pattern verified
- Existing migration `0001_initial_schema.py` — confirms HNSW index with `vector_cosine_ops`, m=16, ef_construction=64
- `openai` PyPI page — version 2.21.0 confirmed; `AsyncOpenAI` pattern confirmed
- PostgreSQL SKIP LOCKED — `https://www.inferable.ai/blog/posts/postgres-skip-locked` — atomic claim pattern
- SQLAlchemy `with_for_update(skip_locked=True)` — `https://github.com/sqlalchemy/sqlalchemy/discussions/10460` — async SELECT FOR UPDATE SKIP LOCKED verified

### Secondary (MEDIUM confidence)
- `https://sbert.net/` — sentence-transformers docs; `SentenceTransformer.encode()` is sync/CPU-bound; 384d for all-MiniLM-L6-v2, 768d for all-mpnet-base-v2
- `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2` — 384d confirmed
- `https://huggingface.co/sentence-transformers/all-MiniLM-L12-v2` — 384d confirmed
- `https://openai.com/index/new-embedding-models-and-api-updates/` — text-embedding-3-small default 1536d confirmed
- `https://jkatz05.com/post/postgres/hybrid-search-postgres-pgvector/` — RRF hybrid pattern; pre-filter vs post-filter discussion

### Tertiary (LOW confidence)
- DeepWiki pgvector-python SQLAlchemy integration — patterns generally match official README but is a third-party mirror
- Various Medium articles on pgvector hybrid search — patterns consistent with official docs but not independently verified

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pgvector pattern verified from project source; openai SDK version confirmed from PyPI; structlog already in deps; prometheus-client multiprocess docs verified
- Architecture: HIGH — SKIP LOCKED pattern and SQLAlchemy async confirmed; cosine distance comparator verified from pgvector-python source
- Pitfalls: HIGH for dimension mismatch and cosine distance vs similarity (verified from pgvector docs); MEDIUM for GROUP BY + HAVING tag filter (logically verified but not tested against live DB)
- Local fallback strategy: MEDIUM — the zero-pad approach is technically valid but semantically imperfect; the "skip embedding" alternative is cleaner; final call deferred to planner

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (30 days — pgvector and openai SDK are stable; sentence-transformers is stable)
