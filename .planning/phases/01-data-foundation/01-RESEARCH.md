# Phase 1: Data Foundation — Research

**Researched:** 2026-02-20
**Domain:** PostgreSQL schema design, pgvector, SQLAlchemy 2 async ORM, Alembic migrations, Docker Compose
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Trace Schema Design**
- Context and solution fields are both free-form markdown — agents write naturally with code blocks, explanations, steps
- Traces have a required title field (short summary, like a StackOverflow question title)
- Agent model and version captured as metadata on each trace
- Schema must be domain-agnostic — coding agents are the first users, but the data model should work for marketing, research, writing tasks too. Don't hard-code code-specific fields
- Additional metadata fields at Claude's discretion, keeping them general-purpose (not code-specific)

**Tag Taxonomy**
- Hybrid model: core controlled tags (curated list) + free-form user tags (agents create any tag)
- Flat labels (not namespaced/hierarchical) — simple tags like "python", "fastapi", "docker"
- Unlimited tags per trace (no cap)
- Tags are optional when contributing — lower friction for agents, system can suggest/auto-tag later
- Tags normalized: lowercase, trimmed, deduplicated

**Trust State Transitions**
- Two-tier model: pending → validated
- Dynamic validation threshold: starts low (2-3 confirmations), increases as the platform grows. Store threshold as a configurable parameter, not hardcoded
- Validated traces can be demoted back to pending if they accumulate enough downvotes
- Only validated traces appear in search results — pending traces are not surfaced
- Seed traces (curated by humans) are auto-validated on import — no confirmation process needed

**Dev Environment & Project Structure**
- Separate sub-packages within this repo: `api/`, `mcp-server/`, `skill/` — structured independently from day one for clean future splits
- Docker Compose provides: PostgreSQL + pgvector, Redis, FastAPI app (hot reload), ARQ worker
- Pre-loaded fixture data (sample traces) so developers can test immediately — not an empty database
- Planning docs (`.planning/`) live at the repo root

