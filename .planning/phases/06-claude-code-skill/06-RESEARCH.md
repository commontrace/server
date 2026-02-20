# Phase 6: Claude Code Skill - Research

**Researched:** 2026-02-20
**Domain:** Claude Code plugin system (skill + commands + hooks + MCP auto-configuration)
**Confidence:** HIGH

## Summary

Phase 6 delivers the Claude Code skill layer: a Claude Code plugin that gives agents explicit `/trace:search` and `/trace:contribute` slash commands, auto-configures the MCP server connection on install, silently injects CommonTrace search results at task start, and prompts agents to contribute after task completion. The implementation surface is entirely in the `skill/` workspace directory (a Claude Code plugin), using no Python runtime — only Markdown command files, a SKILL.md, a hooks/hooks.json, and an .mcp.json.

Claude Code plugins are the correct unit of distribution for this feature. A plugin bundles commands, skills, hooks, and MCP server configuration into a single installable unit. The `.mcp.json` at plugin root auto-configures the MCP server connection when the plugin is enabled, satisfying SKIL-02 with zero manual setup. The `SessionStart` hook (fires when a session begins) is the correct mechanism for SKIL-03 (silent auto-query). The `Stop` hook (fires when Claude finishes responding) is the correct mechanism for SKIL-04 (post-task contribution prompt). The two slash commands (/trace:search and /trace:contribute) map directly to Claude Code `commands/` Markdown files.

The hardest design problem is SKIL-03: the auto-query hook must detect relevant context (repo, file type, error), call the MCP tool silently, threshold-gate injection so irrelevant sessions are not polluted, and complete fast enough to not block session start. The prior decisions note "Auto-query trigger heuristics have no established prior art — plan for iteration." This is accurate. The SessionStart hook provides the right lifecycle event, but context detection heuristics must be designed from scratch.

**Primary recommendation:** Implement Phase 6 as a Claude Code plugin in `skill/` with: `.mcp.json` for MCP auto-configuration (SKIL-02), `commands/trace/search.md` and `commands/trace/contribute.md` for slash commands (SKIL-01), a `SessionStart` command hook for silent auto-query (SKIL-03), and a `Stop` command hook for post-task contribution prompt (SKIL-04). All hooks call Python scripts bundled in `skill/hooks/` via `${CLAUDE_PLUGIN_ROOT}`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Claude Code plugin system | current | Plugin container | The only way to bundle MCP config + commands + hooks + skills for Claude Code |
| MCP (via .mcp.json) | current | Auto-configure CommonTrace MCP server on plugin install | Plugin .mcp.json starts the server automatically when plugin enables |
| Python 3.12+ | system | Hook scripts | jq-equivalent parsing, MCP tool call detection, context heuristics |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| bash | system | Lightweight hook scripts where Python is overkill | Fast checks (e.g., git repo detection) |
| jq | system | JSON parsing in shell hooks | When hook logic is simple enough for bash |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python hook scripts | Node.js scripts | Python already on system (uv workspace). Node requires separate install. |
| Plugin hooks | User-level `~/.claude/settings.json` hooks | Plugin hooks are bundled and activated on plugin install. User-level hooks require manual setup per machine. |
| SessionStart hook for auto-query | UserPromptSubmit hook for auto-query | SessionStart is more appropriate — fires once per session, not on every prompt. UserPromptSubmit would add latency to every user interaction. |
| SKILL.md skill triggering | Command-only approach (no skill) | SKILL.md provides the guidance Claude needs to know when to call the MCP tools autonomously. Both approaches are needed. |

**Installation:**
```bash
# The plugin is the skill/  directory in the commontrace workspace.
# Installing it = running: claude plugin install /path/to/commontrace/skill
# Or for development: claude --plugin-dir /path/to/commontrace/skill
```

## Architecture Patterns

### Recommended Project Structure
```
skill/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest (name, description, author)
├── .mcp.json                  # MCP server auto-configuration (SKIL-02)
├── commands/
│   └── trace/
│       ├── search.md          # /trace:search command (SKIL-01)
│       └── contribute.md      # /trace:contribute command (SKIL-01)
├── skills/
│   └── commontrace/
│       └── SKILL.md           # Skill context — when/how to use CommonTrace tools
├── hooks/
│   ├── hooks.json             # Hook event configuration
│   ├── session-start.py       # Auto-query logic (SKIL-03)
│   └── stop.py                # Post-task contribution prompt (SKIL-04)
├── pyproject.toml             # Already exists (empty deps, keep it)
└── README.md                  # Setup and usage docs
```

