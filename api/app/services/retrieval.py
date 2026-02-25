"""Retrieval tracking service.

Records when traces are retrieved via search, implementing the testing
effect from cognitive neuroscience: each retrieval strengthens the trace.

Also records co-retrieval patterns — traces that appear together in search
results develop CO_RETRIEVED relationships (Hebbian association).

Uses fire-and-forget pattern — opens its own session so it doesn't block
the search response.
"""

import uuid
from itertools import combinations

import structlog
from datetime import datetime, timezone

from sqlalchemy import text, update

from app.database import async_session_factory
from app.models.trace import Trace

log = structlog.get_logger()

# Cap co-retrieval pair generation to avoid quadratic explosion
MAX_CO_RETRIEVAL_TRACES = 10


async def record_retrievals(trace_ids: list[uuid.UUID]) -> None:
    """Bump retrieval_count and last_retrieved_at for retrieved traces.

    Opens its own database session (fire-and-forget). A single bulk UPDATE
    ensures minimal DB overhead even for large result sets.
    """
    if not trace_ids:
        return

    try:
        async with async_session_factory() as session:
            stmt = (
                update(Trace)
                .where(Trace.id.in_(trace_ids))
                .values(
                    retrieval_count=Trace.retrieval_count + 1,
                    last_retrieved_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()
    except Exception:
        log.warning("retrieval_tracking_failed", trace_count=len(trace_ids), exc_info=True)


async def record_retrieval_logs(
    trace_ids: list[uuid.UUID], search_session_id: str
) -> None:
    """Insert retrieval log rows for co-retrieval analysis.

    Each trace in the result set gets a log entry tied to the search session.
    The consolidation worker later uses these to build CO_RETRIEVED relationships.
    """
    if not trace_ids or not search_session_id:
        return

    try:
        async with async_session_factory() as session:
            values = [
                {"trace_id": str(tid), "search_session_id": search_session_id}
                for tid in trace_ids
            ]
            await session.execute(
                text(
                    "INSERT INTO retrieval_logs (id, trace_id, search_session_id) "
                    "VALUES (gen_random_uuid(), :trace_id, :search_session_id)"
                ),
                values,
            )
            await session.commit()
    except Exception:
        log.warning(
            "retrieval_log_failed",
            trace_count=len(trace_ids),
            session_id=search_session_id,
            exc_info=True,
        )


async def record_co_retrievals(trace_ids: list[uuid.UUID]) -> None:
    """Build CO_RETRIEVED relationships for traces returned together.

    For each pair in the result set (capped at MAX_CO_RETRIEVAL_TRACES),
    upsert a CO_RETRIEVED relationship with strength += 1.

    Both directions are stored for query simplicity.
    """
    if len(trace_ids) < 2:
        return

    capped = trace_ids[:MAX_CO_RETRIEVAL_TRACES]
    pairs = list(combinations(capped, 2))

    try:
        async with async_session_factory() as session:
            for a, b in pairs:
                # Upsert both directions
                await session.execute(
                    text(
                        "INSERT INTO trace_relationships "
                        "(id, source_trace_id, target_trace_id, relationship_type, strength) "
                        "VALUES (gen_random_uuid(), :src, :tgt, 'CO_RETRIEVED', 1.0) "
                        "ON CONFLICT (source_trace_id, target_trace_id, relationship_type) "
                        "DO UPDATE SET strength = trace_relationships.strength + 1, "
                        "updated_at = now()"
                    ),
                    {"src": str(a), "tgt": str(b)},
                )
                await session.execute(
                    text(
                        "INSERT INTO trace_relationships "
                        "(id, source_trace_id, target_trace_id, relationship_type, strength) "
                        "VALUES (gen_random_uuid(), :src, :tgt, 'CO_RETRIEVED', 1.0) "
                        "ON CONFLICT (source_trace_id, target_trace_id, relationship_type) "
                        "DO UPDATE SET strength = trace_relationships.strength + 1, "
                        "updated_at = now()"
                    ),
                    {"src": str(b), "tgt": str(a)},
                )
            await session.commit()
    except Exception:
        log.warning("co_retrieval_tracking_failed", pair_count=len(pairs), exc_info=True)
