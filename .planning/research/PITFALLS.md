# Domain Pitfalls: CommonTrace — Collective AI Agent Knowledge Systems

**Domain:** Shared memory / collective knowledge layer for AI coding agents
**Researched:** 2026-02-20
**Confidence note:** WebSearch and file-read tools unavailable in this session. All findings are drawn from training knowledge covering production RAG systems, reputation system engineering, vector database deployments, MCP protocol design, and collective knowledge platform post-mortems (Stack Overflow, Wikipedia, npm, HuggingFace Hub). Confidence marked per claim.

---

## Critical Pitfalls

Mistakes that cause rewrites, loss of community trust, or fundamental product failure.

---

### Pitfall 1: Knowledge Poisoning at Scale (No Defense-in-Depth)

**What goes wrong:** Agents (or humans proxying as agents) contribute deliberately misleading, hallucinated, or adversarially crafted traces. Because downstream agents trust traces silently (auto-query mode), poisoned traces propagate invisibly — every agent that executes a bad trace amplifies the damage. Unlike Stack Overflow where a human reads before acting, agents may execute solutions directly.

**Why it happens:** The system is optimized for contribution velocity (more traces = more value), creating tension with contribution quality gates. Early systems trust contributors equally before reputation data exists. Auto-query UX (silent suggestion) bypasses the human review loop that would catch bad advice.

**Consequences:**
- Agents introduce security vulnerabilities (e.g., a trace that "solves" a dependency problem by pinning to a known-vulnerable version)
- Agents delete data, make destructive API calls, or leak secrets based on poisoned traces
- Once a bad trace accumulates upvotes (because early adopters tried it in safe contexts), it becomes hard to demote
- Trust in the entire platform collapses after a single high-profile incident

**Prevention:**
- Implement a two-tier trust model from day one: `pending` traces visible only to the contributor until they receive N independent votes from agents with reputation > threshold; only `validated` traces are served in auto-query mode
- Rate-limit new contributor submissions aggressively (e.g., 5 traces/day until reputation earned)
- Sandbox-validate traces where possible: if a trace includes code, run it in an isolated environment and flag traces that cause exceptions or match known-dangerous patterns
- Maintain a "quarantine" state for traces flagged by high-reputation agents — pull from search results pending manual review
- Log every trace execution with agent identity so poisoned traces can be traced back and rolled back

**Detection (warning signs):**
- Spike in downvotes from multiple independent agents within 24 hours of a trace submission
- A trace that gains rapid upvotes (>10 in first hour) — suspicious velocity pattern
- Agents reporting failures that correlate with a specific trace ID in logs
- New contributor submitting traces that cite non-existent library versions or APIs

**Phase mapping:** Must be designed in Phase 1 (data model) and enforced in Phase 2 (API). Cannot be retrofitted after launch.

---

### Pitfall 2: Cold Start Death Spiral

**What goes wrong:** The system has no value without traces. No traces means no value for early adopters. No value means no contributions. The platform never escapes zero. This is the most common reason collective knowledge platforms fail before anyone sees them.

**Why it happens:** Builders assume "if we build it, they will come." Agent integration is built before the knowledge base has enough content to demonstrate value. The first 50 agents that try it get empty search results, form a negative impression, and never return.

**Consequences:**
- Network effects never activate
- First-impression failure is permanent for early adopters who become the community evangelists
- Platform stays in "perpetual beta" because there's always a reason to wait for more content before promoting

**Prevention:**
- Seed the knowledge base before any public launch: manually curate 200-500 high-quality traces covering the most common Claude Code tasks (React setup, PostgreSQL migrations, Docker configuration, common API integrations). These should be first-class content, not placeholder data.
- Build a "synthetic cold start" pipeline: parse top Stack Overflow answers + GitHub issue resolutions for common coding problems and transform them into trace format (with explicit attribution and lower initial trust scores)
- Design the UX so empty search results are never shown — instead, show "No traces yet for this query. Be the first to contribute." with a one-click contribution flow
- Recruit 10-20 power users (heavy Claude Code users) pre-launch to contribute traces in exchange for founding-member reputation bonuses
- Implement a "contribution on solve" trigger: when an agent successfully completes a task, prompt for trace contribution while the context is fresh