### Pattern 1: Plugin MCP Auto-Configuration (.mcp.json)
**What:** A `.mcp.json` at plugin root defines the CommonTrace MCP server. Claude Code auto-starts it when the plugin is enabled. No `claude mcp add` command needed.
**When to use:** Always — this is how SKIL-02 ("no manual MCP configuration required") is satisfied.
**Example:**
```json
{
  "commontrace": {
    "type": "http",
    "url": "${COMMONTRACE_MCP_URL:-http://localhost:8080/mcp}",
    "headers": {
      "X-API-Key": "${COMMONTRACE_API_KEY}"
    }
  }
}
```
Source: Official Claude Code MCP docs (code.claude.com/docs/en/mcp — "Plugin-provided MCP servers" section)

**Key detail:** `${COMMONTRACE_MCP_URL:-http://localhost:8080/mcp}` uses shell default expansion so local dev works without setting the variable. `${COMMONTRACE_API_KEY}` must be set in the user's environment — Claude Code passes it to the MCP config automatically.

**Alternative for stdio transport (local dev):**
```json
{
  "commontrace": {
    "command": "uv",
    "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/../mcp-server", "python", "-m", "app.server"],
    "env": {
      "COMMONTRACE_API_KEY": "${COMMONTRACE_API_KEY}",
      "API_BASE_URL": "${COMMONTRACE_API_BASE_URL:-http://localhost:8000}"
    }
  }
}
```
Use stdio for local development (runs the MCP server as a subprocess). Use HTTP for deployed environments.

### Pattern 2: Slash Commands as Markdown Files
**What:** Command files in `commands/trace/` become `/trace:search` and `/trace:contribute` slash commands. The namespace (`trace`) comes from the subdirectory name.
**When to use:** Always for SKIL-01.
**Example (commands/trace/search.md):**
```markdown
---
description: Search CommonTrace knowledge base for relevant traces
argument-hint: [query]
allowed-tools: ["mcp__plugin_commontrace_commontrace__search_traces"]
---

Search CommonTrace for traces matching the query: "$ARGUMENTS"

Use the mcp__plugin_commontrace_commontrace__search_traces tool to search.
Present results clearly, including title, context summary, solution summary, and trace ID.
If no results are found, say so clearly.
```

**Tool naming pattern:** `mcp__plugin_<plugin-name>_<server-name>__<tool-name>`
- Plugin name from plugin.json `"name"` field: `commontrace`
- Server name from .mcp.json key: `commontrace`
- Tool name from MCP server tool definition: `search_traces`
- Full name: `mcp__plugin_commontrace_commontrace__search_traces`

Source: mcp-integration SKILL.md from plugin-dev plugin (verified locally)

### Pattern 3: SessionStart Hook for Silent Auto-Query (SKIL-03)
**What:** A `SessionStart` command hook runs a Python script that detects context (git repo, recent errors, file types) and calls the CommonTrace MCP search tool if relevant context is found. Results are injected as `additionalContext` for Claude.
**When to use:** For SKIL-03. The hook runs at session start, before the user's first prompt.
**How it works:**

hooks/hooks.json:
```json
{
  "description": "CommonTrace auto-query and contribution hooks",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

The `matcher: "startup"` ensures auto-query only on new sessions, not on resume/clear/compact (which would re-inject context uselessly).

The script must:
1. Detect context from environment: `$CLAUDE_PROJECT_DIR`, git status, `CLAUDE_CODE_RESUME_TRANSCRIPT` if available
2. Run `claude mcp call commontrace search_traces` (or call the MCP tool directly via the plugin's MCP connection) — **this is the key open question** (see Open Questions)
3. Gate on relevance threshold: only inject if >= 1 result above confidence threshold
4. Return `additionalContext` via JSON stdout if results found, exit 0 with no output if not

SessionStart output format:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Relevant CommonTrace results for your session:\n\n1. [title]..."
  }
}
```

