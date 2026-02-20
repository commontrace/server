---
phase: 03-search-discovery
plan: 02
subsystem: api
tags: [pgvector, openai, fastapi, sqlalchemy, prometheus-client, hybrid-search, cosine-similarity, tag-filter]

# Dependency graph
requires:
  - phase: 03-search-discovery
    plan: 01
    provides: EmbeddingService with AsyncOpenAI text-embedding-3-small and EmbeddingSkippedError
  - phase: 01-data-foundation
    provides: Trace.embedding Vector(1536), Trace.trust_score, Trace.is_flagged, trace_tags join table, HNSW index
  - phase: 02-core-api
    provides: CurrentUser, DbSession, ReadRateLimit dependencies, structlog, Redis lifespan

provides:
  - POST /api/v1/traces/search endpoint with hybrid pgvector cosine ANN + SQL tag pre-filter
  - Trust-weighted re-ranking formula: (1 - distance) * log1p(max(0, trust_score) + 1)
  - Tag-only search mode (no embedding service call) returning results ordered by trust_score DESC
  - TraceSearchRequest, TraceSearchResult, TraceSearchResponse Pydantic schemas
  - search_requests Counter and search_duration Histogram Prometheus metrics

affects:
  - 03-search-discovery (Plan 03 — observability/metrics consolidation may reference search metrics)
  - 05-mcp-layer (MCP tool will call this endpoint to surface traces to AI agents)
  - 06-skill-layer (Skill layer queries will use this search endpoint)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - pgvector cosine ANN with SEARCH_LIMIT_ANN=100 over-fetch before trust re-ranking
    - SET LOCAL hnsw.ef_search = 64 scoped to transaction for improved ANN recall
    - Tag AND-filter: JOIN trace_tags + JOIN Tag + GROUP BY Trace.id + HAVING COUNT(DISTINCT tag.id) == N
    - Trust re-ranking: similarity * log1p(trust_score + 1) — logarithmic weight dampens outliers
    - Path split: semantic (query_vector is not None) vs tag-only at endpoint entry
    - EmbeddingSkippedError caught and re-raised as HTTP 503 (only in semantic mode)

key-files:
  created:
    - api/app/schemas/search.py
    - api/app/routers/search.py
  modified:
    - api/app/main.py

key-decisions:
  - "SEARCH_LIMIT_ANN=100 over-fetch: ANN finds nearest 100, re-ranking selects top limit to avoid trust-reranking cutting off good semantic matches"
  - "GROUP BY uses full cosine_distance expression not alias: PostgreSQL requires expression in GROUP BY, not SELECT alias (avoids pitfall from 03-RESEARCH.md)"
  - "Tag-only mode sets similarity_score=0.0 and combined_score=trust_score: clearly signals no semantic ranking occurred"
  - "503 only when q is provided and embedding service unavailable: tag-only search never fails due to missing API key"

patterns-established:
  - "Search path split: check query_vector at top of endpoint, two code paths for semantic vs tag-only"
  - "Prometheus metrics at endpoint level: Counter(has_tags label) + Histogram(duration)"

# Metrics
duration: 1min
completed: 2026-02-20
---

# Phase 3 Plan 02: Hybrid Search Endpoint Summary

**POST /api/v1/traces/search combining pgvector cosine ANN with SQL tag AND-filter and trust-weighted re-ranking (1-distance)*log1p(trust+1); tag-only mode bypasses embedding service entirely**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-20T06:09:41Z
- **Completed:** 2026-02-20T06:10:52Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Full hybrid search endpoint (q-only, tags-only, and q+tags modes) in a single implementation
- Cosine ANN with pgvector, over-fetch 100 candidates, then trust-weighted re-ranking applied in Python
- Tag AND-filter via GROUP BY Trace.id + HAVING COUNT(DISTINCT Tag.id) == len(tags) — handles any N tags
- Tag-only path returns trust_score DESC without touching the embedding service (never 503s)
- HNSW ef_search=64 via SET LOCAL (transaction-scoped) for improved ANN recall in semantic mode
- search_requests Counter (labeled by has_tags) and search_duration Histogram instrumented

## Task Commits

Each task was committed atomically:

1. **Task 1: Search schemas and endpoint** - `5fe17d9` (feat)

## Files Created/Modified
- `api/app/schemas/search.py` - TraceSearchRequest (q Optional[str], tags list, limit), TraceSearchResult, TraceSearchResponse
- `api/app/routers/search.py` - POST /api/v1/traces/search with semantic/tag-only/hybrid paths, trust re-ranking, Prometheus metrics
- `api/app/main.py` - search router imported and registered

## Decisions Made
- SEARCH_LIMIT_ANN=100: over-fetch from ANN before re-ranking ensures trust score can promote results that weren't ranked #1 by cosine distance alone
- GROUP BY uses full `Trace.embedding.cosine_distance(query_vector)` expression not the `distance_col` alias — PostgreSQL requires the expression in GROUP BY (confirmed from research pitfall notes)
- Tag-only similarity_score set to 0.0, combined_score set to trust_score — unambiguous signal to callers that no semantic ranking occurred
- 503 returned only in semantic mode when OPENAI_API_KEY absent; tag-only never raises 503 (embedding service not involved)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all imports resolved cleanly, all 7 verification checks passed on first run.

## User Setup Required

None - no additional configuration required beyond OPENAI_API_KEY (documented in 03-01 setup).

## Next Phase Readiness
- POST /api/v1/traces/search is fully operational and ready for 03-03 (observability consolidation)
- Search metrics (search_requests, search_duration) already in place for Phase 03-03 consolidation
- MCP layer (Phase 5) can wrap this endpoint as a tool call
- Tag-only mode lets agents discover traces without requiring embeddings to exist

---
*Phase: 03-search-discovery*
*Completed: 2026-02-20*
