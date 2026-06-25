"""No-DB async test harness for the API.

CI runs `pytest tests/ -q` with no database (see .github/workflows/ci.yml).
These fakes stand in for SQLAlchemy's AsyncSession / Result so router and
query logic can be tested by feeding canned rows and inspecting what was
built — the same approach as ops/tests/conftest.py (FakeConn/FakeResponse).
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional


class FakeResult:
    def __init__(self, scalar_value: Any = None, rows: Optional[list] = None):
        self._scalar = scalar_value
        self._rows = list(rows) if rows is not None else []

    def scalar(self): return self._scalar
    def scalar_one(self): return self._scalar
    def scalar_one_or_none(self): return self._scalar
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def all(self): return list(self._rows)
    def scalars(self): return self


class FakeDbSession:
    def __init__(self, results: Optional[list] = None):
        self._results = list(results) if results is not None else []
        self.added: list = []
        self.executed: list = []
        self.commits: int = 0
        self.refreshed: list = []

    def add(self, obj): self.added.append(obj)

    async def execute(self, statement, params=None):
        self.executed.append((statement, params))
        if self._results:
            return self._results.pop(0)
        return FakeResult()

    async def commit(self): self.commits += 1
    async def flush(self): pass
    async def refresh(self, obj): self.refreshed.append(obj)


def make_user(can_contribute: bool = True, email: str = "tester@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        can_contribute=can_contribute,
        display_name=None,
        country_code=None,
    )


def make_trace(**overrides):
    """Build a fake Trace ORM-ish object for router/query tests.

    Every field _serialize_trace / _apply_somatic_floor touches is present.
    `tags` is a list of objects exposing `.name` (mirrors the ORM relationship).
    """
    defaults = dict(
        id=uuid.uuid4(),
        title="fake trace",
        context_text="ctx",
        solution_text="sol",
        trust_score=1.0,
        status="active",
        tags=[],
        contributor_id=uuid.uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieval_count=0,
        depth_score=0,
        somatic_intensity=0.9,
        impact_level="normal",
        trace_type="episodic",
        context_fingerprint=None,
        convergence_level=None,
        memory_temperature=None,
        valid_from=None,
        valid_until=None,
        is_flagged=False,
        embedding=[0.1] * 1536,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)
