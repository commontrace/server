# Phase 4: Reputation Engine — Research

**Researched:** 2026-02-20
**Domain:** Wilson score statistics, PostgreSQL materialized views, per-domain reputation modeling, email identity gating, FastAPI dependency injection
**Confidence:** HIGH

---

## Summary

Phase 4 adds the reputation layer that Phase 2 deliberately deferred. The core problem is well-studied: Wilson score lower-bound is the correct formula for ranking by average rating under uncertainty, and the math is stable. Reddit uses it; Evan Miller's 2009 post remains canonical. The formula translates directly to a PostgreSQL SQL expression. The question is WHERE the computation lives and WHEN it runs.

Two architectural choices are in tension. Option A computes the Wilson score in a PostgreSQL materialized view and refreshes it on demand (or via a background task). This keeps Python code thin — the view is an artifact of a migration and a refresh call. Option B computes the score in Python application code and stores the result back with an atomic UPDATE. Both work; the choice affects where bugs live and how easy testing is. Given that: (a) this codebase already uses the atomic-UPDATE pattern for trust scores, (b) materialized views require a UNIQUE index on the view and CONCURRENTLY refresh serializes on the view, and (c) Python computation is easier to unit-test, the recommendation is to compute Wilson score in Python within the trust service and persist it back with an atomic UPDATE — no materialized view needed for the contributor reputation column.

For per-domain reputation: the existing `Tag` and `trace_tags` tables give us domain tags already (e.g., "python", "javascript"). A new `contributor_domain_reputation` table with `(contributor_id, domain_tag, reputation_score)` rows, updated whenever a vote touches a tagged trace, is the standard normalized approach. The voter's domain-specific reputation (for the tags on the trace being voted on) becomes the `vote_weight` passed into `apply_vote_to_trace` — replacing the current flat `reputation_score` fallback.

For email identity gating (REPU-02): the current auth endpoint `POST /api/v1/keys` already accepts an optional `email` but does not require it. Phase 4 must enforce that contributions (traces, votes, amendments) require a registered email. The cleanest approach is a new `RequireEmail` FastAPI dependency that raises 403 if `user.email is None`, applied at the router level to write paths — no schema changes needed.

**Primary recommendation:** Compute Wilson scores in Python (trust service), persist to `users.reputation_score` via atomic UPDATE after each vote. Store per-domain scores in a new `contributor_domain_reputation` table. Gate contributions behind a `RequireEmail` dependency. Do not introduce a materialized view — it adds operational complexity (refresh scheduling, UNIQUE index requirement, CONCURRENTLY lock) without benefit at this scale.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `math` | stdlib | `math.sqrt` for Wilson score formula | No external dep needed; formula is pure arithmetic |
| `pydantic[email]` / `email-validator` | `>=2.3.0` | `EmailStr` for validating email on registration | Pydantic v2 requires `email-validator` separately; `pydantic[email]` installs it |
| `sqlalchemy[asyncio]` | `>=2.0.46` (already in project) | Async ORM for new `contributor_domain_reputation` table and atomic UPDATE | Project baseline |
| `alembic` | `>=1.18.0` (already in project) | Migration for new table | Project baseline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi` | `>=0.129.0` (already in project) | `RequireEmail` dependency, new `/reputation` read endpoint | Project baseline |
| `redis` | `>=5.0` (already in project) | Optional: cache Wilson score computation to avoid recalculating on every read | Only needed if GET /reputation becomes a hot path |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python Wilson score computation | PostgreSQL materialized view | Materialized view requires UNIQUE index on view, CONCURRENTLY refresh serializes, refresh scheduling needs a cron/worker. Python computation is simpler, testable, and consistent with the existing atomic UPDATE pattern in `trust.py`. |
| Python Wilson score computation | PostgreSQL generated column | Generated columns cannot reference aggregate data from other rows — votes are in a separate table. Rule-out: generated columns only see the current row. |
| Separate `contributor_domain_reputation` table | JSONB column on `users` for per-domain scores | JSONB makes atomic per-domain increments awkward (requires PostgreSQL jsonb path operators). Normalized table with `ON CONFLICT DO UPDATE` is simpler and indexable. |
| `RequireEmail` as router-level dependency | Email verification with token email send | Email verification (sending actual email) is out of scope and adds external service dependency. Requiring email at registration time (identity cost) is the stated requirement. |

### Installation
```bash
# Add email-validator to project dependencies
uv add "email-validator>=2.3.0"
# No other new external packages needed
```

---

## Architecture Patterns

### Recommended Project Structure

```
api/app/
├── models/
│   ├── user.py                      # Existing — reputation_score (Float) already present
│   └── reputation.py                # NEW: ContributorDomainReputation model
├── routers/
│   └── reputation.py                # NEW: GET /api/v1/contributors/{user_id}/reputation
├── services/
│   └── trust.py                     # EXTEND: Wilson score computation, domain reputation update
├── dependencies.py                  # EXTEND: RequireEmail dependency
├── schemas/
│   └── reputation.py                # NEW: ReputationResponse schema
└── migrations/versions/
    └── 0003_domain_reputation.py    # NEW: Alembic migration for new table
