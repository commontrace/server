"""Environment configuration with fail-fast validation."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    resend_api_key: str
    github_token: str
    alert_from: str
    alert_to: str
    repos: list[str]
    model: str
    database_url: str | None
    audit_issue_repo: str | None
    discord_webhook_url: str | None = None


REQUIRED = [
    "OPENAI_API_KEY",
    "RESEND_API_KEY",
    "GITHUB_TOKEN",
    "ALERT_EMAIL_FROM",
    "ALERT_EMAIL_TO",
    "REPOS",
]


def _normalize_db_url(url: str) -> str:
    # asyncpg.connect() does not accept the SQLAlchemy "+asyncpg" dialect suffix.
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def load_config(
    *,
    env: dict | None = None,
    require_db: bool = False,
    require_issue_repo: bool = False,
) -> Config:
    env = dict(os.environ if env is None else env)

    missing = [k for k in REQUIRED if not env.get(k)]
    if require_db and not env.get("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if require_issue_repo and not env.get("AUDIT_ISSUE_REPO"):
        missing.append("AUDIT_ISSUE_REPO")
    if missing:
        raise ConfigError(f"missing required env: {', '.join(missing)}")

    repos = [r.strip() for r in env["REPOS"].split(",") if r.strip()]
    if not repos:
        raise ConfigError("REPOS is empty after parsing")

    db_url = env.get("DATABASE_URL")
    return Config(
        openai_api_key=env["OPENAI_API_KEY"],
        resend_api_key=env["RESEND_API_KEY"],
        github_token=env["GITHUB_TOKEN"],
        alert_from=env["ALERT_EMAIL_FROM"],
        alert_to=env["ALERT_EMAIL_TO"],
        repos=repos,
        model=env.get("CT_MODEL", "gpt-5.5"),
        database_url=_normalize_db_url(db_url) if db_url else None,
        audit_issue_repo=env.get("AUDIT_ISSUE_REPO"),
        discord_webhook_url=env.get("DISCORD_WEBHOOK_URL"),
    )
