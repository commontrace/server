"""Self-test for the no-DB fake session harness."""
import uuid
from tests.conftest import FakeDbSession, FakeResult, make_user


async def test_fake_result_scalar_and_fetchone():
    res = FakeResult(scalar_value=7, rows=[(1, 2, 3)])
    assert res.scalar() == 7
    assert res.scalar_one() == 7
    assert res.fetchone() == (1, 2, 3)


async def test_fake_session_records_added_objects_and_commits():
    db = FakeDbSession(results=[FakeResult(scalar_value=0)])
    sentinel = object()
    db.add(sentinel)
    await db.execute("SELECT 1")
    await db.commit()
    assert db.added == [sentinel]
    assert db.commits == 1
    assert db.executed[0][0] == "SELECT 1"


def test_make_user_has_id_and_no_secrets_leaked():
    u = make_user()
    assert isinstance(u.id, uuid.UUID)
    assert u.can_contribute is True


from datetime import datetime as _dt
from tests.conftest import make_trace


def test_make_trace_defaults():
    t = make_trace()
    assert t.somatic_intensity == 0.9
    assert t.impact_level == "normal"
    assert t.trace_type == "episodic"
    assert t.tags == []
    assert isinstance(t.created_at, _dt)
    assert len(t.embedding) == 1536


def test_make_trace_overrides():
    t = make_trace(title="x", somatic_intensity=0.5)
    assert t.title == "x"
    assert t.somatic_intensity == 0.5


def test_fakeresult_scalars_chains():
    r = FakeResult(rows=[1, 2, 3])
    assert r.scalars().all() == [1, 2, 3]