```

### Pattern 1: Wilson Score Lower Bound in Python

**What:** Compute the 95% confidence lower bound of the Wilson score interval. Takes upvote count and total vote count, returns a float in [0, 1].

**When to use:** Called inside the trust service whenever a vote is cast on a trace contributed by a user. The result is stored back on `users.reputation_score`.

**Formula derivation (source: Evan Miller, https://www.evanmiller.org/how-not-to-sort-by-average-rating.html):**
- `p_hat` = observed fraction of positive ratings = upvotes / total_votes
- `z` = 1.96 (95% confidence, z-score)
- Lower bound = `(p_hat + z²/(2n) - z * sqrt(p_hat*(1-p_hat)/n + z²/(4n²))) / (1 + z²/n)`

**Constant-expanded form (z=1.96, so z²=3.8416, z²/2=1.9208, z/sqrt=1.96):**

```python
# Source: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html
# + verified via https://gist.github.com/technetium/de8e58df900c5b11c372346c3d911893
import math

def wilson_score_lower_bound(upvotes: int, total_votes: int) -> float:
    """Compute the 95% Wilson score lower bound for a binary rating.

    Returns 0.0 if total_votes == 0 (no data = no confidence).
    Returns a value in [0, 1] representing the lower bound of the true
    positive rate at 95% confidence.

    Args:
        upvotes: Number of upvotes (positive ratings).
        total_votes: Total votes (upvotes + downvotes).

    Returns:
        Wilson score lower bound in [0, 1].
    """
    if total_votes == 0:
        return 0.0

    z = 1.9600  # 95% confidence
    z2 = z * z   # 3.8416
    p_hat = upvotes / total_votes
    n = total_votes

    numerator = p_hat + z2 / (2 * n) - z * math.sqrt(
        (p_hat * (1 - p_hat) + z2 / (4 * n)) / n
    )
    denominator = 1 + z2 / n
    return numerator / denominator
