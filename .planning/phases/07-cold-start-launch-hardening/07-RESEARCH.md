# Phase 7: Cold Start + Launch Hardening - Research

**Researched:** 2026-02-20
**Domain:** Seed data curation, pgvector HNSW capacity testing, rate limiter burst validation
**Confidence:** MEDIUM — pgvector latency benchmarks vary by hardware; seed data quality is inherently subjective

## Summary

Phase 7 consists of two logically distinct tracks that must both complete before public launch. Track 07-01 is a content problem: creating 200-500 high-quality, hand-curated seed traces that cover common Claude Code tasks, importing them into production with a dedicated pipeline that bypasses the normal pending/validation flow (using the `is_seed` flag already in the schema), and triggering the embedding worker to generate vectors for all of them. Track 07-02 is a systems validation problem: proving the infrastructure holds under realistic load by populating a test environment with 100K synthetic traces, running pgvector HNSW searches to verify sub-50ms p99 latency, and exercising the Lua token-bucket rate limiter to confirm it handles agent burst workloads without incorrectly blocking legitimate traffic.

The most significant technical risks are: (1) the 100K synthetic trace population for capacity testing requires calling OpenAI at ~\$1.20 in embedding cost and will take significant clock time due to the embedding worker's 10-trace-per-batch, 5-second-poll design; (2) the pgvector HNSW index requires approximately 800 MB of `maintenance_work_mem` to build in-memory for 100K 1536-dim vectors — the current Docker Compose setup has no memory limits configured, which is fine for local testing but must be validated; (3) the rate limiter's 60-second TTL on Redis keys means burst validation tests must account for bucket state carried over between test runs.

The 12 existing seed traces in `api/fixtures/sample_traces.json` provide a quality template. They use the `agent_model`/`agent_version` fields and include real code in `solution_text`. The seed import pipeline needs to: create a seed contributor user, insert traces with `is_seed=True` and `status="validated"` (bypassing the normal pending flow), attach tags, and let the existing embedding worker pick up embedding via the normal `embedding IS NULL` poll.

**Primary recommendation:** Build the seed import as a standalone Python script (not an API endpoint) that connects directly to the database, reuses the existing `Trace` and `Tag` models, and marks records with `is_seed=True`/`status="validated"`. Use Locust 2.43.3 for capacity and rate-limit validation, with separate locustfiles for each test scenario. Do not call OpenAI for the 100K capacity test — use pre-computed random vectors or a local sentence-transformers model to avoid cost and rate limit issues.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| locust | 2.43.3 | Load testing for capacity and rate limit validation | Standard Python load testing tool; pure Python, no XML; used by Google/Microsoft |
| faker | current (30.x) | Generate realistic synthetic trace metadata for capacity test | Deterministic, seeded, zero API cost |
| sentence-transformers | >=3.0 (already in pyproject.toml) | Generate synthetic embeddings for capacity test without OpenAI | Avoids \$1.20 OpenAI cost; `all-MiniLM-L6-v2` produces 384-dim vectors that can be zero-padded to 1536 for HNSW testing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncpg | >=0.31.0 (already pinned) | Direct async bulk insert for 100K trace capacity population | COPY protocol is faster than SQLAlchemy ORM for bulk loads |
| pgvectorbench | latest | Dedicated pgvector HNSW benchmarking with p99 latency output | Use if you want repeatable, hardware-normalized benchmarks |
| httpx | >=0.27 (already pinned) | Locust can use httpx for async client if needed | Locust's default requests client is synchronous; sufficient for the tests here |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Locust | k6, Gatling, wrk | k6 is JS; Gatling is Scala; wrk is C with no Python logic. Locust lets us write burst patterns and rate-limit assertions in plain Python. Locust is the right choice. |
| faker for synthetic capacity data | OpenAI to generate real traces | OpenAI costs \$1.20, takes hours due to rate limits, and is unnecessary — HNSW performance testing doesn't require semantically meaningful text |
| Random numpy vectors for embedding | sentence-transformers | numpy random vectors are fastest but produce uniform cosine distances, which tests index mechanics but not realistic ANN search behavior. sentence-transformers generates realistic embedding distributions. |
| Standalone Python import script | FastAPI endpoint for seed import | An endpoint would be exposed permanently and require auth flow; a one-time script is safer, simpler, and can run `alembic upgrade head` first |

