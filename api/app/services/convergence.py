"""Convergence detection service.

Discovers when different contexts converge on the same solution and
classifies the convergence level:
  0 = universal (cross-language)
  1 = ecosystem (same language family)
  2 = stack (same language, different framework)
  3 = environment (same language + framework, different OS)
  4 = contextual (single context)

Runs as part of the consolidation worker sleep cycle.
"""

import uuid as uuid_mod

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trace import Trace

log = structlog.get_logger(__name__)

# Cosine distance threshold for considering traces as solving the same problem
_SIMILARITY_THRESHOLD = 0.15


def classify_convergence_level(cluster_fingerprints: list[dict]) -> int:
    """Classify convergence level from context fingerprints in a cluster.

    Args:
        cluster_fingerprints: All context fingerprints from traces in a cluster.

    Returns:
        0-4 convergence level.
    """
    if not cluster_fingerprints:
        return 4  # No context = contextual by default

    # Collect unique values per field
    languages = {fp.get("language") for fp in cluster_fingerprints if fp.get("language")}
    frameworks = {fp.get("framework") for fp in cluster_fingerprints if fp.get("framework")}
    oses = {fp.get("os") for fp in cluster_fingerprints if fp.get("os")}

    # Different languages solving same problem → universal
    if len(languages) > 1:
        return 0

    # Same language, but different ecosystem signals → ecosystem
    # (e.g., all Python but very different frameworks/environments)
    if len(languages) == 1 and len(frameworks) > 1:
        return 2  # Stack-agnostic (same language, different framework)

    # Same language + framework, different OS → environment-agnostic
    if len(languages) <= 1 and len(frameworks) <= 1 and len(oses) > 1:
        return 3

    # Everything the same → contextual (single context)
    return 4


async def detect_convergence_clusters(session: AsyncSession) -> int:
    """Detect convergence clusters using pgvector similarity.

    Groups traces with very similar content embeddings into clusters,
    then classifies each cluster's convergence level.

    Returns:
        Count of newly clustered traces.
    """
    # Find traces with embeddings that haven't been clustered yet
    unclustered = await session.execute(
        select(Trace.id, Trace.context_fingerprint)
        .where(Trace.embedding.is_not(None))
        .where(Trace.convergence_cluster_id.is_(None))
    )
    unclustered_traces = unclustered.all()

    if not unclustered_traces:
        return 0

    newly_clustered = 0

    for trace_row in unclustered_traces:
        trace_id = trace_row.id

        # Check if this trace was clustered in a previous iteration of this loop
        check = await session.execute(
            select(Trace.convergence_cluster_id).where(Trace.id == trace_id)
        )
        current_cluster = check.scalar_one_or_none()
        if current_cluster is not None:
            continue

        # Find similar traces within cosine distance threshold
        neighbors = await session.execute(
            text(
                "SELECT t.id, t.convergence_cluster_id, t.context_fingerprint "
                "FROM traces t "
                "WHERE t.embedding IS NOT NULL "
                "AND t.id != :trace_id "
                "AND t.embedding <=> (SELECT embedding FROM traces WHERE id = :trace_id) < :threshold "
                "LIMIT 50"
            ),
            {"trace_id": str(trace_id), "threshold": _SIMILARITY_THRESHOLD},
        )
        neighbor_rows = neighbors.all()

        if not neighbor_rows:
            continue  # No similar traces — skip

        # Greedy clustering: join existing cluster if any neighbor has one
        existing_cluster_id = None
        for n in neighbor_rows:
            if n.convergence_cluster_id is not None:
                existing_cluster_id = n.convergence_cluster_id
                break

        cluster_id = existing_cluster_id or uuid_mod.uuid4()

        # Collect all fingerprints for classification
        all_fingerprints = []
        trace_fp_result = await session.execute(
            select(Trace.context_fingerprint).where(Trace.id == trace_id)
        )
        trace_fp = trace_fp_result.scalar_one_or_none()
        if trace_fp:
            all_fingerprints.append(trace_fp)

        # Gather neighbor fingerprints
        neighbor_ids = [n.id for n in neighbor_rows]
        for n in neighbor_rows:
            if n.context_fingerprint:
                all_fingerprints.append(n.context_fingerprint)

        # If joining existing cluster, also gather fingerprints from existing cluster members
        if existing_cluster_id:
            existing_members = await session.execute(
                select(Trace.context_fingerprint)
                .where(Trace.convergence_cluster_id == existing_cluster_id)
                .where(Trace.context_fingerprint.is_not(None))
            )
            for row in existing_members:
                all_fingerprints.append(row.context_fingerprint)

        # Classify convergence level
        level = classify_convergence_level(all_fingerprints)

        # Assign this trace to the cluster
        await session.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(convergence_cluster_id=cluster_id, convergence_level=level)
        )
        newly_clustered += 1

        # Also assign unclustered neighbors to this cluster
        for n in neighbor_rows:
            if n.convergence_cluster_id is None:
                await session.execute(
                    update(Trace)
                    .where(Trace.id == n.id)
                    .values(convergence_cluster_id=cluster_id, convergence_level=level)
                )
                newly_clustered += 1

        # Update convergence level for all members of this cluster
        await session.execute(
            update(Trace)
            .where(Trace.convergence_cluster_id == cluster_id)
            .values(convergence_level=level)
        )

        log.info(
            "convergence_cluster_updated",
            cluster_id=str(cluster_id),
            level=level,
            member_count=len(neighbor_rows) + 1,
        )

    await session.flush()
    return newly_clustered
