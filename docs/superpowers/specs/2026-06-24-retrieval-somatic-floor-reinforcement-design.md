# Cycle 1: Retrieval Somatic Floor + Local Reinforcement Loop

**Date:** 2026-06-24
**Status:** Approved design (pending user spec review)
**Repos:** commontrace/server + commontrace/skill

## Context

This is the first of several independent cycles adapting a proven two-tier
agent-memory mechanism into CommonTrace. The reference mechanism pairs a durable
store of hard-won lessons (each carrying a scalar importance + applicability gates
+ usage reinforcement) with a per-run episode log. Each cycle is its own spec →
plan → implement loop. Cycle 1 ships its **two signature primitives**, both 100%
structural (zero LLM — the product's hard constraint):

- **#1 Importance-floor safety override** on retrieval: every lesson above an
  importance floor is always included, even when absent from the cosine top-K.
- **#2 The closed reinforcement loop** (`uses`/`last_hit` → rank), wired locally.

The reference mechanism's LLM sub-agents and its local-numpy retrieval substrate
are *not* transferable. What transfers is the **structure** of these two
primitives. The validation gate (#3), `applies_when` predicates (#4), and the
rejected-episode trail (#5) are deferred to later cycles.

## Problem

Two structural gaps, each silently contradicting a stated CommonTrace principle.

### Gap 1 — retrieval silently drops hard-won knowledge (contradicts Principle 3)

CLAUDE.md Principle 3: *"A trace born from a 45-minute, 15-error security
investigation permanently outranks a 2-minute convenience finding in search
results."* At retrieval this is false twice over, then compounded by the skill:

1. **The candidate pool is pure cosine.** `search.py` cuts the top-100 by cosine
   distance alone (`.order_by(distance_col).limit(SEARCH_LIMIT_ANN)`,
   search.py:261-262). `somatic_intensity` is **never consulted to ENTER the
   pool**. A high-somatic trace worded orthogonally to the query never makes the
   100 — it is invisible regardless of how it *would* have ranked.
2. **Inside the pool, somatic is only a tiebreaker.** `somatic_mult = 1.0 + 0.3 *
   somatic_intensity` (search.py:311) caps at **1.3×**, while `sim` is the leading
   multiplier with full dynamic range (search.py:312). Similarity dominates;
   somatic nudges. The principle says somatic should *override*, not nudge.
3. **The skill compounds it.** `session_start.py` requests `limit: 3` and sends
   **no context fingerprint** (session_start.py:405) — so even the existing
   `ctx_boost` (which the server computes from `body.context`) is **dormant** for
   every skill-originated search.

The importance-floor primitive is the precise fix: every lesson above an
importance floor is **always included** in retrieval output, even when absent from
the cosine top-K. Cosine **complements** qualitative ranking; it never replaces it.

### Gap 2 — detection weights never learn from outcomes (the open wire)

`stop.py::compute_importance` (stop.py:263) scores knowledge candidates with
**frozen per-pattern constants** (`error_resolution = 3.0`, …, stop.py:284). The
skill **already computes** per-project trigger effectiveness —
`get_trigger_effectiveness(conn, project_id)` → `{pattern: {fired, consumed,
rate}}` (local_store.py:543) — but that rate is consumed **only** by
`_report_trigger_stats` (stop.py:952) as anonymized analytics. It never feeds back
into (a) `compute_importance` weights or (b) injection ordering. Both ends of the
wire exist locally and sit **unconnected**. The reinforcement primitive closes
exactly this loop: `uses`/`last_hit` → lesson rank.

## Scope

| # | Transfer | Where | LLM? |
|---|----------|-------|------|
| 1 | Importance/somatic floor on retrieval | server `search.py` + skill `session_start.py` | none |
| 2 | Local reinforcement loop | skill `stop.py` + `session_start.py` | none |

**Deferred to later cycles** (each its own spec): #3 validation gate
(`stop.py::_validate_candidate`), #4 `applies_when` / `do_not_apply_when`
predicates, #5 rejected-episode trail, surfaced-vs-consumed self-demotion.

## Invariants (every change in this cycle upholds these)

- **Pure structural, zero LLM.** No API call in the retrieval, indexing, or scoring
  path. (Embeddings for the *query* are pre-existing and unchanged.)
- **Floor complements, never replaces similarity.** Similarity stays the primary
  sort. Floor entries are a guaranteed-inclusion **union**, deduped, and placed at
  the **bottom** of the result list — never injected above a higher-similarity hit.
  (The mechanism's explicit anti-pattern: cosine is not a replacement for
  qualitative rank.)
- **Showstopper protection, both directions.** The floor only **adds** traces;
  it never removes or reorders similarity hits. Reinforcement may dampen a weight
  but may **only ever boost** a genuine `error_resolution` / `security_*` pattern,
  never cut it.
- **No schema migration.** #1 reuses the existing `context` request field and the
  `somatic_intensity` / `valid_until` columns. #2 reuses `local.db`
  `trigger_feedback` via the already-shipped `get_trigger_effectiveness`.
- **Fully disable-able.** `RETRIEVAL_FLOOR_N=0` → byte-identical legacy retrieval.
  Reinforcement is gated on `fired >= 3`, so cold/new projects are untouched.

---

## Part 1 — Retrieval somatic floor (#1)

### Server — `search.py`, main semantic path only

The floor attaches to the **semantic search path** (`query_vector is not None`,
search.py Path 1) — the path `session_start.py` uses. The spreading-activation
path (search.py:156) and the third ranking path (search.py:400) are **out of
scope** for cycle 1.

After the existing similarity ranking
(`ranked = sorted(rows, key=_rank_score, reverse=True)[:body.limit]`), compute a
**floor set** and union it in:

```
floor_rows = SELECT Trace
  WHERE is_flagged = false
    AND embedding IS NOT NULL
    AND somatic_intensity >= RETRIEVAL_SOMATIC_FLOOR
    AND (valid_until IS NULL OR valid_until >= now_utc)     -- same validity gate as Path 1
    AND <same tag pre-filter as the query, when tags provided>
  ORDER BY somatic_intensity DESC
  LIMIT RETRIEVAL_FLOOR_N

# Optional finer context-scope (off by default — see RETRIEVAL_FLOOR_MIN_ALIGN):
# when body.context present AND MIN_ALIGN > 0, keep only floor rows whose
# compute_context_alignment(body.context, trace.context_fingerprint) >= MIN_ALIGN

guaranteed = [f for f in floor_rows if f.id not in {r.Trace.id for r in ranked}]
results = ranked + guaranteed     # floor entries appended at the bottom, never dropped
```

**Properties:**

- Floor entries already present in `ranked` change nothing (deduped by id).
- Floor entries *not* in `ranked` are **appended after** the similarity-sorted
  results — never above a higher-similarity hit. Similarity stays the primary
  experience; the floor is additive recall insurance.
- **Response-size implication (decision to confirm at review):** because the floor
  is a guaranteed union appended to `ranked[:limit]`, `len(results)` can exceed the
  requested `limit` by **up to `RETRIEVAL_FLOOR_N`** (bounded: `len ≤ limit +
  FLOOR_N`). This is the faithful translation of "always included even when absent
  from top-K" (output can exceed K). The endpoint docstring and
  `response.total` are updated to reflect this. *Alternative considered:* keep
  `len ≤ limit` strictly by displacing the lowest-similarity tail entries to make
  room for the floor. Rejected for cycle 1 because on small limits (the skill's
  `limit:3`) displacement lets the floor crowd out similarity; the bounded-overflow
  union is simpler and preserves every similarity hit. Flagged here so the user can
  pick the strict-length variant at the review gate if API consumers assume
  `len ≤ limit`.
- Tag-only mode (`query_vector is None`) is unchanged — existing trust-DESC order
  already surfaces high-trust traces; no floor needed there in v1.

### Server — `config.py` settings (no schema migration)

```python
# Retrieval somatic floor (importance-floor safety override). FLOOR_N=0 disables.
retrieval_somatic_floor: float = 0.75   # env RETRIEVAL_SOMATIC_FLOOR — min intensity to qualify
retrieval_floor_n: int = 2              # env RETRIEVAL_FLOOR_N — max guaranteed floor entries; 0 = off
retrieval_floor_min_align: float = 0.0  # env RETRIEVAL_FLOOR_MIN_ALIGN — extra context gate; 0 = off
```

Names are deliberately `RETRIEVAL_FLOOR_*` to avoid collision with the unrelated
`IMPACT_FLOOR` decay floor (search.py:84). `MIN_ALIGN` defaults **off**: the floor
is already scoped by `somatic >= 0.75` **and** the query's tag pre-filter (which
includes language), so a hard alignment gate is unnecessary in v1 and hard to
calibrate without data. The knob exists for later tuning if the floor surfaces
off-context traces.

### Skill — `session_start.py`

- **Send the `context` fingerprint** in the search body. The hook already builds a
  context fingerprint for its bridge files — reuse it. This activates the dormant
  `ctx_boost` for *all* skill searches (an independent win) and enables the floor's
  optional `MIN_ALIGN` scoping later.
- **Keep `limit: 3`, but render all returned traces.** The server now bounds the
  response to `≤ limit + FLOOR_N` (= 5: up to 3 similarity hits + up to 2 floor).
  `session_start.py` must display **all** returned traces, not re-truncate to a
  hard top-3 — otherwise the appended floor entries (positions 4-5) are silently
  dropped client-side, defeating the floor. No `limit` bump is needed: the floor
  is what adds the extra recall, and `limit:3` keeps the similarity portion small.

---

## Part 2 — Local reinforcement loop (#2, skill, zero migration)

### Skill — `stop.py::compute_importance`

Change the signature to accept the already-computed effectiveness map (keeps the
function pure and unit-testable; the `stop.py` caller already opens a conn and has
`project_id`):

```python
def compute_importance(state_dir, effectiveness: dict | None = None) -> tuple[float, str, dict]:
    ...
    # after base per-pattern `scores` are computed, before thresholding:
    if effectiveness:
        for pattern in list(scores):
            e = effectiveness.get(pattern)
            if not e or e["fired"] < MIN_FIRED:        # MIN_FIRED = 3 (smoothing)
                continue
            lo = 1.0 if _is_protected(pattern) else 0.7
            factor = _clamp(lo, 1.3, 0.85 + 0.5 * e["rate"])
            scores[pattern] *= factor
```

- `MIN_FIRED = 3` — one sample cannot swing a weight.
- `factor = clamp(lo, 1.3, 0.85 + 0.5 * rate)`: `rate=0 → 0.85` (mild damp),
  `rate=0.3 → 1.0` (neutral), `rate=1.0 → 1.3` (boost). Bounded to ±30%.
- `_is_protected(pattern)` → `True` for `error_resolution`, `security_hardening`,
  and any pattern name starting with `security`. For protected patterns the lower
  clamp is **1.0**, so reinforcement can only ever **boost** them, never cut —
  the same showstopper logic as the floor. Local noise (a project that ignores its
  error-resolution traces) can never suppress the product's highest-value pattern.
- Detection is untouched: `post_tool_use.py` still detects the same patterns. Only
  the **weight** a detected pattern contributes in `stop.py` adapts.

The `stop.py` caller computes `effectiveness = get_trigger_effectiveness(conn,
project_id)` once (it already does this for `_report_trigger_stats`) and passes it
in. The analytics report is unchanged.

### Skill — `session_start.py`, local cache recall ordering

The **"Previously useful traces"** local recall path (`get_cached_traces`,
session_start.py:618) is reordered by local track record: traces this project has
actually consumed rank ahead of merely-seen ones, using `trace_cache.use_count`
plus `trigger_feedback` consumption already in `local.db`. The **fresh server
results keep the server's order** (similarity-first, floor-last) — the skill does
not second-guess the server's ranking. Reinforcement reordering applies only to the
local recall list. No migration.

### Explicitly deferred (needs a migration → later cycle)

Surfaced-vs-consumed self-demotion (demote traces repeatedly shown but never
consumed) requires a new per-trace `surfaced` counter, i.e. an additive schema
migration. **Out of scope for cycle 1.**

---

## Files touched

**Server (commontrace/server):**
- `api/app/routers/search.py` — floor union in the main semantic path, after the
  `_rank_score` sort.
- `api/app/config.py` — `retrieval_somatic_floor`, `retrieval_floor_n`,
  `retrieval_floor_min_align`.
- `api/tests/` — floor unit + golden tests.
- *No request-schema change* — `TraceSearchRequest.context` already exists.

**Skill (commontrace/skill):**
- `hooks/session_start.py` — send `context` fingerprint; render all returned
  traces (≤ `limit + FLOOR_N`) instead of a hard top-3; order local cache recall by
  track record.
- `hooks/stop.py` — reinforcement factor in `compute_importance` (+ caller passes
  `effectiveness`); protected-pattern guard.
- `tests/` — reinforcement + protection tests.

## Error handling & edge cases

- **Floor query errors / DB hiccup** → log, fall back to similarity-only results.
  The floor is best-effort and must never break search.
- **`body.context` absent** → floor still works (somatic + tag scoped); `ctx_boost`
  and `MIN_ALIGN` are simply skipped.
- **`RETRIEVAL_FLOOR_N=0`** → floor disabled, byte-identical legacy behavior
  (golden test asserts this).
- **No qualifying traces** (all somatic below floor for the query's tags) → floor
  empty, no-op.
- **`get_trigger_effectiveness` empty or `fired < 3`** → factor not applied, base
  weights unchanged (cold-start safe).
- **Protected pattern with `rate=0`** → factor clamped to `1.0` (uncut).

## Testing

**Server:**
- A high-somatic trace **absent from the cosine top-100** IS returned when
  `somatic >= floor` (the core guarantee).
- A floor trace already in `ranked` → no duplicate; result ids unique.
- `RETRIEVAL_FLOOR_N=0` → output identical to pre-floor (golden test).
- Floor respects the tag pre-filter and the `valid_until` validity gate.
- `len(results) ≤ limit + FLOOR_N`; similarity hits all preserved and ordered above
  floor entries.

**Skill:**
- `rate=0, fired>=3`, non-protected pattern → factor `0.85` applied.
- Protected pattern (`error_resolution`) with `rate=0` → factor clamped `1.0`
  (uncut).
- `rate=1.0` → factor `1.3`.
- `fired<3` → no factor (base weight).
- `compute_importance(state_dir, effectiveness=None)` → identical to today
  (backward-compatible default).
- The existing 177-test suite stays green.

## Out of scope (cycle 1)

- #3 validation gate, #4 `applies_when` / `do_not_apply_when`, #5
  rejected-episode trail.
- Surfaced-vs-consumed self-demotion (needs a migration).
- Floor on the spreading-activation (search.py:156) and third (search.py:400)
  ranking paths.
- Any LLM / NLU.

## Cost

- **Server:** one extra bounded `SELECT … ORDER BY somatic_intensity DESC LIMIT
  FLOOR_N` per semantic search. `FLOOR_N` is tiny (2) and the corpus is < 100K
  rows; negligible. Add a partial index on `somatic_intensity` only if it becomes
  hot.
- **Skill:** in-process arithmetic over `local.db` rows already loaded for the
  analytics report — zero added cost.
- No new vendor, no LLM, no migration.
