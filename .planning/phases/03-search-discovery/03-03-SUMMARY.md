---
phase: 03-search-discovery
plan: 03
subsystem: api
tags: [structlog, prometheus-client, observability, middleware, metrics, tracing, logging]

# Dependency graph
requires:
  - phase: 03-search-discovery
    plan: 01
    provides: EmbeddingService, embedding_worker, prometheus-client installed
  - phase: 03-search-discovery
    plan: 02
    provides: search_requests Counter and search_duration Histogram already defined in search.py

provides:
  - configure_logging() with JSON structlog, merge_contextvars, and ISO timestamps
  - Prometheus Counter and Histogram definitions for embedding worker (embeddings_processed, embedding_duration)
  - Prometheus Counter and Histogram definitions for HTTP layer (http_requests, http_request_duration)
  - GET /metrics endpoint serving Prometheus exposition format
  - RequestLoggingMiddleware: per-request request_id binding, timing, structured JSON log on completion
  - Embedding model drift detection at worker startup (warning log when existing model IDs differ)

affects:
  - 04-reputation-engine (Prometheus metrics available; GET /metrics scraped by monitoring stack)
  - 05-mcp-layer (structured logs with request_id enable end-to-end trace of MCP calls)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - structlog contextvars pattern: clear_contextvars() + bind_contextvars() per request for coroutine-safe context
    - Prometheus metric registration in dedicated metrics.py module (no duplicate registrations across modules)
    - BaseHTTPMiddleware for request lifecycle instrumentation (timing + headers + structured log)
    - Drift detection via GROUP BY embedding_model_id at worker startup (one DB query, O(N models) log entries)

key-files:
  created:
    - api/app/logging_config.py
    - api/app/metrics.py
    - api/app/middleware/logging_middleware.py
  modified:
    - api/app/main.py
    - api/app/worker/embedding_worker.py

key-decisions:
  - "Search metrics (search_requests, search_duration) remain in routers/search.py from Plan 03-02 — no duplication into metrics.py to avoid prometheus_client duplicate registration errors"
  - "configure_logging() called in lifespan startup for API, and at top of run_worker() for worker — each process independently configures structlog"
  - "Drift detection uses a single DB query at startup (not per-batch) to minimize overhead"

# Metrics
duration: 2min
completed: 2026-02-20
---

# Phase 3 Plan 03: Observability (Structlog + Prometheus) Summary

**JSON structured logging on all HTTP requests with per-request request_id via contextvars, Prometheus counters/histograms for embedding worker operations and HTTP layer, GET /metrics endpoint, and embedding model drift detection at worker startup**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-20T06:13:31Z
- **Completed:** 2026-02-20T06:15:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `api/app/logging_config.py`: `configure_logging()` using structlog with `merge_contextvars` as first processor, JSON rendering, ISO timestamps
- `api/app/metrics.py`: `embeddings_processed` Counter (model, status labels), `embedding_duration` Histogram, `http_requests` Counter, `http_request_duration` Histogram, `metrics_endpoint` async handler
- `api/app/middleware/logging_middleware.py`: `RequestLoggingMiddleware` generates UUID request_id per request, binds to contextvars, times request, logs completion with status_code and duration_ms, increments Prometheus counters, adds X-Request-ID response header
- `api/app/main.py`: `configure_logging()` called first in lifespan startup, `RequestLoggingMiddleware` registered, `GET /metrics` endpoint wired to `metrics_endpoint`
- `api/app/worker/embedding_worker.py`: `configure_logging()` at worker startup, Prometheus counters/histograms instrumented on success/error/skipped paths in `process_batch`, model drift detection in `run_worker()` warns when existing traces used a different `embedding_model_id`

## Task Commits

Each task was committed atomically:

1. **Task 1: Structlog config, Prometheus metrics, and logging middleware** - `de99ae0` (feat)
2. **Task 2: Wire observability into main.py, worker, and search endpoint** - `edaa2c7` (feat)

## Files Created/Modified

- `api/app/logging_config.py` - configure_logging() with merge_contextvars, JSON rendering, structlog stdlib integration
- `api/app/metrics.py` - embeddings_processed Counter, embedding_duration Histogram, http_requests Counter, http_request_duration Histogram, metrics_endpoint handler
- `api/app/middleware/logging_middleware.py` - RequestLoggingMiddleware with UUID request_id, contextvars binding, timing, Prometheus instrumentation, X-Request-ID header
- `api/app/main.py` - configure_logging() in lifespan, add_middleware(RequestLoggingMiddleware), GET /metrics endpoint
- `api/app/worker/embedding_worker.py` - configure_logging() call, embeddings_processed/embedding_duration instrumentation on all three paths (success/error/skipped), drift detection block before main loop

## Decisions Made

- Search endpoint metrics (`search_requests`, `search_duration`) are defined in `api/app/routers/search.py` (Plan 03-02) and NOT duplicated in `metrics.py` — prometheus_client raises `ValueError: Duplicated timeseries` if the same metric name is registered twice; since search.py is always imported before metrics.py would register them, keeping them in search.py is the correct arrangement
- `configure_logging()` is called separately in API lifespan and worker `run_worker()` — each process is independent and needs its own structlog configuration call
- Drift detection runs once at worker startup (single SQL `GROUP BY embedding_model_id`) rather than per-batch to avoid DB overhead on every poll cycle

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all imports resolved cleanly, all verification checks passed on first run.

## User Setup Required

None beyond existing requirements (OPENAI_API_KEY for embeddings, documented in 03-01).

## Next Phase Readiness

- GET /metrics endpoint live for Prometheus scraping
- All HTTP requests produce structured JSON logs with request_id for log correlation
- Embedding worker produces structured logs with trace_id and model for every operation
- Phase 4 (reputation engine) can rely on Prometheus metrics and structured logs for dashboards and alerting

## Self-Check: PASSED

- FOUND: api/app/logging_config.py
- FOUND: api/app/metrics.py
- FOUND: api/app/middleware/logging_middleware.py
- FOUND: api/app/main.py
- FOUND: api/app/worker/embedding_worker.py
- FOUND: commit de99ae0
- FOUND: commit edaa2c7

---
*Phase: 03-search-discovery*
*Completed: 2026-02-20*
