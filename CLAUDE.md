# CommonTrace Development Guide

## What This Project Is

CommonTrace is a shared knowledge base for AI coding agents. When an agent solves a problem, it contributes the solution. When another agent faces the same problem, it finds the solution. The goal is collective intelligence — agents learn from each other across projects, users, and sessions.

Four repos, four Railway services:
- **commontrace/server** (`/home/bitnami/commontrace/api/`) — FastAPI backend, PostgreSQL + pgvector, Redis
- **commontrace/mcp** (`/tmp/ct-mcp/`) — FastMCP 3.0 HTTP proxy to API
- **commontrace/frontend** (`/tmp/ct-frontend/`) — Jinja2 static site, nginx
- **commontrace/skill** (`/tmp/ct-skill/`) — Claude Code plugin (hooks + SKILL.md)

## Core Design Principles

### 1. No LLM API calls — structural intelligence only
The user explicitly rejected using Anthropic SDK, OpenAI (beyond embeddings), or any LLM API for analysis. All intelligence in the skill hooks must be **structural** — detected from tool-use sequences, file changes, error patterns, and timing. No NLU on user messages. No summarization. No classification calls. The only LLM cost is OpenAI text-embedding-3-small for vector search (~$0.02/1M tokens).

### 2. Knowledge detection = state transitions
The fundamental question is: "how does an AI agent know it just learned something worth remembering?" The answer is structural detection of **state transitions** where "not knowing" becomes "knowing":

