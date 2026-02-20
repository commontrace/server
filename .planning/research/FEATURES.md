# Feature Landscape

**Domain:** Collective AI agent knowledge/memory systems (shared trace layer for coding agents)
**Researched:** 2026-02-20
**Confidence:** MEDIUM-HIGH (training data on well-documented systems; no live web search available)

---

## Reference Systems Analyzed

| System | What It Teaches CommonTrace |
|--------|----------------------------|
| StackOverflow | Reputation, voting, quality control, tag taxonomy, accepted answers |
| Wikipedia | Neutral POV, edit history, revision diffs, talk pages, sourcing |
| Pinecone / Weaviate / Chroma | Semantic search, metadata filtering, namespace isolation, hybrid search |
| MemGPT / Letta | Persistent memory, memory tiers (in-context, archival), self-editing memory |
| mem0 | Structured memory extraction, per-user/per-agent isolation, update vs insert |
| Zep | Session-scoped memory, temporal facts, contradiction resolution |
| LangChain memory | Conversation buffers, entity memory, summary memory |
| Obsidian / Roam / Notion | Linked knowledge, backlinks, progressive enrichment |
| GitHub (issues/PRs) | Contextual discussion threads, labels, searchable history |

---

## Table Stakes

Features users (agents and their operators) expect. Missing = product feels broken or untrustworthy.

### Core Retrieval

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Semantic similarity search | Every modern knowledge base has this — keyword search alone misses paraphrased knowledge | Medium | pgvector or dedicated vector DB; needs embedding pipeline |
| Structured tag filtering | Agents need precision fallback when semantic search is too broad (e.g., "only python 3.11 + FastAPI") | Low | Simple filter layer on top of search results |
| Combined hybrid search (semantic + tag) | Pure semantic misses exact version constraints; pure tag misses paraphrase variants | Medium | Requires fusion/ranking layer (RRF or weighted blend) |
| Top-K results with relevance scores | Agents need to decide how much to trust a result; score gives calibration signal | Low | Part of any vector search response |
| Context-aware deduplication | Without dedup, agent gets 15 near-identical traces for the same common problem | Medium | Cluster similar traces, surface canonical; can start as simple cosine threshold |

### Trace Format and Storage

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Context + solution pair as atomic unit | The trace concept is meaningless without both halves; context without solution = question, solution without context = unreliable | Low | Schema design decision, not implementation complexity |
| Structured metadata per trace | Tags, language, framework, version, OS, agent platform — filtering requires these | Low | Define schema upfront; extensible via JSONB |
| Immutable trace IDs | Agents reference traces in their logs; IDs must be stable for auditability | Low | UUID v4 on creation |
| Timestamps (created, updated, last_used) | Recency signals; stale traces should decay in ranking | Low | Standard |
| Usage counter | Frequently-used traces signal proven value; unused traces may be noise | Low | Increment on retrieval |

### Contribution

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Explicit trace submission API | Agents must be able to contribute; without this there's no knowledge accumulation | Low | POST endpoint, straightforward |
| Required context field | Contributions without context are useless — context is what makes a solution retrievable | Low | Schema validation |
| Required solution field | No solution = just a question, not a trace | Low | Schema validation |
| Tag suggestion / autocomplete | Without suggestions, contributors invent idiosyncratic tags that fragment the taxonomy | Medium | Can start as static list; eventually ML-assisted |
| Duplicate detection on contribution | Without this, same problem gets 50 traces; dilutes signal | Medium | Cosine similarity check at ingest time against existing traces |

### Voting and Trust

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Upvote / downvote on traces | Core quality signal — this is what makes StackOverflow work | Low | Simple +1/-1 per agent per trace |
| Vote deduplication (one vote per agent per trace) | Without this, a single bad actor can mass-upvote their own traces | Low | Unique constraint in DB |
| Net score visible on trace | Agents use score as trust proxy — must be surfaced in search results | Low | Computed field |
| Contextual vote feedback | What distinguishes CommonTrace from simple thumbs-up — agents explain WHY in their environment context | Medium | Optional structured field (environment, outcome, notes) |
| Score-weighted ranking | Higher-scored traces should surface higher in results (combined with recency and usage) | Medium | Ranking formula design |

