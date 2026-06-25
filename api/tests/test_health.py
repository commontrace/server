"""Tests for the rich /health readiness probe — no live Postgres or Redis.

The endpoint reads `app.database.async_session_factory` (imported inside the
handler) and `app.state.redis`, plus worker-task liveness off `app.state`. We
patch those so each path can be exercised without a real backend:

  * happy path            -> 200, status "ok"
  * a core dep is down    -> 503, status "degraded" (DB or Redis)
  * a worker is stopped   -> still 200 (worker status is informational)

TestClient is used WITHOUT its context manager so the real lifespan (which would
start the background workers against a nonexistent DB) never runs; we set
`app.state` by hand instead.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


@asynccontextmanager
async def _ok_session_factory():
    """Stands in for async_session_factory(): yields a session whose execute()
    succeeds (SELECT 1 returns nothing meaningful, which is fine)."""
    class _S:
        async def execute(self, *a, **k):
            return None

    yield _S()


def _bad_session_factory():
    """Simulates Postgres unreachable: raising on the factory call mirrors a
    connection failure when entering `async with async_session_factory()`."""
    raise RuntimeError("postgres unreachable")


class _FakeRedis:
    def __init__(self, ok: bool = True):
        self._ok = ok

    async def ping(self):
        if not self._ok:
            raise RuntimeError("redis unreachable")
        return True


def _worker(done: bool):
    return SimpleNamespace(done=lambda: done)


def _set_state(redis_ok=True, embedding_done=False, consolidation_done=False):
    app.state.redis = _FakeRedis(ok=redis_ok)
    app.state.embedding_worker_task = _worker(embedding_done)
    app.state.consolidation_worker_task = _worker(consolidation_done)


def test_health_ok(monkeypatch):
    monkeypatch.setattr("app.database.async_session_factory", _ok_session_factory)
    _set_state()
    r = TestClient(app).get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["embedding_worker"] == "running"
    assert body["checks"]["consolidation_worker"] == "running"


def test_health_db_down_returns_503(monkeypatch):
    monkeypatch.setattr("app.database.async_session_factory", _bad_session_factory)
    _set_state()
    r = TestClient(app).get("/health")

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"
    # Internal error string must not leak to the client.
    assert "unreachable" not in r.text.lower()


def test_health_redis_down_returns_503(monkeypatch):
    monkeypatch.setattr("app.database.async_session_factory", _ok_session_factory)
    _set_state(redis_ok=False)
    r = TestClient(app).get("/health")

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "error"
    assert "unreachable" not in r.text.lower()


def test_health_stopped_worker_is_not_fatal(monkeypatch):
    monkeypatch.setattr("app.database.async_session_factory", _ok_session_factory)
    _set_state(embedding_done=True)  # worker died
    r = TestClient(app).get("/health")

    # Core deps are fine, so still healthy despite a dead worker.
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["embedding_worker"] == "stopped"
    assert body["checks"]["consolidation_worker"] == "running"
