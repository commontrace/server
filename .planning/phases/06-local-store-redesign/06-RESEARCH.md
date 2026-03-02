# Phase 6: Local Store Redesign - Research

**Researched:** 2026-03-02
**Domain:** SQLite schema migration, Python hook architecture, local store simplification
**Confidence:** HIGH — based on direct codebase analysis of current files

---

## Summary

Phase 6 replaces the current 10-table `local_store.py` with a 5-table working memory cache. The current implementation duplicates the remote API's intelligence (BM25 search, temperature classification, decay computation, spreading activation, Jaro-Winkler deduplication) in SQLite at smaller scale and lower quality. The redesign deletes all of this and keeps only what a working memory layer actually needs: project identity, session metadata, trace pointers, trigger feedback, and error signatures.

The current file is 1,440 lines. The target is approximately 300-400 lines. Every function in the current file has been mapped: 12 functions survive in simplified form, 18 functions are deleted entirely, and 3 hook callers require updates to stop calling deleted functions.

The most critical constraint is safe migration of existing `~/.commontrace/local.db` databases. Users have accumulated session history and error signatures. The migration must preserve `projects`, `sessions`, `trigger_feedback`, and `error_signatures` data while discarding `entities`, `events`, `local_knowledge`, `discovered_knowledge`, `session_insights`, and `error_resolutions`. The `PRAGMA user_version` gate is the correct pattern — without it, the code silently runs against old schemas.

**Primary recommendation:** Implement numbered migrations with `PRAGMA user_version = 2` gate. Delete all 18 functions listed in the deletion map below. Rewrite the 4 hook files to remove calls to deleted functions. Enable WAL mode. The result is a ~300-line local_store.py with no algorithmic complexity.

---

## Current State: Complete Code Map

### Current Schema (10 tables)

```
local.db (current)
├── projects          (keep, rename columns)
├── sessions          (keep, add 2 columns)
├── entities          (DELETE — data becomes inline in projects)
├── events            (DELETE — JSONL stays ephemeral)
├── error_signatures  (keep, simplify)
├── trigger_feedback  (keep as-is)
├── local_knowledge   (DELETE — replace with trace_cache)
├── error_resolutions (DELETE — no replacement needed)
├── discovered_knowledge (DELETE — merge into trace_cache)
└── session_insights  (DELETE — fold into sessions table)
```

**Tables deleted:** entities, events, local_knowledge, error_resolutions, discovered_knowledge, session_insights (6 tables removed)
**Tables kept:** projects (modified), sessions (modified), error_signatures (simplified), trigger_feedback (unchanged)
**Tables added:** trace_cache (new — merges local_knowledge + discovered_knowledge as pointers)

### Current Column Details

**projects** (current columns):
- `id`, `path`, `primary_language`, `primary_framework`, `first_seen_at`, `last_seen_at`, `session_count`
- Change: rename `primary_language` → `language`, `primary_framework` → `framework` (via migration, not ALTER)

**sessions** (current columns):
- `id`, `project_id`, `started_at`, `ended_at`, `error_count`, `resolution_count`, `contribution_count`
- Add: `top_pattern TEXT`, `importance_score REAL DEFAULT 0.0` (from session_insights)

**error_signatures** (current columns):
- `id`, `project_id`, `session_id`, `signature`, `raw_tail`, `created_at`
- Change: drop `session_id` and `raw_tail` columns (SQLite requires table rebuild)

**trigger_feedback** (current columns):
- `id`, `session_id`, `trigger_name`, `triggered_at`, `trace_consumed_id`, `consumed_at`
- No change needed — keep exactly as-is

---

## Current Functions: Delete vs Keep Map

### Functions to DELETE (18 total)

These functions implement the duplicate encyclopedia logic. Every caller must be updated.

