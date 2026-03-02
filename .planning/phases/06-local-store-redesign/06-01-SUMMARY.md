---
phase: 06-local-store-redesign
plan: 01
subsystem: skill
tags: [sqlite, wal, migration, local-store, working-memory]

# Dependency graph
requires: []
provides:
  - 5-table SQLite working memory schema (projects, sessions, trace_cache, trigger_feedback, error_signatures)
  - PRAGMA user_version=2 migration gate with shutil.copy2 backup
  - WAL mode on every connection (set before DDL)
  - 13 public functions: 8 kept/simplified + 5 new (cache_trace_pointer, mark_trace_used_v2, record_trace_vote_v2, get_cached_traces, prune_stale_cache)
  - Safe v1->v2 migration using table-rebuild pattern (no ALTER TABLE RENAME COLUMN)
affects:
  - 06-02 (hook callers: session_start, stop, post_tool_use, user_prompt)
  - Any future local_store additions

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PRAGMA user_version gate for SQLite schema versioning"
    - "WAL mode set as first statement after sqlite3.connect()"
    - "Table-rebuild pattern for column rename/drop (BEGIN EXCLUSIVE + CREATE/INSERT/DROP/RENAME)"
    - "ON CONFLICT DO UPDATE for idempotent upserts"
    - "conn.commit() before PRAGMA wal_checkpoint(PASSIVE)"

key-files:
  created: []
  modified:
    - /tmp/ct-skill/hooks/local_store.py

key-decisions:
  - "Pointer cache only: trace_cache stores trace_id + title, no context_text or solution_text"
  - "commit() must precede wal_checkpoint(PASSIVE) — checkpoint fails if called inside active transaction"
  - "Migration backup via shutil.copy2 to local.db.bak before any schema changes"
  - "Table-rebuild (not ALTER TABLE RENAME COLUMN) for projects and error_signatures column changes"
  - "trace_cache table created by executescript(_SCHEMA) in _get_conn, not inside _migrate_to_v2"

patterns-established:
  - "Pattern: PRAGMA user_version gate — check version before running any DDL, backup before migration"
  - "Pattern: WAL-first — set journal_mode=WAL immediately after connect(), before migrations"
  - "Pattern: commit-then-checkpoint — always commit() before PRAGMA wal_checkpoint(PASSIVE)"
  - "Pattern: prune-at-exit — prune_stale_cache runs at session end only, never blocks start"

# Metrics
duration: 9min
completed: 2026-03-02
---

# Phase 6 Plan 01: Local Store Rewrite Summary

**1440-line 10-table SQLite encyclopedia replaced with 434-line 5-table working memory cache using WAL mode, PRAGMA user_version=2 migration gate, and safe column-rename via table-rebuild pattern**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-02T00:28:44Z
- **Completed:** 2026-03-02T00:38:09Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Replaced 1440-line 10-table encyclopedic local_store.py with a 434-line 5-table working memory cache
- Deleted 24 encyclopedia functions: BM25 search, temperature classification, Ebbinghaus decay, spreading activation, Jaro-Winkler deduplication, migrate_jsonl_events
- Added 5 new functions for trace pointer caching (cache_trace_pointer, mark_trace_used_v2, record_trace_vote_v2, get_cached_traces, prune_stale_cache)
- Implemented safe v1->v2 migration: projects column rename via table-rebuild, sessions additive ALTER TABLE, error_signatures rebuild, 6 obsolete table drops
- Verified migration on synthetic v1 database with all 10 original tables and test data

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite local_store.py with new schema, migration gate, and all functions** - `969b798` (feat)
2. **Task 2: Verify migration works on a synthetic v1 database** - `510b380` (fix)

**Plan metadata:** (docs commit — created after self-check)

## Files Created/Modified

- `/tmp/ct-skill/hooks/local_store.py` - Complete rewrite: 5-table schema (projects, sessions, trace_cache, trigger_feedback, error_signatures), PRAGMA user_version=2 gate, WAL mode, 13 public functions, 0 encyclopedia code

## Decisions Made

- **Pointer cache only:** trace_cache stores only trace_id + title (120-char truncated), never context_text or solution_text. When full content is needed, the hook calls the remote API.
- **commit() before wal_checkpoint:** PRAGMA wal_checkpoint(PASSIVE) fails with "database table is locked" when called inside an active transaction. DELETEs in prune_stale_cache open a transaction; commit() must close it first.
- **Table-rebuild for column changes:** projects (primary_language/primary_framework -> language/framework) and error_signatures (drop session_id, raw_tail) use CREATE/INSERT FROM/DROP/RENAME pattern inside BEGIN EXCLUSIVE. ALTER TABLE RENAME COLUMN not used (SQLite version compatibility).
- **trace_cache created by _SCHEMA executescript, not inside _migrate_to_v2:** The new table is created by the `conn.executescript(_SCHEMA)` call at step 9 of `_get_conn()`, after `_apply_migrations()`. This is correct — _SCHEMA uses CREATE TABLE IF NOT EXISTS so it works for both fresh and migrated databases.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed wal_checkpoint called inside active transaction**
- **Found during:** Task 2 (migration verification test)
- **Issue:** Research Pattern 3 had `conn.execute("PRAGMA wal_checkpoint(PASSIVE)")` before `conn.commit()`. When DELETEs run, Python sqlite3 opens an implicit transaction. Calling `PRAGMA wal_checkpoint(PASSIVE)` while `conn.in_transaction = True` raises `sqlite3.OperationalError: database table is locked`.
- **Fix:** Moved `conn.commit()` to before `conn.execute("PRAGMA wal_checkpoint(PASSIVE)")` in `prune_stale_cache()`
- **Files modified:** /tmp/ct-skill/hooks/local_store.py
- **Verification:** Migration test passes with "ALL MIGRATION TESTS PASSED"; prune_stale_cache verified on fresh connection after migration
- **Committed in:** `510b380` (Task 2 fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in research pattern)
**Impact on plan:** Single-line order-of-operations fix. No scope creep. The research correctly described the WAL checkpoint pattern but had the commit/checkpoint ordering reversed.

## Issues Encountered

- `prune_stale_cache` test failure required systematic debugging across 8 test cases to isolate the commit/checkpoint ordering issue. Root cause: the research Pattern 3 (from 06-RESEARCH.md) specified the wrong order. The fix is 1 line: swap commit() and wal_checkpoint().

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `local_store.py` is complete and passes all function/migration verification
- Phase 06-02 (hook callers) can now update session_start.py, stop.py, post_tool_use.py, user_prompt.py to remove calls to deleted functions and use the new v2 functions
- The 13 public functions are the contract: 8 kept/simplified + 5 new
- No blockers

---
*Phase: 06-local-store-redesign*
*Completed: 2026-03-02*

## Self-Check: PASSED

- /tmp/ct-skill/hooks/local_store.py: FOUND
- 06-01-SUMMARY.md: FOUND
- Commit 969b798 (feat: rewrite local_store.py): FOUND
- Commit 510b380 (fix: wal_checkpoint ordering): FOUND
