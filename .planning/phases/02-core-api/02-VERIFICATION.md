---
phase: 02-core-api
verified: 2026-02-20T05:28:16Z
status: gaps_found
score: 9/10 must-haves verified
re_verification: false
gaps:
  - truth: "Vote impact is weighted by the voting agent's reputation score"
    status: partial
    reason: "The wiring is present (reputation_score passed to apply_vote_to_trace) but reputation_score defaults to 0.0 for all users and is never updated in Phase 2, causing max(0.0, 1.0) = 1.0 for every vote. All votes are equal weight until Phase 4 ships the reputation engine. CONT-03 is mapped to Phase 2 in REQUIREMENTS.md but the actual weighting is a Phase 4 concern."
    artifacts:
      - path: "api/app/routers/votes.py"
        issue: "vote_weight = user.reputation_score if user.reputation_score > 0 else 1.0 — reputation_score is always 0.0 in Phase 2, so all votes carry weight 1.0. The column exists and the wiring is correct but no code updates reputation_score in this phase."
      - path: "api/app/models/user.py"
        issue: "reputation_score column exists and defaults to 0.0; no update path exists until Phase 4 (REPU-01 through REPU-03)"
    missing:
      - "Either mark CONT-03 as a Phase 4 responsibility (recommend), or add a stub mechanism that updates reputation_score after successful contributions so the weighting is demonstrably non-uniform during Phase 2 testing"
human_verification:
  - test: "Submit a trace with a clean payload, verify 202 response and pending state in database"
    expected: "POST /api/v1/traces returns 202 with trace ID; SELECT * FROM traces WHERE id = :id shows status='pending'"
    why_human: "Requires a running database and Redis; can't verify end-to-end HTTP behavior with static code analysis alone"
  - test: "Submit a trace containing 'AKIAIOSFODNN7EXAMPLE' in solution_text, verify 422 rejection"
    expected: "POST /api/v1/traces returns 422 with 'Content rejected' error; no row appears in the traces table"
    why_human: "Requires live HTTP request; confirms scanner fires before database write end-to-end"
  - test: "Cast a downvote without a feedback_tag, verify 422 rejection at schema level"
    expected: "POST /api/v1/traces/{id}/votes with vote_type='down' and no feedback_tag returns 422 Unprocessable Entity"
    why_human: "Requires live HTTP call; confirms Pydantic model_validator fires in production ASGI handler"
  - test: "Flag a trace as harmful, then query GET /api/v1/moderation/flagged and confirm it appears"
    expected: "POST flag returns 200 with flagged:true; GET /moderation/flagged includes the trace with is_flagged=true"
    why_human: "Requires running database to confirm is_flagged=True and flagged_at are persisted correctly"
  - test: "Run alembic upgrade head on a fresh database and confirm amendments table and staleness columns exist"
    expected: "\\d traces shows is_stale, is_flagged, flagged_at; \\d amendments shows the table with FKs to traces and users"
    why_human: "Requires a real PostgreSQL+pgvector instance; confirms migration chain 0001->0002 applies cleanly"
---

# Phase 2: Core API Verification Report