Source: Official hooks reference (code.claude.com/docs/en/hooks — "SessionStart decision control" section)

**Critical constraint:** The 200ms MCP read timeout from the MCP server (set in Phase 5) applies. The SessionStart hook itself has a 5-second timeout. These are compatible — the MCP call must return within that window. If CommonTrace is unavailable, the script exits 0 with no output (session continues normally).

### Pattern 4: Stop Hook for Post-Task Contribution Prompt (SKIL-04)
**What:** A `Stop` command hook runs a Python script when Claude finishes responding. The script checks if the session involved successful task completion and, if so, injects a contribution prompt as `systemMessage` or uses `decision: "block"` to continue the conversation.
**When to use:** For SKIL-04.
**How it works:**

hooks/hooks.json (added to Stop event):
```json
{
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop.py",
          "timeout": 10
        }
      ]
    }
  ]
}
```

Stop hook input includes `last_assistant_message` and `stop_hook_active`. The script must:
1. Check `stop_hook_active` — if `true`, this hook already ran once this cycle; do NOT block again (prevents infinite loop)
2. Check `last_assistant_message` for task completion signals ("completed", "done", "finished", "implemented", "fixed")
3. If task completion detected AND not already prompted: return `decision: "block"` with `reason` = contribution prompt text
4. If stop_hook_active is true (we already prompted): allow stop (`exit 0`)

Stop hook output to trigger contribution prompt:
```json
{
  "decision": "block",
  "reason": "Before we finish: Would you like to contribute this solution to CommonTrace? Use /trace:contribute to share it with future agents. (Or just continue if not applicable.)"
}
```

Source: Official hooks reference (code.claude.com/docs/en/hooks — "Stop decision control" section)

**Critical constraint:** The `stop_hook_active` field MUST be checked. If it is `true`, the hook is already running in a loop because it previously blocked Claude from stopping. Exit 0 unconditionally when `stop_hook_active` is true.

### Pattern 5: SKILL.md for Autonomous Context Guidance
**What:** The `skills/commontrace/SKILL.md` teaches Claude when to proactively use CommonTrace tools without being explicitly asked.
**When to use:** Always — SKILL.md context is what enables Claude to search traces before writing code and offer to contribute after solving problems.
**Example (skills/commontrace/SKILL.md frontmatter):**
```yaml
---
name: commontrace
description: This skill should be used when the agent is about to solve a coding problem, implement a feature, debug an error, or configure a tool. It provides access to the CommonTrace knowledge base of coding traces contributed by other AI agents. Search before writing code. Contribute after solving.
version: 0.1.0
---
```

### Pattern 6: MCP Tool Names in Commands
**What:** Commands must pre-allow MCP tools in frontmatter to avoid permission prompts.
**Full MCP tool name format:** `mcp__plugin_<plugin-name>_<server-name>__<tool-name>`

For this plugin (plugin name: `commontrace`, server name from .mcp.json: `commontrace`):
```
mcp__plugin_commontrace_commontrace__search_traces
mcp__plugin_commontrace_commontrace__contribute_trace
mcp__plugin_commontrace_commontrace__vote_trace
mcp__plugin_commontrace_commontrace__get_trace
mcp__plugin_commontrace_commontrace__list_tags
```

Source: mcp-integration SKILL.md (verified locally), pattern `mcp__plugin_<name>_<server>__<tool>`

### Anti-Patterns to Avoid
- **Auto-querying on every UserPromptSubmit:** This adds latency to every user message. Use SessionStart (once per session) instead.
- **Blocking session start to wait for CommonTrace:** The SessionStart hook must return within timeout. If CommonTrace is slow or down, exit 0 immediately — never block the user.
- **Infinite Stop loop:** Always check `stop_hook_active` before returning `decision: "block"`. If it is `true`, exit 0.
- **Hardcoded MCP server URL:** Use `${COMMONTRACE_MCP_URL:-http://localhost:8080/mcp}` with a sensible default.
- **Injecting all search results:** Gate injection on a relevance threshold. Do not inject 10 results when 0-2 are relevant.
- **Plugin name mismatch:** The plugin name in `plugin.json`, the `.mcp.json` server key, and the MCP tool prefix must be consistent. Mismatch causes tools to appear with wrong names.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP server connection config | Custom claude mcp add scripts | `.mcp.json` at plugin root | Auto-configured on plugin enable. No script needed. |
| Slash command routing | Custom command dispatch | `commands/trace/search.md`, `commands/trace/contribute.md` | Markdown files auto-discovered by Claude Code |
| Hook registration | Manual `.claude/settings.json` edits | `hooks/hooks.json` in plugin | Bundled, versioned, auto-applied on plugin install |
| Context injection format | Custom system prompt injection | `hookSpecificOutput.additionalContext` | Official API for injecting context from hooks |
| Stop loop detection | Custom counter/state file | `stop_hook_active` field in hook input | Built-in field explicitly provided for this purpose |

