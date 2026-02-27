# Infrastructure

## Services (Railway)

| Service | Repo | Domain | Runtime |
|---------|------|--------|---------|
| API | commontrace/server | api.commontrace.org | FastAPI + uvicorn |
| MCP | commontrace/mcp | mcp.commontrace.org | FastMCP 3.0 HTTP |
| Frontend | commontrace/frontend | commontrace.org + docs.commontrace.org | nginx Alpine |
| Skill | commontrace/skill | (not deployed) | Claude Code plugin |

## Local Paths

- API: `/home/bitnami/commontrace/api/`
- MCP: `/tmp/ct-mcp/` (cloned from commontrace/mcp)
- Frontend: `/tmp/ct-frontend/` (cloned from commontrace/frontend)
- Skill: `/tmp/ct-skill/` (cloned from commontrace/skill)

## Database

- PostgreSQL with pgvector extension (1536-dim embeddings)
- HNSW index for similarity search
- Alembic for migrations (`api/migrations/versions/`)
- **Scaling wall**: PostgreSQL RAM when HNSW index grows past 100K traces

## Caching

- Redis for rate limiting and caching
- No Redis-backed queues — background workers use in-process async

## Deployment

- `git push` to any repo → Railway auto-deploy
- API start command: `alembic upgrade head && uvicorn app.main:app`
- Frontend: `python3 build.py && nginx` (static site generation)

## Cost Structure

- OpenAI embeddings: ~$0.02/1M tokens (negligible)
- Railway: ~$25-30/mo for 4 services + Postgres + Redis (main cost)

## Auth Flow

1. `POST /api/v1/keys` (no auth) → generates API key + user record
2. All other endpoints require `X-API-Key` header
3. Trace submission requires email on the user record (RequireEmail gate)
