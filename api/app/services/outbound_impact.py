"""Outbound-impact query — what the caller's OWN traces saved others.

Contributor side of the Savings & Impact system (spec phase 4). Sums, over
the caller's traces only:
  tokens_saved_for_others  = Σ( tokens_to_resolution * retrieval_count )
  minutes_saved_for_others = Σ( time_to_resolution_minutes * retrieval_count )
Both effort fields live in the JSON metadata_json column. The result is
returned ONLY for the authenticated caller's contributor_id — never another
user's (privacy: docs/privacy-what-is-shared.md). No content, no per-trace
who-helped-whom linkage leaves the query; only the caller's own rollup.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Read effort fields from metadata_json, multiply by retrieval_count, sum.
# COALESCE + NULLIF guards: missing/blank JSON keys contribute 0, never error.
_OUTBOUND_SQL = text(
    "SELECT "
    "  COALESCE(SUM("
    "    COALESCE(NULLIF(metadata_json ->> 'tokens_to_resolution', '')::bigint, 0)"
    "    * retrieval_count"
    "  ), 0) AS tokens_for_others, "
    "  COALESCE(SUM("
    "    COALESCE(NULLIF(metadata_json ->> 'time_to_resolution_minutes', '')::numeric, 0)"
    "    * retrieval_count"
    "  ), 0) AS minutes_for_others, "
    "  COUNT(*) AS trace_count "
    "FROM traces "
    "WHERE contributor_id = :cid"
)

async def compute_outbound_impact(
    db: AsyncSession, contributor_id: uuid.UUID
) -> dict:
    """Compute the owner-scoped outbound rollup for one contributor."""
    result = await db.execute(_OUTBOUND_SQL, {"cid": str(contributor_id)})
    row = result.fetchone()
    if row is None:
        return {
            "tokens_saved_for_others": 0,
            "minutes_saved_for_others": 0,
            "trace_count": 0,
        }
    tokens = int(row[0] or 0)
    minutes = int(row[1] or 0)
    count = int(row[2] or 0)
    return {
        "tokens_saved_for_others": tokens,
        "minutes_saved_for_others": minutes,
        "trace_count": count,
    }
