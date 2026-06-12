# Contribution Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce spec §6.4 — trace and amendment writes require an invitation-granted contributor account; reading, search, and voting stay open to every key.

**Architecture:** New `invitations` table plus four gate columns on `users`. A `require_contributor` FastAPI dependency (chained after `require_email`) returns 403 on publish endpoints for non-contributors. Invitation mint/redeem endpoints use single atomic UPDATEs (burn guarded by `invites_remaining > 0`, claim guarded by `redeemed_by IS NULL`) so there is no TOCTOU window. Three doors: **vouched** (peer mint), **earned** (admin grant after Keeper review), **founding** (admin mint + migration backfill of existing contributors).

**Tech Stack:** FastAPI, SQLAlchemy 2.x async (asyncpg), Alembic, PostgreSQL.

**Scope notes:**
- Out of scope: skill-side changes (the Stop hook already falls back to `~/.commontrace/pending/` on HTTP errors — a 403 queues the candidate locally, nothing is lost), lineage visualization, earned-review UI, quarantine reactivation.
- Work directly on `main` in `/home/denem/commontrace` (user-approved for this repo). One commit per task. **NEVER `git push` — production auto-deploys from origin/main.**
- This repo has no DB test harness (`api/tests/` contains only `test_wilson_score.py`). Verification is `py_compile` per task plus the full e2e curl flow in Task 5 against the local docker stack — consistent with how every prior feature in this repo was verified.

**Existing patterns you must reuse (do not reinvent):**
- `hash_api_key(raw)` in `api/app/dependencies.py:16` — HMAC-SHA256 with optional pepper, falls back to SHA-256. Invitation codes are hashed with this same function; raw codes are shown exactly once.
- `RequireEmail` / `RequireModerator` Annotated-alias pattern in `api/app/dependencies.py:86,103`.
- `WriteRateLimit` from `app.middleware.rate_limiter` (see `api/app/routers/traces.py:14`).
- Admin endpoints: `X-Admin-Token` header + `_check_token()` + raw `text()` SQL (see `api/app/routers/admin.py:31-46`).
- Migration chain head: `0019_user_telemetry.py`, revision `190a1b2c3d4e`.

---

### Task 1: Schema — invitations table + user gate fields + founding backfill

**Files:**
- Create: `api/app/models/invitation.py`
- Modify: `api/app/models/user.py`
- Modify: `api/app/models/__init__.py`
- Create: `api/migrations/versions/0020_contribution_gate.py`

- [ ] **Step 1: Create the Invitation model**

Create `api/app/models/invitation.py`:

```python
"""Invitation model — contribution gate (spec §6.4).

An invitation is minted by an existing contributor (or the admin), carries
a hashed one-time code, and records lineage: who created it, who redeemed
it, and through which door (vouched / earned / founding) the redeemer
entered the commons.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    redeemed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    door: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="vouched"
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Add gate fields to the User model**

In `api/app/models/user.py`, change the import line (line 5) from:

```python
from sqlalchemy import Boolean, DateTime, Float, String, func
```

to:

```python
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
```

Then insert after the `install_source` column (line 43) and before the `# Relationships` comment:

```python
    # Contribution gate (spec §6.4) — publishing requires an invitation.
    # Reading and search stay open; can_contribute gates writes only.
    can_contribute: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    entry_door: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    invites_remaining: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
```

- [ ] **Step 3: Export Invitation from the models package**

In `api/app/models/__init__.py`, add after the `from .rif_shadow import RifShadow` line:

```python
from .invitation import Invitation
```

and add `"Invitation",` to `__all__` (after `"RifShadow",`).

- [ ] **Step 4: Create migration 0020**

Create `api/migrations/versions/0020_contribution_gate.py`:

```python
"""Contribution gate: invitations table + user gate fields (spec §6.4).

Revision ID: 200a1b2c3d4e
Revises: 190a1b2c3d4e
Create Date: 2026-06-11 12:00:00.000000

Adds can_contribute / entry_door / invited_by / invites_remaining to users,
creates the invitations table, and backfills existing contributors (seed
users, moderators, anyone who has already submitted a trace) as founding
contributors with 2 invites — the gate must never lock out the people who
built the current corpus.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "200a1b2c3d4e"
down_revision: str = "190a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_contribute",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("entry_door", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "invites_remaining",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "door", sa.String(length=16), nullable=False, server_default="vouched"
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invitations_created_by", "invitations", ["created_by"])

    # Founding backfill — existing contributors keep publishing rights.
    op.execute(
        "UPDATE users SET can_contribute = true, entry_door = 'founding', "
        "invites_remaining = 2 "
        "WHERE is_seed = true OR is_moderator = true OR id IN "
        "(SELECT DISTINCT contributor_id FROM traces WHERE contributor_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_index("ix_invitations_created_by", table_name="invitations")
    op.drop_table("invitations")
    op.drop_column("users", "invites_remaining")
    op.drop_column("users", "invited_by")
    op.drop_column("users", "entry_door")
    op.drop_column("users", "can_contribute")
```

- [ ] **Step 5: Syntax-check all four files**

Run from `/home/denem/commontrace/api`:

```bash
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app/models/invitation.py', 'app/models/user.py', 'app/models/__init__.py', 'migrations/versions/0020_contribution_gate.py']]" && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`

- [ ] **Step 6: Commit**

```bash
cd /home/denem/commontrace
git add api/app/models/invitation.py api/app/models/user.py api/app/models/__init__.py api/migrations/versions/0020_contribution_gate.py
git commit -m "feat(gate): invitations table + user gate fields, founding backfill (spec §6.4)"
```

---

### Task 2: Gate dependency — RequireContributor on trace + amendment writes

**Files:**
- Modify: `api/app/dependencies.py`
- Modify: `api/app/routers/traces.py`
- Modify: `api/app/routers/amendments.py`

- [ ] **Step 1: Add require_contributor to dependencies.py**

In `api/app/dependencies.py`, insert after the `RequireEmail = Annotated[User, Depends(require_email)]` line (line 86) and before `require_moderator`:

```python
async def require_contributor(user: User = Depends(require_email)) -> User:
    """Gate: requires an invitation-granted contributor account (spec §6.4).

    Chains require_email — publishing needs both a registered email and
    can_contribute=true. Reading, search, and voting stay open to every
    authenticated key; only publishing (traces, amendments) is gated.
    """
    if not user.can_contribute:
        raise HTTPException(
            status_code=403,
            detail="Contribution requires an invitation. Reading and search remain "
            "open to everyone, and your agent keeps capturing knowledge locally. "
            "Redeem an invitation code via POST /api/v1/invitations/redeem "
            "to unlock publishing.",
        )
    return user


RequireContributor = Annotated[User, Depends(require_contributor)]
```

- [ ] **Step 2: Gate trace submission**

In `api/app/routers/traces.py`:
- Line 13: change `from app.dependencies import CurrentUser, DbSession, RequireEmail` to `from app.dependencies import CurrentUser, DbSession, RequireContributor` — but first `grep -n "RequireEmail" api/app/routers/traces.py`; if `RequireEmail` appears anywhere besides line 13 and the `submit_trace` signature, keep it in the import list too.
- In `submit_trace` (line 32): change `user: RequireEmail,` to `user: RequireContributor,`.
- Update the docstring line `1. Authentication (RequireEmail dependency — email required for contributions)` to `1. Authentication (RequireContributor dependency — invitation + email required, spec §6.4)`.

- [ ] **Step 3: Gate amendment submission**

In `api/app/routers/amendments.py`:
- Line 11: change `from app.dependencies import CurrentUser, DbSession, RequireEmail` to `from app.dependencies import CurrentUser, DbSession, RequireContributor` — same grep check as Step 2; also check whether `CurrentUser` is actually used in this file and drop it from the import if not.
- In `submit_amendment` (line 29): change `user: RequireEmail,` to `user: RequireContributor,`.

- [ ] **Step 4: Syntax-check**

Run from `/home/denem/commontrace/api`:

```bash
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app/dependencies.py', 'app/routers/traces.py', 'app/routers/amendments.py']]" && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`

- [ ] **Step 5: Commit**

```bash
cd /home/denem/commontrace
git add api/app/dependencies.py api/app/routers/traces.py api/app/routers/amendments.py
git commit -m "feat(gate): RequireContributor dependency gates trace + amendment writes"
```

---

### Task 3: Invitation endpoints — mint / redeem / list

**Files:**
- Create: `api/app/schemas/invitation.py`
- Create: `api/app/routers/invitations.py`
- Modify: `api/app/main.py`

- [ ] **Step 1: Create the invitation schemas**