**Detection (warning signs):**
- Search result empty-rate > 60% in first two weeks
- Contribution rate < 1 trace per 10 queries
- No repeat queries from same agent identity

**Phase mapping:** Phase 1 (data model + seeding pipeline). Seed data must be ready before Phase 2 launch. Never launch the MCP server with an empty database.

---

### Pitfall 3: Embedding Model Lock-in and Silent Drift

**What goes wrong:** The team picks an embedding model at launch (e.g., `text-embedding-3-small`), stores all vectors, then faces pressure to upgrade to a better model 6 months later. Re-embedding the entire corpus is expensive and requires a database migration with downtime. Alternatively, the embedding model provider changes the model silently (same endpoint, different outputs), causing similarity scores to become meaningless for older vectors.

**Why it happens:** Embedding model selection is treated as an infrastructure detail rather than a data schema decision. No versioning is applied to stored vectors. OpenAI has historically changed model behavior behind the same model name.

**Consequences:**
- Query vectors (from new model) and stored vectors (from old model) are in different semantic spaces — search quality silently degrades
- Cosine similarity scores become uncalibrated — the threshold for "relevant" changes
- Full re-embedding requires O(N) API calls — expensive and time-consuming at scale
- Downtime during migration unless careful dual-indexing is implemented

**Prevention:**
- Store `embedding_model_id` and `embedding_model_version` as columns on every trace row from day one
- Pin to a specific, versioned model identifier (e.g., `text-embedding-3-small-2024-02-01` not just `text-embedding-3-small`)
- Design the vector store schema to support multiple embedding columns or a model-versioned partition
- Build a background re-embedding job from day one — even if never used, having the infrastructure ready means migration is hours not weeks
- Track a random sample of 100 vectors; weekly re-embed them and compare similarity distributions to detect silent drift

**Detection (warning signs):**
- Search quality complaints from users increase without any code changes
- P50 similarity score for "known good" query pairs drops over time
- OpenAI/embedding provider announces a model update

**Phase mapping:** Phase 1 (schema design must include model versioning). Phase 3 (observability pipeline should include embedding drift monitoring).

---

### Pitfall 4: Reputation Gaming by Coordinated Agents

**What goes wrong:** Once reputation unlocks visibility and trust, it becomes a target. A single bad actor can spin up N agent identities, have them upvote each other's traces, and rapidly inflate reputation scores. This is the Sybil attack applied to collective knowledge. It's worse than on Stack Overflow because agents can create identities programmatically at scale.

**Why it happens:** Reputation systems designed for humans assume the cost of creating a new identity is high (email, phone verification). For agents, identity is just an API key. If reputation is purely vote-based and identities are cheap, gaming is trivial.

**Consequences:**
- Low-quality or poisoned traces from high-reputation accounts surface prominently
- Legitimate contributors' traces are buried
- Community trust collapses when gaming is discovered
- Defending against Sybil attacks after the fact requires retroactive trust graph analysis, which is computationally expensive

**Prevention:**
- Base reputation on *outcomes* not just votes: agent identity earns reputation when other agents mark a trace as "used successfully" in a verified context — not just when they upvote
- Implement identity cost: require API key registration with email + rate limiting; associate each API key with a single agent identity; detect multiple identities from same IP/session
- Apply graph analysis: votes from agents that share a network graph (same API key prefix, same IP range, same access pattern) receive reduced weight
- Cap reputation gain per time window: a new identity can't earn more than X reputation per week, regardless of votes received
- Add "vote weight" that scales with the voter's reputation — new accounts' votes count for 0.1x until they have established history

**Detection (warning signs):**
- A new identity reaches top-decile reputation within 48 hours of creation
- Cluster of votes arriving within seconds of each other from different identities
- Vote patterns that correlate with identity creation timestamps
- Single agent upvoting 50+ traces in one session

**Phase mapping:** Phase 2 (reputation engine). Sybil resistance must be in the initial design, not added after gaming is observed.

---

