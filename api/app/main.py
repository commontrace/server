import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.metrics import metrics_endpoint
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.routers import admin, amendments, analytics, auth, invitations, moderation, reputation, search, tags, telemetry, traces, votes
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # L3: Log full traceback instead of silently swallowing
            log.exception("embedding_worker_error", error=str(exc))
        await asyncio.sleep(WORKER_POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure structured logging before anything else
    configure_logging()

    # Startup: create Redis connection and store on app.state
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )

    # Start background workers — stored on app.state so /health can inspect
    # their liveness (informational only; a dead worker is not a fatal health
    # state, see health_check).
    app.state.embedding_worker_task = asyncio.create_task(_embedding_worker_loop())
    app.state.consolidation_worker_task = asyncio.create_task(consolidation_worker_loop())
    try:
        yield
    finally:
        app.state.embedding_worker_task.cancel()
        app.state.consolidation_worker_task.cancel()
        # Shutdown: close Redis connection
        await app.state.redis.aclose()


# H1: Disable docs/openapi in production (only available when debug=True)
_docs_kwargs = {}
if not settings.debug:
    _docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(title="CommonTrace API", version="1.0.0", lifespan=lifespan, **_docs_kwargs)

# H3: CORS — explicit origin whitelist
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://commontrace.org",
        "https://www.commontrace.org",
        "https://docs.commontrace.org",
    ],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "X-Admin-Token", "Content-Type"],
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

# Invitations router (contribution gate, spec §6.4)
app.include_router(invitations.router)

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

# Analytics router (aggregate-only, unauthenticated by design — dashboard endpoint)
app.include_router(analytics.router)

# Admin router (PII-revealing, gated by X-Admin-Token header / ADMIN_DASHBOARD_TOKEN env var)
app.include_router(admin.router)

# H2: Gate /metrics behind auth (only available when debug=True)
if settings.debug:
    app.get("/metrics")(metrics_endpoint)


def _worker_status(task) -> str:
    """Liveness of a background worker task. Informational only — never fatal."""
    if task is None:
        return "unknown"
    return "stopped" if task.done() else "running"


@app.get("/health")
async def health_check(response: Response):
    """Readiness probe.

    Core dependencies (Postgres, Redis) are gating: if either is unreachable the
    service cannot serve traffic, so we return 503. Background workers are
    reported for visibility but are NOT gating — a stuck/dead worker shouldn't
    flip the pod unhealthy and trigger a restart loop that wouldn't fix it.

    Error details are logged server-side only; the response never leaks internal
    error strings to the client.
    """
    checks: dict[str, str] = {}
    healthy = True

    # Core dependency: Postgres
    try:
        from sqlalchemy import text

        from app.database import async_session_factory

        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.error("health_check_database_failed", error=str(exc))
        checks["database"] = "error"
        healthy = False

    # Core dependency: Redis
    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        log.error("health_check_redis_failed", error=str(exc))
        checks["redis"] = "error"
        healthy = False

    # Background workers — informational, not gating.
    checks["embedding_worker"] = _worker_status(
        getattr(app.state, "embedding_worker_task", None)
    )
    checks["consolidation_worker"] = _worker_status(
        getattr(app.state, "consolidation_worker_task", None)
    )

    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}