Create `api/app/schemas/invitation.py`:

```python
"""Pydantic schemas for invitation endpoints (contribution gate, spec §6.4)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InvitationMintRequest(BaseModel):
    """Request schema for minting a new invitation code."""

    note: Optional[str] = Field(None, max_length=255)


class InvitationMintResponse(BaseModel):
    """Response after minting. The raw code is shown exactly once."""

    code: str
    door: str
    invites_remaining: int
    message: str = (
        "Share this code privately -- it can be redeemed exactly once "
        "and cannot be retrieved again"
    )


class InvitationRedeemRequest(BaseModel):
    """Request schema for redeeming an invitation code."""

    code: str = Field(..., min_length=8, max_length=128)


class InvitationRedeemResponse(BaseModel):
    """Response after a successful redemption."""

    can_contribute: bool
    entry_door: Optional[str]
    invites_remaining: int


class InvitationListItem(BaseModel):
    """One invitation minted by the caller. Raw codes are never re-shown."""

    id: uuid.UUID
    door: str
    note: Optional[str]
    created_at: datetime
    redeemed: bool


class InvitationListResponse(BaseModel):
    invitations: list[InvitationListItem]
    invites_remaining: int
```

- [ ] **Step 2: Create the invitations router**

Create `api/app/routers/invitations.py`:

```python
"""Invitation endpoints — contribution gate (spec §6.4).

POST /api/v1/invitations         -- mint a code (contributors only, burns an invite)
POST /api/v1/invitations/redeem  -- redeem a code (unlocks publishing)
GET  /api/v1/invitations         -- list own minted invitations + balance
"""

import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, update

from app.dependencies import CurrentUser, DbSession, RequireContributor, hash_api_key
from app.middleware.rate_limiter import WriteRateLimit
from app.models.invitation import Invitation
from app.models.user import User
from app.schemas.invitation import (
    InvitationListItem,
    InvitationListResponse,
    InvitationMintRequest,
    InvitationMintResponse,
    InvitationRedeemRequest,
    InvitationRedeemResponse,
)

router = APIRouter(prefix="/api/v1", tags=["invitations"])

INVITE_CODE_PREFIX = "ctinv_"
# Invites granted to a newly redeemed contributor (spec §6.4: 2-3 per member,
# replenished by confirmed-helpful contributions)
REDEEM_GRANT_INVITES = 2


def generate_invite_code() -> str:
    return INVITE_CODE_PREFIX + secrets.token_urlsafe(16)


@router.post("/invitations", response_model=InvitationMintResponse, status_code=201)
async def mint_invitation(
    body: InvitationMintRequest,
    user: RequireContributor,
    db: DbSession,
    _rate: WriteRateLimit,
) -> InvitationMintResponse:
    """Mint a one-time invitation code, spending one invite.

    Moderators mint without spending. The burn is a single atomic UPDATE
    guarded by invites_remaining > 0 — two concurrent mints cannot
    double-spend the same invite.
    """
    invites_remaining = user.invites_remaining
    if not user.is_moderator:
        result = await db.execute(
            update(User)
            .where(User.id == user.id, User.invites_remaining > 0)
            .values(invites_remaining=User.invites_remaining - 1)
            .returning(User.invites_remaining)
        )
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=403,
                detail="No invites remaining. Invites replenish when your "
                "contributions are confirmed helpful by other agents.",
            )
        invites_remaining = row[0]

    raw_code = generate_invite_code()
    invitation = Invitation(
        code_hash=hash_api_key(raw_code),
        created_by=user.id,
        door="vouched",
        note=body.note,
    )
    db.add(invitation)
    await db.commit()

    return InvitationMintResponse(
        code=raw_code,
        door="vouched",
        invites_remaining=invites_remaining,
    )


@router.post("/invitations/redeem", response_model=InvitationRedeemResponse)
async def redeem_invitation(
    body: InvitationRedeemRequest,
    user: CurrentUser,
    db: DbSession,
) -> InvitationRedeemResponse:
    """Redeem an invitation code, unlocking publishing for the caller.

    The claim is a single atomic UPDATE guarded by redeemed_by IS NULL —
    two concurrent redemptions of the same code cannot both succeed.
    """
    if user.can_contribute:
        raise HTTPException(status_code=409, detail="Account is already a contributor")

    code_hash = hash_api_key(body.code)
    result = await db.execute(
        update(Invitation)
        .where(Invitation.code_hash == code_hash, Invitation.redeemed_by.is_(None))
        .values(redeemed_by=user.id, redeemed_at=func.now())
        .returning(Invitation.created_by, Invitation.door)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404, detail="Invalid or already-redeemed invitation code"
        )
    created_by, door = row

    if created_by == user.id:
        # Defense in depth — a non-contributor cannot normally mint, but a
        # demoted account must not re-enter through its own old invite.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot redeem your own invitation")

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            can_contribute=True,
            entry_door=door,
            invited_by=created_by,
            invites_remaining=REDEEM_GRANT_INVITES,
        )
    )
    await db.commit()

    return InvitationRedeemResponse(
        can_contribute=True,
        entry_door=door,
        invites_remaining=REDEEM_GRANT_INVITES,
    )


@router.get("/invitations", response_model=InvitationListResponse)
async def list_invitations(
    user: CurrentUser,
    db: DbSession,
) -> InvitationListResponse:
    """List invitations minted by the caller. Raw codes are never re-shown."""
    result = await db.execute(
        select(Invitation)
        .where(Invitation.created_by == user.id)
        .order_by(Invitation.created_at.desc())
    )
    invitations = result.scalars().all()
    return InvitationListResponse(
        invitations=[
            InvitationListItem(
                id=inv.id,
                door=inv.door,
                note=inv.note,
                created_at=inv.created_at,
                redeemed=inv.redeemed_by is not None,
            )
            for inv in invitations
        ],
        invites_remaining=user.invites_remaining,
    )
```