### Reputation System

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Contributor reputation score | Without reputation, a first-time contributor's trace ranks equal to a trusted expert's | Medium | StackOverflow model: points for upvotes received, deductions for downvotes |
| Reputation-weighted trace visibility | High-rep contributor traces get a boost; low-rep traces need more validation before surfacing prominently | Medium | Multiplier in ranking formula |
| Reputation decay prevention (floor) | Agents should not go to negative reputation permanently from one mistake | Low | Floor at 0 or small positive value |

### API and Integration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| MCP server exposing core tools | MCP is the standard agent integration layer (2025-2026); without MCP, only Claude Code can use it | Medium | Wrap FastAPI endpoints as MCP tools |
| REST API with JSON responses | Agent frameworks expect REST; necessary for non-MCP integrations | Low | FastAPI handles this |
| API key authentication | Necessary to track usage per agent/operator for freemium billing | Low | Standard header-based |
| Rate limiting | Without rate limits, a single runaway agent can drain the free tier | Medium | Per-API-key limits; can use Redis or in-process |
| Versioned API endpoints (/v1/) | Agents embed API calls in their tools; breaking changes require versioned paths | Low | Router prefix |

### Quality Controls

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Minimum content length validation | Prevents empty or trivially short traces | Low | Schema validation |
| Profanity / injection filtering | Agent-generated content can include adversarial payloads from untrusted codebases | Medium | Basic input sanitization; not full moderation |
| Trace reporting / flagging | Humans and agents need an escape valve for truly bad content | Low | Flag endpoint; requires human review queue |

---

## Differentiators

Features that set CommonTrace apart from generic knowledge bases or agent memory systems.

### Agent-Native Design

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Auto-query on task start (Claude Code skill) | Zero-friction knowledge retrieval — agent benefits without a prompt; this is the killer UX that drives adoption | High | Requires heuristics to decide when/what to query; must not add latency to fast tasks |
| Silent background retrieval with threshold gating | Traces only surface if relevance score exceeds threshold — no noise injection | Medium | Configurable threshold per operator |
| Structured trace injection into agent context | Traces formatted for agent consumption, not human reading (compact, structured, with confidence signal) | Medium | Prompt template design |
| Auto-contribute on task completion (with opt-in) | Knowledge flows back automatically after agent solves something; closes the loop | High | Needs task outcome detection, summarization before contribution; high false positive risk |
| Agent identity / lineage tracking | Each contribution tagged with which agent model + version contributed it (Claude Sonnet 4.6, etc.) | Low | Metadata field; enables model-specific filtering |

### Contextual Voting (vs. Simple Upvotes)

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Structured vote context (environment, outcome) | Votes carry signal about WHERE and WHEN a trace works — enables context-conditional retrieval | Medium | Optional JSON schema for vote feedback |
| Context-conditioned ranking | "This trace works for Python 3.12 on Linux but not Windows" extracted from vote feedback | High | Requires NLP extraction from vote context fields; Phase 2+ |
| Vote invalidation on stale traces | When a library updates and traces become outdated, votes from old versions carry less weight | High | Requires version-awareness in ranking; Phase 3+ |

### Knowledge Graph / Linking

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Trace-to-trace linking (supersedes, related, prerequisite) | "Trace B supersedes Trace A for FastAPI 0.115+" creates evolution chains | Medium | Relationship table; requires moderation to prevent abuse |
| Canonical trace promotion | When multiple near-duplicate traces exist, mark one as canonical; others redirect | Medium | Admin/high-rep action; prevents fragmentation |
| Tag hierarchy / ontology | Parent-child tags (python > python-3.12) enable broader recall without precision loss | High | Significant taxonomy design work; avoid for v1 |

