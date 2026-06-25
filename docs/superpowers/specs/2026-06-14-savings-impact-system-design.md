# CommonTrace Savings & Impact System

**Date:** 2026-06-14
**Status:** Approved design (pending user spec review)
**Repos:** commontrace/skill, commontrace/server, commontrace/frontend

## Problem

Users have no visible sense of what CommonTrace is worth to them. When a retrieved
trace resolves or pre-empts a problem, the value is invisible — so the project
feels free-but-abstract, and contributors feel no identity or belonging.

Three asks, one system:

1. **Per-resolution savings** — quantify the cost saved each time a retrieved
   CommonTrace contribution resolves *or pre-empts* a problem.
2. **Global view** — show total time and money saved across the whole commons.
3. **Community identity** — make people feel they belong, by showing their
   concrete dent in the shared pool (both directions).

The unifying frame: **savings is the engine, the personal number is the
identity.** "The commons saved you 9h / $14; your traces saved others 12h / $22."

## Core constraint

**No LLM API calls** (the product's structural-intelligence rule applies here —
this is product surface, not ops tooling). Every number must come from data the
system already records structurally, or from a real external price. No model is
asked "how much did this save."

## Decisions (locked with user)

| Decision | Choice |
|----------|--------|
| Framing | **Savings as engine, "my saved total" = identity** (integrated) |
| Source model | **Both, labelled**: measured-recurrence + contributor-effort proxy |
| Units | **Time** (minutes) + **Money** (API tokens × price) |
| Money definition | **API token cost avoided** — not a developer hourly rate |
| Token measurement | **Real**: stop hook sums transcript `usage` over the resolution window |
| Storage | **Local personal + anonymized server aggregate** |
| Pre-emption | Credit only on **observable use** (recurrence re-hit, or trace consumed) |
| Price basis | **One canonical published `$/Mtok`**, config constant, overridable |
| Double-count guard | One booking per `(session, signature/trace)` |

## Two directions of value

Both computed from data the system already creates:

- **Inbound** — what the commons saved *you* (consumer side). Booked locally as
  resolutions happen.
- **Outbound** — what *your* traces saved everyone else (contributor side, the
  belonging hook). Server-side: `Σ(tokens_to_resolution × retrieval_count)` over
  your traces, plus the time equivalent. Returned only for your own API key.

## Savings model (per event)

Two labelled sources. Both reduce to real recorded units — no fuzzy
somatic→minutes reconstruction.