**IMPORTANT:** `redeemed_at=func.now()` uses `func` imported from `sqlalchemy` at the top of the file. Do NOT invent a `func_now` symbol — it does not exist.

- [ ] **Step 3: Register the router in main.py**

In `api/app/main.py`:
- Line 15: change the routers import to include `invitations` (alphabetical):

```python
from app.routers import admin, amendments, analytics, auth, invitations, moderation, reputation, search, tags, telemetry, traces, votes
```

- After `app.include_router(amendments.router)` (line 96), add:

```python
# Invitations router (contribution gate, spec §6.4)
app.include_router(invitations.router)
```

- [ ] **Step 4: Syntax-check**

Run from `/home/denem/commontrace/api`:

```bash
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app/schemas/invitation.py', 'app/routers/invitations.py', 'app/main.py']]" && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`

- [ ] **Step 5: Commit**

```bash
cd /home/denem/commontrace
git add api/app/schemas/invitation.py api/app/routers/invitations.py api/app/main.py
git commit -m "feat(gate): invitation mint/redeem/list endpoints -- atomic burn and claim"
```

---

### Task 4: Registration-time redemption, admin mint/grant, invite replenishment

**Files:**
- Modify: `api/app/schemas/auth.py`
- Modify: `api/app/routers/auth.py`
- Modify: `api/app/routers/admin.py`
- Modify: `api/app/services/trust.py`

- [ ] **Step 1: Extend auth schemas**

In `api/app/schemas/auth.py`, change `APIKeyCreate` to:

```python
class APIKeyCreate(BaseModel):
    """Request schema for creating a new API key / user registration."""

    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, max_length=100)
    invitation_code: Optional[str] = Field(None, min_length=8, max_length=128)
```

and add `can_contribute: bool = False` to `APIKeyResponse` after `user_id`.

- [ ] **Step 2: Registration-time redemption in auth.py**

Rewrite `api/app/routers/auth.py` `generate_api_key` as follows. Replace the imports block (lines 7-17) with:

```python
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, hash_api_key
from app.models.invitation import Invitation
from app.models.user import User
from app.schemas.auth import APIKeyCreate, APIKeyResponse
```

Add after `router = APIRouter(...)`:

```python
# Invites granted when an invitation is redeemed at registration time —
# keep in sync with REDEEM_GRANT_INVITES in app/routers/invitations.py
REGISTRATION_GRANT_INVITES = 2
```

Inside `generate_api_key`, after the existing email-conflict check and before `def _make_user`, insert:

```python
    # Contribution gate (spec §6.4): optionally redeem an invitation at
    # registration time. Pre-validate loudly — a bad code must fail the
    # request, not silently create an ungated account.
    invitation = None
    if body.invitation_code:
        inv_hash = hash_api_key(body.invitation_code)
        result = await db.execute(
            select(Invitation).where(
                Invitation.code_hash == inv_hash,
                Invitation.redeemed_by.is_(None),
            )
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise HTTPException(
                status_code=422, detail="Invalid or already-redeemed invitation code"
            )
```

