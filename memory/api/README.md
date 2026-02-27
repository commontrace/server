# API — FastAPI Backend

## Tech Stack

- FastAPI + uvicorn (async)
- SQLAlchemy async + asyncpg
- PostgreSQL + pgvector (1536-dim, HNSW index)
- Redis (rate limiting)
- OpenAI text-embedding-3-small (only LLM cost)
- Alembic (migrations at `api/migrations/versions/`)

## Key Endpoints

- `POST /api/v1/keys` — provision API key (no auth)
- `POST /api/v1/traces` — submit trace (requires email)
- `POST /api/v1/traces/search` — semantic search
- `GET /api/v1/traces/{id}` — fetch trace
- `POST /api/v1/traces/{id}/vote` — up/down vote
- `POST /api/v1/traces/{id}/amend` — propose improved solution
- `GET /api/v1/tags` — list available tags
- `POST /api/v1/telemetry/triggers` — anonymized trigger stats

## Search Ranking Formula

```
score = similarity * trust * depth * decay * ctx_boost * convergence * temp_mult * validity * somatic_mult
```

### Key Signals

- **somatic_intensity** (0.0-1.0): Damasio-inspired — how intensely knowledge was learned. Computed at ingestion from detection metadata (pattern, error_count, time, iterations). Up to +30% search boost.
- **memory_temperature** (HOT/WARM/COOL/COLD/FROZEN): Activity-based retrieval priority
- **convergence_level** (0-4): Cross-context validation (encoding variability)
- **depth_score** (0-4): Trace richness (levels of processing)
- **context_fingerprint**: Language/framework/OS fingerprint for alignment boosting

## Models

- `Trace` — core knowledge unit (title, context_text, solution_text, tags, embedding)
- `TraceRelationship` — SUPERSEDES, CONTRADICTS, RELATED
- `RetrievalLog` — tracks every search for decay/temperature updates
- `TagTrend` — tag popularity over time
- `RifShadow` — RIF (retrieval-induced forgetting) tracking

## Workers

- `embedding_worker.py` — generates embeddings for new traces (async)
- `consolidation_worker.py` — periodic maintenance (temperature updates, convergence detection)

## Services

- `retrieval.py` — search + ranking logic
- `enrichment.py` — depth_score, somatic_intensity computation at ingestion
- `activation.py` — spreading activation on retrieval
- `rif.py` — retrieval-induced forgetting
- `diversity.py` — result diversification
- `contradiction.py` — contradiction detection between traces
- `trends.py` — tag trend tracking
- `pattern_synthesis.py` — pattern-level analysis
