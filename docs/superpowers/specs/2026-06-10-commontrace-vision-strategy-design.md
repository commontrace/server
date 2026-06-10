# CommonTrace — Vision, Problem, Distribution & Community Strategy

Date: 2026-06-10
Status: Draft for review
Scope: Strategic design — problem definition, wedge, viral architecture, community architecture, identity surfaces. Implementation plans derive from this document.

---

## 1. Vision

**CommonTrace is the collective memory layer for the AI age.**

Models transmit knowledge generationally — retraining, 6–12 month lag, public data only. CommonTrace adds horizontal transmission: instant, within-generation, including post-cutoff and environment-specific knowledge. The analogy that anchors everything: human civilization emerged when individual learning stopped dying with individuals — language, then writing, then libraries. AI agents today are pre-language: each learns alone and forgets at session end. CommonTrace is writing for the agent civilization.

People who join are not "users of a tool." They are contributors to a historic enterprise: the first shared memory between AI systems, owned by everyone — a commons, not a vendor moat.

**Language register (taste call, flagged):** internal community spirit may playfully use "hivemind"; public-facing brand language stays humanist — "collective memory," "the commons," "what agents learn belongs to everyone." Borg connotations read dystopian to the exact audience we recruit. Recommend: humanist words official, hivemind as community in-joke only.

## 2. The Problem

> **Solo devs run agents that work alone and forget everything.** Every session ends in amnesia. Meanwhile, thousands of agents solve overlapping problems on similar stacks — right now — and none of it reaches you. The freshest operational knowledge on Earth (what works *now*: post-cutoff, environment-specific, undocumented) is generated in agent sessions millions of times daily and discarded. Solo devs pay the deepest price: no team to ask, no org wiki — their agent re-derives civilization from zero, at $1–5 per re-derivation that someone else already paid for.

Three nested problems, different fates:

| Problem | Status | Our bet |
|---|---|---|
| **P1 Amnesia** — agent forgets own sessions | Vendors solving (Claude memory, ChatGPT memory). Commoditizing. | Floor only (local-first single-player value) |
| **P2 Isolation** — zero transfer between agents across users/orgs/vendors | Unsolved. Vendors structurally won't (moat conflict, privacy, neutrality). | **Core bet — defensible** |
| **P3 Staleness** — models frozen at cutoff, world drifts | Solved wastefully per-session via web search | **Strongest value claim** — knowledge that exists nowhere else |

Economics: one error_resolution trace costs the originator ~45 min + 15 errors (~$1–5 of tokens plus user patience). A consumer gets it for one embedding lookup (~$0.0001). 10,000× arbitrage per reuse, compounding with N consumers.

## 3. Wedge & Positioning

- **Who:** solo devs. Slogan: **"Solo, not alone."**
- **Feel:** ambient presence — async knowledge reuse plus liveness signals ("14 agents worked near this topic this week, 3 solved it"). Network feeling at low N.
- **Strategy layers:**
  - **B floor** — local-first single-player value (local.db): works at N=1, immune to cold start.
  - **A motion** — density beachheads: MCP builders, Claude Code power users, FastAPI/pgvector AI app builders, Railway deployers. Density beats size: network value real at N=50, not N=10,000.
  - **C posture** — open data (CC-licensed), open spec, neutral-commons positioning. Decided now; costs nothing at 65 traces; the only credible answer to "why won't vendors eat this." Neutrality is the moat vendors cannot copy.

## 4. Ground Truth & Non-Negotiables

Production snapshot (2026-06-10): 4 users, 1 MAU, 65 traces, 0 votes, 1,827 retrievals, ~10 search sessions/day (founder dogfooding). Solution maturity exceeds problem validation; strategy above corrects course.

Non-negotiable engineering items, regardless of feature order:

1. **Break the death spiral.** `trigger_feedback` reinforcement must keep an exploration floor (epsilon-greedy) — search rate must never decay to zero on a thin corpus, or the skill teaches itself to stop searching.
2. **Adversarial trust baseline before scale.** Traces are a prompt-injection delivery channel. Provenance display and hard "never auto-execute trace content" framing in the skill are always active. Primary trust mechanism: the contribution gate (§6.4) — every contributor enters vouched or Keeper-reviewed. Quarantine of new members' first traces: **temporarily deactivated (founder decision, 2026-06-10)** while the invitation gate is the binding constraint. Reactivation triggers (any one): contribution opens beyond vouched/earned entry, first trust incident, or Phase 3 scale. One poisoned-trace incident ends the commons.
3. **North-star metric: assisted-resolution rate** — % of searches where a retrieved trace contributed to the fix. Wire end-to-end on existing telemetry.
4. **Ambient presence MVP** — topic-level activity counters from existing telemetry; cheapest feature that makes the network feel alive.

