# Phase 2: Core API — Auth, Safety, Contribution - Research

**Researched:** 2026-02-20
**Domain:** FastAPI authentication, PII/secrets scanning, Redis rate limiting, SQLAlchemy async patterns
**Confidence:** HIGH

---

## Summary

Phase 2 adds the request-handling layer on top of Phase 1's data foundation. Every write path must pass through three synchronous gates in order: authentication (API key lookup + hash verification), rate limiting (per-key token bucket via Redis), and PII/secrets scanning (detect-secrets plugins over submitted text). Only after all three pass does the request touch the database. This ordering is deliberate — it keeps the database free of any unauthenticated or malicious content.

The implementation uses FastAPI's dependency injection system exclusively (no middleware for auth), with `APIKeyHeader` extracting `X-API-Key` and a chained `get_current_user` dependency performing the SHA-256 hash lookup against `users.api_key_hash`. Rate limiting is implemented via custom Lua scripts executed against the existing Redis instance (already in docker-compose), giving per-key token buckets with separate capacities for read vs write endpoints. The amendments model requires a new `amendments` table (a new Alembic migration) with a `original_trace_id` foreign key back to `traces`. The staleness detection mechanism uses the PyPI JSON API to compare versions stored in `metadata_json` against the current published release and flags traces by setting a `is_stale` column that must be added to the `traces` table (second migration in this phase).

**Primary recommendation:** Build auth as a layered Annotated dependency (`CurrentUser`), keep the PII scanner as a pure synchronous service function (no async — detect-secrets is CPU-bound), apply rate limiting via custom Lua + redis.asyncio before the handler body executes, and extend the schema with two new migrations: amendments table and `is_stale`/`flagged_at` columns on traces.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | >=0.129.0 (already in deps) | Router, dependency injection, OpenAPI | Project baseline |
| `redis[asyncio]` | >=5.0 | Async Redis client (replaces aioredis) | aioredis merged into redis-py; `redis.asyncio` is the canonical async interface |
| `detect-secrets` | 1.5.0 | Secrets/PII scanning with 20+ built-in detectors | Widely adopted; has `scan_line()` / `scan_adhoc_string()` for in-memory scanning |
| `passlib[bcrypt]` or `hashlib` | stdlib | SHA-256 hashing of API keys | stdlib `hashlib.sha256` is sufficient; `hmac.compare_digest` for timing-safe compare |
| `packaging` | >=23.0 | PEP 440 version parsing for staleness comparison | stdlib-adjacent; already a transitive dep via many packages |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | >=0.27 (already in dev deps) | Async HTTP client for PyPI JSON API version check | Staleness detection — one outbound call per unique library/version tag |
| `slowapi` | >=0.1.9 | Alternative if custom Lua rate limiter is out of scope | Only use if Lua script approach becomes too complex; adds a decorator per endpoint |
| `starlette.status` | (bundled with fastapi) | Status code constants for all 4xx/5xx responses | Always prefer constants over magic numbers |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Lua token bucket | `slowapi` | slowapi is simpler but uses fixed-window by default; Lua gives true per-key token bucket with separate read/write capacities |
| `detect-secrets` | `microsoft/presidio` | Presidio is better for NLP-based PII (names, emails); detect-secrets is better for credentials/tokens/API keys. This phase's requirement is credential scanning — detect-secrets wins |
| `detect-secrets` | Custom regex | detect-secrets has 20+ tuned detectors including entropy analysis; custom regex misses high-entropy generic tokens |
| `hashlib.sha256` | `bcrypt` | bcrypt is for passwords (adaptive cost factor); API keys are randomly generated strings — SHA-256 is fast enough and appropriate |

### Installation
```bash
# Add to api/pyproject.toml dependencies
uv add "redis[asyncio]>=5.0" "detect-secrets>=1.5.0" "packaging>=23.0"
# httpx already in dev deps; promote to main deps if staleness check is not test-only
uv add "httpx>=0.27"
```

---

## Architecture Patterns

