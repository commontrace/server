"""Spreading activation service for search result expansion.

After initial ANN + re-ranking, graph neighbors of top results receive
an activation boost. Mimics how human memory activation spreads from
retrieved concepts to associated concepts.

Inspired by DroidClaw's spreading activation on knowledge graphs.

Constraints:
- Single hop only (no recursive activation)
- Max 50 total neighbors fetched
- Only CO_RETRIEVED and SUPERSEDES relationships
- Activation boost capped at 0.15
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Tuning knobs
MAX_ACTIVATION_SOURCES = 20
MAX_TOTAL_NEIGHBORS = 50
MAX_ACTIVATION_BOOST = 0.15
ACTIVATION_DECAY = 0.15


async def fetch_activation_neighbors(
    session: AsyncSession,
    source_ids: list[uuid.UUID],
    exclude_ids: set[uuid.UUID],
) -> list[dict]:
    """Fetch graph neighbors of source traces for spreading activation.

    Single query fetching all neighbors of all sources in one round-trip.
    Filters out flagged traces, unembedded traces, and traces already in results.
    """
    if not source_ids:
        return []

    result = await session.execute(
        text(
            "SELECT tr.source_trace_id, tr.target_trace_id, "
            "tr.relationship_type, tr.strength "
            "FROM trace_relationships tr "
            "JOIN traces t ON t.id = tr.target_trace_id "
            "WHERE tr.source_trace_id = ANY(:source_ids) "
            "AND tr.relationship_type IN ('CO_RETRIEVED', 'SUPERSEDES') "
            "AND t.is_flagged = false "
            "ORDER BY tr.strength DESC "
            "LIMIT :max_neighbors"
        ),
        {
            "source_ids": [str(sid) for sid in source_ids],
            "max_neighbors": MAX_TOTAL_NEIGHBORS,
        },
    )
    rows = result.all()

    neighbors = []
    for row in rows:
        target_id = row.target_trace_id
        if target_id not in exclude_ids:
            neighbors.append({
                "source_trace_id": row.source_trace_id,
                "target_trace_id": row.target_trace_id,
                "relationship_type": row.relationship_type,
                "strength": row.strength,
            })

    return neighbors


def compute_activation_boost(
    source_combined_score: float,
    max_combined_score: float,
    relationship_strength: float,
    max_relationship_strength: float,
) -> float:
    """Compute the activation boost for a neighbor trace.

    Formula: ACTIVATION_DECAY x (source_score / max_score) x normalized_strength
    Capped at MAX_ACTIVATION_BOOST.
    """
    if max_combined_score <= 0 or max_relationship_strength <= 0:
        return 0.0

    score_ratio = source_combined_score / max_combined_score
    strength_ratio = relationship_strength / max_relationship_strength

    boost = ACTIVATION_DECAY * score_ratio * strength_ratio
    return min(boost, MAX_ACTIVATION_BOOST)
