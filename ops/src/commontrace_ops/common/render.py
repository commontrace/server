"""Pure markdown / HTML rendering for the audit issue and review digest."""
from __future__ import annotations

import json


def render_audit_issue(title: str, result: dict, facts: dict) -> str:
    lines = [f"# {title}", ""]
    grade = result.get("overall_grade", "?")
    lines.append(f"**Overall grade:** {grade}")
    lines.append("")
    if result.get("summary"):
        lines.append(result["summary"])
        lines.append("")

    lines.append("## Prioritized suggestions")
    lines.append("")
    suggestions = sorted(result.get("suggestions", []), key=lambda s: s.get("priority", 99))
    for s in suggestions:
        lines.append(f"### {s.get('priority', '?')}. {s.get('title', 'Untitled')}")
        lines.append(s.get("detail", ""))
        lines.append("")

    lines.append("## Per-repo assessment")
    lines.append("")
    for r in result.get("repos", []):
        lines.append(f"### {r.get('repo', '?')}")
        lines.append(r.get("assessment", ""))
        scores = r.get("scores", {})
        if scores:
            lines.append("")
            for dim, val in scores.items():
                lines.append(f"- {dim}: {val}/5")
        lines.append("")

    lines.append("---")
    lines.append("<details><summary>Raw gathered facts</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(facts, indent=2, default=str))
    lines.append("```")
    lines.append("</details>")
    return "\n".join(lines)


def _section(title: str, rows: list[str]) -> list[str]:
    out = [f"## {title}", ""]
    if not rows:
        out.append("_none_")
    else:
        out.extend(rows)
    out.append("")
    return out


def render_review_digest(subject: str, data: dict, result: dict) -> tuple[str, str]:
    prs = data.get("prs", [])
    pending = data.get("pending_traces", [])
    flagged = data.get("flagged_traces", [])
    amendments = data.get("amendments", [])

    rec_by = {
        "prs": {(r.get("repo"), r.get("number")): r for r in result.get("prs", [])},
        "traces": {r.get("id"): r for r in result.get("traces", [])},
        "amendments": {r.get("id"): r for r in result.get("amendments", [])},
    }

    total = len(prs) + len(pending) + len(flagged) + len(amendments)

    text_lines = [subject, "=" * len(subject), ""]
    if total == 0:
        text_lines.append("All clear — nothing pending this week. (heartbeat: job ran OK)")
    else:
        text_lines.append(f"{total} item(s) awaiting attention.")
    text_lines.append("")

    pr_rows = []
    for p in sorted(prs, key=lambda x: x.get("age_days", 0), reverse=True):
        rec = rec_by["prs"].get((p.get("repo"), p.get("number")), {})
        draft = " [draft]" if p.get("draft") else ""
        pr_rows.append(
            f"- **{p.get('repo')} #{p.get('number')}**{draft} {p.get('title', '')} "
            f"— {p.get('author', '?')}, {p.get('age_days', '?')}d old "
            f"→ **{rec.get('recommendation', '?')}**: {rec.get('reason', '')}"
        )
    text_lines += _section("Pull Requests (priority)", pr_rows)

    trace_rows = []
    for t in sorted(pending, key=lambda x: x.get("age_days", 0), reverse=True):
        rec = rec_by["traces"].get(t.get("id"), {})
        trace_rows.append(
            f"- **{t.get('title', t.get('id'))}** — {t.get('contributor', '?')}, "
            f"{t.get('age_days', '?')}d → **{rec.get('recommendation', '?')}**: "
            f"{rec.get('reason', '')}"
        )
    text_lines += _section("Pending Traces", trace_rows)

    flagged_rows = [
        f"- **{f.get('title', f.get('id'))}** — flagged {f.get('flagged_at', '?')}"
        for f in flagged
    ]
    text_lines += _section("Flagged Traces", flagged_rows)

    amend_rows = []
    for a in amendments:
        rec = rec_by["amendments"].get(a.get("id"), {})
        amend_rows.append(
            f"- amendment on trace {a.get('original_trace_id', '?')} "
            f"by {a.get('submitter', '?')} → **{rec.get('recommendation', '?')}**: "
            f"{rec.get('reason', '')}"
        )
    text_lines += _section("Amendments", amend_rows)

    text = "\n".join(text_lines)
    html = "<html><body><pre>" + _escape(text) + "</pre></body></html>"
    return text, html


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