| Function | Lines (approx) | Why Deleted | Current Callers |
|----------|----------------|-------------|-----------------|
| `jaro_winkler()` | 162-225 | Entity dedup — entities table gone | `record_entity()` (internal) |
| `record_entity()` | 288-338 | entities table deleted | `stop.py` line 657 |
| `migrate_jsonl_events()` | 341-401 | events table deleted | `stop.py` line 629, `user_prompt.py` line 113 |
| `get_known_languages()` | 449-457 | entities table deleted | `post_tool_use.py` line 579 |
| `record_error_signature()` | 462-473 | error_signatures simplified | `post_tool_use.py` line 472 |
| `find_similar_errors()` | 476-523 | error_signatures simplified | `post_tool_use.py` line 525 |
| `record_local_knowledge()` | 603-636 | local_knowledge deleted | `post_tool_use.py` line 1077 |
| `supersede_local_knowledge()` | 639-666 | local_knowledge deleted | `post_tool_use.py` lines 1085, 1095 |
| `_tokenize()` | 669-671 | BM25 support — deleted | `search_local_bm25()`, `search_discovered_bm25()` |
| `_jaccard_tokens()` | 674-678 | BM25/MMR support — deleted | `search_local_bm25()`, `spread_activation()` |
| `search_local_bm25()` | 681-775 | No local search | `post_tool_use.py` line 357-364, `post_tool_use.py` line 1090 |
| `cache_discovered_trace()` | 778-806 | discovered_knowledge deleted; replace with `cache_trace_pointer()` | `post_tool_use.py` lines 962, 996 |
| `mark_trace_used()` | 809-817 | discovered_knowledge deleted; replace with `mark_trace_used_v2()` | `post_tool_use.py` line 954 |
| `record_trace_vote()` | 820-835 | discovered_knowledge deleted; add `vote` to trace_cache | `post_tool_use.py` line 1021 |
| `search_discovered_bm25()` | 838-922 | No local search | `post_tool_use.py` lines 386, 503, `session_start.py` line 297 |
| `record_error_resolution()` | 925-960 | error_resolutions table deleted | `stop.py` line 680 |
| `find_error_resolution()` | 963-1000 | error_resolutions table deleted | `post_tool_use.py` line 476 |
| `record_session_insight()` | 1003-1014 | session_insights deleted; data folds into sessions | `stop.py` line 688 |
| `get_recent_insights()` | 1017-1035 | session_insights deleted | `stop.py` line 544 |
| `HALF_LIFE_RULES` dict + constants | 1043-1074 | Temperature system deleted | `compute_half_life()` |
| `TEMPERATURE_MULTIPLIERS` dict | 1054-1056 | Temperature system deleted | `get_project_knowledge_ranked()` |
| `EVERGREEN_TAGS/PATTERNS` sets | 1060-1066 | Temperature system deleted | `is_evergreen_knowledge()` |
| `PATTERN_HALF_LIFE_OVERRIDES` dict | 1070-1074 | Temperature system deleted | `compute_half_life()` |
| `compute_half_life()` | 1077-1090 | Temperature system deleted | `record_local_knowledge()`, `consolidate_local_memory()` |
| `is_evergreen_knowledge()` | 1093-1105 | Temperature system deleted | `record_local_knowledge()`, `consolidate_local_memory()` |
| `classify_local_temperature()` | 1108-1148 | Temperature system deleted | `consolidate_local_memory()` |
| `compute_local_decay()` | 1151-1184 | Decay system deleted | `search_local_bm25()`, `classify_local_temperature()`, `get_project_knowledge_ranked()` |
| `boost_local_recall()` | 1187-1197 | local_knowledge deleted | `post_tool_use.py` lines 369, 482 |
| `spread_activation()` | 1200-1284 | No local spreading activation | `post_tool_use.py` lines 370, 483 |
| `get_project_knowledge_ranked()` | 1287-1362 | local_knowledge deleted | `session_start.py` line 282 |
| `consolidate_local_memory()` | 1365-1439 | Replaced by `prune_stale_cache()` | `stop.py` line 691 |

**Also delete:** `JARO_WINKLER_THRESHOLD` constant (line 21), `import math` (used only by BM25/decay functions)

### Functions to KEEP (12 total, some with modifications)

| Function | Lines (approx) | Keep/Modify | Notes |
|----------|----------------|-------------|-------|
| `_get_conn()` | 146-159 | **Rewrite** | Add WAL mode, `PRAGMA user_version` migration gate, remove `_COLUMN_MIGRATIONS` loop |
| `ensure_project()` | 228-257 | **Keep + simplify** | Use `ON CONFLICT DO UPDATE`, change column names `primary_language` → `language` |
| `start_session()` | 260-268 | **Keep as-is** | No change needed |
| `end_session()` | 271-285 | **Modify** | Add `top_pattern` and `importance_score` params |
| `get_project_context()` | 404-446 | **Rewrite** | Remove entities query — read directly from projects table; return compact dict |
| `record_error_signature()` | NEW | **New simplified version** | Simplified: just `(project_id, signature, created_at)` — no session_id, no raw_tail |
| `record_trigger()` | 528-538 | **Keep as-is** | No change |
| `record_trace_consumed()` | 541-569 | **Keep as-is** | No change |
| `get_trigger_effectiveness()` | 572-598 | **Keep as-is** | No change |

### New Functions to ADD (5 total)

