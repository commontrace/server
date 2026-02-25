"""Consolidation worker — the "sleep cycle".

Runs periodically to maintain knowledge health:
1. Trust downscaling (prevents unbounded inflation)
2. Stale trace detection (flags inactive/low-quality traces)
3. Co-retrieval relationship building from retrieval logs
4. Log pruning (removes retrieval logs older than 30 days)
5. Prospective memory checks (marks traces stale when review_after passes)

Pattern extraction (cluster similar traces, generate pattern traces via LLM)
is deferred until the knowledge base reaches sufficient scale.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select, text, update

from app.config import settings
from app.database import async_session_factory
from app.models.consolidation_run import ConsolidationRun
from app.models.trace import Trace
from app.services.maturity import get_decay_multiplier, get_maturity_tier, should_apply_temporal_decay

log = structlog.get_logger()


async def _trust_downscaling(session, decay_factor: float) -> int:
    """Apply gradual trust decay to prevent unbounded inflation.

    Decay factor is maturity-tier-aware: no decay in SEED, moderate in
    GROWING, aggressive in MATURE.
    """
    if decay_factor >= 1.0:
        return 0  # No decay at this tier
    result = await session.execute(
        update(Trace)
        .where(Trace.trust_score > 0)
        .values(trust_score=Trace.trust_score * decay_factor)
    )
    return result.rowcount


async def _stale_trace_detection(session) -> dict:
    """Flag traces that show no signs of usefulness.

    - retrieval_count=0 AND age > stale_age_days → is_stale=True
    - trust_score < -2 → is_flagged=True
    """
    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.consolidation_stale_age_days
    )

    stale_result = await session.execute(
        update(Trace)
        .where(Trace.retrieval_count == 0)
        .where(Trace.created_at < stale_cutoff)
        .where(Trace.is_stale.is_(False))
        .values(is_stale=True)
    )

    flagged_result = await session.execute(
        update(Trace)
        .where(Trace.trust_score < -2)
        .where(Trace.is_flagged.is_(False))
        .values(is_flagged=True, flagged_at=datetime.now(timezone.utc))
    )

    return {
        "newly_stale": stale_result.rowcount,
        "newly_flagged": flagged_result.rowcount,
    }


async def _build_co_retrieval_links(session) -> int:
    """Process retrieval logs to build CO_RETRIEVED relationships.

    Groups logs by search_session_id, generates pairs, and upserts
    relationships with cumulative strength.
    """
    # Get distinct sessions from the last 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    sessions = await session.execute(
        text(
            "SELECT search_session_id, array_agg(DISTINCT trace_id) as trace_ids "
            "FROM retrieval_logs "
            "WHERE retrieved_at > :cutoff "
            "GROUP BY search_session_id "
            "HAVING count(DISTINCT trace_id) >= 2"
        ),
        {"cutoff": cutoff},
    )

    link_count = 0
    for row in sessions:
        trace_ids = row.trace_ids[:10]  # Cap at 10 to prevent quadratic explosion
        for i in range(len(trace_ids)):
            for j in range(i + 1, len(trace_ids)):
                a, b = str(trace_ids[i]), str(trace_ids[j])
                for src, tgt in [(a, b), (b, a)]:
                    await session.execute(
                        text(
                            "INSERT INTO trace_relationships "
                            "(id, source_trace_id, target_trace_id, relationship_type, strength) "
                            "VALUES (gen_random_uuid(), :src, :tgt, 'CO_RETRIEVED', 1.0) "
                            "ON CONFLICT (source_trace_id, target_trace_id, relationship_type) "
                            "DO UPDATE SET strength = trace_relationships.strength + 1, "
                            "updated_at = now()"
                        ),
                        {"src": src, "tgt": tgt},
                    )
                    link_count += 1

    return link_count


async def _prune_retrieval_logs(session) -> int:
    """Delete retrieval logs older than 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await session.execute(
        text("DELETE FROM retrieval_logs WHERE retrieved_at < :cutoff"),
        {"cutoff": cutoff},
    )
    return result.rowcount


async def _check_prospective_memory(session) -> int:
    """Mark traces stale when their review_after date has passed."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(Trace)
        .where(Trace.review_after.is_not(None))
        .where(Trace.review_after < now)
        .where(Trace.is_stale.is_(False))
        .values(is_stale=True)
    )
    return result.rowcount


async def run_consolidation_cycle() -> dict:
    """Execute one full consolidation cycle.

    Returns stats dict for audit trail.
    """
    stats = {}

    async with async_session_factory() as session:
        # Check for recent completed run (idempotency)
        interval = timedelta(hours=settings.consolidation_interval_hours)
        cutoff = datetime.now(timezone.utc) - interval
        recent = await session.execute(
            select(ConsolidationRun).where(
                ConsolidationRun.completed_at > cutoff,
                ConsolidationRun.status == "completed",
            )
        )
        if recent.scalar_one_or_none():
            log.info("consolidation_skipped", reason="recent_run_exists")
            return {"skipped": True}

        # Create run record
        run = ConsolidationRun(status="running")
        session.add(run)
        await session.flush()

        try:
            # Determine maturity tier for adaptive behavior
            tier = await get_maturity_tier(session)
            decay_factor = get_decay_multiplier(tier)
            stats["maturity_tier"] = tier.value

            stats["trust_downscaled"] = await _trust_downscaling(session, decay_factor)
            stats.update(await _stale_trace_detection(session))
            stats["co_retrieval_links"] = await _build_co_retrieval_links(session)
            stats["logs_pruned"] = await _prune_retrieval_logs(session)
            stats["prospective_staled"] = await _check_prospective_memory(session)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.stats_json = stats
            await session.commit()

            log.info("consolidation_completed", stats=stats)
        except Exception:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.stats_json = {"error": "cycle_failed"}
            await session.commit()
            log.error("consolidation_failed", exc_info=True)
            raise

    return stats


async def consolidation_worker_loop():
    """Background loop that runs consolidation on a configurable interval."""
    interval = settings.consolidation_interval_hours * 3600
    log.info("consolidation_worker_started", interval_hours=settings.consolidation_interval_hours)

    # Initial delay — let the app warm up
    await asyncio.sleep(60)

    while True:
        try:
            await run_consolidation_cycle()
        except Exception:
            log.error("consolidation_worker_error", exc_info=True)
        await asyncio.sleep(interval)
