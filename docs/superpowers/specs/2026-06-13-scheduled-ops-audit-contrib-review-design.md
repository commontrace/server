# Scheduled Ops: OSS-Health Audit + Contribution Review

**Date:** 2026-06-13
**Status:** Approved design (pending user spec review)
**Repo:** commontrace/server (this monorepo)

## Problem

Two recurring ops needs, both currently manual:

1. **Is CommonTrace a good open-source project?** Nobody checks the project's
   OSS health (community files, CI, security policy, dependency freshness,
   issue/PR responsiveness) on a cadence. Gaps drift unnoticed.
2. **Pending contributions pile up.** Submitted traces, flagged traces,
   amendments, and — most importantly — **open pull requests awaiting merge**
   across the 4 repos have no nag/triage loop. Things rot in the queue.

Both should run automatically, weekly, **orchestrated by Railway cron**, with an
**email alert if a run itself fails** (distinct from "the audit found problems").

## Decisions (locked with user)

| Decision | Choice |
|----------|--------|
| Audit/review engine | **Claude-powered (LLM)** via Anthropic Messages API |
| Model | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) — judgment + cheap |
| Orchestration host | **Railway cron** (two services) |
| Audit scope | **All 4 repos**: server, mcp, frontend, skill |
| Job B scope | **pending traces + flagged traces + amendments + open PRs** (PRs are the priority) |
| Job B action | **Triage digest** — Claude recommends, human decides (no auto-mutation) |
| Reminder cadence | **Weekly, folded into the review digest** (one email, one cadence) |
| Email transport | **Resend** (verified domain `denemlabs.com`) |
| Report destination | Job A → **GitHub issue** in commontrace/server; Job B → **email digest** |
| Failure alert | **Email** to `tools@denemlabs.com` on any unhandled exception |

> **Ethos note:** the product forbids LLM calls (structural intelligence only).
> That rule governs the *product*. This is *ops tooling*, not product — LLM use
> here is a deliberate, scoped exception.

## Architecture

One Docker image, two Railway cron services (same `ops/` root, different
`railwayConfigPath` → different `startCommand` + `cronSchedule`). Standard
Railway monorepo pattern.

```
ops/
  Dockerfile                      # one image, both entrypoints
  pyproject.toml                  # httpx, anthropic, asyncpg, sqlalchemy, pytest
  railway.audit.toml              # cron "0 8 * * 1",  start = python -m commontrace_ops.oss_audit
  railway.review.toml             # cron "0 9 * * 1",  start = python -m commontrace_ops.contrib_review
  src/commontrace_ops/
    common/
      config.py       # env loading + validation (fail fast on missing secret)
      llm.py          # Anthropic Messages API wrapper (Claude Sonnet 4.6)
      github.py       # GitHub REST via httpx: community profile, repo meta, PRs, issues, CI runs
      db.py           # READ-ONLY asyncpg to CommonTrace Postgres (Job B only)
      emailer.py      # Resend HTTP wrapper
      alerting.py     # run_with_alerting(job, name): try/except -> failure email -> exit(1)
      render.py       # markdown rendering helpers (shared)
    oss_audit/
      __main__.py     # entrypoint: gather -> judge -> file issue
      gather.py       # GitHub facts per repo
      judge.py        # build prompt, call llm, parse result
    contrib_review/
      __main__.py     # entrypoint: gather -> triage -> email
      gather.py       # PRs (github) + pending/flagged/amendments (db)
      triage.py       # build prompt, call llm, parse result
  tests/
    test_alerting.py        # exception path sends email + exits non-zero
    test_github.py          # mocked REST responses -> fact shapes
    test_db.py              # query shapes against a fixture / mocked rows
    test_render.py          # report/digest markdown rendering
    test_dry_run.py         # --dry-run prints, sends/files nothing
```

### Configuration (Railway env)

Shared:
- `ANTHROPIC_API_KEY`
- `GITHUB_TOKEN` — fine-grained PAT, scoped to the 4 repos: contents:read,
  metadata:read, pull_requests:read, **issues:write** (for Job A issue filing)
- `RESEND_API_KEY`
- `ALERT_EMAIL_FROM=alerts@denemlabs.com`
- `ALERT_EMAIL_TO=tools@denemlabs.com`
- `CT_MODEL=claude-sonnet-4-6` (override knob)
- `REPOS=commontrace/server,commontrace/mcp,commontrace/frontend,commontrace/skill`

Job B only:
- `DATABASE_URL` — read-only connection to CommonTrace Postgres (Railway
  reference variable to the Postgres plugin)

Job A only:
- `AUDIT_ISSUE_REPO=commontrace/server`

Each entrypoint validates required env at startup via `config.py` and **fails
fast** (which routes through `run_with_alerting` → failure email) if a secret is
missing.

