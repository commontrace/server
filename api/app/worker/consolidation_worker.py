"""Consolidation worker — the "sleep cycle".

Runs periodically to maintain knowledge health:
1. Trust downscaling (prevents unbounded inflation)
2. Memory temperature computation (HOT→WARM→COOL→COLD→FROZEN classification)
3. Co-retrieval relationship building from retrieval logs
4. Log pruning (removes retrieval logs older than 30 days)
5. Prospective memory checks (marks traces FROZEN when review_after passes)
6. Convergence detection (clusters similar traces, classifies convergence level)

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

from app.services.convergence import detect_convergence_clusters
from app.services.maturity import MaturityTier, get_decay_multiplier, get_maturity_tier, should_apply_temporal_decay
from app.services.temperature import classify_temperature

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


async def _compute_temperatures(session) -> dict:
    """Classify memory temperature for all traces and sync backward-compat flags.

    Replaces binary stale detection with graduated HOT→WARM→COOL→COLD→FROZEN.
    Also flags traces with trust_score < -2 (unchanged from previous logic).
    """
    result = await session.execute(
        select(
            Trace.id,
            Trace.created_at,
            Trace.last_retrieved_at,
            Trace.retrieval_count,
            Trace.trust_score,
            Trace.depth_score,
            Trace.memory_temperature,
        )
    )
    rows = result.all()

    temperatures_changed = 0
    distribution: dict[str, int] = {}
    for row in rows:
        new_temp = classify_temperature(
            row.created_at,
            row.last_retrieved_at,
            row.retrieval_count,
            row.trust_score,
            row.depth_score,
        )
        distribution[new_temp.value] = distribution.get(new_temp.value, 0) + 1

        if row.memory_temperature != new_temp.value:
            is_stale = new_temp.value == "FROZEN"
            await session.execute(
                update(Trace)
                .where(Trace.id == row.id)
                .values(memory_temperature=new_temp.value, is_stale=is_stale)
            )
            temperatures_changed += 1

    # Flag deeply negative trust traces (unchanged behavior)
    flagged_result = await session.execute(
        update(Trace)
        .where(Trace.trust_score < -2)
        .where(Trace.is_flagged.is_(False))
        .values(is_flagged=True, flagged_at=datetime.now(timezone.utc))
    )

    return {
        "temperatures_changed": temperatures_changed,
        "temperature_distribution": distribution,
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
    """Mark traces FROZEN when their review_after date has passed."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(Trace)
        .where(Trace.review_after.is_not(None))
        .where(Trace.review_after < now)
        .where(Trace.is_stale.is_(False))
        .values(is_stale=True, memory_temperature="FROZEN")
    )
    return result.rowcount


async def _detect_convergence(session) -> int:
    """Detect convergence clusters among similar traces."""
    return await detect_convergence_clusters(session)


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

        # Determine maturity tier for adaptive behavior
        tier = await get_maturity_tier(session)
        decay_factor = get_decay_multiplier(tier)
        stats["maturity_tier"] = tier.value
        errors = []

        # Each job runs independently — one failure doesn't block others
        jobs: list[tuple[str, object]] = [
            ("trust_downscaled", _trust_downscaling(session, decay_factor)),
            ("temperature_computation", _compute_temperatures(session)),
            ("co_retrieval_links", _build_co_retrieval_links(session)),
            ("logs_pruned", _prune_retrieval_logs(session)),
            ("prospective_staled", _check_prospective_memory(session)),
        ]

        # Convergence detection only in GROWING/MATURE
        if tier in (MaturityTier.GROWING, MaturityTier.MATURE):
            jobs.append(("convergence_detected", _detect_convergence(session)))

        for job_name, coro in jobs:
            try:
                result = await coro
                if isinstance(result, dict):
                    stats.update(result)
                else:
                    stats[job_name] = result
            except Exception:
                log.error("consolidation_job_failed", job=job_name, exc_info=True)
                stats[job_name] = "error"
                errors.append(job_name)

        run.status = "completed" if not errors else "partial"
        run.completed_at = datetime.now(timezone.utc)
        run.stats_json = stats
        await session.commit()

        if errors:
            log.warning("consolidation_partial", failed_jobs=errors, stats=stats)
        else:
            log.info("consolidation_completed", stats=stats)

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
