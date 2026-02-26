"""Tests for intelligent health check endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from app.main import app


@pytest.fixture
def client():
    """Test client for health check tests."""
    return TestClient(app)


def test_health_check_all_healthy(client, monkeypatch):
    """Health check returns 200 when all components are healthy."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    mock_worker = MagicMock()
    mock_worker.done.return_value = False
    mock_worker.cancelled.return_value = False

    mock_consolidation = MagicMock()
    mock_consolidation.done.return_value = False
    mock_consolidation.cancelled.return_value = False

    app.state.redis = mock_redis
    app.state.embedding_worker_task = mock_worker
    app.state.consolidation_worker_task = mock_consolidation

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"]["status"] == "healthy"
    assert data["checks"]["redis"]["status"] == "healthy"
    assert data["checks"]["embedding_worker"]["status"] == "healthy"
    assert data["checks"]["consolidation_worker"]["status"] == "healthy"


def test_health_check_redis_down(client, monkeypatch):
    """Health check returns 503 when Redis is down."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=Exception("Connection failed"))

    # Mock healthy workers
    mock_worker = MagicMock()
    mock_worker.done.return_value = False
    mock_worker.cancelled.return_value = False

    app.state.redis = mock_redis
    app.state.embedding_worker_task = mock_worker
    app.state.consolidation_worker_task = mock_worker

    response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["redis"]["status"] == "unhealthy"


def test_health_check_worker_stopped(client, monkeypatch):
    """Health check returns 503 when a worker is stopped."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    mock_worker = MagicMock()
    mock_worker.done.return_value = True  # Worker stopped
    mock_worker.cancelled.return_value = False

    mock_healthy_worker = MagicMock()
    mock_healthy_worker.done.return_value = False
    mock_healthy_worker.cancelled.return_value = False

    app.state.redis = mock_redis
    app.state.embedding_worker_task = mock_worker
    app.state.consolidation_worker_task = mock_healthy_worker

    response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["embedding_worker"]["status"] == "unhealthy"