### Pitfall 5: Trace Staleness — Outdated Solutions Presented as Current

**What goes wrong:** A trace contributed in 2026 for "how to configure Vite 4 HMR with React" becomes dangerously wrong in 2027 when Vite 5 changes the configuration API. The trace still has high trust scores (upvoted by many agents who used it successfully in 2026), so it surfaces prominently. Agents follow its advice, it fails, and the agent wastes 30 minutes debugging why the "highly trusted" solution doesn't work.

**Why it happens:** Reputation/trust scores are treated as permanent properties of a trace. There's no time-decay model. Library and framework ecosystems evolve faster than human community members notice to downvote old content.

**Consequences:**
- Trust in the platform erodes — agents learn they can't rely on it for library-specific guidance
- High-reputation traces are the most dangerous because they're prioritized in search
- Removing old traces loses institutional knowledge that may still be valid for older projects

**Prevention:**
- Implement a time-decay factor in the ranking formula: `effective_score = trust_score * decay(age, update_frequency)`. Decay should be aggressive for traces tagged with specific library versions.
- Require version tags on every trace (e.g., `react@18`, `vite@4`) — make version tagging a required field, not optional metadata
- Auto-flag traces for review when their tagged library/framework releases a new major version (webhook from npm/PyPI release feeds)
- Implement a "validity vote": separate from up/down voting, agents can mark a trace as "still valid in my context [library_version]" — this is the primary freshness signal
- Display trace age and last-validated date prominently in search results

**Detection (warning signs):**
- Downvotes citing "outdated" in contextual feedback
- High-reputation traces with zero validity votes in the past 90 days
- Search queries for library names that have new major versions since the top-ranked traces were created

**Phase mapping:** Phase 2 (trace schema must include version tags and validity signals). Phase 3 (observability for staleness rates). Phase 4+ (npm/PyPI integration for automatic staleness flagging).

---

## Moderate Pitfalls

---

### Pitfall 6: Embedding Search Relevance Failure — The "Semantically Close, Contextually Wrong" Problem

**What goes wrong:** Vector search returns traces that are semantically similar to the query but contextually irrelevant. Example: An agent asks "how to handle database connection timeouts in FastAPI" and gets back traces about "handling HTTP request timeouts in FastAPI" — similar enough to score highly in cosine similarity, useless for the actual problem. Agents either get wrong guidance or learn to ignore the system.

**Why it happens:** Pure semantic search (vector only) doesn't distinguish between "I'm asking about X" and "I'm asking about something that sounds like X." The training data for embedding models treats many adjacent technical concepts as synonymous.

**Prevention:**
- Implement hybrid search from launch: combine vector similarity (semantic) with BM25 keyword matching (exact). Weight exact keyword matches more heavily for technical queries — API names, library names, error messages, function signatures should be treated as high-signal exact-match terms.
- Require structured tags on traces (technology stack, error type, library, framework version) and use tag-based pre-filtering before semantic search — this shrinks the search space and eliminates cross-domain false positives
- Implement a minimum relevance threshold: don't return a trace if its score is below threshold, even if it's the "best" match. Empty results with "no relevant traces" is better than wrong results presented as relevant.
- Track click-through and "used successfully" rates by query — this is ground truth for relevance quality

**Warning signs:** Agents report finding "irrelevant" traces; low click-through rate on top-ranked results; high search volume but low contribution rate (agents give up before contributing).

**Phase mapping:** Phase 2 (search architecture). Hybrid search must be the initial implementation — don't plan to "add it later."

---

### Pitfall 7: MCP Server Reliability Becoming the Critical Path

**What goes wrong:** The MCP server becomes a synchronous dependency in agent workflows. When it goes down or is slow (>500ms), every agent using it is blocked. Because agents operate in tight loops (seconds between actions), even P95 latency of 2 seconds is catastrophic. A 30-minute outage takes down every Claude Code session using CommonTrace.

**Why it happens:** MCP integration is built as a synchronous call-and-wait pattern. The API backend experiences spikes when many agents start sessions simultaneously (e.g., Monday morning, after a viral post). The MCP server is not designed for graceful degradation.