### Claude's Discretion
- Exact fixture data content and quantity for dev
- PostgreSQL schema optimizations (indexes, constraints beyond what's specified)
- Alembic migration configuration approach
- Docker Compose networking and volume setup
- Additional automatic metadata fields (keeping them domain-agnostic)
- Embedding column dimensions and HNSW index parameters

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

## Summary

Phase 1 delivers the stable foundation every downstream phase builds on: a complete PostgreSQL schema with all required tables and columns, pgvector HNSW index for similarity search, SQLAlchemy 2.0 async ORM models, Alembic migrations, and a Docker Compose environment that boots the full stack with pre-loaded fixture data in one command.

The standard stack for this phase is mature and well-documented. SQLAlchemy 2.0 (currently at 2.0.46, released January 2026) with asyncpg as the async driver is the canonical approach for FastAPI + PostgreSQL. Alembic 1.18.4 (released February 2026) provides schema migrations and offers a dedicated `async` template via `alembic init -t async` that handles async engine configuration correctly. pgvector 0.8.1 (the PostgreSQL extension) with the Python client library pgvector 0.4.2 integrates with SQLAlchemy via an event listener on the sync engine.

The most important decisions for this phase are: (1) the schema must include `embedding_model_id` and `embedding_model_version` from day one to prevent later embedding lock-in; (2) the trust state machine (`pending`/`validated`) must be a schema column so Phase 2 can enforce it without migration pain; (3) tag normalization must happen at the ORM/service layer before the database, not via triggers; (4) Alembic must use a named constraint convention so autogenerate can detect constraint changes. These are schema decisions — making them wrong in Phase 1 costs every downstream phase.

**Primary recommendation:** Use the `alembic init -t async` template; define `Base` with SQLAlchemy's naming convention in `MetaData`; register pgvector via `event.listens_for(engine.sync_engine, "connect")`; use `pgvector/pgvector:pg17` Docker image; structure the monorepo as a uv workspace with `api/`, `mcp-server/`, `skill/` as separate workspace members.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.46 | Async ORM, schema definition | The standard Python ORM; 2.0 adds native async support via `AsyncSession`; `DeclarativeBase` + `Mapped[]` type hints are the current canonical pattern |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async Postgres driver for Python; required for SQLAlchemy async mode with `postgresql+asyncpg://` URL scheme |
| Alembic | 1.18.4 | Schema migrations | The SQLAlchemy-native migration tool; has an async template (`alembic init -t async`); autogenerate detects schema changes; required for any production project |
| pgvector (Python) | 0.4.2 | SQLAlchemy/asyncpg vector type support | Official pgvector Python client; provides `Vector` type for SQLAlchemy columns, HNSW index DSL, and async registration via event listener |
| pgvector (PG ext) | 0.8.1 | Vector similarity search in Postgres | Open-source Postgres extension; HNSW index gives good ANN performance without a second database; 0.8.x adds iterative index scans for filtered queries |
| FastAPI | 0.129.0 | Application entry point (minimal in Phase 1) | Already in stack; Phase 1 only needs the app factory and database wiring |
| Pydantic | 2.12.5 | Schema validation | FastAPI-native; define request/response schemas alongside SQLAlchemy models |
| uv | latest | Package management | Workspace support for monorepo; single lockfile across `api/`, `mcp-server/`, `skill/`; significantly faster than pip/poetry |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | latest | Environment variable loading | `.env` file for local dev; all service URLs, DB credentials, secrets |
| factory-boy | 3.x | Dev fixture data generation | Generate realistic sample traces for the pre-loaded fixture dataset; also used in tests |
| structlog | 24.x | Structured logging | Include from Phase 1 — log migration runs, engine events; propagates to Phase 2+ |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLAlchemy 2 async | Tortoise ORM | Tortoise is async-native but smaller ecosystem; fewer Alembic equivalents; SQLAlchemy is the dominant standard |
| SQLAlchemy 2 async | SQLModel | SQLModel (by FastAPI author) wraps SQLAlchemy but adds another abstraction layer; less control; verify active maintenance before using |
| asyncpg | psycopg3 (async) | psycopg3 async is production-ready as of 2024; slightly more standard PostgreSQL driver but asyncpg is faster and more mature with pgvector |
| uv workspace | Multiple repos | Separate repos make cross-package changes painful early on; monorepo with workspace allows shared lockfile and local editable installs |
| Alembic async template | Manual env.py | The `alembic init -t async` template is the official supported path; manual setup works but risks subtle bugs in async context handling |

**Installation:**
```bash
# From repo root — initialize uv workspace
uv init commontrace
cd commontrace

# Core API dependencies (inside api/ sub-package)
cd api
uv add fastapi uvicorn[standard]
uv add sqlalchemy[asyncio] asyncpg alembic
uv add pgvector
uv add pydantic python-dotenv
uv add structlog

# Dev dependencies
uv add --dev pytest pytest-asyncio httpx factory-boy
uv add --dev ruff mypy

# Initialize Alembic with async template
alembic init -t async migrations
```

---

## Architecture Patterns

### Recommended Project Structure

```
commontrace/                          # Repo root
├── pyproject.toml                    # uv workspace root
├── docker-compose.yml                # All services
├── docker-compose.override.yml       # Dev overrides (hot reload volumes)
├── .env.example                      # Environment variable template
├── .planning/                        # Planning docs (at repo root per decision)
│
├── api/                              # FastAPI sub-package (uv workspace member)
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app factory
│   │   ├── config.py                 # Settings (Pydantic BaseSettings)
│   │   ├── database.py               # Engine, session factory, Base
│   │   ├── models/                   # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # DeclarativeBase with naming convention
│   │   │   ├── trace.py              # Trace, TraceStatus enum
│   │   │   ├── user.py               # User
│   │   │   ├── vote.py               # Vote, VoteType enum
│   │   │   └── tag.py                # Tag, TraceTag (join table)
│   │   └── dependencies.py           # get_db() FastAPI dependency
│   ├── migrations/                   # Alembic migrations
│   │   ├── env.py                    # Async env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── fixtures/                     # Dev fixture data
│   │   ├── seed_fixtures.py          # Script to load sample traces
│   │   └── sample_traces.json        # Sample trace content
│   └── tests/
│       ├── conftest.py
│       └── test_models.py
│
├── mcp-server/                       # MCP server sub-package (Phase 5)
│   └── pyproject.toml
│
└── skill/                            # Claude Code skill sub-package (Phase 6)
    └── pyproject.toml
```

### Pattern 1: Monorepo as uv Workspace

**What:** Root `pyproject.toml` declares a `[tool.uv.workspace]` with `members = ["api", "mcp-server", "skill"]`. Each member has its own `pyproject.toml` with independent dependencies. One `uv.lock` file covers all members.

**When to use:** From day one — the decision is locked in the user constraints. Prevents per-package dependency drift.

**Example:**
```toml
# commontrace/pyproject.toml (workspace root)
[project]
name = "commontrace"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["api", "mcp-server", "skill"]
```

```toml
# commontrace/api/pyproject.toml (sub-package)
[project]
name = "commontrace-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.129.0",
    "sqlalchemy[asyncio]>=2.0.46",
    "asyncpg>=0.31.0",
    "alembic>=1.18.4",
    "pgvector>=0.4.2",
    "pydantic>=2.12.5",
    "python-dotenv",
    "structlog",
]
```

### Pattern 2: DeclarativeBase with Naming Convention + AsyncAttrs

**What:** The `Base` class uses `AsyncAttrs` mixin (for async attribute access) and `DeclarativeBase`, configured with a metadata naming convention. All models inherit from this base.

**When to use:** Always — naming conventions are required for Alembic to detect and drop named constraints during autogenerate. `AsyncAttrs` prevents lazy-loading errors in async sessions.

**Example:**
```python
# api/app/models/base.py
# Source: Alembic docs + SQLAlchemy 2.0 asyncio docs
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

### Pattern 3: Async Engine + Session Factory + FastAPI Dependency

**What:** One async engine per application, one session factory, and a `get_db()` generator dependency that yields an `AsyncSession` per request.

**When to use:** Standard FastAPI + SQLAlchemy async wiring. `expire_on_commit=False` is critical — prevents SQLAlchemy from expiring ORM objects after commit, which would trigger lazy loading (forbidden in async sessions).

**Example:**
```python
# api/app/database.py
# Source: SQLAlchemy 2.0 asyncio docs (docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from pgvector.asyncpg import register_vector

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/commontrace"

engine = create_async_engine(DATABASE_URL, echo=False)

# Register pgvector types with asyncpg connection pool
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    dbapi_connection.run_async(register_vector)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db():
    """FastAPI dependency: yields AsyncSession per request."""
    async with async_session_factory() as session:
        yield session
```

### Pattern 4: Alembic Async Migration Setup

**What:** Initialize Alembic with `alembic init -t async migrations` to get the async-aware `env.py` template. Wire `target_metadata` to `Base.metadata` and override the DB URL from app settings.

**When to use:** Required when using asyncpg driver. The async template handles `async_engine_from_config` and `asyncio.run()` automatically. Upgrade/downgrade functions remain synchronous (Alembic limitation).

**Key pitfall:** Import all models in `env.py` before autogenerate runs, or schema changes won't be detected.

**Example:**
```python
# api/migrations/env.py (async template, customized)
# Source: github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.config import settings
from app.models.base import Base

# Import ALL models so autogenerate detects them
from app.models.trace import Trace  # noqa: F401
from app.models.user import User    # noqa: F401
from app.models.vote import Vote    # noqa: F401
from app.models.tag import Tag, TraceTag  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override with app settings (reads from .env)
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Pattern 5: pgvector HNSW Index with SQLAlchemy

**What:** Create the HNSW index using `sqlalchemy.Index` with pgvector-specific DDL options. Use `vector_cosine_ops` as the operator class (matches the cosine similarity queries Phase 3 will use).

**When to use:** Define this index in the Alembic migration, not at model definition time (index creation is DDL, not ORM). Must match the distance operator used at query time.

**Example:**
```python
# api/migrations/versions/0001_initial_schema.py
# Source: pgvector-python README (github.com/pgvector/pgvector-python)
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),  # Null until embedded
        sa.Column("embedding_model_id", sa.String(100), nullable=True),
        sa.Column("embedding_model_version", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("contributor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_model", sa.String(100), nullable=True),    # domain-agnostic
        sa.Column("agent_version", sa.String(50), nullable=True),   # domain-agnostic
        sa.Column("metadata_json", sa.JSON(), nullable=True),       # open-ended extras
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # HNSW index — cosine similarity, 1536 dimensions (text-embedding-3-small)
    # m=16 (default, good for <5M vectors), ef_construction=64 (default)
    # Use m=32/ef_construction=128 if recall requirements increase at scale
    op.execute("""
        CREATE INDEX ix_traces_embedding_hnsw
        ON traces
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # B-tree indexes for common filter queries
    op.create_index("ix_traces_status", "traces", ["status"])
    op.create_index("ix_traces_contributor_id", "traces", ["contributor_id"])
    op.create_index("ix_traces_created_at", "traces", ["created_at"])
```

### Pattern 6: Docker Compose with Hot Reload

**What:** Separate `docker-compose.yml` (base services) and `docker-compose.override.yml` (dev-specific volume mounts and commands). The override file is loaded automatically in local development. The base file is used in CI/production.

**When to use:** This pattern is the Docker Compose convention for dev/prod parity. The API service mounts source code for hot reload; the ARQ worker does the same.

**Example:**
```yaml
# docker-compose.yml (base — all services)
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: commontrace
      POSTGRES_PASSWORD: commontrace
      POSTGRES_DB: commontrace
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U commontrace"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  api:
    build:
      context: ./api
    environment:
      - DATABASE_URL=postgresql+asyncpg://commontrace:commontrace@postgres:5432/commontrace
      - REDIS_URL=redis://redis:6379
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  worker:
    build:
      context: ./api
    command: ["python", "-m", "arq", "app.workers.embed_worker.WorkerSettings"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://commontrace:commontrace@postgres:5432/commontrace
      - REDIS_URL=redis://redis:6379
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

volumes:
  postgres_data:
  redis_data:
```

```yaml
# docker-compose.override.yml (dev — loaded automatically)
services:
  api:
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    volumes:
      - ./api:/app  # hot reload

  worker:
    command: ["python", "-m", "arq", "app.workers.embed_worker.WorkerSettings", "--watch", "/app"]
    volumes:
      - ./api:/app  # hot reload
```

### Anti-Patterns to Avoid

- **Anonymous constraints:** Define all constraints with names (handled by naming convention on `Base.metadata`). PostgreSQL autogenerated names vary by version; Alembic cannot reliably detect changes to anonymous constraints. Always use the naming convention.
- **Hardcoded validation threshold:** The user decision requires a configurable threshold. Store it in a `config` table or environment variable, never as a Python/SQL literal.
- **Triggers for tag normalization:** Use the service/ORM layer for tag normalization (lowercase, trim, deduplicate), not database triggers. Triggers are invisible to application code, hard to test, and complicate migrations.
- **Inline `CREATE EXTENSION` in migrations:** Register `CREATE EXTENSION IF NOT EXISTS vector` as the very first migration. It is idempotent and must exist before any `vector` column can be created.
- **Migrating during app startup:** Running `alembic upgrade head` in FastAPI's `lifespan` event with an async engine is known to fail (context variable is None). Run migrations as a separate Docker Compose command before the app starts, not during startup.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema migrations | Custom SQL scripts with version tracking | Alembic | Handles ordering, conflicts, rollbacks, offline SQL generation, autogenerate from models |
| Vector type support | Custom Postgres type codec | `pgvector` Python library | Handles type registration, serialization, all distance ops, asyncpg event listener pattern |
| HNSW index creation | Raw DDL strings | pgvector SQLAlchemy `Index` DSL | Type-safe, handles operator class selection, integrates with Alembic autogenerate |
| Constraint naming | Manual column/constraint names | SQLAlchemy `MetaData(naming_convention=...)` | Without naming convention, Alembic's autogenerate cannot detect constraint changes |
| Fixture generation | Hardcoded INSERT statements | `factory-boy` with `SQLAlchemyModelFactory` | Declarative, random-but-realistic data, integrates with test sessions |

**Key insight:** Every problem listed here has an established library solution. The schema domain is mature. The only custom logic this phase needs is: (1) tag normalization function, (2) trust state machine transitions, (3) fixture data content. Everything else is configuration of existing tools.

---

## Common Pitfalls

### Pitfall 1: Missing `CREATE EXTENSION` as First Migration

**What goes wrong:** The initial migration creates the `traces` table with a `vector` column, but the `pgvector` extension isn't installed. The migration fails with `ERROR: type "vector" does not exist`.

**Why it happens:** Developers install pgvector in the Docker image (`pgvector/pgvector:pg17`) assuming the extension is active. The extension binary is present, but the extension must be activated per-database with `CREATE EXTENSION`.

**How to avoid:** Create `migrations/versions/0000_enable_pgvector.py` as the very first migration, containing only:
```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

def downgrade():
    op.execute("DROP EXTENSION IF EXISTS vector")
```

**Warning signs:** `ProgrammingError: type "vector" does not exist` on migration run.

---

### Pitfall 2: Not Importing All Models in Alembic env.py

**What goes wrong:** `alembic revision --autogenerate` generates empty migrations even though models have changed. Developers manually write migration SQL they shouldn't need to write.

**Why it happens:** Alembic's autogenerate only detects tables that are registered in `Base.metadata`. If a model file isn't imported before autogenerate runs, its table is invisible. Import statements are often omitted from `env.py` because they "shouldn't be needed" — but they are.

**How to avoid:** In `env.py`, explicitly import every model module after setting `target_metadata`:
```python
# ALL models must be imported — autogenerate inspects Base.metadata at import time
from app.models.trace import Trace       # noqa: F401
from app.models.user import User         # noqa: F401
from app.models.vote import Vote         # noqa: F401
from app.models.tag import Tag, TraceTag # noqa: F401
```

**Warning signs:** `alembic revision --autogenerate` produces migrations with empty `upgrade()` bodies.

---

### Pitfall 3: HNSW Index Operator Class Mismatch

**What goes wrong:** The HNSW index is created with `vector_l2_ops` (L2/Euclidean distance) but queries use `embedding.cosine_distance(query_embedding)` (cosine distance). PostgreSQL cannot use the index for the query, falling back to a sequential scan. Search latency jumps from <10ms to >1000ms at even modest table sizes.

**Why it happens:** The index operator class and the query operator must match. This is non-obvious from the pgvector README — `vector_cosine_ops` and `<=>` (cosine distance) are paired; `vector_l2_ops` and `<->` (L2 distance) are paired.

**How to avoid:** Decide on cosine similarity (recommended for text embeddings — the standard for OpenAI and sentence-transformers outputs). Use `vector_cosine_ops` in the index and `<=>` / `.cosine_distance()` in all queries. Document this pairing in a comment in the migration.

**Warning signs:** Search queries that should use the HNSW index show sequential scans in `EXPLAIN ANALYZE`. A query plan showing `Seq Scan on traces` instead of `Index Scan using ix_traces_embedding_hnsw`.

---

### Pitfall 4: Running Alembic Migrations During FastAPI App Startup

**What goes wrong:** Migrations run inside FastAPI's `lifespan` event handler with an async engine. Context variable is `None` inside `do_run_migrations`. Migrations never execute. The app starts successfully (no exception), but the schema is never applied.

**Why it happens:** Alembic's async migration support uses `asyncio.run()` internally. Running `asyncio.run()` inside an already-running event loop (FastAPI's uvicorn loop) raises `RuntimeError: This event loop is already running`. Even when this is worked around, context propagation fails.

