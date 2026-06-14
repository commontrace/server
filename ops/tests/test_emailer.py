import pytest

from commontrace_ops.common.config import Config
from commontrace_ops.common.emailer import send_email
from tests.conftest import FakeHTTPClient, FakeResponse


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re-key", github_token="gh",
        alert_from="alerts@denemlabs.com", alert_to="tools@denemlabs.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


def test_send_email_posts_to_resend_with_auth_and_payload():
    client = FakeHTTPClient(FakeResponse(200, {"id": "email_123"}))
    cfg = make_cfg()
    send_email(cfg, subject="Hi", body="plain text", client=client)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re-key"
    payload = call["json"]
    assert payload["from"] == "alerts@denemlabs.com"
    assert payload["to"] == ["tools@denemlabs.com"]
    assert payload["subject"] == "Hi"
    assert payload["text"] == "plain text"
    assert "html" not in payload


def test_send_email_includes_html_when_provided():
    client = FakeHTTPClient(FakeResponse(200, {"id": "x"}))
    send_email(make_cfg(), subject="S", body="t", html="<p>t</p>", client=client)
    assert client.calls[0]["json"]["html"] == "<p>t</p>"


def test_send_email_raises_on_non_2xx():
    client = FakeHTTPClient(FakeResponse(422, {"error": "bad"}, text="bad"))
    with pytest.raises(RuntimeError) as exc:
        send_email(make_cfg(), subject="S", body="t", client=client)
    assert "422" in str(exc.value)
