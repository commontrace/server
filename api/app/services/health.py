"""Knowledge-health analysis for the owner dashboard.

Surfaces the knowledge base's self-maintenance signals in one place — trust
distribution, memory-temperature distribution, convergence clusters, stale
traces, and stored contradiction/alternative relationships. All read-only.

On top of the *stored* signals it runs an **early-warning pass**: the same
pgvector cosine analysis the consolidation "sleep cycle" performs
(context-embedding proximity = same problem, solution-embedding divergence =
different fix, plus near-duplicate clustering), but with small-corpus
thresholds, **un-gated by maturity tier**, computed on demand and never
persisted. The sleep cycle defers convergence/contradiction detection until the
GROWING tier (1,000+ traces); this lets the owner curate conflicts and
duplicates from the very first traces instead.

Reuses the 1536-dim embeddings already stored on each trace. No LLM calls, no
writes, no schema changes — a pure additive view over what already exists.
"""

import re
import uuid
from collections import Counter, defaultdict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_run import ConsolidationRun
from app.models.tag import trace_tags
from app.models.trace import Trace
from app.models.trace_relationship import TraceRelationship

# --- Early-warning thresholds (cosine DISTANCE: 0 = identical, larger = further) ---
# Near-identical content → duplicate candidate.
DUP_DISTANCE = 0.10
# Contexts this close describe the same problem.
SAME_PROBLEM_DISTANCE = 0.25
# Solutions this far apart are divergent fixes (matches contradiction.py).
DIVERGENT_SOLUTION_DISTANCE = 0.40
# Cap rows returned to the dashboard.
MAX_PAIRS = 50
MAX_CLUSTERS = 25

# Temperature tiers in coldest-to-hottest display order.
_TEMP_ORDER = ["HOT", "WARM", "COOL", "COLD", "FROZEN"]

# Cheap, network-free staleness signals over trace text (the sleep cycle's
# PyPI check needs the network; this is a fast heuristic for the dashboard).
# Calibrated to Sentinel's staleness_of: fire only on genuine *age* signals,
# never on subject matter. Deprecation / "no longer works" language was tried
# and dropped — on the curated corpus it flagged the topic ("the old pattern is
# deprecated, use X" is the *current* advice), producing only false positives.

# Known-current MAJOR version per fast-moving lib. A version pin signals age only
# when it sits BELOW the current major; pinning to the current major is normal.
CURRENT_MAJOR = {
    "pydantic": 2, "fastapi": 0, "react": 18, "next": 14, "nextjs": 14,
    "langchain": 0, "sqlalchemy": 2, "vue": 3, "angular": 17, "tailwind": 3,
    "django": 5, "numpy": 2, "pandas": 2, "torch": 2, "tensorflow": 2,
}
# A genuine pin needs an explicit operator (pydantic==1.8); bare prose like
# "Pydantic v1" is a comparative mention, not a dependency pin.
_VERSION_PIN = re.compile(r"\b([a-zA-Z][\w\-]+)\s*(==|>=|~=)\s*v?(\d+)(?:\.\d+)*")
# Figures stamped "as of <year>" (rate limits, pricing, quotas) drift with time.
_ASOF = re.compile(r"\bas of\s+(?:\w+\s+)?(20\d\d)\b", re.IGNORECASE)
_STALE_YEAR_CUTOFF = 2024  # current_year - 2

# Tokenisation for plain-English conflict divergence summaries (Sentinel's
# _divergence_summary): dominant API/library-ish tokens per solution.
_WORD = re.compile(r"[a-zA-Z_][a-zA-Z0-9_\.]{2,}")
_STOP = {
    "the", "and", "for", "with", "you", "use", "using", "this", "that", "from",
    "your", "can", "are", "not", "but", "will", "have", "has", "into", "via",
    "when", "what", "how", "why", "should", "would", "could", "code",
}