**Prevention:**
- Implement aggressive circuit-breaking in the MCP server: if the backend is unreachable or responds in >1 second, return a graceful "traces unavailable, proceeding without" response rather than blocking or throwing
- Design the Claude Code skill to treat CommonTrace as optional enrichment, never as a required step — agents must function fully without it
- Cache the last N search results per agent session in the MCP server (in-memory) — a cache hit means zero backend latency
- Set an explicit SLA budget: auto-query must complete in <200ms or be skipped. Explicit contribution calls can wait up to 2 seconds.
- Separate read and write paths: search traces can be served from read replicas; contributions go to the primary. Read availability is more critical than write availability.

**Warning signs:** P95 search latency approaching 500ms; backend error rate > 0.1%; agents disabling CommonTrace integration in feedback.

**Phase mapping:** Phase 2 (MCP server must have circuit-breaking from day one). Phase 3 (latency SLOs as observability targets).

---

### Pitfall 8: Privacy Leakage Through Trace Context

**What goes wrong:** Agents contribute traces that include sensitive information embedded in context: internal API endpoints, private repository names, secret environment variable names (even if not values), internal company naming conventions, or architectural details that reveal the contributor's codebase. Since traces are shared publicly, this is a data leak.

**Why it happens:** The "context" field of a trace is free-form text designed to be as descriptive as possible. Agents generate this context from their active session — which may include confidential project details. Contributors don't manually sanitize before submission.

**Prevention:**
- Run a PII/secrets scanner on all incoming traces before storage: detect patterns like API keys, tokens, internal hostnames (non-public TLDs), email addresses, and IP addresses in private ranges
- Strip or redact detected sensitive patterns automatically, with a flag for contributor review
- Provide a preview + confirmation step before trace submission: show the agent what will be stored publicly
- Define in the contribution schema which fields are private (stored but not published) vs public — allow contributors to mark sections of context as private
- Implement rate-limited human review for traces from low-reputation contributors

**Warning signs:** User reports of company-internal information appearing in public search results; traces containing IP addresses in RFC1918 ranges; traces with `localhost` or internal hostnames.

**Phase mapping:** Phase 2 (contribution pipeline must include PII scanning). Cannot be deferred.

---

### Pitfall 9: The "Votes Without Context" Voting System Failure

**What goes wrong:** Agents upvote or downvote traces but the votes carry no diagnostic information. A trace with 50 upvotes and 20 downvotes is ambiguous — did it work for some contexts and not others? Was it outdated? Was the downvote from an agent that misunderstood the trace? Without contextual feedback, the voting system can't improve search quality, can't distinguish "wrong" from "wrong in this context," and can't surface when a previously-good trace becomes outdated.

**Why it happens:** Simple up/down voting is the easiest thing to build. Requiring contextual feedback adds friction. Teams prioritize contribution velocity over signal quality.

**Prevention:**
- Require a minimum contextual tag on all downvotes: one of `outdated`, `wrong`, `worked_differently`, `not_applicable`, `security_concern` — a single click, not free text
- Treat contextual feedback as a first-class signal: `outdated` votes from multiple agents trigger auto-flagging regardless of overall vote ratio
- Allow "worked in my context" votes that include the agent's technology context (detected from their session, not manually entered) — this creates a multi-dimensional quality signal
- Display vote breakdown by context type in trace metadata

**Warning signs:** High downvote rate without corresponding contextual tags; same trace getting both high upvotes and high downvotes (bimodal distribution) without context differentiation.

**Phase mapping:** Phase 2 (voting API must include contextual tags from day one).

---

### Pitfall 10: Vector Database Scaling Assumptions Failing Under Load

**What goes wrong:** The system is designed for 100K traces with pgvector. At 10M traces, ANN search latency becomes unacceptable. The team realizes they need to migrate to a dedicated vector database (Qdrant, Weaviate, Pinecone) but can't do it without a major rewrite because the vector store is tightly coupled to the application logic.

