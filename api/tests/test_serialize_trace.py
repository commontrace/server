from tests.conftest import make_trace
from app.routers.search import _serialize_trace


def test_serialize_maps_all_fields():
    class Tag:
        def __init__(self, name): self.name = name
    t = make_trace(tags=[Tag("python"), Tag("fastapi")])
    out = _serialize_trace(t, similarity=0.0, combined=0.9)
    assert out.id == t.id
    assert out.title == t.title
    assert out.tags == ["python", "fastapi"]
    assert out.similarity_score == 0.0
    assert out.combined_score == 0.9
    assert out.somatic_intensity == 0.9
    assert out.impact_level == "normal"


def test_serialize_impact_level_fallback():
    t = make_trace(impact_level=None)
    out = _serialize_trace(t, similarity=0.0, combined=0.5)
    assert out.impact_level == "normal"