# ---------------------------------------------------------------------------
# Pure helpers (no DB) — unit-testable in isolation
# ---------------------------------------------------------------------------
def cluster_pairs(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Union-find the (a_id, b_id) edges into connected components.

    Returns only components with 2+ members, largest first.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    clusters = [sorted(members) for members in groups.values() if len(members) >= 2]
    clusters.sort(key=len, reverse=True)
    return clusters


def text_staleness_reasons(context: str, solution: str) -> list[str]:
    """Network-free staleness signals for a trace's text. Empty list = fine.

    Ports Sentinel's calibrated ``staleness_of``: two signals that indicate
    genuine *age*, not subject matter — an outdated dependency pin (explicit
    operator, below the current major) and a dated "as of <year>" data stamp.
    Deprecation language is intentionally NOT a signal (see module header).
    """
    blob = f"{context or ''}\n{solution or ''}"
    reasons: list[str] = []
    # 1. Outdated dependency pin: explicit operator + below the current major.
    for m in _VERSION_PIN.finditer(blob):
        lib, op, ver = m.group(1), m.group(2), m.group(3)
        cur = CURRENT_MAJOR.get(lib.lower())
        if cur is not None and int(ver) < cur:
            reasons.append(
                f"outdated version pin: {lib}{op}{ver} (current major v{cur})"
            )
            break
    # 2. Dated external data that decays.
    for m in _ASOF.finditer(blob):
        if int(m.group(1)) <= _STALE_YEAR_CUTOFF:
            reasons.append(f"references dated data (“as of {m.group(1)}”)")
            break
    return reasons


def health_score(
    total: int, stale: int, flagged: int, conflicts: int, duplicate_traces: int
) -> int:
    """Composite 0-100 knowledge-health score. Higher = healthier.

    Penalises the share of stale + flagged traces and the presence of
    unresolved conflicts / duplicates. Deliberately simple and legible.
    """
    if total <= 0:
        return 100
    stale_ratio = stale / total
    flagged_ratio = flagged / total
    dup_ratio = duplicate_traces / total
    score = 100.0
    score -= stale_ratio * 30.0
    score -= flagged_ratio * 25.0
    score -= dup_ratio * 20.0
    score -= min(conflicts, 10) * 1.5  # each open conflict shaves a little
    return max(0, min(100, round(score)))


def completeness(solution: str, has_code: bool, tag_count: int) -> float:
    """Heuristic completeness for a trace (ported from Sentinel's dedup).

    Longer solution + fenced code + more tags = more complete. Used to pick the
    canonical "keeper" of a duplicate cluster — the richest member survives.
    """
    score = 0.0
    score += min(len(solution or ""), 1500) / 1500.0
    score += 1.0 if has_code else 0.0
    score += min(tag_count, 5) / 5.0
    return score


def _approach_tokens(solution: str, k: int = 6) -> list[str]:
    """Dominant API/library-ish tokens in a solution (for legible divergence)."""
    words = [w.lower() for w in _WORD.findall(solution or "")]
    words = [w for w in words if w not in _STOP and not w.isdigit()]
    return [w for w, _ in Counter(words).most_common(k)]


def divergence_summary(sol_a: str, sol_b: str) -> str:
    """Plain-English "A favors X; B favors Y" for a conflicting pair.

    Ported from Sentinel's ``_divergence_summary``: contrast the dominant tokens
    of each solution so the owner sees *how* two same-problem fixes diverge
    without reading both in full.
    """
    ta, tb = _approach_tokens(sol_a), _approach_tokens(sol_b)
    only_a = [w for w in ta if w not in tb][:3]
    only_b = [w for w in tb if w not in ta][:3]
    if only_a and only_b:
        return f"A favors {', '.join(only_a)}; B favors {', '.join(only_b)}"
    if only_a:
        return f"A introduces {', '.join(only_a)}; B does not"
    if only_b:
        return f"B introduces {', '.join(only_b)}; A does not"
    return "Solutions diverge but share vocabulary; review manually"


# ---------------------------------------------------------------------------
# DB-backed aggregation
# ---------------------------------------------------------------------------
async def _distribution(db: AsyncSession, column) -> dict[str, int]:
    result = await db.execute(select(column, func.count()).group_by(column))
    return {str(row[0]) if row[0] is not None else "UNCLASSIFIED": int(row[1])
            for row in result.all()}


async def _solutions_map(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    """Solution text for a set of trace ids, in one bulk query (no N+1)."""
    if not ids:
        return {}
    rows = await db.execute(
        select(Trace.id, Trace.solution_text)
        .where(Trace.id.in_([uuid.UUID(i) for i in ids]))
    )
    return {str(tid): (sol or "") for tid, sol in rows.all()}


async def _completeness_map(db: AsyncSession, ids: set[str]) -> dict[str, float]:
    """completeness() per trace id (solution length + fenced code + tag count)."""
    if not ids:
        return {}
    sols = await _solutions_map(db, ids)
    tag_rows = await db.execute(
        select(trace_tags.c.trace_id, func.count())
        .where(trace_tags.c.trace_id.in_([uuid.UUID(i) for i in ids]))
        .group_by(trace_tags.c.trace_id)
    )
    tag_counts = {str(tid): int(c) for tid, c in tag_rows.all()}
    return {
        tid: completeness(sol, "```" in sol, tag_counts.get(tid, 0))
        for tid, sol in sols.items()
    }


async def _duplicate_clusters(db: AsyncSession, titles: dict[str, str]) -> list[dict]:
    """Near-identical trace pairs → clusters (early-warning dedup)."""
    result = await db.execute(
        text(
            """
            SELECT a.id AS a_id, b.id AS b_id,
                   a.embedding <=> b.embedding AS dist
            FROM traces a
            JOIN traces b ON a.id < b.id
            WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
              AND a.is_flagged = false AND b.is_flagged = false
              AND a.embedding <=> b.embedding < :dup
            ORDER BY dist ASC
            """
        ),
        {"dup": DUP_DISTANCE},
    )
    edges: list[tuple[str, str]] = []
    closest: dict[frozenset, float] = {}
    for row in result.all():
        a, b = str(row.a_id), str(row.b_id)
        edges.append((a, b))
        closest[frozenset((a, b))] = float(row.dist)

    raw_clusters = cluster_pairs(edges)[:MAX_CLUSTERS]
    # Canonical "keeper" per cluster = most complete member (one bulk lookup).
    member_ids = {m for members in raw_clusters for m in members}
    comp = await _completeness_map(db, member_ids)
    clusters = []
    for members in raw_clusters:
        # Tightest similarity inside this cluster, for a headline number.
        best = min(
            (closest[frozenset((x, y))]
             for i, x in enumerate(members)
             for y in members[i + 1:]
             if frozenset((x, y)) in closest),
            default=DUP_DISTANCE,
        )
        canonical = max(members, key=lambda m: comp.get(m, 0.0))
        clusters.append({
            "size": len(members),
            "max_similarity": round(1.0 - best, 4),
            "canonical_id": canonical,
            "traces": [{"id": m, "title": titles.get(m, "—"),
                        "canonical": m == canonical} for m in members],
        })
    return clusters


async def _conflict_pairs(db: AsyncSession, titles: dict[str, str]) -> list[dict]:
    """Same problem, divergent fix — early-warning conflict detection."""
    result = await db.execute(
        text(
            """
            SELECT a.id AS a_id, b.id AS b_id,
                   a.trust_score AS trust_a, b.trust_score AS trust_b,
                   COALESCE(a.context_embedding, a.embedding) <=>
                   COALESCE(b.context_embedding, b.embedding) AS ctx_dist,
                   COALESCE(a.solution_embedding, a.embedding) <=>
                   COALESCE(b.solution_embedding, b.embedding) AS sol_dist
            FROM traces a
            JOIN traces b ON a.id < b.id
            WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
              AND a.is_flagged = false AND b.is_flagged = false
              AND (COALESCE(a.context_embedding, a.embedding) <=>
                   COALESCE(b.context_embedding, b.embedding)) < :same
              AND (COALESCE(a.solution_embedding, a.embedding) <=>
                   COALESCE(b.solution_embedding, b.embedding)) > :diverge
              AND (a.embedding <=> b.embedding) >= :dup
            ORDER BY ctx_dist ASC
            LIMIT :lim
            """
        ),
        {
            "same": SAME_PROBLEM_DISTANCE,
            "diverge": DIVERGENT_SOLUTION_DISTANCE,
            "dup": DUP_DISTANCE,
            "lim": MAX_PAIRS,
        },
    )
    rows = result.all()
    # Solution text for every involved trace, one bulk query, for divergence.
    ids = {str(r.a_id) for r in rows} | {str(r.b_id) for r in rows}
    sols = await _solutions_map(db, ids)
    pairs = []
    for row in rows:
        a, b = str(row.a_id), str(row.b_id)
        pairs.append({
            "a": {"id": a, "title": titles.get(a, "—"),
                  "trust": round(float(row.trust_a), 2)},
            "b": {"id": b, "title": titles.get(b, "—"),
                  "trust": round(float(row.trust_b), 2)},
            "problem_similarity": round(1.0 - float(row.ctx_dist), 4),
            "solution_similarity": round(1.0 - float(row.sol_dist), 4),
            "divergence": divergence_summary(sols.get(a, ""), sols.get(b, "")),
        })
    return pairs


async def compute_knowledge_health(db: AsyncSession) -> dict:
    """Assemble the full knowledge-health report for the owner dashboard."""
    total = int((await db.execute(select(func.count()).select_from(Trace))).scalar() or 0)

    # Titles once, for labelling pairs/clusters cheaply.
    title_rows = await db.execute(select(Trace.id, Trace.title))
    titles = {str(tid): title for tid, title in title_rows.all()}

    # --- Trust ---
    trust_rows = await db.execute(
        select(
            func.coalesce(func.avg(Trace.trust_score), 0.0),
            func.coalesce(func.min(Trace.trust_score), 0.0),
            func.coalesce(func.max(Trace.trust_score), 0.0),
            func.count().filter(Trace.trust_score < 0),
            func.count().filter(Trace.trust_score > 0),
            func.count().filter(Trace.is_flagged.is_(True)),
        )
    )
    avg_t, min_t, max_t, distrusted, trusted, flagged = trust_rows.one()

    # --- Temperature (staleness) ---
    temp_dist_raw = await _distribution(db, Trace.memory_temperature)
    temperature = {tier: temp_dist_raw.get(tier, 0) for tier in _TEMP_ORDER}
    if "UNCLASSIFIED" in temp_dist_raw:
        temperature["UNCLASSIFIED"] = temp_dist_raw["UNCLASSIFIED"]
    stale_stored = int((await db.execute(
        select(func.count()).select_from(Trace).where(Trace.is_stale.is_(True))
    )).scalar() or 0)

    # Stale list: stored is_stale + text heuristic, deduped by id.
    stale_list: list[dict] = []
    seen_stale: set[str] = set()
    stored_stale = await db.execute(
        select(Trace.id, Trace.title, Trace.memory_temperature)
        .where(Trace.is_stale.is_(True)).limit(MAX_PAIRS)
    )
    for tid, title, temp in stored_stale.all():
        sid = str(tid)
        seen_stale.add(sid)
        stale_list.append({"id": sid, "title": title,
                           "reason": f"marked stale ({temp or 'FROZEN'})"})
    heuristic_rows = await db.execute(
        select(Trace.id, Trace.title, Trace.context_text, Trace.solution_text)
        .where(Trace.is_stale.is_(False)).limit(500)
    )
    for tid, title, ctx, sol in heuristic_rows.all():
        sid = str(tid)
        if sid in seen_stale:
            continue
        reasons = text_staleness_reasons(ctx, sol)
        if reasons:
            stale_list.append({"id": sid, "title": title, "reason": "; ".join(reasons)})
        if len(stale_list) >= MAX_PAIRS:
            break

    # --- Convergence (stored duplicate/cluster signal) ---
    conv_clusters = int((await db.execute(
        select(func.count(func.distinct(Trace.convergence_cluster_id)))
        .where(Trace.convergence_cluster_id.is_not(None))
    )).scalar() or 0)
    conv_levels = await _distribution(db, Trace.convergence_level)

    # --- Stored relationships (what the sleep cycle already found) ---
    rel_rows = await db.execute(
        select(TraceRelationship.relationship_type, func.count())
        .group_by(TraceRelationship.relationship_type)
    )
    relationships = {rt: int(c) for rt, c in rel_rows.all()}

    # --- Early-warning pass (Sentinel layer) ---
    duplicate_clusters = await _duplicate_clusters(db, titles)
    conflicts = await _conflict_pairs(db, titles)
    duplicate_traces = sum(c["size"] for c in duplicate_clusters)

    # --- Last sleep cycle ---
    last_run_row = await db.execute(
        select(ConsolidationRun)
        .order_by(ConsolidationRun.started_at.desc())
        .limit(1)
    )
    last_run = last_run_row.scalar_one_or_none()
    last_consolidation = None
    if last_run is not None:
        last_consolidation = {
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
            "status": last_run.status,
            "stats": last_run.stats_json or {},
        }

    stale_total = len(stale_list)
    score = health_score(total, stale_total, int(flagged), len(conflicts), duplicate_traces)

    return {
        "total_traces": total,
        "health_score": score,
        "trust": {
            "avg": round(float(avg_t), 3),
            "min": round(float(min_t), 3),
            "max": round(float(max_t), 3),
            "distrusted": int(distrusted),
            "trusted": int(trusted),
            "flagged": int(flagged),
        },
        "temperature": temperature,
        "stale": {"count": stale_total, "stored": stale_stored, "traces": stale_list},
        "convergence": {"clusters": conv_clusters, "levels": conv_levels},
        "relationships": relationships,
        "early_warning": {
            "note": (
                "Conflict and duplicate detection runs on demand at every scale. "
                "The background sleep cycle defers this to the GROWING tier "
                "(1,000+ traces); here it curates from trace #1."
            ),
            "conflicts": conflicts,
            "duplicate_clusters": duplicate_clusters,
            "thresholds": {
                "duplicate_distance": DUP_DISTANCE,
                "same_problem_distance": SAME_PROBLEM_DISTANCE,
                "divergent_solution_distance": DIVERGENT_SOLUTION_DISTANCE,
            },
        },
        "last_consolidation": last_consolidation,
    }
