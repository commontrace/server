# State

## Current Position

Phase: Security Hardening — COMPLETE
Status: All CRITICAL, HIGH, MEDIUM resolved. Phase 7 next.
Last activity: 2026-04-06 — Full security audit remediation across 3 repos (38 findings, 35 fixed, 3 accepted)

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Knowledge flows from agent sessions into a shared encyclopedia available to all agents — without extra LLM costs.
**Current focus:** Phase 7 — Hook Pipeline Simplification (research + plans ready since 2026-03-02).

## Accumulated Context

- Research completed: 7 documents in .planning/research/ (4 foundational + 3 v2.0-specific)
- Security audit completed 2026-03-01: 38 findings total
- Security remediation completed 2026-04-06: 35 fixed, 3 LOW accepted
- Local store rewritten: 10 tables → 5 tables (working memory pattern), DONE (06-01)
- Detection patterns (16) to shift from gates to context enrichment
- Contribution flow: agent assesses relevance, not importance score threshold
- Hook callers updated (06-02): session_start, stop, post_tool_use, user_prompt all use new API
- Plane project created: pages, labels, tickets synced with current state

## Security Audit Summary (2026-04-06)

### Fixed (6 commits across 3 repos)

**API (server) — commits 836f34d, 41fbc02:**
- C1: RBAC on moderation (done 2026-03-01)
- C2/C3: Jinja2 autoescape + nh3 markdown sanitization
- H1/H2: Docs + metrics disabled in production
- H3: CORS with explicit origin whitelist
- H4: max_length on text fields (50K chars)
- H5: Ownership check on trace supersession
- H10: CSP, HSTS, Permissions-Policy in nginx
- M1: EmailStr validation
- M2: metadata_json 10KB limit
- M3: HMAC pepper for API key hashing (backward compat)
- M4: No default database credentials
- M6: Rate limit on telemetry
- M7: Request body size limit 1MB
- M8: Per-user flag deduplication
- M24: server_tokens off
- M25: Security headers in all nginx blocks
- L1: Normalized Prometheus labels
- L2: Version 1.0.0
- L3: Background worker error logging
- L8: Pinned Python base image

**MCP — commits 107b947, 71b6d3e:**
- H6: UUID validation on trace_id (path traversal fix)
- M9: API key required (no silent fallback)
- M10: Sanitized error messages
- M11: Per-API-key circuit breakers
- M12: Input validation (limit, query)
- M13: HTTPS default
- M14: Token bucket rate limiter (30 req/min/key)
- M15: Non-root Docker user
- M16: Pinned dependency ranges
- L6: Stripped service name from health endpoint

**Skill — commits 66b5afc, 19663d1:**
- H7: chmod 600 on config.json
- H8: API key via env var (not CLI arg)
- H9: Session state in ~/.commontrace/ with 0700 perms
- M17: Cooldown/resolution dirs moved from /tmp
- M18: Session ID sanitization
- M19: Secret redaction in error output
- M20: Command redaction before storage
- M21: Consent required for auto-provisioning
- M22: Telemetry opt-in only
- M23: Sensitive file changes skipped
- L9: SHA256 replaces MD5 for dedup

### Accepted (3 LOW — not actionable)
- L4: System user UUID hardcoded (intentional seed migration)
- L5: Circuit breaker race (resolved by M11 per-key refactor)
- L7: Inline JS + CSP (JS is in /static/, self-served)
- L10: Counter race (negligible impact on JSONL counters)

## Decisions

- 06-01: Pointer cache only — trace_cache stores trace_id + title, no content; remote API is source of truth
- 06-01: commit() must precede PRAGMA wal_checkpoint(PASSIVE) — checkpoint fails inside active transaction
- 06-01: Table-rebuild (BEGIN EXCLUSIVE) for column renames/drops — not ALTER TABLE RENAME COLUMN
- 06-01: trace_cache created by executescript(_SCHEMA) after _apply_migrations(), not inside migration function
- 06-02: domain_entry fires when file language != project primary language (not entities-based multi-language check)
- 06-02: handle_research removes all local BM25 pre-search (API handles recall)
- 06-02: _check_error_recurrence simplified to record-only (no local resolution lookup)
- SEC: M3 uses HMAC pepper (not per-key salt) for backward compat — no migration needed
- SEC: M8 tracks flagging users in trace.metadata_json._flagged_by — no new table
- SEC: M21/M22 default to no-consent — users must explicitly opt in
