---
phase: 05-mcp-server
plan: 02
subsystem: api
tags: [fastmcp, httpx, circuit-breaker, resilience, python, mcp]

requires:
  - phase: 05-01
    provides: BackendClient singleton and 5 MCP tool definitions to wrap with circuit breaker

provides:
  - CircuitBreaker class with closed/open/half-open states and configurable threshold/recovery
  - CircuitOpenError and BackendUnavailableError exception classes
  - BackendClient.post() and .get() wrapped with self.breaker.call() for all requests
  - 5 MCP tools each catching CircuitOpenError, BackendUnavailableError, httpx.HTTPStatusError, and generic Exception
  - Distinct degradation messages: read tools say "Continuing without results", write tools say "Please try again later"
  - 4xx responses do NOT trip circuit breaker — only 5xx, timeouts, and connection errors do

affects:
  - 06-skill-layer (consumes MCP server; circuit breaker ensures agent sessions survive backend outages)

tech-stack:
  added: []
  patterns:
    - Circuit breaker pattern: closed/open/half-open state machine with asyncio.wait_for for timeout enforcement
    - Graceful degradation: every tool returns human-readable string on all failure modes (never raises)
    - Selective circuit tripping: 4xx client errors handled outside circuit; 5xx manually trip it via _on_failure()
    - Error message differentiation: read vs write tools have distinct messages reflecting data loss implications

key-files:
  created: []
  modified:
    - mcp-server/app/backend_client.py
    - mcp-server/app/server.py

key-decisions:
  - "CircuitBreaker is custom async implementation using asyncio.wait_for — no third-party library needed"
  - "4xx errors raise httpx.HTTPStatusError OUTSIDE circuit breaker — client errors do not count as backend failures"
  - "5xx errors manually call self.breaker._on_failure() after returning response — server errors trip circuit without double-counting"
  - "half-open state allows exactly one probe; _on_success() resets to closed, _on_failure() re-opens"
  - "Read tool degradation: 'Continuing without results' — agent moves on, no data loss risk"
  - "Write tool degradation: 'Please try again later' — agent knows submission was NOT recorded"

patterns-established:
  - "Circuit breaker pattern: call(coroutine, timeout) wraps every async HTTP call — timeout + error in one step"
  - "Graceful degradation: except CircuitOpenError -> except BackendUnavailableError -> except HTTPStatusError -> except Exception"
  - "5xx handling: check resp.status_code >= 500 after breaker.call(), call _on_failure() manually, raise BackendUnavailableError"

duration: 3min
completed: 2026-02-20
---

# Phase 5 Plan 2: Circuit Breaker and Graceful Degradation Summary

**Async circuit breaker protecting all 5 MCP tools from backend outages, with human-readable degradation strings replacing every error path so agent sessions never crash**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T20:46:45Z
- **Completed:** 2026-02-20T20:49:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added CircuitBreaker class with closed/open/half-open state machine — opens after 5 failures, recovers after 30s, half-open allows one probe
- Wrapped BackendClient.post() and .get() with `self.breaker.call()` enforcing per-operation SLA timeouts via asyncio.wait_for
- Updated all 5 MCP tools with four-layer exception handling: CircuitOpenError → BackendUnavailableError → httpx.HTTPStatusError → Exception
- Differentiated degradation messages for read tools ("Continuing without results") vs write tools ("Please try again later")
- 4xx errors correctly skip circuit tripping; only 5xx, timeouts, and connection errors count as circuit failures

## Task Commits

Each task was committed atomically:

1. **Task 1: CircuitBreaker class and circuit-protected BackendClient** - `67c8594` (feat)
2. **Task 2: Graceful degradation in all MCP tools and API key injection verification** - `fa34ce0` (feat)

**Plan metadata:** (docs commit — created after self-check)

## Files Created/Modified

- `mcp-server/app/backend_client.py` - Added CircuitOpenError, BackendUnavailableError, CircuitBreaker class; updated BackendClient with circuit-wrapped post/get methods
- `mcp-server/app/server.py` - Updated all 5 tools with CircuitOpenError/BackendUnavailableError/HTTPStatusError/Exception catches returning degradation strings

## Decisions Made

- CircuitBreaker implemented as a custom class (no third-party library) — asyncio.wait_for handles the timeout, a simple counter handles state transitions
- 4xx errors are client errors and must NOT trip the circuit breaker; the fix is to return the raw response from inside the circuit, check status_code >= 500 outside, and call `_on_failure()` manually for server errors
- Read tool messages end with "Continuing without results" to signal the agent can proceed; write tool messages end with "Please try again later" to signal the submission was not saved
- half-open state resets to closed on first success (via `_on_success`) and re-opens on first failure (via `_on_failure` which increments past threshold)

## Deviations from Plan

None - plan executed exactly as written. The 4xx/5xx handling revision was included in the plan itself (the "REVISED approach" section).

## Issues Encountered

The plan's verification test for `_extract_api_key` had a timing issue (sets env var after module import, so settings object was already instantiated with empty value). The function itself is correct — when `COMMONTRACE_API_KEY` is set before server import, the fallback works as designed. Verified with correct ordering.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MCP server is now fully resilient — no backend failure can crash an agent session
- Circuit breaker is configurable via `CIRCUIT_FAILURE_THRESHOLD` and `CIRCUIT_RECOVERY_TIMEOUT` env vars
- Phase 5 is complete — ready for Phase 6 (skill layer) which will consume the MCP server as transport
- All must-have truths from plan verified: degradation strings, circuit state transitions, SLA timeouts, API key injection

## Self-Check: PASSED

- `mcp-server/app/backend_client.py` found on disk
- `mcp-server/app/server.py` found on disk
- Task 1 commit `67c8594` verified in git log
- Task 2 commit `fa34ce0` verified in git log

---
*Phase: 05-mcp-server*
*Completed: 2026-02-20*
