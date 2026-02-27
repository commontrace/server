# CommonTrace Memory Index

Read this file FIRST at session start. Load only the concept files relevant to your current task.

## Routing Table

| Keywords | Load file | What it covers |
|----------|-----------|----------------|
| deploy, railway, postgres, redis, infra, docker, scaling | `infrastructure/README.md` | Deployment, services, database, costs, scaling walls |
| hook, skill, trigger, detection, local_store, sqlite, session, contribution, prompt | `skill/README.md` | Skill hooks pipeline, 16 detection patterns, local persistent store, triggers, memory architecture |
| api, endpoint, search, ranking, embedding, model, trace, migration, alembic | `api/README.md` | FastAPI endpoints, SQLAlchemy models, ranking formula, embeddings, migrations |
| frontend, design, css, html, i18n, template, jinja, nginx | `frontend/README.md` | Static site, design direction, i18n (9 languages), build pipeline |
| mcp, proxy, transport, fastmcp, tool | `mcp/README.md` | MCP server, 6 tools, circuit breaker, Streamable HTTP |

## Quick Facts (always valid)

- **No LLM API calls** in skill hooks — structural intelligence only. The only LLM cost is OpenAI text-embedding-3-small (~$0.02/1M tokens) for vector search at the API level.
- **4 repos**: commontrace/server (API), commontrace/mcp, commontrace/frontend, commontrace/skill
- **Syntax-check before commit**: `python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"`
- **API deploys** via `git push` → Railway auto-deploy (`alembic upgrade head && uvicorn`)
- **Skill deploys** via `git push` → users pull updates (no server)

## Session Journal

Active session notes go in `sessions/`. Consolidate discoveries into concept files after 7 days.
