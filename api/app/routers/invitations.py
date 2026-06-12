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
