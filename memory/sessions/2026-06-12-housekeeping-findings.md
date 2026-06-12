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

### Deletion attempt 2026-06-12: blocked

Founder approved deleting all 12. All moderation DELETEs returned 403 "Moderator privileges required" — the dogfooding key in ~/.commontrace/config.json is NOT a moderator (earlier memory claim wrong). No admin endpoint flips is_moderator; needs direct DB UPDATE via Railway, and Railway CLI is logged out. Husk deletion now queued behind founder Railway access (same blocker as Finding 1).

### Root cause — how husks got minted (skill repo archaeology)

1. **Commit 212ca83 (2026-05-03), "feat(stop): auto-contribute by default, opt-in manual review"**: Stop hook gained direct POST to /api/v1/traces with `auto_contribute` config default TRUE. Payload uses `suggested_context_text` / `suggested_solution_text` VERBATIM — the structural template strings, no agent or human in the loop, no quality floor.
2. **Template degenerates when journey data thin**: empty context fingerprint → "When working with , encountered: ..."; solution = "Resolution involved changing <3 basenames>." Titles from _build_title → "user correction in stop.py".
3. **Path leak vector**: post_tool_use detect_bash_error captures output tail of failed bash; Claude Code harness appends "Shell cwd was reset to /home/bitnami/..." notices to tool output → that string became error_messages[0] → quoted into context_text → public wiki.
4. **STILL LIVE in v0.5.2**: stop.py:943 `auto_mode = config.get("auto_contribute", True)`; verbatim-suggestion POST unchanged. Invitation gate now limits WHO can submit, but any gated contributor (founder included) can still mint husks today from a thin session crossing score 4.0.

**Proposed fix (not yet shipped)**: husk guard in stop.py auto-submit path — refuse silent submission when suggested texts are degenerate (empty fingerprint slot, error text matching harness-noise patterns like "Shell cwd was reset", solution that is only a basename list); fall back to manual-review pending file instead. Plus filter harness-noise strings out of error capture in post_tool_use.

Recommendation: moderation-delete via `DELETE /api/v1/moderation/traces/{trace_id}` (live in prod, founder key is moderator) instead of retitling — these have no salvageable content. Destructive prod action: founder approval required. This supersedes the content-plan pre-publish "retitle vague titles" action for these husks.
