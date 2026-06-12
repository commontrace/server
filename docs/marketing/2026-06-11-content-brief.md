# CommonTrace Content Brief — 2026-06-11

Prepared for comms. Every number below is live production data pulled today from the
public analytics endpoints (`api.commontrace.org/api/v1/analytics/*`). Anyone can
re-run these queries — which is exactly why the content strategy below refuses to
fake scale.

---

## 1. Reality check (read before writing anything)

**Live state today:** 67 traces, 4 accounts (one active — the founder, dogfooding),
1,914 total retrievals, 303 sessions reported, 7,258 errors caught by triggers,
0 votes, 0 amendments.

**The analytics are public.** Any journalist, HN commenter, or competitor can hit
`/api/v1/analytics/summary` and see exactly how early we are. Content that implies
fleet-scale adoption ("agents everywhere have learned...") gets debunked in one
curl. Content that owns the early stage ("here's what one developer's agents
learned in two months, automatically") is both safe and more distinctive.

**The honest frame is the strong frame:** one developer, real projects, two months
— and the system already surfaced known fixes 1,914 times. That is 28.6 retrievals
per unit of captured knowledge. The flywheel works at n=1; that's the story.

---

## 2. Verdict on the six questions

| # | Comms question | Verdict | Why |
|---|---|---|---|
| 1 | 7 benefits of using CommonTrace | **Keep, sharpen** | Capability claims, not traction claims — answerable truthfully today |
| 2 | 7 most important real-world use cases from the repository | **Reframe** | Material exists (8 strong real traces) but "use cases" implies breadth we don't have. Frame as dogfooding: "what my agents learned building real software" |
| 3 | 5 most common FastAPI mistakes agents have already learned to avoid | **Kill** | Zero `fastapi`-tagged traces in the repository. Publishing this fabricates a corpus. Replacement below uses what actually exists |
| 4 | 5-step guide to contributing | **Reframe** | v0.5.0 (shipped today) made this obsolete in the best way: install is the only step. "There is no step 2" is a better headline and it's true |
| 5 | What is a code trace and why is it the most valuable asset of an AI team | **Keep — flagship** | Deepest substance: state transitions, somatic intensity, the neuroscience model. Our best long-form piece |
| 6 | 7 benefits of agents sharing knowledge in real time | **Differentiate or merge** | 80% overlap with #1 as written. Keep only if reframed as the *fleet/team economics* piece (#1 = individual developer) |

---

## 3. Drafted content

### Piece 1 — Seven benefits of using CommonTrace (sharpened)

1. **Never debug the same error twice.** When a previously solved error recurs,
   the known fix is injected at the failure moment — not after you ask, not after
   another 40-minute investigation. Error-time injection is the core loop.
2. **Knowledge survives session death.** Context windows end; compactions are
   lossy. A trace captured today fires in a session six months from now.
3. **Hard-won knowledge ranks higher — permanently.** Somatic intensity: a fix
   born from a 45-minute, 15-error investigation outranks a 2-minute convenience
   finding in every future search. The system remembers how hard learning was.
4. **Zero workflow change.** Hooks detect knowledge structurally (16 patterns:
   error→fix→verify, user corrections, approach reversals...). No commands to
   remember, nothing to write up.
5. **Cross-project memory.** The fix your agent discovered in project A fires in
   project B. Project boundaries stop being knowledge boundaries.
6. **Privacy by architecture.** Contributions are anonymized and secret-redacted;
   file references are basenames only; detection never reads your prompts or
   interprets your messages — it watches tool sequences and exit codes.
7. **The flywheel.** Every solved problem makes every agent smarter. 67 traces
   have already been surfaced 1,914 times — knowledge reuse at 28× per trace.

### Piece 2 — What my agents learned building real software (replaces "use cases")

Frame honestly: *"Everything below is a real trace in the repository, contributed
automatically while I built real products. No curation, no writing-up — the hooks
caught these."*

1. **FastMCP returns 421 "Invalid Host header" behind a proxy** (Railway, Fly,
   Cloud Run) — SDK ~1.14+ enables DNS-rebinding protection by default with
   `allowed_hosts=["127.0.0.1"]`. Surfaced **455 times** since April. Bonus story:
   contributed *twice from different contexts* — convergence detection flagged the
   same solution arriving from independent paths, which is the system's signal for
   "this is universal knowledge."
2. **Stripe checkout metadata field-name mismatch silently drops paid top-ups**
   (Firestore + Netlify functions) — a paying-customer bug with zero error output.
   115 retrievals.
3. **Security hardening in an auth gate component** — security-pattern detection
   fired on the structural shape (security file changed after errors). 101
   retrievals.
4. **Porting a bot that shells out to `gh` CLI from a full host to a slim Docker
   image** — the class of deployment knowledge nobody documents. 54 retrievals.
5. **Sharing Claude Code OAuth credentials across Linux users** — symlinks break;
   systemd path works. 50 retrievals.
6. **Config discovery in a PHP runtime config** — config knowledge is notoriously
   underdocumented; the hooks catch it because config edits that resolve errors
   have a recognizable structural shape. 58 retrievals.
7. **The user-correction cluster** — 32 traces where a human redirected the agent
   and the system captured the gap between initial approach and corrected one.
   The gap IS the knowledge: "agent assumed X, reality was Y."
8. **7,258 errors caught across 303 sessions** — the ambient reality this all
   sits on. Coding agents hit errors constantly; each one is a retrieval
   opportunity.

> **Action item before publishing:** auto-generated titles like "user correction
> in stop.py" are too vague to showcase. Retitle the showcase traces first.

### Piece 3 — The bug nobody debugs twice (replaces the FastAPI listicle)

One deep, true story beats five invented ones.

Narrative arc: You deploy an MCP server behind Railway's proxy. Every request
returns `421 Invalid Host header`. Nothing in your code changed. The cause: the
`mcp` Python SDK (~1.14+) silently turned on DNS-rebinding protection that only
allows `127.0.0.1` — fine on localhost, fatal behind any proxy. The fix is one
`TransportSecuritySettings` argument.

My agent debugged this once, in April. The trace has since been surfaced **455
times** at the exact moment the error reappeared — across new sessions, new
projects, post-compaction contexts that remembered nothing. Conservative math:
at even two minutes saved per surfacing, one captured debugging session has
returned ~15 hours. That is the asset class.

(Phrasing care: say "surfaced/retrieved 455 times," not "used 455 times" — we
track injection, not application.)

### Piece 4 — Contributing guide: "There is no step 2"

The old world (and every knowledge tool before this): get an API key, edit a
config file, set an env var, read the contribution guidelines, and — the step
where it all dies — *remember to write things up*.

CommonTrace v0.5.0, shipped this week:

**Step 1:** `claude plugin add commontrace@commontrace/skill`

There is no step 2.

First session: an anonymous account is auto-provisioned (random ID, no personal
data), the MCP server registers itself, and you get a one-paragraph disclosure of
exactly what was set up and how to undo it. From then on the hooks detect
knowledge structurally and contribute it in anonymized, secret-redacted form.
Prefer reviewing before anything is shared? Set `auto_contribute: false`. Want
out entirely? Three commands, listed in the disclosure itself.

If comms insists on five steps, the honest five: **install → code normally →
recurring errors get known fixes injected → new solutions get contributed
automatically → review or delete anything from the dashboard.** But "there is no
step 2" is the headline.

### Piece 5 — What is a code trace? (flagship long-form)

**Definition:** a trace is the captured record of a state transition — the moment
an agent went from *not knowing* to *knowing*. Error signature, what was tried,
what worked, and how hard it was to get there.

**Why it's not documentation:** docs are written after the fact, by humans, when
the pain has faded — so they're sparse, optimistic, and stale. A trace is the
residue of the actual learning moment, detected structurally from tool sequences,
exit codes, and file changes at the instant the transition happens. Detection
never interprets your prompts or your code; it watches the shape of the work.

**Why it's the most valuable asset of an AI team:**
- Your team already paid for every debugging hour. Without capture, that
  investment evaporates at session end. Traces are the only artifact that
  compounds.
- Not all knowledge is equal, and the system knows it. Somatic intensity
  (Damasio's somatic marker hypothesis, applied to agents): knowledge born from
  long, error-dense investigations carries permanent rank weight over quick
  finds.
- Memory behaves like memory: traces have temperature (HOT→FROZEN), temporal
  decay unless retrieved, and convergence levels — the same fix arriving from
  independent contexts gets promoted as universal.
- The economics at n=1: two months of one developer's dogfooding → 67 traces →
  1,914 retrievals. Knowledge reuse at 28× before a single external user.

**Kicker:** model capability is rented; everyone gets the same models. What
accumulates inside *your* loop is the only compounding asset an AI team owns.

### Piece 6 — Seven benefits of real-time knowledge sharing (fleet economics frame)

Only run this if differentiated from Piece 1: Piece 1 = the individual developer;
this = the team running many agents.

1. Parallel agents stop hitting the same wall twice — first solver mints the fix
   for the rest, mid-task.
2. Onboarding a new agent costs nothing — session one inherits everything ever
   learned.
3. Your weakest context learns from your strongest — fresh post-compaction
   sessions get the senior agent's scars.
4. Error-time injection scales across the fleet — the fix arrives where the error
   happens, not where it was solved.
5. No duplicate burn — tokens spent re-deriving known solutions drop toward zero.
6. Institutional memory without the institution — no wiki rot, no doc decay;
   capture is structural and automatic.
7. Cross-stack arbitrage — deployment knowledge learned in one stack transfers
   wherever the same infrastructure appears.

---

## 4. Data appendix (verbatim, pulled 2026-06-11)

```
/summary:   users {total 4, with_email 3, dau 1, wau 1, mau 1}
            traces {total 67, new_7d 2, new_30d 37, total_retrievals 1914}
            votes {total 0} · amendments {total 0}
            searches {distinct_sessions_7d 58, distinct_sessions_30d 302, retrievals_7d 174}
/top-tags:  user-correction 32 · python 15 · javascript 11 · iteration-depth 9 ·
            config-discovery 9 · typescript 7 · railway 4 · deployment 4 ·
            security-hardening 4 · next 3 · fastmcp 2 · dns-rebinding 2
/triggers:  303 sessions · bash_error fired 7,258 · consumed 0
/top-traces (retrievals): 455 FastMCP 421 · 431 user-correction stop.py ·
            279 user-correction brain.py · 144 FastMCP 421 (convergent dup) ·
            115 Stripe metadata · 101 AuthGate hardening · 58 PHP config ·
            54 gh-CLI Docker · 50 base.html · 50 OAuth/systemd · 45 ping
```

**Numbers to use publicly:** 1,914 retrievals · 455 on one trace · 28.6× reuse ·
7,258 errors caught · 67 traces in two months of dogfooding.

**Numbers to avoid or frame carefully:** user counts (4 total, 1 active — fine in
build-in-public posts, fatal in growth claims) · votes/amendments (0 — features
exist, unused) · trigger consumption rate (0.0 — instrumentation gap, not a
product fact; do not cite).
