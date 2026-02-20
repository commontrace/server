# Technology Stack

**Project:** CommonTrace — Collective Knowledge Layer for AI Agents
**Researched:** 2026-02-20
**Confidence Note:** WebSearch, WebFetch, Read, and Bash tools were unavailable during this research session. All findings are based on training data (cutoff August 2025). Confidence levels reflect this constraint. Versions should be verified against official docs before implementation.

---

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | 0.115.x | HTTP API layer | Async-native, automatic OpenAPI docs, Pydantic v2 integration, dominant in Python ML/AI stacks. Actively maintained. Alternatives (Django REST, Flask) are sync-first or lack type integration. |
| Python | 3.12+ | Runtime | 3.12 brings significant performance gains (~25% faster), free-threaded GIL experiments in 3.13. 3.11 is minimum viable but 3.12 is now the ecosystem standard. |
| Pydantic | v2.x | Data validation / schemas | FastAPI's native validation layer. v2 is Rust-backed, 5-50x faster than v1. Defines Trace, Contribution, Vote schemas centrally. |
| Uvicorn + Gunicorn | 0.30.x / 22.x | ASGI server | Uvicorn as ASGI worker, Gunicorn as process manager in production. Standard FastAPI deployment pattern. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16.x | Primary relational store | Traces, users, votes, reputation scores, tags. ACID compliance critical for reputation correctness. Ecosystem-standard for production Python. |
| pgvector | 0.7.x | Vector similarity search | Runs inside Postgres — no separate vector DB to operate. Supports IVFFlat and HNSW indexes. For <10M traces, pgvector is sufficient and avoids operational complexity of a second database. Alternatives below. |
| Redis | 7.x | Cache + rate limiting + sessions | Token bucket rate limiting for freemium API, session cache, short-lived embedding cache to avoid redundant API calls. Redis Stack (includes RedisJSON, RediSearch) if needed. |
| Alembic | 1.13.x | Schema migrations | Standard SQLAlchemy migration tool. Required for any production Postgres project. |
| SQLAlchemy | 2.x (async) | ORM | SQLAlchemy 2.0+ with async engine (`asyncpg` driver). Async is critical for FastAPI concurrency. |
| asyncpg | 0.29.x | PostgreSQL async driver | Fastest async Postgres driver for Python. Required for SQLAlchemy async mode. |

**Vector DB choice rationale:** pgvector over Qdrant/Weaviate/Chroma for this project because:
- CommonTrace traces are structured data (context + solution + tags + votes) that needs relational integrity
- Keeping vectors in Postgres means joins between trace metadata and vectors are free
- Operational simplicity matters for an open source project (contributors run one DB, not two)
- At 1M traces with 1536-dim embeddings, pgvector HNSW handles this comfortably
- Migrate to Qdrant only if query latency at scale becomes a bottleneck (>5M traces)

### Embeddings

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| OpenAI text-embedding-3-small | API | Primary embedding model | 1536 dimensions, $0.02/1M tokens, best cost-quality tradeoff for semantic code search. text-embedding-3-large is 3x the cost with marginal gains for code. |
| sentence-transformers / all-MiniLM-L6-v2 | 3.x | Local/offline embedding fallback | For self-hosted deployments or cost-sensitive contributors. 384 dimensions, runs on CPU. Critical for open source — users shouldn't need an OpenAI key just to contribute. |
| httpx | 0.27.x | Async HTTP client for embedding API calls | FastAPI-native async client. Use over `requests` (sync-only). |
| tenacity | 8.x | Retry logic for embedding API | Exponential backoff on API rate limits. Critical for batch ingestion pipelines. |

**Embedding pipeline design:** Store model name + version alongside each trace embedding. When embedding model changes, traces can be re-indexed without losing metadata. Use a background task queue (Celery or ARQ) for batch re-embedding, not inline API calls.

