from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.config import settings


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


@app.get("/health")
async def health_check():
    return {"status": "ok"}
