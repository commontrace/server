---
phase: 08-tech-debt-cleanup
plan: 01
subsystem: mcp-server
tags: [fastmcp, httpx, circuit-breaker, mcp-tools, async]

# Dependency graph
requires:
  - phase: 05-mcp-server
    provides: MCP server with 5 tools, BackendClient with CircuitBreaker, formatters
provides:
  - amend_trace MCP tool (POST /api/v1/traces/{id}/amendments)
  - format_amendment_result formatter
  - httpx explicit dependency in pyproject.toml
  - CircuitBreaker.call() accepts coroutine factory (no RuntimeWarning when open)
affects: [mcp-server, 08-tech-debt-cleanup]

# Tech tracking
tech-stack:
  added: [httpx>=0.27 (explicit, was transitive)]
  patterns:
    - Pass coroutine factory (zero-arg callable) to circuit breaker instead of pre-created coroutine

key-files:
  created: []
  modified:
    - mcp-server/app/formatters.py
    - mcp-server/app/server.py
    - mcp-server/pyproject.toml
    - mcp-server/app/backend_client.py

key-decisions:
  - "CircuitBreaker.call() takes coro_factory (callable) not coro (coroutine) — prevents unawaited coroutine creation when circuit is open"
  - "httpx declared as explicit dependency (>=0.27) — not relying on transitive availability through fastmcp"
  - "amend_trace follows vote_trace pattern exactly: readOnlyHint False, 2s write_timeout, same error handling structure"

patterns-established:
  - "Coroutine factory pattern: pass _request (the function) not _request() (the result) to circuit breaker"

# Metrics
duration: 3min
completed: 2026-02-21
---

# Phase 8 Plan 01: MCP Server Tech Debt Cleanup Summary

**Added amend_trace as 6th MCP tool (POST /api/v1/traces/{id}/amendments), declared httpx as explicit dependency, and fixed unawaited coroutine RuntimeWarning in circuit breaker via factory pattern**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-21T03:26:05Z
- **Completed:** 2026-02-21T03:29:54Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added `amend_trace` MCP tool giving agents a way to propose improved solutions to existing traces — brings tool count from 5 to 6, matching all 6 backend write/read operations
- Added `format_amendment_result` formatter in formatters.py following the `format_contribution_result` pattern
- Declared `httpx>=0.27` as an explicit dependency in pyproject.toml (was previously available only transitively through fastmcp)
- Fixed `CircuitBreaker.call()` to accept a coroutine factory instead of a pre-created coroutine, eliminating the "coroutine was never awaited" RuntimeWarning when the circuit is open

## Task Commits

Each task was committed atomically:

1. **Task 1: Add amend_trace MCP tool with formatter and httpx dependency** - `62d1281` (feat)
2. **Task 2: Fix unawaited coroutine warning in circuit breaker** - `6d22ae8` (fix)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `mcp-server/app/formatters.py` - Added `format_amendment_result` function
- `mcp-server/app/server.py` - Updated docstring to six tools, added `amend_trace` import and tool definition, updated FastMCP instructions
- `mcp-server/pyproject.toml` - Added `httpx>=0.27` as explicit dependency
- `mcp-server/app/backend_client.py` - Changed `CircuitBreaker.call()` parameter from `coro` to `coro_factory`, updated both call sites to pass `_request` not `_request()`

## Decisions Made
- `CircuitBreaker.call()` takes `coro_factory` (zero-arg callable) not `coro` (coroutine) — prevents the coroutine from being created at all when circuit is open, eliminating the RuntimeWarning entirely
- httpx declared as explicit dependency at `>=0.27` rather than pinning a specific version, matching the style of other deps
- `amend_trace` follows `vote_trace` pattern exactly for consistency: `readOnlyHint: False`, `settings.write_timeout`, same error handling structure

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- Plan verification commands used `python` which is not on PATH (only `python3` and `uv run python`). Ran commands via `uv run python` after running `uv sync` to create the virtualenv. Not a code issue, just an environment detail.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- All 3 tech debt items closed: amend_trace tool, explicit httpx dep, circuit breaker warning
- MCP server now has complete tool coverage (6 tools for 6 API operations)
- Ready for remaining 08-tech-debt-cleanup plans

---
*Phase: 08-tech-debt-cleanup*
*Completed: 2026-02-21*

## Self-Check: PASSED

- FOUND: mcp-server/app/formatters.py
- FOUND: mcp-server/app/server.py
- FOUND: mcp-server/pyproject.toml
- FOUND: mcp-server/app/backend_client.py
- FOUND: .planning/phases/08-tech-debt-cleanup/08-01-SUMMARY.md
- FOUND: task1 commit 62d1281
- FOUND: task2 commit 6d22ae8
