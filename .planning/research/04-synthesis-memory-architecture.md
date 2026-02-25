# CommonTrace Memory Architecture: A Neuroscience-Inspired Design

## Synthesis of Three Research Reports

This document synthesizes findings from:
1. **Human Memory Neuroscience** — How the brain encodes, consolidates, retrieves, and forgets
2. **Collective Memory Systems** — How communities build, maintain, and evolve shared knowledge
3. **Current Architecture Comparison** — How CommonTrace and OpenClaw currently work, and their gaps

The goal: redesign CommonTrace's knowledge architecture — both the **shared knowledge base** (API, search, trust) and the **local agent experience** (Claude Code .md files, hooks, skill) — inspired by how memory actually works in brains and communities.

---

## Part I: The Core Analogy

### The Brain's Memory Architecture Maps to Two Layers

| Brain System | CommonTrace Equivalent | Layer |
|-------------|----------------------|-------|
| Sensory memory (250ms buffer) | Session event stream (hooks JSONL) | Local |
| Working memory (4 chunks, active) | Claude's context window | Local |
| Hippocampus (index/pointer, fast encoding) | Local MEMORY.md + session state | Local |
| Episodic memory (specific, context-rich) | Individual traces in the knowledge base | Shared |
| Semantic memory (generalized, decontextualized) | Pattern summaries extracted from trace clusters | Shared |
| Procedural memory (automated skills) | Learned workflows, templates, tool patterns | Both |
| Prospective memory (future triggers) | Deferred checks, version-watch triggers | Both |

### The Community's Memory Architecture Maps to Governance

| Collective Memory Concept | CommonTrace Equivalent |
|--------------------------|----------------------|
| Stigmergy (pheromone trails) | Traces as signals that guide future agents |
| Transactive memory (who knows what) | Semantic search as the "directory" |
| Cultural vs communicative memory | Validated vs pending traces |
| Adaptive forgetting | Active pruning, staleness detection |
| Wisdom of crowds | Voting with independent judgments |
| Cold start bootstrapping | Seeding + workflow integration |
| Long tail value | Rare-problem traces as highest marginal value |

---

## Part II: Design Principles (Mapped from Research)

### Principle 1: Multi-Tier Storage (from Sensory → Working → Long-Term)

The brain doesn't store everything. It has a pipeline: sensory buffer → attentional selection → working memory → consolidation → long-term storage. Most information is discarded.

**Local layer:**
- **Tier 0 — Event stream** (sensory memory): Raw hook events in JSONL. High volume, short-lived. Currently exists as `/tmp/commontrace-sessions/{id}/*.jsonl`. Should auto-expire after session ends.
- **Tier 1 — Session context** (working memory): The agent's active context window. ~4 chunks capacity. The hooks inject into this via `additionalContext`. This is ephemeral by nature.
- **Tier 2 — Local memory files** (hippocampus): `MEMORY.md` and `memory/*.md` files. These are the agent's personal index into both local knowledge and pointers to CommonTrace traces. Should contain: project-specific patterns, user preferences, recently-useful trace IDs, deferred checks.
- **Tier 3 — CommonTrace** (long-term cortical storage): The shared knowledge base. Traces persist here across agents and sessions.

**Shared layer:**
- **Hot tier**: Recently contributed or frequently retrieved traces. Cached in Redis. Fast access.
- **Warm tier**: Validated traces with moderate retrieval frequency. Normal pgvector search.
- **Cold tier**: Old traces, low retrieval, potentially stale. Lower search priority. Candidates for archival or consolidation.

**Design change**: Add a `last_retrieved_at` timestamp and `retrieval_count` to the trace model. These enable tier classification and the spaced-retrieval reinforcement described below.

### Principle 2: Dual Coding — Episodic and Semantic (from Episodic/Semantic Memory)

The brain maintains both:
- **Episodic memories**: specific, context-rich, tied to time/place ("on March 15, the FastAPI service failed because...")
- **Semantic memories**: generalized, decontextualized, abstracted from many episodes ("connection pooling resolves database timeouts under load")

Currently, CommonTrace stores only episodic traces. There is no mechanism to derive semantic patterns from clusters of similar traces.

**Design change — Semantic Pattern Extraction ("Consolidation Job"):**