### Recommended Project Structure
```
api/app/
├── routers/
│   ├── __init__.py
│   ├── traces.py          # POST /api/v1/traces, GET /api/v1/traces/{id}
│   ├── votes.py           # POST /api/v1/traces/{id}/votes
│   ├── amendments.py      # POST /api/v1/traces/{id}/amendments
│   └── moderation.py      # POST /api/v1/traces/{id}/flag
├── schemas/
│   ├── __init__.py
│   ├── trace.py           # TraceCreate, TraceResponse
│   ├── vote.py            # VoteCreate, VoteResponse
│   ├── amendment.py       # AmendmentCreate, AmendmentResponse
│   └── common.py          # ErrorResponse, PaginatedResponse
├── services/
│   ├── tags.py            # (exists) normalize_tag, validate_tag
│   ├── scanner.py         # scan_content() — PII/secrets gate
│   ├── staleness.py       # check_version_staleness() — PyPI lookup
│   └── trust.py           # recalculate_trust_score(), promote_if_validated()
├── middleware/
│   └── rate_limiter.py    # Lua token bucket, get_rate_limit_dependency()
├── models/
│   ├── (all Phase 1 models)
│   └── amendment.py       # Amendment model (new in Phase 2)
├── dependencies.py        # DbSession, CurrentUser, RequireScope
├── config.py              # (extend with rate limit settings)
├── database.py            # (exists)
└── main.py                # (extend with lifespan, router registration)
```

### Pattern 1: Chained Auth Dependency

**What:** APIKeyHeader extracts the raw key; a second dependency hashes it and queries the user row; a third dependency validates scope. All three are composed with Annotated aliases.

**When to use:** Every protected endpoint. The `CurrentUser` alias provides the authenticated User ORM object.

```python
# Source: FastAPI official docs — https://fastapi.tiangolo.com/reference/security/
# + verified pattern from zhanymkanov/fastapi-best-practices
import hashlib
import hmac
from typing import Annotated
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)
# auto_error=True means FastAPI auto-returns 401 when header is absent

async def get_current_user(
    raw_key: Annotated[str, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(User).where(User.api_key_hash == key_hash)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # DO NOT distinguish "missing key" from "invalid key" in error message
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# Reusable type alias — the pattern from fastapi-best-practices
CurrentUser = Annotated[User, Depends(get_current_user)]
```

**Critical:** Use `hmac.compare_digest()` if you ever compare the key directly. When doing a DB lookup by hash, the database does the comparison — timing attacks are not relevant there, but the hash itself must not be logged.

### Pattern 2: Token Bucket Rate Limiter (Lua + Redis)

**What:** A Lua script on Redis performs an atomic read-modify-write on a per-key token bucket. FastAPI dependency calls it before handler body executes.

**When to use:** All write endpoints get a tighter limit; read endpoints get a looser limit. Keys are `rl:{user_id}:write` and `rl:{user_id}:read`.

```python
# Source: https://redis.io/tutorials/howtos/ratelimiting/ (verified pattern)
# Adapted for python redis.asyncio

RATE_LIMIT_LUA = """
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])  -- tokens per second
local now = tonumber(ARGV[3])

local bucket = redis.call('HGETALL', key)
local tokens = max_tokens
local last_refill = now

if #bucket > 0 then
    tokens = tonumber(bucket[2])
    last_refill = tonumber(bucket[4])
end

local elapsed = math.max(0, now - last_refill)
local refilled = math.min(max_tokens, tokens + elapsed * refill_rate)

local allowed = 0
if refilled >= 1 then
    allowed = 1
    refilled = refilled - 1
end

redis.call('HSET', key, 'tokens', refilled, 'last_refill', now)
redis.call('EXPIRE', key, math.ceil(max_tokens / refill_rate + 1))

return allowed
"""

import time
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException

async def check_rate_limit(
    user: CurrentUser,
    redis_client: aioredis.Redis,  # injected via app.state
    bucket_type: str = "read",     # "read" or "write"
) -> None:
    # Separate capacities: writes are more restricted
    config = {
        "read":  {"max_tokens": 60, "refill_rate": 1.0},   # 60 req/min
        "write": {"max_tokens": 20, "refill_rate": 0.33},  # 20 req/min
    }[bucket_type]

    key = f"rl:{user.id}:{bucket_type}"
    allowed = await redis_client.eval(
        RATE_LIMIT_LUA, 1, key,
        config["max_tokens"], config["refill_rate"], time.time()
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
```

