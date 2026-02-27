"""Pattern trace synthesis service (Principle 2 — Dual Coding).

Generates pattern traces from convergence clusters. When 3+ traces
converge on a similar topic with sufficient trust, a pattern trace
is synthesized structurally (no LLM calls) and linked via
PATTERN_SOURCE relationships.

Pattern traces are auto-validated and attributed to the system user.
"""

import uuid
from collections import Counter

import structlog
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.trace import Trace

log = structlog.get_logger(__name__)

# System user for auto-generated content
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Minimum cluster size and trust for pattern generation
MIN_CLUSTER_SIZE = 3
MIN_CLUSTER_TRUST = 0.5

# Impact level hierarchy for aggregation
_IMPACT_HIERARCHY = {"critical": 4, "high": 3, "normal": 2, "low": 1}


async def generate_pattern_traces(session: AsyncSession) -> int:
    """Generate pattern traces from qualifying convergence clusters.

    Qualifying clusters: >= 3 members, average trust >= 0.5.
    Skips clusters that already have a pattern trace.

    Returns count of pattern traces generated.
    """
    # Find qualifying clusters
    cluster_result = await session.execute(
        text(
            """
            SELECT
                convergence_cluster_id AS cluster_id,
                COUNT(*) AS member_count,
                AVG(trust_score) AS avg_trust
            FROM traces
            WHERE convergence_cluster_id IS NOT NULL
                AND is_flagged = false
                AND trace_type = 'episodic'
            GROUP BY convergence_cluster_id
            HAVING COUNT(*) >= :min_size AND AVG(trust_score) >= :min_trust
            """
        ),
        {"min_size": MIN_CLUSTER_SIZE, "min_trust": MIN_CLUSTER_TRUST},
    )
    clusters = cluster_result.all()

    if not clusters:
        return 0

    generated = 0
    for cluster in clusters:
        cluster_id = cluster.cluster_id

        # Skip if pattern trace already exists for this cluster
        existing = await session.execute(
            select(func.count()).select_from(Trace).where(
                Trace.trace_type == "pattern",
                Trace.convergence_cluster_id == cluster_id,
            )
        )
        if existing.scalar() > 0:
            continue

        # Load top-20 members with tags, ordered by trust
        member_result = await session.execute(
            select(Trace)
            .where(
                Trace.convergence_cluster_id == cluster_id,
                Trace.is_flagged.is_(False),
                Trace.trace_type == "episodic",
            )
            .options(selectinload(Trace.tags))
            .order_by(Trace.trust_score.desc())
            .limit(20)
        )
        members = list(member_result.scalars().all())

        if len(members) < MIN_CLUSTER_SIZE:
            continue

        # Synthesize pattern content
        synth = _synthesize_pattern(members, cluster_id)

        # Create pattern trace
        pattern_trace = Trace(
            title=synth["title"],
            context_text=synth["context"],
            solution_text=synth["solution"],
            trace_type="pattern",
            status="validated",
            trust_score=cluster.avg_trust * 0.8,
            contributor_id=SYSTEM_USER_ID,
            convergence_cluster_id=cluster_id,
            convergence_level=members[0].convergence_level,
            metadata_json=synth["metadata"],
            impact_level=synth["impact_level"],
            memory_temperature="WARM",
            depth_score=min(4, max(m.depth_score for m in members)),
            somatic_intensity=max(m.somatic_intensity for m in members),
        )
        session.add(pattern_trace)
        await session.flush()

        # Create PATTERN_SOURCE relationships to all members
        for member in members:
            await session.execute(
                text(
                    "INSERT INTO trace_relationships "
                    "(id, source_trace_id, target_trace_id, relationship_type, strength) "
                    "VALUES (gen_random_uuid(), :pattern_id, :member_id, 'PATTERN_SOURCE', 1.0) "
                    "ON CONFLICT (source_trace_id, target_trace_id, relationship_type) DO NOTHING"
                ),
                {"pattern_id": str(pattern_trace.id), "member_id": str(member.id)},
            )

        # Link tags (union of member tags, top 10 by frequency)
        tag_counter: Counter = Counter()
        for member in members:
            for tag in member.tags:
                tag_counter[tag.id] += 1

        top_tag_ids = [tid for tid, _ in tag_counter.most_common(10)]
        for tag_id in top_tag_ids:
            await session.execute(
                text(
                    "INSERT INTO trace_tags (trace_id, tag_id) "
                    "VALUES (:trace_id, :tag_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"trace_id": str(pattern_trace.id), "tag_id": str(tag_id)},
            )

        generated += 1
        log.info(
            "pattern_trace_generated",
            cluster_id=str(cluster_id),
            member_count=len(members),
            pattern_trace_id=str(pattern_trace.id),
        )

    return generated


def _synthesize_pattern(members: list, cluster_id: uuid.UUID) -> dict:
    """Structurally synthesize pattern trace content from cluster members.

    No LLM calls — pure structural synthesis:
    - Title: "Pattern: {exemplar title}"
    - Context: aggregated from top-3 members
    - Solution: exemplar solution + alternative snippets
    - Tags: union sorted by frequency, top 10
    - Metadata: cluster info + language/framework from exemplar
    """
    exemplar = members[0]  # Highest trust
    top_3 = members[:3]

    # Title
    title = f"Pattern: {exemplar.title}"
    if len(title) > 500:
        title = title[:497] + "..."

    # Context
    context_parts = [
        f"Observed across {len(members)} traces in convergence cluster.",
        "",
        "Representative contexts:",
    ]
    for i, m in enumerate(top_3, 1):
        snippet = m.context_text[:300]
        if len(m.context_text) > 300:
            snippet += "..."
        context_parts.append(f"\n{i}. {snippet}")

    context = "\n".join(context_parts)

    # Solution
    solution_parts = [exemplar.solution_text]
    alternatives = [m for m in top_3[1:] if m.solution_text != exemplar.solution_text]
    if alternatives:
        solution_parts.append("\n\nAlternative approaches:")
        for m in alternatives:
            snippet = m.solution_text[:200]
            if len(m.solution_text) > 200:
                snippet += "..."
            solution_parts.append(f"\n- {snippet}")

    solution = "\n".join(solution_parts)

    # Impact level: highest from cluster
    impact_level = _aggregate_impact(members)

    # Metadata
    meta = {
        "cluster_id": str(cluster_id),
        "source_count": len(members),
        "exemplar_id": str(exemplar.id),
    }
    exemplar_meta = exemplar.metadata_json or {}
    if exemplar_meta.get("language"):
        meta["language"] = exemplar_meta["language"]
    if exemplar_meta.get("framework"):
        meta["framework"] = exemplar_meta["framework"]

    return {
        "title": title,
        "context": context,
        "solution": solution,
        "metadata": meta,
        "impact_level": impact_level,
    }


def _aggregate_impact(members: list) -> str:
    """Return the highest impact_level from cluster members."""
    best_level = "normal"
    best_rank = _IMPACT_HIERARCHY.get("normal", 2)

    for m in members:
        il = getattr(m, "impact_level", "normal") or "normal"
        rank = _IMPACT_HIERARCHY.get(il, 2)
        if rank > best_rank:
            best_rank = rank
            best_level = il

    return best_level