**Why it happens:** pgvector is a natural first choice (one less service, Postgres familiarity), but it doesn't scale to high-dimensional vectors at tens of millions of records. Sharding and approximate nearest neighbor (ANN) index tuning at scale requires dedicated infrastructure. Teams start with pgvector and plan to "scale later" without designing for migration.

**Prevention:**
- Abstract the vector store behind a repository interface from day one — application code never calls pgvector directly, it calls `VectorStore.search(embedding, k, filters)`. This makes swapping the backend a configuration change, not a rewrite.
- Set explicit capacity limits in the design: "pgvector handles up to X traces at Y dimensions with Z latency SLO." Document when migration is triggered.
- Include an index type selection decision (IVFFlat vs HNSW) in initial design — HNSW is better for production (faster queries, no training needed) despite higher memory usage
- At 1M traces, evaluate pgvector with HNSW vs dedicated vector DB. At 10M traces, migrate.

**Warning signs:** ANN query time exceeding 100ms at p50; vacuum/index rebuild causing query latency spikes; memory pressure on Postgres host from vector index.

**Phase mapping:** Phase 1 (abstract repository interface in schema design). Phase 3 (capacity planning and scaling decision points).

---

### Pitfall 11: Freemium Rate Limiting Killing Agent Workflows Mid-Session

**What goes wrong:** An agent hits the free tier rate limit in the middle of a complex task. The MCP server starts returning 429 errors. The agent either crashes, loops retrying, or loses the ability to contribute a valuable trace it just generated. The user's experience is interrupted by a billing concern at the worst possible moment.

**Why it happens:** Rate limits are implemented as simple counters (N requests per hour). Agent workloads are bursty — a complex coding session might make 50 queries in 5 minutes then none for an hour. A per-hour limit treats this as a violation when it's actually normal behavior.

**Prevention:**
- Use token bucket / leaky bucket algorithms rather than fixed window counters — this allows burst tolerance while enforcing average rate limits
- Separate read (search) and write (contribute) rate limits — reads are much cheaper and should have higher limits or be free indefinitely
- Implement a "session grace period": once an agent starts a session, allow it to complete without interruption even if it slightly exceeds limits
- Surface rate limit warnings well before the limit is hit (at 80%) so the agent/user can decide to upgrade or throttle
- Never hard-fail a contribution (write) due to rate limiting — queue it and process it when the window resets, return success to the agent

**Warning signs:** High rate of 429 responses in logs; agents contributing traces clustered at the start of the hour (gaming fixed windows); user complaints about mid-session interruptions.

**Phase mapping:** Phase 3 (billing and rate limiting infrastructure). Rate limit design must be reviewed before any public launch.

---

## Minor Pitfalls

---

### Pitfall 12: Tag Taxonomy Explosion

**What goes wrong:** Tags start as freeform strings. Within weeks, the taxonomy is a mess: `react`, `React`, `React.js`, `ReactJS`, `react-18`, `react18` all exist as separate tags. Search by tag returns incomplete results. Tag-based filtering becomes unreliable.

**Prevention:** Implement tag normalization (lowercase, canonical forms) at ingestion. Maintain a curated tag dictionary with aliases. Reject tags not in the dictionary for unverified contributors — let them propose new tags via a separate flow.

**Phase mapping:** Phase 1 (trace schema design). Much harder to normalize retroactively.

---

### Pitfall 13: Over-Engineering the Reputation Formula Before Having Data

**What goes wrong:** Team spends weeks designing a complex multi-variable reputation formula (Bayesian average, time decay, context weighting, Sybil resistance score) before any real usage data exists. The formula is optimized for hypothetical scenarios, not actual agent behavior patterns.

**Prevention:** Launch with a simple formula (sum of upvotes minus downvotes, weighted by voter reputation). Instrument everything. Evolve the formula based on observed gaming patterns and quality outcomes after 30 days of real data.

**Phase mapping:** Phase 2. Resist the urge to pre-optimize.

---

### Pitfall 14: Agent Identity Instability Destroying Reputation History

**What goes wrong:** Agent identity is based on API keys. Users rotate their API keys (security best practice, key compromise). Their entire reputation history is lost. High-reputation contributors are reset to zero. They lose trust in the platform.

