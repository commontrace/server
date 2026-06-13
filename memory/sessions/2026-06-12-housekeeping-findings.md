# 2026-06-12 — Housekeeping sweep findings

## Shipped (local commits, push pending founder confirmation)

- `d5fd56c` — `DELETE /api/v1/admin/users/{user_id}`: junk-account deletion, guarded (401 bad token, 422 bad uuid, 409 system user / moderator / any FK activity, 404 unknown, 200 clean delete). Full guard matrix verified e2e in docker compose, environment torn down with `-v` after.
- `d944ff6` — CLAUDE.md detection table corrected 16→17: `fail_then_succeed` row (detected in post_tool_use.py and labeled in artifacts.py, not yet weighted in stop.py) + note on the dynamic `user_emphasis` booster (1.0–1.5).
- `8b774eb` — marketing content.
- `8935ad0` — session notes.
- skill repo `df44ac7` (/tmp/ct-skill) — plugin.json description now lists `/trace:brain`. Version stays 0.5.2 (description-only change).

## Finding 1 — prod admin router disabled

Every `/api/v1/admin/*` endpoint in production returns 503 "Admin dashboard disabled. Set ADMIN_DASHBOARD_TOKEN env var." The variable was never set in Railway — the token in local `.env` only matches docker-compose. Consequences until the founder sets it in the Railway dashboard (api service → Variables, triggers redeploy):

- No invitation minting via admin endpoints
- No user detail / contribution funnel views
- The new delete-user endpoint (`d5fd56c`) is unusable in prod even after push

## Finding 2 — husk traces in public wiki

Early skill versions auto-submitted template traces with empty slots: context like "When working with , encountered: ..." and solution "Resolution involved changing <basenames>." Zero knowledge content; some leak old project directory paths from earlier servers into the public wiki.

Expanded sweep 2026-06-12 (10 semantic searches total — still not exhaustive; full audit needs admin trace listing, blocked on Finding 1). All 12 below body-verified as zero-content: context "When working with [lang], encountered: ..." (empty slots) + solution "Resolution involved changing <basenames>", except the last which is a literal x/y ping test. Four leak old bitnami project paths in context_text.

| ID | Title | Leak |
|----|-------|------|
| 2b41772d-53cc-49ac-af1a-28fdcb25223a | config discovery in config.runtime.php | — |
| 1d0404b6-6508-42c1-b969-2c9d8b33280a | security hardening in AuthGate.tsx | kasper-smc path |
| 81fb1df7-5f12-4085-9324-1c54816147bc | user correction in 002_seed.sql | thepatchtc path |
| 9cee16aa-e559-40d4-bde7-c279532fc365 | user correction in base.html | commontrace path |
| de90a3d6-5f4a-4178-af5f-d4f640fd980c | user correction in stop.py | — |
| 2dd8c23f-2039-419a-b903-967628854498 | config discovery in package.json | — |
| ad1be8c0-1914-443d-8969-4d4051c1ee92 | user correction in user-logo.svg (typescript) | denemlabs path |
| e6df9b96-2998-4721-bdd7-531b85964297 | user correction in brain.py (python) | — |
| 8861b4d9-e5e2-4b17-9308-d88e664939a8 | user correction in apache-port.conf (javascript) | — |
| f587e0a6-870a-4f70-b406-4424f4848673 | config discovery in railway.json | thepatchtc path |
| aab93041-1000-4397-8712-978d81dff69e | config discovery in package.json (javascript) | — |
| 394fedb6-708c-4ce0-8aaa-3115a15bba5a | ping (context "x", solution "y") | — |

Separate finding, NOT in delete list: duplicate pair with identical titles and real content — a54a5e86-b33b-4410-9e3e-7b1be4babf8a and 19d26683-40cd-4898-89bb-e9811ca5ec60 ("FastMCP SSE returns 421 Invalid Host header…"). Dedup is its own decision.

### RESOLVED 2026-06-12 — all 12 husks deleted

Sequence: (1) founder ran `railway login` out-of-band; CLI authed as DENEM Labs. (2) Set `ADMIN_DASHBOARD_TOKEN` (openssl rand -hex 32) on api service via `railway variables --set` → admin router live. (3) 2 junk accounts deleted via `DELETE /api/v1/admin/users/{id}` — both 200. (4) Flipped founder `is_moderator=true` via `railway ssh -s pgvector` → psql (DB is private-network only, no TCP proxy; base64-piped SQL to dodge railway arg-join quoting). (5) First husk-delete pass: 500 on all 12 — moderation handler only cleared votes/amendments/trace_tags, but traces also FK from retrieval_logs / rif_shadows / trace_relationships → ForeignKeyViolation. (6) Fixed handler (commit 1070fc5, pushed — Railway redeploy), then 12 deletes via `DELETE /api/v1/moderation/traces/{id}` all succeeded. Verified: sampled IDs 404, real FastMCP dup pair (a54a5e86 / 19d26683) untouched.

