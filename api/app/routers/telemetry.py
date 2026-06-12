"""Telemetry router — anonymized usage stats from skill clients.

Three endpoints:
  POST /api/v1/telemetry/triggers — per-session trigger effectiveness (opt-in)
  POST /api/v1/telemetry/install  — install beacon (fires once per install)
  POST /api/v1/telemetry/ping     — lightweight heartbeat (daily, updates last_seen)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import WriteRateLimit
from app.models.trigger_stats import TriggerStats
from app.models.user import User

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


# ---------------------------------------------------------------------------
# Trigger stats (unchanged)
# ---------------------------------------------------------------------------


class TriggerStatsBody(BaseModel):
    session_id: str
    trigger_stats: dict
    searches_fired: Optional[int] = Field(default=None, ge=0)
    traces_consumed: Optional[int] = Field(default=None, ge=0)
    resolutions_total: Optional[int] = Field(default=None, ge=0)
    resolutions_assisted: Optional[int] = Field(default=None, ge=0)


class TriggerStatsResponse(BaseModel):
    status: str = "ok"


@router.post("/triggers", response_model=TriggerStatsResponse, status_code=201)
async def report_trigger_stats(
    body: TriggerStatsBody,
    user: CurrentUser,
    db: DbSession,
    _rate: WriteRateLimit,
) -> TriggerStatsResponse:
    """Accept anonymized trigger effectiveness stats from a skill client."""
    record = TriggerStats(
        session_id=body.session_id,
        stats_json=body.trigger_stats,
        searches_fired=body.searches_fired,
        traces_consumed=body.traces_consumed,
        resolutions_total=body.resolutions_total,
        resolutions_assisted=body.resolutions_assisted,
    )
    db.add(record)
    await db.commit()
    return TriggerStatsResponse()


# ---------------------------------------------------------------------------
# Install beacon
# ---------------------------------------------------------------------------


class InstallBody(BaseModel):
    platform: Optional[str] = Field(default=None, max_length=50)
    skill_version: Optional[str] = Field(default=None, max_length=20)
    install_source: Optional[str] = Field(default=None, max_length=50)


def _country_from_request(request: Request) -> Optional[str]:
    """Extract 2-letter country code from common CDN headers."""
    for header in ("CF-IPCountry", "X-Vercel-IP-Country", "X-Country-Code"):
        val = request.headers.get(header)
        if val and len(val) == 2 and val.isalpha():
            return val.upper()
    return None


@router.post("/install", status_code=201)
async def report_install(
    body: InstallBody,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    """Record install metadata. Idempotent — overwrites prior values."""
    now = datetime.now(timezone.utc)
    country = _country_from_request(request)
    stmt = (
        update(User)
        .where(User.id == user.id)
        .values(
            platform=body.platform,
            skill_version=body.skill_version,
            install_source=body.install_source,
            last_seen_at=now,
            country_code=country if country else User.country_code,
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Heartbeat / DAU ping
# ---------------------------------------------------------------------------


@router.post("/ping", status_code=204)
async def ping(
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """Lightweight heartbeat — bumps last_seen_at. Skill calls this once per
    session start (locally rate-limited to once per day per install).
    """
    now = datetime.now(timezone.utc)
    country = _country_from_request(request)
    stmt = (
        update(User)
        .where(User.id == user.id)
        .values(
            last_seen_at=now,
            country_code=country if country else User.country_code,
        )
    )
    await db.execute(stmt)
    await db.commit()
