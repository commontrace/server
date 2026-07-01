"""Unit tests for the shared admin-dashboard token gate (dependencies.py).

`verify_admin_token` is the single source of truth for owner-only gating,
used by both the admin router and the (now private) analytics router. These
tests exercise it directly by monkeypatching the configured secret — no DB,
no HTTP client, matching the no-DB harness in conftest.py.
"""
import pytest
from fastapi import HTTPException

from app import dependencies
from app.dependencies import require_admin_token, verify_admin_token


def test_unset_token_returns_503(monkeypatch):
    """Feature disabled (env var empty) → 503, never a silent pass."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "")
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("anything")
    assert exc.value.status_code == 503


def test_wrong_token_returns_401(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("wrong")
    assert exc.value.status_code == 401


def test_missing_header_returns_401(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    with pytest.raises(HTTPException) as exc:
        verify_admin_token(None)
    assert exc.value.status_code == 401


def test_correct_token_passes(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    assert verify_admin_token("s3cret") is None


@pytest.mark.asyncio
async def test_dependency_form_delegates(monkeypatch):
    """The FastAPI dependency wrapper delegates to verify_admin_token."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    assert await require_admin_token("s3cret") is None
    with pytest.raises(HTTPException) as exc:
        await require_admin_token("nope")
    assert exc.value.status_code == 401
