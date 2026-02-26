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

### Knowledge Detection Patterns (16 total)
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

### Search Ranking Formula
```
score = similarity * trust * depth * decay * ctx_boost * convergence * temp_mult * validity * somatic_mult
```

### Persistent Local Store
SQLite at `~/.commontrace/local.db` — survives across sessions:
- `projects` — working directory → language/framework mapping
- `sessions` — per-session stats (errors, resolutions, contributions)
- `entities` — accumulated language/framework/domain knowledge per project
- `events` — migrated JSONL events for cross-session analysis
- `error_signatures` — fuzzy error signatures for recurrence detection
- `trigger_feedback` — which triggers led to trace consumption (reinforcement)

## Development Workflow

- API deploys via `git push` to commontrace/server → Railway auto-deploy runs `alembic upgrade head && uvicorn`
- Skill deploys via `git push` to commontrace/skill → users pull updates
- MCP deploys via `git push` to commontrace/mcp → Railway auto-deploy
- Frontend deploys via `git push` to commontrace/frontend → Railway auto-deploy

Always syntax-check before committing: `python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"`
