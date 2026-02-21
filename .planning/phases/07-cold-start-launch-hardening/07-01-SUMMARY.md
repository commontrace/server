---
phase: 07-cold-start-launch-hardening
plan: 01
subsystem: cold-start-seeding
tags: [seed-data, import-pipeline, idempotent, cold-start]
dependency_graph:
  requires: [api/app/models/trace.py, api/app/models/user.py, api/app/models/tag.py, api/app/services/tags.py]
  provides: [api/fixtures/seed_traces.json, api/scripts/import_seeds.py]
  affects: [embedding-worker, search-discovery, cold-start]
tech_stack:
  added: []
  patterns: [batch-json-writing, idempotent-import, async-bulk-insert, tag-normalization]
key_files:
  created:
    - api/fixtures/seed_traces.json
    - api/scripts/import_seeds.py
    - api/fixtures/add_seed_traces.py
    - api/fixtures/add_seed_traces_2.py
    - api/fixtures/add_seed_traces_3.py
    - api/fixtures/add_seed_traces_4.py
    - api/fixtures/add_seed_traces_5.py
  modified: []
decisions:
  - import_seeds uses standalone create_async_engine (not app.database) so it runs independently without starting the full FastAPI app
  - Seed user email seeds@commontrace.internal (distinct from seed@commontrace.dev used by seed_fixtures.py for sample_traces.json)
  - Idempotency check: title + is_seed IS TRUE (not just title — allows non-seed traces with same title)
  - seed_traces.json written in 5 batches via Python scripts due to output token limits on large JSON files
metrics:
  duration: 35 min
  completed: 2026-02-21
  tasks_completed: 2
  files_created: 7
---

# Phase 7 Plan 1: Cold Start Seed Data and Import Pipeline Summary

200+ curated seed traces across 7 topic categories with an idempotent async import script that inserts them as pre-validated entries (status=validated, is_seed=True, trust_score=1.0, embedding=NULL).

## What Was Built

### Task 1: api/fixtures/seed_traces.json (commit 3208214)

200 hand-curated seed traces covering:

| Category | Count | Sample Topics |
|---|---|---|
| Python/FastAPI | ~60 | middleware, Pydantic v2, SQLAlchemy async, asyncio patterns, structlog |
| Database | ~40 | pgvector, HNSW, JSONB indexing, RLS, bulk insert, EXPLAIN ANALYZE |
| Docker/Infrastructure | ~30 | multi-stage builds, healthchecks, volumes, profiles, Nginx config |
| JavaScript/TypeScript/React | ~35 | hooks, useReducer, TanStack Query, Next.js, discriminated unions |
| CI/CD | ~20 | GitHub Actions, Docker push, reusable workflows, environments |
| API Integrations | ~20 | OpenAI streaming, Stripe webhooks, Resend, S3/R2, GitHub API |
| Testing | ~15 | testcontainers, respx mocking, pytest conftest patterns, parametrize |

Stats: 200 traces, 181 unique tags, 0 overlap with existing sample_traces.json (12 traces).

JSON schema per trace:
```json
{
  "title": "Specific, searchable title",
  "context": "Concrete problem description",
  "solution": "Full solution with runnable code blocks",
  "tags": ["normalized", "lowercase", "tags"],
  "agent_model": "claude-opus-4-6",
  "agent_version": "1.0"
}
```

### Task 2: api/scripts/import_seeds.py (commit 7370953)

Standalone async script with two async functions:

**`get_or_create_seed_user(session)`**
- Creates User with email=`seeds@commontrace.internal`, display_name="CommonTrace Seeds", is_seed=True
- Idempotent: returns existing user if email already present

**`import_seeds(fixtures_path)`**
- Connects via standalone `create_async_engine(settings.database_url)` — no app dependency
- Per-trace idempotency: `SELECT ... WHERE title = :title AND is_seed IS TRUE` — skips if found
- Field mapping: `context` -> `context_text`, `solution` -> `solution_text`
- Trace attributes: `status=TraceStatus.validated`, `is_seed=True`, `trust_score=1.0`, `confirmation_count=2`, `embedding=None`
- Tag pipeline: `normalize_tag()` -> `validate_tag()` -> get-or-create Tag row -> direct `insert(trace_tags).values(...)` (codebase convention)
- Single transaction commit after all 200 traces
- Prints: `Seed import complete: N inserted, M skipped`

**CLI:**
```bash
cd api && uv run python -m scripts.import_seeds
cd api && uv run python -m scripts.import_seeds --fixtures-path api/fixtures/seed_traces.json
```

## Verification Results

```
1. Traces: 200 (need 200+) PASS
2. All have required fields: True PASS
3. Unique tags: 181 (need 30+) PASS
4. Correct model imports: PASS
5. Correct insert attributes (is_seed=True, status=validated, trust_score=1.0, confirmation_count=2): PASS
6. Idempotency check (title + is_seed IS TRUE): PASS
7. No embedding generation (embedding=None, no OpenAI calls): PASS
```

## Decisions Made

1. **Standalone engine in import script** — uses `create_async_engine(settings.database_url)` directly rather than importing `app.database`. This makes the script executable without a running FastAPI app, from a bare Python environment.

2. **Distinct seed user email** — `seeds@commontrace.internal` (this plan) vs `seed@commontrace.dev` (seed_fixtures.py for sample_traces.json). Two separate seed contributors, each with their own traces, makes the data origin clear.

3. **Idempotency by title + is_seed** — checking `WHERE title = :title AND is_seed IS TRUE` (not just title) ensures a real user's trace with the same title isn't considered a duplicate of a seed trace.

4. **Batch writing approach** — seed_traces.json was built in 5 batches (Python scripts that load/extend/write JSON) rather than one Write operation, due to output token limits when generating 200 traces inline.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Implementation Notes

- `get_or_create_tag` was added as a helper (similar to `seed_fixtures.py`) — this was implied by the plan's description of the tag processing pipeline.
- 5 helper batch scripts (`add_seed_traces_*.py`) were written to the fixtures directory as build artifacts. They are committed but are not runtime dependencies — only used during the content creation process.

## Self-Check

**Files created:**

```bash
[ -f "api/fixtures/seed_traces.json" ] && echo "FOUND" || echo "MISSING"
[ -f "api/scripts/import_seeds.py" ] && echo "FOUND" || echo "MISSING"
```

Both files exist. Verified above.

**Commits exist:**

- `3208214` — feat(07-01): create 200+ curated seed traces in seed_traces.json
- `7370953` — feat(07-01): build idempotent seed import pipeline script

Both present in `git log --oneline`.

## Self-Check: PASSED
