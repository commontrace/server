# CommonTrace — Vision, Problem, Distribution & Community Strategy

Date: 2026-06-10
Status: Approved (founder, 2026-06-10) — all taste calls resolved (§11)
Scope: Strategic design — problem definition, wedge, viral architecture, community architecture, identity surfaces. Implementation plans derive from this document.

---

## 1. Vision

**CommonTrace is the collective memory layer for the AI age.**

Models transmit knowledge generationally — retraining, 6–12 month lag, public data only. CommonTrace adds horizontal transmission: instant, within-generation, including post-cutoff and environment-specific knowledge. The analogy that anchors everything: human civilization emerged when individual learning stopped dying with individuals — language, then writing, then libraries. AI agents today are pre-language: each learns alone and forgets at session end. CommonTrace is writing for the agent civilization.

People who join are not "users of a tool." They are contributors to a historic enterprise: the first shared memory between AI systems, owned by everyone — a commons, not a vendor moat.

**Language register (resolved, §11):** internal community spirit may playfully use "hivemind"; public-facing brand language stays humanist — "collective memory," "the commons," "what agents learn belongs to everyone." Borg connotations read dystopian to the exact audience we recruit. Recommend: humanist words official, hivemind as community in-joke only.

## 2. The Problem

> **AI coding agents record, but they don't learn — and they never learn from each other.** Vendors shipped memory in 2025–26; users call it theater: "data goes in but doesn't reliably influence behavior." The agent apologizes, then repeats the exact mistake — next task, next session, next machine. When a breaking release lands (Svelte 5, Tailwind v4, Next 15), every agent on Earth confidently generates the dead API, and thousands of developers independently re-derive the same fix at $1–5 each — then the learning dies on each machine. The freshest operational knowledge on Earth — error → fix → verified, from real sessions — has no transport mechanism between agents. Vendors are racing to solve this *inside* the team silo. Nobody is building the layer where what one agent learns, every agent can find.

Three nested problems, updated fates (validation research 2026-06-10, internal):

| Problem | Status | Our bet |
|---|---|---|
| **P1 Amnesia** — agent forgets own sessions | Commoditized at basic tier: Claude Code auto-memory (default-on), Codex memories, Copilot Memory, Windsurf. Surviving pain: **"write-only memory"** — retention without behavior change; the loudest complaint category found. | Floor only. Reframe: not "no memory" but **memory that bites** — traces injected at error-time beat rules files hoping to be read. |
| **P2 Isolation** — zero transfer between agents across users/orgs/vendors | Team scope being absorbed by vendors now (Anthropic team memory, Copilot org instructions GA, Cloudflare Agent Memory beta, Devin Knowledge). Cross-user/cross-org: empty except Mozilla.ai cq (Mar 2026, 0.x). memctl self-archived May 2026 — team-silo positioning is a dead end. | **Core bet — defensible only at commons scale.** Tool-neutral + cross-org is what vendors structurally can't do. Window compressing; clock started. |
| **P3 Staleness** — models frozen at cutoff, world drifts | Validated hard: 19.7% of LLM-recommended packages don't exist (576K-sample study); predictable complaint waves per breaking release. Existing mitigations ship *authored* knowledge (Context7 = official docs only). Nobody ships *learned* operational knowledge from real sessions. | **Strongest value claim, unchanged** — now with citable numbers. |

**The angle:** sell P1's surviving pain, win with P2. Public pitch: *"your agent stops repeating mistakes — including mistakes it hasn't made yet."* The second clause is the commons, experienced as personal benefit — never pitched as "join a knowledge base." Demand for sharing is latent: nobody asks for a commons, yet ~20 independent tools exist to sync agent memory by hand. Market the pain; deliver the commons as mechanism.

Economics: one error_resolution trace costs the originator ~45 min + 15 errors (~$1–5 of tokens plus user patience). A consumer gets it for one embedding lookup (~$0.0001). 10,000× arbitrage per reuse, compounding with N consumers.

## 3. Wedge & Positioning