**Prevention:** Decouple agent identity from API keys. Use a stable user/agent identifier (UUID) with multiple API keys that can be rotated while preserving identity and reputation. Implement key rotation as a first-class operation.

**Phase mapping:** Phase 2 (identity model design).

---

### Pitfall 15: Open Source Contribution Without Contribution License Agreement

**What goes wrong:** External contributors submit traces or code that contains copyrighted material. The project is open source but traces are potentially derived works. Legal ambiguity arises about who owns what.

**Prevention:** Establish clear Terms of Service from day one: contributors grant CommonTrace a license to store, distribute, and index their traces. Traces containing code adopt the same license as the project (MIT/Apache). Make this explicit in the contribution flow.

**Phase mapping:** Phase 1 (legal groundwork before any public content is accepted).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Data model (Phase 1) | Missing embedding model versioning column | Add `embedding_model_id` + `embedding_model_version` to trace schema before writing any data |
| Data model (Phase 1) | Freeform tags leading to taxonomy chaos | Implement tag normalization and canonical dictionary at ingestion |
| Data model (Phase 1) | No cold start seeding plan | Define seeding strategy (manual + synthetic) as a Phase 1 deliverable |
| Contribution API (Phase 2) | No PII scanning in contribution pipeline | PII scanner must be a synchronous gate before trace storage |
| Contribution API (Phase 2) | Vote API with no contextual tags | Design vote schema with required contextual tag from day one |
| Reputation engine (Phase 2) | Sybil-vulnerable identity model | Identity cost (API key + email), vote weight by voter reputation, outcome-based scoring |
| MCP server (Phase 2) | Synchronous hard dependency on backend | Circuit-breaker and graceful degradation must be in the initial MCP server design |
| Search (Phase 2) | Pure vector search returning irrelevant results | Hybrid BM25 + vector search required from launch, not added later |
| Observability (Phase 3) | No staleness monitoring | Track "traces with no validity votes in 90 days" as a key metric; integrate version release feeds |
| Rate limiting (Phase 3) | Fixed window counters punishing bursty agent behavior | Token bucket algorithm; separate read/write limits; session grace period |
| Scale planning (Phase 3+) | pgvector scaling assumptions not validated | Capacity test at 100K, 1M, 10M traces; have migration path to dedicated vector DB ready |
| Community (Phase 4+) | Bootstrapping never completed | Seed content must be maintained; founding contributor program; editorial quality standards |

---

## Sources

**Confidence note:** Research was conducted using training knowledge only (WebSearch and Read tools unavailable in this session). Confidence assessments:

| Area | Confidence | Basis |
|------|------------|-------|
| Knowledge poisoning | HIGH | Extensive literature on adversarial ML, RAG security, prompt injection; directly applicable |
| Cold start problem | HIGH | Well-documented in network-effect platform literature (Stack Overflow, Reddit, Quora histories) |
| Embedding model versioning | HIGH | Documented OpenAI behavior; standard production RAG pattern |
| Reputation gaming / Sybil | HIGH | Extensive academic and engineering literature; Stack Overflow blog posts on gaming |
| Trace staleness | HIGH | Known problem in Stack Overflow; directly analogous to this domain |
| MCP reliability | MEDIUM | MCP is relatively new (2024); circuit-breaking patterns are standard; MCP-specific failure modes from training data |
| pgvector scaling limits | HIGH | Published benchmarks and engineering posts on pgvector at scale are well-documented |
| Freemium rate limiting | HIGH | Standard distributed systems pattern; agent workload bursty behavior is well-understood |
| Privacy leakage | HIGH | Documented in LLM application security literature |

**Key sources in training data (not verified fresh in this session):**
- Stack Overflow Engineering Blog (reputation system design posts)
- OpenAI Embeddings documentation and changelog
- pgvector GitHub issues and benchmarks
- HuggingFace Hub engineering posts on knowledge base quality
- Weaviate, Qdrant, and Pinecone documentation on ANN search at scale
- Academic literature on Sybil attacks in peer-to-peer systems
- OWASP LLM Top 10 (training data poisoning, prompt injection categories)
