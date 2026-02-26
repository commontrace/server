"""Hybrid semantic + tag search endpoint.

POST /api/v1/traces/search -- search traces by natural language query, tags, or both.

Search modes:
  - Semantic-only (q provided, tags empty): cosine ANN over pgvector embeddings, trust re-ranked
  - Tag-only (q omitted, tags provided): SQL filter ordered by trust_score DESC, no embed call
  - Hybrid (q + tags): cosine ANN with tag pre-filter, trust re-ranked
  - Both empty: 422 validation error
"""

import asyncio
import math
import time
import uuid as uuid_mod
import structlog
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from prometheus_client import Counter, Histogram
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit
from app.schemas.search import (
    RelatedTrace,
    TraceSearchRequest,
    TraceSearchResult,
    TraceSearchResponse,
)
from app.models.trace import Trace
from app.models.tag import Tag, trace_tags
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.activation import (
    fetch_activation_neighbors,
    compute_activation_boost,
    MAX_ACTIVATION_SOURCES,
)
from app.services.context import compute_context_alignment
from app.services.decay import temporal_decay_factor
from app.services.embedding import EmbeddingService, EmbeddingSkippedError
from app.services.retrieval import record_co_retrievals, record_retrieval_logs, record_retrievals
from app.services.tags import normalize_tag
from app.services.temperature import get_temperature_multiplier

# Track background tasks to prevent GC before completion
_background_tasks: set[asyncio.Task] = set()


