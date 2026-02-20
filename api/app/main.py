from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.config import settings
from app.routers import amendments, auth, moderation, traces, votes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create Redis connection and store on app.state
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    try:
        yield
    finally:
        # Shutdown: close Redis connection
        await app.state.redis.aclose()


app = FastAPI(title="CommonTrace API", version="0.1.0", lifespan=lifespan)

# Register all API routers
app.include_router(auth.router)
app.include_router(traces.router)
app.include_router(votes.router)
app.include_router(amendments.router)

# Moderation router (02-04)
app.include_router(moderation.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