| Function | Purpose | Called From |
|----------|---------|-------------|
| `cache_trace_pointer(conn, trace_id, project_id, title, source)` | Replace `cache_discovered_trace()` and `record_local_knowledge()` — stores pointer only | `post_tool_use.py` handle_get_trace, handle_search_results, handle_contribution |
| `mark_trace_used_v2(conn, trace_id, project_id)` | Replace `mark_trace_used()` — operates on `trace_cache` | `post_tool_use.py` handle_get_trace |
| `record_trace_vote_v2(conn, trace_id, vote_type)` | Replace `record_trace_vote()` — operates on `trace_cache` | `post_tool_use.py` handle_vote |
| `get_cached_traces(conn, project_id, limit)` | Replace `get_project_knowledge_ranked()` — simple recency sort | `session_start.py` contribution_recall section |
| `prune_stale_cache(conn)` | Replace `consolidate_local_memory()` — TTL pruning only | `stop.py` _persist_session |

---

## Target Schema (5 tables)

```sql
-- ~/.commontrace/local.db schema version 2
-- Working memory cache. PostgreSQL API is source of truth.

PRAGMA user_version = 2;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    language TEXT,
    framework TEXT,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    session_count INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    started_at REAL NOT NULL,
    ended_at REAL,
    error_count INTEGER DEFAULT 0,
    resolution_count INTEGER DEFAULT 0,
    contribution_count INTEGER DEFAULT 0,
    top_pattern TEXT,
    importance_score REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

CREATE TABLE IF NOT EXISTS trace_cache (
    trace_id TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'search',  -- 'search' | 'contributed'
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    use_count INTEGER DEFAULT 0,
    vote TEXT,                               -- 'up' | 'down' | NULL
    PRIMARY KEY (trace_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_trace_cache_project ON trace_cache(project_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS trigger_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    trigger_name TEXT NOT NULL,
    triggered_at REAL NOT NULL,
    trace_consumed_id TEXT,
    consumed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_trigger_feedback_session ON trigger_feedback(session_id);

CREATE TABLE IF NOT EXISTS error_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    signature TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_sig_project ON error_signatures(project_id, created_at DESC);
```

---

## Migration Path: v1 → v2

### The Core Challenge

SQLite does not support `ALTER TABLE ... DROP COLUMN` reliably before SQLite 3.35.0 (2021) and does not support `ALTER TABLE ... RENAME COLUMN` before 3.25.0 (2018). The macOS system SQLite may be older. The safest approach for column drops/renames is the table-rebuild pattern: create new table, copy, drop old, rename new.

### PRAGMA user_version Strategy

```python
CURRENT_SCHEMA_VERSION = 2

def _apply_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        _migrate_to_v2(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
```

### What _migrate_to_v2() Does

**Step 1: Rebuild `projects` table** (rename `primary_language`/`primary_framework` → `language`/`framework`)
```python
conn.executescript("""
    BEGIN EXCLUSIVE;
    CREATE TABLE projects_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        language TEXT,
        framework TEXT,
        first_seen_at REAL NOT NULL,
        last_seen_at REAL NOT NULL,
        session_count INTEGER DEFAULT 1
    );
    INSERT INTO projects_v2
        SELECT id, path, primary_language, primary_framework,
               first_seen_at, last_seen_at, session_count
        FROM projects;
    DROP TABLE projects;
    ALTER TABLE projects_v2 RENAME TO projects;
    CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);
    COMMIT;
""")
```

**Step 2: Add columns to `sessions`** (additive — safe with ALTER TABLE)
```python
for col_def in [
    "top_pattern TEXT",
    "importance_score REAL DEFAULT 0.0",
]:
    try:
        conn.execute(f"ALTER TABLE sessions ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass  # Already exists
```

**Step 3: Migrate `error_signatures`** (drop `session_id` and `raw_tail` — requires table rebuild)
```python
# Only do this if the table exists with old schema
existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(error_signatures)")}
if "raw_tail" in existing_cols or "session_id" in existing_cols:
    conn.executescript("""
        BEGIN EXCLUSIVE;
        CREATE TABLE error_signatures_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            signature TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        INSERT INTO error_signatures_v2 (id, project_id, signature, created_at)
            SELECT id, project_id, signature, created_at
            FROM error_signatures;
        DROP TABLE error_signatures;
        ALTER TABLE error_signatures_v2 RENAME TO error_signatures;
        CREATE INDEX IF NOT EXISTS idx_error_sig_project
            ON error_signatures(project_id, created_at DESC);
        COMMIT;
    """)
```

**Step 4: Drop obsolete tables** (order matters — FK constraints)
```python
obsolete = [
    "session_insights",   # No FK deps
    "local_knowledge",    # No FK deps on other obsolete tables
    "discovered_knowledge",  # No FK deps
    "error_resolutions",  # No FK deps
    "events",             # FK on sessions — drop events first
    "entities",           # FK on projects
]
for table in obsolete:
    conn.execute(f"DROP TABLE IF EXISTS {table}")
conn.commit()
```

