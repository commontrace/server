---
phase: 04-reputation-engine
verified: 2026-02-20T07:30:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Cast a vote on a tagged trace and confirm domain reputation row created"
    expected: "contributor_domain_reputation row appears with correct domain_tag, upvote_count=1, and wilson_score > 0"
    why_human: "Requires live PostgreSQL database with migration applied; cannot verify UPSERT behavior without DB"
  - test: "Cast a vote without email registration (API key created without email)"
    expected: "POST /api/v1/traces/{id}/votes returns 403 with 'Email registration required' message"
    why_human: "Requires live HTTP request with authenticated user lacking email"
---

# Phase 04: Reputation Engine Verification Report

**Phase Goal:** Agent contributions earn trust over time, high-reputation votes carry more weight, and reputation is tracked per domain so a Python expert's vote on a Python trace matters more than a stranger's
**Verified:** 2026-02-20T07:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Each contributor has a trust score computed via Wilson score confidence interval — a trace with one upvote does not outrank a trace with 50 upvotes and 5 downvotes | VERIFIED | `wilson_score_lower_bound` in `trust.py`: `wilson(1,1)=0.2065`, `wilson(50,55)=0.8042`. 10 TDD tests all pass. Formula: 95% CI lower bound using z=1.9600. Zero-vote guard returns 0.0. |
| 2 | A new contributor's first vote counts less than a vote from a contributor with established reputation — the weight difference is measurable and documented | VERIFIED | `BASE_WEIGHT=0.1` defined in `trust.py` (line 127). `get_vote_weight_for_trace` returns `BASE_WEIGHT` for unmatched domains. An established contributor with `wilson_score=0.8` has exactly 8x the vote influence of a new contributor (8:1 ratio documented in code comment). |
| 3 | Registering with an email address is required to establish a contributor identity — anonymous API key usage without email registration cannot submit contributions | VERIFIED | `require_email` dependency in `dependencies.py` raises `HTTPException(status_code=403)` when `user.email is None`. `RequireEmail` alias applied to: POST /api/v1/traces (line 28), POST /api/v1/traces/{id}/votes (line 35), POST /api/v1/traces/{id}/amendments (line 29). GET endpoints keep `CurrentUser` (no email requirement). |
| 4 | A contributor's reputation is tracked separately by domain context (e.g., Python, JavaScript) — high Python reputation does not automatically grant high JavaScript reputation | VERIFIED | `ContributorDomainReputation` table with `UniqueConstraint(['contributor_id', 'domain_tag'])`. One row per (contributor, domain_tag) pair. `get_vote_weight_for_trace` queries only rows matching `trace_tags`. Python and JavaScript reputation stored in separate rows; querying max wilson_score across matching tags only. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/services/trust.py` | Wilson score lower bound + domain reputation functions + BASE_WEIGHT | VERIFIED | Contains `wilson_score_lower_bound`, `get_vote_weight_for_trace`, `update_contributor_domain_reputation`, `BASE_WEIGHT=0.1`. All functions importable. |
| `api/app/models/reputation.py` | ContributorDomainReputation ORM model | VERIFIED | `class ContributorDomainReputation` with `UniqueConstraint(contributor_id, domain_tag)`, `CDR_UNIQUE_CONSTRAINT` constant, `lazy="raise"` relationship. Tablename: `contributor_domain_reputation`. |
| `api/app/dependencies.py` | RequireEmail dependency alias | VERIFIED | `require_email` function raises 403 when `user.email is None`. `RequireEmail = Annotated[User, Depends(require_email)]`. Confirmed raises 403 in live test. |
| `api/app/schemas/reputation.py` | ReputationResponse and DomainReputationItem schemas | VERIFIED | Both classes exist and are instantiable. `ReputationResponse` uses `ConfigDict(from_attributes=True)`. Per-domain breakdown via `domains: list[DomainReputationItem]`. |
| `api/migrations/versions/0003_domain_reputation.py` | Alembic migration for contributor_domain_reputation table | VERIFIED | `revision="d4e5f6a7b8c9"`, `down_revision="c3d4e5f6a7b8"` (chains correctly from migration 0002). Creates table with all expected columns, two indexes, unique constraint. |
| `api/app/routers/votes.py` | Vote endpoint with RequireEmail, domain vote weight, reputation update | VERIFIED | `RequireEmail` on cast_vote. Full wiring: tag fetch → `get_vote_weight_for_trace` → `apply_vote_to_trace` → `update_contributor_domain_reputation` → `db.commit()`. |
| `api/app/routers/reputation.py` | GET /api/v1/contributors/{user_id}/reputation endpoint | VERIFIED | Endpoint exists, selects from `ContributorDomainReputation`, returns `ReputationResponse` with per-domain breakdown ordered by wilson_score desc. |
| `api/app/routers/traces.py` | Trace submission gated by RequireEmail | VERIFIED | `user: RequireEmail` on `submit_trace`. `get_trace` keeps `CurrentUser` (correct — reads don't require email). |
| `api/app/routers/amendments.py` | Amendment submission gated by RequireEmail | VERIFIED | `user: RequireEmail` on `submit_amendment`. |
| `api/app/main.py` | Reputation router registered | VERIFIED | `from app.routers import amendments, auth, moderation, reputation, search, traces, votes`. `app.include_router(reputation.router)` present. Route `/api/v1/contributors/{user_id}/reputation` confirmed registered. |
| `api/app/models/__init__.py` | ContributorDomainReputation exported | VERIFIED | `from .reputation import ContributorDomainReputation` and in `__all__`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `trust.py` | `models/reputation.py` | `pg_insert(ContributorDomainReputation).on_conflict_do_update(constraint=CDR_UNIQUE_CONSTRAINT)` | WIRED | Lines 199-214 in trust.py: full UPSERT with RETURNING, followed by wilson_score recompute. |
| `models/__init__.py` | `models/reputation.py` | `from .reputation import ContributorDomainReputation` | WIRED | Line 7 in `__init__.py`; also in `__all__`. |
| `routers/votes.py` | `trust.py` | `get_vote_weight_for_trace` called before `apply_vote_to_trace` | WIRED | Lines 97-106: domain-aware weight retrieved, then passed to `apply_vote_to_trace`. |
| `routers/votes.py` | `trust.py` | `update_contributor_domain_reputation` called after `apply_vote_to_trace` | WIRED | Lines 110-115: called with `contributor_id`, `domain_tags`, `is_upvote`. |
| `routers/reputation.py` | `models/reputation.py` | `select(ContributorDomainReputation).where(...).order_by(wilson_score.desc())` | WIRED | Lines 43-47 in reputation.py: full SELECT with filtering and ordering. |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|---------|
| REPU-01: Trust score via Wilson score interval | SATISFIED | `wilson_score_lower_bound` implemented, TDD-tested (10 tests pass), integrated into vote flow and domain reputation UPSERT |
| REPU-02: Email required for identity cost | SATISFIED | `RequireEmail` raises 403 when email is None; applied to all three write endpoints (traces, votes, amendments) |
| REPU-03: Per-domain reputation tracking | SATISFIED | `ContributorDomainReputation` table with unique constraint on `(contributor_id, domain_tag)`; separate rows per domain; vote weight from matching domain scores only |
| CONT-03: Vote impact weighted by reputation | SATISFIED | `get_vote_weight_for_trace` returns max domain wilson_score or `BASE_WEIGHT=0.1`; `apply_vote_to_trace` receives this weight as `vote_weight` parameter |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `api/app/routers/traces.py` | 35 | Docstring says "1. Authentication (CurrentUser dependency)" but `submit_trace` uses `RequireEmail` | Info | Misleading comment only; actual code is correct — `RequireEmail` is applied. No functional impact. |

### Human Verification Required

#### 1. Database: Domain reputation row creation on vote

**Test:** Create two users (one with email, one without). Have user A submit a Python-tagged trace. Have user B (with email) vote on it. Inspect the `contributor_domain_reputation` table.
**Expected:** One row with `contributor_id=user_A.id`, `domain_tag='python'`, `upvote_count=1`, `wilson_score > 0`.
**Why human:** Requires live PostgreSQL with migration 0003 applied. The UPSERT logic in `update_contributor_domain_reputation` is correct in code but can only be confirmed as working against a real DB.

#### 2. HTTP: 403 for email-less contributor on write endpoints

**Test:** Register an API key without providing an email address. Attempt POST /api/v1/traces, POST /api/v1/traces/{id}/votes, POST /api/v1/traces/{id}/amendments with that key.
**Expected:** All three return HTTP 403 with message "Email registration required to submit contributions."
**Why human:** Requires live HTTP server and DB-backed auth flow to confirm the gate fires correctly end-to-end.

### Gaps Summary

No gaps. All four observable truths are verified. All ten artifacts pass all three levels (exists, substantive, wired). All four key links are confirmed wired with actual code patterns. All four requirements (REPU-01, REPU-02, REPU-03, CONT-03) are satisfied.

The one anti-pattern found (docstring says `CurrentUser` but code correctly uses `RequireEmail` in `traces.py`) is informational only — it is a stale comment in the docstring body, not in the function signature, and does not affect runtime behavior.

Two items are flagged for human verification because they require a live database and HTTP server to confirm end-to-end behavior. The code logic for both is fully implemented and correct.

---

_Verified: 2026-02-20T07:30:00Z_
_Verifier: Claude (gsd-verifier)_
