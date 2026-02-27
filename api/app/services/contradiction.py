"""Contradiction and alternative detection service.

Finds traces within the same convergence cluster that offer different
solutions (ALTERNATIVE_TO) or directly conflict (CONTRADICTS).

Uses pgvector cosine distance on solution_embedding (or main embedding
as fallback) to measure solution divergence within clusters.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Minimum cosine distance between solution embeddings to consider them different approaches
ALTERNATIVE_DISTANCE_THRESHOLD = 0.4

# Trust score thresholds for CONTRADICTS (one trusted, one distrusted)
TRUST_HIGH = 1.0
TRUST_LOW = -0.5


async def detect_alternatives(session: AsyncSession) -> int:
    """Detect ALTERNATIVE_TO and CONTRADICTS relationships within convergence clusters.

    For each cluster with 2+ traces that have embeddings:
    - ALTERNATIVE_TO: solution embeddings differ significantly (cosine distance > 0.4)
    - CONTRADICTS: additionally, trust scores conflict (one > 1.0, other < -0.5)

    Uses pgvector <=> operator for distance computation in SQL.
    Upserts with ON CONFLICT DO NOTHING for idempotency.

    Returns count of new relationships created.
    """
    # Find all cluster pairs where solution divergence exceeds threshold
    # Uses solution_embedding if available, falls back to main embedding
    result = await session.execute(
        text(
            """
            WITH cluster_pairs AS (
                SELECT
                    a.id AS trace_a_id,
                    b.id AS trace_b_id,
                    a.trust_score AS trust_a,
                    b.trust_score AS trust_b,
                    COALESCE(a.solution_embedding, a.embedding) <=>
                    COALESCE(b.solution_embedding, b.embedding) AS solution_distance
                FROM traces a
                JOIN traces b ON a.convergence_cluster_id = b.convergence_cluster_id
                    AND a.id < b.id
                WHERE a.convergence_cluster_id IS NOT NULL
                    AND COALESCE(a.solution_embedding, a.embedding) IS NOT NULL
                    AND COALESCE(b.solution_embedding, b.embedding) IS NOT NULL
                    AND a.is_flagged = false
                    AND b.is_flagged = false
            )
            SELECT trace_a_id, trace_b_id, trust_a, trust_b, solution_distance
            FROM cluster_pairs
            WHERE solution_distance > :threshold
            """
        ),
        {"threshold": ALTERNATIVE_DISTANCE_THRESHOLD},
    )
    rows = result.all()

    created = 0
    for row in rows:
        trace_a = row.trace_a_id
        trace_b = row.trace_b_id
        trust_a = row.trust_a
        trust_b = row.trust_b

        # Determine relationship type
        is_contradiction = (
            (trust_a > TRUST_HIGH and trust_b < TRUST_LOW)
            or (trust_b > TRUST_HIGH and trust_a < TRUST_LOW)
        )
        rel_type = "CONTRADICTS" if is_contradiction else "ALTERNATIVE_TO"

        # Upsert both directions
        for src, tgt in [(trace_a, trace_b), (trace_b, trace_a)]:
            result = await session.execute(
                text(
                    "INSERT INTO trace_relationships "
                    "(id, source_trace_id, target_trace_id, relationship_type, strength) "
                    "VALUES (gen_random_uuid(), :src, :tgt, :rel_type, 1.0) "
                    "ON CONFLICT (source_trace_id, target_trace_id, relationship_type) "
                    "DO NOTHING"
                ),
                {"src": str(src), "tgt": str(tgt), "rel_type": rel_type},
            )
            if result.rowcount > 0:
                created += 1

    if created > 0:
        log.info("alternatives_detected", new_relationships=created, pairs_evaluated=len(rows))

    return created