### Background Tasks

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ARQ | 0.25.x | Async task queue | Redis-backed, async-native (matches FastAPI's async model). Handles: embedding generation, reputation score recalculation, batch re-indexing. Lighter than Celery for Python async stacks. Celery is acceptable if team already knows it. |
| Redis | 7.x | ARQ broker | Same Redis instance as cache layer |

### Authentication & API Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-jose / PyJWT | 3.x / 2.x | JWT token handling | API key auth for freemium model. Prefer python-jose for JWKS support if OAuth later. |
| passlib | 1.7.x | Password hashing | Bcrypt for user passwords, if user accounts needed beyond API keys |
| slowapi | 0.1.x | Rate limiting middleware | Built on limits library, integrates with FastAPI. Redis backend for distributed rate limiting across workers. |

### MCP Server

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| mcp (Python SDK) | 1.x | MCP server implementation | Anthropic's official Python MCP SDK. Exposes CommonTrace as MCP tools: `query_traces`, `contribute_trace`, `vote_trace`. SSE transport for Claude.ai, stdio transport for Claude Code. |
| FastMCP | 2.x | Higher-level MCP framework | FastMCP wraps the official SDK with FastAPI-like decorator syntax. Reduces boilerplate dramatically. Recommended over raw SDK for tool definitions. |
| httpx | 0.27.x | MCP server → Backend API calls | MCP server is a thin proxy to the FastAPI backend. Async HTTP calls to backend API. |

**MCP architecture decision:** The MCP server should be a separate lightweight process that proxies to the FastAPI backend, NOT a monolith embedding MCP into FastAPI. Reasons:
- MCP protocol (stdio/SSE) is fundamentally different from HTTP REST
- Separation allows MCP server to be updated independently
- Contributors who only want the HTTP API don't need MCP dependencies
- Claude Code uses stdio transport; keeping it separate avoids mixing transports

### Claude Code Skill (`.claude/commands/`)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Claude Code slash commands | Current | Skill entry points | `/project:trace-query`, `/project:trace-contribute` as slash commands. No additional dependencies — pure prompt + bash script pattern. |
| Shell scripts (bash) | - | Auto-query trigger | Thin wrapper that calls CommonTrace API, formats response as context injection. |
| jq | 1.7.x | JSON parsing in shell | Parse API responses in bash scripts. Standard Linux tool. |

**Skill design:** Auto-query should fire at conversation start (detect context: repo, file, error) and inject matching traces into the system prompt. Explicit `/trace-contribute` is for saving new solutions after Claude Code resolves something. Keep skills thin — all logic lives in the API.

### Reputation Engine

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL (native SQL) | 16.x | Reputation calculations | Wilson score confidence interval computed in SQL. Reputation is a derived value from votes — no separate service needed initially. Materialized views for performance. |
| APScheduler / ARQ | - | Scheduled reputation recalc | Recalculate reputation scores nightly (or on vote events) via background tasks. Not real-time — eventual consistency is fine for reputation. |

**Reputation formula:** Wilson score lower bound (used by Reddit/HN) over raw upvote ratio. `score = (p̂ + z²/2n - z*sqrt(p̂(1-p̂)/n + z²/4n²)) / (1 + z²/n)` where z=1.96 (95% confidence). This prevents new traces with one upvote from ranking above proven traces. Implement in SQL as a generated column or materialized view.

### API Documentation & Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI built-in OpenAPI | - | API docs | Auto-generated Swagger UI at `/docs`, ReDoc at `/redoc`. No extra setup. |
| pytest | 8.x | Test framework | Standard Python testing |
| pytest-asyncio | 0.23.x | Async test support | Required for testing async FastAPI endpoints |
| httpx | 0.27.x | Test client | FastAPI's recommended async test client (`AsyncClient`) |
| factory-boy | 3.x | Test fixtures | Generate Trace, Vote, User fixtures without manual setup |

### Observability

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| structlog | 24.x | Structured logging | JSON logs with trace IDs. Critical for debugging embedding failures, vote anomalies. Integrates with FastAPI middleware. |
| prometheus-fastapi-instrumentator | 7.x | Metrics | Request latency, error rates, embedding call counts. Exposes `/metrics` for Prometheus scraping. |
| Sentry SDK | 2.x | Error tracking | Async-aware, FastAPI integration. Catch and alert on embedding pipeline failures. |

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker + Docker Compose | 26.x / v2 | Local development | Single `docker compose up` runs Postgres (+ pgvector), Redis, API, MCP server. Essential for open source contributor onboarding. |
| uv | 0.4.x | Python package management | 10-100x faster than pip. Lockfiles. Modern Python standard. Use over Poetry (slower, complex) or pip (no lockfiles). |
| GitHub Actions | - | CI/CD | Free for open source. Run tests, linting, build Docker images. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Vector DB | pgvector | Qdrant | Qdrant is excellent but adds operational complexity (second database). Use if pgvector query latency becomes bottleneck at scale. |
| Vector DB | pgvector | Chroma | Chroma is good for prototyping but lacks production reliability story and relational features needed for trace metadata. |
| Vector DB | pgvector | Weaviate | Weaviate is production-grade but heavy. GraphQL interface adds complexity. Overkill for this use case. |
| Task Queue | ARQ | Celery | Celery is sync-first (Celery Beat + workers). ARQ is async-native, matches FastAPI. Celery only if team has existing expertise. |
| ORM | SQLAlchemy 2 async | Tortoise ORM | Tortoise is async-native but smaller ecosystem, fewer StackOverflow answers, less mature migrations. |
| ORM | SQLAlchemy 2 async | SQLModel | SQLModel (by FastAPI author) sits on SQLAlchemy but adds another abstraction layer. Use SQLAlchemy directly for more control. |
| Embedding | OpenAI text-embedding-3-small | Cohere Embed v3 | Cohere is competitive but adds vendor dependency. OpenAI is already likely in the stack. |
| Embedding | OpenAI text-embedding-3-small | Local (Ollama) | High-quality local embeddings require GPU. text-embedding-3-small on CPU API is more practical for most contributors. |
| MCP Framework | FastMCP | Raw MCP SDK | Raw SDK works but FastMCP reduces tool definition boilerplate by ~60%. FastMCP is actively maintained by the community and aligns with SDK direction. |
| Package Manager | uv | Poetry | Poetry is 10-100x slower than uv. uv has become the de facto standard in new Python projects as of 2024-2025. |
| Package Manager | uv | pip + requirements.txt | No lockfiles, no virtual env management. Only acceptable for tiny scripts. |
| Rate Limiting | slowapi | Custom Redis middleware | slowapi is a maintained library that handles the edge cases. Don't reinvent. |
| Auth | python-jose | Authlib | Authlib is more complete for OAuth flows but heavier. python-jose is sufficient for API key JWT. |

---

## Installation

```bash
# Create project with uv
uv init commontrace
cd commontrace

# Core API dependencies
uv add fastapi uvicorn[standard] gunicorn
uv add pydantic sqlalchemy[asyncio] asyncpg alembic
uv add redis arq
uv add httpx tenacity

# Embeddings
uv add openai
uv add sentence-transformers  # local fallback

# Auth & rate limiting
uv add python-jose[cryptography] passlib[bcrypt] slowapi

# Observability
uv add structlog prometheus-fastapi-instrumentator sentry-sdk[fastapi]

# MCP server (separate package/directory)
uv add mcp fastmcp

# Dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov factory-boy
uv add --dev ruff mypy pre-commit

# pgvector extension (in Postgres)
# CREATE EXTENSION IF NOT EXISTS vector;
```

```bash
# Docker services (docker-compose.yml)
services:
  postgres:
    image: pgvector/pgvector:pg16
  redis:
    image: redis:7-alpine
  api:
    build: ./api
  mcp:
    build: ./mcp
```

---

## Version Verification Status

**IMPORTANT:** All versions below are from training data (cutoff August 2025). Verify against PyPI and official docs before pinning in `pyproject.toml`.

| Package | Training Data Version | Verify At |
|---------|----------------------|-----------|
| fastapi | 0.115.x | https://pypi.org/project/fastapi/ |
| pydantic | 2.9.x | https://pypi.org/project/pydantic/ |
| sqlalchemy | 2.0.x | https://pypi.org/project/SQLAlchemy/ |
| asyncpg | 0.29.x | https://pypi.org/project/asyncpg/ |
| pgvector | 0.3.x (Python client) | https://pypi.org/project/pgvector/ |
| pgvector | 0.7.x (Postgres ext) | https://github.com/pgvector/pgvector/releases |
| mcp | 1.x | https://pypi.org/project/mcp/ |
| fastmcp | 2.x | https://pypi.org/project/fastmcp/ |
| arq | 0.25.x | https://pypi.org/project/arq/ |
| openai | 1.x | https://pypi.org/project/openai/ |
| slowapi | 0.1.x | https://pypi.org/project/slowapi/ |
| uv | 0.4.x | https://github.com/astral-sh/uv/releases |
| structlog | 24.x | https://pypi.org/project/structlog/ |

---

## Confidence Levels

| Area | Confidence | Notes |
|------|------------|-------|
| FastAPI as core framework | HIGH | Dominant standard; no serious contender in Python async API space |
| PostgreSQL + pgvector | HIGH | Well-established pattern; pgvector HNSW is production-grade |
| OpenAI embeddings | MEDIUM | API exists and is widely used; pricing/model names may have changed |
| MCP Python SDK (mcp + fastmcp) | MEDIUM | SDK existed and was maintained as of Aug 2025; FastMCP v2 trajectory was clear. Verify current API. |
| ARQ over Celery | MEDIUM | Pattern is sound; ARQ was actively maintained as of Aug 2025 |
| uv as package manager | HIGH | Clear ecosystem shift toward uv was already underway by Aug 2025 |
| Exact package versions | LOW | Training data cutoff; all versions must be verified before use |
| Wilson score for reputation | HIGH | Mathematical formula is stable; implementation in SQL is standard |
| FastMCP v2 API | LOW | FastMCP was evolving rapidly; verify current decorator syntax before building |

---

## Sources

- Training data (cutoff August 2025) — all findings should be verified
- pgvector GitHub: https://github.com/pgvector/pgvector
- FastAPI docs: https://fastapi.tiangolo.com
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- FastMCP: https://github.com/jlowin/fastmcp (verify current maintainer/repo)
- uv: https://github.com/astral-sh/uv
- ARQ: https://arq-docs.helpmanual.io
- Wilson score lower bound: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html