**Step 5: Create new `trace_cache` table**
```python
conn.executescript("""
    CREATE TABLE IF NOT EXISTS trace_cache (
        trace_id TEXT NOT NULL,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'search',
        first_seen_at REAL NOT NULL,
        last_seen_at REAL NOT NULL,
        use_count INTEGER DEFAULT 0,
        vote TEXT,
        PRIMARY KEY (trace_id, project_id)
    );
    CREATE INDEX IF NOT EXISTS idx_trace_cache_project
        ON trace_cache(project_id, last_seen_at DESC);
""")
```

### Backup Before Migration

```python
def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Backup if migration needed
    current_ver = 0
    if DB_PATH.exists():
        try:
            tmp = sqlite3.connect(str(DB_PATH))
            current_ver = tmp.execute("PRAGMA user_version").fetchone()[0]
            tmp.close()
        except Exception:
            pass
        if current_ver < CURRENT_SCHEMA_VERSION:
            import shutil
            backup = Path(str(DB_PATH) + ".bak")
            try:
                shutil.copy2(str(DB_PATH), str(backup))
            except OSError:
                pass

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    conn.executescript(_SCHEMA)  # CREATE IF NOT EXISTS for all 5 tables
    return conn
```

---

## Hook Changes Required

### session_start.py (4 changes)

**Currently imports from local_store:**
```python
from local_store import (
    _get_conn, ensure_project, start_session, get_project_context,
    get_project_knowledge_ranked, get_trigger_effectiveness,
    search_discovered_bm25,
)
```

**After redesign — import changes:**
```python
from local_store import (
    _get_conn, ensure_project, start_session, get_project_context,
    get_cached_traces, get_trigger_effectiveness,
    # REMOVED: get_project_knowledge_ranked, search_discovered_bm25
)
```

**Contribution recall section** (lines 282-307) — rewrite:
- Remove: `get_project_knowledge_ranked()` call and FROZEN filter
- Remove: `search_discovered_bm25()` call
- Add: `get_cached_traces(conn, project_id, limit=3)` — returns (trace_id, title, use_count)
- New output: simple "Previously useful traces: {titles}" without temperature/recall framing

### stop.py (4 changes)

**`_persist_session()` function** — currently imports:
```python
from local_store import (
    _get_conn, migrate_jsonl_events, end_session, record_entity,
    record_error_resolution, record_session_insight,
    consolidate_local_memory,
)
```

**After redesign:**
```python
from local_store import (
    _get_conn, end_session, prune_stale_cache,
    # REMOVED: migrate_jsonl_events, record_entity, record_error_resolution,
    # REMOVED: record_session_insight, consolidate_local_memory
)
```

**Changes inside `_persist_session()`:**
- Remove: `migrate_jsonl_events(conn, session_id, state_dir)` call
- Remove: entire `record_entity()` loop (lines 647-657)
- Remove: entire `record_error_resolution()` block (lines 659-681)
- Remove: `record_session_insight()` call (lines 684-688)
- Change: `end_session()` call to pass `top_pattern` and `importance_score`
- Change: `consolidate_local_memory(conn)` → `prune_stale_cache(conn)`

**`_build_prompt()` function** (line 541-544) — `get_recent_insights` call:
- Remove entire insights_hint block (lines 538-554)
- Remove import: `from local_store import _get_conn, get_recent_insights`

**`_report_trigger_stats()` function** (line 701) — no changes needed (uses `get_trigger_effectiveness` which is kept)

**`compute_importance()` function** (line 279-289) — `generation_effect` detection:
- Remove: `from local_store import _get_conn` + trigger_feedback query (lines 279-289)
- Replace: query against `trigger_feedback` with simple JSONL-based detection (consumed_traces always 0, simplify logic)

### user_prompt.py (1 change)

**`_periodic_flush()` function** (lines 100-116) — delete entirely:
- Remove: `_periodic_flush()` function definition
- Remove: import `from local_store import _get_conn, migrate_jsonl_events`
- Remove: the `if count % FLUSH_INTERVAL == 0` call (lines 143-145)
- Rationale: events table deleted; no JSONL migration needed

### post_tool_use.py (7 changes across 7 handlers)

**Change 1: `handle_bash_error_with_local_recall()`** (around line 356-394)
- Remove: `search_local_bm25()`, `boost_local_recall()`, `spread_activation()` calls
- Remove: `search_discovered_bm25()` call
- Keep: `record_trigger()` call (trigger_feedback table unchanged)
- The trigger fires but no longer does local search; relies on API search for recall