- Error → Fix → Verify (the agent didn't know how to fix it, now it does)
- Research → Implement (the agent searched for knowledge, then applied it)
- Approach reversal (the agent's initial mental model was wrong)
- User correction (the user redirected the approach — the gap between initial and correct is the knowledge)
- Test fail → Code fix → Test pass (TDD-style discovery)

Each transition has a **weight** reflecting how valuable the knowledge typically is. Temporal proximity compounding (synaptic tagging) boosts co-occurring patterns. The total score must reach 4.0 before prompting the user.

### 3. Somatic intensity — harder-won knowledge ranks higher
Inspired by Damasio's somatic marker hypothesis. Every trace carries a `somatic_intensity` (0.0-1.0) computed from detection metadata at ingestion time. A trace born from a 45-minute, 15-error security vulnerability investigation permanently outranks a 2-minute convenience finding in search results. The intensity is the **emotional residue** of the learning experience, encoded structurally.

### 4. Neuroscience-inspired memory model
- **Levels of processing** (depth_score): richer context = better retrieval
- **Temporal decay** (half_life_days): knowledge fades unless retrieved
- **Memory temperature** (HOT/WARM/COOL/COLD/FROZEN): activity-based priority
- **Convergence detection**: same solution from different contexts = universal knowledge
- **Spreading activation**: related traces boost each other in search
- **Context fingerprinting**: language/framework/OS alignment boosts relevance

### 5. Skill hooks are the bottleneck, not the API
The API is mature. The skill (what agents actually use) determines:
- **When** to search (triggers)
- **Whether** to prompt for contribution (importance scoring)
- **What metadata** to include (detection pattern, error count, time invested)
- **How** to learn across sessions (persistent SQLite store)

Most improvements should focus on the skill hooks.

## Architecture Quick Reference

### Skill Hook Pipeline
```
session_start.py → detect project context, search CommonTrace, write bridge files
user_prompt.py   → count user turns, record timestamps
post_tool_use.py → record events (errors/changes/research), detect knowledge candidates
stop.py          → score importance, prompt for contribution, persist session data, report telemetry
```

### Knowledge Detection Patterns (17 total)
| Weight | Pattern | Signal |
|--------|---------|--------|
| 3.0 | error_resolution | error → code change → successful verification |
| 2.5 | security_hardening | security file changes after errors |
| 2.5 | user_correction | same file edited before and after user message |
| 2.5 | approach_reversal | Write to file previously Edit-ed 3+ times |
| 2.0 | test_fix_cycle | test fails → code fix → test passes |
| 2.0 | dependency_resolution | package manager errors → config fix → success |
| 2.0 | config_discovery | config changes that resolved errors |
| 2.0 | novelty_encounter | new language/domain in this project |
| 2.0 | infra_discovery | infrastructure file changes after errors |
| 2.0 | migration_pattern | 5+ files across dirs + config changes |
| 2.0 | research_then_implement | search/fetch then code with no errors |
| 1.5 | generation_effect | solved without any external knowledge |
| 1.5 | cross_file_breadth | changes spanning 3+ directories |
| 1.5 | iteration_depth | same file edited 3+ times (scales to 2.0) |
| 1.5 | workaround | research + errors + changes |
| 1.0 | temporal_investment | long session with sustained activity |
| — | fail_then_succeed | bash success after error → change sequence (detected and labeled in artifacts; not yet weighted in stop.py scoring) |

Plus a dynamic `user_emphasis` booster (1.0–1.5) scored in stop.py from structural emphasis signals. Source of truth: `hooks/post_tool_use.py` (detection) + `hooks/stop.py` (scoring) — trust the code over this table.

### Search Ranking Formula
```
score = similarity * trust * depth * decay * ctx_boost * convergence * temp_mult * validity * somatic_mult
```

### Persistent Local Store
SQLite at `~/.commontrace/local.db` (schema v3 as of skill v0.3.0) — survives across sessions, 5 tables:
- `projects` — working directory → project identity (language/framework fingerprint)
- `sessions` — per-session stats (errors, resolutions, contributions)
- `trace_cache` — pointers to traces seen (id + title only, no content)
- `trigger_feedback` — fired/consumed per trigger (reinforcement; assisted resolutions recorded as `local:<hash>` consumption)
- `error_signatures` — deduplicated per project (UNIQUE(project_id, signature)) with resolution payload: `last_seen_at`, `seen_count`, `resolved_at`, `fix_command`, `fix_files` (JSON basenames), `trace_id`. Powers error-time injection: when a previously resolved signature recurs, the known fix is injected at the failure moment.

Source of truth is `hooks/local_store.py` (`_SCHEMA` + `CURRENT_SCHEMA_VERSION`) — trust the code over this list.

## Development Workflow

- API deploys via `git push` to commontrace/server → Railway auto-deploy runs `alembic upgrade head && uvicorn`
- Skill deploys via `git push` to commontrace/skill → users pull updates
- MCP deploys via `git push` to commontrace/mcp → Railway auto-deploy
- Frontend deploys via `git push` to commontrace/frontend → Railway auto-deploy

Always syntax-check before committing: `python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"`

## Persistent Memory System

Project knowledge is organized in `memory/` as concept files. This survives across sessions and context compactions.

### Structure

```
memory/
  INDEX.md              ← routing table (keyword → concept file). Read FIRST.
  _manifest.json        ← metadata, split threshold
  infrastructure/       ← deployment, services, database, costs
  api/                  ← endpoints, models, ranking, embeddings
  skill/                ← hooks, detection, local store, triggers
  frontend/             ← design, i18n, build pipeline
  mcp/                  ← proxy, tools, circuit breaker
  sessions/             ← session journal (short-term notes)
```

### Work Mode

1. **After context compaction**: Read `memory/INDEX.md`. Load only the concept files relevant to the current task (use keywords in the routing table).
2. **After completing a task**: Update the relevant concept file with new discoveries. If a concept file exceeds 500 lines, split it into a subdirectory with sub-files and update `INDEX.md`.
3. **Pre-compaction flush**: During long sessions (10+ tool calls on a topic), proactively write key findings to `memory/sessions/` before context grows large. Don't wait for task completion — compaction is lossy and unpredictable. Flush early, flush often.
4. **Session notes**: Put work-in-progress notes in `memory/sessions/`. Consolidate stable patterns into concept files after they're confirmed across multiple interactions.
5. **Never duplicate**: Check existing concept files before writing. Update in place rather than creating parallel entries.
6. **Manifest**: Keep `_manifest.json` in sync when adding new concept files or keywords.