Mechanism note: `railway ssh -s <svc> <cmd...>` space-joins argv into the remote command line (no implicit `sh -c` wrapper that survives) — pass pipelines as escaped argv (`echo $B64 \| base64 -d \| psql ...`), keep any spaced payload inside the base64 blob. `railway connect` / interactive `railway login` need a TTY (fail under the `!`-prefix non-interactive shell).

### Root cause — how husks got minted (skill repo archaeology)

1. **Commit 212ca83 (2026-05-03), "feat(stop): auto-contribute by default, opt-in manual review"**: Stop hook gained direct POST to /api/v1/traces with `auto_contribute` config default TRUE. Payload uses `suggested_context_text` / `suggested_solution_text` VERBATIM — the structural template strings, no agent or human in the loop, no quality floor.
2. **Template degenerates when journey data thin**: empty context fingerprint → "When working with , encountered: ..."; solution = "Resolution involved changing <3 basenames>." Titles from _build_title → "user correction in stop.py".
3. **Path leak vector**: post_tool_use detect_bash_error captures output tail of failed bash; Claude Code harness appends "Shell cwd was reset to /home/bitnami/..." notices to tool output → that string became error_messages[0] → quoted into context_text → public wiki.
4. **STILL LIVE in v0.5.2**: stop.py:943 `auto_mode = config.get("auto_contribute", True)`; verbatim-suggestion POST unchanged. Invitation gate now limits WHO can submit, but any gated contributor (founder included) can still mint husks today from a thin session crossing score 4.0.

**Proposed fix (not yet shipped)**: husk guard in stop.py auto-submit path — refuse silent submission when suggested texts are degenerate (empty fingerprint slot, error text matching harness-noise patterns like "Shell cwd was reset", solution that is only a basename list); fall back to manual-review pending file instead. Plus filter harness-noise strings out of error capture in post_tool_use.

Recommendation: moderation-delete via `DELETE /api/v1/moderation/traces/{trace_id}` (live in prod, founder key is moderator) instead of retitling — these have no salvageable content. Destructive prod action: founder approval required. This supersedes the content-plan pre-publish "retitle vague titles" action for these husks.

### FULL SWEEP 2026-06-12 — exhaustive body-classification, 49 more husks deleted (86% of wiki)

The 12 above were found by semantic search (non-exhaustive). With the admin router live (`GET /admin/traces/recent`) the sweep went exhaustive, then classification moved from **title-shape regex** to **body content** — the authoritative signal. Husk signature, SQL:

```
context_text LIKE 'When working with%encountered%'   -- degenerate template, empty slots
OR solution_text LIKE 'Resolution involved changing%' -- basename-list "solution"
OR length(context_text) < 5                           -- the x/y ping
```

Result on the post-12-delete corpus: **49 of 57 traces (86%) were husks, all `retrieval_count 0`**, span 2026-05-03 → present. Body classification caught 49 vs title-regex's 46 — 2 husks wore real-looking titles, 1 fresh husk minted *mid-sweep* (count ticked 48→49 between two queries: the v0.5.2 `auto_contribute` faucet is still live and actively minting).

8 real survivors, all genuine prose + non-trivial retrieval: Beehiiv/Ghost (rc0, new), Railway Nixpacks EBUSY (rc37), Claude OAuth sharing (rc62), `gh api` POST switch (rc31), gh-CLI port (rc67), Stripe metadata mismatch (rc129), FastMCP 421 dup pair (a54a5e86 rc494 / 19d26683 rc159).

Deletion (founder approved "Delete all 49 now"): looped `DELETE /api/v1/moderation/traces/{id}`. First pass 22 deleted then `WriteRateLimit` 429'd the rest — retried remainder with 6s backoff-on-429 + 2s inter-delete pacing, all cleared. **Final DB state: 0 husks, 8 traces.** Wiki now 100% real content.

**Faucet fix BUILT (committed `c44dac8`, NOT pushed).** Skill v0.5.3, `/tmp/ct-skill`. Two defenses against the 212ca83 auto_contribute root cause:
1. `redact.strip_harness_noise` / `contains_harness_noise` (new) — `detect_bash_error` scrubs agent-runtime noise lines ("Shell cwd was reset to /home/…", `<system-reminder>`, CommonTrace injection) from bash error capture before storage/signature/publish. Closes the path-leak vector at source.
2. `stop._is_husk` (new) — quality floor on auto-submit. Empty / bare-template (`When working with…encountered:` / `Resolution involved changing…`) / noise-tainted candidates no longer silently POST; fall through to existing manual-review pending file. Rich captures still auto-submit.

Tests: `tests/test_husk_guard.py` 15 cases; full suite 119/119 green. `auto_contribute` default left TRUE (founder's product decision) — guard makes it safe rather than reverting it. **Push gated on founder confirmation** (Railway/users auto-pull on push). Until pushed, deployed v0.5.2 faucet is still live and husks can regrow.