**Change 2: `_record_trigger_safe()`** (line 413-422) — keep as-is (uses `record_trigger`)

**Change 3: `handle_bash_error()`** (around line 459-535)
- Remove: `record_error_signature()`, `find_similar_errors()` calls
- Remove: `find_error_resolution()`, `boost_local_recall()`, `spread_activation()` calls
- Remove: `search_discovered_bm25()` call
- Add: simplified `record_error_signature(conn, project_id, sig)` call (new simplified version)
- Keep: `record_trigger()` call

**Change 4: domain_entry handler** (around line 577-584)
- Remove: `get_known_languages()` call
- Replace: check if project has `language` field in projects table (or track separately in JSONL)
- The trigger still fires via `_record_trigger_safe()`

**Change 5: `handle_get_trace()`** (around line 946-970)
- Remove: `cache_discovered_trace()`, `mark_trace_used()` calls
- Add: `cache_trace_pointer(conn, trace_id, project_id, title, source='search')` call
- Add: `mark_trace_used_v2(conn, trace_id, project_id)` call

**Change 6: `handle_search_results()`** (around line 989-1003)
- Remove: `cache_discovered_trace()` call (stores full content)
- Add: `cache_trace_pointer(conn, trace_id, project_id, title, source='search')` call (pointer only)

**Change 7: `handle_vote()`** (around line 1019-1023)
- Remove: `record_trace_vote()` call (operates on discovered_knowledge)
- Add: `record_trace_vote_v2(conn, trace_id, vote_type)` call (operates on trace_cache)

**Change 8: `handle_contribution()`** (around line 1054-1100)
- Remove: `record_local_knowledge()`, `supersede_local_knowledge()`, `search_local_bm25()` calls
- Add: `cache_trace_pointer(conn, trace_id, project_id, title, source='contributed')` call

**Change 9: `handle_amendment()`** (around line 1114-1133)
- Remove: `UPDATE local_knowledge` query
- Remove: `UPDATE discovered_knowledge` query
- No replacement needed — trace_cache stores only title, not solution content

---

## Architecture Patterns

### Pattern 1: Pointer Cache Only

The trace_cache stores `trace_id + title + source + timestamps + use_count + vote`. No `context_text`, no `solution_text`. When the agent needs full content it calls `search_traces` via MCP. The local store only answers "have I seen this before?" not "what was the solution?".

### Pattern 2: WAL Mode for Hook Concurrency

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-8000")
conn.execute("PRAGMA temp_store=MEMORY")
```

WAL mode is persistent once set — subsequent connections benefit automatically. Enables concurrent readers without write lock errors when multiple hook processes run simultaneously.

### Pattern 3: Session-End Pruning Only

```python
def prune_stale_cache(conn: sqlite3.Connection) -> None:
    """Run once at session exit. Never block session start."""
    now = time.time()
    conn.execute("DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
                 (now - 90 * 86400,))
    conn.execute("DELETE FROM trace_cache WHERE use_count = 0 AND first_seen_at < ?",
                 (now - 30 * 86400,))
    conn.execute("DELETE FROM trace_cache WHERE vote = 'down' AND last_seen_at < ?",
                 (now - 7 * 86400,))
    conn.execute("DELETE FROM trigger_feedback WHERE triggered_at < ?",
                 (now - 60 * 86400,))
    conn.execute("DELETE FROM error_signatures WHERE created_at < ?",
                 (now - 90 * 86400,))
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    conn.commit()
```

### Pattern 4: Upsert with ON CONFLICT

For all write operations, use SQLite's native conflict resolution:

```python
def cache_trace_pointer(conn, trace_id, project_id, title, source='search'):
    now = time.time()
    conn.execute(
        "INSERT INTO trace_cache (trace_id, project_id, title, source, "
        "first_seen_at, last_seen_at, use_count) VALUES (?, ?, ?, ?, ?, ?, 0) "
        "ON CONFLICT(trace_id, project_id) DO UPDATE SET "
        "last_seen_at = excluded.last_seen_at, title = excluded.title",
        (trace_id, project_id, title[:120], source, now, now)
    )
    conn.commit()
```

### Pattern 5: Simplified get_project_context()

The new version reads only from the `projects` table (no entities join):

```python
def get_project_context(conn, cwd):
    row = conn.execute(
        "SELECT id, language, framework, session_count FROM projects WHERE path = ?",
        (cwd,)
    ).fetchone()
    if not row:
        return None
    ctx = {"project_id": row["id"], "session_count": row["session_count"]}
    if row["language"]:
        ctx["language"] = row["language"]
    if row["framework"]:
        ctx["framework"] = row["framework"]
    return ctx
