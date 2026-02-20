---
phase: 06-claude-code-skill
plan: 02
subsystem: skill
tags: [claude-code, hooks, session-start, stop, auto-query, contribution-prompt]

requires:
  - phase: 06-claude-code-skill
    plan: 01
    provides: Plugin manifest at skill/.claude-plugin/plugin.json with CLAUDE_PLUGIN_ROOT env var available to hooks

provides:
  - hooks.json at skill/hooks/hooks.json — hook event config for SessionStart (startup matcher, 5s) and Stop (10s)
  - session_start.py at skill/hooks/session_start.py — silent auto-query to CommonTrace backend at session start
  - stop.py at skill/hooks/stop.py — post-task contribution prompt with loop prevention

affects:
  - 06-03 (skill packaging and install instructions reference hooks/)
  - All Claude Code agents that install the commontrace plugin

tech-stack:
  added: []
  patterns:
    - Hooks are shell commands (not MCP tool calls) — must use direct HTTP, not MCP client
    - urllib.request with 3s timeout inside 5s total hook budget — leaves headroom for Python startup
    - SessionStart matcher=startup prevents re-injection on resume/clear/compact
    - stop_hook_active checked first (within-cycle loop prevention), then session flag file (cross-cycle)
    - Session key: session_id from payload (primary) or os.getppid() (fallback); never os.getpid()
    - Flag file at /tmp/commontrace-prompted-{session_key} persists for session lifetime

key-files:
  created:
    - skill/hooks/hooks.json
    - skill/hooks/session_start.py
    - skill/hooks/stop.py
  modified: []

key-decisions:
  - "Direct HTTP call in session_start.py (not MCP) — hooks are shell commands, cannot call MCP tools; urllib.request is stdlib with zero deps"
  - "matcher=startup on SessionStart — prevents re-injection on resume/clear/compact; only fires on new sessions"
  - "stop_hook_active checked first (loop prevention within one stop cycle), then session flag file (prevents re-prompting across responses)"
  - "Session key uses session_id from payload or os.getppid() fallback — never os.getpid() (new PID per invocation would break flag file lookup)"
  - "Conservative completion signal list — split-into-words check for single words, substring for multi-word patterns — avoids false positives"

duration: 2min
completed: 2026-02-20
---

# Phase 6 Plan 2: Hooks — SessionStart Auto-Query and Stop Contribution Prompt Summary

**SessionStart hook silently queries CommonTrace at new session startup and injects relevant traces as context; Stop hook prompts contribution after task completion with dual loop prevention (stop_hook_active + session flag file)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-20T21:27:08Z
- **Completed:** 2026-02-20T21:29:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created hooks.json with SessionStart (matcher: startup, 5s timeout) and Stop (10s timeout) event configuration — ${CLAUDE_PLUGIN_ROOT}/hooks/*.py references wired in
- Created session_start.py: detects git+source file context, identifies primary language and framework from manifest files (pyproject.toml, package.json, Cargo.toml, go.mod), queries CommonTrace backend directly via urllib, formats results as additionalContext for Claude's awareness at session start
- Created stop.py: checks stop_hook_active first (prevents infinite loop within a stop cycle), then checks /tmp/commontrace-prompted-{session_key} flag file (prevents re-prompting across responses in same session), detects task completion via conservative word/pattern list, emits decision:block with contribution prompt
- All three scripts exit 0 silently on any error — SessionStart never blocks session start, Stop never prevents Claude from stopping

## Task Commits

Each task was committed atomically:

1. **Task 1: Hooks configuration and SessionStart auto-query** - `05fd57b` (feat)
2. **Task 2: Stop hook for post-task contribution prompt** - `7a1f0d6` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `skill/hooks/hooks.json` - Hook event config: SessionStart with startup matcher and 5s timeout, Stop with 10s timeout
- `skill/hooks/session_start.py` - Context detection (git repo + source files + framework detection), direct HTTP to /api/v1/traces/search with 3s timeout, additionalContext injection; exits 0 silently on all failures
- `skill/hooks/stop.py` - stop_hook_active guard, session flag file at /tmp/commontrace-prompted-{session_key}, completion signal detection (word boundary + pattern), decision:block contribution prompt

## Decisions Made

- Direct HTTP (urllib.request) in session_start.py rather than MCP tool calls — hooks execute as shell commands in a subprocess, not as Claude agent turns; MCP tools are unavailable from that context
- `"matcher": "startup"` on SessionStart — without this, the hook fires on every resume/clear/compact, re-injecting context uselessly and adding latency each time
- stop_hook_active checked before the flag file — the active flag prevents loops within the same stop cycle (already in stop processing); the flag file prevents prompting again on the next response in the same session; both guards are needed for different scenarios
- `os.getppid()` as session_id fallback — the parent PID (Claude's process) is stable within a session; `os.getpid()` would create a fresh PID per invocation, making the flag file never findable
- Completion signal list is conservative by design — "working now" and "all tests pass" as patterns rather than individual words to avoid false matches on common phrasing; word-boundary split prevents "done" from matching "abandoned"

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all file content matched plan spec exactly. All verification checks passed on first run.

## Next Phase Readiness

- skill/hooks/ directory complete — all three files present and executable
- hooks.json is valid JSON with correct event names, matchers, timeouts, and command references
- Plugin shell from 06-01 + hooks from 06-02 = complete Claude Code plugin
- Plan 06-03 can now address skill packaging and install documentation

## Self-Check: PASSED
