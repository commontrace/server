import hashlib
import hmac
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User


def hash_api_key(raw_key: str) -> str:
    """M3: Hash API key with optional HMAC pepper.

    If API_KEY_PEPPER is set, uses HMAC-SHA256 (peppered).
    Falls back to plain SHA-256 for backward compatibility.
    """
    if settings.api_key_pepper:
        return hmac.new(
            settings.api_key_pepper.encode(),
            raw_key.encode(),
            hashlib.sha256,
        ).hexdigest()
    return hashlib.sha256(raw_key.encode()).hexdigest()

# Existing dependency — keep as-is
DbSession = Annotated[AsyncSession, Depends(get_db)]

# API key security scheme — registers in OpenAPI security definition
api_key_header = APIKeyHeader(name=settings.api_key_header_name, auto_error=True)


async def get_redis(request: Request) -> aioredis.Redis:
    """Inject the Redis client from app.state (set during lifespan startup)."""
    return request.app.state.redis


async def get_current_user(
    raw_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a request via X-API-Key header.

    Computes SHA-256 hash of the raw key and looks it up in users.api_key_hash.
    Raises 401 for both missing and invalid keys (no distinction — prevents enumeration).
    """
    key_hash = hash_api_key(raw_key)
    result = await db.execute(select(User).where(User.api_key_hash == key_hash))
    user = result.scalar_one_or_none()

    # M3: backward compat — if pepper is set but key was stored without it, try plain hash
    if user is None and settings.api_key_pepper:
        plain_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        result = await db.execute(select(User).where(User.api_key_hash == plain_hash))
        user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


# Annotated type aliases for clean endpoint signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]


async def require_email(user: User = Depends(get_current_user)) -> User:
    """Gate: requires authenticated user to have a registered email.

    Raises 403 if user.email is None. Implements identity cost (REPU-02):
    anonymous API key usage cannot submit contributions.
    Applied to write paths only — NOT to POST /api/v1/keys or GET endpoints.
    """
    if user.email is None:
        raise HTTPException(
            status_code=403,
            detail="Email registration required to submit contributions. "
                   "Re-register with POST /api/v1/keys providing an email address.",
        )
    return user


RequireEmail = Annotated[User, Depends(require_email)]


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


async def require_moderator(user: User = Depends(get_current_user)) -> User:
    """Gate: requires authenticated user to have moderator privileges.

    Raises 403 if user.is_moderator is False.
    Applied to moderation endpoints (listing flagged, removing traces).
    """
    if not user.is_moderator:
        raise HTTPException(
            status_code=403,
            detail="Moderator privileges required",
        )
    return user


RequireModerator = Annotated[User, Depends(require_moderator)]


def verify_admin_token(x_admin_token: str | None) -> None:
    """Constant-time check of the admin dashboard shared secret.

    Single source of truth for owner-only gating, shared by the admin router
    and the analytics router. Raises 503 if the token env var is unset
    (feature disabled — defense in depth so a misconfigured deploy cannot leak
    data), 401 if the header is missing or wrong.
    """
    if not settings.admin_dashboard_token:
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard disabled. Set ADMIN_DASHBOARD_TOKEN env var.",
        )
    # Encode both sides to bytes before comparing. hmac.compare_digest raises
    # TypeError on str args containing non-ASCII characters; a non-ASCII byte in
    # the configured secret would otherwise surface as a 500 for every request
    # (including the correct token). Bytes-like args have no ASCII restriction
    # and keep the constant-time guarantee.
    if not x_admin_token or not hmac.compare_digest(
        x_admin_token.encode("utf-8"),
        settings.admin_dashboard_token.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid admin token")


async def require_admin_token(
    x_admin_token: str | None = Header(default=None),
) -> None:
    """FastAPI dependency form — gates a route behind the admin token.

    Apply via ``dependencies=[Depends(require_admin_token)]`` so the route
    signature is untouched. Aggregate analytics are owner-only, same secret as
    the admin router.
    """
    verify_admin_token(x_admin_token)
