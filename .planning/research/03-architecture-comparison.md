I now have a thorough understanding of both systems. Here is the full architectural report.

---

# Architectural Report: Memory Systems of CommonTrace and OpenClaw

## 1. Data Model Comparison

### CommonTrace

CommonTrace structures knowledge as **traces** -- discrete, atomic units of problem/solution knowledge stored in PostgreSQL. Each trace has a rigid schema:

**Trace model** (`/home/bitnami/commontrace/api/app/models/trace.py`):
- `title` (text) -- short description of what the trace solves
- `context_text` (text) -- the problem context
- `solution_text` (text) -- what worked
- `embedding` (Vector(1536), nullable) -- pgvector column, null until background worker processes it
- `embedding_model_id` / `embedding_model_version` -- tracks which model produced the embedding
- `status` (pending | validated) -- trust state machine
- `trust_score` (float, default 0.0) -- net vote score
- `confirmation_count` (int) -- number of votes received
- `contributor_id` (FK to users) -- who submitted it
- `agent_model` / `agent_version` -- metadata about the AI agent that produced the solution
- `metadata_json` (JSON, nullable) -- open-ended bag for library name, library version, etc.
- `is_seed` / `is_stale` / `is_flagged` -- lifecycle flags
- `created_at` / `updated_at` -- timestamps

**Related models:**
- `Tag` (`/home/bitnami/commontrace/api/app/models/tag.py`): normalized string (max 50 chars), many-to-many via `trace_tags` join table
- `Vote` (`/home/bitnami/commontrace/api/app/models/vote.py`): one vote per (trace, voter), stores vote_type (up/down), feedback_text, context_json
- `Amendment` (`/home/bitnami/commontrace/api/app/models/amendment.py`): proposed improved solution linked to an original trace, with explanation
- `ContributorDomainReputation` (`/home/bitnami/commontrace/api/app/models/reputation.py`): per-(contributor, domain_tag) pair tracking upvote/downvote counts and a Wilson score

The data model is **relational and normalized**. Knowledge is structured as explicit problem-solution pairs, categorized by tags, and quality-controlled through votes and reputation.

### OpenClaw

OpenClaw structures knowledge as **plain Markdown files** on disk, chunked into embedding-indexed segments stored in SQLite. There is no rigid schema for the content -- the structure is freeform prose.

**Schema** (`/home/bitnami/openclaw/src/memory/memory-schema.ts`):
- `files` table: `path` (PK), `source` (memory|sessions), `hash`, `mtime`, `size`
- `chunks` table: `id` (PK), `path`, `source`, `start_line`, `end_line`, `hash`, `model`, `text`, `embedding` (JSON text), `updated_at`
- `embedding_cache` table: caches embeddings by (provider, model, provider_key, hash)
- FTS5 virtual table (`chunks_fts`): full-text index over chunk text
- sqlite-vec virtual table (`chunks_vec`): vector distance queries

**Memory sources** (from `MemorySource` type in `/home/bitnami/openclaw/src/memory/types.ts`):
- `"memory"` -- Markdown files: `MEMORY.md` (curated long-term) and `memory/YYYY-MM-DD.md` (daily logs)
- `"sessions"` -- session transcript JSONL files (experimental, opt-in)

**Search result shape** (`MemorySearchResult`):
- `path`, `startLine`, `endLine` -- location within a file
- `score` -- relevance score
- `snippet` -- text extract (max 700 chars)
- `source` -- which source (memory vs sessions)
- `citation` -- optional path#line reference

**Key difference**: CommonTrace has an explicit, structured data model (title/context/solution/tags/votes) while OpenClaw has an implicit, unstructured model (chunks of Markdown, dated files, freeform content). CommonTrace's unit of knowledge is a "trace" (a solved problem); OpenClaw's unit is a "chunk" (a segment of prose from a memory file).

---

## 2. Encoding Pipeline

### CommonTrace: Raw Experience to Stored Knowledge

The encoding pipeline has two stages, involving both agent-side hooks and server-side processing:

**Stage 1: Agent-side pattern detection (CT-Skill hooks)**

The hook system in `/tmp/ct-skill/hooks/` operates as a two-layer architecture:

1. **Layer 1 (state writers)**: `post_tool_use.py`, `post_tool_failure.py`, `user_prompt.py` write structural signals to JSONL files in `/tmp/commontrace-sessions/{session_id}/`:
   - `errors.jsonl` -- Bash errors (non-zero exit code or stderr)
   - `resolutions.jsonl` -- successful Bash runs after errors
   - `changes.jsonl` -- file modifications (with config-file detection)
   - `research.jsonl` -- WebSearch/WebFetch activity
   - `contributions.jsonl` -- traces already contributed
   - `user_turn_count` -- integer counter of user messages

2. **Layer 2 (pattern recognizer)**: `stop.py` reads all Layer 1 state and detects six structural patterns: error_resolution, workaround, config_discovery, iteration, multi_turn_work, post_contribution. When a pattern is detected with sufficient confidence (temporal ordering, verification through resolutions or absence of new errors), it prompts the agent to contribute.

**Stage 2: Server-side processing**

When the agent submits via `POST /api/v1/traces` (`/home/bitnami/commontrace/api/app/routers/traces.py`):
1. PII/secrets scan (`scanner.py`) -- blocks credentials from entering the database
2. Tag normalization and validation (`tags.py`) -- lowercase, strip, truncate to 50 chars, alphanumeric only
3. Staleness check (`staleness.py`) -- checks PyPI for outdated library versions
4. Trace row created in "pending" status
5. Background embedding worker (`embedding_worker.py`) polls every 5 seconds, claims unembedded traces with `FOR UPDATE SKIP LOCKED`, concatenates title+context+solution, calls OpenAI `text-embedding-3-small` to produce a 1536-dim vector

**Embedding input**: `f"{trace.title}\n{trace.context_text}\n{trace.solution_text}"` -- all three fields concatenated.

### OpenClaw: Raw Experience to Stored Knowledge

OpenClaw has three encoding pathways:

**Pathway 1: Manual memory writes**

The agent (or user) directly writes to `MEMORY.md` or `memory/YYYY-MM-DD.md`. The agent is instructed in `SOUL.md` (`/home/bitnami/openclaw/docs/reference/templates/SOUL.md`):
> "Each session, you wake up fresh. These files _are_ your memory. Read them. Update them. They're how you persist."

**Pathway 2: Automatic pre-compaction memory flush**

When a session approaches the context window limit (`/home/bitnami/openclaw/src/auto-reply/reply/memory-flush.ts`), OpenClaw triggers a silent agentic turn with the prompt:
> "Pre-compaction memory flush. Store durable memories now (use memory/YYYY-MM-DD.md; create memory/ if needed)."

This runs the LLM with a system prompt telling it the session is near auto-compaction and it should capture durable memories. The threshold is `contextWindow - reserveTokensFloor - softThresholdTokens` (default ~4000 tokens before compaction).

**Pathway 3: Session-to-memory hook**

When the user issues `/new` (`/home/bitnami/openclaw/src/hooks/bundled/session-memory/handler.ts`):
1. Reads the last N messages (default 15) from the session transcript JSONL
2. Calls an LLM to generate a descriptive slug (e.g., "api-design", "vendor-pitch")
3. Writes to `memory/YYYY-MM-DD-{slug}.md` with session metadata and conversation content

**Indexing pipeline**:

Once files exist on disk, the `MemoryIndexManager` (`/home/bitnami/openclaw/src/memory/manager.ts`) handles indexing:
1. File watcher (chokidar) detects changes, debounced at 1.5 seconds
2. Files are chunked (~400 tokens with 80-token overlap)
3. Each chunk is embedded via configurable provider (OpenAI text-embedding-3-small, Gemini, Voyage, or local GGUF model)
4. Embeddings stored in SQLite (both JSON text in `chunks` table and as Float32 blobs in `chunks_vec` virtual table)
5. FTS5 full-text index updated in parallel
6. Embedding cache prevents re-embedding unchanged chunks

**Key difference**: CommonTrace requires explicit, structured contribution with title/context/solution separation. OpenClaw allows freeform prose -- the agent decides what and how to write. CommonTrace has a human-in-the-loop gate (the agent asks user approval before contributing); OpenClaw's memory flush is autonomous.

