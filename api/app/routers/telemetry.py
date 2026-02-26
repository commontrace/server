"""Telemetry router — anonymized usage stats from skill clients."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession
from app.models.trigger_stats import TriggerStats

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


class TriggerStatsBody(BaseModel):
    session_id: str
    trigger_stats: dict


class TriggerStatsResponse(BaseModel):
    status: str = "ok"


@router.post("/triggers", response_model=TriggerStatsResponse, status_code=201)
async def report_trigger_stats(
    body: TriggerStatsBody,
    user: CurrentUser,
    db: DbSession,
) -> TriggerStatsResponse:
    """Accept anonymized trigger effectiveness stats from a skill client.

    Payload: {"session_id": "...", "trigger_stats": {"bash_error": {"total": 5, "consumed": 2, "rate": 0.4}, ...}}

    No rate limiting — this fires once per session at most.
    """
    record = TriggerStats(
        session_id=body.session_id,
        stats_json=body.trigger_stats,
    )
    db.add(record)
    await db.commit()
    return TriggerStatsResponse()