## Job A — `oss-audit` (weekly Mon 08:00 UTC)

**Flow:**
1. For each repo in `REPOS`, gather via GitHub REST:
   - community health: README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT,
     SECURITY, issue/PR templates, CODEOWNERS (via community/profile + contents)
   - repo meta: description, topics, license, archived, default branch
   - CI: latest workflow run conclusion on default branch
   - issues/PRs: open counts + age of oldest
   - releases: latest tag + cadence (gap between last releases)
   - activity: last push timestamp
2. Pack facts → JSON. Single Claude call with an **OSS-health rubric** system
   prompt → returns: overall grade, per-repo assessment, and a **prioritized
   list of improvement suggestions** (most-impactful first).
3. Render markdown report. **File or update** a GitHub issue in
   `AUDIT_ISSUE_REPO`, title `OSS Health Audit — <ISO-year>-W<week>`, label
   `audit`. Dedup: if an open issue with that exact title exists, post a comment
   / edit body instead of opening a duplicate.
4. Any unhandled exception → failure email, exit 1.

**Rubric dimensions** (fed to the model, scored 0–5 each): documentation,
licensing & legal, contribution on-ramp, security policy & disclosure, CI &
tests, release hygiene, issue/PR responsiveness, dependency freshness, project
activity. Suggestions are derived from the lowest-scoring dimensions.

## Job B — `contrib-review` (weekly Mon 09:00 UTC)

**Flow:**
1. **GitHub (priority section):** open PRs across all 4 repos — number, title,
   author, age, draft flag, review state, CI status, mergeable state, changed-
   file list, description. (Not full diffs in v1, to bound tokens.)
2. **DB (read-only):**
   - pending traces: `status = 'pending'` — id, title, context/solution text,
     contributor, created_at, age, confirmation_count
   - flagged traces: `is_flagged = true` — id, title, flagged_at, flag
     categories (from `metadata_json`)
   - amendments: id, original_trace_id, submitter, created_at, age,
     improved_solution + explanation
3. Single Claude call → triage each item:
   - PRs: recommend **merge / review-needed / close**, with one-line reason
   - traces & amendments: **keep / reject / needs-work**, with reason
   - rank by age + severity; surface the aging/pending list as the reminder
4. Email the digest (Resend) to `ALERT_EMAIL_TO`, subject
   `CommonTrace contribution review — <ISO-year>-W<week>`. The aging list IS the
   weekly reminder (per "weekly with the review" decision).
5. Any unhandled exception → failure email, exit 1.

## Failure alerting

`common/alerting.py`:

```python
def run_with_alerting(job, name: str) -> None:
    try:
        job()
    except Exception:
        tb = traceback.format_exc()
        send_failure_email(name, tb)   # Resend; best-effort, never masks original
        raise                          # non-zero exit -> Railway native notification too
```

Both `__main__.py` entrypoints call `run_with_alerting`. Railway's native
cron-failure notification is enabled in the dashboard as a backstop, so an alert
fires even if Resend itself is the thing that's down.

## Error handling & edge cases

- **Missing secret** → fail fast at startup, routed through alerting.
- **GitHub rate limit / 5xx** → bounded retry with backoff in `github.py`; if
  still failing, raise → failure email.
- **Anthropic API error** → raise → failure email (no partial report filed).
- **DB unreachable (Job B)** → raise → failure email.
- **Empty queues (Job B)** → still send a digest ("nothing pending") so the
  weekly heartbeat confirms the job ran.
- **Duplicate issue (Job A)** → title-based dedup, update existing open issue.
- **DKIM/email** → already verified live (denemlabs.com); From must stay on the
  verified domain.

## Known tradeoff

Job B reads the live Postgres schema directly (read-only). Couples to
`traces` / `amendments` columns. Mitigation: all queries isolated in
`common/db.py`, only stable columns selected, covered by a test fixture.
Cleaner-but-bigger alternative — a moderator-only "list pending" API endpoint —
is **deferred** unless the coupling bites.

## Testing

- Unit tests with mocked GitHub / Anthropic / Resend / DB — no live calls in CI.
- `--dry-run` flag on both entrypoints: gather + build prompt + render, but
  print to stdout instead of emailing / filing. Used for local runs and a CI
  smoke test.
- `alerting` test asserts the exception path sends a failure email and exits
  non-zero.
- CI (existing `.github/workflows/ci.yml`) extended to run `ops/` tests.

## Out of scope (v1)

- Full PR diffs in triage (metadata + file list only for now).
- OpenSSF Scorecard integration (LLM engine chosen instead).
- Auto-acting on contributions (human-in-the-loop only).
- A second Resend domain for ops/Workspace mail separation.

## Cost

Sonnet 4.6, ~a handful of calls/week across both jobs → pennies/week. Railway:
two cron services, near-zero idle cost (containers run only on schedule).
