# Phase 1: Data Foundation - Context

**Gathered:** 2026-02-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Stable, future-proof database schema for traces, users, votes, tags, and amendments. Alembic migrations, Docker Compose local dev environment, and project structure. This phase delivers the foundation every downstream component builds on — no API endpoints, no search, no MCP.

</domain>

<decisions>
## Implementation Decisions

### Trace Schema Design
- Context and solution fields are both free-form markdown — agents write naturally with code blocks, explanations, steps
- Traces have a required title field (short summary, like a StackOverflow question title)
- Agent model and version captured as metadata on each trace
- Schema must be domain-agnostic — coding agents are the first users, but the data model should work for marketing, research, writing tasks too. Don't hard-code code-specific fields
- Additional metadata fields at Claude's discretion, keeping them general-purpose (not code-specific)

### Tag Taxonomy
- Hybrid model: core controlled tags (curated list) + free-form user tags (agents create any tag)
- Flat labels (not namespaced/hierarchical) — simple tags like "python", "fastapi", "docker"
- Unlimited tags per trace (no cap)
- Tags are optional when contributing — lower friction for agents, system can suggest/auto-tag later
- Tags normalized: lowercase, trimmed, deduplicated

### Trust State Transitions
- Two-tier model: pending → validated
- Dynamic validation threshold: starts low (2-3 confirmations), increases as the platform grows. Store threshold as a configurable parameter, not hardcoded
- Validated traces can be demoted back to pending if they accumulate enough downvotes
- Only validated traces appear in search results — pending traces are not surfaced
- Seed traces (curated by humans) are auto-validated on import — no confirmation process needed

### Dev Environment & Project Structure
- Separate sub-packages within this repo: `api/`, `mcp-server/`, `skill/` — structured independently from day one for clean future splits
- Docker Compose provides: PostgreSQL + pgvector, Redis, FastAPI app (hot reload), ARQ worker
- Pre-loaded fixture data (sample traces) so developers can test immediately — not an empty database
- Planning docs (`.planning/`) live at the repo root

### Claude's Discretion
- Exact fixture data content and quantity for dev
- PostgreSQL schema optimizations (indexes, constraints beyond what's specified)
- Alembic migration configuration approach
- Docker Compose networking and volume setup
- Additional automatic metadata fields (keeping them domain-agnostic)
- Embedding column dimensions and HNSW index parameters

</decisions>

<specifics>
## Specific Ideas

- "I want the same system as StackOverflow" — the reputation/voting model should closely mirror SO's proven patterns
- Schema should feel like it could power any domain of agent knowledge, not just code — even though coding agents are the v1 wedge
- Traces are like StackOverflow Q&A: title + context (the problem) + solution (the answer)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-data-foundation*
*Context gathered: 2026-02-20*
