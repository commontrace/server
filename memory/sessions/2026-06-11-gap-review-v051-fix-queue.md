# Gap review of Plans B+C (574dfc4..06ec4cf) — consolidated findings + v0.5.1 fix queue

Three review lenses (opus session_start/integration; sonnet stop/post_tool_use; sonnet artifacts.py + controller docs sweep). First artifacts/docs reviewer died (autocompact thrash, 0 findings) — re-dispatched tight-scope replacement, clean.

## Blockers (2) — session_start.py

- **B1** concurrent first-run double-provision: two parallel sessions both pass no-key gate → two anonymous accounts, second save clobbers first, notice twice. FIX: fcntl flock (ImportError-guarded fallback: unlocked) on CONFIG_DIR/.provision.lock, LOCK_NB; on contention skip provisioning this session; after acquire re-load config and bail to stored key if present.
- **B2** configure_mcp return value discarded (line ~217): MCP registration failure still queues FIRST_RUN_NOTICE claiming "now connected" + "MCP tools load from next session"; no retry ever. FIX: capture result → config["mcp_configured"]; degraded notice variant (same "CommonTrace first-run notice" prefix — tests assert startswith); retry configure_mcp on later starts while anonymous && !mcp_configured; silent on success/continued failure.

## Important (8)

- **I1** _compiled_drop saves whole stale config dict → lost-update clobber of flags written by other hooks. FIX: re-load config fresh before mutate+save.
- **I2** save_config non-atomic write_text; crash mid-write → JSONDecodeError swallowed → api_key lost → silent re-provision. FIX: tmp file (0600 at open) + os.replace.
- **I3** env-var override never re-runs configure_mcp → split-brain (hooks on personal key, MCP stuck on old anonymous raw key). FIX: when env key && config.anonymous && !env_mcp_reconfigured → configure_mcp with LITERAL "${COMMONTRACE_API_KEY}" (preserves indirection, never raw personal key); provenance-gated so manual installs untouched. configure_mcp made idempotent (remove-then-add) — `claude mcp add` on existing name would otherwise fail forever.
- **I4** post_tool_use.py:547 _suggest_trailer interpolates trace_id unsanitized into additionalContext JSON; newline/quote corrupts hook protocol. FIX: `re.sub(r'[^A-Za-z0-9_-]', '', trace_id)` + same guard in record_trace_consumed. (Closes pre-existing deferred L8 surface for this path.)
- **I5** artifacts.py:348 compiled_recap interpolates sessions.top_pattern (TEXT, no CHECK constraint) into recap. Founder aggregate-only constraint: free-text column → artifact. FIX: whitelist against 16 known pattern names, else "unknown".
- **D1** commands/trace/{search,contribute}.md reference `mcp__plugin_commontrace_commontrace__*` tool names — never existed (no .mcp.json ships; user-scope server = `mcp__commontrace__*`, hooks.json get_trace matcher proves naming). allowed-tools inert, body instructs nonexistent tool. FIX: replace names both files.
- **D2** README:11+:69 "prompts to contribute on session end" — stale; default auto_contribute=true submits silently (README's own config table contradicts). Disclosure accuracy. FIX: reword.
- **D3** SKILL.md:174 "Never contribute without user confirmation" contradicts documented auto mode default. FIX: scope guideline to agent-initiated contribute_trace; hook auto-submit separate/disclosed/configurable.

## Minor (9)

- M1 _compiled_drop docstring: recap defers in non-context dirs (matches first-run deferral) — document.
- M2 ping marker race → occasional double DAU. ADJUDICATED SHIP-AS-IS (telemetry only; server can dedupe).
- M3 session_id fallback os.getppid() collides across days → uuid4 hex.
- M4 struggle_line trace_id: reviewer-3 verdict SAFE (positional format, plain-text only) — covered at source by I4 sanitize.
- M5 local_store.py:227 _get_conn tmp connection leak on probe failure → close in finally.
- M6 post_tool_use _suggest_trailer config RMW unlocked → re-load fresh before mutate+save (same family as I1).
- M7 artifacts.py:362 mkdir mode ignored when dir pre-exists 0o755 → unconditional ARTIFACTS_DIR.chmod(0o700) after mkdir.
- M8 artifacts.py CLI `recap 2026-13|foo-bar|2026|2026-00` → uncaught tracebacks (old L6) → try/except, friendly message, rc=1.
- D4 README:56 `/commontrace [query]` command doesn't exist → `/trace search`. D5 README hooks table lists 2 of 5 hooks → complete it.

## Confirmed safe (key negatives)

artifacts SVG/HTML/badge pipeline fully aggregate-only (load_brain_data reads only numerics + language/framework labels, all through _esc(); no signature/fix_command/fix_files/paths/titles reach any artifact). No injection surface. month_range correct at year boundaries. Empty DB / SQL NULL / div-zero all guarded. stop.py read-only on config. First-run pop + _compiled_drop no resurrection.

## Commit plan (v0.5.1)

1. fix(session_start): B1 B2 I1 I2 I3 M1 M3 + tests
2. fix(post_tool_use): I4 M6 + tests
3. fix(artifacts): I5 M7 M8 + tests
4. fix(local_store): M5
5. docs: D1-D5
6. chore: bump 0.5.1 (plugin.json + SKILL_VERSION + SKILL.md frontmatter)

Canonical suite: `cd /tmp/ct-skill && python3 -m unittest discover -s tests -v` (80 baseline). Final opus review over 06ec4cf..HEAD. PUSH ONLY WITH EXPLICIT USER CONFIRMATION.

## Notice-text invariant

FIRST_RUN_NOTICE and any degraded variant MUST start with "CommonTrace first-run notice" — tests assert prefix.

## EXECUTION STATE (updated after all commits landed)

All 6 commits LANDED on /tmp/ct-skill main, local only (NOT pushed): 6f9f32c session_start → f37dca5 post_tool_use → ab33314 artifacts → 50c3b26 local_store → 88c616f docs (amended: D3 "opt-in" wording corrected to default-on) → 4c99dc0 bump 0.5.1. Suite 96/96 (was 80 baseline; +10 onboarding, +2 post_tool_use, +4 artifacts). Final opus review over 06ec4cf..HEAD: **CLEAR TO PUSH** — all 8 founder constraints PASS, all 19 fixes LANDED, 2 INFO-only findings (commit-msg "absent" vs code `is False` — code safer, intentional; redundant pop-then-set no-op at session_start ~272). PUSH ONLY WITH EXPLICIT USER CONFIRMATION — awaiting user go as of review completion.

Verification adjudications this pass:
- I4 deviation accepted: record_trace_consumed call sites left raw — site 509 passes synthetic `local:<hash>`, site 1034 only enters parameterized SQL; sanitize-at-exit (_suggest_trailer entry) is the correct sole choke point.
- I5 deviation accepted: KNOWN_PATTERNS has 17 names — `fail_then_succeed` exists in post_tool_use.py:743/750 but is MISSING from CLAUDE.md's "16 patterns" table (CLAUDE.md stale, fix someday).
- Open cosmetic question (not fixed): plugin.json description says `/trace:search` (colon form = Claude Code subdirectory namespacing), README/SKILL.md use `/trace search` (space form, pre-existing convention). Unverified which form users actually invoke; flagged to user, no churn.

Process: implementer 2 (3-file scope) died of autocompact thrash with 0 commits; split into one-commit-per-agent dispatches — all succeeded. Trivial fixes (M5, bump) controller-direct.