**Key insight:** The Claude Code plugin system handles all wiring automatically. The only custom code is the hook scripts for context detection (SKIL-03) and completion detection (SKIL-04) — which are ~50-100 lines of Python each.

## Common Pitfalls

### Pitfall 1: MCP Tool Names Are Sensitive to Plugin Name
**What goes wrong:** If plugin.json `name` is `"commontrace"` but the .mcp.json key is `"ct"`, the MCP tools appear as `mcp__plugin_commontrace_ct__search_traces` — which won't match pre-allowed tools in command frontmatter.
**Why it happens:** Tool name is constructed from `plugin-name` (from plugin.json) and `server-name` (from .mcp.json key).
**How to avoid:** Keep plugin name and .mcp.json key consistent. Use `commontrace` for both. Verify with `/mcp` command after installing plugin.
**Warning signs:** `/trace:search` command says tool not found or requires permission approval.

### Pitfall 2: SessionStart Hook Only Fires for `startup` Matcher
**What goes wrong:** Using no matcher (fires for startup, resume, clear, compact) causes auto-query to run on every `/clear` or context compaction — injecting context at the wrong time.
**Why it happens:** Default hook behavior when matcher is omitted fires on all session start types.
**How to avoid:** Use `"matcher": "startup"` to fire only on new sessions.
**Warning signs:** Context injected after /clear or mid-session compaction.

### Pitfall 3: Stop Hook Infinite Loop
**What goes wrong:** Stop hook always returns `decision: "block"`. Claude never stops. Session hangs.
**Why it happens:** Forgetting to check `stop_hook_active` before blocking.
**How to avoid:** First thing in stop.py: `if data.get("stop_hook_active"): sys.exit(0)`. Also: only block once per session (track with a flag file in `/tmp`).
**Warning signs:** Claude never finishes responding, session appears to loop.

### Pitfall 4: Context Detection That Always Triggers
**What goes wrong:** Auto-query hook runs for every session (Docker container management, documentation writing) even when CommonTrace results are irrelevant.
**Why it happens:** No context detection — always queries with an empty/generic query.
**How to avoid:** Detect context signals: git repo present, Python/JS/TypeScript files in cwd, recent error messages in transcript, CLAUDE.md mentions coding. Only query when signals are present.
**Warning signs:** CommonTrace results injected into sessions about writing, management, etc.

### Pitfall 5: Plugin Name Contains Characters That Break Tool Names
**What goes wrong:** Plugin named `"commontrace-skill"` causes tool name `mcp__plugin_commontrace-skill_commontrace__search_traces` which is invalid or unexpected.
**Why it happens:** Tool name format normalizes names but hyphens may cause issues.
**How to avoid:** Use a simple lowercase alphanumeric name like `"commontrace"` in plugin.json.
**Warning signs:** Tools appear with garbled names in `/mcp`.

### Pitfall 6: `${COMMONTRACE_API_KEY}` Not Set Causes Plugin Failure
**What goes wrong:** If `COMMONTRACE_API_KEY` is unset and .mcp.json references `${COMMONTRACE_API_KEY}` without a default, Claude Code fails to parse the config.
**Why it happens:** Claude Code's environment variable expansion fails for required vars without defaults.
**How to avoid:** Either document the requirement clearly, or use a default (but API key cannot have a safe default). Best practice: fail gracefully with a helpful error message when key is missing, rather than silently not connecting.
**Warning signs:** MCP server doesn't appear in `/mcp`, no error shown.

