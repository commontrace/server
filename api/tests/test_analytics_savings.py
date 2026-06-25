"""GET /analytics/savings returns the global savings shape.

No DB: feed three FakeResults (minutes sum, tokens sum, count) in the order
the handler queries them, and assert the response dict shape + values. The
endpoint is aggregate-only and unauthenticated (it takes only `db`).
"""

from app.routers.analytics import get_savings
from tests.conftest import FakeDbSession, FakeResult


async def test_returns_global_minutes_tokens_events():
    db = FakeDbSession(results=[
        FakeResult(scalar_value=540),      # SUM(minutes_saved)
        FakeResult(scalar_value=128_000),  # SUM(tokens_saved)
        FakeResult(scalar_value=37),       # COUNT(*)
    ])

    out = await get_savings(db=db)

    assert out == {
        "total_minutes_saved": 540,
        "total_tokens_saved": 128_000,
        "total_usd_saved": 0.64,  # 128_000 / 1e6 * 5.00
        "event_count": 37,
    }


async def test_empty_ledger_returns_zeros():
    db = FakeDbSession(results=[
        FakeResult(scalar_value=None),  # COALESCE handles NULL -> 0 in prod;
        FakeResult(scalar_value=None),  # the handler must also int(None or 0).
        FakeResult(scalar_value=0),
    ])

    out = await get_savings(db=db)

    assert out == {
        "total_minutes_saved": 0,
        "total_tokens_saved": 0,
        "total_usd_saved": 0.0,
        "event_count": 0,
    }