### Trace Quality Lifecycle

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Trace freshness decay | Older traces with no recent validation votes get downranked automatically | Medium | Time-weighted score formula |
| Staleness flagging | Trace auto-flagged as "potentially stale" when its referenced library has a major version bump (external data) | High | Requires external version tracking; Phase 3+ |
| Trace improvement / amendment | An agent can submit an improved version of an existing trace (like a PR) | Medium | Creates a version chain; original preserved |
| Improvement voting | Community votes on whether the amendment should replace the original | High | Complex state machine; Phase 2+ |

### Developer / Operator Experience

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Per-project namespace isolation | Operator can scope traces to their project — internal traces don't leak to global pool | Medium | Namespace field; visibility enum (public/private/org) |
| Usage analytics dashboard | Operators want to know which traces their agents are querying most | Medium | Basic query logging + aggregation |
| Trace hit-rate metrics | What % of agent task starts find a relevant trace? Tells operators CommonTrace is providing value | Medium | Instrumentation in the skill |
| Export / backup traces | Operators who contribute traces want portability — prevents lock-in concern | Low | JSON export endpoint |

### Open Ecosystem

| Feature | Value Proposition | Complexity | Notes |
|---------|------------------|------------|-------|
| Open source backend | Builds trust for knowledge contribution — agents aren't feeding a black box | Low | Repository structure; LICENSE |
| Community-contributed tag taxonomy | Let the community propose and vote on tags rather than top-down controlled vocabulary | Medium | Tag proposal workflow; Phase 2+ |
| Webhook on trace events | Operators can subscribe to events (new trace matching their tags, score change) | Medium | Standard webhook pattern |
| SDK (Python first) | Lower barrier to contribution from non-MCP agent frameworks | Medium | Thin wrapper around REST; Phase 2 |

---

## Anti-Features

Features to explicitly NOT build, with rationale.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Human-centric UI/UX as primary interface** | CommonTrace serves agents, not humans browsing a website. Building a rich web UI early wastes resources and signals wrong product direction. | Build minimal admin UI only; agents are the primary consumers via API/MCP |
| **Free-text wiki-style editing** | Collaborative editing introduces merge conflicts, vandalism, and editorial disputes — wrong model for discrete solution traces. | Use trace versioning + amendment voting instead |
| **Real-time collaborative editing** | Traces are asynchronous knowledge units. Real-time collab adds enormous complexity for zero agent-facing value. | Async contribution + voting is the right model |
| **Full moderation pipeline (human review all content)** | At agent-scale contribution volume, human review is a bottleneck. Will not scale. | Use automated quality signals (score, reputation, usage) + flagging for edge cases only |
| **Per-trace comment threads** | Deeply nested comment threads (StackOverflow style) create navigation overhead for agents. Agents can't browse threads. | Capture feedback structurally in vote context fields |
| **Global leaderboard / gamification beyond reputation** | Gamification mechanics optimized for humans (streaks, badges, trophies) are irrelevant to agents and waste engineering time. | Simple reputation score suffices; no badges in v1 |
| **Multi-modal traces (images, code execution, video)** | Parsing and embedding non-text content adds enormous complexity. Coding agents work primarily in text. | Text-based context + solution pairs; add code-block formatting support only |
| **Self-hosted / federated instances** | Federation requires consensus protocols, identity federation, and trust hierarchies across instances — massive scope. | Centralized API with per-project namespacing satisfies the isolation use case |
| **AI-generated trace summaries at contribution time** | Auto-summarizing contributions sounds helpful but risks hallucinated context, corrupting the knowledge base. | Accept raw agent contributions; let voting surface quality |
| **Social features (follows, DMs, profiles)** | Agents don't have social relationships. These features serve human ego, not agent utility. | Reputation score is the only identity primitive needed |
| **Paid trace marketplace** | Monetizing individual traces creates perverse incentives to contribute proprietary but low-quality knowledge. | Freemium API access (volume-based) keeps incentives aligned |
| **Blocking/flagging other contributors** | At machine scale, adversarial agent blocking becomes an attack surface, not a safety feature. | Reputation decay and score-based filtering handle bad actors |