Change `_make_user` to:

```python
    def _make_user(raw_key: str) -> User:
        key_hash = hash_api_key(raw_key)
        user = User(
            api_key_hash=key_hash,
            email=body.email,
            display_name=body.display_name,
        )
        if invitation is not None:
            user.can_contribute = True
            user.entry_door = invitation.door
            user.invited_by = invitation.created_by
            user.invites_remaining = REGISTRATION_GRANT_INVITES
        return user
```

After `await db.refresh(user)`, replace the final `return` with:

```python
    if invitation is not None:
        # Atomic claim — guards the race where the same code is redeemed
        # between our pre-validation and this point.
        claim = await db.execute(
            update(Invitation)
            .where(Invitation.id == invitation.id, Invitation.redeemed_by.is_(None))
            .values(redeemed_by=user.id, redeemed_at=func.now())
        )
        if claim.rowcount == 0:
            # Lost the race: remove the just-created account so the client
            # can retry cleanly with a fresh code.
            await db.delete(user)
            await db.commit()
            raise HTTPException(
                status_code=422,
                detail="Invitation code was redeemed by another request",
            )
        await db.commit()

    return APIKeyResponse(
        api_key=raw_key,
        user_id=user.id,
        can_contribute=user.can_contribute,
    )
```

- [ ] **Step 3: Admin founding mint + direct contributor grant**

In `api/app/routers/admin.py`:

Add to the imports (keep existing ones):

```python
import uuid

from pydantic import BaseModel, Field

from app.dependencies import hash_api_key
from app.routers.invitations import generate_invite_code
```

Add after `_check_token`:

```python
class AdminInvitationMint(BaseModel):
    count: int = Field(1, ge=1, le=100)
    door: str = Field("founding", pattern="^(founding|vouched)$")
    note: str | None = Field(None, max_length=255)


class AdminContributorGrant(BaseModel):
    door: str = Field("earned", pattern="^(earned|founding)$")
```

Add the two endpoints at the end of the file:

```python
@router.post("/invitations", status_code=201)
async def admin_mint_invitations(
    body: AdminInvitationMint,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Mint founding/vouched invitation codes (admin only).

    Codes are attributed to the oldest moderator account so lineage always
    points at a real user. Raw codes are returned exactly once.
    """
    _check_token(x_admin_token)

    row = (
        await db.execute(
            text(
                "SELECT id FROM users WHERE is_moderator = true "
                "ORDER BY created_at ASC LIMIT 1"
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="No moderator account exists to attribute invitations to",
        )
    created_by = row[0]

    codes = []
    for _ in range(body.count):
        raw_code = generate_invite_code()
        await db.execute(
            text(
                "INSERT INTO invitations (id, code_hash, created_by, door, note) "
                "VALUES (:id, :code_hash, :created_by, :door, :note)"
            ),
            {
                "id": uuid.uuid4(),
                "code_hash": hash_api_key(raw_code),
                "created_by": created_by,
                "door": body.door,
                "note": body.note,
            },
        )
        codes.append(raw_code)
    await db.commit()

    return {"codes": codes, "door": body.door, "count": len(codes)}


@router.post("/contributors/{user_id}", status_code=200)
async def admin_grant_contributor(
    user_id: str,
    body: AdminContributorGrant,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Grant contributor status directly — the earned door (Wanted Board
    quest reviewed by a Keeper) or founding door for hand-picked contributors."""
    _check_token(x_admin_token)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user id")

    row = (
        await db.execute(
            text(
                "UPDATE users SET can_contribute = true, entry_door = :door, "
                "invites_remaining = GREATEST(invites_remaining, 2) "
                "WHERE id = :uid RETURNING id, invites_remaining"
            ),
            {"door": body.door, "uid": uid},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()

    return {"user_id": str(row[0]), "door": body.door, "invites_remaining": row[1]}
```

- [ ] **Step 4: Invite replenishment on trace validation**

In `api/app/services/trust.py`:

Add `from app.models.user import User` to the imports (check the existing import block first — `update` and `select` are already imported).

Add near `BASE_WEIGHT` (line 132):

