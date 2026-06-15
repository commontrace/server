"""POST /telemetry/savings persists an anonymized row only."""
from app.models.savings_ledger import SavingsLedger
from app.routers.telemetry import report_savings
from app.schemas.savings import SavingsIngest
from tests.conftest import FakeDbSession, make_user


async def test_persists_anonymized_row_and_returns_ok():
    db = FakeDbSession()
    user = make_user()
    body = SavingsIngest(minutes_saved=9, tokens_saved=2100, event_type="proxy_consumption")
    resp = await report_savings(body=body, user=user, db=db, _rate=None)
    assert db.commits == 1
    assert len(db.added) == 1
    row = db.added[0]
    assert isinstance(row, SavingsLedger)
    assert (row.minutes_saved, row.tokens_saved, row.event_type) == (9, 2100, "proxy_consumption")
    assert resp.status == "ok"


async def test_user_identity_is_never_written_to_the_row():
    db = FakeDbSession()
    user = make_user(email="someone@real.example")
    body = SavingsIngest(minutes_saved=1, tokens_saved=10, event_type="measured_recurrence")
    await report_savings(body=body, user=user, db=db, _rate=None)
    row = db.added[0]
    leaked = [
        name for name in vars(row)
        if getattr(row, name, None) in {user.id, user.email}
    ]
    assert leaked == []
    for forbidden in ("contributor_id", "user_id", "session_id", "email"):
        assert getattr(row, forbidden, None) is None


def test_request_schema_rejects_smuggled_identity_fields():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SavingsIngest(
            minutes_saved=1, tokens_saved=10, event_type="measured_recurrence",
            contributor_id="00000000-0000-0000-0000-000000000000",
        )
