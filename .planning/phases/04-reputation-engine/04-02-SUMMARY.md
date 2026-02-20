---
phase: 04-reputation-engine
plan: "02"
subsystem: api
tags: [reputation, wilson-score, vote-weight, sqlalchemy, postgresql, domain-reputation, fastapi]

# Dependency graph
requires:
  - phase: 04-01
    provides: wilson_score_lower_bound, ContributorDomainReputation model, CDR_UNIQUE_CONSTRAINT, RequireEmail, ReputationResponse schema
  - phase: 02-core-api
    provides: trust.py apply_vote_to_trace, CurrentUser/DbSession patterns, vote router structure
  - phase: 01-data-foundation
    provides: Tag model, trace_tags join table, User model with reputation_score

provides:
  - get_vote_weight_for_trace() in trust.py — domain-aware vote weight from max wilson_score across trace tags
  - update_contributor_domain_reputation() in trust.py — atomic UPSERT of per-domain rows + aggregate users.reputation_score
  - BASE_WEIGHT=0.1 constant for new-contributor vote floor (8:1 difference vs established contributor)
  - POST /api/v1/traces gated by RequireEmail (403 without email)
  - POST /api/v1/traces/{id}/votes gated by RequireEmail with domain-weighted vote_weight
  - POST /api/v1/traces/{id}/amendments gated by RequireEmail
  - GET /api/v1/contributors/{user_id}/reputation — overall wilson_score + per-domain breakdown

affects:
  - 04-03 (if any remaining reputation plan depends on vote flow)
  - 05-mcp-server (reputation scores now update on every vote, MCP can use them for trace selection)

# Tech tracking
tech-stack:
  added:
    - sqlalchemy.dialects.postgresql.insert (pg_insert) — used for ON CONFLICT DO UPDATE upsert pattern
    - sqlalchemy.func — used for SUM aggregation in aggregate wilson_score computation
  patterns:
    - Domain-aware vote weight: max wilson_score across voter's domain rows matching trace tags, fallback to BASE_WEIGHT
    - Atomic UPSERT: pg_insert().on_conflict_do_update() with RETURNING for immediate recompute
    - Two-phase reputation update: per-domain upsert then aggregate SUM re-computation in same transaction
    - RequireEmail gate applied to POST endpoints, CurrentUser kept on GET endpoints

key-files:
  created:
    - api/app/routers/reputation.py (GET /api/v1/contributors/{user_id}/reputation endpoint)
  modified:
    - api/app/services/trust.py (get_vote_weight_for_trace, update_contributor_domain_reputation, BASE_WEIGHT)
    - api/app/routers/votes.py (RequireEmail, tag fetch, domain vote weight, domain reputation update)
    - api/app/routers/traces.py (RequireEmail on submit_trace)
    - api/app/routers/amendments.py (RequireEmail on submit_amendment)
    - api/app/main.py (reputation router registered)

key-decisions:
  - "get_vote_weight_for_trace uses max() across matching domain scores — a voter with Python expertise gets their best domain score on Python traces"
  - "Untagged traces fall back to users.reputation_score (global Wilson score) — domain-agnostic traces use global reputation"
  - "update_contributor_domain_reputation is a no-op when domain_tags is empty — no phantom rows created for untagged traces"
  - "Reputation read endpoint uses CurrentUser not RequireEmail — reading another contributor's reputation does not require email identity cost"
  - "Aggregate users.reputation_score recomputed via SUM across all CDR rows in same transaction as the upsert — always consistent"

patterns-established:
  - "Vote flow order: RequireEmail -> WriteRateLimit -> trace lookup -> tag fetch -> self-vote check -> Vote INSERT + flush -> get_vote_weight_for_trace -> apply_vote_to_trace -> update_contributor_domain_reputation -> db.commit()"
  - "Domain upsert pattern: pg_insert().on_conflict_do_update(constraint=CDR_UNIQUE_CONSTRAINT).returning(...) — safe, idempotent, constraint-name from module constant"
  - "RequireEmail on writes, CurrentUser on reads — consistent access pattern across all routers"

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 4 Plan 02: Reputation Engine Wiring Summary