**How to avoid:** Run migrations as a Docker Compose startup command before launching the API process:
```yaml
# docker-compose.yml
api:
  command: >
    sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```
Or as a separate Docker Compose service that runs and exits before `api` starts. Never run in `lifespan`.

**Warning signs:** App starts cleanly but schema changes aren't reflected; `alembic current` shows no migrations applied.

---

### Pitfall 5: Hardcoded Validation Threshold (Against User Decision)

**What goes wrong:** The validation threshold (number of confirmations to transition `pending` → `validated`) is hardcoded as a Python constant or SQL literal. When the platform grows and the threshold needs to change, a code deployment is required.

**Why it happens:** It's the simplest implementation. But the user explicitly decided: store threshold as a configurable parameter.

**How to avoid:** Create a `platform_config` table with key/value pairs, or load from an environment variable with a fallback:
```python
# In app/config.py
validation_threshold: int = Field(default=2, env="VALIDATION_THRESHOLD")
```
The initial Alembic migration can insert the default value into a `platform_config` table if a DB-stored approach is preferred. This allows changing the threshold without a deployment.

**Warning signs:** Any `VALIDATION_THRESHOLD = 2` in a Python file; any `WHERE confirmation_count >= 2` in SQL without a variable reference.

---

### Pitfall 6: Tag Normalization at the Wrong Layer