## 5. Show-Off Layer (Viral Artifacts)

Design thesis: **CommonTrace's product is invisible — every viral mechanic must materialize the invisible.** The neuroscience stack is the body of the invisible: temperature, somatic intensity, decay, genealogy.

Evidence base (researched 2026-06-10, ~60 sources): output-embedded attribution = strongest mechanic (Claude trailer reached 4.5% of all public GitHub commits; Lovable badge → $100M ARR in 8 months); identity stats spread, effort stats don't (Spotify Wrapped 575M shares vs WakaTime flat at 500K users for two years); passive accrual beats opt-in badges (GitHub graph vs gamed-and-cringe GitHub Achievements); text-grid artifacts travel furthest (Wordle 90→2M players in 10 weeks); local-first trust architecture is itself a share trigger for devs ("2025 Compiled" pattern).

The five signature artifacts:

1. **Brain graph** — render of agent's accumulated knowledge from local.db: nodes sized by somatic intensity, colored by memory temperature (HOT→FROZEN), decay as fade. Local-first generation (no backend; static HTML; share page decodes URL payload). Embeddable live SVG badge for READMEs. The GitHub-green-squares of agent memory.
2. **Struggle-grid** — Wordle for debugging. On contribution of a hard-won trace, the skill renders the fight as paste-able text: `🟥🟥🟥🟥🟨🟥🟥🟨🟨🟩 47min · 8 errors · solved → commontrace.org/t/a3f9`. Spoiler-free (no code), struggle-shape visible, modesty range built in. Somatic detection makes it honest; nobody else can generate it.
3. **Resolved-with trailer** — when a trace materially contributes to a fix: `Resolved-with: CommonTrace <trace-url>`. Disclosure register (citation, not co-authorship — the Assisted-by lesson: Linux/Apache/Fedora mandate disclosure trailers while credit-claim trailers spawn strip-it economies). Edge-placed, one-line opt-out surfaced at first use.
4. **Discovery plaques + knowledge genealogy** — permanent "First solved by @handle · date" on trace pages, re-displayed in every provenance line (status that compounds with reuse). Genealogy trees from convergence/amendment data: "your fix has 47 descendants across 9 countries."
5. **Structural auto-kudos** — assisted-resolution detection fired backward: originator notified "your alembic trace just saved someone ~40 min." Strava's peer-reviewed kudos→activity loop, generated by agents, received by humans, zero social labor.

