import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Response

from app.config import settings
from app.logging_config import configure_logging
from app.metrics import metrics_endpoint
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers import (
    amendments,
    auth,
    moderation,
    reputation,
    search,
    tags,
    traces,
    votes,
)
from app.worker.consolidation_worker import consolidation_worker_loop
from app.worker.embedding_worker import process_batch
from app.services.embedding import EmbeddingService

log = structlog.get_logger(__name__)

WORKER_POLL_INTERVAL = 5


async def _embedding_worker_loop():
    """Background embedding worker — polls for unembedded traces."""
    svc = EmbeddingService()
    log.info("embedding_worker_started", poll_interval=WORKER_POLL_INTERVAL)
    while True:
        try:
            from app.database import async_session_factory

            async with async_session_factory() as db:
                count = await process_batch(db, svc)
                if count > 0:
                    log.info("embedding_batch_processed", count=count)
        except Exception as exc:
            log.error("embedding_worker_error", error=str(exc))
        await asyncio.sleep(WORKER_POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure structured logging before anything else
    configure_logging()

    # Startup: create Redis connection and store on app.state
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )

    # Start background workers and store in app.state for health checks
    app.state.embedding_worker_task = asyncio.create_task(_embedding_worker_loop())
    app.state.consolidation_worker_task = asyncio.create_task(
        consolidation_worker_loop()
    )
    try:
        yield
    finally:
        app.state.embedding_worker_task.cancel()
        app.state.consolidation_worker_task.cancel()
        # Shutdown: close Redis connection
        await app.state.redis.aclose()


app = FastAPI(title="CommonTrace API", version="0.1.0", lifespan=lifespan)

# Register request logging middleware (runs on every request)
app.add_middleware(RequestLoggingMiddleware)

# Register all API routers
app.include_router(auth.router)
app.include_router(traces.router)
app.include_router(votes.router)
app.include_router(amendments.router)

# Moderation router (02-04)
app.include_router(moderation.router)

# Search router (03-02)
app.include_router(search.router)

# Reputation router (04-02)
app.include_router(reputation.router)

# Tags router (05-01)
app.include_router(tags.router)

# Prometheus metrics endpoint
app.get("/metrics")(metrics_endpoint)


@app.get("/health")
async def health_check(response: Response):
    """Intelligent health check — verifies all system components.

    Returns 200 if all components are healthy, 503 if any component is unhealthy.

    Checks:
    - PostgreSQL connectivity
    - Redis connectivity
    - Embedding worker status
    - Consolidation worker status
    """
    from app.database import async_session_factory
    from sqlalchemy import text

    checks = {}
    overall_healthy = True

    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    try:
        await app.state.redis.ping()
        checks["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    try:
        worker = app.state.embedding_worker_task
        if worker.done() or worker.cancelled():
            checks["embedding_worker"] = {
                "status": "unhealthy",
                "error": "Worker task stopped",
            }
            overall_healthy = False
        else:
            checks["embedding_worker"] = {"status": "healthy"}
    except AttributeError:
        checks["embedding_worker"] = {
            "status": "unhealthy",
            "error": "Worker not initialized",
        }
        overall_healthy = False

    try:
        worker = app.state.consolidation_worker_task
        if worker.done() or worker.cancelled():
            checks["consolidation_worker"] = {
                "status": "unhealthy",
                "error": "Worker task stopped",
            }
            overall_healthy = False
        else:
            checks["consolidation_worker"] = {"status": "healthy"}
    except AttributeError:
        checks["consolidation_worker"] = {
            "status": "unhealthy",
            "error": "Worker not initialized",
        }
        overall_healthy = False

    response.status_code = 200 if overall_healthy else 503
    return {"status": "healthy" if overall_healthy else "unhealthy", "checks": checks}
