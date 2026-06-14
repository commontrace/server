"""Read-only access to the CommonTrace Postgres for the contribution digest.

Only stable columns are selected. All SQL is isolated here so schema coupling
has one place to change (see design 'Known tradeoff')."""
from __future__ import annotations

PENDING_SQL = """
    SELECT t.id, t.title, t.context_text, t.solution_text,
           t.confirmation_count, t.created_at,
           COALESCE(u.display_name, u.email, 'unknown') AS contributor
    FROM traces t
    LEFT JOIN users u ON u.id = t.contributor_id
    WHERE t.status = 'pending'
    ORDER BY t.created_at ASC
    LIMIT 200
"""

FLAGGED_SQL = """
    SELECT t.id, t.title, t.flagged_at, t.metadata_json
    FROM traces t
    WHERE t.is_flagged = true
    ORDER BY t.flagged_at ASC
    LIMIT 200
"""

AMENDMENTS_SQL = """
    SELECT a.id, a.original_trace_id, a.improved_solution, a.explanation,
           a.created_at,
           COALESCE(u.display_name, u.email, 'unknown') AS submitter
    FROM amendments a
    LEFT JOIN users u ON u.id = a.submitter_id
    ORDER BY a.created_at ASC
    LIMIT 200
"""


async def query_review_data(conn) -> dict:
    """Run the three read-only queries against an open connection (injectable)."""
    pending = await conn.fetch(PENDING_SQL)
    flagged = await conn.fetch(FLAGGED_SQL)
    amendments = await conn.fetch(AMENDMENTS_SQL)
    return {
        "pending_traces": [dict(r) for r in pending],
        "flagged_traces": [dict(r) for r in flagged],
        "amendments": [dict(r) for r in amendments],
    }


async def fetch_review_data(database_url: str) -> dict:
    """Connect (read-only intent), query, close. Thin asyncpg shell around
    query_review_data so the query logic stays unit-testable without a DB."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        return await query_review_data(conn)
    finally:
        await conn.close()
