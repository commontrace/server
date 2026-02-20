# Phase 3: Plan Review Log

**Phase:** 03-search-discovery (Search + Discovery)
**Plans reviewed:** 3 (03-01, 03-02, 03-03)
**Review iterations:** 2
**Final status:** PASSED (all blockers resolved)

---

## Iteration 1: Initial Review

**Checker found:** 1 blocker, 1 warning, 1 info

### Issue 1 — BLOCKER: Pure tag-only search broken (requirement_coverage)

**Plan:** 03-02 (Search endpoint)
**Requirement:** SRCH-02 — Agent can filter traces by structured tags

**Problem:** `TraceSearchRequest.q` was defined as `str` with `min_length=1`, making it a required field. This meant:
- An agent performing a pure tag-only query (SRCH-02, SC-2) had to always supply a query string
- The endpoint always embedded the query and computed cosine distance, polluting tag-only results with unwanted semantic signal
- If the embedding service was unavailable (no API key), tag-only search returned HTTP 503 — making tag search entirely dependent on the embedding service

**Fix applied:** Changed `q` to `Optional[str] = None`. When `q` is None:
- Skip the embed call entirely
- Run a pure tag+trust SQL query ordered by `trust_score DESC`
- No HNSW tuning, no embedding IS NULL filter (those are valid results for tag-only)
- `similarity_score` set to `0.0`, `combined_score` equals `trust_score`
- 422 returned when both `q` and `tags` are empty

**Impact:** SRCH-02 now works independently of the embedding service.

### Issue 2 — WARNING: Wave 2 file conflict between 03-02 and 03-03 (dependency_correctness)

**Plans:** 03-02, 03-03
**Problem:** Plan 03-03 Task 2 modified `api/app/routers/search.py`, which doesn't exist until Plan 03-02 creates it. Both plans were wave 2, permitting parallel execution that would cause a file write conflict.

**Fix applied:** Moved search metric instrumentation (4 lines + imports) into 03-02 itself — search metrics (`search_requests`, `search_duration`) are defined locally in `api/app/routers/search.py`. Plan 03-03 no longer touches `search.py` at all. Plan 03-03's `metrics.py` explicitly notes NOT to duplicate these definitions to avoid prometheus_client duplicate registration errors.

**Impact:** No file conflicts between wave 2 plans.

### Issue 3 — INFO: Missing ReadRateLimit import (task_completeness)

**Plan:** 03-02, Task 1
**Problem:** Search endpoint function signature used `_rate: ReadRateLimit` but the action didn't list the import statement.

**Fix applied:** Added explicit `from app.middleware.rate_limiter import ReadRateLimit` to the imports section.

**Impact:** Executor can implement without inferring import paths.

---

## Iteration 2: Post-Revision Review

**Checker found:** 1 blocker, 1 warning

### Issue 4 — BLOCKER: Verify imports non-existent name (task_completeness)

**Plan:** 03-03, Task 1
**Problem:** The verify command imported `search_requests` from `app.metrics`, but that name was explicitly removed from `metrics.py` in the iteration 1 fix (moved to `routers/search.py`). The verify step would always fail with `ImportError`.

**Fix applied (orchestrator):** Changed verify import from:
```python
from app.metrics import embeddings_processed, search_requests, metrics_endpoint
```
To:
```python
from app.metrics import embeddings_processed, embedding_duration, http_requests, metrics_endpoint
```

**Impact:** Verify step now tests names that actually exist in `metrics.py`.

### Issue 5 — WARNING: Plans 03-02 and 03-03 both modify main.py in wave 2 (dependency_correctness)

**Plans:** 03-02, 03-03
**Problem:** Both plans added lines to `main.py` in wave 2 without ordering constraint. Additionally, 03-03's context block referenced `@api/app/routers/search.py` from 03-02, implying an implicit dependency.

**Fix applied (orchestrator):** Changed 03-03 frontmatter:
- `wave: 2` → `wave: 3`
- `depends_on: ["03-01"]` → `depends_on: ["03-01", "03-02"]`

**Impact:** Execution order is now explicit: 03-01 → 03-02 → 03-03. No file collision on main.py.

---

## Final Wave Structure

| Wave | Plans | What it builds |
|------|-------|----------------|
| 1 | 03-01 | Embedding worker + EmbeddingService |
| 2 | 03-02 | Hybrid search endpoint (semantic + tag + trust ranking) |
| 3 | 03-03 | Observability (structlog, Prometheus, middleware, drift detection) |

---

## Key Design Decisions Made During Review

1. **Tag-only search path:** When `q` is None, results are ordered by `trust_score DESC` only — no semantic signal. `similarity_score` is `0.0` for tag-only results.

2. **Search metrics ownership:** Defined locally in `routers/search.py` (not centralized in `metrics.py`) to avoid cross-plan file conflicts and prometheus duplicate registration errors.

3. **Sequential waves:** Changed from 2 waves to 3 waves to make dependency ordering explicit and prevent main.py file collisions.

---

*Reviewed: 2026-02-20*
*Iterations: 2 (initial + 1 revision)*
*All blockers resolved*