def _track_task(coro) -> None:
    """Create a tracked background task that removes itself when done."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

log = structlog.get_logger()
_embedding_svc = EmbeddingService()

# Search metrics (defined here; 03-03 may consolidate into app.metrics)
search_requests = Counter(
    "commontrace_search_requests_total",
    "Total search requests",
    ["has_tags"],
)
search_duration = Histogram(
    "commontrace_search_duration_seconds",
    "End-to-end search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

router = APIRouter(prefix="/api/v1", tags=["search"])

# Over-fetch from ANN before re-ranking to ensure we have enough candidates
SEARCH_LIMIT_ANN = 100


async def _apply_spreading_activation(
    db: AsyncSession,
    results: list[TraceSearchResult],
    limit: int,
    searcher_fp: Optional[dict],
    now_utc: datetime,
    query_vector: Optional[list[float]],
) -> list[TraceSearchResult]:
    """Boost graph neighbors of top results via spreading activation.

    Takes top-N results as activation sources, fetches their neighbors from
    trace_relationships, scores each neighbor, and merges into results.
    Short-circuits if no neighbors found. Adds at most 2 DB queries.
    """
    source_ids = [r.id for r in results[:MAX_ACTIVATION_SOURCES]]
    existing_ids = {r.id for r in results}

    neighbors = await fetch_activation_neighbors(db, source_ids, existing_ids)
    if not neighbors:
        return results

    # Load full Trace objects for neighbors
    neighbor_ids = [n["target_trace_id"] for n in neighbors]
    neighbor_result = await db.execute(
        select(Trace)
        .where(Trace.id.in_(neighbor_ids))
        .options(selectinload(Trace.tags))
    )
    neighbor_traces = {t.id: t for t in neighbor_result.scalars().all()}

    # Build lookup: source score by ID for activation boost calculation
    score_by_id = {r.id: r.combined_score for r in results}
    max_score = max(score_by_id.values()) if score_by_id else 1.0
    max_strength = max((n["strength"] for n in neighbors), default=1.0)

    for n in neighbors:
        trace = neighbor_traces.get(n["target_trace_id"])
        if trace is None or trace.id in existing_ids:
            continue

        # Base score using same factors as main ranking
        trust = math.log1p(max(0.0, trace.trust_score) + 1)
        depth = 1 + 0.1 * trace.depth_score
        decay = temporal_decay_factor(
            trace.created_at, trace.last_retrieved_at, trace.half_life_days,
        )
        ctx_boost = 1.0
        if searcher_fp and trace.context_fingerprint:
            alignment = compute_context_alignment(searcher_fp, trace.context_fingerprint)
            ctx_boost = 1.0 + 0.3 * alignment
        convergence_boost = 1.0
        if trace.convergence_level is not None:
            convergence_boost = 1.0 + 0.05 * (4 - trace.convergence_level)
        temp_mult = get_temperature_multiplier(trace.memory_temperature)
        validity_factor = 1.0
        if trace.valid_until is not None and trace.valid_until < now_utc:
            validity_factor = 0.5

        # Cosine similarity (0.0 if no query vector / no embedding)
        sim = 0.0
        if query_vector is not None and trace.embedding is not None:
            # Approximate: use trust-based score without similarity
            # (computing cosine in Python is too slow for a hot path)
            pass

        base = trust * depth * decay * ctx_boost * convergence_boost * temp_mult * validity_factor

        # Activation boost from source
        source_score = score_by_id.get(n["source_trace_id"], 0.0)
        boost = compute_activation_boost(source_score, max_score, n["strength"], max_strength)
        combined = base * (1.0 + boost)

        tag_names = [tag.name for tag in trace.tags]
        results.append(
            TraceSearchResult(
                id=trace.id,
                title=trace.title,
                context_text=trace.context_text,
                solution_text=trace.solution_text,
                trust_score=trace.trust_score,
                status=trace.status,
                tags=tag_names,
                similarity_score=sim,
                combined_score=combined,
                contributor_id=trace.contributor_id,
                created_at=trace.created_at,
                retrieval_count=trace.retrieval_count,
                depth_score=trace.depth_score,
                context_fingerprint=trace.context_fingerprint,
                convergence_level=trace.convergence_level,
                memory_temperature=trace.memory_temperature,
                valid_from=trace.valid_from,
                valid_until=trace.valid_until,
            )
        )
        existing_ids.add(trace.id)

    # Re-sort by combined score and trim to limit
    results.sort(key=lambda r: r.combined_score, reverse=True)
    return results[:limit]


@router.post("/traces/search", response_model=TraceSearchResponse)
async def search_traces(
    body: TraceSearchRequest,
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> TraceSearchResponse:
    """Search traces by natural language query, tags, or both.

    Search modes:
    - q only: cosine ANN over pgvector embeddings, trust-weighted re-ranking
    - tags only: SQL tag filter ordered by trust_score DESC (no embedding service call)
    - q + tags: cosine ANN with tag pre-filter, trust-weighted re-ranking
    - neither: 422 validation error

    Flagged traces are always excluded. Traces with embedding IS NULL are excluded
    only when q is provided (semantic ranking requires an embedding).
    """
    start = time.monotonic()
    search_requests.labels(has_tags=str(bool(body.tags)).lower()).inc()

    # Step A: Embed the query text (only when q is provided)
    query_vector: Optional[list[float]] = None
    if body.q is not None:
        try:
            query_vector, _, _ = await _embedding_svc.embed(body.q)
        except EmbeddingSkippedError:
            raise HTTPException(
                status_code=503,
                detail="Search unavailable — embedding service not configured (OPENAI_API_KEY required)",
            )
    else:
        # Tag-only mode: validate that at least tags are provided
        if not body.tags:
            raise HTTPException(
                status_code=422,
                detail="At least one of 'q' or 'tags' must be provided",
            )

    # Step B: Set HNSW search parameters (only when using vector search)
    if query_vector is not None:
        await db.execute(text("SET LOCAL hnsw.ef_search = 64"))

    # Extract searcher context and expiry preferences
    searcher_fp = body.context
    include_expired = body.include_expired
    now_utc = datetime.now(timezone.utc)

    # Normalize tags for consistent matching
    normalized_tags = [normalize_tag(t) for t in body.tags]

    results: list[TraceSearchResult] = []

    if query_vector is not None:
        # Step C Path 1: Semantic search (q is provided, query_vector exists)
        distance_col = Trace.embedding.cosine_distance(query_vector).label("distance")

        stmt = (
            select(Trace, distance_col)
            .where(Trace.embedding.is_not(None))
            .where(Trace.embedding_model_id == "text-embedding-3-small")
            .where(Trace.is_flagged.is_(False))
            .options(selectinload(Trace.tags))
            .order_by(distance_col)
            .limit(SEARCH_LIMIT_ANN)
        )

        # Exclude expired traces when include_expired=False
        if not include_expired:
            from sqlalchemy import or_
            stmt = stmt.where(
                or_(Trace.valid_until.is_(None), Trace.valid_until >= now_utc)
            )

        # Step D: Tag pre-filter (if tags provided) — Path 1
        if normalized_tags:
            stmt = (
                stmt
                .join(trace_tags, trace_tags.c.trace_id == Trace.id)
                .join(Tag, Tag.id == trace_tags.c.tag_id)
                .where(Tag.name.in_(normalized_tags))
                .group_by(Trace.id, Trace.embedding.cosine_distance(query_vector))
                .having(func.count(func.distinct(Tag.id)) == len(normalized_tags))
            )

        # Step E: Execute and re-rank
        result = await db.execute(stmt)
        rows = result.all()  # list of Row(Trace, distance)

        # Trust-weighted re-ranking with depth, decay, context, convergence, temperature, validity
        def _rank_score(r):
            sim = 1.0 - r.distance
            trust = math.log1p(max(0.0, r.Trace.trust_score) + 1)
            depth = 1 + 0.1 * r.Trace.depth_score
            decay = temporal_decay_factor(
                r.Trace.created_at,
                r.Trace.last_retrieved_at,
                r.Trace.half_life_days,
            )
            ctx_boost = 1.0
            if searcher_fp and r.Trace.context_fingerprint:
                alignment = compute_context_alignment(searcher_fp, r.Trace.context_fingerprint)
                ctx_boost = 1.0 + 0.3 * alignment
            convergence_boost = 1.0
            if r.Trace.convergence_level is not None:
                convergence_boost = 1.0 + 0.05 * (4 - r.Trace.convergence_level)
            temp_mult = get_temperature_multiplier(r.Trace.memory_temperature)
            validity_factor = 1.0
            if r.Trace.valid_until is not None and r.Trace.valid_until < now_utc:
                validity_factor = 0.5
            return sim * trust * depth * decay * ctx_boost * convergence_boost * temp_mult * validity_factor

        ranked = sorted(rows, key=_rank_score, reverse=True)[:body.limit]

        # Step F: Serialize response — Path 1 (semantic)
        for row in ranked:
            similarity = 1.0 - row.distance
            combined = _rank_score(row)
            tag_names = [tag.name for tag in row.Trace.tags]
            results.append(
                TraceSearchResult(
                    id=row.Trace.id,
                    title=row.Trace.title,
                    context_text=row.Trace.context_text,
                    solution_text=row.Trace.solution_text,
                    trust_score=row.Trace.trust_score,
                    status=row.Trace.status,
                    tags=tag_names,
                    similarity_score=similarity,
                    combined_score=combined,
                    contributor_id=row.Trace.contributor_id,
                    created_at=row.Trace.created_at,
                    retrieval_count=row.Trace.retrieval_count,
                    depth_score=row.Trace.depth_score,
                    context_fingerprint=row.Trace.context_fingerprint,
                    convergence_level=row.Trace.convergence_level,
                    memory_temperature=row.Trace.memory_temperature,
                    valid_from=row.Trace.valid_from,
                    valid_until=row.Trace.valid_until,
                )
            )

    else:
        # Step C Path 2: Tag-only search (q is None)
        # Over-fetch 100 for re-ranking with decay/depth, then trim to limit
        stmt = (
            select(Trace)
            .where(Trace.is_flagged.is_(False))
            .options(selectinload(Trace.tags))
            .order_by(Trace.trust_score.desc())
            .limit(100)
        )

        # Exclude expired traces when include_expired=False
        if not include_expired:
            from sqlalchemy import or_
            stmt = stmt.where(
                or_(Trace.valid_until.is_(None), Trace.valid_until >= now_utc)
            )

        # Step D: Tag pre-filter (if tags provided) — Path 2
        if normalized_tags:
            stmt = (
                stmt
                .join(trace_tags, trace_tags.c.trace_id == Trace.id)
                .join(Tag, Tag.id == trace_tags.c.tag_id)
                .where(Tag.name.in_(normalized_tags))
                .group_by(Trace.id)
                .having(func.count(func.distinct(Tag.id)) == len(normalized_tags))
            )

        # Step E: Execute and re-rank with depth + decay
        result = await db.execute(stmt)
        rows_tag_only = result.scalars().all()

        def _tag_rank_score(t):
            trust = math.log1p(max(0.0, t.trust_score) + 1)
            depth = 1 + 0.1 * t.depth_score
            decay = temporal_decay_factor(t.created_at, t.last_retrieved_at, t.half_life_days)
            ctx_boost = 1.0
            if searcher_fp and t.context_fingerprint:
                alignment = compute_context_alignment(searcher_fp, t.context_fingerprint)
                ctx_boost = 1.0 + 0.3 * alignment
            convergence_boost = 1.0
            if t.convergence_level is not None:
                convergence_boost = 1.0 + 0.05 * (4 - t.convergence_level)
            temp_mult = get_temperature_multiplier(t.memory_temperature)
            validity_factor = 1.0
            if t.valid_until is not None and t.valid_until < now_utc:
                validity_factor = 0.5
            return trust * depth * decay * ctx_boost * convergence_boost * temp_mult * validity_factor

        rows_tag_only = sorted(rows_tag_only, key=_tag_rank_score, reverse=True)[:body.limit]

        # Step F: Serialize response — Path 2 (tag-only)
        for trace in rows_tag_only:
            similarity = 0.0  # No semantic similarity in tag-only mode
            combined = _tag_rank_score(trace)
            tag_names = [tag.name for tag in trace.tags]
            results.append(
                TraceSearchResult(
                    id=trace.id,
                    title=trace.title,
                    context_text=trace.context_text,
                    solution_text=trace.solution_text,
                    trust_score=trace.trust_score,
                    status=trace.status,
                    tags=tag_names,
                    similarity_score=similarity,
                    combined_score=combined,
                    contributor_id=trace.contributor_id,
                    created_at=trace.created_at,
                    retrieval_count=trace.retrieval_count,
                    depth_score=trace.depth_score,
                    context_fingerprint=trace.context_fingerprint,
                    convergence_level=trace.convergence_level,
                    memory_temperature=trace.memory_temperature,
                    valid_from=trace.valid_from,
                    valid_until=trace.valid_until,
                )
            )

    # Step G: Spreading activation — graph neighbors of top results get a boost
    if results:
        results = await _apply_spreading_activation(
            db, results, body.limit, searcher_fp, now_utc, query_vector,
        )

    # Fire-and-forget: record retrievals + co-retrieval patterns
    # Tasks are tracked in _background_tasks set to prevent GC before completion
    if results:
        trace_ids = [r.id for r in results]
        search_session_id = str(uuid_mod.uuid4())
        _track_task(record_retrievals(trace_ids))
        _track_task(record_retrieval_logs(trace_ids, search_session_id))
        _track_task(record_co_retrievals(trace_ids))

    # Attach related traces (top 3 per result by relationship strength)
    if results:
        result_ids = [r.id for r in results]
        related_rows = await db.execute(
            text(
                "SELECT tr.source_trace_id, tr.target_trace_id, tr.relationship_type, "
                "tr.strength, t.title "
                "FROM trace_relationships tr "
                "JOIN traces t ON t.id = tr.target_trace_id "
                "WHERE tr.source_trace_id = ANY(:ids) "
                "ORDER BY tr.strength DESC"
            ),
            {"ids": result_ids},
        )
        # Group by source, take top 3 per result
        related_by_source: dict[str, list[RelatedTrace]] = {}
        for row in related_rows:
            src = str(row.source_trace_id)
            if src not in related_by_source:
                related_by_source[src] = []
            if len(related_by_source[src]) < 3:
                related_by_source[src].append(
                    RelatedTrace(
                        id=row.target_trace_id,
                        title=row.title,
                        relationship_type=row.relationship_type,
                        strength=row.strength,
                    )
                )
        for r in results:
            r.related_traces = related_by_source.get(str(r.id), [])

    # Step H: Search metrics instrumentation
    search_duration.observe(time.monotonic() - start)
    log.info(
        "search_executed",
        query_len=len(body.q) if body.q else 0,
        tag_count=len(body.tags),
        result_count=len(results),
    )

    return TraceSearchResponse(results=results, total=len(results), query=body.q)