**Phase Goal:** Agents can authenticate, submit traces, amend traces, and vote — with PII scanning, content moderation, and staleness detection enforced at the write path before anything touches the database
**Verified:** 2026-02-20T05:28:16Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An API request without a valid API key is rejected with 401 | VERIFIED | `get_current_user` in `api/app/dependencies.py` raises `HTTPException(status_code=401)` when hash lookup returns None; `APIKeyHeader(auto_error=True)` returns 401 on missing header |
| 2 | Submitting a trace containing an API key, password, or credential token is rejected before storage — the trace is never written to the database | VERIFIED | `scan_trace_submission` called at line 46 of `traces.py`; `db.add(trace)` is at line 67; scanner raises `SecretDetectedError` which is caught and raised as HTTP 422 before any DB write |
| 3 | An agent can submit a new trace and receive a 202 Accepted response; the trace appears in the database in "pending" state | VERIFIED | `@router.post("/traces", status_code=202)` in `traces.py`; `Trace(status="pending", ...)` set explicitly; `TraceAccepted(id=trace.id, status="pending")` returned |
| 4 | An agent can upvote or downvote a trace; downvotes require a contextual tag; the vote is recorded and associated with the voter's identity | VERIFIED | `VoteCreate` has `model_validator` requiring `feedback_tag in DOWNVOTE_REQUIRED_TAGS` for downvotes; `Vote(voter_id=user.id, ...)` in `votes.py`; `apply_vote_to_trace` called after successful insert |
| 5 | An agent can submit an amendment to an existing trace with an improved solution and explanation; the amendment is stored and linked to the original trace | VERIFIED | `amendments.py` creates `Amendment(original_trace_id=trace_id, submitter_id=user.id, ...)` with PII scan gate before DB write; returns 201 |
| 6 | A trace flagged by any agent is queryable by a moderator and can be removed; a trace whose referenced library/API version is outdated is automatically flagged as potentially stale | VERIFIED | `POST /traces/{id}/flag` sets `is_flagged=True, flagged_at=func.now()`; `GET /moderation/flagged` queries `Trace.is_flagged == True`; `DELETE /moderation/traces/{id}` hard-deletes with cascade; staleness check in `traces.py` sets `trace.is_stale = True` at submission time |
| 7 | Vote impact is weighted by the voting agent's reputation score (CONT-03) | PARTIAL | `reputation_score` column exists on User; `vote_weight = user.reputation_score if user.reputation_score > 0 else 1.0` is wired in `votes.py`; but `reputation_score` is never updated in Phase 2 — all users have 0.0, so all votes use weight 1.0. The weighting infrastructure is correct but the input data is always the default |
| 8 | A rate-limited user receives 429 with Retry-After header; read and write have separate capacities | VERIFIED | `check_rate_limit` raises `HTTPException(429, headers={"Retry-After": "60"})`; separate `rate_limit_read_per_minute=60` and `rate_limit_write_per_minute=20` settings; `ReadRateLimit`/`WriteRateLimit` applied to correct endpoints |
| 9 | The amendments table and staleness columns exist in the database after migration 0002 | VERIFIED | `0002_amendments_and_staleness.py` revision `c3d4e5f6a7b8` revising `b2c3d4e5f6a7`; adds `is_stale`, `is_flagged`, `flagged_at` to traces; creates `amendments` table with named FKs and indexes |
| 10 | A trace with sufficient upvotes is promoted from pending to validated | VERIFIED | `apply_vote_to_trace` in `trust.py` atomically updates `confirmation_count` and `trust_score`; promotes to `TraceStatus.validated` when `confirmation_count >= settings.validation_threshold AND trust_score > 0` |