---

## 3. Retrieval Mechanisms

### CommonTrace

Three search modes via `POST /api/v1/traces/search` (`/home/bitnami/commontrace/api/app/routers/search.py`):

1. **Semantic-only** (q provided, tags empty): Embeds the query via OpenAI, then performs cosine ANN via pgvector (`HNSW ef_search=64`). Over-fetches 100 candidates, then trust-weighted re-ranks: `(1.0 - distance) * log1p(max(0, trust_score) + 1)`. Returns top N.

2. **Tag-only** (tags provided, q empty): SQL filter with AND semantics (all tags must match), ordered by `trust_score DESC`. No embedding call.

3. **Hybrid** (q + tags): Cosine ANN with tag pre-filter (JOIN on trace_tags), then trust-weighted re-ranking.

Flagged traces are always excluded. Traces with null embeddings are excluded only in semantic mode.

### OpenClaw

Search via `MemoryIndexManager.search()` (`/home/bitnami/openclaw/src/memory/manager.ts`) with a multi-stage pipeline:

1. **Vector search**: Embeds the query, performs cosine distance via sqlite-vec (or fallback in-process cosine similarity)
2. **BM25 keyword search**: FTS5 full-text search with BM25 ranking, using `buildFtsQuery()` which tokenizes and AND-joins quoted terms
3. **Hybrid merge**: `finalScore = vectorWeight * vectorScore + textWeight * textScore` (default 70/30 split)
4. **Temporal decay** (optional): `decayedScore = score * e^(-lambda * ageInDays)` with 30-day half-life. Evergreen files (`MEMORY.md`, non-dated `memory/*.md`) are exempt.
5. **MMR re-ranking** (optional): Maximal Marginal Relevance penalizes redundant results using Jaccard token similarity.
6. **Min-score filter and top-K**: Default min score 0.35, default max results 6.

**FTS-only fallback**: When no embedding provider is available, OpenClaw falls back to keyword extraction via `extractKeywords()` (`/home/bitnami/openclaw/src/memory/query-expansion.ts`) which strips stop words (English + Chinese) and tokenizes the query for FTS matching.

