"""tokens_to_resolution rides into metadata_json at contribution time."""
from app.schemas.trace import TraceCreate
from app.services.enrichment import auto_enrich_metadata, coerce_tokens_to_resolution


def test_schema_accepts_top_level_tokens_to_resolution():
    body = TraceCreate(title="x", context_text="c", solution_text="s", tokens_to_resolution=4200)
    assert body.tokens_to_resolution == 4200


def test_coerce_folds_top_level_field_into_metadata():
    meta = coerce_tokens_to_resolution({"language": "python"}, 4200)
    assert meta["tokens_to_resolution"] == 4200
    assert meta["language"] == "python"


def test_coerce_preserves_already_nested_value_when_no_top_level():
    meta = coerce_tokens_to_resolution({"tokens_to_resolution": 999}, None)
    assert meta["tokens_to_resolution"] == 999


def test_coerce_top_level_takes_precedence_and_handles_none_meta():
    meta = coerce_tokens_to_resolution(None, 1234)
    assert meta == {"tokens_to_resolution": 1234}


def test_enrichment_preserves_tokens_to_resolution():
    enriched = auto_enrich_metadata({"tokens_to_resolution": 4200}, "print('hi')")
    assert enriched["tokens_to_resolution"] == 4200


def test_negative_tokens_rejected_by_schema():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TraceCreate(title="x", context_text="c", solution_text="s", tokens_to_resolution=-1)