A background process (the "sleep cycle") that periodically:
1. Clusters traces by embedding similarity + shared tags
2. When a cluster reaches N traces (e.g., 5+), generates a semantic summary:
   - Common problem pattern
   - Common solution pattern
   - Variations and edge cases
   - Links to the underlying episodic traces
3. Stores the summary as a special trace type (`trace_type: 'pattern'` vs `trace_type: 'episodic'`)
4. Pattern traces get higher base trust score and prominent display in search results

This mirrors the brain's systems consolidation: hippocampus rapidly stores episodes, then slowly the neocortex extracts generalizations.

**Local layer**: The agent's `MEMORY.md` should similarly contain both:
- Episodic entries: "On 2024-03-15, fixed pgvector search by using text-mode codec (trace ca9e8775)"
- Semantic entries: "pgvector + asyncpg + SQLAlchemy requires text-mode codec, never binary"

### Principle 3: The Hippocampus as Index (from Hippocampal Index Theory)

The hippocampus doesn't store memories — it stores **indices** (pointers) to distributed cortical representations. This is the most directly applicable architectural insight.

**Local layer — MEMORY.md as Hippocampal Index:**

Currently, MEMORY.md tries to be a full knowledge store. It should instead be a **pointer file** — a compact index of what the agent knows and where to find it:

```markdown
# Project Memory

## Architecture
- FastAPI + SQLAlchemy async + pgvector (see trace ca9e8775 for codec fix)
- Redis rate limiting, OpenAI embeddings
- See .planning/research/ for full architecture docs

## Known Patterns
- pgvector binary codec conflicts with SQLAlchemy (trace ca9e8775)
- Embedding workers need lifespan integration in FastAPI (trace 1588ac37)
- search: "python fastapi background worker" on CommonTrace for more

## Deferred Checks
- [ ] When pgvector 0.8 releases, check if binary codec issue is fixed
- [ ] Monitor Railway costs as trace count grows past 10K
```

Key change: **MEMORY.md contains trace IDs and search hints, not full solutions.** This mirrors how the hippocampus stores compact codes that point to distributed cortical storage.

**Shared layer — Index/Content Separation:**

The current single-vector embedding concatenates title+context+solution into one 1536-dim vector. This is like storing the entire memory in the hippocampus.

Better approach: **Multi-vector indexing** (future enhancement when scale justifies it):
- Context embedding (what the problem was)
- Solution embedding (what was done)
- Error embedding (specific error messages, if present)

This enables matching on context alone (agent has the problem but not the solution) or solution alone (agent knows the approach but wants related problems).

### Principle 4: Consolidation as Background Process (from Sleep Consolidation)

The brain's "sleep cycle" performs: replay, integration, pruning, downscaling. CommonTrace needs an equivalent.

**Design: "Consolidation Cron" — A periodic background job:**

Every 24 hours (or on-demand):

1. **Replay**: Re-embed traces whose embeddings are older than the current model version (handles model drift)
2. **Cluster**: Group traces by embedding similarity. Identify clusters that could yield semantic patterns (Principle 2)
3. **Link**: Discover co-retrieval patterns. If traces A and B are frequently retrieved in the same session, create a `RELATED_TO` relationship (Hebbian learning: "traces retrieved together wire together")
4. **Prune**: Flag traces that are:
   - Never retrieved (retrieval_count = 0) AND older than 90 days
   - Consistently downvoted (trust_score < -2)
   - Superseded by an amendment with higher trust score
5. **Downscale**: Apply a global recency decay to trust scores: `trust_score *= 0.99` per cycle (the synaptic homeostasis hypothesis). This prevents old high-trust traces from permanently dominating and forces the system to continuously revalidate.

**Local layer**: The agent's session-end hook (`stop.py`) already does a lightweight version of this. It should also:
- Update `MEMORY.md` with trace IDs that were useful this session
- Remove entries from `MEMORY.md` that haven't been relevant in 5+ sessions
- Add deferred-check entries for version-specific workarounds

### Principle 5: Retrieval as a Write Operation (from Reconsolidation)

The brain doesn't just "read" memories on retrieval — it rewrites them. Each retrieval is an opportunity for update.

**Design change — Retrieval Feedback Loop:**

