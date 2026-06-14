import pytest

from commontrace_ops.common.alerting import run_with_alerting
from commontrace_ops.common.config import Config
from commontrace_ops.common.discord import _chunks, send_discord
from tests.conftest import FakeHTTPClient, FakeResponse


def make_cfg(discord_url=None):
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="alerts@denemlabs.com", alert_to="tools@denemlabs.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
        discord_webhook_url=discord_url,
    )


def test_chunks_short_content_single_piece():
    assert _chunks("hello") == ["hello"]


def test_chunks_splits_on_newline_boundary():
    content = "a" * 1500 + "\n" + "b" * 1500
    parts = _chunks(content, limit=2000)
    assert len(parts) == 2
    assert parts[0] == "a" * 1500
    assert parts[1] == "b" * 1500


def test_chunks_hard_split_when_no_newline():
    content = "x" * 4500
    parts = _chunks(content, limit=2000)
    assert [len(p) for p in parts] == [2000, 2000, 500]


def test_send_discord_posts_content():
    client = FakeHTTPClient(FakeResponse(status_code=204))
    send_discord("https://discord/wh", "boom", client=client)
    assert len(client.calls) == 1
    assert client.calls[0]["url"] == "https://discord/wh"
    assert client.calls[0]["json"]["content"] == "boom"


def test_send_discord_raises_on_non_2xx():
    client = FakeHTTPClient(FakeResponse(status_code=400, text="bad"))
    with pytest.raises(RuntimeError, match="Discord send failed: 400"):
        send_discord("https://discord/wh", "x", client=client)


def test_alerting_posts_to_discord_when_configured():
    sent = []
    discord = []

    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        run_with_alerting(
            boom, "oss-audit", make_cfg(discord_url="https://discord/wh"),
            emailer=lambda cfg, **kw: sent.append(kw),
            discord_send=lambda url, content, **kw: discord.append((url, content)),
        )

    assert len(sent) == 1
    assert len(discord) == 1
    assert discord[0][0] == "https://discord/wh"
    assert "oss-audit" in discord[0][1]
    assert "kaboom" in discord[0][1]


def test_alerting_skips_discord_when_unconfigured():
    discord = []

    def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        run_with_alerting(
            boom, "job", make_cfg(discord_url=None),
            emailer=lambda cfg, **kw: None,
            discord_send=lambda url, content, **kw: discord.append(content),
        )

    assert discord == []


def test_alerting_discord_failure_does_not_mask_original():
    def boom():
        raise ValueError("original")

    with pytest.raises(ValueError, match="original"):
        run_with_alerting(
            boom, "job", make_cfg(discord_url="https://discord/wh"),
            emailer=lambda cfg, **kw: None,
            discord_send=lambda url, content, **kw: (_ for _ in ()).throw(RuntimeError("discord down")),
        )