**Installation:**
```bash
# In the api dev environment
uv add --dev locust faker

# Or for the capacity test runner (separate script, no production dep)
pip install locust faker
```

## Architecture Patterns

### Recommended Project Structure
```
api/
├── fixtures/
│   ├── sample_traces.json        # 12 existing traces (Phase 1)
│   └── seed_traces.json          # 200-500 curated seed traces (07-01 creates this)
├── scripts/
│   ├── import_seeds.py           # 07-01: standalone seed import pipeline
│   └── generate_capacity_data.py # 07-02: generates 100K synthetic traces
tests/
└── load/
    ├── locustfile_capacity.py    # 07-02: HNSW p99 latency test
    └── locustfile_rate_limit.py  # 07-02: rate limiter burst validation
```

### Pattern 1: Seed Import Pipeline

**What:** A standalone Python script that connects to the database, creates a seed contributor user (or finds existing one by email), reads `seed_traces.json`, and inserts each trace with `is_seed=True`, `status="validated"`, `trust_score=1.0`, `confirmation_count=2` (matching the `validation_threshold=2` default). Tags are normalized and created using the same logic as `app/services/tags.py`.

**When to use:** Run once before public launch. Re-running must be idempotent (skip traces that already exist by title match or by a seed_id field).

**Key design choices:**
- `status="validated"` at insert time — seed traces skip the confirmation flow by design (they're pre-validated by a human curator)
- `is_seed=True` flag already exists on the `Trace` model (added in Phase 1)
- Embedding is NOT generated by the import script — traces are inserted with `embedding=NULL` and the existing embedding worker picks them up via its `embedding IS NULL` poll
- The seed contributor user should have `is_seed=True` (the `User` model has this flag)
- Tags are normalized with the same `normalize_tag()` / `validate_tag()` functions from `app/services/tags.py`

**Example:**
```python
# api/scripts/import_seeds.py
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.trace import Trace, TraceStatus
from app.models.user import User
from app.models.tag import Tag, trace_tags
from app.services.tags import normalize_tag, validate_tag

SEED_CONTRIBUTOR_EMAIL = "seeds@commontrace.internal"

async def get_or_create_seed_user(db) -> uuid.UUID:
    result = await db.execute(
        select(User).where(User.email == SEED_CONTRIBUTOR_EMAIL)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=SEED_CONTRIBUTOR_EMAIL,
            display_name="CommonTrace Seeds",
            is_seed=True,
        )
        db.add(user)
        await db.flush()
    return user.id

async def import_seeds(seeds_path: Path) -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    seeds = json.loads(seeds_path.read_text())

    async with session_factory() as db:
        contributor_id = await get_or_create_seed_user(db)

        inserted = 0
        skipped = 0
        for raw in seeds:
            # Idempotency: skip if title already exists
            existing = await db.execute(
                select(Trace).where(Trace.title == raw["title"], Trace.is_seed.is_(True))
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            trace = Trace(
                title=raw["title"],
                context_text=raw["context"],
                solution_text=raw["solution"],
                status=TraceStatus.validated,
                trust_score=1.0,
                confirmation_count=2,  # >= validation_threshold
                is_seed=True,
                contributor_id=contributor_id,
                agent_model=raw.get("agent_model"),
                agent_version=raw.get("agent_version"),
            )
            db.add(trace)
            await db.flush()

            # Tags
            for raw_tag in raw.get("tags", []):
                normalized = normalize_tag(raw_tag)
                if not validate_tag(normalized):
                    continue
                result = await db.execute(select(Tag).where(Tag.name == normalized))
                tag = result.scalar_one_or_none()
                if tag is None:
                    tag = Tag(name=normalized)
                    db.add(tag)
                    await db.flush()
                await db.execute(
                    insert(trace_tags).values(trace_id=trace.id, tag_id=tag.id)
                )

            inserted += 1

        await db.commit()

    print(f"Seed import complete: {inserted} inserted, {skipped} skipped")

if __name__ == "__main__":
    asyncio.run(import_seeds(Path("api/fixtures/seed_traces.json")))
```

### Pattern 2: Capacity Test Data Generation (100K Traces)

**What:** Generate 100K synthetic traces with realistic embeddings for HNSW p99 latency validation.

**Critical insight:** Do NOT use OpenAI for 100K trace embeddings. Use one of:
1. Random numpy vectors (fastest, ~30 seconds, but flat cosine distribution)
2. Pre-compute a small set (~1000) of real embeddings and tile them with small random perturbations (realistic distribution, no rate limits)
3. Use sentence-transformers with `all-MiniLM-L6-v2` (384-dim) and zero-pad to 1536 (realistic, ~1-2 hours on CPU)

The recommended approach for HNSW latency testing is option 2 (tiled real embeddings with noise) — it produces a realistic ANN search landscape at ~\$0.02 cost (1000 embeddings) and takes minutes.

**Key insert technique:** Use asyncpg COPY protocol for bulk insert, not SQLAlchemy ORM. The ORM adds overhead that makes 100K inserts impractical.

```python
# api/scripts/generate_capacity_data.py
import asyncio
import asyncpg
import numpy as np
import uuid
from faker import Faker

fake = Faker(seed=42)
np.random.seed(42)

SEED_VECTORS = 1000  # real embeddings to tile from
TOTAL_TRACES = 100_000
DIM = 1536

async def generate_capacity_data(base_url: str):
    conn = await asyncpg.connect(base_url)

    # Generate base vectors (either load from pre-computed file or generate random)
    # For HNSW testing, random normalized vectors are sufficient
    base_vectors = np.random.randn(SEED_VECTORS, DIM).astype(np.float32)
    base_vectors /= np.linalg.norm(base_vectors, axis=1, keepdims=True)  # normalize to unit sphere

    # Create seed user for capacity test
    seed_user_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO users (id, email, display_name, is_seed) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
        uuid.UUID(seed_user_id), "capacity-test@commontrace.internal", "Capacity Test", True
    )

    # Bulk insert using COPY
    records = []
    for i in range(TOTAL_TRACES):
        base_idx = i % SEED_VECTORS
        # Add small noise to base vector for realistic ANN distribution
        noise = np.random.randn(DIM).astype(np.float32) * 0.05
        vec = base_vectors[base_idx] + noise
        vec /= np.linalg.norm(vec)  # renormalize

        records.append((
            uuid.uuid4(),
            f"Capacity test trace {i}: {fake.bs()}",
            fake.paragraph(nb_sentences=3),
            fake.paragraph(nb_sentences=5),
            vec.tolist(),
            "text-embedding-3-small",
            "validated",
            1.0,
            2,
            uuid.UUID(seed_user_id),
            True,
        ))

        if len(records) >= 1000:
            await conn.executemany(
                """INSERT INTO traces
                   (id, title, context_text, solution_text, embedding, embedding_model_id,
                    status, trust_score, confirmation_count, contributor_id, is_seed)
                   VALUES ($1, $2, $3, $4, $5::vector, $6, $7, $8, $9, $10, $11)""",
                records
            )
            records = []
            print(f"Inserted {i+1}/{TOTAL_TRACES}")

    if records:
        await conn.executemany(...)

    await conn.close()
```

### Pattern 3: Locust Rate Limiter Burst Validation

**What:** Test that the token-bucket rate limiter correctly handles burst workloads without incorrectly blocking legitimate agents.

**Key validation assertions:**
1. Burst of `rate_limit_read_per_minute` requests in <1 second: all should succeed (bucket starts full)
2. After burst, next `rate_limit_read_per_minute` requests within the same minute: most should get 429
3. After waiting ~10 seconds (partial refill): `10 * (rate/60)` more requests should succeed
4. Different user IDs get independent buckets (no cross-user interference)

```python
# tests/load/locustfile_rate_limit.py
from locust import HttpUser, task, between, constant
import time

class BurstAgent(HttpUser):
    """Simulates a Claude Code agent that sends a burst of requests."""
    wait_time = constant(0)  # No wait — pure burst test

    def on_start(self):
        # Register and authenticate
        resp = self.client.post("/api/v1/auth/register", json={
            "email": f"agent-{self.environment.runner.user_count}@test.invalid"
        })
        self.token = resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.burst_count = 0
        self.success_count = 0
        self.rate_limited_count = 0

    @task
    def search_burst(self):
        with self.client.post(
            "/api/v1/traces/search",
            json={"q": "react hooks useState"},
            headers=self.headers,
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                self.success_count += 1
                resp.success()
            elif resp.status_code == 429:
                self.rate_limited_count += 1
                resp.success()  # 429 is EXPECTED behavior — not a test failure
            else:
                resp.failure(f"Unexpected status {resp.status_code}")
        self.burst_count += 1
```

**Rate limit validation assertions (in a pytest test, not Locust):**

```python
# tests/test_rate_limiter.py
import pytest
import asyncio
import time
from httpx import AsyncClient

async def test_burst_does_not_incorrectly_block(client: AsyncClient, auth_headers):
    """A full bucket allows burst equal to rate_limit_read_per_minute."""
    # Clear Redis key first to reset bucket state
    await redis.delete(f"rl:{user_id}:read")

    READ_LIMIT = 60  # rate_limit_read_per_minute default
    responses = await asyncio.gather(*[
        client.post("/api/v1/traces/search", json={"q": "test"}, headers=auth_headers)
        for _ in range(READ_LIMIT)
    ])

    success_count = sum(1 for r in responses if r.status_code == 200)
    # Full bucket should allow exactly READ_LIMIT requests
    assert success_count == READ_LIMIT, f"Expected {READ_LIMIT} successes, got {success_count}"

async def test_rate_limit_enforced_after_burst(client: AsyncClient, auth_headers):
    """After exhausting the bucket, next request is rate-limited."""
    await redis.delete(f"rl:{user_id}:read")
    READ_LIMIT = 60

    # Exhaust the bucket
    for _ in range(READ_LIMIT):
        await client.post("/api/v1/traces/search", json={"q": "test"}, headers=auth_headers)

    # Next request should be rate-limited
    resp = await client.post("/api/v1/traces/search", json={"q": "test"}, headers=auth_headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers

async def test_refill_after_wait(client: AsyncClient, auth_headers):
    """After partial wait, some tokens refill."""
    await redis.delete(f"rl:{user_id}:read")
    READ_LIMIT = 60

    # Exhaust bucket
    for _ in range(READ_LIMIT):
        await client.post("/api/v1/traces/search", json={"q": "test"}, headers=auth_headers)

    # Wait 10 seconds — refill_rate = 60/60 = 1 token/sec → ~10 tokens
    await asyncio.sleep(10)

    responses = await asyncio.gather(*[
        client.post("/api/v1/traces/search", json={"q": "test"}, headers=auth_headers)
        for _ in range(15)
    ])
    success_count = sum(1 for r in responses if r.status_code == 200)
    # Should have ~10 successes (±1 for timing)
    assert 8 <= success_count <= 12, f"Expected ~10 refilled tokens, got {success_count}"
```

### Pattern 4: HNSW p99 Latency Measurement with Locust

**What:** Run 100K-trace HNSW search queries and measure p99 latency using Locust's built-in percentile reporting.

```python
# tests/load/locustfile_capacity.py
from locust import HttpUser, task, constant

SEARCH_QUERIES = [
    "react hooks useState",
    "postgresql migration alembic",
    "docker compose healthcheck",
    "fastapi async sqlalchemy",
    "python error handling retry",
    "github actions ci pipeline",
    "jwt authentication middleware",
    "redis caching ttl pattern",
]

class SearchLoadUser(HttpUser):
    wait_time = constant(0.1)  # 10 RPS per user, scale with --users

    def on_start(self):
        resp = self.client.post("/api/v1/auth/register", json={"email": f"load-{id(self)}@test.invalid"})
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}
        self._query_idx = 0

    @task
    def search(self):
        query = SEARCH_QUERIES[self._query_idx % len(SEARCH_QUERIES)]
        self._query_idx += 1
        self.client.post(
            "/api/v1/traces/search",
            json={"q": query, "limit": 10},
            headers=self.headers,
            name="/api/v1/traces/search"
        )
```

**Run command:**
```bash
locust -f tests/load/locustfile_capacity.py \
  --host http://localhost:8000 \
  --users 20 \
  --spawn-rate 5 \
  --run-time 60s \
  --headless \
  --csv=results/capacity
# Check results/capacity_stats.csv for p99 column
```

Locust reports p99 latency natively in its CSV output and web UI.

### Anti-Patterns to Avoid

- **Using OpenAI to embed 100K capacity test traces:** This costs \$1.20, takes hours (due to RPM limits), and is unnecessary. Use random normalized vectors or pre-computed+tiled embeddings.
- **Inserting capacity test data via the REST API:** The rate limiter will block it. Insert directly to the database using asyncpg COPY.
- **Testing rate limits without resetting Redis state:** Bucket state persists in Redis with 120-second TTL. Always `redis.delete(f"rl:{user_id}:{bucket_type}")` before a rate limit assertion test.
- **Running HNSW build without sufficient `maintenance_work_mem`:** At 100K 1536-dim vectors, the HNSW graph requires ~800 MB during build. With insufficient memory, the build spills to disk and takes much longer (still works, just slow).
- **Seed traces in `pending` status:** Seed traces MUST be inserted with `status="validated"` and `is_seed=True`. The search router filters by `embedding IS NOT NULL` and `embedding_model_id`, not by status — but the trust re-ranking uses `trust_score`, so seeds need `trust_score=1.0`.
- **Mixing capacity test data with production data:** The capacity test inserts 100K traces with `is_seed=True` and a dedicated `capacity-test@commontrace.internal` contributor. Clean up by deleting that user (CASCADE deletes traces) after the test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Load testing | Custom async benchmark scripts | Locust 2.43.3 | Locust handles concurrency, p99 reporting, ramp-up, CSV export automatically |
| Synthetic names/text | Custom random text generators | faker | faker produces realistic-looking text that makes logs readable |
| Bulk vector insert | SQLAlchemy ORM loop | asyncpg executemany / COPY | ORM is 10-50x slower for bulk operations; asyncpg binary COPY is the fastest path |
| p99 latency calculation | Manual percentile computation | Locust's built-in percentile reporting | Locust generates p50/p90/p95/p99 in CSV automatically |
| HNSW benchmarking | Custom timing scripts | pgvectorBench (optional) | pgvectorBench is purpose-built for pgvector with proper warmup and percentile reporting |

**Key insight:** Both tracks in this phase are about validation, not new features. Every custom tool you build is overhead that delays the actual validation signal.

## Common Pitfalls

### Pitfall 1: HNSW Index Not in Shared Memory
**What goes wrong:** Queries take 200-500ms instead of <5ms because the HNSW graph is being read from disk on each query.
**Why it happens:** The Docker Compose postgres container has default `shared_buffers` (128MB), which is far too small to hold a 600MB+ HNSW index for 100K 1536-dim vectors.
**How to avoid:** Set `POSTGRES_SHARED_BUFFERS=2GB` in Docker Compose environment variables for the capacity test. The index size is approximately `100K * (8 + 1536*4) bytes = ~600 MB` plus adjacency list overhead.
**Warning signs:** Query times are inconsistent (disk cache cold/warm swings). Check with `\d+ traces` in psql — if the table is large and `shared_buffers` is small, the index won't fit.

Configuration fix for capacity test:
```yaml
# docker-compose.yml postgres service
command: >
  postgres
  -c shared_buffers=2GB
  -c effective_cache_size=4GB
  -c maintenance_work_mem=1GB
```

### Pitfall 2: Rate Limit Bucket State Contamination Between Tests
**What goes wrong:** Rate limit tests fail inconsistently because Redis buckets carry state from previous test runs.
**Why it happens:** The Lua token bucket stores state in Redis with a 120-second TTL (`EXPIRE key 120`). If a test run exhausts a bucket, the next test run within 120 seconds sees a partially-depleted bucket.
**How to avoid:** In pytest fixtures, flush the specific Redis key before each rate limit test. Never use `flushall` in integration tests (kills other state). Use the key format `rl:{user_id}:{read|write}`.
**Warning signs:** Tests pass when run individually but fail in sequence.

### Pitfall 3: Embedding Worker Processing Seed Traces Too Slowly
**What goes wrong:** After importing 500 seed traces, search returns no results because the embedding worker hasn't processed them yet.
**Why it happens:** The embedding worker polls every 5 seconds in batches of 10 traces. 500 traces / 10 per batch = 50 poll cycles = ~4 minutes minimum. Plus OpenAI API latency per call.
**How to avoid:** After running `import_seeds.py`, run the import script's own embedding pass (directly calling the EmbeddingService for each trace) OR wait for the worker and add a readiness check to the import script that verifies `embedding IS NOT NULL` for all inserted seeds before exiting.
**Warning signs:** Search returns 0 results immediately after seed import. Query `SELECT count(*) FROM traces WHERE is_seed = true AND embedding IS NULL;` to check progress.

### Pitfall 4: HNSW ef_search=64 Undershooting Recall at High Throughput
**What goes wrong:** Under concurrent load (20+ users), p99 latency spikes because `hnsw.ef_search=64` is set with `SET LOCAL` (transaction-scoped), but high concurrency means many transactions compete for the same index pages.
**Why it happens:** `SET LOCAL hnsw.ef_search = 64` in the search router is correct — it's per-transaction. But under load, the HNSW graph traversal becomes CPU-bound, not I/O-bound, at 100K scale. Higher ef_search values increase CPU time per query.
**How to avoid:** Keep `ef_search=64` (current codebase value) for the capacity test. If p99 exceeds 50ms, try lowering to `ef_search=40` (the pgvector default). The tradeoff is recall vs. latency. At 100K traces with 1536 dims, `ef_search=40-64` should comfortably achieve sub-10ms p99 on any modern server.
**Warning signs:** p99 > 50ms at ef_search=64. Check Prometheus `commontrace_search_duration_seconds` histogram.

### Pitfall 5: Seed Trace Quality — Context Without Code
**What goes wrong:** Seed traces have good titles but context/solution fields that are too abstract, making them unfindable via semantic search on specific queries.
**Why it happens:** Abstract traces ("How to use Docker") have embeddings far from specific queries ("Docker Compose healthcheck for PostgreSQL service"). The 12 existing sample traces are good models — they all include actual code in `solution_text`.
**How to avoid:** For each seed trace, the solution MUST include runnable code (not pseudocode). The context MUST describe a specific, concrete problem a Claude Code agent would encounter. Review the 12 existing `sample_traces.json` entries as the quality bar.
**Warning signs:** After seeding, search for "docker compose healthcheck" returns no results even though you have a Docker trace. The embedding is too generic.

### Pitfall 6: Freemium Tier Limits Not Validated Against Agent Patterns
**What goes wrong:** The freemium tier rate limits (default: 60 reads/min, 20 writes/min) block legitimate Claude Code agent workloads during a coding session.
**Why it happens:** Agent workloads are bursty — a single coding task might trigger 10-15 search requests in 30 seconds, then go quiet for 5 minutes. A token-bucket refilling at 1 req/sec from 60-token capacity handles this fine. But if an agent batches all requests at startup (no think-time), it could exhaust the bucket.
**How to avoid:** Validate with a realistic Claude Code agent simulation: 10-15 searches over 30 seconds, then idle for 5 minutes. The token bucket should handle this burst (starts full at 60 tokens, uses 15, refills to ~65 over 5 minutes — still well within limits).
**Warning signs:** Agents getting 429 during legitimate burst activity. The Locust burst test should expose this.

## Code Examples

Verified patterns from official sources and codebase inspection:

### HNSW Search Latency Measurement via Prometheus
```python
# Already implemented in api/app/routers/search.py
# Measures end-to-end search latency including embedding call
search_duration = Histogram(
    "commontrace_search_duration_seconds",
    "End-to-end search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)
# The 0.05 bucket (50ms) is already in the histogram — use this to validate p99
# curl http://localhost:8000/metrics | grep commontrace_search_duration
```

### Check HNSW p99 via PostgreSQL
```sql
-- Measure raw HNSW query latency (bypasses embedding API latency)
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, title, 1 - (embedding <=> '[...]'::vector) as similarity
FROM traces
WHERE status = 'validated'
  AND embedding IS NOT NULL
  AND embedding_model_id = 'text-embedding-3-small'
  AND is_flagged = false
ORDER BY embedding <=> '[...]'::vector
LIMIT 10;
-- Look for "Execution Time:" in output
```

### Verify HNSW Index Is Being Used
```sql
-- Confirm the planner uses the HNSW index (not a seq scan)
SET hnsw.ef_search = 64;
EXPLAIN SELECT id FROM traces ORDER BY embedding <=> '[...]'::vector LIMIT 10;
-- Should show "Index Scan using ix_traces_embedding_hnsw on traces"
```

### Check HNSW Index Memory Fit
```sql
-- Check actual index size
SELECT pg_size_pretty(pg_relation_size('ix_traces_embedding_hnsw')) as index_size;

-- Check shared_buffers
SHOW shared_buffers;

-- If index_size > shared_buffers, the index won't fit in memory → slow queries
```

### Rate Limiter State Inspection
```bash
# Check current token bucket state for a user
redis-cli HGETALL "rl:{user_id}:read"
# Output: tokens (current), last_refill (unix timestamp)

# Reset a user's read bucket (for test setup)
redis-cli DEL "rl:{user_id}:read"
```

### Locust Run Command for p99 Validation
```bash
# Run capacity test — adjust --users for your target concurrency
locust -f tests/load/locustfile_capacity.py \
  --host http://localhost:8000 \
  --users 50 \
  --spawn-rate 10 \
  --run-time 120s \
  --headless \
  --only-summary \
  --csv=results/capacity_test

# Check p99 in results
awk -F',' 'NR==2{print "p50:", $10, "p90:", $11, "p99:", $12}' results/capacity_test_stats.csv
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IVFFlat for ANN | HNSW for ANN | pgvector 0.5.0 (2023) | 30x QPS boost, 30x p99 latency improvement at same recall |
| `maintenance_work_mem=64MB` | Must size to ~1.3x index data for in-memory build | pgvector 0.5.0+ | Without sufficient memory, HNSW build spills to disk and is much slower |
| Fixed-window rate limiting | Token-bucket rate limiting | — | Token bucket allows burst while enforcing average rate — essential for agent workloads |
| Manual data fixtures | Seed data with `is_seed=True` flag | Phase 1 design | Clean separation between seed and user-contributed traces |
| Alembic autogenerate for vector indexes | Manual HNSW DDL | Phase 1 decision | Autogenerate cannot handle HNSW or Vector types reliably |

**Deprecated/outdated:**
- IVFFlat: Still available in pgvector but superseded by HNSW for most workloads. Use HNSW for any new deployment.
- `asyncio.wait_for()` timeout: Replaced by `asyncio.timeout()` in Python 3.11+. The codebase targets Python 3.12, so prefer `asyncio.timeout()`.

## Open Questions

1. **What is the actual p99 HNSW latency for 100K 1536-dim vectors on the production host?**
   - What we know: At ~58K vectors, p99 is ~1.5ms. At 1M vectors on high-memory AWS instances, p99 is ~5ms. Our target is <50ms, which the literature strongly suggests is achievable at 100K scale.
   - What's unclear: The production host hardware (CPU, RAM, disk speed) is unknown. Docker Compose adds overhead vs. bare-metal PostgreSQL.
   - Recommendation: Run the actual capacity test on the target host and measure. The <50ms target is conservative enough that it should pass unless the host is severely memory-constrained.

2. **Does the HNSW index handle concurrent writes during the capacity test?**
   - What we know: PostgreSQL uses a write lock on HNSW pages during updates. Concurrent reads are allowed.
   - What's unclear: Whether the embedding worker inserting embeddings (updating `embedding` column) during load testing causes lock contention.
   - Recommendation: Run capacity test with the embedding worker stopped. The test is for read latency, not write throughput.

3. **What is the right freemium rate limit for agents vs. humans?**
   - What we know: Default is 60 reads/min, 20 writes/min. The phase context notes "freemium tier pricing needs market validation."
   - What's unclear: Whether 60 reads/min is too low for an agent running a multi-step coding task, or too high for a free tier.
   - Recommendation: The token-bucket design handles this — limits are env vars (`rate_limit_read_per_minute`, `rate_limit_write_per_minute`), so they can be changed without code changes. Validate with the Locust burst test using realistic agent request patterns (10-15 searches in 30 seconds, then idle).

4. **How many seed trace topics are needed for "first query returns relevant results"?**
   - What we know: Success criterion requires 200+ validated traces covering React setup, PostgreSQL migrations, Docker configuration, common API integrations. The 12 existing sample traces cover FastAPI, SQLAlchemy, Docker, pgvector, Alembic, Redis, JWT, Pydantic, GitHub Actions, React, PostgreSQL indexing, and async Python.
   - What's unclear: Whether 200 traces is enough for adequate semantic search coverage, or if clusters of similar traces (5+ per topic) are needed for the HNSW index to produce good results.
   - Recommendation: Aim for 50+ distinct topic clusters with 3-5 traces per cluster. This gives diversity for semantic search and enough confirmation mass for trust scores.

## Sources

### Primary (HIGH confidence)
- Codebase: `/home/bitnami/commontrace/api/app/models/trace.py` — Trace model, `is_seed` flag, status enum
- Codebase: `/home/bitnami/commontrace/api/app/middleware/rate_limiter.py` — Lua token-bucket implementation, key format, TTL
- Codebase: `/home/bitnami/commontrace/api/app/worker/embedding_worker.py` — Batch size=10, poll interval=5s
- Codebase: `/home/bitnami/commontrace/api/app/routers/search.py` — SEARCH_LIMIT_ANN=100, ef_search=64, search metrics
- Codebase: `/home/bitnami/commontrace/api/fixtures/sample_traces.json` — 12 existing seed traces as quality template
- Codebase: `/home/bitnami/commontrace/api/app/config.py` — `rate_limit_read_per_minute=60`, `rate_limit_write_per_minute=20`
- [Locust documentation 2.43.3](https://docs.locust.io/en/stable/) — catch_response, load shapes, CSV output
- [pgvector GitHub issue #844](https://github.com/pgvector/pgvector/issues/844) — HNSW memory formula: `n * (8 + dims*4) * 1.3`

### Secondary (MEDIUM confidence)
- [Crunchy Data: HNSW Indexes with pgvector](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector) — default ef_search=40, m=16 guidance
- [Jonathan Katz: pgvector 150x speedup](https://jkatz05.com/post/postgres/pgvector-performance-150x-speedup/) — p99 of ~2.65-5.51ms at 1M vectors on high-memory AWS
- [Neon: vector search optimization](https://neon.com/docs/ai/ai-vector-search-optimization) — ef_construction should be >= 2*m
- [OpenAI pricing](https://openai.com/api/pricing/) — text-embedding-3-small \$0.02/1M tokens (batch: \$0.01/1M)
- [pgvectorBench](https://github.com/pgvectorBench/pgvectorBench) — cohere_small_100k dataset, p90/p99/p99.9 reporting
- Neon blog: ~1.5ms query latency at ~58K vectors with HNSW cosine distance

### Tertiary (LOW confidence)
- Various Medium/blog posts on HNSW latency — consistent with ~1-5ms for sub-million scale on adequate hardware, but hardware-dependent

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Locust 2.43.3 is current stable, faker is well-established, all other dependencies already in the codebase
- Architecture (import pipeline): HIGH — built on the existing Trace/Tag models, the `is_seed` flag is already in the schema, the embedding worker already polls `embedding IS NULL`
- Architecture (capacity test): MEDIUM — the approach is sound, but the specific asyncpg COPY invocation for pgvector columns needs validation (pgvector requires the `::vector` cast)
- HNSW p99 latency: MEDIUM — literature strongly supports <50ms at 100K scale, but actual numbers are hardware-dependent; the 50ms target is conservative and should be met
- Rate limiter validation: HIGH — the Lua token-bucket logic is deterministic and the test patterns follow directly from the implementation
- Pitfalls: HIGH — most come from direct codebase inspection (Redis TTL=120s, batch_size=10, ef_search=64 already set)

**Research date:** 2026-02-20
**Valid until:** 2026-04-01 (pgvector and Locust are stable; OpenAI pricing could change)
