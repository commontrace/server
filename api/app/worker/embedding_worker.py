"""Embedding worker: polls for unembedded traces and stores OpenAI vectors.

Uses FOR UPDATE SKIP LOCKED to safely claim batches, allowing multiple worker
instances to run without double-processing the same trace.
"""
import asyncio

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.trace import Trace
from app.services.embedding import EmbeddingService, EmbeddingSkippedError

log = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 10


async def process_batch(db: AsyncSession, svc: EmbeddingService) -> int:
    """Claim a batch of unembedded traces with SKIP LOCKED and embed them.

    Returns:
        Number of traces processed in this batch.
    """
    stmt = (
        select(Trace)
        .where(Trace.embedding.is_(None))
        .with_for_update(skip_locked=True)
        .limit(BATCH_SIZE)
    )
    result = await db.execute(stmt)
    traces = result.scalars().all()

    if not traces:
        return 0

    processed = 0
    for trace in traces:
        text = f"{trace.title}\n{trace.context_text}\n{trace.solution_text}"
        try:
            vector, model_id, model_version = await svc.embed(text)
        except EmbeddingSkippedError:
            log.warning(
                "embedding_skipped_no_api_key",
                message="OPENAI_API_KEY not configured — skipping entire batch.",
            )
            return 0
        except Exception as exc:
            log.error(
                "embedding_error",
                trace_id=str(trace.id),
                error=str(exc),
            )
            continue

        update_stmt = (
            update(Trace)
            .where(Trace.id == trace.id)
            .values(
                embedding=vector,
                embedding_model_id=model_id,
                embedding_model_version=model_version,
            )
            .execution_options(synchronize_session=False)
        )
        await db.execute(update_stmt)
        log.info("embedding_stored", trace_id=str(trace.id), model=model_id)
        processed += 1

    await db.commit()
    return processed


async def run_worker() -> None:
    """Main polling loop: claims and embeds unembedded traces every POLL_INTERVAL_SECONDS."""
    svc = EmbeddingService()
    log.info("embedding_worker_started", poll_interval=POLL_INTERVAL_SECONDS, batch_size=BATCH_SIZE)

    while True:
        try:
            async with async_session_factory() as db:
                count = await process_batch(db, svc)
                if count > 0:
                    log.info("batch_processed", count=count)
        except Exception as exc:
            log.error("worker_loop_error", error=str(exc))

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_worker())