### Pattern 3: PII/Secrets Scanner as Synchronous Gate

**What:** detect-secrets plugins are invoked line-by-line against submitted text fields before any DB write.

**When to use:** Called inside service layer for `TraceCreate` and `AmendmentCreate` payloads.

**Critical architectural note:** detect-secrets is CPU-bound (no I/O). Run it in a sync function. If you need to call it from an async context, use `asyncio.run_in_executor(None, scan_content, text)` — but for a synchronous gate the simpler approach is to keep the service function sync and call it directly since FastAPI runs sync functions in a threadpool automatically.

```python
# Source: https://github.com/Yelp/detect-secrets (verified API)
# detect_secrets.main.scan_adhoc_string is the correct programmatic entry point
from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings
from detect_secrets.core.scan import scan_line

class SecretDetectedError(Exception):
    """Raised when submitted content contains secrets/credentials."""
    pass

def scan_content(text: str) -> None:
    """Synchronous PII/secrets gate. Raises SecretDetectedError if triggered.

    Uses scan_line() which invokes all enabled plugins against each line.
    Each plugin's analyze_line() calls analyze_string() internally.
    """
    with default_settings():
        for line in text.splitlines():
            secrets = list(scan_line(line))
            if secrets:
                # Do NOT echo the detected secret in the error message
                types_found = {s.type for s in secrets}
                raise SecretDetectedError(
                    f"Content contains potential secrets: {types_found}"
                )

def scan_trace_fields(title: str, context_text: str, solution_text: str) -> None:
    """Scan all user-supplied text fields in a trace submission."""
    for field_value in [title, context_text, solution_text]:
        scan_content(field_value)
```

**Plugin coverage in detect-secrets 1.5.0 (HIGH confidence — verified from GitHub):**
- `AWSKeyDetector`, `GitHubTokenDetector`, `GitLabTokenDetector`
- `BasicAuthDetector` (catches `user:pass@host` patterns)
- `PrivateKeyDetector` (PEM blocks)
- `KeywordDetector` (catches `password=`, `api_key=`, `secret=` etc.)
- `Base64HighEntropyString`, `HexHighEntropyString` (catches generic high-entropy tokens)
- `JwtTokenDetector`, `SlackDetector`, `StripeDetector`, `TwilioKeyDetector`

### Pattern 4: Amendment Model (New Table)

**What:** Amendments are stored in a dedicated `amendments` table linked to the parent trace via `original_trace_id`. This is NOT a self-referential relationship on `traces` — that would complicate the async lazy-load situation. A separate model is cleaner.

**When to use:** POST /api/v1/traces/{id}/amendments

```python
# app/models/amendment.py
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .trace import Trace
    from .user import User

class Amendment(Base):
    __tablename__ = "amendments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("traces.id", name="fk_amendments_original_trace_id_traces"),
        nullable=False,
        index=True,
    )
    submitter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_amendments_submitter_id_users"),
        nullable=False,
    )
    improved_solution: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships — use lazy="raise" to force explicit loading in async context
    original_trace: Mapped["Trace"] = relationship(
        "Trace", lazy="raise", foreign_keys=[original_trace_id]
    )
    submitter: Mapped["User"] = relationship("User", lazy="raise")
```

### Pattern 5: Trust Score Update Without ORM Load

**What:** When a vote is cast, increment `confirmation_count` and recalculate `trust_score` in a single UPDATE statement — no SELECT first.

```python
# Source: https://docs.sqlalchemy.org/en/21/tutorial/data_update.html (verified)
from sqlalchemy import update, select
from app.models.trace import Trace, TraceStatus
from app.config import settings

async def apply_vote_to_trace(
    db: AsyncSession,
    trace_id: uuid.UUID,
    vote_weight: float,  # voter's reputation_score
    is_upvote: bool,
) -> None:
    score_delta = vote_weight if is_upvote else -vote_weight

    # Atomic increment — no object load required
    await db.execute(
        update(Trace)
        .where(Trace.id == trace_id)
        .values(
            confirmation_count=Trace.confirmation_count + 1,
            trust_score=Trace.trust_score + score_delta,
        )
    )

    # Check for promotion — re-query the updated row
    result = await db.execute(
        select(Trace.confirmation_count, Trace.trust_score, Trace.status)
        .where(Trace.id == trace_id)
    )
    row = result.one()
    if (
        row.status == TraceStatus.pending
        and row.confirmation_count >= settings.validation_threshold
        and row.trust_score > 0
    ):
        await db.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(status=TraceStatus.validated)
        )
```

