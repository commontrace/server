from app.config import Settings


def test_floor_defaults():
    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/test")
    assert s.retrieval_somatic_floor == 0.75
    assert s.retrieval_floor_n == 2
    assert s.retrieval_floor_min_align == 0.0


def test_floor_env_override(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_FLOOR_N", "0")
    monkeypatch.setenv("RETRIEVAL_SOMATIC_FLOOR", "0.9")
    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/test")
    assert s.retrieval_floor_n == 0
    assert s.retrieval_somatic_floor == 0.9
