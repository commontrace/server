---
phase: 05-mcp-server
plan: 01
subsystem: api
tags: [fastmcp, httpx, pydantic-settings, mcp, python, docker]

requires:
  - phase: 04-reputation-engine
    provides: trust score infrastructure that MCP tools expose via search results
  - phase: 03-search-discovery
    provides: POST /api/v1/traces/search endpoint consumed by search_traces tool
  - phase: 02-core-api
    provides: POST /traces, GET /traces/{id}, POST /votes endpoints

provides:
  - FastMCP 3.0.0 server with 5 tool definitions (search_traces, contribute_trace, vote_trace, get_trace, list_tags)
  - BackendClient wrapping httpx.AsyncClient with API key forwarding
  - MCPSettings via pydantic-settings with SLA timeouts and transport config
  - GET /api/v1/tags endpoint returning distinct tag names from the database
  - mcp-server/Dockerfile for containerized deployment
  - mcp-server service in docker-compose.yml on port 8080

affects:
  - 05-02-circuit-breaker (adds resilience on top of BackendClient)
  - 06-skill-layer (consumes MCP server as protocol transport)

tech-stack:
  added:
    - fastmcp==3.0.0
    - pydantic-settings>=2.0.0
    - structlog>=24.0
    - httpx (transitive via fastmcp)
  patterns:
    - MCP as thin protocol adapter (no business logic — backend HTTP calls only)
    - API key forwarded from MCP client headers with env var fallback for stdio
    - Format functions convert JSON to agent-readable strings (not dicts)
    - Module-level singleton BackendClient (shared across tool invocations)
    - Error handling returns format_error strings (session-safe, no crashes)

key-files:
  created:
    - mcp-server/app/server.py
    - mcp-server/app/backend_client.py
    - mcp-server/app/config.py
    - mcp-server/app/formatters.py
    - mcp-server/app/__main__.py
    - mcp-server/app/__init__.py
    - mcp-server/Dockerfile
    - api/app/routers/tags.py
  modified:
    - api/app/main.py
    - mcp-server/pyproject.toml
    - docker-compose.yml

key-decisions:
  - "FastMCP 3.0.0 tool decorator syntax verified before implementation — CurrentHeaders() in fastmcp.dependencies"
  - "format_* functions return strings not dicts — MCP tools return str for direct agent readability"
  - "BackendClient has no circuit breaker yet — Plan 05-02 adds it; kept simple for this plan"
  - "GET /api/v1/tags uses CurrentUser not RequireEmail — read operation, not a write contribution"
  - "docker-compose uses service_started not service_healthy for api dependency — circuit breaker handles backend unavailability"
  - "Error handling catches httpx.HTTPStatusError and generic httpx.HTTPError separately for precise error messages"

patterns-established:
  - "MCP tool pattern: extract API key → call backend → format result → catch httpx errors → return string"
  - "Formatter pattern: one format_* function per tool output type, input is raw API dict, output is agent-readable string"
  - "BackendClient singleton: instantiated at module level, reused across all tool invocations"

duration: 8min
completed: 2026-02-20
---

# Phase 5 Plan 1: MCP Server Foundation Summary

**FastMCP 3.0.0 server with 5 tools bridging MCP protocol to CommonTrace REST API, plus GET /api/v1/tags endpoint and Docker Compose service**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T20:41:05Z
- **Completed:** 2026-02-20T20:49:05Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Created FastMCP 3.0.0 server with 5 tool definitions — each maps to a backend HTTP endpoint with SLA-driven timeouts (200ms read, 2s write)
- Added GET /api/v1/tags endpoint to the FastAPI backend returning distinct tag names ordered alphabetically
- Created BackendClient wrapping httpx.AsyncClient with connection pooling and per-request API key forwarding

## Task Commits

Each task was committed atomically:

1. **Task 1: GET /api/v1/tags endpoint + MCP server skeleton** - `902db42` (feat)
2. **Task 2: Five MCP tools, formatters, entrypoints, and Docker Compose** - `c696d82` (feat)

**Plan metadata:** (docs commit — created after self-check)

## Files Created/Modified

- `mcp-server/app/server.py` - FastMCP instance with 5 @mcp.tool definitions and /health custom route
- `mcp-server/app/backend_client.py` - BackendClient wrapping httpx.AsyncClient, module-level singleton
- `mcp-server/app/config.py` - MCPSettings with API URL, transport config, SLA timeouts, circuit breaker params
- `mcp-server/app/formatters.py` - format_search_results, format_trace, format_contribution_result, format_vote_result, format_tags, format_error
- `mcp-server/app/__main__.py` - Entrypoint for `python -m app`
- `mcp-server/app/__init__.py` - Empty package marker
- `mcp-server/Dockerfile` - Docker image following api/Dockerfile pattern
- `api/app/routers/tags.py` - GET /api/v1/tags endpoint using existing auth/rate-limit deps
- `api/app/main.py` - Added tags router import and include_router call
- `mcp-server/pyproject.toml` - Updated with fastmcp>=3.0.0, pydantic-settings, structlog
- `docker-compose.yml` - Added mcp-server service on port 8080

## Decisions Made

- FastMCP 3.0.0 API was verified before writing — `CurrentHeaders()` is in `fastmcp.dependencies`, tool annotations use `{"readOnlyHint": True}` dict syntax
- All format functions return strings, not dicts — MCP tools returning strings is idiomatic for direct agent consumption
- BackendClient has no circuit breaker — Plan 05-02 adds it; kept methods simple (direct httpx, no try/except wrapping inside the client)
- GET /api/v1/tags uses `CurrentUser` (not `RequireEmail`) — listing tags is informational, no identity cost required
- docker-compose uses `service_started` not `service_healthy` for the API dependency — circuit breaker (Plan 05-02) handles backend unavailability at runtime

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — FastMCP 3.0.0 API matched the plan spec. The `=3.0.0` file in mcp-server/ was a leftover artifact from a botched pip command (not created in this plan), left as-is since it does not affect functionality.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MCP server foundation is complete and importable — `from app.server import mcp` works
- BackendClient is ready for circuit breaker wrapping in Plan 05-02
- MCPSettings already includes `circuit_failure_threshold` and `circuit_recovery_timeout` fields for Plan 05-02
- All 5 tools have correct error handling patterns that Plan 05-02 can layer circuit breaker on top of

## Self-Check: PASSED

All 9 created files found on disk. Both task commits verified in git log (902db42, c696d82).

---
*Phase: 05-mcp-server*
*Completed: 2026-02-20*
