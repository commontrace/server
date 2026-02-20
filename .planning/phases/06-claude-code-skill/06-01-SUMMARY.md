---
phase: 06-claude-code-skill
plan: 01
subsystem: skill
tags: [claude-code, plugin, mcp, slash-commands, skill-layer]

requires:
  - phase: 05-mcp-server
    provides: FastMCP HTTP server on port 8080 with search_traces, contribute_trace, vote_trace, get_trace, list_tags tools

provides:
  - Claude Code plugin manifest at skill/.claude-plugin/plugin.json (name "commontrace")
  - MCP auto-configuration at skill/.mcp.json (HTTP transport, no manual claude mcp add needed)
  - /trace:search slash command at skill/commands/trace/search.md
  - /trace:contribute slash command at skill/commands/trace/contribute.md with preview-confirm flow
  - SKILL.md at skill/skills/commontrace/SKILL.md for autonomous tool activation guidance

affects:
  - 06-02-hooks (SessionStart and Stop hooks build on this plugin structure)
  - downstream Claude Code agents that install this plugin

tech-stack:
  added: []
  patterns:
    - Plugin name in plugin.json and .mcp.json server key must match — both "commontrace" — determines MCP tool prefix
    - MCP tool prefix pattern: mcp__plugin_<plugin-name>_<server-name>__<tool-name>
    - allowed-tools frontmatter in command .md files pre-allows MCP tools to avoid permission prompts
    - Shell default expansion ${VAR:-default} for optional env vars (COMMONTRACE_MCP_URL) vs required (COMMONTRACE_API_KEY has no default)
    - SKILL.md description field drives when Claude autonomously activates the skill

key-files:
  created:
    - skill/.claude-plugin/plugin.json
    - skill/.mcp.json
    - skill/commands/trace/search.md
    - skill/commands/trace/contribute.md
    - skill/skills/commontrace/SKILL.md
  modified: []

key-decisions:
  - "Plugin name and .mcp.json server key both 'commontrace' — consistency required for correct MCP tool prefix mcp__plugin_commontrace_commontrace__*"
  - "HTTP transport in .mcp.json (not stdio) — targets deployed CommonTrace MCP server on port 8080"
  - "COMMONTRACE_API_KEY has no default — must be set in user environment; no safe default possible for an API key"
  - "/trace:contribute enforces preview-then-confirm flow — SKIL-04 requirement that no trace submits without explicit 'yes'"
  - "SKILL.md description field describes coding contexts explicitly — drives autonomous skill activation for framework/debug/config tasks"

patterns-established:
  - "Command pattern: allowed-tools frontmatter + $ARGUMENTS expansion + graceful degradation if unavailable"
  - "Contribute flow: collect-then-preview-then-confirm — never submits without explicit user confirmation"

duration: 2min
completed: 2026-02-20
---

# Phase 6 Plan 1: Claude Code Plugin Shell Summary

**Claude Code plugin with MCP auto-configuration, /trace:search and /trace:contribute slash commands, and SKILL.md for autonomous CommonTrace activation — zero manual setup required**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-20T21:22:25Z
- **Completed:** 2026-02-20T21:24:07Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created plugin manifest (skill/.claude-plugin/plugin.json) and MCP auto-configuration (skill/.mcp.json) — installing this plugin automatically configures the CommonTrace MCP server, no `claude mcp add` command needed
- Created /trace:search command with search_traces pre-allowed and $ARGUMENTS expansion for query passthrough
- Created /trace:contribute command with multi-step preview-confirm flow (list tags, preview, ask "yes/no", only submit after explicit yes)
- Created SKILL.md with autonomous activation guidance for coding contexts — "Search before writing code. Contribute after solving."

## Task Commits

Each task was committed atomically:

1. **Task 1: Plugin manifest and MCP auto-configuration** - `23fb95b` (feat)
2. **Task 2: Slash commands and SKILL.md** - `55ef4dd` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `skill/.claude-plugin/plugin.json` - Plugin manifest with name "commontrace" and author info
- `skill/.mcp.json` - HTTP MCP server config pointing to ${COMMONTRACE_MCP_URL:-http://localhost:8080/mcp} with X-API-Key header
- `skill/commands/trace/search.md` - /trace:search command pre-allowing search_traces, formats 5 results with title/context/solution/tags/ID
- `skill/commands/trace/contribute.md` - /trace:contribute command with 7-step guided flow, preview at step 5, confirmation required before step 6 submission
- `skill/skills/commontrace/SKILL.md` - Skill context document defining when to search (before coding) and when to contribute (after solving)

## Decisions Made

- Plugin name "commontrace" (no hyphens) — avoids normalization surprises in MCP tool prefix construction
- HTTP transport for .mcp.json — targets the deployed FastMCP server from Phase 5 on port 8080
- `${COMMONTRACE_API_KEY}` has no default value — API keys cannot have safe defaults; documented requirement in SKILL.md
- `allowed-tools` in command frontmatter — pre-allows MCP tools so agents aren't interrupted by permission prompts
- SKILL.md description uses explicit coding context triggers ("framework, library, or API", "error message or debugging", "configuration or setup") — concrete triggers are more reliable than vague ones

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all file content matched plan spec exactly. Artifact check for "Search before writing code" in SKILL.md was split across two lines in the YAML block scalar but the text is present.

## User Setup Required

`COMMONTRACE_API_KEY` must be set in the user's environment before using the plugin. The MCP server won't authenticate without it. `COMMONTRACE_MCP_URL` is optional (defaults to http://localhost:8080/mcp for local development).

## Next Phase Readiness

- Plugin shell is complete and installable — `claude plugin install /path/to/commontrace/skill`
- Plan 06-02 can now add SessionStart and Stop hooks to skill/hooks/ — the plugin structure is ready for it
- All MCP tool names in commands use the correct prefix (mcp__plugin_commontrace_commontrace__) — hooks can reuse these names

## Self-Check: PASSED

All 6 files found on disk. Both task commits verified in git log (23fb95b, 55ef4dd).

---
*Phase: 06-claude-code-skill*
*Completed: 2026-02-20*
