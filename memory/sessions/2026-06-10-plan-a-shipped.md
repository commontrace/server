# 2026-06-10 — Plan A shipped: error-time injection hardening (skill v0.3.0)

**Status: COMPLETE.** All 7 tasks of `docs/superpowers/plans/2026-06-10-error-time-injection-hardening.md` executed via subagent-driven development and pushed to commontrace/skill main (900871d → 574dfc4).

## What shipped (commits on commontrace/skill main)

| Commit | Task |
|--------|------|
| f813308 | Test scaffold (tests/base.py HookTestCase, offline isolation) |
| 1091ba4 | local.db v2→v3 migration (error_signatures deduplicated, UNIQUE(project_id, signature), resolution payload columns; auto-backup local.db.bak) |
| 65ffee3 | record_error_signature upsert + record_resolution (COALESCE) |
| c7f0b70 | Error-time injection: _check_error_recurrence → PostToolUse additionalContext with known fix (informational, provenance line always-on) |
| b1eab32 | Resolution pairing: _command_head + _pair_resolution on success path; assisted resolution → record_trace_consumed("local:<hash>") |
| 47c8af6 | Death-spiral fix: epsilon-greedy exploration floor (EXPLORATION_EVERY=10) in adaptive cooldown |
| 574dfc4 | End-to-end integration test (error → fix → recurrence in new session → injection → assisted resolution); version 0.3.0 |

30 tests, all stdlib unittest, fully offline. Final opus review verdict: **DONE AS-IS** — all 7 hard constraints (no LLM calls, M19/M20 redact-before-sig, M22 consent, informational injections + provenance, basenames-only, H9, backup-before-migrate idempotent) verified with file:line evidence; entire deferred-findings ledger adjudicated dismiss/accept-document, zero fix-now items.

## Accepted-as-documented (future hardening candidates, NOT urgent)

- conn-close-on-raise missing in _check_error_recurrence + _pair_resolution (masked by short-lived hook process)
- record_trace_consumed (pre-existing v2) has no trigger_name filter — "local:" marker can mis-attribute if a different bash_error trigger interleaves between injection and fix; canonical flow correct
- Pre-existing (NOT Plan A): local.db / local.db.bak land 0o644 when _get_conn creates them (session_start creates dir 0o700, but file perms unenforced) — one-line `os.chmod(DB_PATH, 0o600)` candidate
- Repeat-pairing drift within session (bounded: [:10] stored, [:5] displayed)
- SELECT-then-INSERT race in upsert (bounded by UNIQUE + IntegrityError-as-recurrence; chosen over ON CONFLICT for SQLite<3.24)

## Process lessons (subagent-driven dev)

- "⚠️ CRITICAL RULE — VERBATIM CODE" in implementer prompts: after one implementer paraphrased plan code (6 spec violations Task 4), every later task passed spec review first-try with this rule.
- When reviewer report unusable/hallucinated → controller verifies directly against plan, doesn't re-dispatch (Task 6 one-liner; Task 7 "missing t" claim refuted by session_state.append_event setdefault).
- Two-stage review (spec gate before quality) caught what tests couldn't: assertIn substring checks too loose to detect paraphrased injection messages.

## Next (not started)

- **Plan B: viral artifacts** (brain graph, struggle-grid, Resolved-with trailer, README badge, monthly Compiled — local-first at N=1) — needs own writing-plans invocation
- **Plan C: friction-kill onboarding** — needs own writing-plans invocation
- Founder-facing: project CLAUDE.md "Persistent Local Store" table list stale (pre-dates v2 drop AND v3); should now describe v3 error_signatures shape
