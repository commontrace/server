---
phase: 04-reputation-engine
plan: "01"
subsystem: api
tags: [wilson-score, reputation, sqlalchemy, pydantic, alembic, tdd, email-validator]

# Dependency graph
requires:
  - phase: 02-core-api
    provides: User model, dependencies.py pattern, trust.py vote logic
  - phase: 03-search-discovery
    provides: trust score re-ranking (wilson_score_lower_bound extends trust.py)

provides:
  - wilson_score_lower_bound() function in trust.py (TDD-tested, 10 tests)
  - ContributorDomainReputation ORM model with unique constraint on (contributor_id, domain_tag)
  - Migration 0003 (d4e5f6a7b8c9) chained after 0002 (c3d4e5f6a7b8)
  - RequireEmail = Annotated[User, Depends(require_email)] — 403 gate for anonymous contributors
  - ReputationResponse and DomainReputationItem Pydantic schemas
  - CDR_UNIQUE_CONSTRAINT module constant for upsert safety

affects:
  - 04-02 (vote flow wiring + read endpoint — consumes all artifacts from this plan)
  - 05-mcp-server (reputation score will influence MCP trace selection)

# Tech tracking
tech-stack:
  added:
    - email-validator==2.3.0 (Pydantic EmailStr validation)
    - dnspython==2.8.0 (transitive dep of email-validator)
  patterns:
    - TDD RED/GREEN commits: test(04-01) commit precedes feat(04-01) commit
    - CDR_UNIQUE_CONSTRAINT module constant for ON CONFLICT DO UPDATE (avoids hardcoding)
    - lazy="raise" on ORM relationships in async context (prevents implicit loads)
    - TYPE_CHECKING import for User in reputation.py (avoids circular import)
    - RequireEmail follows CurrentUser pattern (Annotated type alias, not decorator)

key-files:
  created:
    - api/app/services/trust.py (wilson_score_lower_bound function added above apply_vote_to_trace)
    - api/app/models/reputation.py
    - api/migrations/versions/0003_domain_reputation.py
    - api/app/schemas/reputation.py
    - api/tests/test_wilson_score.py
  modified:
    - api/app/models/__init__.py (added ContributorDomainReputation export)
    - api/app/dependencies.py (added require_email + RequireEmail)
    - api/pyproject.toml (email-validator>=2.3.0 added)

key-decisions:
  - "Wilson score uses z=1.9600 (95% CI) — returns 0.0 for total_votes==0, float in [0,1] otherwise"
  - "CDR_UNIQUE_CONSTRAINT constant defined at module level for safe ON CONFLICT DO UPDATE in plan 04-02"
  - "lazy='raise' on ContributorDomainReputation.contributor — prevents implicit async loading"
  - "RequireEmail raises 403 (not 401) — user is authenticated but lacks identity cost"
  - "email-validator installed as uv add (not optional dependency) — required for Pydantic EmailStr"

patterns-established:
  - "Wilson score: wilson_score_lower_bound(upvotes, total_votes) -> float, 0.0 for no data"
  - "Reputation schema: ReputationResponse(user_id, overall_wilson_score, domains: list[DomainReputationItem])"
  - "Identity gate: RequireEmail alias used in endpoint signature like CurrentUser"

# Metrics
duration: 8min
completed: 2026-02-20
---

# Phase 4 Plan 01: Reputation Engine Foundation Summary

**Wilson score lower bound (TDD, 10 tests), ContributorDomainReputation model + migration 0003, RequireEmail 403 gate, and ReputationResponse/DomainReputationItem schemas**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-20T06:39:00Z
- **Completed:** 2026-02-20T06:47:23Z
- **Tasks:** 1 (with TDD RED + GREEN sub-phases + non-TDD artifacts)
- **Files modified:** 8

## Accomplishments

- Wilson score lower bound formula implemented and verified with 10 TDD tests (RED/GREEN protocol)
- ContributorDomainReputation ORM model with unique constraint, CDR_UNIQUE_CONSTRAINT constant, lazy="raise" relationship
- Migration 0003 chained from 0002 with all columns, indexes (ix_cdr_contributor_id, ix_cdr_domain_tag)
- RequireEmail dependency raises 403 if user.email is None — identity cost gate for write paths
- ReputationResponse and DomainReputationItem schemas importable and ready for Plan 04-02

## Task Commits

Each sub-phase committed atomically:

1. **TDD RED: Wilson score failing tests** - `a311417` (test) — pre-existing commit from plan setup
2. **TDD GREEN: Wilson score implementation** - `5100b04` (feat)
3. **Non-TDD artifacts: model, migration, RequireEmail, schemas** - `b180240` (feat)

## Files Created/Modified

- `api/app/services/trust.py` - Added wilson_score_lower_bound() above apply_vote_to_trace
- `api/tests/test_wilson_score.py` - 10 TDD tests (zero guard, sample size, return type, known value)
- `api/app/models/reputation.py` - ContributorDomainReputation ORM model + CDR_UNIQUE_CONSTRAINT
- `api/app/models/__init__.py` - Added ContributorDomainReputation to imports and __all__
- `api/migrations/versions/0003_domain_reputation.py` - Manual migration chained from c3d4e5f6a7b8
- `api/app/dependencies.py` - Added require_email() + RequireEmail alias after CurrentUser
- `api/app/schemas/reputation.py` - ReputationResponse + DomainReputationItem Pydantic schemas
- `api/pyproject.toml` - email-validator>=2.3.0 added

## Decisions Made

- Wilson score uses z=1.9600 (95% CI) per Evan Miller formula; returns 0.0 when total_votes==0
- CDR_UNIQUE_CONSTRAINT module constant avoids hardcoding constraint name in upsert code (Plan 04-02)
- lazy="raise" on ContributorDomainReputation.contributor prevents accidental implicit loading in async context
- RequireEmail raises 403 (not 401) because the user is authenticated but lacks the identity cost email requirement
- email-validator installed as a direct uv dependency (not optional) since EmailStr usage is core to reputation schema

## Deviations from Plan

None - plan executed exactly as written. The test file (test_wilson_score.py) was already committed as the RED phase in a prior run, and trust.py had only partial changes (import math + docstring). GREEN phase was applied and committed cleanly.

## Issues Encountered

- `test_wilson_score.py` already existed with `a311417` commit — RED phase was already done before this execution. Plan continued from GREEN phase.
- `trust.py` had staged changes (only `import math` and docstring update) — these were incorporated into the GREEN commit.
- `uv.lock` is in repo root (not `api/`) — path corrected during staging.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All foundation artifacts for Plan 04-02 are ready:
  - `wilson_score_lower_bound()` available in trust.py for vote-time score computation
  - `ContributorDomainReputation` model + migration ready for upsert in vote flow
  - `RequireEmail` ready to apply to POST /api/v1/traces and POST /api/v1/votes
  - `ReputationResponse` schema ready for GET /api/v1/reputation/{user_id}
- No blockers.

---
*Phase: 04-reputation-engine*
*Completed: 2026-02-20*

## Self-Check: PASSED

All files found, all commits verified:
- FOUND: api/app/services/trust.py
- FOUND: api/tests/test_wilson_score.py
- FOUND: api/app/models/reputation.py
- FOUND: api/migrations/versions/0003_domain_reputation.py
- FOUND: api/app/schemas/reputation.py
- FOUND: api/app/dependencies.py
- FOUND: a311417 (test RED)
- FOUND: 5100b04 (feat GREEN)
- FOUND: b180240 (feat artifacts)