**Key differences**:
- CommonTrace combines semantic similarity with trust score (community quality signal). OpenClaw combines semantic similarity with keyword relevance and recency.
- CommonTrace retrieval is community-wide (searches across all contributors). OpenClaw retrieval is personal (searches only the agent's own workspace memory).
- CommonTrace has no temporal decay -- all traces are equally accessible regardless of age. OpenClaw can decay old memories.
- OpenClaw has a diversity mechanism (MMR) that CommonTrace lacks.

---

## 4. Quality/Trust Mechanisms

### CommonTrace

A sophisticated, multi-layered trust system:

**Trace lifecycle** (`pending` -> `validated`):
- All new traces start as `pending`
- Promoted to `validated` when `confirmation_count >= validation_threshold` AND `trust_score > 0`

**Voting system** (`/home/bitnami/commontrace/api/app/services/trust.py`):
- Each user can vote once per trace (enforced by DB unique constraint)
- Vote weight is reputation-dependent: new contributors get `BASE_WEIGHT = 0.1`, established contributors get up to their Wilson score (max ~1.0)
- Trust score is atomically updated: `trust_score += vote_weight` (up) or `trust_score -= vote_weight` (down)

**Domain reputation** (`ContributorDomainReputation`):
- Per-(contributor, tag) reputation tracked separately
- Uses Wilson score lower bound at 95% confidence interval
- An established contributor with 80% upvote rate on 50 votes gets ~0.66, giving them 6.6x the vote weight of a new contributor (0.1)
- Aggregate Wilson score propagated to `users.reputation_score`

**Safety gates**:
1. **PII/secrets scanner** (`scanner.py`) -- uses `detect-secrets` with `enable_eager_search=False` to block credentials
2. **Staleness detection** (`staleness.py`) -- checks PyPI for outdated library versions, sets `is_stale` flag
3. **Flagging** -- `is_flagged` flag with `flagged_at` timestamp excludes traces from search results
4. **Amendment system** -- allows proposing improved solutions without destroying the original

### OpenClaw

OpenClaw has minimal quality mechanisms:

- **No voting or community validation** -- the agent's own writes are trusted by default
- **No reputation system** -- single-user context
- **Temporal decay** -- old information is naturally deprioritized (if enabled), acting as a soft quality signal
- **Manual curation** -- the user or agent manually updates `MEMORY.md` and can delete/edit memory files
- **Stale file cleanup** (`/home/bitnami/openclaw/src/memory/sync-stale.ts`): When files are deleted from disk, their indexed chunks, vectors, and FTS entries are cleaned up
- **Min-score threshold** (default 0.35) -- low-relevance results are filtered out

**Key difference**: CommonTrace has a full community trust layer (votes, reputation, Wilson scores, validation threshold, PII scanning). OpenClaw trusts its own agent's writes implicitly and relies on the user to curate quality. This is appropriate for their different scopes -- CommonTrace is a shared knowledge base where bad actors exist; OpenClaw is a personal assistant where trust is assumed.

---

## 5. Trigger Mechanisms

### CommonTrace: When Knowledge is Stored

**Inbound triggers (storage):**
1. **Session start hook** (`session_start.py`): Detects project context (language, framework from pyproject.toml/package.json/Cargo.toml), searches CommonTrace, injects results as `additionalContext` in the session start event.
2. **Post-tool-use hook** (`post_tool_use.py`): On Bash error (non-zero exit code or stderr), automatically searches CommonTrace with the last 200 chars of error text. Records errors, resolutions, file changes, research activity, and contributions to session state files.
3. **Stop hook** (`stop.py`): Reads accumulated session state and detects six structural patterns (error_resolution, workaround, config_discovery, iteration, multi_turn_work, post_contribution). Prompts the agent to contribute when a pattern is detected.
4. **User prompt hook** (`user_prompt.py`): On first user turn, injects a reminder to search CommonTrace.

**Inbound triggers (retrieval):**
1. Automatic at session start (context-based search)
2. Automatic on Bash errors (error-based search, with 30-second cooldown)
3. Agent-initiated via MCP tools (`search_traces`)

### OpenClaw: When Knowledge is Stored

**Inbound triggers (storage):**
1. **Agent writes** -- the agent decides when to write to memory files during normal conversation
2. **Pre-compaction memory flush** (`memory-flush.ts`): Triggered automatically when session token usage crosses `contextWindow - reserveTokensFloor - softThresholdTokens`. Runs once per compaction cycle.
3. **Session-memory hook** (`handler.ts`): Triggered by `/new` command, saves previous session content to a dated memory file

**Inbound triggers (retrieval):**
1. **Session start sync** (`sync.onSessionStart: true`): Index is synced when a new session begins
2. **On-search sync** (`sync.onSearch: true`): Dirty index is synced when a search is initiated
3. **File watcher**: Chokidar watches memory files, debounced at 1.5s, marks index dirty
4. **Interval sync**: Configurable periodic sync
5. **Agent-initiated**: Via `memory_search` tool, described as "Mandatory recall step: semantically search MEMORY.md + memory/*.md before answering questions about prior work, decisions, dates, people, preferences, or todos"
6. **Session delta thresholds**: For session transcript indexing, sync triggers after 100KB or 50 JSONL lines of changes

**Key difference**: CommonTrace has a sophisticated hook-based pattern detection system that structurally identifies when a coding problem has been solved (error->fix->verify cycle) and prompts contribution. OpenClaw relies on the agent's own judgment about what to remember, plus an automated pre-compaction safety net. CommonTrace's triggers are event-driven (tool failures, Bash errors); OpenClaw's triggers are threshold-driven (token count, file changes).

---

## 6. Context Injection

### CommonTrace

Context injection happens through two mechanisms:

1. **Session start injection**: The `session_start.py` hook outputs a JSON object with `hookSpecificOutput.additionalContext` containing formatted search results or a generic reminder. This is injected into the session start event by the Claude Code hook system.

2. **Post-tool-use injection**: When an error triggers a CommonTrace search that returns results, `post_tool_use.py` injects them as `additionalContext` in the PostToolUse event.

3. **First-turn nudge**: `user_prompt.py` injects a brief reminder on the first user message: "search CommonTrace (search_traces) before solving coding problems."

4. **SKILL.md** (`/tmp/ct-skill/skills/commontrace/SKILL.md`): Loaded as behavioral guidance for the skill, instructing the agent when to search and contribute.

The injection is **push-based** (hooks push context into the agent's working context) and **pull-based** (agent calls MCP tools to search).

### OpenClaw

Context injection uses multiple mechanisms:

1. **Bootstrap files**: `SOUL.md` and `MEMORY.md` are loaded at workspace boot (`boot-md` hook, `/home/bitnami/openclaw/src/hooks/bundled/boot-md/handler.ts`). SOUL.md defines the agent's identity and behavioral anchor. MEMORY.md contains curated long-term memory.

2. **Memory search tool**: `memory_search` (`/home/bitnami/openclaw/src/agents/tools/memory-tool.ts`) is described as a "Mandatory recall step" -- the tool description tells the agent it must use this before answering questions about prior work. Returns snippets with path, line numbers, source, and optional citations.

3. **Memory get tool**: `memory_get` allows targeted retrieval of specific memory file content after an initial search.

4. **Pre-compaction flush**: Injects a system prompt + user prompt telling the agent to write durable memories before compaction.

5. **Session transcript indexing** (experimental): Past conversation transcripts are indexed and searchable, so the agent can recall previous conversations.

**Key difference**: OpenClaw has a rich, layered context injection system -- identity (SOUL.md), curated facts (MEMORY.md), daily logs (memory/YYYY-MM-DD.md), and searchable session transcripts. CommonTrace injects discrete problem/solution pairs. OpenClaw's memory is deeply personal and continuous; CommonTrace's is communal and episodic.

---

## 7. Forgetting/Pruning

### CommonTrace

CommonTrace has limited forgetting mechanisms:

- **Flagging**: `is_flagged = True` excludes a trace from search results, but does not delete it
- **Staleness**: `is_stale = True` marks traces whose referenced library versions are behind PyPI current major.minor, but stale traces are not excluded from search
- **No TTL or automatic pruning**: Traces persist indefinitely. There is no temporal decay in search ranking.
- **No automatic deletion**: The data model has no `deleted_at` or soft-delete column

### OpenClaw

OpenClaw has more sophisticated forgetting:

- **Temporal decay** (`/home/bitnami/openclaw/src/memory/temporal-decay.ts`): Exponential decay with configurable half-life (default 30 days). After 180 days, a memory's score is reduced to ~1.6% of its original value. Evergreen files are exempt.
- **Stale file cleanup** (`sync-stale.ts`): When files are deleted from disk, their chunks, vectors, and FTS entries are purged from the SQLite index.
- **Hash-based reindexing**: If a file's content hash changes, the old chunks are replaced with new ones.
- **Compaction-driven flush**: The pre-compaction memory flush is explicitly designed to preserve important information before the LLM context window is compacted (information that stays only in context is lost).
- **Manual deletion**: Users can simply delete memory files from disk.

**Key difference**: CommonTrace never forgets (by design -- it is a shared knowledge base that accumulates). OpenClaw has natural forgetting through temporal decay, file deletion, and the compaction lifecycle. This reflects their different purposes: CommonTrace preserves community knowledge; OpenClaw prioritizes recency for personal context.

---

## 8. Gaps and Limitations

### CommonTrace

1. **No temporal awareness in search ranking**: The trust-weighted re-ranking formula `(1 - distance) * log1p(trust_score + 1)` has no time component. A 3-year-old trace with high trust can permanently outrank a newer, more accurate one. The staleness check only covers PyPI library versions, not general knowledge decay.

2. **Embedding model lock-in**: The search filter `WHERE embedding_model_id = 'text-embedding-3-small'` means any future model migration requires re-embedding the entire corpus. The embedding worker has drift detection but no migration path.

3. **No negative search signal**: If a user searches, gets results, and they are unhelpful, there is no feedback mechanism. Votes happen on individual traces, not on search quality.

4. **Single-vector embedding**: The entire trace (title + context + solution) is embedded as a single 1536-dim vector. There is no multi-vector approach that could independently match context vs. solution.

5. **No trace versioning**: Amendments create separate rows but do not replace the original trace's content. There is no mechanism to supersede outdated traces.

6. **Hook detection is limited to structural signals**: The stop hook only detects patterns when there are explicit error/resolution cycles or file changes. Knowledge gained through pure conversation (e.g., learning an API pattern through reading docs) is invisible to the hooks.

7. **Scaling wall**: As noted in the project memory, PostgreSQL HNSW index performance degrades past ~100K traces due to RAM requirements.

8. **No deduplication at submission**: Two agents can submit identical traces. There is no semantic dedup check during contribution.

9. **Cold start problem**: New traces start at trust_score=0 with pending status. The validation threshold creates a chicken-and-egg problem: traces need votes to be validated, but agents may skip pending traces.

### OpenClaw

1. **No community knowledge sharing**: All memory is personal to a single agent/user. There is no mechanism to share learned knowledge across users or agent instances.

2. **No structured knowledge representation**: Freeform Markdown means the system cannot distinguish between a solved problem, a preference, a fact, and a to-do. Everything is an undifferentiated chunk of text.

3. **Quality depends entirely on the LLM's writing**: If the agent writes poor or inaccurate memories, there is no correction mechanism beyond the user manually editing files.

4. **Pre-compaction flush is best-effort**: The memory flush prompt says "usually NO_REPLY is correct" -- the LLM may choose not to save important context, leading to information loss during compaction.

5. **Session memory hook only triggers on /new**: If a session ends without the user issuing `/new` (browser closed, timeout, etc.), the session content is only preserved if it was already written to memory files or indexed as a session transcript.

6. **No cross-session coherence**: Each session starts fresh (as stated in SOUL.md). The agent must re-discover context from memory files every time. There is no mechanism for maintaining an ongoing understanding that evolves across sessions beyond what is written to disk.

7. **Chunk boundary artifacts**: With 400-token chunks and 80-token overlap, a piece of knowledge that spans a chunk boundary may be partially matched, giving inaccurate results.

8. **No provenance tracking**: Unlike CommonTrace (which tracks contributor, agent model, timestamps), OpenClaw memory chunks have no provenance metadata beyond file path and modification time. There is no way to know which conversation or what evidence produced a particular memory.

9. **FTS-only fallback is weak**: When no embedding provider is available, the system falls back to keyword extraction and FTS matching. The stop-word lists are hardcoded (English + Chinese only), and the tokenizer uses simple character-based splitting for CJK text rather than proper word segmentation.

10. **No truth verification**: If the agent writes something factually wrong to memory, it will be faithfully recalled and cited in future sessions with no mechanism to flag or correct it beyond manual user intervention.

---

## Summary Table

| Dimension | CommonTrace | OpenClaw |
|-----------|-------------|----------|
| **Scope** | Community (multi-agent, multi-user) | Personal (single agent/user) |
| **Knowledge unit** | Trace (title/context/solution) | Chunk (~400 tokens of Markdown) |
| **Storage** | PostgreSQL + pgvector | SQLite + sqlite-vec + FTS5 |
| **Embedding** | OpenAI text-embedding-3-small, 1536-dim | Configurable (OpenAI/Gemini/Voyage/local GGUF) |
| **Encoding trigger** | Structural pattern detection (error->fix->verify) | Agent judgment + pre-compaction flush + /new hook |
| **Search** | Cosine ANN + trust re-ranking | Hybrid vector+BM25 + temporal decay + MMR |
| **Quality control** | Votes, Wilson scores, domain reputation, PII scan | Manual curation, temporal decay |
| **Forgetting** | None (accumulates indefinitely) | Temporal decay, file deletion, compaction |
| **Context injection** | Hook-injected context + MCP tools | Bootstrap files + memory_search/memory_get tools |
| **Identity anchor** | SKILL.md (behavioral guidance) | SOUL.md (personality + philosophy) |
| **Tag/categorization** | Explicit normalized tags with AND-filter search | Implicit (file path, date in filename) |
| **Provenance** | contributor_id, agent_model, timestamps | File path, mtime only |
