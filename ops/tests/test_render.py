from commontrace_ops.common.render import render_audit_issue, render_review_digest


def test_render_audit_issue_includes_grade_suggestions_and_facts_footer():
    result = {
        "overall_grade": "B",
        "summary": "Solid but docs thin.",
        "repos": [
            {"repo": "commontrace/server", "assessment": "Good CI.",
             "scores": {"documentation": 3, "ci_tests": 5}},
        ],
        "suggestions": [
            {"priority": 1, "title": "Add SECURITY.md", "detail": "No disclosure policy."},
            {"priority": 2, "title": "Add CONTRIBUTING", "detail": "Onboarding unclear."},
        ],
    }
    facts = {"commontrace/server": {"open_issues": 4}}
    body = render_audit_issue("OSS Health Audit — 2026-W24", result, facts)

    assert "OSS Health Audit — 2026-W24" in body
    assert "**Overall grade:** B" in body
    assert "Add SECURITY.md" in body
    assert "Add CONTRIBUTING" in body
    assert "commontrace/server" in body
    assert body.index("Add SECURITY.md") < body.index("Add CONTRIBUTING")
    assert "open_issues" in body


def test_render_review_digest_priority_prs_first_and_returns_text_and_html():
    data = {
        "prs": [{"repo": "commontrace/mcp", "number": 7, "title": "Fix proxy",
                 "author": "alice", "age_days": 9, "draft": False}],
        "pending_traces": [{"id": "t1", "title": "Redis tip", "contributor": "bob",
                            "age_days": 3}],
        "flagged_traces": [],
        "amendments": [],
    }
    result = {
        "prs": [{"repo": "commontrace/mcp", "number": 7,
                 "recommendation": "review-needed", "reason": "CI red."}],
        "traces": [{"id": "t1", "recommendation": "keep", "reason": "Useful."}],
        "amendments": [],
    }
    text, html = render_review_digest("CommonTrace contribution review — 2026-W24", data, result)

    assert "CommonTrace contribution review — 2026-W24" in text
    assert text.index("Pull Requests") < text.index("Pending Traces")
    assert "#7" in text
    assert "review-needed" in text
    assert "<html" in html.lower() or "<table" in html.lower()
    assert "#7" in html


def test_render_review_digest_empty_queue_is_heartbeat():
    data = {"prs": [], "pending_traces": [], "flagged_traces": [], "amendments": []}
    result = {"prs": [], "traces": [], "amendments": []}
    text, html = render_review_digest("subj", data, result)
    assert "nothing pending" in text.lower() or "all clear" in text.lower()
