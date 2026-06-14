import pytest

from commontrace_ops.common.alerting import run_with_alerting
from commontrace_ops.common.config import Config


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="alerts@denemlabs.com", alert_to="tools@denemlabs.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


def test_success_path_does_not_email():
    sent = []
    run_with_alerting(lambda: "ok", "test-job", make_cfg(),
                      emailer=lambda cfg, **kw: sent.append(kw))
    assert sent == []


def test_failure_sends_email_then_reraises():
    sent = []

    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        run_with_alerting(boom, "oss-audit", make_cfg(),
                          emailer=lambda cfg, **kw: sent.append(kw))

    assert len(sent) == 1
    assert "oss-audit" in sent[0]["subject"]
    assert "kaboom" in sent[0]["body"]
    assert "ValueError" in sent[0]["body"]


def test_emailer_failure_does_not_mask_original():
    def boom():
        raise ValueError("original")

    def broken_emailer(cfg, **kw):
        raise RuntimeError("resend down")

    with pytest.raises(ValueError, match="original"):
        run_with_alerting(boom, "job", make_cfg(), emailer=broken_emailer)