### Pattern 6: Staleness Detection via PyPI JSON API

**What:** When a trace has `metadata_json` containing a `library` and `library_version` key, check the current PyPI release. If the stored version is behind the current major/minor, flag the trace.

**When to use:** Runs at submission time for traces with library metadata AND as a background check for existing traces (out of scope in this phase — Phase 2 only does submission-time check).

```python
# Source: https://docs.pypi.org/api/json/ (verified endpoint)
# + https://packaging.pypa.io/en/stable/version.html (packaging.version)
import httpx
from packaging.version import Version, InvalidVersion

async def check_library_staleness(
    library_name: str, stored_version_str: str
) -> bool:
    """Returns True if stored_version is behind current major.minor on PyPI."""
    try:
        stored = Version(stored_version_str)
    except InvalidVersion:
        return False  # Can't parse — don't flag

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"https://pypi.org/pypi/{library_name}/json",
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return False  # PyPI unavailable — don't block/flag
            latest_str = resp.json()["info"]["version"]
        latest = Version(latest_str)
        # Flag if stored major.minor is behind latest major.minor
        return (stored.major, stored.minor) < (latest.major, latest.minor)
    except Exception:
        return False  # Network failure — graceful degradation
```

### Pattern 7: Redis Connection via Lifespan

**What:** Single async Redis connection pool, stored on `app.state`, injected as a dependency.

```python
# Source: verified pattern from redis.io FastAPI tutorial and multiple 2025 sources
import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    yield
    # Shutdown
    await app.state.redis.aclose()

app = FastAPI(title="CommonTrace API", version="0.1.0", lifespan=lifespan)

async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis

RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
```

### Pattern 8: Schema Organization (Pydantic v2)

**What:** Request/response schemas live in `schemas/` separate from ORM models. Use `model_config = ConfigDict(from_attributes=True)` for response schemas that serialize from ORM objects.

```python
# Source: Pydantic v2 official docs
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import uuid
from datetime import datetime

class TraceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    context_text: str = Field(min_length=1)
    solution_text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=20)
    agent_model: Optional[str] = Field(None, max_length=100)
    agent_version: Optional[str] = Field(None, max_length=50)
    metadata_json: Optional[dict] = None

class TraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    title: str
    created_at: datetime

class TraceAccepted(BaseModel):
    """202 Accepted response — trace queued, not yet validated."""
    id: uuid.UUID
    status: str  # always "pending"
    message: str = "Trace accepted for processing"
```

### Anti-Patterns to Avoid

- **Using middleware for auth:** Middleware runs for ALL requests including health checks, static files, and OPTIONS preflight. Use dependencies on routers instead — they compose better and appear in OpenAPI docs.
- **Logging raw API keys:** Never log `X-API-Key` header value. Log only the `user.id` after successful auth.
- **async detect-secrets:** detect-secrets has no async API and is CPU-bound. Calling it directly in an async handler blocks the event loop. Keep it in a sync service function; FastAPI threadpools it automatically.
- **ORM relationship lazy loading in async:** The existing models have lazy relationships. Never access `trace.votes` or `trace.tags` directly in an async context without `selectinload()` or `joinedload()` in the query. This is the MissingGreenlet error from Phase 1.
- **Checking votes before scanning:** Run the PII scanner before any DB write. If you write the vote first and scan second, malicious content can slip through if scan raises.
- **String comparison for API keys:** Never use `==` to compare API key hashes — use DB lookup (equality in SQL is timing-safe at the protocol level). If comparing in Python, use `hmac.compare_digest()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Secret/credential detection patterns | Custom regex for API keys, passwords | `detect-secrets` 1.5 with `scan_line()` | 20+ tuned detectors, entropy analysis for generic tokens, maintained by Yelp |
| PEP 440 version parsing | String split on `.` | `packaging.version.Version` | Handles pre-release, epochs, local versions, provides `<` `>` operators |
| Token bucket atomicity | Read-then-write in Python | Redis Lua script | Without Lua, concurrent requests bypass the limit via TOCTOU race |
| Timing-safe key comparison | `==` on hashes | `hmac.compare_digest()` | Standard string comparison leaks timing information |
| OpenAPI security docs | Manual `__doc__` | `APIKeyHeader(name="X-API-Key")` | Automatically registers security scheme in `/docs` |

**Key insight:** detect-secrets is the only mature Python library that does both pattern-matching AND entropy analysis. Entropy analysis is necessary to catch generic high-entropy tokens that don't match known patterns (e.g., a custom internal API key). Custom regex would miss these.

---

## Common Pitfalls

### Pitfall 1: MissingGreenlet on Relationship Access in Async Context
**What goes wrong:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` when accessing ORM relationships (e.g., `trace.tags`, `trace.votes`) in an async handler.
**Why it happens:** Default lazy loading triggers a synchronous DB call, which is not allowed inside asyncio event loop.
**How to avoid:** Always use `selectinload()` or `joinedload()` when fetching objects that need relationships. Example:
```python
result = await db.execute(
    select(Trace)
    .options(selectinload(Trace.tags))
    .where(Trace.id == trace_id)
)
```
**Warning signs:** Error message mentions `greenlet_spawn`, relationship access works in sync tests but fails in async tests.

