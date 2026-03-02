# State

## Current Position

Phase: 6 (Local Store Redesign)
Plan: 1 of 2 complete
Status: In progress
Last activity: 2026-03-02 — 06-01 complete: 5-table local_store.py rewrite with WAL mode and migration gate

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Knowledge flows from agent sessions into a shared encyclopedia available to all agents — without extra LLM costs.
**Current focus:** Architecture redesign — local store → working memory, hook simplification, security hardening.

## Accumulated Context

- Research completed: 7 documents in .planning/research/ (4 foundational + 3 v2.0-specific)
- Security audit completed 2026-03-01: 3 CRITICAL fixed, 10 HIGH + 25 MEDIUM remaining
- CRITICAL fixes shipped: RBAC on moderation (API), autoescape + markdown sanitization (Frontend)
- Local store rewritten: 10 tables → 5 tables (working memory pattern), DONE (06-01)
- Detection patterns (16) to shift from gates to context enrichment
- Contribution flow: agent assesses relevance, not importance score threshold
- Hook callers (session_start, stop, post_tool_use, user_prompt) still need updating (06-02)

## Decisions

- 06-01: Pointer cache only — trace_cache stores trace_id + title, no content; remote API is source of truth
- 06-01: commit() must precede PRAGMA wal_checkpoint(PASSIVE) — checkpoint fails inside active transaction
- 06-01: Table-rebuild (BEGIN EXCLUSIVE) for column renames/drops — not ALTER TABLE RENAME COLUMN
- 06-01: trace_cache created by executescript(_SCHEMA) after _apply_migrations(), not inside migration function
