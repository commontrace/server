# CommonTrace Content Questions — Working Doc

This is the question list we iterate on. Each question is a piece of content waiting to be
written. Status moves through: `draft` → `in progress` → `published` (or `killed`).

**How this list differs from the comms list:** his six questions were all benefits and
listicles — answers to "why is this good?" That's necessary but it only converts people who
already trust us. What his list never asks: the trust questions ("what does this thing see?"),
the comparison questions ("why not CLAUDE.md?"), and the category questions ("what even is a
trace?"). Those are the pieces that earn the install. This list keeps his strongest material
(reframed honestly per the data brief) and adds the missing layers.

Companion doc: `2026-06-11-content-brief.md` (live numbers, verdicts, drafted pieces, data appendix).

---

## Group A — Trust (the install blocker)

Nobody installs a hook that watches their coding sessions until the privacy question is
answered in plain language. These three pieces remove the biggest objection first.

### Q1. What does CommonTrace see — and what can it never see?

| | |
|---|---|
| **Why this question** | The first question every skeptical developer asks. Answering it before they ask is the single highest-trust move available to us. |
| **Answer's spine** | Detection is structural only: tool sequences, exit codes, file paths, timestamps. It never reads or interprets your prompts, your messages, or your code semantics. Contributions are anonymized and secret-redacted; file references are basenames only; local artifacts are aggregate shapes (counts, labels) — never code, error text, or repo names. Then the receipts: the skill repo is open, point at the exact hook code, invite audit. |
| **Data** | None needed — this is an architecture piece. Link the open repo. |
| **Format** | Long-form + a permanent docs page (this answer should live at a stable URL forever, not just a post). |
| **Status** | draft |

### Q2. What of mine could ever end up in the public wiki?

| | |
|---|---|
| **Why this question** | Q1 calms "what does it watch?" — this kills the sharper fear: "is something from *my* sessions going to show up on a public website?" For almost every user the honest answer is radical: nothing, because installing does not grant the right to publish. Install ≠ contribution. Also disarms the EM-shaped version of the fear ("my junior installs this and leaks our codebase"). |
| **Answer's spine** | Reading is open; writing is invitation-only. A fresh install provisions a read/search account with `can_contribute: false` — any trace submission returns 403 until a vetted member vouches you in. Contributors enter through three doors (vouched, earned, founding), each one vetted; members hold a small number of invitations, so the write side grows through chains of human trust, not through signups. Your agent still captures everything locally — `local.db` is yours and never uploads; an invitation only unlocks publishing. And what a vetted contributor publishes is the trace itself — title, context, solution, file basenames — anonymized (`anon-<8hex>` unless they claim a display name), secret-redacted, PII-scanned at the API; never prompts, never repo names, never raw session content. Session telemetry is separate and aggregate-only: counters, no content. Close on the reframe: most knowledge platforms beg everyone to write; this one verifies its writers, because a shared memory is only useful if you can trust what's in it. The gate is a privacy feature *and* a quality feature. |
| **Data** | Curl-receipts, both live in prod: registration response carries `can_contribute: false`; uninvited `POST /traces` → 403. |
| **Format** | Second half of the Q1 permanent docs page — the privacy pair ("what it sees" / "what can leave"). Also works as a standalone short post. |
| **Status** | draft |

### Q3. Why does CommonTrace make zero LLM calls?

| | |
|---|---|
| **Why this question** | Counter-positioning. Every competitor bolts an LLM onto memory; we deliberately refused. The contrarian engineering decision is the story. |
| **Answer's spine** | Three reasons: cost (only LLM spend is embeddings at ~$0.02/1M tokens — the system stays near-free at scale), privacy (no prompt ever leaves for analysis), determinism (the 17 detection patterns are shapes in the tool stream — error→fix→verify, same file edited before and after a user message — not a model's opinion about your work). Knowledge detection as signal processing, not NLU. |
| **Data** | Cost figure; the 17-pattern table. |
| **Format** | Mid-length technical post. HN-friendly framing ("we removed the LLM from our AI product"). Pairs with Q9. |
| **Status** | draft |

---

## Group B — Pain (top of funnel)

Name the problem better than the reader can. These pieces don't sell CommonTrace; they sell
the problem CommonTrace exists for.

### Q4. Why do AI agents keep solving the same problem?

| | |
|---|---|
| **Why this question** | The universal pain. Every agent user has watched a session re-derive something a previous session already figured out. Naming it precisely is instant recognition. |
| **Answer's spine** | Session amnesia (context windows end), lossy compaction (summaries drop the fix details), project-scoped memory (CLAUDE.md doesn't travel). The agent isn't dumb — it's amnesiac by architecture. Close with the ambient scale: 7,258 errors caught across 303 sessions of one developer's normal work. Errors are constant; memory is not. |
| **Data** | 7,258 errors / 303 sessions. |
| **Format** | Short, punchy, top-of-funnel. The piece you can post anywhere. |
| **Status** | draft |

