"""Retrieval-induced forgetting (RIF) detection service.

Tracks which traces consistently lose to the same competitor across
search sessions. When a trace appears at position > 0 while another
trace wins position 0 in the same session >= 3 times, a rif_shadow
entry is created or updated.

Based on Principle 6 — Retrieval-Induced Forgetting from cognitive neuroscience.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Minimum co-occurrence count before creating a shadow
MIN_CO_OCCURRENCE = 3


async def detect_rif_shadows(session: AsyncSession) -> int:
    """Detect RIF shadow relationships from retrieval logs.

    Joins winners (position=0) with losers (position>0) in the same
    search_session_id, counts co-occurrences, and upserts into rif_shadows
    for pairs meeting the minimum threshold.

    Returns count of new or updated shadow entries.
    """
    result = await session.execute(
        text(
            """
            WITH winner_loser AS (
                SELECT
                    w.trace_id AS winner_id,
                    l.trace_id AS loser_id,
                    COUNT(*) AS co_occurrence
                FROM retrieval_logs w
                JOIN retrieval_logs l
                    ON w.search_session_id = l.search_session_id
                    AND w.result_position = 0
                    AND l.result_position > 0
                    AND w.trace_id != l.trace_id
                WHERE w.result_position IS NOT NULL
                    AND l.result_position IS NOT NULL
                GROUP BY w.trace_id, l.trace_id
                HAVING COUNT(*) >= :min_co_occurrence
            )
            SELECT winner_id, loser_id, co_occurrence
            FROM winner_loser
            """
        ),
        {"min_co_occurrence": MIN_CO_OCCURRENCE},
    )
    rows = result.all()

    updated = 0
    for row in rows:
        res = await session.execute(
            text(
                """
                INSERT INTO rif_shadows (id, loser_trace_id, winner_trace_id, loss_count, last_observed)
                VALUES (gen_random_uuid(), :loser_id, :winner_id, :count, now())
                ON CONFLICT (loser_trace_id, winner_trace_id)
                DO UPDATE SET
                    loss_count = rif_shadows.loss_count + :count,
                    last_observed = now()
                """
            ),
            {
                "loser_id": str(row.loser_id),
                "winner_id": str(row.winner_id),
                "count": row.co_occurrence,
            },
        )
        if res.rowcount > 0:
            updated += 1

    if updated > 0:
        log.info("rif_shadows_detected", shadow_count=updated, pairs_evaluated=len(rows))

    return updated
