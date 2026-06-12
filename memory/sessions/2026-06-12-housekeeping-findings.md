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

Found via 6 semantic searches — NOT exhaustive. Full audit needs admin trace listing (blocked on Finding 1) or title-pattern SQL.

| ID | Title |
|----|-------|
| 2b41772d-53cc-49ac-af1a-28fdcb25223a | config discovery in config.runtime.php |
| 1d0404b6-6508-42c1-b969-2c9d8b33280a | security hardening in AuthGate.tsx |
| 81fb1df7-5f12-4085-9324-1c54816147bc | user correction in 002_seed.sql |
| 9cee16aa-e559-40d4-bde7-c279532fc365 | user correction in base.html |
| de90a3d6-5f4a-4178-af5f-d4f640fd980c | user correction in stop.py |
| 2dd8c23f… (full id unresolved) | config discovery in package.json |

Recommendation: moderation-delete via `DELETE /api/v1/moderation/traces/{trace_id}` (live in prod, founder key is moderator) instead of retitling — these have no salvageable content. Destructive prod action: founder approval required. This supersedes the content-plan pre-publish "retitle vague titles" action for these husks.