### Pitfall 7: Calling MCP Tools From Within a Hook
**What goes wrong:** Hook script tries to invoke MCP tools via `claude mcp call` but this is not the correct way hooks call MCP tools in the plugin architecture.
**Why it happens:** MCP tools are available to Claude (the agent), not to hook scripts directly. Hooks are shell scripts, not Claude agent turns.
**How to avoid:** Hook scripts should NOT call MCP tools. Instead, they should output `additionalContext` that prompts Claude to call the MCP tools, OR use the hook's `systemMessage` to instruct Claude to search. The auto-query must be done by Claude in response to the hook's context injection, not directly by the hook. (See Open Questions #1 for full analysis.)
**Warning signs:** Hook script hangs or errors on `claude mcp call`.

## Code Examples

Verified patterns from official sources:

### Plugin Manifest (plugin.json)
```json
{
  "name": "commontrace",
  "description": "CommonTrace knowledge base integration for Claude Code agents. Auto-searches for relevant traces at session start, provides /trace:search and /trace:contribute commands.",
  "author": {
    "name": "CommonTrace",
    "email": "support@commontrace.dev"
  }
}
```
Source: example-plugin/.claude-plugin/plugin.json (verified locally)

### MCP Auto-Configuration (.mcp.json) for HTTP Transport
```json
{
  "commontrace": {
    "type": "http",
    "url": "${COMMONTRACE_MCP_URL:-http://localhost:8080/mcp}",
    "headers": {
      "X-API-Key": "${COMMONTRACE_API_KEY}"
    }
  }
}
```
Source: Official Claude Code MCP docs (code.claude.com/docs/en/mcp) — "Plugin-provided MCP servers" section

### Search Command (commands/trace/search.md)
```markdown
---
description: Search CommonTrace knowledge base for coding traces
argument-hint: [query]
allowed-tools: ["mcp__plugin_commontrace_commontrace__search_traces"]
---

Search CommonTrace for traces matching: "$ARGUMENTS"

Use mcp__plugin_commontrace_commontrace__search_traces with:
- query: "$ARGUMENTS"
- limit: 5

Present each result with: title, context summary (2 sentences), solution summary (2 sentences), and trace ID.
If no results found, say so clearly. If CommonTrace is unavailable, say so and continue normally.
```
Source: command frontmatter docs (plugin-features-reference.md verified locally), MCP tool naming pattern (mcp-integration SKILL.md verified locally)

### Contribute Command (commands/trace/contribute.md)
```markdown
---
description: Contribute a trace to CommonTrace knowledge base
allowed-tools: ["mcp__plugin_commontrace_commontrace__contribute_trace", "mcp__plugin_commontrace_commontrace__list_tags"]
---

Guide the user through contributing a trace to CommonTrace.

Step 1: Ask what problem was solved (context_text).
Step 2: Ask what the solution was (solution_text).
Step 3: Ask for a short title (title).
Step 4: Use mcp__plugin_commontrace_commontrace__list_tags to show available tags, ask user to select applicable ones.
Step 5: Show a preview of the trace and ask for confirmation before submitting.
Step 6: Only after confirmation, use mcp__plugin_commontrace_commontrace__contribute_trace to submit.
Step 7: Report the trace ID from the result.

Never submit without explicit user confirmation. Always show a preview first.
```

### Hooks Configuration (hooks/hooks.json)
```json
{
  "description": "CommonTrace auto-query at session start, contribution prompt at task completion",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```
Source: hook-development SKILL.md (verified locally), hookify/hooks/hooks.json (verified locally)

### SessionStart Hook Script (hooks/session-start.py)
```python
#!/usr/bin/env python3
"""
SessionStart hook: detect coding context, inject CommonTrace search prompt.
SKIL-03: silent auto-query at task start.
"""
import json
import os
import sys

def detect_context(cwd: str) -> str | None:
    """Return a search query if coding context detected, else None."""
    # Signal 1: git repo present
    if not os.path.exists(os.path.join(cwd, ".git")):
        return None  # Not a code project

    # Signal 2: detect primary language from file extensions
    known_extensions = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb"}
    detected_lang = None
    try:
        for entry in os.scandir(cwd):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1]
                if ext in known_extensions:
                    detected_lang = ext.lstrip(".")
                    break
    except OSError:
        pass

    if detected_lang:
        return f"common patterns and pitfalls for {detected_lang} projects"

    return None

def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd", os.getcwd())

    query = detect_context(cwd)
    if not query:
        sys.exit(0)  # No relevant context, session starts normally

    # Inject context that prompts Claude to search CommonTrace
    result = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"[CommonTrace] This appears to be a coding project. "
                f"Consider searching CommonTrace for relevant traces before starting work. "
                f"Use: search_traces(query='{query}') via the MCP tool."
            )
        }
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
```

### Stop Hook Script (hooks/stop.py)
```python
#!/usr/bin/env python3
"""
Stop hook: prompt agent to contribute a trace after task completion.
SKIL-04: post-task contribution prompt with preview-confirm flow.
"""
import json
import sys

COMPLETION_SIGNALS = [
    "completed", "done", "finished", "implemented", "fixed", "solved",
    "working", "successfully", "resolved", "deployed"
]

def main():
    data = json.load(sys.stdin)

    # CRITICAL: Check stop_hook_active to prevent infinite loop
    if data.get("stop_hook_active"):
        sys.exit(0)

    last_message = data.get("last_assistant_message", "").lower()

    # Check for task completion signals
    if not any(signal in last_message for signal in COMPLETION_SIGNALS):
        sys.exit(0)  # No task completion detected

    # Prompt contribution (non-blocking — agent can decline)
    result = {
        "decision": "block",
        "reason": (
            "CommonTrace contribution opportunity: If you just solved a problem that others might face, "
            "consider contributing it to the shared knowledge base. "
            "Use /trace:contribute to start the contribution flow, or just say 'no thanks' to continue."
        )
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE transport in .mcp.json | HTTP transport in .mcp.json | MCP spec 2025 | SSE deprecated; use `"type": "http"` for remote servers |
| UserPromptSubmit for context injection | SessionStart for context injection | SessionStart hook launched 2025 | SessionStart fires once per session, correct for auto-query |
| Separate hook settings files per project | Plugin hooks/hooks.json | Plugin system launch | Bundled with plugin, auto-applied on install |
| Manual `claude mcp add` for team tools | `.mcp.json` in plugin root | Plugin MCP support launch | Zero-config MCP for plugin consumers |
| `stop_hook_active` absent from Stop input | `stop_hook_active` always present | Added to prevent infinite loops | Reliable loop detection; always check this field |

**Deprecated/outdated:**
- SSE transport: Use HTTP (`"type": "http"`) in .mcp.json. SSE still works but is deprecated.
- Plugin hooks without `hooks` wrapper: Plugin hooks/hooks.json REQUIRES a `"hooks"` wrapper object (not direct event array at root). This differs from user settings.json format.

## Open Questions

1. **How does the SessionStart hook call MCP tools?**
   - What we know: Hook scripts are shell commands, not Claude agent turns. They cannot use MCP tools directly. The `additionalContext` field injects text into Claude's context.
   - What's unclear: Can the hook inject context that causes Claude to automatically call the search_traces MCP tool, or does it only inject static text that Claude reads? The SKIL-03 success criterion says "silently queries CommonTrace based on detected context and injects relevant traces into agent context." This implies the actual MCP call must happen.
   - Two interpretations:
     - A) Hook does context detection only → outputs `additionalContext` instructing Claude to search → Claude then calls MCP tool proactively (but this requires Claude to act autonomously, not guaranteed)
     - B) Hook makes a direct HTTP call to the CommonTrace backend (bypassing MCP) using `requests` or `httpx` → formats results → outputs them as `additionalContext` (achieves true "silent injection" without Claude's involvement)
   - **Recommendation:** Option B is the only way to guarantee "silently queries CommonTrace without user prompting." The hook script calls the CommonTrace API directly (using `COMMONTRACE_API_KEY` and `COMMONTRACE_API_BASE_URL` env vars), bypassing MCP entirely for the auto-query use case. This is a key design decision the planner must make explicit.

2. **What context detection heuristics are sufficient for SKIL-03?**
   - What we know: "Auto-query trigger heuristics have no established prior art — plan for iteration" (prior decisions).
   - What's unclear: Which signals are reliable enough (git repo, file types, error messages in transcript, CLAUDE.md content) vs. which produce too many false positives.
   - Recommendation: Start with: (1) git repo present, (2) source code files in cwd, (3) query based on detected language. Skip if: no git repo (not a code project). The threshold question (how many results must be found to inject) should default to 1 but be tunable.

3. **How to track "already prompted for contribution" in the Stop hook?**
   - What we know: The Stop hook fires on every Claude response stop. `stop_hook_active` prevents infinite loop within one stop cycle. But if Claude responds again (user says "thanks"), Stop fires again.
   - What's unclear: Should the hook prompt for every task completion in a session, or only once?
   - Recommendation: Write a session-scoped flag file to `/tmp/commontrace-contributed-{session_id}` on first prompt. Check it before prompting again. The `session_id` is in the hook input.

4. **What is the exact plugin name / MCP tool prefix?**
   - What we know: Tool name is `mcp__plugin_<plugin-name>_<server-name>__<tool-name>`. Plugin name comes from plugin.json `name` field.
   - What's unclear: Whether hyphens in plugin/server names are preserved or normalized (e.g., `common-trace` → `common_trace` in tool prefix).
   - Recommendation: Use `"commontrace"` (no hyphens) in plugin.json to avoid normalization surprises. Use `"commontrace"` as the .mcp.json server key too. Full tool prefix: `mcp__plugin_commontrace_commontrace__`.

## Sources

### Primary (HIGH confidence)
- Official Claude Code hooks reference — SessionStart, Stop events, decision control, `stop_hook_active`, `additionalContext`: https://code.claude.com/docs/en/hooks (fetched 2026-02-20)
- Official Claude Code MCP docs — Plugin MCP auto-configuration, `.mcp.json` at plugin root, HTTP transport: https://code.claude.com/docs/en/mcp (fetched 2026-02-20)
- plugin-dev plugin SKILL.md (skill-development) — skill structure, SKILL.md format, progressive disclosure: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/skill-development/SKILL.md`
- plugin-dev plugin (mcp-integration) — MCP tool naming convention `mcp__plugin_<name>_<server>__<tool>`: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/mcp-integration/SKILL.md`
- plugin-dev plugin (hook-development) — hooks/hooks.json format (wrapper with `"hooks"` key), SessionStart matcher values, Stop decision control: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/hook-development/SKILL.md`
- plugin-dev plugin (command-development) — frontmatter reference, allowed-tools format, argument-hint: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/command-development/references/frontmatter-reference.md`
- hookify plugin — real-world hooks.json with plugin wrapper format: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/hookify/hooks/hooks.json`
- example-plugin — minimal plugin.json + .mcp.json structure: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/example-plugin/`
- Phase 5 research (05-RESEARCH.md) — MCP server tools available, MCP server config patterns: `/home/bitnami/commontrace/.planning/phases/05-mcp-server/05-RESEARCH.md`

### Secondary (MEDIUM confidence)
- WebSearch for plugin MCP auto-configuration: confirmed plugin `.mcp.json` auto-starts MCP servers when plugin enabled (multiple sources, consistent with official docs)
- plugin-features-reference.md — plugin-specific command discovery, `${CLAUDE_PLUGIN_ROOT}`: `/home/bitnami/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/command-development/references/plugin-features-reference.md`

### Tertiary (LOW confidence)
- Stop hook contribution flow heuristic (completion signal detection via last_assistant_message keywords) — no official prior art, designed from first principles

## Metadata

**Confidence breakdown:**
- Plugin structure: HIGH — verified from official docs + local plugin examples
- MCP auto-configuration via .mcp.json: HIGH — official docs confirm, local example-plugin/.mcp.json verified
- Slash command format: HIGH — verified from plugin frontmatter docs + real plugin examples
- Hook events (SessionStart, Stop): HIGH — official hooks reference fetched and verified
- `stop_hook_active` field: HIGH — official docs confirm, designed specifically to prevent infinite loops
- `additionalContext` for SessionStart: HIGH — official docs confirm the field and format
- MCP tool naming convention: HIGH — verified from mcp-integration SKILL.md
- Context detection heuristics (SKIL-03): LOW — no established prior art, designed from first principles
- Direct API call from hook (Option B for SKIL-03): MEDIUM — technically sound but not a documented plugin pattern

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (Claude Code plugin system is stable; 30-day validity)
