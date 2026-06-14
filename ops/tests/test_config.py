import pytest

from commontrace_ops.common.config import Config, ConfigError, load_config

BASE_ENV = {
    "OPENAI_API_KEY": "sk-test",
    "RESEND_API_KEY": "re-test",
    "GITHUB_TOKEN": "ghp-test",
    "ALERT_EMAIL_FROM": "alerts@denemlabs.com",
    "ALERT_EMAIL_TO": "tools@denemlabs.com",
    "REPOS": "commontrace/server,commontrace/mcp",
}


def test_load_config_parses_repos_and_defaults_model():
    cfg = load_config(env=BASE_ENV)
    assert isinstance(cfg, Config)
    assert cfg.repos == ["commontrace/server", "commontrace/mcp"]
    assert cfg.model == "gpt-5.5"
    assert cfg.alert_to == "tools@denemlabs.com"


def test_model_override():
    cfg = load_config(env={**BASE_ENV, "CT_MODEL": "gpt-5.5-mini"})
    assert cfg.model == "gpt-5.5-mini"


def test_missing_required_raises_config_error():
    env = dict(BASE_ENV)
    del env["OPENAI_API_KEY"]
    with pytest.raises(ConfigError) as exc:
        load_config(env=env)
    assert "OPENAI_API_KEY" in str(exc.value)


def test_require_db_demands_database_url():
    with pytest.raises(ConfigError) as exc:
        load_config(env=BASE_ENV, require_db=True)
    assert "DATABASE_URL" in str(exc.value)


def test_require_issue_repo_demands_audit_issue_repo():
    with pytest.raises(ConfigError) as exc:
        load_config(env=BASE_ENV, require_issue_repo=True)
    assert "AUDIT_ISSUE_REPO" in str(exc.value)


def test_db_url_normalizes_asyncpg_scheme():
    env = {**BASE_ENV, "DATABASE_URL": "postgresql+asyncpg://u:p@h/db"}
    cfg = load_config(env=env, require_db=True)
    assert cfg.database_url == "postgresql://u:p@h/db"
