import pytest

from commontrace_ops.common.db import query_review_data


class FakeConn:
    """Returns queued rows per fetch() call, in order. Rows are dicts (asyncpg
    Records behave like mappings)."""

    def __init__(self, batches):
        self._batches = list(batches)
        self.queries = []

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        return self._batches.pop(0)


async def test_query_review_data_returns_three_buckets():
    pending = [{"id": "t1", "title": "Redis", "context_text": "c",
                "solution_text": "s", "confirmation_count": 0,
                "created_at": "2026-06-01T00:00:00Z", "contributor": "bob"}]
    flagged = [{"id": "t2", "title": "Bad", "flagged_at": "2026-06-05T00:00:00Z",
                "metadata_json": {"flags": ["spam"]}}]
    amendments = [{"id": "a1", "original_trace_id": "t9", "improved_solution": "x",
                   "explanation": "y", "created_at": "2026-06-02T00:00:00Z",
                   "submitter": "carol"}]
    conn = FakeConn([pending, flagged, amendments])

    data = await query_review_data(conn)

    assert len(conn.queries) == 3
    assert data["pending_traces"][0]["id"] == "t1"
    assert data["flagged_traces"][0]["id"] == "t2"
    assert data["amendments"][0]["id"] == "a1"
    assert "status" in conn.queries[0].lower()
    assert "is_flagged" in conn.queries[1].lower()
    assert "amendments" in conn.queries[2].lower()
