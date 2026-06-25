import uuid
from app.services.outbound_impact import compute_outbound_impact
from app.routers.analytics import get_outbound_impact
from tests.conftest import FakeDbSession, FakeResult, make_user

async def test_query_is_owner_scoped_and_shaped():
    cid = uuid.uuid4()
    db = FakeDbSession(results=[FakeResult(rows=[(54000, 320, 7)])])
    out = await compute_outbound_impact(db, cid)
    assert out == {
        "tokens_saved_for_others": 54000,
        "minutes_saved_for_others": 320,
        "trace_count": 7,
    }
    stmt, params = db.executed[0]
    sql = str(stmt).lower()
    assert "contributor_id" in sql
    assert "retrieval_count" in sql
    assert "tokens_to_resolution" in sql
    assert "time_to_resolution_minutes" in sql
    assert params["cid"] == str(cid)

async def test_endpoint_passes_only_the_callers_own_id():
    db = FakeDbSession(results=[FakeResult(rows=[(0, 0, 0)])])
    user = make_user()
    resp = await get_outbound_impact(user=user, db=db, _rate=None)
    _, params = db.executed[0]
    assert params["cid"] == str(user.id)
    assert resp.tokens_saved_for_others == 0
    assert resp.minutes_saved_for_others == 0
    assert resp.trace_count == 0

async def test_null_aggregate_row_yields_zeros():
    db = FakeDbSession(results=[FakeResult(rows=[(None, None, 0)])])
    out = await compute_outbound_impact(db, uuid.uuid4())
    assert out == {
        "tokens_saved_for_others": 0,
        "minutes_saved_for_others": 0,
        "trace_count": 0,
    }
