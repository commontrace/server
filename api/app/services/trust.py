"""Vote application and trust score / trace promotion logic.

This module handles the atomic update of a trace's trust state when a vote
is applied, and promotes traces from 'pending' to 'validated' when the
validation threshold is reached (SAFE-01).

Design notes:
- All database updates use column expressions (Trace.column + delta) to
  ensure atomicity — no Python-side read-modify-write that could race.
- Promotion check happens after the UPDATE by re-querying the row. This is
  a separate SELECT + conditional UPDATE, which is safe under the assumption
  that each user can vote only once per trace (enforced by DB unique constraint).
- vote_weight allows future reputation-weighted voting without schema changes.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trace import Trace, TraceStatus


async def apply_vote_to_trace(
    db: AsyncSession,
    trace_id: uuid.UUID,
    vote_weight: float,
    is_upvote: bool,
) -> None:
    """Atomically apply a vote to a trace and promote if threshold is reached.

    Increments confirmation_count by 1 and adjusts trust_score by
    +vote_weight (upvote) or -vote_weight (downvote) using a single atomic
    UPDATE statement — no SELECT is performed before the UPDATE.

    After the UPDATE, the trace is re-queried to check promotion eligibility.
    If status is pending, confirmation_count >= validation_threshold, and
    trust_score > 0, the trace is promoted to 'validated'.

    Args:
        db: The async SQLAlchemy session (caller manages commit/rollback).
        trace_id: UUID of the trace receiving the vote.
        vote_weight: Positive float weight for this vote (typically 1.0).
        is_upvote: True for an upvote (+weight), False for a downvote (-weight).
    """
    score_delta = vote_weight if is_upvote else -vote_weight

    # Atomic UPDATE — column expressions prevent read-modify-write races
    await db.execute(
        update(Trace)
        .where(Trace.id == trace_id)
        .values(
            confirmation_count=Trace.confirmation_count + 1,
            trust_score=Trace.trust_score + score_delta,
        )
        .execution_options(synchronize_session=False)
    )

    # Re-query to check promotion eligibility
    result = await db.execute(
        select(Trace.status, Trace.confirmation_count, Trace.trust_score).where(
            Trace.id == trace_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return

    status, confirmation_count, trust_score = row

    # Promote if pending, threshold reached, and net positive trust
    if (
        status == TraceStatus.pending
        and confirmation_count >= settings.validation_threshold
        and trust_score > 0
    ):
        await db.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(status=TraceStatus.validated)
            .execution_options(synchronize_session=False)
        )