```python
# Replenishment cap (spec §6.4): confirmed-helpful contributions refill
# invites up to this many, never beyond.
MAX_INVITES = 3
```

In `apply_vote_to_trace`, change the re-query (lines 100-104) to also select the contributor:

```python
    result = await db.execute(
        select(
            Trace.status, Trace.confirmation_count, Trace.trust_score, Trace.contributor_id
        ).where(Trace.id == trace_id)
    )
    row = result.one_or_none()
    if row is None:
        return

    status, confirmation_count, trust_score, contributor_id = row
```

Replace the promotion block (lines 116-126) with:

```python
    # Promote if pending, threshold reached, and net positive trust
    if (
        status == TraceStatus.pending
        and confirmation_count >= threshold
        and trust_score > 0
    ):
        promo = await db.execute(
            update(Trace)
            .where(Trace.id == trace_id, Trace.status == TraceStatus.pending)
            .values(status=TraceStatus.validated)
            .execution_options(synchronize_session=False)
        )
        # Invite replenishment (spec §6.4): a confirmed-helpful contribution
        # refills one invite, capped at MAX_INVITES. The status guard in the
        # UPDATE makes promotion fire exactly once per trace, so concurrent
        # votes cannot double-grant.
        if promo.rowcount == 1 and contributor_id is not None:
            await db.execute(
                update(User)
                .where(User.id == contributor_id, User.invites_remaining < MAX_INVITES)
                .values(invites_remaining=User.invites_remaining + 1)
                .execution_options(synchronize_session=False)
            )
```

- [ ] **Step 5: Syntax-check**

Run from `/home/denem/commontrace/api`:

```bash
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['app/schemas/auth.py', 'app/routers/auth.py', 'app/routers/admin.py', 'app/services/trust.py']]" && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`

- [ ] **Step 6: Commit**

```bash
cd /home/denem/commontrace
git add api/app/schemas/auth.py api/app/routers/auth.py api/app/routers/admin.py api/app/services/trust.py
git commit -m "feat(gate): registration-time redemption, admin founding mint, earned grant, invite replenishment"
```

---

### Task 5: End-to-end verification against the local docker stack

**Files:** none (verification only — no commit)

The repo root has `docker-compose.yml` with `postgres` (pgvector/pg17, user/pass/db all `commontrace`), `redis`, and `api` (runs `alembic upgrade head && uvicorn` on port 8000, reads `.env`). Docker is available on this machine.

- [ ] **Step 1: Start the stack with fresh code**

```bash
cd /home/denem/commontrace
grep -q ADMIN_DASHBOARD_TOKEN .env || echo 'ADMIN_DASHBOARD_TOKEN=local-e2e-token' >> .env
docker compose up -d --build postgres redis api
sleep 20 && docker compose ps
```

Expected: `api` healthy. If the api container crash-loops, run `docker compose logs api --tail 50` — a migration error here means Task 1 has a bug; fix it before continuing. **Never commit `.env`.**

Note the actual token: `TOK=$(grep ADMIN_DASHBOARD_TOKEN .env | cut -d= -f2)`

- [ ] **Step 2: Register an uninvited user — expect open registration but no publishing**

```bash
curl -s -X POST localhost:8000/api/v1/keys -H 'Content-Type: application/json' \
  -d '{"email":"gate-test-a@example.com"}'
```

Expected: 201 with `"can_contribute": false`. Save the key as `KEY_A`, the user_id as `UID_A`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/v1/traces \
  -H "X-API-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{"title":"Gate e2e probe","context_text":"Testing the contribution gate end to end","solution_text":"This submission must be rejected with 403","tags":["testing"]}'
```

Expected: `403`. Re-run without `-o /dev/null` to confirm the detail mentions "Contribution requires an invitation".

- [ ] **Step 3: Seed a moderator and mint founding codes via admin**

```bash
docker compose exec postgres psql -U commontrace -c \
  "UPDATE users SET is_moderator = true WHERE email = 'gate-test-a@example.com';"
curl -s -X POST localhost:8000/api/v1/admin/invitations \
  -H "X-Admin-Token: $TOK" -H 'Content-Type: application/json' \
  -d '{"count":2,"door":"founding"}'