**Score:** 9/10 truths verified (1 partial)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/dependencies.py` | CurrentUser auth dependency, RedisClient dependency | VERIFIED | Contains `get_current_user` with SHA-256 hash lookup, `get_redis`, `CurrentUser` and `RedisClient` type aliases |
| `api/app/middleware/rate_limiter.py` | Token bucket rate limiter via Redis Lua script | VERIFIED | Contains `RATE_LIMIT_LUA` (973 chars), `check_rate_limit`, `require_read_limit`, `require_write_limit`, `ReadRateLimit`, `WriteRateLimit` |
| `api/app/main.py` | FastAPI app with Redis lifespan and all routers | VERIFIED | `lifespan` stores Redis on `app.state.redis`; all 5 routers registered via `include_router` |
| `api/app/models/amendment.py` | Amendment ORM model | VERIFIED | `class Amendment` with UUID PK, named FK constraints, `lazy="raise"` relationships, proper `Mapped` columns |
| `api/migrations/versions/0002_amendments_and_staleness.py` | Alembic migration for amendments + is_stale/is_flagged | VERIFIED | `create_table("amendments")`, `add_column("is_stale")`, `add_column("is_flagged")`, `add_column("flagged_at")` with proper downgrade |
| `api/app/services/scanner.py` | PII/secrets scanning gate | VERIFIED | `scan_content` uses `_scan_line` with `enable_eager_search=False`; `SecretDetectedError` raised with types (not values); AWS key and quoted passwords detected in smoke test |
| `api/app/services/staleness.py` | PyPI version staleness checker | VERIFIED | `check_library_staleness` queries `https://pypi.org/pypi/{name}/json` with 3s timeout; compares major.minor; all exceptions silently swallowed |
| `api/app/services/trust.py` | Vote application and trace promotion logic | VERIFIED | `apply_vote_to_trace` uses `update(Trace).values(confirmation_count=Trace.confirmation_count+1, ...)` with `synchronize_session=False`; promotion logic checks threshold |
| `api/app/schemas/trace.py` | TraceCreate, TraceResponse, TraceAccepted | VERIFIED | All three classes present; `TraceCreate` has `min_length`, `max_length` validation; `TraceResponse` has `from_attributes=True` |
| `api/app/schemas/vote.py` | VoteCreate with downvote validation, DOWNVOTE_REQUIRED_TAGS | VERIFIED | `DOWNVOTE_REQUIRED_TAGS = {"outdated", "wrong", "security_concern", "spam"}`; `model_validator(mode="after")` rejects missing/invalid tags on downvote |
| `api/app/schemas/amendment.py` | AmendmentCreate, AmendmentResponse | VERIFIED | Both classes present; `explanation` has `max_length=5000`; `AmendmentResponse` has `from_attributes=True` |
| `api/app/routers/traces.py` | POST /api/v1/traces endpoint | VERIFIED | `submit_trace` with `status_code=202`; three-gate chain: auth + rate limit + PII scan; `scan_trace_submission` at line 46, `db.add(trace)` at line 67 — scan before write confirmed |
| `api/app/routers/votes.py` | POST /api/v1/traces/{id}/votes endpoint | VERIFIED | `cast_vote` with auth + rate limit; self-vote 403; `IntegrityError` caught with constraint name check for 409; `apply_vote_to_trace` called after successful insert |
| `api/app/routers/amendments.py` | POST /api/v1/traces/{id}/amendments endpoint | VERIFIED | `submit_amendment` with auth + rate limit + PII scan (`scan_amendment_submission` before `db.add`) |
| `api/app/routers/auth.py` | POST /api/v1/keys endpoint | VERIFIED | `generate_api_key` uses `secrets.token_urlsafe(32)`; SHA-256 hash stored; raw key returned once; IntegrityError retry on collision |
| `api/app/routers/moderation.py` | Flag, list-flagged, delete endpoints | VERIFIED | `flag_trace` (idempotent), `list_flagged_traces` (paginated, selectinload), `remove_trace` (cascade delete in FK order) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `api/app/dependencies.py` | `api/app/models/user.py` | SHA-256 hash lookup on users.api_key_hash | WIRED | Line 35: `hashlib.sha256(raw_key.encode()).hexdigest()` → `select(User).where(User.api_key_hash == key_hash)` |
| `api/app/middleware/rate_limiter.py` | `api/app/dependencies.py` | RedisClient dependency injection | WIRED | `from app.dependencies import CurrentUser, RedisClient`; used in both `require_read_limit` and `require_write_limit` inner functions |
| `api/app/main.py` | `redis.asyncio` | lifespan context manager stores Redis on app.state | WIRED | `app.state.redis = aioredis.from_url(...)` in lifespan; `await app.state.redis.aclose()` on shutdown |
| `api/app/services/scanner.py` | `detect_secrets` | _scan_line with default_settings context | WIRED | `from detect_secrets.settings import default_settings`; `with default_settings():` wraps all scanning |
| `api/app/services/trust.py` | `api/app/models/trace.py` | atomic UPDATE on confirmation_count and trust_score | WIRED | `update(Trace).values(confirmation_count=Trace.confirmation_count + 1, ...)` with column expressions |
| `api/app/services/staleness.py` | `httpx` | PyPI JSON API lookup with 3s timeout | WIRED | `httpx.AsyncClient(timeout=3.0)` → `https://pypi.org/pypi/{library_name}/json` |
| `api/app/routers/traces.py` | `api/app/services/scanner.py` | scan_trace_submission called before db.add | WIRED | Line 46: `scan_trace_submission(...)` | Line 67: `db.add(trace)` — scan precedes write |
| `api/app/routers/traces.py` | `api/app/services/staleness.py` | check_trace_staleness on metadata_json | WIRED | Line 63: `is_stale = await check_trace_staleness(body.metadata_json)` |
| `api/app/routers/votes.py` | `api/app/services/trust.py` | apply_vote_to_trace after vote insert | WIRED | `apply_vote_to_trace(db, trace_id, user.reputation_score if ... else 1.0, ...)` called after successful `db.flush()` |
| `api/app/routers/votes.py` | `sqlalchemy.exc.IntegrityError` | catch duplicate vote UniqueConstraint | WIRED | `except IntegrityError as exc` checks `"uq_votes_trace_id_voter_id" in str(exc.orig)` → 409; Vote model has matching `UniqueConstraint(..., name="uq_votes_trace_id_voter_id")` |
| `api/app/main.py` | `api/app/routers/*.py` | app.include_router for all routers | WIRED | All 5 routers (auth, traces, votes, amendments, moderation) registered; 14 total routes confirmed |
| `api/app/routers/moderation.py` | `api/app/models/trace.py` | UPDATE traces SET is_flagged=True, flagged_at=now() | WIRED | `update(Trace).values(is_flagged=True, flagged_at=func.now())` at line 66; `Trace.is_flagged == True` query at line 97 |