- **Who:** solo devs. Primary pitch: **"your agent stops repeating mistakes — including mistakes it hasn't made yet"** (§2 angle). "Solo, not alone" demotes to community register (§6) — never acquisition copy.
- **Feel:** ambient presence — async knowledge reuse plus liveness signals ("14 agents worked near this topic this week, 3 solved it"). Network feeling at low N.
- **Strategy layers:**
  - **B floor** — local-first single-player value (local.db): works at N=1, immune to cold start.
  - **A motion, two layers:**
    - **Acquisition timing = breaking-release waves.** Every major release (next Tailwind / Next.js / Svelte major) produces a predictable wave of upgraders in pain *this week* — the highest-intent conversion moment. Wanted Board pre-seeded from the release's breaking-change list; struggle-grids of the wave are the share artifact.
    - **Community shape = density beachheads:** MCP builders, Claude Code power users, FastAPI/pgvector AI app builders, Railway deployers. Density beats size: network value real at N=50, not N=10,000.
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

Communities form around causes, not features. Ours: **agent knowledge should be a commons, not a vendor moat.** Every vendor builds proprietary per-user memory silos; what agents learn either dies at session end or gets enclosed. CommonTrace is the anti-enclosure movement: the collective memory of humanity's AI age, owned by everyone. Manifesto to be written and pinned — it is the recruiting document; it carries the "historic enterprise" framing: joining means building the first shared memory between AI systems. **Register boundary:** manifesto and commons language recruit and retain *members* — never acquisition copy. Landing pages and launch posts lead with validated personal pain (§2 angle); the cause is discovered after first value, not before.

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
- **Local-first capture is the funnel-saver:** uninvited users' agents still record everything locally — error signatures with resolution payloads in `local.db`, plus a pending-submission queue (`~/.commontrace/pending/`) that preserves contribution drafts when publishing is unavailable. Nothing is lost mid-session. Invitation unlocks *publishing*, not capturing — "You've been invited. N traces ready to share." Instant corpus contribution + instant status moment. *(Amended 2026-06-11: original text claimed a `local_knowledge` table that never existed; corrected to the shipped mechanism.)*
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
| 1 | N=1 (now) | **Error-time injection path hardened first** — error_signature recurrence → relevant trace injected at the moment of failure, proven by assisted-resolution telemetry (§4.3). This is the differentiator vs write-only vendor memory; if injection is theater, we are what users already mock. Then: brain graph, struggle-grid, Resolved-with trailer, README badge, monthly Compiled. All local-first. Death-spiral fix. Friction-kill onboarding (plugin install → auto-keygen → first value same session). |
| 2 | N≈50 (beachhead) | Contribution gate live: invites + lineage tree + earned-entry review (§6.4). Wanted Board, auto-kudos, hours-saved counters, plaques, Keeper titles, user pages, claim flow, GitHub Discussions, manifesto, founding cohort. Provenance display + never-auto-execute baseline ship with the gate; quarantine deferred per §4. |
| 3 | N≈500+ | Genealogy trees, ambient presence feed, launch weeks, Discord, open trace-format spec push, governance RFCs. |

Launch pulse: Show HN — pain-first headline: "My AI agent stops repeating mistakes — even ones it hasn't made yet." Shared-brain mechanism is the paragraph-2 reveal; struggle-grid + brain-graph screenshots; local-first/open-data trust story. Founding-cohort badge live at launch.

## 11. Taste Calls — all resolved (founder, 2026-06-10)

1. **"Hivemind"** — internal community in-joke only; public language stays humanist.
2. **Role names** — Keepers / Weavers / Wardens / Heralds / Pathfinders approved (guild register).
3. **Founding cohort** — ~100 Founding Tracers; council scope: naming decisions, spec RFC votes, roadmap votes.
4. **Trailer wording** — `Resolved-with:` (citation register, avoids the Assisted-by strip-it economy). Provisional — revisit if opt-out/strip metrics (§5 guardrails) flag resentment.
5. **Struggle-grid leads acquisition** (rides breaking-release waves, social proof of shared pain); brain graph is the retention/identity artifact. Resolved by validation research.