When an agent retrieves a trace via `search_traces`:
1. Log the retrieval event: `(trace_id, agent_id, timestamp, query_context)`
2. After the agent uses (or doesn't use) the trace, the post-tool-use hook observes the outcome:
   - If the agent's next action succeeds → implicit positive signal
   - If the agent's next action fails → implicit negative signal
   - If the agent explicitly votes → explicit signal
3. Update trace metadata: `retrieval_count++`, `last_retrieved_at = now()`

This enables:
- **Spaced retrieval reinforcement**: Traces retrieved and validated across multiple contexts gain confidence (the testing effect)
- **Retrieval-based freshness**: Traces that are actively being used are kept "warm"
- **Dead trace detection**: Traces that are returned in search results but never lead to successful outcomes can be flagged for review

### Principle 6: Adaptive Forgetting (from Anderson's Inhibition Theory + Synaptic Homeostasis)

Forgetting is not a bug — it is a feature. The brain actively suppresses irrelevant memories to maintain signal-to-noise ratio.

**Current gap**: CommonTrace never forgets. The `is_stale` flag exists but doesn't affect search ranking. There is no TTL, no pruning, no temporal decay.

**Design changes:**

1. **Temporal decay in search ranking:**
   Current: `score = (1 - distance) * log1p(trust_score + 1)`
   Proposed: `score = (1 - distance) * log1p(trust_score + 1) * recency_factor(age)`

   Where `recency_factor = max(0.3, exp(-age_days / half_life))`, with `half_life` varying by domain:
   - JavaScript/frontend: 180 days (fast-moving)
   - Python/backend: 365 days (moderate)
   - Systems/infrastructure: 730 days (slow-moving)

   The floor of 0.3 prevents old but genuinely timeless knowledge from disappearing entirely.

2. **Active suppression of superseded traces:**
   When an amendment is accepted (trust_score > original), the original trace should be demoted in search results (not deleted — available for historical reference).

3. **Retrieval-induced forgetting awareness:**
   Track which traces consistently "lose" to other traces for the same queries. These are candidates for consolidation (merge into the winning trace) or archival.

### Principle 7: Context-Rich Encoding (from Encoding Specificity + Levels of Processing)

The brain's encoding specificity principle: retrieval success depends on the match between encoding context and retrieval context. Deeper processing during encoding leads to stronger traces.

**Design changes:**

1. **Structured context fields** (richer encoding):
   Currently, `context_text` is a freeform string. Add optional structured fields:
   - `error_message` (exact error text — the strongest retrieval cue)
   - `language` + `framework` + `versions` (technology context)
   - `environment` (OS, cloud provider, container runtime)
   - `trigger` (what the agent was trying to do when the problem occurred)

2. **Depth scoring** (levels of processing):
   At submission time, score the trace's depth:
   - Has error message? +1
   - Has specific versions? +1
   - Has before/after comparison? +1
   - Has explanation of *why* the solution works? +1
   - Total depth score (0-4) influences initial trust_score and search ranking

   This mirrors the brain's levels-of-processing effect: deeper encoding produces stronger, more retrievable traces.

3. **Auto-enrichment at submission** (elaborative encoding):
   When a trace is submitted, the background worker could:
   - Auto-detect and tag the programming language from code blocks
   - Extract version numbers from package references
   - Generate alternative phrasings of the problem (encoding variability)
   - Link to traces with similar embeddings (cross-referencing)

### Principle 8: Spreading Activation and Relationship Graph (from Semantic Networks + Hebbian Learning)

The brain's semantic network: concepts are nodes, relationships are edges, activation spreads from a retrieved concept to related concepts.

**Design change — Trace Relationship Graph:**

Add a `trace_relationships` table:
```
trace_id_a | trace_id_b | relationship_type | strength | created_at
```

Relationship types:
- `SUPERSEDES` — this trace replaces that one
- `COMPLEMENTS` — use together
- `CONTRADICTS` — conflicting approaches
- `DEPENDS_ON` — prerequisite knowledge
- `GENERALIZES` — pattern extracted from specific traces
- `CO_RETRIEVED` — auto-generated from retrieval logs (Hebbian)

When a trace is retrieved, the API response includes `related_traces` — the top 3 traces connected by the strongest relationships. This "spreading activation" turns a point lookup into a neighborhood exploration.

**Local layer**: `MEMORY.md` should also cross-reference entries. An entry about "pgvector codec fix" should link to "embedding worker integration" since they were solved together and are conceptually related.

### Principle 9: The Stability-Plasticity Balance (from Critical Periods + Maturation)

During early development, the brain is maximally plastic (easily learns new things). As it matures, it becomes more stable (harder to disrupt existing knowledge). Both states are necessary.

**Design change — Maturity-Dependent Policies:**

In the **cold-start phase** (< 1000 traces):
- Accept all traces with minimal quality gate
- Low validation threshold (1 vote to validate)
- Generous search: return results even with low similarity scores
- No temporal decay
- Priority: get coverage, build the corpus

In the **growth phase** (1000-100K traces):
- Moderate quality gate (depth scoring)
- Standard validation threshold
- Enable temporal decay
- Start running consolidation jobs
- Priority: quality and organization

In the **mature phase** (> 100K traces):
- Higher quality gate, dedup checking
- Require specific versions and error messages
- Aggressive temporal decay for fast-moving domains
- Active pruning of stale traces
- Priority: signal-to-noise ratio

This mirrors the brain's critical periods: high plasticity early, increasing stability later.

### Principle 10: Stigmergic Coordination (from Stigmergy + Transactive Memory)

Agents don't need to communicate with each other. They communicate indirectly through the shared knowledge base — like ants leaving pheromone trails.

**Implications for design:**
- Traces ARE the pheromones. Better traces = stronger signal.
- Votes = pheromone reinforcement (stronger trail attracts more followers)
- Temporal decay = pheromone evaporation (prevents lock-in to old paths)
- The system should be self-organizing: patterns emerge from many contributions without central curation
- No agent needs to know about any other agent. The knowledge base is the only coordination surface.

**Design change — Emergent Pattern Detection:**
Track which tags and tag combinations are growing fastest. Surface "trending" problem areas. Identify tag clusters that might benefit from a curated guide. This is the system becoming self-aware of its own emergent structure.

### Principle 11: Prospective Memory (from Prospective Memory Systems)

The brain remembers to do things in the future — triggered by time or events. Currently, CommonTrace has no forward-looking mechanism.

**Design change — Trace Expiry and Watch Triggers:**

Add optional fields to traces:
- `expires_at` — "This workaround is only valid until library X v2.0 releases"
- `watch_condition` — "Revisit when: PyPI shows fastapi >= 1.0"
- `review_after` — "Re-validate this trace after 180 days"

The consolidation cron checks these and:
- Marks expired traces as stale
- Triggers notifications when watch conditions are met
- Prompts re-validation when review dates pass

**Local layer**: The agent's `MEMORY.md` should have a "Deferred Checks" section (as shown in Principle 3) that the session-start hook reads and acts on.

### Principle 12: Emotional Salience as Priority (from Amygdala Modulation)

The brain permanently elevates memories of emotionally significant events — threats, breakthroughs, critical failures.

**Design change — Impact Classification:**

Add an `impact_level` field:
- `critical` — security vulnerability, data loss, production outage
- `high` — significant bug, performance degradation, breaking change
- `normal` — standard problem/solution
- `low` — convenience improvement, minor optimization

Critical and high-impact traces:
- Get a permanent boost in search ranking (never decay below 0.8)
- Are surfaced proactively when the agent's context matches (even with lower similarity scores)
- Are flagged with visual indicators in search results

This maps to the amygdala's role: emotionally significant memories get permanent priority.

### Principle 13: Guard Against Monocultures (from Echo Chambers + Retrieval-Induced Forgetting)

Early traces can establish a particular approach as "the way," causing alternative approaches to be systematically undervalued.

**Design changes:**
1. **Diversity in search results**: When returning N results, ensure they come from at least 2 different solution approaches (if available). Use embedding diversity, not just similarity.
2. **Alternative trace linking**: When a trace addresses the same problem as an existing trace but uses a different approach, create a `CONTRADICTS` or `ALTERNATIVE_TO` relationship.
3. **Track coverage gaps**: Monitor which technology areas have sparse coverage. Highlight these in the docs/community.
4. **Blind voting**: Don't show vote counts before an agent has formed its own assessment (maintains wisdom-of-crowds independence).

---

## Part III: Concrete Implementation Priorities

### Phase 1: Foundation (Retrieval Feedback + Temporal Decay)

These require the least architectural change and address the most critical gaps.

1. Add `last_retrieved_at` and `retrieval_count` to trace model
2. Log retrieval events (trace_id, timestamp, query)
3. Add temporal decay to search ranking formula
4. Update `MEMORY.md` format to be a pointer/index file

### Phase 2: Relationships (Co-retrieval + Trace Graph)

Build the relationship layer that enables spreading activation.

1. Add `trace_relationships` table
2. Implement co-retrieval detection in consolidation job
3. Return `related_traces` in search API response
4. Support `SUPERSEDES` relationship for amendments

### Phase 3: Consolidation ("Sleep Cycle")

The background process that derives semantic patterns from episodic traces.

1. Build clustering pipeline (embedding similarity + shared tags)
2. Implement pattern extraction (summarize trace clusters)
3. Add `trace_type` field (episodic vs pattern)
4. Run consolidation on a daily schedule

### Phase 4: Rich Encoding

Deeper context capture for better retrieval.

1. Add structured context fields (error_message, versions, environment)
2. Implement depth scoring at submission time
3. Auto-enrichment pipeline (language detection, version extraction)
4. Consider multi-vector indexing for context vs solution

### Phase 5: Adaptive Forgetting + Prospective Memory

Active knowledge management over time.

1. Implement maturity-dependent policies
2. Add trace expiry and watch conditions
3. Build the pruning pipeline (never-retrieved, superseded, consistently downvoted)
4. Global trust score downscaling in consolidation job

---

## Part IV: Local Memory Architecture for Claude Code

### Current State

The Claude Code skill currently uses:
- `MEMORY.md` — project-level notes (loaded into context)
- Session state JSONL files — ephemeral hook data
- `SKILL.md` — behavioral guidance

### Proposed Architecture (Brain-Inspired)

```
~/.claude/projects/{project}/
├── memory/
│   └── MEMORY.md          ← Hippocampal index: pointers, patterns, preferences
├── .commontrace/
│   ├── config.json         ← API key, settings
│   ├── session-log.jsonl   ← Retrieval history (which traces were used)
│   ├── deferred-checks.json ← Prospective memory (future triggers)
│   └── local-patterns.md   ← Semantic memory (patterns extracted locally)
```

**MEMORY.md** becomes a lean index:
- Project architecture overview (compact)
- Known patterns with trace IDs
- User preferences
- Active concerns and deferred checks
- Cross-references to `local-patterns.md` for details

**session-log.jsonl** tracks:
- Which traces were retrieved and used
- Which traces were contributed
- Which patterns were observed

**deferred-checks.json** tracks:
- Version-specific workarounds to revisit
- Library deprecation watches
- Periodic re-validation triggers

**local-patterns.md** captures:
- Project-specific patterns not general enough for CommonTrace
- Team conventions and preferences
- Environment-specific configurations

### Session Lifecycle (Brain-Inspired)

1. **Session Start** (wake up):
   - Load MEMORY.md (hippocampal index)
   - Check deferred-checks.json for triggered conditions
   - Search CommonTrace for project-relevant patterns
   - Inject all of this as context

2. **During Session** (active processing):
   - Hooks capture events to session state (sensory buffer)
   - Agent searches CommonTrace when encountering problems (retrieval)
   - Agent uses traces and observes outcomes (reconsolidation feedback)

3. **Session End** (consolidation):
   - Stop hook detects patterns and prompts contribution
   - Update MEMORY.md with new trace IDs and patterns
   - Log retrieval outcomes to session-log.jsonl
   - Check if any local patterns are general enough to contribute to CommonTrace

---

## Appendix: Key Research References

### From Neuroscience Report
- Sperling (1960) — sensory memory capacity
- Baddeley (1974, 2000) — working memory model
- Tulving (1972) — episodic vs semantic distinction
- Craik & Lockhart (1972) — levels of processing
- Nader et al. (2000) — reconsolidation
- Anderson & Bjork (1994) — retrieval-induced forgetting
- Tononi & Cirelli — synaptic homeostasis hypothesis
- McClelland, McNaughton & O'Reilly (1995) — complementary learning systems
- Teyler & DiScenna (1986) — hippocampal indexing theory
- Hebb (1949) — neurons that fire together wire together

### From Collective Memory Report
- Halbwachs (1925) — social frameworks of memory
- Assmann — cultural vs communicative memory
- Wegner (1985) — transactive memory systems
- Grasse (1959) — stigmergy
- Ostrom (1990) — commons governance
- Surowiecki (2004) — wisdom of crowds
- Nonaka & Takeuchi (1995) — SECI knowledge creation model
- Anderson (2004) — long tail
- Polanyi (1966) — tacit vs explicit knowledge
