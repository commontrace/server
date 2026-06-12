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
