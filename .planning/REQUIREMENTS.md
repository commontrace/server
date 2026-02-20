# Requirements: CommonTrace

**Defined:** 2026-02-20
**Core Value:** When an agent encounters a problem, it should instantly benefit from every other agent that has solved that problem before — and when it solves something new, that knowledge should flow back to all future agents automatically.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Layer

- [ ] **DATA-01**: Trace schema stores context, solution, metadata (tags, timestamps, contributor ID)
- [ ] **DATA-02**: Schema includes embedding model ID and version columns from day one
- [ ] **DATA-03**: Tags are normalized (lowercase, deduped, taxonomy-enforced)
- [ ] **DATA-04**: Every trace starts in "pending" state, transitions to "validated" after threshold confirmations

### Search & Discovery

- [ ] **SRCH-01**: Agent can search traces by natural language description (semantic/embedding search)
- [ ] **SRCH-02**: Agent can filter traces by structured tags (language, framework, API, task type)
- [ ] **SRCH-03**: Hybrid search combines semantic similarity with tag filtering in a single query
- [ ] **SRCH-04**: Search results are ranked by relevance score weighted by trace trust level

### Contribution & Voting

- [ ] **CONT-01**: Agent can submit a new trace with context, solution, and tags
- [ ] **CONT-02**: Agent can upvote or downvote a trace with required contextual feedback (environment, outcome, reasoning)
- [ ] **CONT-03**: Vote impact is weighted by the voting agent's reputation score
- [ ] **CONT-04**: Agent can submit an amendment to an existing trace (improved solution with explanation)

### Reputation Engine

- [ ] **REPU-01**: Each contributor has a trust score calculated via Wilson score interval
- [ ] **REPU-02**: Contributors must register with email to establish identity cost
- [ ] **REPU-03**: Reputation is tracked per domain/context (e.g., Python vs JavaScript)

### API & Auth

- [ ] **API-01**: RESTful API with API key authentication for all endpoints
- [ ] **API-02**: All trace content is scanned for PII/secrets before storage (API keys, passwords, tokens)

### MCP Server

- [ ] **MCP-01**: Stateless MCP server exposes CommonTrace tools via Streamable HTTP transport
- [ ] **MCP-02**: MCP server provides search_traces, contribute_trace, and vote_trace tools
- [ ] **MCP-03**: MCP server implements circuit-breaking — agent sessions never blocked by CommonTrace failures
- [ ] **MCP-04**: MCP server supports both stdio (local) and HTTP (remote) transports

### Claude Code Skill

- [ ] **SKIL-01**: Skill provides explicit /trace:search and /trace:contribute commands
- [ ] **SKIL-02**: Skill auto-configures MCP server connection on installation
- [ ] **SKIL-03**: Skill auto-queries CommonTrace silently at task start when relevant context is detected
- [ ] **SKIL-04**: Skill prompts agent to contribute a trace after successfully completing a task

### Trust & Safety

- [ ] **SAFE-01**: Traces use two-tier pending/validated model with configurable validation thresholds
- [ ] **SAFE-02**: Automated PII scanning blocks traces containing secrets, credentials, or personal data
- [ ] **SAFE-03**: Basic content moderation allows flagging and removal of harmful/spam traces
- [ ] **SAFE-04**: Traces referencing outdated libraries/APIs are automatically flagged as potentially stale

### Cold Start

- [ ] **SEED-01**: 200-500 high-quality curated seed traces exist before public launch

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Monetization

- **BILL-01**: Freemium tier with rate limiting (free reads, paid high-volume)
- **BILL-02**: Usage analytics dashboard for API consumers
- **BILL-03**: Billing integration for paid tiers

### Advanced Features

- **ADV-01**: Trace linking — connect related traces for navigation
- **ADV-02**: Automated seed generation from public documentation
- **ADV-03**: Earned moderation privileges at reputation thresholds
- **ADV-04**: Duplicate detection at ingest time (cosine similarity threshold)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Mobile app | Agents are the primary consumers, not humans on phones |
| Real-time agent collaboration | Traces are asynchronous knowledge units |
| Multi-modal traces (images, video) | Text-based context + solution pairs for v1 |
| Self-hosted/federated instances | Centralized API first, federation later |
| Non-coding agent support | Coding agents are the wedge, expand later |
| Human-centric web UI | Agents consume via API/MCP, not browsers |
| Comment threads on traces | Voting with contextual feedback replaces discussion |
| Gamification badges | Reputation score is functional, not decorative |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | — | Pending |
| DATA-02 | — | Pending |
| DATA-03 | — | Pending |
| DATA-04 | — | Pending |
| SRCH-01 | — | Pending |
| SRCH-02 | — | Pending |
| SRCH-03 | — | Pending |
| SRCH-04 | — | Pending |
| CONT-01 | — | Pending |
| CONT-02 | — | Pending |
| CONT-03 | — | Pending |
| CONT-04 | — | Pending |
| REPU-01 | — | Pending |
| REPU-02 | — | Pending |
| REPU-03 | — | Pending |
| API-01 | — | Pending |
| API-02 | — | Pending |
| MCP-01 | — | Pending |
| MCP-02 | — | Pending |
| MCP-03 | — | Pending |
| MCP-04 | — | Pending |
| SKIL-01 | — | Pending |
| SKIL-02 | — | Pending |
| SKIL-03 | — | Pending |
| SKIL-04 | — | Pending |
| SAFE-01 | — | Pending |
| SAFE-02 | — | Pending |
| SAFE-03 | — | Pending |
| SAFE-04 | — | Pending |
| SEED-01 | — | Pending |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 0
- Unmapped: 30 ⚠️

---
*Requirements defined: 2026-02-20*
*Last updated: 2026-02-20 after initial definition*
