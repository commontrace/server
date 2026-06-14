"""Triage prompt + judge call for the contribution review digest."""
from __future__ import annotations

from ..common.llm import judge_json

TRIAGE_SYSTEM_PROMPT = """\
You triage the open contribution queue for CommonTrace. You receive JSON with:
open pull requests (the PRIORITY — they block release), pending traces, flagged
traces, and amendments.

For each PULL REQUEST recommend one of: merge | review-needed | close, with a
one-line reason. Treat PRs as the highest priority and surface the oldest first.
For each TRACE and AMENDMENT recommend one of: keep | reject | needs-work, with a
one-line reason.

Respond ONLY with a JSON object of this exact shape:
{
  "prs": [{"repo": "owner/name", "number": 0,
           "recommendation": "merge|review-needed|close", "reason": "..."}],
  "traces": [{"id": "...", "recommendation": "keep|reject|needs-work", "reason": "..."}],
  "amendments": [{"id": "...", "recommendation": "keep|reject|needs-work", "reason": "..."}]
}
"""


def triage(cfg, data: dict, *, client=None) -> dict:
    return judge_json(cfg, TRIAGE_SYSTEM_PROMPT, data, client=client)