### Q5. Where does your team's debugging knowledge go when the session ends?

| | |
|---|---|
| **Why this question** | Same pain as Q4 but aimed at the person who pays: engineering managers. Frames lost knowledge as lost money. |
| **Answer's spine** | You paid for every debugging hour — tokens, wall-clock, human review. At session end the investment evaporates. Docs don't catch it (written after the pain fades, by humans, optimistically). Traces are the only artifact that compounds: captured at the moment of learning, ranked by how hard the learning was, surfaced at the moment of recurrence. |
| **Data** | Light: 1,914 retrievals as the "what compounding looks like" proof point. |
| **Format** | Mid-length. EM/lead audience, LinkedIn-shaped. |
| **Status** | draft |

---

## Group C — Proof (the receipts)

We can't show scale, so we show depth. Real traces, real numbers, honest n=1.

### Q6. How one debugging session saved ~15 hours

| | |
|---|---|
| **Why this question** | The single best story we own. One concrete narrative beats any abstract claim. |
| **Answer's spine** | The FastMCP 421 "Invalid Host header" story: deploy behind Railway's proxy, every request 421s, nothing in your code changed. Cause: the `mcp` Python SDK (~1.14+) silently enabled DNS-rebinding protection allowing only `127.0.0.1`. Fix is one `TransportSecuritySettings` argument. Debugged once in April; surfaced 455 times since, at the exact moment the error recurred, in sessions that remembered nothing. Conservative math: ~2 min saved per surfacing ≈ 15 hours from one captured session. Bonus beat: the same fix was contributed independently from a second context — convergence detection flagged it as universal knowledge. The system noticed it twice; that's the signal working. |
| **Data** | 455 surfacings + 144 on the convergent duplicate. **Phrasing rule: "surfaced/retrieved," never "used" — we track injection, not application.** |
| **Format** | Narrative long-form. This is the proof piece; everything else links to it. |
| **Status** | draft |

### Q7. What did my agents learn building real software?

| | |
|---|---|
| **Why this question** | The honest replacement for "use cases." Build-in-public: real traces, contributed automatically, zero curation. |
| **Answer's spine** | Two months, one developer, real products: 67 traces, 1,914 retrievals, 28.6× reuse per captured unit. Then the eight real traces from the brief (FastMCP 421, Stripe metadata silent-drop, auth-gate hardening, gh-CLI in slim Docker, OAuth-across-Linux-users, PHP config discovery, the 32-trace user-correction cluster, the 7,258-error backdrop). Frame: "the hooks caught these — I never wrote anything up." |
| **Data** | The full top-traces list from the brief. **Pre-publish action: retitle vague auto-generated trace titles ("user correction in stop.py") before showcasing.** |
| **Format** | Listicle, build-in-public register. |
| **Status** | draft |

---

## Group D — Category (own the noun)

If "code trace" becomes a term people use, we win the category by default.

### Q8. What is a code trace — and why is it the only asset an AI team actually accumulates?

| | |
|---|---|
| **Why this question** | The flagship. Defines the noun we want to own. Comms question #5 was right to flag this; the brief drafted it; this is the canonical long-form. |
| **Answer's spine** | A trace is the captured record of a state transition — the moment an agent went from not-knowing to knowing. Why it beats documentation (docs are post-hoc, human, optimistic, stale; traces are the residue of the actual learning moment, captured structurally at the instant of transition). The memory model: somatic intensity (hard-won knowledge permanently outranks quick finds — Damasio applied to agents), temperature (HOT→FROZEN), temporal decay, convergence promotion. Kicker: model capability is rented — everyone gets the same models. Traces are the only compounding asset an AI team owns. |
| **Data** | n=1 economics: 67 traces → 1,914 retrievals → 28.6×. |
| **Format** | Flagship long-form. The piece we'd want cited when someone else explains the category. |
| **Status** | draft |

### Q9. How does an agent know it just learned something?

| | |
|---|---|
| **Why this question** | The mechanism deep-dive for the technical reader Q8 hooked. Also our most defensible IP story: 17 patterns, no NLU. |
| **Answer's spine** | The fundamental question the whole system answers. Knowledge appears at state transitions, and transitions have recognizable structural shapes: error→fix→verify; user correction (same file edited before and after a user message — the gap IS the knowledge); approach reversal (Write to a file previously Edit-ed 3+ times — the agent gave up on its mental model); test fail→code fix→test pass; research→implement. Each pattern weighted; temporal proximity compounds co-occurring signals; threshold gates contribution. All from tool sequences and exit codes — no model ever reads your prompts. |
| **Data** | The 17-pattern weight table. |
| **Format** | Technical long-form. Pairs with Q3 (Q3 = why no LLM; Q9 = how it works anyway). |
| **Status** | draft |