```

### Pattern 6: Simplified end_session()

```python
def end_session(conn, session_id, stats, top_pattern=None, importance_score=0.0):
    conn.execute(
        "UPDATE sessions SET ended_at = ?, error_count = ?, "
        "resolution_count = ?, contribution_count = ?, "
        "top_pattern = ?, importance_score = ? WHERE id = ?",
        (time.time(), stats.get("error_count", 0),
         stats.get("resolution_count", 0), stats.get("contribution_count", 0),
         top_pattern, importance_score, session_id)
    )
    conn.commit()
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trace search/ranking | BM25, decay scoring in SQLite | Remote API (pgvector) | API has embeddings, trust scores, convergence — SQLite has none of this |
| Entity deduplication | Jaro-Winkler similarity | Direct field on projects table | Language/framework are known enumerations; fuzzy match adds complexity |
| Temperature classification | HOT/WARM/COOL/COLD/FROZEN | Delete entirely | The API maintains authoritative memory_temperature; local cache is read-only |
| Spreading activation | Multi-hop BFS over tag overlap | Delete entirely | Only meaningful over large corpus; local corpus is always small |
| Knowledge bi-temporality | valid_from/valid_to on local_knowledge | Delete entirely | Source of truth is remote; no need for local amendment history |
| JSONL→SQLite migration | migrate_jsonl_events() | Keep JSONL as JSONL | JSONL bridge files are ephemeral; the events table grows unboundedly |

---

## Common Pitfalls

### Pitfall 1: SQLite Migration Without PRAGMA user_version Gate
**What goes wrong:** Current `_get_conn()` runs `CREATE TABLE IF NOT EXISTS` on every connection with no version tracking. If v2 runs against a v1 database, `DROP TABLE entities` happens immediately and permanently, losing all entity data. The user sees nothing.
**Prevention:** Always check `PRAGMA user_version` before running DDL. Backup the database file before any migration that will change user_version.
**Warning signs:** If `_get_conn()` runs `DROP TABLE` without first checking `user_version`, migration is unsafe.

### Pitfall 2: Column Rename via ALTER TABLE
**What goes wrong:** SQLite's `ALTER TABLE ... RENAME COLUMN` requires SQLite >= 3.25.0. macOS Monterey ships 3.37; macOS Ventura ships 3.39. But older systems may have 3.22. Using `RENAME COLUMN` crashes `_get_conn()` on those systems.
**Prevention:** Use the table-rebuild pattern (CREATE NEW, INSERT FROM OLD, DROP OLD, RENAME NEW). Confirmed safe across all SQLite versions.
**Code:** `BEGIN EXCLUSIVE` transaction wraps the entire table rebuild.

### Pitfall 3: Deleting discovered_knowledge Before Updating All Callers
**What goes wrong:** post_tool_use.py calls `cache_discovered_trace()` (line 962, 996) and `mark_trace_used()` (line 954). If the table is dropped but the function calls remain, `_get_conn()` succeeds but the INSERT fails silently (swallowed by `except Exception: pass`).
**Prevention:** Update all 9 hook call sites in parallel with the schema change. Do not merge a schema-only change without the corresponding hook updates.

### Pitfall 4: Forgetting to Remove the Periodic JSONL Flush
**What goes wrong:** `user_prompt.py`'s `_periodic_flush()` calls `migrate_jsonl_events()` which inserts into the `events` table. After the `events` table is dropped, this silently fails every 10 turns.
**Prevention:** Delete `_periodic_flush()` entirely from `user_prompt.py`. The events table is gone; there is nothing to flush to.

### Pitfall 5: generation_effect Pattern Breaks Without trigger_feedback Query
**What goes wrong:** `stop.py`'s `compute_importance()` queries `trigger_feedback` to count `consumed_traces` (lines 279-289). This specific query is retained in the redesign (`trigger_feedback` table is kept). But the import changes. If the import is deleted carelessly, `consumed_traces` stays at 0 and generation_effect fires incorrectly.
**Prevention:** The `from local_store import _get_conn` import at stop.py line 279 is still needed. Keep this specific import block. Only delete the `migrate_jsonl_events`, `record_entity`, `record_error_resolution`, `record_session_insight`, `consolidate_local_memory` imports.

### Pitfall 6: handle_amendment() Leaves Dead SQL
**What goes wrong:** `handle_amendment()` in post_tool_use.py (lines 1119-1130) runs `UPDATE local_knowledge SET solution_snippet...` and `UPDATE discovered_knowledge SET solution_snippet...`. After those tables are dropped, these queries silently no-op (SQLite UPDATE against a non-existent table raises OperationalError, caught by try/except). The function still exists and looks functional but does nothing.
**Prevention:** Rewrite `handle_amendment()` to either remove it or update the trace_cache title field (the only field we store). Since trace_cache does not store solution content, amendment does not need local storage updates.

