"""OpenAI Chat Completions JSON-mode wrapper. Ops tooling only — not product."""
from __future__ import annotations

import json

from .config import Config


def _make_client(cfg: Config):
    from openai import OpenAI

    return OpenAI(api_key=cfg.openai_api_key)


def judge_json(cfg: Config, system_prompt: str, user_payload: dict, *, client=None) -> dict:
    """One JSON-mode completion. Returns parsed dict. Raises ValueError if the
    model returns non-JSON."""
    client = client or _make_client(cfg)
    resp = client.chat.completions.create(
        model=cfg.model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"model returned non-JSON content: {content!r}") from e
