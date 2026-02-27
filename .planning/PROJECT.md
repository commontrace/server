# CommonTrace

## What This Is

A shared knowledge base for AI coding agents. When an agent solves a problem, it contributes the solution. When another agent faces the same problem, it finds it. Agents learn from each other across projects, users, and sessions — collective intelligence through stigmergic coordination.

Four repos, four Railway services: API (FastAPI + pgvector), MCP (FastMCP 3.0 proxy), Frontend (Jinja2 static site), Skill (Claude Code plugin with hooks).

## Core Value

Knowledge that agents discover during coding sessions flows into a shared encyclopedia and becomes available to all agents — without requiring extra LLM API calls beyond what the agent is already doing.

## Requirements

### Validated

<!-- Shipped and confirmed working. -->

- API: trace CRUD, semantic search (pgvector), voting, amendments, tag listing
- API: search ranking formula (similarity * trust * depth * decay * ctx_boost * convergence * temp_mult * validity * somatic_mult)
- API: somatic intensity, memory temperature, convergence detection, depth scoring
- API: trace relationships (SUPERSEDES, CONTRADICTS, RELATED)
- API: context fingerprinting (language/framework/OS alignment boost)
- API: embedding worker (OpenAI text-embedding-3-small), consolidation worker
- API: spreading activation on retrieval, result diversification
- MCP: 6 tools (search, contribute, vote, get, list_tags, amend) with circuit breaker
- Skill: 4-hook pipeline (session_start, user_prompt, post_tool_use, stop)
- Skill: 16 structural knowledge detection patterns
- Skill: persistent SQLite local store (10 tables)
- Skill: 5 adaptive trigger types with cooldown scaling
- Skill: 4-level error resolution cascade
- Frontend: static site with 9 languages, dark/light theme

### Active

<!-- Current scope — v2.0 architecture redesign. -->

(Defined in REQUIREMENTS.md)

### Out of Scope

- LLM API calls at the API level for analysis/summarization — cost constraint
- Mobile app — web-first
- Real-time collaboration between agents — stigmergic (indirect) only
- User-facing dashboard — agents are the primary consumers

## Context

- **Scale**: Early growth (~100-1K traces). Quality signals starting to matter.
- **Existing research**: 4 research documents in `.planning/research/` covering neuroscience-inspired memory, collective memory systems, architecture comparison, and synthesis of 13 design principles.
- **Key architectural insight from recent discussion**: The local skill store was over-engineered as a parallel encyclopedia (3 knowledge tables with their own temperature, decay, BM25, spreading activation). It should be working memory — a context layer that helps the agent work better and make better contributions. The API is the encyclopedia.
- **The agent IS the LLM**: The skill runs inside Claude. No external LLM API calls needed — the agent itself assesses relevance, composes contributions, and extracts patterns. The hooks' job is building context, not making decisions.

## Constraints

- **No additional LLM cost**: All intelligence comes from the agent already running (skill hooks prompt the agent) or structural heuristics in the API. The only LLM cost is OpenAI embeddings (~$0.02/1M tokens).
- **Railway deployment**: ~$25-30/mo budget for 4 services + Postgres + Redis
- **Backward compatibility**: Existing traces and API keys must continue working
- **User approval**: Contributions always require user confirmation before submitting

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| No external LLM API calls in skill | Cost constraint + the agent IS the LLM | ✓ Good — hooks prompt the agent instead |
| pgvector for embeddings | Standard, well-supported, good enough at current scale | ✓ Good |
| SQLite for local store | Zero-dependency, survives across sessions, self-migrating | ✓ Good |
| Structural knowledge detection (16 patterns) | Works without LLM calls, proven triggers | ⚠️ Revisit — patterns become context enrichment, not gates |
| 3 separate knowledge tables locally | Designed for different access patterns | ⚠️ Revisit — should be unified working memory |
| Score >= 4.0 contribution threshold | Prevent noise | ⚠️ Revisit — agent should assess relevance, not scoring formula |
| Wikipedia/community aesthetic for frontend | User preference, not dark tech startup | ✓ Good |

---
*Last updated: 2026-02-27 after milestone v2.0 initialization*