| Source | Time saved | Money saved |
|--------|-----------|-------------|
| **Measured** (your own recurrence) | `resolved_at − created_at` from local `error_signatures`, capped 120 min/event | tokens you burned solving it the first time, from transcript `usage` over the window, capped |
| **Estimated** (cross-user proxy) | trace's `time_to_resolution_minutes` (already in `metadata_json`) | trace's `tokens_to_resolution` (contributor's measured tokens, carried with the trace) |

- Every figure is labelled **measured** vs **estimated**, `~`-prefixed, with no
  false precision.
- **Money = tokens × canonical price.** Tokens are real counts (measured or
  carried); only the price multiplier is a chosen constant.

### Token instrument (new)

The Stop hook already computes a first-error → resolved **window** to derive
`time_to_resolution_minutes`. Add: read the hook's `transcript_path`, sum
`message.usage` (input + output + cache tokens) across messages in that same
window, and record `tokens_to_resolution` in the contribution's `metadata_json`
alongside the existing effort fields.

- The measured count rides with the trace, so the cross-user **proxy** number is
  also real (the contributor's measured tokens), not invented.
- **Legacy fallback** (pre-instrument traces lacking the field): estimate tokens
  from `(error_count + iteration_count) × TOKENS_PER_TURN_EST`, labelled
  "estimated." Conservative; never inflates. New traces are always measured.

### Pre-emption rule ("anticiper la résolution")

Credit anticipation **only when it is observably used**:

- A previously-resolved signature that **demonstrably recurs** and is injected →
  measured-recurrence saving (you re-hit it; the saving is real).
- A surfaced trace the agent **actually consumes** (recorded as `local:<hash>`
  consumption) → proxy saving.
- A pure session-start impression that is **never acted on** → **no credit.** We
  do not book speculative counterfactuals. This keeps "anticipation" honest.

### Caps, floors, guards

- Per-event cap (120 min; an equivalent sane token cap) so a wall-clock window
  spanning breaks/overnight can't inflate a single event.
- Legacy floor only where a field is missing; always the conservative side.
- One booking per `(session, signature/trace)` (mirrors the existing trailer
  "once per session/trace" pattern). The same signature resolved again in a
  *different* session counts again — that is real repeated value.

## Storage & data flow

```
resolution / error-time injection detected (stop.py, error-time path)
  → compute saving {minutes, tokens, label, event_type, trace_id/signature}
  → write local.db  savings_events   (+ lifetime rollup)
  → best-effort anonymized increment → server
        POST /telemetry/savings  {minutes_saved, tokens_saved, event_type}
        (no content, no who-helped-whom linkage)
  → server append-only  savings_ledger  → global sums
```

- **Personal total** = local-only (real-time, private). Resets on reinstall in
  v1; tying it to the user's API key for cross-machine continuity is **deferred**.
- **Global total** = anonymized increments only — `{minutes, tokens, event_type,
  created_at}`, nothing else. This matches `docs/privacy-what-is-shared.md`
  verbatim ("usage telemetry is anonymized aggregate counts only"). No new
  privacy exposure.
- **Outbound impact** = server query over the caller's own traces, returned only
  for that authenticated key.

## Surfaces

1. **Session-start recap** (`session_start.py`): if savings accrued since the
   last session, emit one quiet line —
   `CommonTrace: saved you ~Xh ~$Y since last session · lifetime ~Ah/$B · your traces saved others ~Ch/$D`.
   Silent when zero. Opt-out via `"savings_recap": false` in
   `~/.commontrace/config.json`.
2. **On-demand breakdown**: extend the existing `artifacts.py recap` command with
   a savings view — lifetime totals, measured/estimated split, inbound vs
   outbound, top traces by savings, this-month.
3. **Global view** (the "where do we put it" answer): `GET /analytics/savings`
   returns global sums; the frontend renders a live "the commons has saved ~N
   hours / ~$M of agent work" counter on the landing / stats page (i18n, all 9
   languages).

## Components

### Skill (commontrace/skill)
- `local_store.py`: new table `savings_events` (id, project_id, session_id,
  event_type, minutes_saved, tokens_saved, source_label, trace_id, signature,
  created_at) + lifetime rollup read helpers. Schema version bump + migration.
- New token-window helper: read `transcript_path`, sum `message.usage` over a
  time window. Used both at contribution time (record `tokens_to_resolution`) and
  at savings-booking time (measured-recurrence).
- Savings-booking logic wired into the existing resolution / error-time-injection
  detection sites.
- `session_start.py`: recap line.
- `artifacts.py`: savings breakdown in `recap`.
- Config: canonical `price_per_mtok` constant + `savings_recap` opt-out flag.

### Server (commontrace/server)
- Alembic migration: append-only `savings_ledger` (anonymized rows: minutes,
  tokens, event_type, created_at).
- `POST /telemetry/savings` — accepts an anonymized increment (authed by API key
  for rate-limiting, but stored without content or identity).
- `GET /analytics/savings` — global sums for the frontend (extends the existing
  `analytics.py` aggregate surface, which already sums `retrieval_count`).
- Accept and persist `tokens_to_resolution` into trace `metadata_json` at
  contribution (flows through the existing metadata path; add to the stop-hook
  metadata hint + server-side enrichment passthrough).
- Outbound-impact query: `Σ(tokens_to_resolution × retrieval_count)` and time
  equivalent over the caller's traces.

### Frontend (commontrace/frontend)
- Global savings counter component on the landing / stats page.
- i18n keys for all 9 languages.

## Error handling & edge cases

- **Transcript unreadable / `usage` absent** → skip token measurement, fall back
  to the conservative estimate; never crash the hook.
- **Server increment fails (offline)** → best-effort; drop or locally queue. The
  personal local total stays correct regardless.
- **Missing trace metadata** → conservative floors, labelled estimated.
- **Pathological session** (huge window) → per-event caps bound the damage.

## Testing

- **Skill**: savings calc (measured vs proxy, caps, fallbacks); token-window
  parse against a fixture transcript; ledger accumulation; recap formatting;
  opt-out honored.
- **Server**: `/telemetry/savings` carries no content and no identity; global
  aggregate query; `tokens_to_resolution` accepted into `metadata_json`; outbound
  query shape; migration up/down.
- **Frontend**: counter renders from the endpoint; i18n keys present in all 9
  languages.

## Privacy consistency

This design must not contradict `docs/privacy-what-is-shared.md`:
- Server sees only anonymized aggregate `(minutes, tokens, event_type)` — never
  content, never "trace X helped user Y."
- Outbound impact is returned only to the trace's own authenticated owner.
- The recap writes nothing to git; no identity leaves the machine beyond the
  existing anonymized telemetry envelope.

## Scope & phasing

Cohesive single feature spanning three repos → one spec, phased implementation:

1. **Instrument** — token-window measurement + record `tokens_to_resolution`.
2. **Calc + local ledger** — `savings_events`, booking logic, lifetime rollup.
3. **Surfaces** — session-start recap + `artifacts.py` breakdown.
4. **Server aggregate** — migration + `/telemetry/savings` + `/analytics/savings`
   + outbound query.
5. **Frontend global** — counter + i18n.

## Out of scope (v1)

- Cross-machine personal total (tie-to-API-key sync) — deferred.
- Developer-hourly-rate money — explicitly replaced by token cost.
- Sponsor copy / `sponsors@` mailbox, GitHub contributor badge — separate tracks,
  not part of this system.
- LLM-based savings estimation — forbidden by the product constraint.