```

Expected: 201 with 2 raw codes (`ctinv_...`). Save as `CODE1`, `CODE2`.

- [ ] **Step 4: Redeem and verify publishing unlocks**

```bash
curl -s -X POST localhost:8000/api/v1/invitations/redeem \
  -H "X-API-Key: $KEY_A" -H 'Content-Type: application/json' -d "{\"code\":\"$CODE1\"}"
```

Expected: 200, `can_contribute: true`, `entry_door: "founding"`, `invites_remaining: 2`.

Re-run the trace POST from Step 2. Expected: `202`.

- [ ] **Step 5: Registration-time redemption**

```bash
curl -s -X POST localhost:8000/api/v1/keys -H 'Content-Type: application/json' \
  -d "{\"email\":\"gate-test-c@example.com\",\"invitation_code\":\"$CODE2\"}"
```

Expected: 201 with `"can_contribute": true`. Save key as `KEY_C`.

- [ ] **Step 6: Double-redeem rejected**

```bash
curl -s -X POST localhost:8000/api/v1/keys -H 'Content-Type: application/json' \
  -d "{\"email\":\"gate-test-d@example.com\",\"invitation_code\":\"$CODE2\"}"
```

Expected: `422` "Invalid or already-redeemed invitation code". Also redeem `$CODE2` via `/invitations/redeem` with a fresh uninvited key — expected `404`.

- [ ] **Step 7: Peer mint burns invites; exhaustion returns 403**

```bash
curl -s -X POST localhost:8000/api/v1/invitations -H "X-API-Key: $KEY_C" \
  -H 'Content-Type: application/json' -d '{"note":"e2e burn 1"}'   # expect 201, invites_remaining 1
curl -s -X POST localhost:8000/api/v1/invitations -H "X-API-Key: $KEY_C" \
  -H 'Content-Type: application/json' -d '{"note":"e2e burn 2"}'   # expect 201, invites_remaining 0
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/v1/invitations \
  -H "X-API-Key: $KEY_C" -H 'Content-Type: application/json' -d '{}'  # expect 403
curl -s localhost:8000/api/v1/invitations -H "X-API-Key: $KEY_C"      # expect 2 items, codes not shown
```

- [ ] **Step 8: Admin direct grant (earned door)**

Register one more uninvited user (`gate-test-e@example.com`, save `UID_E` from the response), then:

```bash
curl -s -X POST "localhost:8000/api/v1/admin/contributors/$UID_E" \
  -H "X-Admin-Token: $TOK" -H 'Content-Type: application/json' -d '{"door":"earned"}'
```

Expected: 200, `invites_remaining: 2`. A trace POST with E's key now returns `202`.

- [ ] **Step 9: Bad code at registration fails loudly**

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/v1/keys \
  -H 'Content-Type: application/json' \
  -d '{"email":"gate-test-f@example.com","invitation_code":"ctinv_definitely_garbage"}'
```

Expected: `422`.

- [ ] **Step 10: Tear down and report**

```bash
docker compose down
git -C /home/denem/commontrace log --oneline -5
```

Report every expected-vs-actual from Steps 2-9. If docker was unavailable or any step could not run, say so explicitly — never claim an unverified step passed.

---

## Self-review notes

- **Three doors covered:** vouched = peer mint (Task 3), earned = admin grant (Task 4 Step 3), founding = admin mint + migration backfill (Tasks 4 + 1). Spec §6.4 satisfied.
- **Reading/search/voting untouched** — only `submit_trace` and `submit_amendment` change dependencies. `pattern_synthesis.py` system traces insert directly via DB and are unaffected.
- **No TOCTOU:** burn and claim are single guarded UPDATEs with RETURNING; registration-time claim has an explicit race fallback that deletes the half-created account.
- **Skill compatibility:** the Stop hook catches `HTTPError` and falls through to `_write_pending()` (stop.py:936-958) — gated agents queue knowledge locally; the 403 message says exactly that. No skill release required.
- **Deliberate gaps (recorded, not forgotten):** no DB unit tests (repo has no harness — e2e is the repo-consistent verification); no lineage visualization; no invitation revocation endpoint; quarantine stays off per founder decision 2026-06-10.
- **Type consistency check:** `RequireContributor` defined Task 2, used Tasks 2-3; `generate_invite_code` defined Task 3, imported Task 4; `hash_api_key` existing; `REDEEM_GRANT_INVITES`/`REGISTRATION_GRANT_INVITES` both 2 with cross-reference comments; `MAX_INVITES` 3 used only in trust.py. Consistent.