**Domain-aware vote weight (max wilson_score across trace tags), per-domain reputation UPSERT on each vote, RequireEmail gating all write endpoints, and GET /api/v1/contributors/{user_id}/reputation endpoint**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-20T06:50:14Z
- **Completed:** 2026-02-20T06:52:57Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Two new trust service functions: `get_vote_weight_for_trace` (returns max domain wilson_score or BASE_WEIGHT=0.1) and `update_contributor_domain_reputation` (atomic UPSERT via ON CONFLICT DO UPDATE + aggregate recompute)
- Vote flow now fully domain-aware: tag fetch -> domain weight lookup -> apply_vote_to_trace -> update_contributor_domain_reputation, all in one transaction
- All three write endpoints (POST traces, votes, amendments) gated by RequireEmail; read endpoints keep CurrentUser
- New reputation router with GET /api/v1/contributors/{user_id}/reputation returning overall_wilson_score + per-domain list ordered by score descending
- Requirements fulfilled: CONT-03, REPU-01, REPU-02, REPU-03

## Task Commits

Each task was committed atomically:

1. **Task 1: Domain reputation update + vote weight functions in trust service** - `78e8bd8` (feat)
2. **Task 2: Wire RequireEmail + domain vote weight into routers + reputation endpoint + router registration** - `ad15cd3` (feat)

## Files Created/Modified

- `api/app/services/trust.py` - Added BASE_WEIGHT=0.1, get_vote_weight_for_trace(), update_contributor_domain_reputation(); added func, pg_insert, CDR_UNIQUE_CONSTRAINT, ContributorDomainReputation, User imports
- `api/app/routers/votes.py` - RequireEmail replaces CurrentUser, tag fetch added, domain-aware vote_weight, update_contributor_domain_reputation call after apply_vote_to_trace
- `api/app/routers/traces.py` - RequireEmail applied to submit_trace; get_trace keeps CurrentUser
- `api/app/routers/amendments.py` - RequireEmail applied to submit_amendment
- `api/app/routers/reputation.py` - New file: GET /api/v1/contributors/{user_id}/reputation with 404 on missing user, per-domain rows ordered by wilson_score desc
- `api/app/main.py` - reputation router imported and registered after search router

## Decisions Made

- `get_vote_weight_for_trace` uses `max()` across matching domain scores — a voter with strong Python reputation gets their peak score on Python traces, not an average
- Untagged traces fall back to `users.reputation_score` (global Wilson score) — semantically correct since untagged traces are not domain-specific
- `update_contributor_domain_reputation` is a no-op when `domain_tags` is empty — avoids creating phantom rows for untagged trace votes
- Reputation read endpoint uses `CurrentUser` not `RequireEmail` — reading reputation is informational, not a contribution action
- `users.reputation_score` always recomputed as SUM-based aggregate in the same transaction as the domain upsert — no eventual consistency delay

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all imports resolved cleanly. `python` binary not in PATH; `uv run python` used instead (consistent with project convention).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Reputation engine is fully operational: domain-weighted votes, per-domain tracking, aggregate score, identity cost gate, read endpoint
- CONT-03, REPU-01, REPU-02, REPU-03 all fulfilled
- Phase 5 (MCP server) can query `users.reputation_score` and `contributor_domain_reputation` for trace selection ranking
- No blockers.

---
*Phase: 04-reputation-engine*
*Completed: 2026-02-20*

## Self-Check: PASSED

All files found, all commits verified:
- FOUND: api/app/services/trust.py
- FOUND: api/app/routers/votes.py
- FOUND: api/app/routers/traces.py
- FOUND: api/app/routers/amendments.py
- FOUND: api/app/routers/reputation.py
- FOUND: api/app/main.py
- FOUND: .planning/phases/04-reputation-engine/04-02-SUMMARY.md
- FOUND: 78e8bd8 (feat Task 1)
- FOUND: ad15cd3 (feat Task 2)