```

**Equivalence of SQL form (for reference, do not use in application — use Python function above):**
```sql
-- Equivalent SQL expression (from evan miller's post, verified)
-- positive = upvotes, negative = downvotes, n = positive + negative
((positive + 1.9208) / (positive + negative) -
 1.96 * SQRT((positive * negative) / (positive + negative) + 0.9604) /
        (positive + negative)) / (1 + 3.8416 / (positive + negative))
```

### Pattern 2: Contributor Domain Reputation Table

**What:** A normalized table storing one row per `(contributor_id, domain_tag)` pair. Each row tracks upvotes and downvotes for that contributor within that domain context.

**Schema design:**

```python
# api/app/models/reputation.py
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class ContributorDomainReputation(Base):
    __tablename__ = "contributor_domain_reputation"
    __table_args__ = (
        UniqueConstraint(
            "contributor_id", "domain_tag",
            name="uq_contributor_domain_reputation_contributor_domain"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_cdr_contributor_id_users"),
        nullable=False,
        index=True,
    )
    # domain_tag mirrors the tag name string (e.g., "python", "javascript")
    # Denormalized from tags table intentionally — avoids FK to tags, which may
    # evolve independently of reputation. Tag name is the stable identifier.
    domain_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    upvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Wilson score lower bound — pre-computed and stored for fast ORDER BY queries
    wilson_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    contributor: Mapped["User"] = relationship("User", lazy="raise")
```

**Key design decisions:**
- `domain_tag` is a `String(50)` directly, matching `Tag.name` max length. Not a FK to `tags` — domain reputation persists even if a tag is renamed or curated differently.
- `upvote_count` and `downvote_count` stored separately so Wilson score can be recalculated at any time without scanning votes table.
- `wilson_score` stored denormalized — recomputed in Python and persisted atomically via `ON CONFLICT DO UPDATE`.
- UniqueConstraint on `(contributor_id, domain_tag)` enables safe `ON CONFLICT` upsert.

### Pattern 3: Reputation Update via UPSERT (ON CONFLICT DO UPDATE)

**What:** When a vote is cast on a trace, for each tag on that trace, atomically increment the trace contributor's domain reputation row and recompute the Wilson score.

**When to use:** Called inside the vote handler after `apply_vote_to_trace`, before `db.commit()`.

```python
# Source: SQLAlchemy 2.1 docs — https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#insert-on-conflict
# + PostgreSQL ON CONFLICT DO UPDATE semantics
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, update
from app.models.reputation import ContributorDomainReputation
from app.services.trust import wilson_score_lower_bound

async def update_contributor_domain_reputation(
    db: AsyncSession,
    contributor_id: uuid.UUID,
    domain_tags: list[str],
    is_upvote: bool,
) -> None:
    """Atomically update per-domain reputation for a trace contributor.

    For each domain tag on the voted trace, upserts a
    contributor_domain_reputation row incrementing the appropriate counter,
    then recomputes and stores the Wilson score.

    Args:
        db: Async SQLAlchemy session.
        contributor_id: UUID of the trace author receiving the reputation effect.
        domain_tags: List of normalized tag names from the voted trace.
        is_upvote: True if the vote was an upvote, False for downvote.
    """
    for tag in domain_tags:
        # UPSERT: create row if absent, increment counter if present
        up_delta = 1 if is_upvote else 0
        down_delta = 0 if is_upvote else 1

        stmt = pg_insert(ContributorDomainReputation).values(
            contributor_id=contributor_id,
            domain_tag=tag,
            upvote_count=up_delta,
            downvote_count=down_delta,
            wilson_score=0.0,  # will be updated below
        ).on_conflict_do_update(
            constraint="uq_contributor_domain_reputation_contributor_domain",
            set_={
                "upvote_count": ContributorDomainReputation.upvote_count + up_delta,
                "downvote_count": ContributorDomainReputation.downvote_count + down_delta,
            }
        ).returning(
            ContributorDomainReputation.upvote_count,
            ContributorDomainReputation.downvote_count,
            ContributorDomainReputation.id,
        )

        result = await db.execute(stmt)
        row = result.one()
        new_wilson = wilson_score_lower_bound(row.upvote_count, row.upvote_count + row.downvote_count)

        # Update wilson_score on the row we just upserted
        await db.execute(
            update(ContributorDomainReputation)
            .where(ContributorDomainReputation.id == row.id)
            .values(wilson_score=new_wilson)
            .execution_options(synchronize_session=False)
        )

    # Also update users.reputation_score with the overall Wilson score
    # across ALL domains (aggregate view)
    await _update_overall_reputation(db, contributor_id)


async def _update_overall_reputation(db: AsyncSession, contributor_id: uuid.UUID) -> None:
    """Recompute and persist the aggregate Wilson score on users.reputation_score."""
    result = await db.execute(
        select(
            func.sum(ContributorDomainReputation.upvote_count),
            func.sum(ContributorDomainReputation.downvote_count),
        ).where(ContributorDomainReputation.contributor_id == contributor_id)
    )
    row = result.one()
    total_up = row[0] or 0
    total_down = row[1] or 0
    overall_wilson = wilson_score_lower_bound(total_up, total_up + total_down)

    await db.execute(
        update(User)
        .where(User.id == contributor_id)
        .values(reputation_score=overall_wilson)
        .execution_options(synchronize_session=False)
    )
```

### Pattern 4: Vote Weight from Domain Reputation

**What:** When a voter casts a vote on a trace, the weight for that vote is computed from the voter's domain reputation for the trace's tags. If the voter has established Python reputation and the trace is tagged "python", their Python wilson_score is used; if they have no domain score, weight defaults to a small positive value (not 1.0 — see pitfall below).

```python
# In the votes router, replace the existing weight computation:
# OLD (Phase 2 stub):
#   vote_weight = user.reputation_score if user.reputation_score > 0 else 1.0

# NEW (Phase 4 — domain-aware):
async def get_vote_weight_for_trace(
    db: AsyncSession,
    voter_id: uuid.UUID,
    trace_tags: list[str],
) -> float:
    """Get the voter's effective weight for a trace based on domain reputation.

    Finds all domain reputation rows for this voter matching any of the trace's
    tags. Returns the maximum Wilson score across matching domains, or a small
    base weight if no domain match exists.

    The base weight for a new contributor (no reputation) is intentionally
    smaller than a contributor with established reputation to create a
    measurable weight difference (REPU-01 success criterion).
    """
    BASE_WEIGHT = 0.1   # new contributors have low-but-nonzero weight
    if not trace_tags:
        # No tags — fall back to overall reputation_score
        result = await db.execute(select(User.reputation_score).where(User.id == voter_id))
        overall = result.scalar_one_or_none() or BASE_WEIGHT
        return max(BASE_WEIGHT, overall)

    result = await db.execute(
        select(ContributorDomainReputation.wilson_score)
        .where(ContributorDomainReputation.contributor_id == voter_id)
        .where(ContributorDomainReputation.domain_tag.in_(trace_tags))
    )
    domain_scores = [row[0] for row in result.fetchall()]

    if not domain_scores:
        return BASE_WEIGHT
    # Use max domain score across matching tags
    return max(BASE_WEIGHT, max(domain_scores))
```

**Critical:** Use `BASE_WEIGHT = 0.1` not `1.0` for new contributors. This creates a *measurable* weight difference (the Phase 4 success criterion requires this). A new voter's vote weighs 0.1; an established domain expert with wilson_score=0.8 has 8x the influence. Document this constant in code comments.

### Pattern 5: RequireEmail Dependency

**What:** A FastAPI dependency that raises 403 if the authenticated user has no email registered. Applied at router level to all write endpoints (traces, votes, amendments).

**When to use:** All write paths. Reads (GET) do not require email — public data retrieval is fine without identity cost.

```python
# In api/app/dependencies.py — add after existing CurrentUser

from fastapi import Depends, HTTPException

async def require_email(user: User = Depends(get_current_user)) -> User:
    """Gate that requires the authenticated user to have a registered email.

    Raises 403 Forbidden if user.email is None (anonymous API key usage).
    This implements the identity cost requirement (REPU-02): anonymous
    agents cannot submit contributions.

    Returns the authenticated user so callers can chain with CurrentUser.
    """
    if user.email is None:
        raise HTTPException(
            status_code=403,
            detail="Email registration required to submit contributions. "
                   "Re-register with POST /api/v1/keys providing an email address.",
        )
    return user

# Alias for use in endpoint signatures
RequireEmail = Annotated[User, Depends(require_email)]
```

**Application pattern (router-level):**
```python
# In votes.py — replace CurrentUser with RequireEmail on write endpoints
@router.post("/traces/{trace_id}/votes", ...)
async def cast_vote(
    trace_id: uuid.UUID,
    body: VoteCreate,
    user: RequireEmail,   # gates on email registration
    db: DbSession,
    _rate: WriteRateLimit,
) -> VoteResponse:
    ...
```

### Pattern 6: Alembic Migration (Manual, Consistent with Project Policy)

```python
# api/migrations/versions/0003_domain_reputation.py
"""Add contributor_domain_reputation table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-20 00:03:00.000000
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "contributor_domain_reputation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contributor_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_cdr_contributor_id_users"),
            nullable=False,
        ),
        sa.Column("domain_tag", sa.String(50), nullable=False),
        sa.Column("upvote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("downvote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wilson_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "contributor_id", "domain_tag",
            name="uq_contributor_domain_reputation_contributor_domain",
        ),
    )
    # Composite index for the most common query: get all domain scores for a user
    op.create_index("ix_cdr_contributor_id", "contributor_domain_reputation", ["contributor_id"])
    # Index for the domain query: find all contributors in a domain
    op.create_index("ix_cdr_domain_tag", "contributor_domain_reputation", ["domain_tag"])

def downgrade() -> None:
    op.drop_index("ix_cdr_domain_tag", table_name="contributor_domain_reputation")
    op.drop_index("ix_cdr_contributor_id", table_name="contributor_domain_reputation")
    op.drop_table("contributor_domain_reputation")
```

### Pattern 7: Reputation Read Endpoint

**What:** `GET /api/v1/contributors/{user_id}/reputation` returns overall reputation plus per-domain breakdown.

```python
# api/app/routers/reputation.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.models.user import User
from app.models.reputation import ContributorDomainReputation
from app.schemas.reputation import ReputationResponse, DomainReputationItem
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit

router = APIRouter(prefix="/api/v1", tags=["reputation"])

@router.get("/contributors/{user_id}/reputation", response_model=ReputationResponse)
async def get_contributor_reputation(
    user_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> ReputationResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    contributor = result.scalar_one_or_none()
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")

    domain_result = await db.execute(
        select(ContributorDomainReputation)
        .where(ContributorDomainReputation.contributor_id == user_id)
        .order_by(ContributorDomainReputation.wilson_score.desc())
    )
    domain_rows = domain_result.scalars().all()

    return ReputationResponse(
        user_id=contributor.id,
        overall_wilson_score=contributor.reputation_score,
        domains=[
            DomainReputationItem(
                domain_tag=row.domain_tag,
                wilson_score=row.wilson_score,
                upvote_count=row.upvote_count,
                downvote_count=row.downvote_count,
            )
            for row in domain_rows
        ],
    )
```

### Anti-Patterns to Avoid

- **Materialized view for Wilson score:** Generated columns cannot reference other tables; materialized views require a UNIQUE index on the view and serialize CONCURRENTLY refresh. Avoid both — compute in Python, persist atomically.
- **Using `vote_weight=1.0` as the new-contributor fallback:** The Phase 4 success criterion explicitly requires that "the weight difference is measurable and documented." Using `1.0` as fallback makes new contributors equal to established ones when no domain score exists. Use `BASE_WEIGHT = 0.1`.
- **Setting `RequireEmail` on GET endpoints:** Read endpoints should not require email — only write paths (POST traces, POST votes, POST amendments). Applying to reads breaks anonymous/read-only access patterns.
- **Computing Wilson score in the database trigger:** PostgreSQL triggers cannot call Python functions. A trigger could compute the SQL-form Wilson score, but this creates two computation paths (Python Wilson score function + SQL trigger formula). Keep computation in one place: the Python trust service.
- **FK from `domain_tag` to `tags.id`:** Tags can be renamed, merged, or curated after the fact. Reputation is earned against the tag name string at the time of the vote, and that history should be stable. Do not FK to the tags table.
- **Updating `users.reputation_score` on every read request:** Reputation recomputation must only happen on write events (vote cast), not on reads. Never recompute on GET requests.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wilson score formula | Custom rating average | `wilson_score_lower_bound()` Python function (10 lines, stdlib math) | A naive "upvotes / total_votes" average over-ranks items with one upvote vs items with 50 upvotes and 5 downvotes. Wilson accounts for sample size. |
| Concurrent upsert for per-domain rows | SELECT then INSERT-or-UPDATE | `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL upsert) | SELECT+conditional-INSERT is a TOCTOU race under concurrent votes. ON CONFLICT is atomic. |
| Email format validation | Custom regex | `pydantic[email]` / `EmailStr` | RFC-compliant validation including international addresses; community maintained. |
| Per-domain score storage | JSONB on users table | Dedicated `contributor_domain_reputation` table | JSONB makes atomic per-key increment impossible without `jsonb_set` and `FOR UPDATE`. Normalized table with integer columns and ON CONFLICT is atomic by nature. |

**Key insight:** The Wilson score formula is 3 lines of arithmetic. The value is understanding WHEN to apply it (on each vote, not on each read), WHERE to store the result (denormalized float column, not computed on demand), and WHAT the edge cases are (total_votes == 0 returns 0.0, not divide-by-zero).

---

## Common Pitfalls

### Pitfall 1: Division by Zero in Wilson Score When No Votes Exist
**What goes wrong:** `wilson_score_lower_bound(0, 0)` raises `ZeroDivisionError`.
**Why it happens:** The formula divides by `n` (total votes); when `n=0` there is no data.
**How to avoid:** Guard at the top of the function — `if total_votes == 0: return 0.0`. This is the correct semantic: no evidence = no confidence = score of 0.
**Warning signs:** Error in trust service when a newly registered contributor receives their first vote before the division guard is in place.

### Pitfall 2: New Contributor Weight Indistinguishable from Established Contributor
**What goes wrong:** Phase 4 success criterion requires that "the weight difference is measurable and documented" between a new contributor's first vote and an established contributor's vote.
**Why it happens:** If `BASE_WEIGHT = 1.0` (the Phase 2 fallback value), there is no weight difference when a new user has no domain score.
**How to avoid:** Set `BASE_WEIGHT = 0.1`. Document this constant in code comments. Add a test that verifies: user with established domain wilson_score=0.8 produces vote_weight=0.8, new user produces vote_weight=0.1, ratio is 8:1.
**Warning signs:** Phase 4 verification fails the "measurable difference" criterion; unit test for vote_weight with a new user and an established user shows identical weights.

### Pitfall 3: RequireEmail Blocks Registration Endpoint
**What goes wrong:** Applying `RequireEmail` dependency to `POST /api/v1/keys` breaks the registration flow — you can't require an email to create an account that has an email.
**Why it happens:** Blanket application of the dependency to all POST routes.
**How to avoid:** Apply `RequireEmail` only to contribution write paths: `POST /traces`, `POST /traces/{id}/votes`, `POST /traces/{id}/amendments`. Never apply to `POST /api/v1/keys` or GET paths.
**Warning signs:** A new user cannot register at all; registration returns 403.

### Pitfall 4: ON CONFLICT Constraint Name Must Match Exactly
**What goes wrong:** `pg_insert(...).on_conflict_do_update(constraint="wrong_name", ...)` raises `ProgrammingError: constraint "wrong_name" of relation "contributor_domain_reputation" does not exist`.
**Why it happens:** The constraint name in the Python code must exactly match the name defined in the migration DDL.
**How to avoid:** Use the constant `"uq_contributor_domain_reputation_contributor_domain"` in both the migration and the application code. Define it as a module-level string constant in the model file.
**Warning signs:** Test setup works but production upsert fails; error message mentions constraint name not found.

### Pitfall 5: Domain Tag Scope — Traces With No Tags
**What goes wrong:** A vote on a trace with no tags skips all domain reputation updates. The voter's weight is always `BASE_WEIGHT = 0.1` even if they have established reputation in other domains.
**Why it happens:** The tag-domain join produces an empty list when a trace has no tags.
**How to avoid:** Fall back to `users.reputation_score` (the global Wilson score) when `trace_tags` is empty. Document this fallback in the code and in the API response schema. This is correct behavior — untagged traces are domain-agnostic so the global score applies.
**Warning signs:** Established contributors have unexpectedly low vote weight on untagged traces; test reveals `BASE_WEIGHT` returned instead of `overall_reputation_score`.

### Pitfall 6: MissingGreenlet on ContributorDomainReputation.contributor Relationship Access
**What goes wrong:** `row.contributor.display_name` inside async handler raises `sqlalchemy.exc.MissingGreenlet`.
**Why it happens:** The `contributor` relationship on `ContributorDomainReputation` uses `lazy="raise"`. The relationship is intentionally not loaded by default.
**How to avoid:** Never access `row.contributor` directly. Use `selectinload()` in queries that need the user object, or query the `users` table separately.
**Warning signs:** Works in sync unit tests, fails under async ASGI handler.

### Pitfall 7: Email Required Error Message Leaks Auth State
**What goes wrong:** The 403 error "Email registration required" confirms that the API key IS valid but the user has no email — slightly more information than necessary.
**Why it happens:** The RequireEmail dependency runs AFTER authentication succeeds.
**How to avoid:** This is acceptable for this use case — the success criterion says anonymous API key usage without email "cannot submit contributions", and the user needs to know why they were rejected. Keep the informative 403 message. It does not leak the existence of other users.

---

## Code Examples

Verified patterns from official sources:

### Wilson Score Formula (verified against Evan Miller's canonical post)
```python
import math

def wilson_score_lower_bound(upvotes: int, total_votes: int) -> float:
    """95% confidence Wilson score lower bound.

    BASE_WEIGHT context: new contributors with no votes score 0.0.
    An established contributor with 80% upvote rate on 50 votes scores ~0.66.
    This creates a measurable weight difference for REPU-01.

    Source: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html
    """
    if total_votes == 0:
        return 0.0
    z = 1.9600
    z2 = z * z
    p_hat = upvotes / total_votes
    n = total_votes
    numerator = p_hat + z2 / (2 * n) - z * math.sqrt(
        (p_hat * (1 - p_hat) + z2 / (4 * n)) / n
    )
    return numerator / (1 + z2 / n)
```

### PostgreSQL Upsert (ON CONFLICT) with SQLAlchemy asyncpg
```python
# Source: SQLAlchemy 2.1 docs — PostgreSQL Insert
# https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#insert-on-conflict
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(ContributorDomainReputation).values(
    contributor_id=contributor_id,
    domain_tag=tag,
    upvote_count=1,
    downvote_count=0,
    wilson_score=0.0,
).on_conflict_do_update(
    constraint="uq_contributor_domain_reputation_contributor_domain",
    set_={
        "upvote_count": ContributorDomainReputation.upvote_count + 1,
    }
).returning(
    ContributorDomainReputation.upvote_count,
    ContributorDomainReputation.downvote_count,
    ContributorDomainReputation.id,
)
result = await db.execute(stmt)
row = result.one()
```

### RequireEmail Dependency Pattern
```python
# Source: FastAPI official docs — https://fastapi.tiangolo.com/tutorial/dependencies/
from typing import Annotated
from fastapi import Depends, HTTPException
from app.dependencies import get_current_user
from app.models.user import User

async def require_email(user: User = Depends(get_current_user)) -> User:
    if user.email is None:
        raise HTTPException(
            status_code=403,
            detail="Email registration required to submit contributions.",
        )
    return user

RequireEmail = Annotated[User, Depends(require_email)]
```

### Email Enforcement at Registration (Updated APIKeyCreate Schema)
```python
# Source: Pydantic v2 docs — https://docs.pydantic.dev/latest/api/networks/
# email-validator package required: uv add "email-validator>=2.3.0"
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class APIKeyCreate(BaseModel):
    """Registration schema — email is optional at key creation.

    Email is NOT required here. The identity cost is enforced at
    contribution time via RequireEmail dependency, not at key issuance.
    This allows read-only agents to exist without email registration.
    """
    email: Optional[EmailStr] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=100)
```

**Important:** The `APIKeyCreate` schema already handles email correctly — it is optional at key creation. The identity cost (REPU-02) is enforced at the contribution level via `RequireEmail`, not at the registration level. This is intentional — read-only API consumers don't need email.

### Reputation Response Schema
```python
# api/app/schemas/reputation.py
import uuid
from pydantic import BaseModel, ConfigDict

class DomainReputationItem(BaseModel):
    domain_tag: str
    wilson_score: float
    upvote_count: int
    downvote_count: int

class ReputationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    overall_wilson_score: float
    domains: list[DomainReputationItem]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Average rating (upvotes / total) | Wilson score lower bound | Reddit ~2009, Evan Miller post | Small-sample items no longer outrank large-sample items; one upvote doesn't beat 50 upvotes and 5 downvotes |
| Upvotes minus downvotes | Wilson score lower bound | Same | Net score ignores total count; Wilson accounts for confidence |
| Global single reputation score | Per-domain reputation scores | Modern Q&A design (post Stack Exchange research 2015+) | Domain expertise is not transferable; a Python expert's vote on Python is more meaningful than a stranger's |
| PostgreSQL generated columns for computed stats | Stored pre-computed columns with explicit UPDATE | PostgreSQL 10+ | Generated columns cannot reference other rows or tables — aggregate stats require explicit UPDATE pattern |

**Deprecated/outdated patterns:**
- `reputation_score = upvotes - downvotes`: Ignores sample size entirely; replaced by Wilson score.
- `reputation_score = upvotes / max(total, 1)`: Ignores confidence; a single upvote gives 100% which equals a highly-reviewed item at 95%.
- Materialized view for per-contributor stats: Requires UNIQUE index on view, refresh serializes, no benefit over atomic UPDATE at this scale.

---

## Wiring to Phase 2 Infrastructure

### What Phase 2 Built (already wired, Phase 4 extends)

| Phase 2 artifact | Phase 4 action |
|-----------------|----------------|
| `users.reputation_score (Float, default=0.0)` | Phase 4 writes real values here via `_update_overall_reputation()` |
| `votes.py: vote_weight = user.reputation_score if user.reputation_score > 0 else 1.0` | Phase 4 replaces this with `get_vote_weight_for_trace()` using domain scores |
| `trust.py: apply_vote_to_trace(vote_weight=...)` | Phase 4 passes domain-aware `vote_weight` from `get_vote_weight_for_trace()` |
| `POST /api/v1/keys` with optional `email` | Phase 4 adds `RequireEmail` dependency on write paths (not on this endpoint) |
| Tags on traces (`trace_tags`, `Tag.name`) | Phase 4 uses tag names as domain identifiers for per-domain reputation |

### Vote flow after Phase 4

```
POST /traces/{id}/votes
  1. CurrentUser (auth)
  2. WriteRateLimit (rate limit)
  3. RequireEmail (identity gate — NEW in Phase 4)
  4. Trace lookup (404 if not found)
  5. Self-vote check (403)
  6. Vote INSERT + flush
  7. get_vote_weight_for_trace(voter_id, trace_tags) — NEW in Phase 4
  8. apply_vote_to_trace(trace_id, vote_weight, is_upvote) — EXISTING
  9. update_contributor_domain_reputation(contributor_id, trace_tags, is_upvote) — NEW
  10. db.commit()
```

---

## Open Questions

1. **Should RequireEmail be enforced on `POST /traces/{id}/amendments` as well?**
   - What we know: REPU-02 says "anonymous API key usage without email registration cannot submit contributions." Amendments are contributions.
   - What's unclear: The phase description says "traces, votes" — not explicitly amendments.
   - Recommendation: Apply `RequireEmail` to amendments too. "Cannot submit contributions" should include all write paths. This is consistent with the identity-cost design intent.

2. **When a trace has multiple tags (e.g., "python" and "django"), does voting on it update reputation for ALL tags?**
   - What we know: The design calls for "per domain context." A trace could have both "python" and "django" tags.
   - What's unclear: Should we update reputation for ALL matching tags, or only one (the "primary" tag)?
   - Recommendation: Update ALL tags. A vote on a "python+django" trace is evidence of competence in both. Use the `domain_tags: list[str]` approach shown in Pattern 3. This aligns with how StackExchange tags work — a highly voted Django answer contributes to both Django and Python reputation.

3. **What happens to reputation if a trace is deleted via the moderation endpoint?**
   - What we know: `DELETE /moderation/traces/{id}` hard-deletes traces with cascade. Votes cascade-delete too.
   - What's unclear: Should reputation be rolled back when a trace is deleted?
   - Recommendation: Do NOT roll back reputation on trace deletion. The reputation was earned at the time of voting; retroactive subtraction creates unexpected behavior and is hard to reason about. Document this as a known limitation. Stack Exchange has the same approach — reputation is not retroactively recalculated when posts are deleted (except for spam/offensive).

4. **Is `GET /api/v1/contributors/{user_id}/reputation` needed, or is reputation returned inline with other contributor data?**
   - What we know: No contributor profile endpoint currently exists.
   - What's unclear: Whether the planner should create a reputation-only endpoint or piggyback on an extended user profile.
   - Recommendation: Create a dedicated read-only `GET /reputation` endpoint. It's simpler to test in isolation and avoids enlarging the auth/user schema in Phase 4.

---

## Sources

### Primary (HIGH confidence)
- Evan Miller, "How Not To Sort By Average Rating" — https://www.evanmiller.org/how-not-to-sort-by-average-rating.html — Wilson score formula, SQL equivalent, rationale
- GitHub Gist (Wilson SQL function) — https://gist.github.com/technetium/de8e58df900c5b11c372346c3d911893 — Verified SQL form of Wilson score lower bound
- PostgreSQL 17 docs, "5.4 Generated Columns" — https://www.postgresql.org/docs/17/ddl-generated-columns.html — Confirmed: cannot reference other tables or aggregates
- PostgreSQL docs, "REFRESH MATERIALIZED VIEW" — https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html — CONCURRENTLY requires UNIQUE index on view; refresh serializes
- Pydantic v2 docs, "Network Types" — https://docs.pydantic.dev/latest/api/networks/ — EmailStr, email-validator requirement confirmed
- SQLAlchemy 2.1 docs, "PostgreSQL Insert" — https://docs.sqlalchemy.org/en/21/dialects/postgresql.html — ON CONFLICT DO UPDATE pattern
- FastAPI official docs, "Dependencies" — https://fastapi.tiangolo.com/tutorial/dependencies/ — RequireEmail dependency pattern

### Secondary (MEDIUM confidence)
- Bakken & Baeck, "Dynamic materialized views in SQLAlchemy" — https://bakkenbaeck.com/tech/dynamic-materialized-views-in-sqlalchemy — Async refresh pattern via `text()` + `execute()`
- Medium (Matthias Gattermeier), "Calculating Better Rating Scores For Things Voted On" — https://medium.com/@gattermeier/calculating-better-rating-scores-for-things-voted-on-7fa3f632c79d — Practical context for Wilson vs naive average

### Tertiary (LOW confidence)
- Research paper (petertsehsun), "Is reputation on Stack Overflow always a good indicator" — https://petertsehsun.github.io/papers/Is_reputation_on_Stack_Overflow_always_a_good_indicator_for_users_expertise_No.pdf — Academic context for per-domain reputation design; not used for implementation decisions

---

## Metadata

**Confidence breakdown:**
- Wilson score formula: HIGH — verified against canonical source (Evan Miller) + independent SQL gist
- PostgreSQL generated column limitation: HIGH — verified against official PostgreSQL 17 docs
- Materialized view CONCURRENTLY requirements: HIGH — verified against PostgreSQL official docs
- ON CONFLICT DO UPDATE pattern: HIGH — verified against SQLAlchemy 2.1 official docs
- RequireEmail dependency pattern: HIGH — straightforward FastAPI dependency injection, verified against official docs
- Per-domain reputation table design: MEDIUM — normalized relational design is standard; specific schema choices (denormalized domain_tag string, separate wilson_score column) are architectural judgment calls consistent with the existing codebase patterns
- BASE_WEIGHT = 0.1 choice: MEDIUM — the need for a measurable difference is specified; 0.1 is a reasonable engineering choice, not a mathematical necessity

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (30 days — stable libraries and mathematical formula)
