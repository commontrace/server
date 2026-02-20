"""Vote application and trust score / trace promotion logic.

This module handles the atomic update of a trace's trust state when a vote
is applied, and promotes traces from 'pending' to 'validated' when the
validation threshold is reached (SAFE-01).

Also provides the Wilson score lower bound formula used for reputation ranking.

Design notes:
- All database updates use column expressions (Trace.column + delta) to
  ensure atomicity — no Python-side read-modify-write that could race.
- Promotion check happens after the UPDATE by re-querying the row. This is
  a separate SELECT + conditional UPDATE, which is safe under the assumption
  that each user can vote only once per trace (enforced by DB unique constraint).
- vote_weight allows future reputation-weighted voting without schema changes.
"""

import math
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trace import Trace, TraceStatus


def wilson_score_lower_bound(upvotes: int, total_votes: int) -> float:
    """Compute the 95% Wilson score confidence interval lower bound.

    Returns 0.0 when total_votes == 0 (no data = no confidence).
    Returns a value in [0, 1] representing the lower bound of the true
    positive rate at 95% confidence.

    BASE_WEIGHT context: new contributors with no votes score 0.0.
    An established contributor with 80% upvote rate on 50 votes scores ~0.66.
    This creates a measurable weight difference for REPU-01.

    Source: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html

    Args:
        upvotes: Number of positive votes.
        total_votes: Total votes (upvotes + downvotes).

    Returns:
        Wilson score lower bound in [0, 1].
    """
    if total_votes == 0:
        return 0.0
    z = 1.9600  # 95% confidence z-score
    z2 = z * z   # 3.8416
    p_hat = upvotes / total_votes
    n = total_votes
    numerator = p_hat + z2 / (2 * n) - z * math.sqrt(
        (p_hat * (1 - p_hat) + z2 / (4 * n)) / n
    )
    return numerator / (1 + z2 / n)


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