---

## Group E — Comparison & Activation (bottom of funnel)

The reader is convinced of the problem. These pieces answer "why this and not the thing I
already have?" and "how hard is it to start?"

### Q10. Why not just use CLAUDE.md, agent memory, or a team wiki?

| | |
|---|---|
| **Why this question** | Highest search intent of any question here. Every convinced reader asks it next, and being the one who answers it fairly is a trust move. |
| **Answer's spine** | Take each alternative seriously. CLAUDE.md: project-scoped, hand-written, unranked — excellent for conventions, structurally unable to carry cross-project debugging knowledge. Agent memory: single-user, single-machine — your agent remembers, your teammate's doesn't. Team wiki: rots, and agents don't read it at error time — retrieval timing is the point (the fix arrives at the failure moment, not in a doc someone might search). Be genuinely fair about where each alternative wins; fairness reads as confidence. |
| **Data** | None required; error-time injection mechanics from the skill. |
| **Format** | Comparison post. Evergreen, SEO-relevant. |
| **Status** | draft |

### Q11. "There is no step 2" — what does onboarding look like when friction dies?

| | |
|---|---|
| **Why this question** | The activation piece. v0.5.x made install the only step; that's a product claim few tools can make, and it's true. |
| **Answer's spine** | The old world: API key, config file, env var, contribution guidelines, and the step where every knowledge tool dies — *remember to write things up*. Now: `claude plugin add commontrace@commontrace/skill`. There is no step 2. First session auto-provisions an anonymous account (random ID, no personal data), registers the MCP server, and delivers a one-paragraph disclosure of exactly what was set up and how to undo it. Prefer review-first? `auto_contribute: false`. Want out? Three commands, listed in the disclosure itself. Optional bridge to Q2: install gives you the reading side instantly; publishing rights are a separate, vetted step. |
| **Data** | None — product walkthrough. |
| **Format** | Short. ~~Hold until v0.5.1 ships~~ — **unblocked: v0.5.2 shipped 2026-06-12**; the onboarding path this piece celebrates is live. |
| **Status** | draft |

### Q12. What changes when a fleet of agents shares one memory?

| | |
|---|---|
| **Why this question** | The vision piece for CTOs running many agents. Comms question #6, kept only in its differentiated form: fleet economics, not individual benefits. |
| **Answer's spine** | First solver mints the fix for every parallel agent mid-task. New agent's session one inherits everything ever learned. Fresh post-compaction contexts get the senior agent's scars. Duplicate token burn on re-derivation drops toward zero. Institutional memory without the institution. **Frame honestly: this is what the architecture does, not what we observe across customers — aspirational register, "what we built it to do."** |
| **Data** | Architecture claims only; n=1 numbers don't support fleet observations. |
| **Format** | Mid-length, CTO audience. Steady-state slot, not launch content. |
| **Status** | draft |

---

## Production order

1. **Q4** (pain — cheapest, widest) →
2. **Q6** (proof — the story everything links to) →
3. **Q1 + Q2** (trust pair — unblocks the installs the first two generate; Q2 is now true of production, gate live since 2026-06-12) →
4. **Q8** (category flagship) →
5. **Q11** (activation — unblocked, v0.5.2 shipped)

Then: **Q10** (catches the convinced), **Q3 + Q9** (technical pair), **Q7** (build-in-public),
**Q5 / Q12** (steady-state).

## Standing rules (apply to every piece)

- **Numbers:** only the cleared set — 1,914 retrievals · 455 on one trace · 28.6× reuse ·
  7,258 errors caught · 67 traces. Avoid user counts in growth framing, 0 votes/amendments,
  trigger consumption rate (instrumentation gap, not a product fact).
- **Never imply adoption scale.** Analytics are public; anyone can curl the truth. Honest
  n=1 IS the strong frame — "one developer, two months, real projects" is distinctive;
  fake scale is fatal.
- **"Surfaced/retrieved," never "used."** We track injection, not application.
- **Every detection/privacy claim must be true of shipped code.** The skill repo is open;
  strangers will audit. If a piece describes behavior, the hook must actually behave that way.
- **Gate claims are now production-true** (deployed 2026-06-12): registration open,
  `can_contribute: false` by default, contribution invitation-only, three doors, funnel-saver
  403. Write them in the present tense.
