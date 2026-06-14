import json

import pytest

from commontrace_ops.common.config import Config
from commontrace_ops.common.llm import judge_json


def make_cfg():
    return Config(
        openai_api_key="sk", resend_api_key="re", github_token="gh",
        alert_from="a@x.com", alert_to="b@x.com",
        repos=["commontrace/server"], model="gpt-5.5",
        database_url=None, audit_issue_repo=None,
    )


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class FakeOpenAI:
    """Mimics openai.OpenAI().chat.completions.create()."""

    def __init__(self, content):
        self._content = content
        self.last_kwargs = None

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                return _FakeCompletion(outer._content)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_judge_json_parses_model_json_and_passes_model_and_messages():
    client = FakeOpenAI(json.dumps({"grade": "B", "items": [1, 2]}))
    out = judge_json(make_cfg(), "system rubric", {"facts": 1}, client=client)

    assert out == {"grade": "B", "items": [1, 2]}
    assert client.last_kwargs["model"] == "gpt-5.5"
    assert client.last_kwargs["response_format"] == {"type": "json_object"}
    msgs = client.last_kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "system rubric"
    assert msgs[1]["role"] == "user"
    assert json.loads(msgs[1]["content"]) == {"facts": 1}


def test_judge_json_raises_on_unparseable_content():
    client = FakeOpenAI("not json")
    with pytest.raises(ValueError):
        judge_json(make_cfg(), "sys", {"x": 1}, client=client)
