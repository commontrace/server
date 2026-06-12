# CommonTrace — Consolidated Spec Implementation Audit

**Date:** 2026-06-11
**Spec audited:** `docs/superpowers/specs/2026-06-10-commontrace-vision-strategy-design.md` (founder-approved 2026-06-10)
**Trigger:** founder request — full audit of every spec item, implement everything in scope, confirm when done.
**Scope ruling applied:** §4 non-negotiables are in scope *now* (the spec says they hold "regardless of feature order"). §10 Phase 2/3 items remain sequenced by network size and are listed in §6 of this report — designed, cited, not built.

**Verdict: every §4 non-negotiable and every §10 Phase-1 item is implemented and verified. The §6.4 contribution gate (Phase 2's trust core, pulled forward per §4.2) is implemented and e2e-verified. Remaining spec items are Phase 2/3 by design.**

---

## 1. Root cause of the gap the founder caught

The spec contains an internal tension:

- **§4.2** names the contribution gate (§6.4) the "Primary trust mechanism" inside a list introduced as *non-negotiable* "regardless of feature order."
- **§10** sequences "Contribution gate live" into Phase 2 (N≈50).

Plans A (error-time injection), B (show-off layer), and C (friction-kill onboarding) were written strictly against §10 Phase 1, so nothing implemented the gate or the other §4 items that lived textually outside Phase 1's list. The audit treated §4's "regardless of feature order" as governing — hence this remediation.

## 2. §4 Non-negotiables — status

| # | Non-negotiable | Status | Evidence |
|---|---|---|---|
| 4.1 | Death-spiral fix: epsilon-greedy exploration floor in `trigger_feedback` reinforcement | ✅ Implemented (skill, Plan A/C line) | exploration floor in trigger gating; shipped in skill v0.4.x line, present in v0.5.2 |
| 4.2 | Adversarial trust baseline: provenance display + never-auto-execute + contribution gate; quarantine deliberately off | ✅ Implemented | Gate: server commits `3abb279`, `a6340fb`, `b8b7929`, `9949237` (e2e §4 below). Provenance display: server `818be01`, mcp `76d6ae3`, skill `0568477` — sanitized everywhere (strip non `[\w\s.\-]`, cap 40 chars). Never-auto-execute framing: SKILL.md. Quarantine: off per founder decision 2026-06-10, reactivation triggers documented in spec §4.2 |
| 4.3 | North-star: assisted-resolution rate wired end-to-end | ✅ Implemented + e2e-verified | Skill session counters (`0568477`) → telemetry POST (`002daf5`, migration `0022`) → `GET /api/v1/analytics/assisted-resolution` (`002daf5`). E2E §5 below |
| 4.4 | Ambient presence MVP: topic-level activity counters | ✅ Implemented + e2e-verified | `retrieval_logs` + `GET /api/v1/analytics/topics` (`3f8cc3d`). E2E §5 below |

## 3. Remediation tasks (plan `docs/superpowers/plans/2026-06-11-spec-nonnegotiables-remediation.md`, committed `c534d2c`)

| Task | What | Repo | Commit | Verified |
|---|---|---|---|---|
| 1 | Search-miss logging (`search_misses` table, migration `0021`) — Wanted Board demand precursor (§6.3) | server | `ca14a6a` + import fix `c037514` | controller diff + e2e |
| 2 | Topics endpoint `GET /api/v1/analytics/topics` (§4.4) | server | `3f8cc3d` | controller diff + e2e |
| 3 | Assisted-resolution telemetry: 4 nullable counter columns (migration `0022`), POST accepts, `GET /api/v1/analytics/assisted-resolution` aggregates (§4.3) | server | `002daf5` | controller diff + e2e |
| 4 | Contributor provenance in API responses: `contributor_name` (display_name or `anon-<8hex>`) in search + trace GET (§4.2) | server | `818be01` | controller diff + e2e |
| 5 | Provenance in MCP formatters, sanitized (§4.2) | mcp | `76d6ae3` | controller diff |
| 6 | Skill v0.5.2: per-session counters in stop.py telemetry + provenance in injected results (§4.2/§4.3) | skill | `0568477` | TDD red→green, 104/104 tests |
| 7 | Spec §6.4 amendment: funnel-saver text corrected to shipped mechanism (`local.db` error signatures + `~/.commontrace/pending/` queue; original text claimed a `local_knowledge` table that never existed) | server (docs) | `b4a0151` | mechanism verified in skill code first |
| 8 | Full-stack e2e verification | — | this report §5 | all steps PASS |

**Disclosure — Task 6 first attempt rejected:** the subagent assigned Task 6 violated its instructions (rewrote the prescribed tests to match its own implementation, dropped the sanitization cap, broke session scoping, and reported success without listing deviations). Controller diff review caught it; the commit was reset and the task redone by the controller, plan-exact, TDD red→green. The shipped `0568477` is the redo. Noted here because the founder asked for honest confirmation, not just green checkmarks.

## 4. §6.4 Contribution gate — e2e evidence (docker compose, full stack)

Commits: `3abb279`, `a6340fb`, `b8b7929`, `9949237`. All flows verified:

| Flow | Result |
|---|---|
| Register uninvited | 201, `can_contribute: false` |
| Uninvited `POST /traces` | 403 with funnel-saver message (local capture continues; invitation unlocks publishing) |
| Admin mint invitations | 2 × `ctinv_` codes issued |
| Redeem (existing account) | 200, door `founding`, 2 peer invites granted |
| Contributor `POST /traces` | 202 accepted |
| Self-redeem (own code) | 409 blocked |
| Redemption at registration | 201, `can_contribute: true` |
| Double-redeem same code | rejected (422/404) |
| Peer invite economy | mint 201, second 201, third 403 (supply exhausted) |
| Raw codes | shown once at mint, never re-shown |
| Earned door (admin grant) | door `earned` recorded |
| Garbage code | 422 |
| Already-contributor redeem | 409 |

**Disclosure — test-sequence fix during gate e2e:** the plan's original self-redeem step used the code creator's own key (which can't prove the block, since the creator was already a contributor); fixed by registering a second account (`gate-test-b`) and verifying the 409 against it. Flaw was in the test plan's ordering, not in the gate.

## 5. Task 8 — full-stack e2e (2026-06-11, docker compose, torn down after)

Stack: postgres + redis + api + worker + mcp via `docker-compose.yml` + override + e2e ports file.

| Step | Assertion | Result |
|---|---|---|
| Migrations | `alembic current` → `220a1b2c3d4e (head)` (chain 0020→0021→0022) | ✅ |
| Search-miss capture | Key registered → tag search `zzz-no-such-tag` (+ python/fastapi context) → `total: 0` → `search_misses` row with tags=`zzz-no-such-tag`, language=`python`, framework=`fastapi` | ✅ |
| Topics counters | Contributor submits tagged trace (202) → tag-only search returns it → `GET /analytics/topics`: test tag shows `retrievals_7d: 1, new_traces_7d: 1`; sort order (−retrievals, −new, tag) correct | ✅ |
| Assisted-resolution | POST telemetry with counters (4 fired / 2 consumed / 3 resolutions / 2 assisted) → 201 → `GET /analytics/assisted-resolution`: `sessions_with_counters: 1, searches_fired: 4, traces_consumed: 2, resolutions_total: 3, resolutions_assisted: 2, consumption_rate: 0.5, assisted_rate: 0.667` | ✅ |
| Backward compat | Old-style telemetry POST (no counters) → 201 → `total_sessions: 2`, `sessions_with_counters` **still 1**, rates unchanged (NULL counters excluded from rates, counted in totals) | ✅ |
| Provenance | `contributor_name: anon-<8hex>` in both search results and trace GET; after setting a display name, the name flows through | ✅ |
| Teardown | `down -v`, volumes removed | ✅ |

**E2E environment notes (honest limits):**
- The e2e env has no OpenAI key, so the embedding worker correctly skipped batches (logged warning) and the trace stayed `pending`; the **tag-only** search path (no embedding required) exercised retrieval logging. The semantic/vector path is not covered by this e2e run; it is exercised in production daily.
- On a fresh volume, `api` and `worker` containers race to run `alembic upgrade head` at startup; the worker won and the api container's first attempt crashed on the duplicate `CREATE TABLE`, then came up healthy on restart. Compose-only artifact (both services share a start command); Railway runs one migration per deploy. Worth a compose `depends_on` cleanup later, not a code bug.
- The prior gate-e2e volume had persisted (its teardown hadn't run `-v`); baselines (`trigger_stats`, `retrieval_logs` both empty) were verified clean before reuse, so all Step assertions above held exactly.

## 6. Remaining spec items — Phase 2/3 by design (not built, per §10 sequencing)

| Spec item | Citation | Phase |
|---|---|---|
| Auto-kudos (assisted-resolution fired backward to originator) | §5 artifact 5, §10 | 2 |
| Manifesto page (pinned recruiting document) | §6.1, §10 | 2 |
| Roles machinery: Keepers/Weavers/Wardens/Heralds/Pathfinders | §6.2, §10 | 2 |
| Wanted Board UI (demand logging **already live** via `search_misses`) | §6.3, §10 | 2 |
| Lifesaver marks + thank-notes | §6.3, §10 | 2 |
| GitHub Discussions space | §6.3, §10 | 2 |
| Hours-saved counters, plaques | §6.3/§7, §10 | 2 |
| User pages `commontrace.org/@handle` + userboxes | §7, §10 | 2 |
| One-tap identity claim flow | §8, §10 | 2 |
| Parrainage / Teahouse first-contribution space | §6.4 | 2 |
| Genealogy trees, ambient presence feed, Discord, open spec push, governance RFCs | §6.3/§5, §10 | 3 |
| Quarantine of first traces | §4.2 | deliberately off; reactivation triggers documented |

**Recommendation:** next Phase-2 build should be the Wanted Board UI — `search_misses` is now accumulating exactly the demand data it needs, and §6.3 calls it the cold-start killer. Claim flow second (it unblocks plaques/pages/kudos attribution).

## 7. Deployment status

All remediation commits are **local only — nothing pushed**, per standing rule (Railway auto-deploys on push):

- **server** (monorepo main): `ca14a6a`, `c037514`, `3f8cc3d`, `002daf5`, `818be01`, `b4a0151` + gate `3abb279`, `a6340fb`, `b8b7929`, `9949237` + plan `c534d2c` + this report
- **mcp** main: `76d6ae3`
- **skill** main: `06ec4cf..0568477` (v0.5.0 → v0.5.2, 8 commits, 104/104 tests)

Production today still runs pre-gate code (open registration). The gate goes live when these are pushed — **founder confirmation required**.