**What goes wrong:** Tags are normalized by a database trigger or CHECK constraint instead of the application layer. Trigger normalization is invisible during unit tests (which mock the DB), silently passes raw tags in tests but normalizes in production — creating test/prod divergence. CHECK constraints can't perform complex normalization (lowercasing, trimming, canonical lookup).

**How to avoid:** Normalize tags in a pure Python function before any database write:
```python
def normalize_tag(raw: str) -> str:
    """Normalize a tag to its canonical form."""
    return raw.strip().lower()[:50]  # max 50 chars per tag
```

Call this function in the service layer before creating `Tag` records or `TraceTag` rows. Write unit tests directly against this function without a database.

**Warning signs:** Tags table contains mixed-case entries; `"Python"` and `"python"` both appear as distinct rows.

---

## Code Examples

Verified patterns from official sources and current best practices:

### SQLAlchemy 2.0 ORM Model: Trace

```python
# api/app/models/trace.py
# Source: SQLAlchemy 2.0 docs + pgvector-python README
import enum
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, DateTime, func, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from .base import Base


class TraceStatus(str, enum.Enum):
    pending = "pending"
    validated = "validated"
    quarantined = "quarantined"


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str] = mapped_column(Text, nullable=False)
    solution_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Vector embedding — null until background worker processes it
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536), nullable=True
    )
    embedding_model_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    embedding_model_version: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # Trust state machine
    status: Mapped[TraceStatus] = mapped_column(
        String(20), default=TraceStatus.pending, nullable=False
    )
    trust_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confirmation_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Contributor link
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Domain-agnostic agent metadata
    agent_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Open-ended metadata (language, framework, task type — without hardcoding)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    contributor: Mapped["User"] = relationship("User", back_populates="traces")
    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="trace")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="trace_tags", back_populates="traces"
    )
```

