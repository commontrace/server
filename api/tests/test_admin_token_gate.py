"""Unit tests for the shared admin-dashboard token gate (dependencies.py).

`verify_admin_token` is the single source of truth for owner-only gating,
used by both the admin router and the (now private) analytics router. These
tests exercise it directly by monkeypatching the configured secret — no DB,
no HTTP client, matching the no-DB harness in conftest.py.
"""
import hashlib

import pytest
from fastapi import HTTPException

from app import dependencies
from app.dependencies import require_admin_token, verify_admin_token


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


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


def test_non_ascii_token_matches(monkeypatch):
    """A non-ASCII secret must still match its exact value.

    Regression: hmac.compare_digest raises TypeError on str args with non-ASCII
    characters, which surfaced as a 500 for every request (even the correct
    token). We now encode to bytes, so a non-ASCII secret compares cleanly.
    """
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "clé-café-☕")
    assert verify_admin_token("clé-café-☕") is None


def test_non_ascii_secret_wrong_token_returns_401(monkeypatch):
    """Wrong token against a non-ASCII secret is 401, never a 500/TypeError."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "clé-café-☕")
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("dummy-wrong")
    assert exc.value.status_code == 401


def test_sha256_hex_digest_authenticates(monkeypatch):
    """The browser gate cannot send a non-ASCII token as an HTTP header, so it
    sends the SHA-256 hex digest instead. That digest must authenticate."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    assert verify_admin_token(_sha256_hex("s3cret")) is None


def test_sha256_hex_digest_of_long_non_ascii_token(monkeypatch):
    """A long, deliberately non-ASCII token authenticates via its hex digest."""
    token = "4SÜ-🔒-" + "λ" * 400 + "-Ω-HGF"
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", token)
    # Raw non-ASCII token would never reach us from a browser; the digest does.
    assert verify_admin_token(_sha256_hex(token)) is None
    # Uppercase hex digest is normalised to lowercase before comparison.
    assert verify_admin_token(_sha256_hex(token).upper()) is None


def test_wrong_hex_digest_returns_401(monkeypatch):
    """A hex-shaped but wrong value is still rejected."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    with pytest.raises(HTTPException) as exc:
        verify_admin_token(_sha256_hex("not-the-secret"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dependency_form_delegates(monkeypatch):
    """The FastAPI dependency wrapper delegates to verify_admin_token."""
    monkeypatch.setattr(dependencies.settings, "admin_dashboard_token", "s3cret")
    assert await require_admin_token("s3cret") is None
    with pytest.raises(HTTPException) as exc:
        await require_admin_token("nope")
    assert exc.value.status_code == 401