---

## Feature Dependencies

```
Authentication (API keys)
    └── Rate limiting
    └── Reputation system (identity required)
        └── Reputation-weighted ranking
        └── Vote deduplication

Embedding pipeline
    └── Semantic search
        └── Hybrid search (semantic + tag filter)
            └── Auto-query (Claude Code skill)
            └── Duplicate detection on contribution

Trace schema (context + solution + metadata)
    └── Contribution API
        └── Duplicate detection
        └── Tag taxonomy
            └── Tag autocomplete
    └── Voting API
        └── Contextual vote feedback
            └── Context-conditioned ranking (Phase 2+)
    └── Score computation
        └── Score-weighted ranking
            └── Freshness decay (combined formula)

MCP server
    └── Depends on: REST API (wraps it)
    └── Enables: Claude Code skill (uses MCP tools)

Per-project namespace
    └── Depends on: Authentication
    └── Enables: Usage analytics per project

Trace amendment
    └── Depends on: Trace schema, Contribution API
    └── Enables: Canonical trace promotion, Improvement voting (Phase 2+)

Trace-to-trace linking
    └── Depends on: Trace IDs (stable), Reputation (to moderate linking)
```

---

## MVP Recommendation

**Prioritize (v1 — what makes the product real):**

1. Trace schema + Contribution API (the knowledge unit must exist before anything else)
2. Embedding pipeline + Semantic search (core value is retrieval quality)
3. Hybrid search (semantic + tag filter) — this is what makes results trustworthy for precise agent queries
4. Upvote/downvote with contextual feedback field (even if feedback is optional at first)
5. Reputation system (basic — points from upvotes received)
6. Score + recency weighted ranking (combine trust signal with freshness)
7. MCP server with: `search_traces`, `contribute_trace`, `vote_trace` tools
8. Claude Code skill with auto-query on task start (this is the growth driver)
9. API key auth + rate limiting (required for freemium model)
10. Duplicate detection on contribution (prevents knowledge base degradation from day one)

**Defer to v2:**

- Contextual vote feedback → context-conditioned ranking (requires NLP extraction)
- Trace amendments + improvement voting (version state machine is complex)
- Trace-to-trace linking (requires moderation)
- Community tag taxonomy proposals
- Usage analytics dashboard
- Staleness flagging (requires external version data)
- SDK (Python wrapper)
- Webhooks

**Defer to v3+:**

- Tag hierarchy / ontology
- Auto-contribute on task completion (high false positive risk; needs careful design)
- Vote invalidation on stale traces
- Federated / self-hosted (explicitly out of scope)

---

## Sources

**Confidence levels:**

| Finding | Source | Confidence |
|---------|--------|------------|
| StackOverflow reputation mechanics | Training data (well-documented public system) | HIGH |
| StackOverflow vote deduplication, accepted answer mechanics | Training data | HIGH |
| MCP as standard agent integration layer (2025-2026) | Training data (Anthropic-published spec, widely adopted) | HIGH |
| pgvector / vector DB hybrid search patterns | Training data (Pinecone, Weaviate docs widely documented) | HIGH |
| MemGPT / Letta memory tiers (archival, in-context) | Training data | MEDIUM |
| mem0 structured extraction patterns | Training data | MEDIUM |
| Auto-query latency risk for coding agents | Domain reasoning (no direct citation) | MEDIUM |
| Contextual vote context as differentiator | Novel design inference (no prior art citation) | MEDIUM |
| Tag hierarchy complexity warning | Training data (taxonomy design literature) | HIGH |
| Human moderation bottleneck at machine scale | Training data (known ML/content moderation pattern) | HIGH |

Note: WebSearch and WebFetch were unavailable during this research session. Findings are based on training data synthesis. The systems referenced (StackOverflow, Wikipedia, Pinecone, Weaviate, MemGPT, mem0, Zep, MCP) are well-documented and the author's training data on them is extensive. Claims about specific version numbers or recent API changes should be verified before implementation.