### Pitfall 2: detect-secrets scan_line Requires default_settings Context
**What goes wrong:** `detect_secrets.core.scan.scan_line()` returns no results or raises when called outside a settings context.
**Why it happens:** detect-secrets uses a global settings object that must be initialized before plugins are discovered.
**How to avoid:** Always wrap scan calls in `with default_settings():` or call `configure_settings()` once at app startup.
**Warning signs:** `scan_line()` returns an empty iterator even on text with obvious secrets.

### Pitfall 3: Redis eval() vs evalsha() Key Count
**What goes wrong:** Lua script receives wrong arguments; `KEYS[1]` is None.
**Why it happens:** `redis.eval(script, numkeys, *keys, *args)` — the second argument is the count of keys, not the first key. Getting it wrong (e.g., passing 0) causes KEYS to be empty.
**How to avoid:** Always pass `1` as numkeys when using one key, then the key, then the ARGV values.

### Pitfall 4: Downvote Missing Contextual Tag Silently Accepted
**What goes wrong:** A downvote is stored without the required contextual tag (e.g., `outdated`, `wrong`, `security_concern`).
**Why it happens:** Validation is in the Pydantic schema but schema allows `feedback_text=None` for upvotes. The discriminated union is not enforced at the model level.
**How to avoid:** Use a Pydantic `model_validator` (v2) that checks: if `vote_type == "down"` then `feedback_text` must be non-None and the tag must be from the approved list.
```python
from pydantic import model_validator
DOWNVOTE_REQUIRED_TAGS = {"outdated", "wrong", "security_concern", "spam"}

class VoteCreate(BaseModel):
    vote_type: str  # "up" or "down"
    feedback_tag: Optional[str] = None
    feedback_text: Optional[str] = None

    @model_validator(mode="after")
    def downvote_requires_tag(self) -> "VoteCreate":
        if self.vote_type == "down":
            if self.feedback_tag not in DOWNVOTE_REQUIRED_TAGS:
                raise ValueError(
                    f"Downvote requires feedback_tag from: {DOWNVOTE_REQUIRED_TAGS}"
                )
        return self
```

### Pitfall 5: UniqueConstraint Violation on Double-Vote Not Handled
**What goes wrong:** A user votes twice on the same trace — the DB raises `IntegrityError` (UniqueConstraint on `trace_id, voter_id`), which becomes a 500.
**Why it happens:** Phase 1 set up the unique constraint but Phase 2 must catch the exception at the service layer.
**How to avoid:** Catch `sqlalchemy.exc.IntegrityError` in the vote handler, check `constraint_name` matches `uq_votes_trace_id_voter_id`, and raise `HTTPException(409, "Already voted on this trace")`.