### Pitfall 7: WAL Mode Not Set on First Connection
**What goes wrong:** WAL mode is persistent — but only after the first connection that sets it. If `_get_conn()` runs migrations inside a DELETE-mode connection and then a second connection opens in WAL mode, there may be journal file conflicts during migration.
**Prevention:** Set `PRAGMA journal_mode=WAL` as the first statement after `sqlite3.connect()`, before running any migrations. WAL mode conversion is safe on an existing database.

---

## Code Examples

### New _get_conn() with Migration Gate

```python
# Source: PITFALLS.md migration strategy + WORKING-MEMORY.md Pattern 4

CURRENT_SCHEMA_VERSION = 2

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Backup before migration if needed
    current_ver = 0
    if DB_PATH.exists():
        try:
            tmp = sqlite3.connect(str(DB_PATH))
            current_ver = tmp.execute("PRAGMA user_version").fetchone()[0]
            tmp.close()
        except Exception:
            pass
        if current_ver < CURRENT_SCHEMA_VERSION:
            import shutil
            try:
                shutil.copy2(str(DB_PATH), str(DB_PATH) + ".bak")
            except OSError:
                pass

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    conn.executescript(_SCHEMA)
    return conn
```

### New cache_trace_pointer()

```python
def cache_trace_pointer(conn: sqlite3.Connection, trace_id: str,
                        project_id: int | None, title: str,
                        source: str = 'search') -> None:
    """Store a trace pointer (ID + title only). No content stored locally."""
    now = time.time()
    conn.execute(
        "INSERT INTO trace_cache (trace_id, project_id, title, source, "
        "first_seen_at, last_seen_at, use_count) VALUES (?, ?, ?, ?, ?, ?, 0) "
        "ON CONFLICT(trace_id, project_id) DO UPDATE SET "
        "last_seen_at = excluded.last_seen_at, title = excluded.title",
        (trace_id, project_id, title[:120], source, now, now)
    )
    conn.commit()
```

### New get_cached_traces() (replaces get_project_knowledge_ranked)

```python
def get_cached_traces(conn: sqlite3.Connection, project_id: int,
                      limit: int = 3) -> list[dict]:
    """Return recently used trace pointers for session-start recall.

    Only returns traces with use_count > 0 (actually used, not just cached).
    """
    rows = conn.execute(
        "SELECT trace_id, title, use_count FROM trace_cache "
        "WHERE project_id = ? AND use_count > 0 "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (project_id, limit)
    ).fetchall()
    return [{"trace_id": r["trace_id"], "title": r["title"],
             "use_count": r["use_count"]} for r in rows]
```

### Migration Function

```python
def _apply_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= CURRENT_SCHEMA_VERSION:
        return
    if version < 2:
        _migrate_to_v2(conn)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        conn.commit()


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate from 10-table v1 schema to 5-table v2 schema."""
    # Step 1: Rebuild projects (rename columns)
    # Check if old column names exist
    proj_cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "primary_language" in proj_cols:
        conn.executescript("""
            BEGIN EXCLUSIVE;
            CREATE TABLE IF NOT EXISTS projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                language TEXT,
                framework TEXT,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                session_count INTEGER DEFAULT 1
            );
            INSERT INTO projects_new
                SELECT id, path, primary_language, primary_framework,
                       first_seen_at, last_seen_at, session_count FROM projects;
            DROP TABLE projects;
            ALTER TABLE projects_new RENAME TO projects;
            COMMIT;
        """)

    # Step 2: Add columns to sessions (additive — safe)
    for col_def in ["top_pattern TEXT", "importance_score REAL DEFAULT 0.0"]:
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # Already exists

    # Step 3: Rebuild error_signatures (drop session_id, raw_tail)
    sig_cols = {row[1] for row in conn.execute(
        "PRAGMA table_info(error_signatures)")}
    if "raw_tail" in sig_cols or "session_id" in sig_cols:
        conn.executescript("""
            BEGIN EXCLUSIVE;
            CREATE TABLE IF NOT EXISTS error_signatures_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                signature TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            INSERT INTO error_signatures_new (id, project_id, signature, created_at)
                SELECT id, project_id, signature, created_at
                FROM error_signatures;
            DROP TABLE error_signatures;
            ALTER TABLE error_signatures_new RENAME TO error_signatures;
            COMMIT;
        """)

    # Step 4: Drop obsolete tables (order: deps first)
    for table in [
        "session_insights", "local_knowledge", "discovered_knowledge",
        "error_resolutions", "events", "entities",
    ]:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
```

---

## State of the Art