### Requirements Coverage

| Requirement | Status | Notes |
|-------------|--------|-------|
| API-01: RESTful API with API key authentication | SATISFIED | `CurrentUser` dependency enforces X-API-Key header on all protected endpoints; `POST /keys` returns raw key once; SHA-256 hash stored |
| API-02: All trace content scanned for PII/secrets before storage | SATISFIED | `scan_trace_submission` gates `POST /traces`; `scan_amendment_submission` gates `POST /amendments`; scanner fires before any `db.add` |
| SAFE-01: Two-tier pending/validated model with configurable thresholds | SATISFIED | `TraceStatus.pending`/`TraceStatus.validated` enforced; `apply_vote_to_trace` promotes at `settings.validation_threshold` (default 2); threshold is env-configurable |
| SAFE-02: Automated PII scanning blocks traces with secrets/credentials/personal data | SATISFIED | `scan_content` detects AWS keys, JWTs, quoted passwords via detect-secrets; `SecretDetectedError` raised before DB write; smoke test confirmed AWS key detection |
| SAFE-03: Content moderation — flagging and removal of harmful/spam traces | SATISFIED | `POST /traces/{id}/flag` (idempotent), `GET /moderation/flagged` (paginated), `DELETE /moderation/traces/{id}` (cascade delete) all implemented and registered |
| SAFE-04: Traces referencing outdated libraries/APIs automatically flagged as stale | SATISFIED | `check_trace_staleness` called at submission time; compares stored major.minor vs PyPI latest; sets `trace.is_stale = True` before commit; graceful degradation on network errors |
| CONT-01: Agent can submit a new trace with context, solution, and tags | SATISFIED | `POST /api/v1/traces` accepts `TraceCreate` with title, context_text, solution_text, tags; returns 202 Accepted |
| CONT-02: Agent can upvote or downvote with required contextual feedback | SATISFIED | `VoteCreate.model_validator` rejects downvote without `feedback_tag` from approved set; feedback stored in `Vote.context_json` |
| CONT-03: Vote impact weighted by voting agent's reputation score | PARTIAL | Wiring is correct (`reputation_score` passed to `apply_vote_to_trace`) but `reputation_score` is never set above 0.0 in Phase 2 (defaults to 0.0 for all users → all votes use weight 1.0). Actual weighting awaits Phase 4 reputation engine. |
| CONT-04: Agent can submit an amendment to an existing trace | SATISFIED | `POST /api/v1/traces/{id}/amendments` creates `Amendment(original_trace_id=trace_id, ...)` with PII scan gate; returns 201 |