### SQLAlchemy 2.0 ORM Model: Tag + TraceTag Join Table

```python
# api/app/models/tag.py
import uuid
from sqlalchemy import String, Boolean, Table, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


# Join table — no ORM class needed unless tracking additional metadata
trace_tags = Table(
    "trace_tags",
    Base.metadata,
    Column("trace_id", UUID(as_uuid=True), ForeignKey("traces.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    is_curated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    traces: Mapped[list["Trace"]] = relationship(
        "Trace", secondary="trace_tags", back_populates="tags"
    )
```

### Dev Fixture Seeding Script

```python
# api/fixtures/seed_fixtures.py
# Run via: docker compose exec api python -m fixtures.seed_fixtures
import asyncio
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session_factory
from app.models.trace import Trace, TraceStatus
from app.models.user import User
from app.models.tag import Tag


async def seed():
    async with async_session_factory() as session:
        # Create a seed user for curated traces
        seed_user = User(
            email="seed@commontrace.dev",
            is_seed=True,
        )
        session.add(seed_user)
        await session.flush()  # get seed_user.id without committing

        # Load fixture data
        fixtures = json.loads(
            (Path(__file__).parent / "sample_traces.json").read_text()
        )

        for fixture in fixtures:
            # Seed traces are auto-validated (user decision: no confirmation process)
            trace = Trace(
                title=fixture["title"],
                context_text=fixture["context"],
                solution_text=fixture["solution"],
                status=TraceStatus.validated,  # auto-validated
                contributor_id=seed_user.id,
            )
            session.add(trace)
            await session.flush()

            # Normalize and attach tags
            for raw_tag in fixture.get("tags", []):
                tag_name = raw_tag.strip().lower()
                tag = await session.get_or_create(Tag, name=tag_name)
                trace.tags.append(tag)

        await session.commit()
        print(f"Seeded {len(fixtures)} traces")


if __name__ == "__main__":
    asyncio.run(seed())
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLAlchemy 1.x sync ORM | SQLAlchemy 2.0 `AsyncSession` + `Mapped[]` type hints | 2023 (2.0 stable) | Async-native; better type safety; required for FastAPI performance |
| `declarative_base()` factory function | `class Base(DeclarativeBase)` | SQLAlchemy 2.0 | Cleaner class hierarchy; better IDE support |
| IVFFlat as default pgvector index | HNSW as default | pgvector 0.5.0 (2023) | HNSW doesn't require training step, better recall, faster queries; IVFFlat only if memory is severely constrained |
| pgvector 0.5.x | pgvector 0.8.1 with iterative index scans | October 2024 | Better filtered ANN queries; more accurate cost estimation so PostgreSQL picks the right index |
| `pip` + `requirements.txt` | `uv` workspaces | 2024–2025 | 10-100x faster installs, lockfiles, monorepo workspace support |
| `alembic init` (sync) | `alembic init -t async` | Alembic 1.11+ | Proper async env.py template; avoids manual async wiring |

**Deprecated/outdated:**
- `declarative_base()`: Still works in SQLAlchemy 2.0 but considered legacy style. Use `class Base(DeclarativeBase)` instead.
- IVFFlat index: Requires training (must specify `lists` count based on row count). Use HNSW unless on severely memory-constrained hardware.
- `asyncio.get_event_loop()`: Deprecated in Python 3.10+. Use `asyncio.run()` at entrypoints only.
- `session.query()` API: Legacy SQLAlchemy 1.x style. Use `select()` + `session.execute()` in all new code.

---

## Open Questions

1. **HNSW Dimensions: 1536 (OpenAI) vs 384 (sentence-transformers) vs multi-model**
   - What we know: The embedding column is `Vector(1536)` to support OpenAI's `text-embedding-3-small`. The local fallback (sentence-transformers `all-MiniLM-L6-v2`) produces 384-dim vectors — incompatible with a 1536-dim HNSW index.
   - What's unclear: How to handle contributors using the local fallback in a shared corpus. Options: (a) refuse 384-dim contributions and require OpenAI key, (b) maintain two separate embedding columns, (c) zero-pad 384 to 1536 (incorrect semantics).
   - Recommendation: For Phase 1, define `Vector(1536)` and accept `nullable=True`. Document in CONTRIBUTING.md that the local fallback produces embeddings that require a separate index. Phase 3 (embedding pipeline) resolves this: the worker always uses the canonical model, local fallback only for self-testing without the worker.

2. **Platform Config Table vs Environment Variable for Validation Threshold**
   - What we know: User decided the threshold must be configurable, not hardcoded. The threshold must be readable at runtime without deployment.
   - What's unclear: Whether to store in a `platform_config` table (survives container restarts, queryable via SQL, requires a migration to change) or environment variable (simple, requires container restart to change).
   - Recommendation: Environment variable with a default of `2`. A `platform_config` table adds complexity for Phase 1 with minimal benefit — the threshold will rarely change, and a container restart is acceptable for a configuration change in early operation.

3. **PostgreSQL 17 vs 16**
   - What we know: `pgvector/pgvector:pg17` and `pgvector/pgvector:pg16` are both available and production-ready. PG17 has vacuum and bulk-load performance improvements over PG16.
   - What's unclear: PG17.0-17.2 had a pgvector compilation issue (fixed in PG17.3). Using `pg17` tag (latest PG17) mitigates this.
   - Recommendation: Use `pgvector/pgvector:pg17` — it is the current standard and the Docker image tag `pg17` always pulls the latest PG17 patch, so PG17.0/17.2 issues are avoided.

---

## Sources

### Primary (HIGH confidence)

- **SQLAlchemy 2.0 asyncio docs** (official, verified 2026-02-20): https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Alembic 1.18.4 async template** (official GitHub, verified 2026-02-20): https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py
- **Alembic naming constraints docs** (official, current): https://alembic.sqlalchemy.org/en/latest/naming.html
- **pgvector-python README** (official GitHub, verified 2026-02-20): https://github.com/pgvector/pgvector-python
- **pgvector 0.8.0 release notes** (official PostgreSQL News, verified 2026-02-20): https://www.postgresql.org/about/news/pgvector-080-released-2952/
- **pgvector Docker Hub** (official, verified 2026-02-20): https://hub.docker.com/r/pgvector/pgvector
- **uv workspaces docs** (official Astral docs, verified 2026-02-20): https://docs.astral.sh/uv/concepts/projects/workspaces/
- **PyPI: SQLAlchemy 2.0.46** (verified 2026-02-20): https://pypi.org/project/SQLAlchemy/
- **PyPI: asyncpg 0.31.0** (verified 2026-02-20): https://pypi.org/project/asyncpg/
- **PyPI: alembic 1.18.4** (verified 2026-02-20): https://pypi.org/project/alembic/
- **PyPI: pgvector 0.4.2** (verified 2026-02-20): https://pypi.org/project/pgvector/
- **PyPI: fastapi 0.129.0** (verified 2026-02-20): https://pypi.org/project/fastapi/
- **PyPI: pydantic 2.12.5** (verified 2026-02-20): https://pypi.org/project/pydantic/

### Secondary (MEDIUM confidence)

- HNSW index parameters for 1536-dim vectors: pgvector DeepWiki + AWS blog post on HNSW configuration (multiple sources agree on m=16/ef_construction=64 defaults; m=32 for higher recall)
- FastAPI + async SQLAlchemy + Alembic project setup: https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/
- pgvector 0.8.1 as latest release (multiple managed platforms report this version, not yet on official PostgreSQL news page at time of research)

### Tertiary (LOW confidence — flag for validation before implementation)

- **ARQ worker hot reload in Docker**: ARQ supports `--watch` flag (cited in multiple examples), but official ARQ docs should be verified before implementation — pattern observed in community examples, not official ARQ docs
- **PostgreSQL 17 compilation fix for pgvector** (PG17.0-17.2 issue): Reported in community posts; using `pgvector/pgvector:pg17` (latest PG17 patch) is the mitigation, which is straightforward to verify

---

## Metadata

**Confidence breakdown:**
- Standard stack (SQLAlchemy, asyncpg, Alembic, pgvector): HIGH — all versions verified on PyPI 2026-02-20; all integration patterns verified against official docs
- Schema design (trace/user/vote/tag tables): HIGH — directly derived from locked user decisions + project research files; no ambiguity
- Alembic async migration pattern: HIGH — official async template verified from GitHub; documented pitfalls (migration during startup, missing model imports) are well-documented in Alembic issue tracker
- pgvector HNSW parameters: MEDIUM — default values (m=16, ef_construction=64) are documented official defaults; tuning recommendations for 1536-dim are from community benchmarks, not official docs
- Docker Compose structure: HIGH — base/override pattern is Docker official convention; service names and volume patterns are standard
- uv workspace setup: HIGH — official uv docs verified 2026-02-20; workspace pattern is actively maintained feature

**Research date:** 2026-02-20
**Valid until:** 2026-05-20 (stable domain; Alembic/SQLAlchemy version updates are semver-stable; pgvector HNSW API is stable post-0.5)
