"""Moderation endpoints: flagging traces, listing flagged traces, and removing harmful content.

Implements SAFE-03: any agent can flag a trace; moderators can remove it.
Listing flagged traces and removing traces require is_moderator=True (security audit C1).
"""
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession, RequireModerator
from app.middleware.rate_limiter import ReadRateLimit, WriteRateLimit
from app.models.amendment import Amendment
from app.models.trace import Trace
from app.models.vote import Vote
from app.schemas.trace import TraceResponse

router = APIRouter(prefix="/api/v1", tags=["moderation"])


class FlagRequest(BaseModel):
    """Request body for flagging a trace."""

    reason: str = Field(min_length=1, max_length=1000)
    category: Literal["harmful", "spam", "incorrect", "duplicate"]


# ---------------------------------------------------------------------------
# POST /api/v1/traces/{trace_id}/flag
# ---------------------------------------------------------------------------


@router.post("/traces/{trace_id}/flag")
async def flag_trace(
    trace_id: uuid.UUID,
    body: FlagRequest,
    current_user: CurrentUser,
    db: DbSession,
    _rate: WriteRateLimit,
) -> dict:
    """Flag a trace as harmful, spam, incorrect, or duplicate.

    Idempotent: flagging an already-flagged trace returns 200 without error.
    """
    result = await db.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()

    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    # M8: Prevent same user from flagging same trace twice.
    # Use metadata_json to track flagging users (lightweight, no migration needed).
    flag_meta = trace.metadata_json or {}
    flagged_by = flag_meta.get("_flagged_by", [])
    user_id_str = str(current_user.id)

    if user_id_str in flagged_by:
        return {
            "trace_id": str(trace_id),
            "flagged": trace.is_flagged,
            "category": body.category,
            "message": "You have already flagged this trace",
        }

    flagged_by.append(user_id_str)
    flag_meta["_flagged_by"] = flagged_by

    # Mark as flagged using an atomic UPDATE (avoids stale ORM state)
    await db.execute(
        update(Trace)
        .where(Trace.id == trace_id)
        .values(
            is_flagged=True,
            flagged_at=func.now(),
            metadata_json=flag_meta,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return {
        "trace_id": str(trace_id),
        "flagged": True,
        "category": body.category,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/moderation/flagged
# ---------------------------------------------------------------------------


@router.get("/moderation/flagged", response_model=list[TraceResponse])
async def list_flagged_traces(
    current_user: RequireModerator,
    db: DbSession,
    _rate: ReadRateLimit,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[TraceResponse]:
    """List all flagged traces, newest-first, with pagination.

    Returns full TraceResponse objects so moderators have full context.
    """
    result = await db.execute(
        select(Trace)
        .where(Trace.is_flagged == True)  # noqa: E712
        .options(selectinload(Trace.tags))
        .order_by(Trace.flagged_at.desc())
        .limit(limit)
        .offset(offset)
    )
    traces = result.scalars().all()

    # Serialize tags as list of name strings (TraceResponse.tags expects list[str])
    output = []
    for trace in traces:
        data = TraceResponse.model_validate(trace)
        data.tags = [tag.name for tag in trace.tags]
        output.append(data)

    return output


# ---------------------------------------------------------------------------
# DELETE /api/v1/moderation/traces/{trace_id}
# ---------------------------------------------------------------------------


@router.delete("/moderation/traces/{trace_id}")
async def remove_trace(
    trace_id: uuid.UUID,
    current_user: RequireModerator,
    db: DbSession,
    _rate: WriteRateLimit,
) -> dict:
    """Hard-delete a trace and all its related records.

    Deletes in dependency order (no cascade FKs in schema). Every table that
    carries an FK to traces.id must be cleared first or the final delete raises
    ForeignKeyViolation (surfaces as 500):
      1. votes
      2. amendments (via original_trace_id FK)
      3. trace_tags association rows
      4. retrieval_logs (trace_id FK)
      5. rif_shadows (loser_trace_id / winner_trace_id FKs)
      6. trace_relationships (source_trace_id / target_trace_id FKs)
      7. the trace itself
    """
    result = await db.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()

    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    # 1. Delete votes referencing this trace
    await db.execute(delete(Vote).where(Vote.trace_id == trace_id))

    # 2. Delete amendments referencing this trace (original_trace_id FK)
    await db.execute(
        delete(Amendment).where(Amendment.original_trace_id == trace_id)
    )

    # 3. Delete trace_tags rows (association table — no standalone ORM model)
    await db.execute(
        text("DELETE FROM trace_tags WHERE trace_id = :tid"),
        {"tid": trace_id},
    )

    # 4. Delete retrieval log rows (every search/injection that surfaced it)
    await db.execute(
        text("DELETE FROM retrieval_logs WHERE trace_id = :tid"),
        {"tid": trace_id},
    )

    # 5. Delete RIF shadow rows (trace appears as loser or winner)
    await db.execute(
        text(
            "DELETE FROM rif_shadows "
            "WHERE loser_trace_id = :tid OR winner_trace_id = :tid"
        ),
        {"tid": trace_id},
    )

    # 6. Delete trace relationship rows (trace as source or target)
    await db.execute(
        text(
            "DELETE FROM trace_relationships "
            "WHERE source_trace_id = :tid OR target_trace_id = :tid"
        ),
        {"tid": trace_id},
    )

    # 7. Delete the trace itself
    await db.delete(trace)
    await db.commit()

    return {"deleted": True, "trace_id": str(trace_id)}