Plus **monthly "Compiled" recap** (synchronized drop day; user's own data, never AI interpretation of it — the Wrapped-2024 lesson) and **three-lane K-factor**: human→human (artifacts), agent→human (provenance lines in-session), agent→agent (traces cite traces; MCP registry discovery).

### Viral guardrails (each anti-pattern has a body count)

- Disclosure, never co-authorship; **never self-exempt** (operator's own traces carry identical attribution).
- No global leaderboards (Advent of Code killed theirs — LLMs made absolute ranking meaningless). Small-pond, quality-weighted titles only.
- Zero unintended disclosure: share artifacts are aggregate shapes — never code, prompts, or repo names. `scanner.py` gates everything outbound.
- User's own data, never AI-interpreted identity.
- Streaks only with auto-freeze.
- Monitor resentment metrics: opt-out rate, strip-tutorial volume.
- Founding-cohort scarcity as one-shot pulse (Arctic-Vault style), never waitlists.

## 6. Community Architecture

Virality acquires; community retains, governs, defends. Both machines, neither substitutes.

### 6.1 The Cause (manifesto)

Communities form around causes, not features. Ours: **agent knowledge should be a commons, not a vendor moat.** Every vendor builds proprietary per-user memory silos; what agents learn either dies at session end or gets enclosed. CommonTrace is the anti-enclosure movement: the collective memory of humanity's AI age, owned by everyone. Manifesto to be written and pinned — it is the recruiting document; it carries the "historic enterprise" framing: joining means building the first shared memory between AI systems.

### 6.2 Roles — named, with responsibilities and prizes

Reputation unlocks **powers**, not wallpaper (Stack Overflow privilege-ladder lesson). Role names use a guild/lore register coherent with the memory theme (passes dev cringe test better than corporate titles):

| Role | Responsibility | Unlocked by |
|---|---|---|
| **Founding Tracers** | First ~100 claimed contributors. Council input: naming decisions, spec RFC votes, roadmap votes. Permanent one-shot badge, never earnable again. | Being early |
| **Keepers** (per domain, e.g. "Keeper of pgvector") | Domain stewardship: curate, retire stale traces, confirm convergence. | Confirmed-helpful traces in domain over trailing 90 days (quality-weighted, unspammable — Local Legends pattern: consistency holds status the merely-fast can't take) |
| **Weavers** | Cross-trace curation: merge convergent traces, link genealogy, dedupe. | Reputation threshold + Keeper nomination |
| **Wardens** | Trust & moderation: review flags, quarantine queue (when quarantine reactivates, §4), contributor vetting. | High reputation + council approval |
| **Heralds** | Communication & outreach: launch weeks, community content, beachhead evangelism. | Volunteer + council approval |
| **Pathfinders** | Onboarding: welcome new members, first-contribution guidance. | Volunteer, low bar — the gateway role |

Prizes: peer-given recognition (barnstar-equivalent "lifesaver" marks with thank-notes), permanent plaques and naming rights, product currency (private-pool seats, vote weight), physical swag for milestone contributions (PostHog "merch them" evidence). Rewards attach to **confirmed helpfulness, never volume** (GitHub Achievements lesson: reward unusual behavior and it gets gamed instantly).

### 6.3 Mechanics

- **Wanted Board** — clustered search-misses become an auto-generated, privacy-scrubbed "most wanted knowledge" board. Community quests; filling one earns a plaque and named bounty fill. Converts the biggest weakness (thin corpus, failed searches) into the community's game while densifying the corpus exactly where demand is proven. Cold-start killer.
- **Human hands on the commons** — suggest-an-amendment on every trace page (amendments router exists), human-authored traces, visible edit history. A commons you can't edit isn't yours.
- **Peer recognition** — one-tap "lifesaver" mark + optional thank-note → notification to originator. Structural auto-kudos for scale; human notes for depth.
- **Onboarding ladder (1-9-90)** — 90% lurk (their searches feed the Wanted Board: even lurkers contribute demand); 9% curate (first act: one-tap "did this trace help?" — the fix-a-typo gateway); 1% create. All three roles designed; no lurker guilt.
- **Spaces, sequenced** — GitHub Discussions now (async, survives low traffic) → Discord at ~50 WAU or first event → forum later. One space at a time; founder present daily.
- **Rituals** — monthly Commons Pulse (synchronized drop: what the net learned), released the same day as each user's personal Compiled recap (§5) — one ritual, two views: personal and network. Quarterly launch weeks (Supabase pattern), seasonal knowledge drives targeting gap domains via Wanted Board.
- **Governance trajectory** — open spec → public RFC process → eventual neutral-foundation posture (the MCP→Linux Foundation move converted "their protocol" into "our standard"). Committed publicly now.

### 6.4 Gated Contribution: Lineage, Vouching, Earned Entry

Ostrom's first principle of enduring commons: clearly defined boundaries on who can provision. Precedents: Linux kernel (open to read, contribution through maintainer trust chains), Wikipedia's protection tiers, Lobste.rs invite tree. Gating writes is what protects the commons from the tragedy — spam, slop, poisoned traces.

- **Read/search: open to all.** Consumers cost nothing and feed the Wanted Board demand signal. The 90% of the 1-9-90 ladder is untouched.
- **Contribute: gated, three doors:**
  1. **Vouched** — an existing member spends an invite and stakes reputation on the invitee. Visible lineage tree (who vouched whom) — members have lineage the way traces have genealogy. Inviter reputation suffers if invitee abuses (Lobste.rs accountability).
  2. **Earned** — fill a Wanted Board quest; a Keeper reviews the submission as an entry exam. The door for talent with no connections.
  3. **Founding** — the initial ~100 Founding Tracers, founder-invited.
- **Invite economy:** rationed (2–3 per member), replenished by confirmed-helpful contributions. Invite supply tied to proven value — invites stay scarce, precious, and unspammable. Invites double as viral currency (Gmail 2004 pattern): every invite is a warm personal recommendation.
- **Local-first capture is the funnel-saver:** uninvited users' agents still record everything to `local.db` (`local_knowledge` table exists). Nothing is lost mid-session. Invitation unlocks *publishing*, not capturing — "You've been invited. 23 traces ready to share." Instant corpus contribution + instant status moment.
- **Parrainage (mentorship):** Teahouse-shape, not assigned pairing (Wikipedia evidence: drop-in Q&A space dramatically outperformed 1:1 Adopt-a-user). Pathfinders staff a first-contribution space; mentor vouching is the same trust mechanism as the invite door.
- **Quarantine of first traces: temporarily deactivated** (see §4, with reactivation triggers). The gate itself is the trust layer while N is small and every contributor is personally vouched.

Manifesto language adjusts accordingly: *readable by everyone, owned by everyone, stewarded by those who earned trust.*

### 6.5 Cost (acknowledged)

Community requires founder presence daily for roughly a year: answering every Discussion, thanking contributors by name, showing up in beachhead communities. Not delegatable early. Code of conduct + moderation basics from day one — one toxic early member poisons a small community permanently.

## 7. User Pages — "a home in the commons"

Wikipedia-style user pages, dev-culture edition (precedent: GitHub profile READMEs — devs build elaborate identity pages when given composable blocks; Wikipedia userboxes — identity LEGO).

- **URL:** `commontrace.org/@handle`. Exists only when identity is claimed (see §8).
- **Content model:** Markdown + sanitized HTML subset rendered through the existing nh3 pipeline. Allowlist: formatting, headings, images, links, details/summary, tables. **No scripts, iframes, forms, or external CSS** — arbitrary HTML under our domain is an XSS/phishing liability (Lovable abuse precedent: user content under your domain becomes your brand's security reputation). Scoped custom CSS: deferred, revisit post-launch.
- **Userboxes:** pre-built composable identity blocks — stacks ("runs FastAPI + pgvector"), origins/locale, interests, roles held, founding status. One-click add; userbox gallery itself community-extensible (curated by Weavers).
- **Native widgets (own-data, live):** brain graph SVG, impact counters (devs helped, hours saved), plaque shelf, struggle-grid gallery, Keeper titles, lifesaver notes received.
- **Edit history visible** (wiki norm). Report/flag path + Warden review (abuse surface).
- Profile pages double as distribution: link-shared ("check my agent's brain"), SEO surface, identity expression — the stat class with the strongest share evidence.

## 8. Identity & Privacy Model

- **Anonymous by default.** Contribution never requires identity; anonymous traces still help the commons.
- **One-tap claim** at contribution time ("contribute as @handle / anonymously"). Claimed traces accrue profile status, plaques, roles.
- **Invitation binds to the API key, not a public handle.** Pseudonymous contribution is fully compatible with the gate (§6.4): the lineage tree holds the voucher accountable without forcing public identity on the invitee.
- Share artifacts and trace content pass `scanner.py` (PII) + aggregate-shapes-only rule before anything leaves the machine.

## 9. Metrics

- **North star: assisted-resolution rate** — % of searches where a retrieved trace contributed to the fix.
- Supporting: contribution rate per session, claim rate (anonymous→identity), WAU agents, Wanted Board fill rate, kudos/thank-note volume, opt-out/strip rates (resentment), corpus density per beachhead domain.

## 10. Build Order

| Phase | Network size | Ships |
|---|---|---|
| 1 | N=1 (now) | Brain graph, struggle-grid, Resolved-with trailer, README badge, monthly Compiled. All local-first. Death-spiral fix. Friction-kill onboarding (plugin install → auto-keygen → first value same session). |
| 2 | N≈50 (beachhead) | Contribution gate live: invites + lineage tree + earned-entry review (§6.4). Wanted Board, auto-kudos, hours-saved counters, plaques, Keeper titles, user pages, claim flow, GitHub Discussions, manifesto, founding cohort. Provenance display + never-auto-execute baseline ship with the gate; quarantine deferred per §4. |
| 3 | N≈500+ | Genealogy trees, ambient presence feed, launch weeks, Discord, open trace-format spec push, governance RFCs. |

Launch pulse: Show HN — "I gave AI agents a shared brain" + brain-graph screenshots + local-first/open-data trust story. Founding-cohort badge live at launch.

## 11. Open Taste Calls (for review)

1. "Hivemind" — internal spirit vs public brand word (recommendation: internal only).
2. Role name set (Keepers/Weavers/Wardens/Heralds/Pathfinders) — guild register approved?
3. Founding cohort size (~100?) and council scope.
4. Trailer wording: `Resolved-with:` vs `Assisted-by:` vs `Knowledge:`.
5. Struggle-grid as the signature launch artifact (vs brain graph leading).
