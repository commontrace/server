---
phase: 02-core-api
plan: "02"
subsystem: api
tags: [detect-secrets, pydantic, httpx, packaging, fastapi, trust-score, pii-scanning]

# Dependency graph
requires:
  - phase: 01-data-foundation
    provides: Trace/Vote/User/Amendment models, TraceStatus enum, Settings config

provides:
  - PII/secrets scanning gate (scanner.py) — SecretDetectedError, scan_content, scan_trace_submission, scan_amendment_submission
  - PyPI staleness checker (staleness.py) — check_library_staleness, check_trace_staleness
  - Trust score and promotion logic (trust.py) — apply_vote_to_trace
  - Pydantic schemas for all endpoints (schemas package) — TraceCreate/Response/Accepted, VoteCreate/Response, AmendmentCreate/Response, APIKeyCreate/Response, ErrorResponse, PaginatedResponse

affects:
  - 02-03-endpoints (consumes all schemas and services directly)
  - 02-04-background-worker (staleness + trust services)
  - 04-reputation-engine (trust.py vote weight pattern)

# Tech tracking
tech-stack:
  added:
    - detect-secrets==1.5.0 (PII/secrets scanning, already in requirements)
    - httpx>=0.27 (async PyPI API calls, already in requirements)
    - packaging>=23.0 (version comparison, already in requirements)
  patterns:
    - enable_eager_search=False for detect-secrets to avoid false positives on descriptive prose
    - Atomic column-expression UPDATE for trust score (no read-modify-write races)
    - model_validator(mode="after") for cross-field schema validation
    - Graceful degradation: staleness check never blocks/fails submission

key-files:
  created:
    - api/app/services/scanner.py
    - api/app/services/staleness.py
    - api/app/services/trust.py
    - api/app/schemas/__init__.py
    - api/app/schemas/common.py
    - api/app/schemas/trace.py
    - api/app/schemas/vote.py
    - api/app/schemas/amendment.py
    - api/app/schemas/auth.py
  modified: []

key-decisions:
  - "detect-secrets enable_eager_search=False: only matches quoted strings and explicit patterns (AWS keys, JWTs), not bare words — eliminates false positives on descriptive prose while catching real credentials"
  - "All three trace fields scanned with same detector set including KeywordDetector — simple and secure, false positives preferable to missed leaks"
  - "Staleness check compares major.minor only (not patch) — patch releases are backwards-compatible bugfixes and don't invalidate trace advice"
  - "apply_vote_to_trace uses separate UPDATE then SELECT for promotion check — safe under one-vote-per-trace unique constraint"
  - "VoteResponse includes feedback_tag field even though Vote model stores it in context_json — endpoints (02-03) handle the mapping"

patterns-established:
  - "scan_content pattern: use _scan_line with enable_eager_search=False inside default_settings() context"
  - "Downvote validation: model_validator(mode='after') checking feedback_tag in DOWNVOTE_REQUIRED_TAGS set"
  - "Trust atomicity: update().values(col=Model.col + delta) with synchronize_session=False"

# Metrics
duration: 4min
completed: 2026-02-20
---

# Phase 2 Plan 02: Service Layer and Schemas Summary

**detect-secrets PII gate (enable_eager_search=False), PyPI staleness checker via httpx, atomic trust-score promotion, and full Pydantic schema suite for all write-path endpoints**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T05:03:03Z
- **Completed:** 2026-02-20T05:07:00Z
- **Tasks:** 2
- **Files modified:** 9 created

## Accomplishments

- PII scanner blocks AWS keys, JWTs, and quoted credential patterns while passing normal descriptive text (enable_eager_search=False key insight)
- PyPI staleness checker with 3s timeout, graceful degradation on all errors, major.minor comparison only
- Atomic trust score updates with column expressions, automatic pending->validated promotion at threshold
- Complete Pydantic schema suite: TraceCreate/Response/Accepted, VoteCreate (downvote enforcement), AmendmentCreate/Response, APIKeyCreate/Response, ErrorResponse, PaginatedResponse

## Task Commits

Each task was committed atomically:

1. **Task 1: PII scanner, staleness checker, and trust service** - `f189d8d` (feat)
2. **Task 2: Pydantic request/response schemas for all endpoints** - `38698a2` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `api/app/services/scanner.py` - SecretDetectedError + scan_content/scan_trace_submission/scan_amendment_submission using detect-secrets
- `api/app/services/staleness.py` - check_library_staleness (PyPI JSON API, major.minor comparison) + check_trace_staleness wrapper
- `api/app/services/trust.py` - apply_vote_to_trace with atomic UPDATE and promotion logic
- `api/app/schemas/__init__.py` - Re-exports all schema classes from app.schemas
- `api/app/schemas/common.py` - ErrorResponse, PaginatedResponse[T]
- `api/app/schemas/trace.py` - TraceCreate (min_length validation, max 20 tags), TraceResponse (from_attributes), TraceAccepted
- `api/app/schemas/vote.py` - VoteCreate with downvote->feedback_tag enforcement via model_validator, DOWNVOTE_REQUIRED_TAGS set
- `api/app/schemas/amendment.py` - AmendmentCreate (explanation max 5000 chars), AmendmentResponse
- `api/app/schemas/auth.py` - APIKeyCreate, APIKeyResponse with "store securely" message

## Decisions Made

- **enable_eager_search=False for detect-secrets:** The default adhoc scan mode (eager) matches every bare word as potential base64 entropy, producing massive false positives on descriptive prose. Using `_scan_line` directly with `enable_eager_search=False` limits detection to quoted strings and explicitly patterned secrets (AWS keys, JWTs, etc.). This is the correct behavior for scanning user-submitted text.
- **All fields with same detector set:** Simpler than per-field filter tuning; false positives (e.g. someone writing `password="hunter2"` in their trace) are correct blocks, not false positives.
- **Major.minor staleness comparison:** Patch versions don't invalidate advice; only major.minor behind counts as stale.
- **VoteResponse.feedback_tag optional with default None:** The Vote ORM model uses `context_json` for this data. The endpoints in 02-03 will serialize correctly; the schema layer only guarantees the field name exists.

## Deviations from Plan

None — plan executed exactly as written.

The one area requiring investigation (detect-secrets false positive behavior) was resolved by using `_scan_line` with `enable_eager_search=False` instead of the higher-level `scan_line` function. This was an implementation detail discovery, not a plan deviation.

## Issues Encountered

- **detect-secrets eager scan false positives:** `scan_line` with `enable_eager_search=True` (adhoc mode) flags every word as "Base64 High Entropy String" because it falls back to non-quoted regex when no quoted matches are found. Resolved by using `_scan_line` with `enable_eager_search=False` directly, which requires quoted strings or specific patterns (AWS keys, JWTs). Verified: AWS key detected, normal prose passes, quoted passwords detected.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All services and schemas ready for Plan 02-03 (HTTP endpoint wiring)
- `scan_trace_submission` and `scan_amendment_submission` are the entry gates for all write operations
- `apply_vote_to_trace` ready to be called from vote endpoint after DB vote record is created
- `check_trace_staleness` ready to be called at trace submission time before DB insert

## Self-Check: PASSED

All 9 created files confirmed present on disk. Both task commits (f189d8d, 38698a2) confirmed in git log.

---
*Phase: 02-core-api*
*Completed: 2026-02-20*
