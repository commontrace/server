# Phase 05 Plan Review

**Date:** 2026-02-20
**Plans reviewed:** 05-01-PLAN.md, 05-02-PLAN.md
**Checker result:** 2 blockers, 3 warnings (1 skipped as acceptable)

---

## Blocker 1: Wrong import path for `Depends` and `CurrentHeaders`

- **Severity:** Blocker (would cause ImportError at runtime)
- **Files:** 05-01-PLAN.md line 276, 05-02-PLAN.md (indirect reference)
- **Problem:** `from fastmcp.server.dependencies import CurrentHeaders, Depends` — `Depends` does not exist at that path in FastMCP v3.0.0
- **Fix applied:** Changed to `from fastmcp.dependencies import Depends, CurrentHeaders` in 05-01-PLAN.md. Added clarification note in 05-02-PLAN.md Part D.

## Blocker 2: Verify block uses non-existent `mcp._tool_manager`

- **Severity:** Blocker (would cause AttributeError during verification)
- **Files:** 05-01-PLAN.md lines 470, 483
- **Problem:** `mcp._tool_manager.tools.values()` and `mcp._tool_manager.tools` do not exist in FastMCP 3.0.0
- **Fix applied:** Replaced with `grep -c '@mcp.tool' server.py` for tool count and `uv run python -c "from app.server import mcp; print(mcp.name)"` for name check.

## Warning 1: Ambiguous import instruction for `api/app/main.py`

- **Severity:** Warning (executor could guess wrong router names)
- **File:** 05-01-PLAN.md line 128
- **Problem:** `from app.routers import ... tags` — ellipsis is ambiguous
- **Fix applied:** Replaced with explicit `from app.routers import amendments, auth, moderation, reputation, search, tags, traces, votes`.

## Warning 2: 05-02 Task 2 Part C should say "replace entire methods"

- **Severity:** Warning (executor could partially patch instead of full replacement)
- **File:** 05-02-PLAN.md Task 2 Part C
- **Problem:** Instruction said "Update post() and get() methods" — executor could try incremental edit
- **Fix applied:** Added explicit instruction: "Replace the entire `post()` and `get()` method bodies from 05-01 with the versions below. Do not partially patch — overwrite each method completely."

## Warning 3: `must_haves` truths are implementation-focused (skipped)

- **Severity:** Low warning
- **File:** 05-01-PLAN.md
- **Problem:** Truths describe implementation details rather than user-facing outcomes
- **Decision:** No change needed — truths are testable and map to the phase goal. Acceptable as-is.