### Anti-Patterns Found

No anti-patterns detected.

- No TODO/FIXME/placeholder comments in any Phase 2 files
- No stub implementations (all endpoints perform real DB operations)
- No `return null`, `return {}`, or empty-array-without-query stubs
- All PII scan gates fire BEFORE database writes (confirmed by line number analysis)
- All handlers catch specific exceptions and return appropriate HTTP codes

### Human Verification Required

#### 1. End-to-end trace submission with real database

**Test:** POST to `/api/v1/keys` to get an API key, then POST to `/api/v1/traces` with a clean payload
**Expected:** 202 Accepted with `{id: uuid, status: "pending"}`; `SELECT status FROM traces WHERE id = :id` returns "pending"
**Why human:** Requires running PostgreSQL + Redis + FastAPI stack; verifies lifespan Redis connection and DB write path together

#### 2. PII scan blocks write end-to-end

**Test:** POST to `/api/v1/traces` with `solution_text` containing `AKIAIOSFODNN7EXAMPLE`
**Expected:** 422 Unprocessable Entity with "Content rejected"; no row in `traces` table
**Why human:** Confirms scanner fires in the live ASGI handler and that the exception propagation is correct under uvicorn

#### 3. Downvote schema validation in production handler

**Test:** POST to `/api/v1/traces/{id}/votes` with `{"vote_type": "down"}` (no feedback_tag)
**Expected:** 422 Unprocessable Entity from Pydantic validation
**Why human:** Confirms the `model_validator` is invoked by FastAPI's request parsing pipeline, not just in unit testing

#### 4. Moderation flag + query flow

**Test:** POST `/api/v1/traces/{id}/flag` with `{"reason": "contains misinformation", "category": "harmful"}`, then GET `/api/v1/moderation/flagged`
**Expected:** Flag returns 200 `{flagged: true}`; list endpoint includes the trace
**Why human:** Confirms `is_flagged=True` and `flagged_at` are committed to DB and queryable

#### 5. Migration 0002 applies cleanly on fresh database

**Test:** `docker compose up -d db` then `alembic upgrade head`; inspect schema
**Expected:** `traces` table has `is_stale`, `is_flagged`, `flagged_at` columns; `amendments` table exists with correct FKs
**Why human:** Confirms actual PostgreSQL migration applies without conflict; verifies the revision chain 0000->0001->0002

### Gaps Summary

One gap was identified: **CONT-03 (vote impact weighted by reputation score)** is partially implemented.

The wiring infrastructure is correct — `reputation_score` is a column on the `User` model, and `votes.py` passes `user.reputation_score` (defaulting to 1.0 when zero) to `apply_vote_to_trace`. However, no code in Phase 2 ever updates `reputation_score` above 0.0, so all votes in this phase carry equal weight of 1.0.

This is acknowledged in the 02-03-SUMMARY.md as a deliberate design decision: "All early votes are equal weight until the reputation engine ships in Phase 4." The REQUIREMENTS.md maps CONT-03 to Phase 2, creating an apparent gap.

**Recommended resolution:** Either update REQUIREMENTS.md to move CONT-03 to Phase 4 alongside REPU-01/REPU-02/REPU-03 (since reputation computation is a Phase 4 concern), or document in Phase 2 state that CONT-03 is structurally ready but behaviorally deferred.

The remaining 9/10 truths are fully verified with real, substantive implementations — all gates fire before DB writes, all endpoints are wired and registered, and all scan/staleness/trust services are connected to their consumers.

---

_Verified: 2026-02-20T05:28:16Z_
_Verifier: Claude (gsd-verifier)_
