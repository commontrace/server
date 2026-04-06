import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.metrics import metrics_endpoint
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.routers import amendments, auth, moderation, reputation, search, tags, telemetry, traces, votes
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

    # Start background workers
    worker_task = asyncio.create_task(_embedding_worker_loop())
    consolidation_task = asyncio.create_task(consolidation_worker_loop())
    try:
        yield
    finally:
        worker_task.cancel()
        consolidation_task.cancel()
        # Shutdown: close Redis connection
        await app.state.redis.aclose()


# H1: Disable docs/openapi in production (only available when debug=True)
_docs_kwargs = {}
if not settings.debug:
    _docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(title="CommonTrace API", version="0.1.0", lifespan=lifespan, **_docs_kwargs)

# H3: CORS — explicit origin whitelist
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://commontrace.org",
        "https://www.commontrace.org",
        "https://docs.commontrace.org",
    ],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
    allow_credentials=False,
)

# M7: Reject request bodies larger than 1 MB
app.add_middleware(BodySizeLimitMiddleware, max_body_size=1_048_576)

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

# Telemetry router
app.include_router(telemetry.router)

# H2: Gate /metrics behind auth (only available when debug=True)
if settings.debug:
    app.get("/metrics")(metrics_endpoint)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
