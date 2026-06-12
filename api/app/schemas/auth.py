"""Pydantic schemas for API key management and authentication."""

import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class APIKeyCreate(BaseModel):
    """Request schema for creating a new API key / user registration."""

    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, max_length=100)
    invitation_code: Optional[str] = Field(None, min_length=8, max_length=128)


class APIKeyResponse(BaseModel):
    """Response schema after a new API key is generated.

    The api_key is shown exactly once. It is stored only as a hash in the
    database and cannot be retrieved again after this response.
    """

    api_key: str
    user_id: uuid.UUID
    can_contribute: bool = False
    message: str = "Store this key securely -- it cannot be retrieved again"