### Pitfall 6: PyPI Staleness Check Blocks Request
**What goes wrong:** A slow or unavailable PyPI API causes the submission endpoint to time out.
**Why it happens:** `httpx` default timeout is 5s; PyPI has no SLA. If called synchronously in the request handler, one slow response blocks a uvicorn worker.
**How to avoid:** Always use `timeout=3.0` in the httpx client. Wrap in try/except `httpx.TimeoutException` and treat timeout as "not stale" (graceful degradation). Cache PyPI responses in Redis with a 1-hour TTL keyed on `pypi:{library_name}` to avoid repeated external calls.

### Pitfall 7: API Key Generated at Registration Must Be Non-Reversible
**What goes wrong:** The raw API key is stored in the database; if the DB is compromised, all keys leak.
**Why it happens:** Developer stores the raw key for convenience.
**How to avoid:** Generate the raw key (e.g., `secrets.token_urlsafe(32)`) once, return it to the caller, store only `hashlib.sha256(raw_key.encode()).hexdigest()` in `users.api_key_hash`. The raw key is never stored.

---

## Code Examples

Verified patterns from official sources:

### Router Registration with Auth Dependency
```python
# All routes in this router require authentication
# Source: FastAPI docs — https://fastapi.tiangolo.com/reference/apirouter/
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user

router = APIRouter(
    prefix="/api/v1",
    tags=["traces"],
    dependencies=[Depends(get_current_user)],  # applies to all routes
)

# Individual endpoints still declare CurrentUser to get the user object
@router.post("/traces", status_code=202)
async def submit_trace(
    body: TraceCreate,
    user: CurrentUser,  # already authenticated by router dep
    db: DbSession,
    redis: RedisClient,
) -> TraceAccepted:
    ...
```

### 202 Accepted Response Pattern
```python
# Source: FastAPI docs — return JSONResponse with status_code
# Alternatively: set status_code=202 on the decorator and return the schema directly
from starlette.status import HTTP_202_ACCEPTED

@router.post("/traces", status_code=HTTP_202_ACCEPTED, response_model=TraceAccepted)
async def submit_trace(body: TraceCreate, user: CurrentUser, db: DbSession) -> TraceAccepted:
    # ... business logic ...
    return TraceAccepted(id=new_trace.id, status="pending")
    # FastAPI serializes to JSON with status 202
```

