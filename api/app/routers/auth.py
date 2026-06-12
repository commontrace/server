"""API key generation and authentication verification endpoints.

POST /api/v1/keys  -- generate a new API key (no auth required)
GET  /api/v1/keys/verify -- verify an existing API key (auth required)
"""

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

router = APIRouter(prefix="/api/v1", tags=["auth"])

# Invites granted when an invitation is redeemed at registration time —
# keep in sync with REDEEM_GRANT_INVITES in app/routers/invitations.py
REGISTRATION_GRANT_INVITES = 2


@router.post("/keys", response_model=APIKeyResponse, status_code=201)
async def generate_api_key(
    body: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
) -> APIKeyResponse:
    """Generate a new API key and register a user account.

    The raw API key is returned exactly once in this response. Only its
    SHA-256 hash is stored in the database; it cannot be retrieved again.

    If an email is provided and already exists in the database, a 409
    Conflict is returned. On the astronomically unlikely event of a hash
    collision, one automatic retry is performed with a freshly generated key.
    """
    # If email provided, check for existing account
    if body.email:
        result = await db.execute(select(User).where(User.email == body.email))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

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

    raw_key = secrets.token_urlsafe(32)
    user = _make_user(raw_key)
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        # Hash collision on api_key_hash (astronomically unlikely) — retry once
        await db.rollback()
        raw_key = secrets.token_urlsafe(32)
        user = _make_user(raw_key)
        db.add(user)
        await db.commit()

    await db.refresh(user)

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


@router.get("/keys/verify")
async def verify_api_key(user: CurrentUser) -> dict:
    """Verify that the provided API key is valid.

    Returns the authenticated user's ID. Primarily for testing that
    authentication is functioning correctly.
    """
    return {"valid": True, "user_id": str(user.id)}