| Old Approach | New Approach | Why Changed |
|--------------|--------------|-------------|
| BM25 search over local SQLite corpus | API pgvector search | API has embeddings + quality signals SQLite cannot replicate |
| Temperature (HOT/WARM/COOL/COLD/FROZEN) in local.db | Delete entirely | Authoritative temperature lives at API; local cache is display-only |
| Exponential decay (half-life, Ebbinghaus) locally | Delete entirely | Decay is a search-quality concern; local store is a pointer cache |
| Spreading activation (BFS over tag overlap) | Delete entirely | Meaningful only over thousands of traces; local corpus is always small |
| Jaro-Winkler entity deduplication | Direct project columns | Language/framework are enumerations; fuzzy match adds ~60 lines of code for zero benefit |
| JSONL → SQLite migration (migrate_jsonl_events) | JSONL stays ephemeral | SQLite events table grew unboundedly; cross-session analysis not needed |
| `local_knowledge` + `discovered_knowledge` split | Single `trace_cache` | No meaningful distinction between own contributions and discovered traces for recall purposes |
| `session_insights` table with journey_json | `top_pattern` + `importance_score` inline in sessions | Journey JSON was written but never read by any hook |
| `PRAGMA journal_mode=DELETE` | `PRAGMA journal_mode=WAL` | WAL allows concurrent readers without lock errors between hook processes |
| Silent `try/except pass` migration | `PRAGMA user_version` gate + backup | Silent migration corrupted databases on schema changes |

---

## Open Questions

1. **domain_entry trigger after entities deletion**
   - What we know: `get_known_languages()` reads from `entities` table to detect if a language is new to the project
   - What's unclear: After entities is deleted, how does `post_tool_use.py` detect novelty_encounter?
   - Recommendation: Track known languages in a JSONL bridge file (`known_languages.jsonl`) written at session_start from the `projects.language` field. Or simplify: fire `domain_entry` if `projects.language IS NULL` (new project). This is actually simpler and more correct.

2. **error_signatures simplified — does Jaccard still work?**
   - What we know: The simplified `error_signatures` drops `raw_tail`. `find_similar_errors()` uses Jaccard on `signature` field (not raw_tail). `find_error_resolution()` uses Jaccard on `error_resolutions.error_signature`.
   - What's unclear: Post-redesign, do we keep `find_similar_errors()` at all, or delete it with the rest?
   - Recommendation: Delete both `record_error_signature()` (old) and `find_similar_errors()`. Add a simplified `record_error_sig(conn, project_id, signature)` that just inserts. The "recurrence detection" trigger (`error_recurrence` in trigger_feedback) can continue as long as we store signatures. But the local lookup before API search (find_error_resolution) should be deleted.

3. **generation_effect detection via trigger_feedback**
   - What we know: `compute_importance()` in stop.py queries trigger_feedback to count consumed_traces for generation_effect scoring
   - What's unclear: This is the one stop.py function that still needs `_get_conn()` after the refactor
   - Recommendation: Keep this specific query. The trigger_feedback table is unchanged. Just ensure the import is not accidentally removed.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `/tmp/ct-skill/hooks/local_store.py` — complete function-by-function read (1,440 lines)
- Direct codebase analysis: `/tmp/ct-skill/hooks/session_start.py` — all local_store imports mapped
- Direct codebase analysis: `/tmp/ct-skill/hooks/stop.py` — all local_store imports mapped
- Direct codebase analysis: `/tmp/ct-skill/hooks/post_tool_use.py` — all local_store imports mapped (grep-verified)
- Direct codebase analysis: `/tmp/ct-skill/hooks/user_prompt.py` — periodic flush function identified
- `.planning/research/WORKING-MEMORY.md` — target schema, WAL patterns, cache-aside design, context injection budget
- `.planning/research/PITFALLS.md` — migration safety, SQLite version constraints, Jaro-Winkler threshold tuning

### Secondary (MEDIUM confidence)
- SQLite official docs: PRAGMA user_version, WAL mode, ALTER TABLE limitations
- WORKING-MEMORY.md sources: SQLite WAL documentation, Simon Willison TIL, phiresky performance blog

---

## Metadata

**Confidence breakdown:**
- Current schema and function map: HIGH — direct file read, line-by-line
- Target schema: HIGH — from WORKING-MEMORY.md (prior research, HIGH confidence)
- Migration path: HIGH — table-rebuild pattern is SQLite canonical for column changes
- Hook change map: HIGH — grep-verified all import sites
- Open questions: MEDIUM — novelty_encounter detection and error_signature behavior need planner decision

**Research date:** 2026-03-02
**Valid until:** Until any hook file is modified (this research reflects current file state)