### Alembic Migration for Amendments + Staleness Columns
```python
# New migration file: 0002_amendments_and_staleness.py
# Two concerns in one migration since they're both Phase 2 additions
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

def upgrade() -> None:
    # Add staleness columns to traces
    op.add_column("traces", sa.Column(
        "is_stale", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("traces", sa.Column(
        "is_flagged", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("traces", sa.Column(
        "flagged_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.create_index("ix_traces_is_flagged", "traces", ["is_flagged"])
    op.create_index("ix_traces_is_stale", "traces", ["is_stale"])

    # Create amendments table
    op.create_table(
        "amendments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "original_trace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("traces.id", name="fk_amendments_original_trace_id_traces"),
            nullable=False,
        ),
        sa.Column(
            "submitter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_amendments_submitter_id_users"),
            nullable=False,
        ),
        sa.Column("improved_solution", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_amendments_original_trace_id", "amendments", ["original_trace_id"])
    op.create_index("ix_amendments_submitter_id", "amendments", ["submitter_id"])

def downgrade() -> None:
    op.drop_index("ix_amendments_submitter_id", table_name="amendments")
    op.drop_index("ix_amendments_original_trace_id", table_name="amendments")
    op.drop_table("amendments")
    op.drop_index("ix_traces_is_stale", table_name="traces")
    op.drop_index("ix_traces_is_flagged", table_name="traces")
    op.drop_column("traces", "flagged_at")
    op.drop_column("traces", "is_flagged")
    op.drop_column("traces", "is_stale")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `aioredis` as separate package | `redis.asyncio` (redis-py >= 4.2) | 2022 | aioredis merged into redis-py; use `import redis.asyncio as aioredis` |
| `@app.on_event("startup")` | `@asynccontextmanager async def lifespan(app)` | FastAPI 0.93 (2023) | on_event deprecated; lifespan is the current pattern |
| `response_model=` on decorator | `-> ResponseType` return annotation (FastAPI 0.100+) | 2023 | Both work; return annotation approach is cleaner but `response_model=` still needed for 202 status codes |
| Middleware for auth | Router-level `dependencies=[Depends(...)]` | Always best practice | Middleware can't easily raise HTTPException with proper OpenAPI docs |

**Deprecated/outdated:**
- `aioredis.create_redis_pool()`: Use `redis.asyncio.from_url()` instead
- `@app.on_event("startup")`: Use lifespan context manager
- `pydantic.validator`: Use `@field_validator` (Pydantic v2)

---

## Open Questions

1. **Rate limit values for production**
   - What we know: Phase description says "separate read/write limits per key" but gives no numbers
   - What's unclear: Should limits be configurable via env var or hardcoded defaults?
   - Recommendation: Add `rate_limit_read_per_minute` and `rate_limit_write_per_minute` to `Settings` with sensible defaults (60/20). Configurable via env is the right call given `validation_threshold` is already env-configurable.

2. **API key issuance endpoint**
   - What we know: `users.api_key_hash` exists; user rows exist from seed data
   - What's unclear: Phase 2 description doesn't explicitly mention a key generation endpoint. Does Phase 2 create new users/keys, or does it only authenticate existing seed users?
   - Recommendation: Add a minimal POST `/api/v1/keys` endpoint that creates a user and returns the raw key exactly once. This is needed to test the auth flow end-to-end.

3. **detect-secrets false positive rate**
   - What we know: `KeywordDetector` triggers on words like "password", "secret", "token" which may appear legitimately in trace `context_text` describing a debugging scenario
   - What's unclear: Whether to use all detectors or a curated subset
   - Recommendation: Disable `KeywordDetector` for `context_text` and `title` fields (which describe the problem domain); enable all detectors for `solution_text` (where actual credentials would be dangerous). This requires per-field scanner configuration.

4. **Amendment scanning scope**
   - What we know: Amendments have `improved_solution` and `explanation` fields
   - What's unclear: Whether `explanation` (reasoning) should be scanned for secrets
   - Recommendation: Scan both fields; the overhead is negligible and the security boundary is clear.

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs `https://fastapi.tiangolo.com/reference/security/` — APIKeyHeader, auto_error, Security()
- FastAPI official docs `https://fastapi.tiangolo.com/tutorial/dependencies/` — Depends, Annotated, router-level deps
- `https://github.com/Yelp/detect-secrets` — Plugin list, scan_adhoc_string, scan_line, BasePlugin.analyze_line()
- `https://github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/base.py` — analyze_line signature, analyze_string interface
- SQLAlchemy 2.1 docs `https://docs.sqlalchemy.org/en/21/tutorial/data_update.html` — column expression UPDATE
- Redis.io `https://redis.io/tutorials/howtos/ratelimiting/` — Lua token bucket script (HGETALL, HSET, EXPIRE pattern)
- PyPI JSON API `https://docs.pypi.org/api/json/` — endpoint structure `GET /pypi/{package}/json`
- packaging docs `https://packaging.pypa.io/en/stable/version.html` — Version class, InvalidVersion, comparison operators
- Python stdlib `https://docs.python.org/3/library/hmac.html` — compare_digest()

### Secondary (MEDIUM confidence)
- `https://github.com/zhanymkanov/fastapi-best-practices` — Router-level dependencies, domain module structure, blocking I/O in async warning
- `https://bryananthonio.com/blog/implementing-rate-limiter-fastapi-redis/` — Per-key Redis rate limiting, Lua atomicity rationale
- `https://gist.github.com/nicksonthc/525742d9a81d3950b443810e8899ee0e` — FastAPI lifespan + redis.asyncio pattern

### Tertiary (LOW confidence)
- Various 2025 Medium articles on SlowAPI and fastapi-limiter — noted as alternative approaches; not used in primary recommendation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified against PyPI, official docs, and GitHub source
- Architecture: HIGH — patterns verified against FastAPI official docs and zhanymkanov/fastapi-best-practices
- Pitfalls: HIGH for MissingGreenlet (Phase 1 experience) and timing attack (stdlib docs); MEDIUM for detect-secrets context manager requirement (verified from source, not official docs)
- detect-secrets programmatic API: MEDIUM — `scan_line()` verified from main.py source read; `default_settings()` context requirement inferred from design.md; test with a quick smoke test at start of implementation

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (30 days — these are stable libraries)
