from datetime import datetime, timezone

import app.routers.search as search_mod
from app.routers.search import _apply_somatic_floor
from tests.conftest import make_trace, FakeResult, FakeDbSession


NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _set(monkeypatch, **kw):
    for k, v in kw.items():
        monkeypatch.setattr(search_mod.settings, k, v)


async def test_disabled_is_noop(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=0)
    db = FakeDbSession()
    out = await _apply_somatic_floor(
        db, [], searcher_fp=None, now_utc=NOW,
        include_expired=False, normalized_tags=[],
    )
    assert out == []
    assert db.executed == []   # floor never touches the DB when disabled


async def test_appends_high_somatic(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=2, retrieval_somatic_floor=0.75,
         retrieval_floor_min_align=0.0)
    hot = make_trace(somatic_intensity=0.95)
    db = FakeDbSession(results=[FakeResult(rows=[hot])])
    out = await _apply_somatic_floor(
        db, [], searcher_fp=None, now_utc=NOW,
        include_expired=True, normalized_tags=[],
    )
    assert len(out) == 1
    assert out[0].id == hot.id
    assert out[0].similarity_score == 0.0
    assert out[0].combined_score == 0.95


async def test_dedups_existing(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=2, retrieval_somatic_floor=0.75,
         retrieval_floor_min_align=0.0)
    dup = make_trace(somatic_intensity=0.95)
    existing = _existing_result(dup.id)
    db = FakeDbSession(results=[FakeResult(rows=[dup])])
    out = await _apply_somatic_floor(
        db, [existing], searcher_fp=None, now_utc=NOW,
        include_expired=True, normalized_tags=[],
    )
    assert len(out) == 1   # dup not re-added


async def test_respects_n_cap(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=1, retrieval_somatic_floor=0.75,
         retrieval_floor_min_align=0.0)
    a = make_trace(somatic_intensity=0.95)
    b = make_trace(somatic_intensity=0.90)
    db = FakeDbSession(results=[FakeResult(rows=[a, b])])
    out = await _apply_somatic_floor(
        db, [], searcher_fp=None, now_utc=NOW,
        include_expired=True, normalized_tags=[],
    )
    assert len(out) == 1   # n=1 cap honored even though 2 candidates returned


async def test_exception_safe(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=2, retrieval_somatic_floor=0.75)

    class Raising:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")
    out = await _apply_somatic_floor(
        Raising(), [], searcher_fp=None, now_utc=NOW,
        include_expired=True, normalized_tags=[],
    )
    assert out == []   # swallowed; returns input unchanged


async def test_min_align_gate(monkeypatch):
    _set(monkeypatch, retrieval_floor_n=2, retrieval_somatic_floor=0.75,
         retrieval_floor_min_align=0.9)
    cand = make_trace(somatic_intensity=0.95,
                      context_fingerprint={"language": "rust"})
    db = FakeDbSession(results=[FakeResult(rows=[cand])])
    out = await _apply_somatic_floor(
        db, [], searcher_fp={"language": "python"}, now_utc=NOW,
        include_expired=True, normalized_tags=[],
    )
    assert out == []   # alignment below min_align → not surfaced


def _existing_result(trace_id):
    import uuid
    from app.schemas.search import TraceSearchResult
    return TraceSearchResult(
        id=trace_id, title="existing", context_text="c", solution_text="s",
        trust_score=1.0, status="active", tags=[], similarity_score=0.8,
        combined_score=0.8, contributor_id=uuid.uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
