from app.models.savings_ledger import SavingsLedger
from app.schemas.savings import SavingsIngest, build_ledger_row

ALLOWED_COLUMNS = {"id", "minutes_saved", "tokens_saved", "event_type", "created_at"}
FORBIDDEN_COLUMNS = {
    "contributor_id", "user_id", "session_id", "trace_id", "signature",
    "title", "context_text", "solution_text", "api_key_hash", "email",
}


def test_table_name_is_savings_ledger():
    assert SavingsLedger.__tablename__ == "savings_ledger"


def test_columns_are_exactly_the_anonymized_set():
    cols = {c.name for c in SavingsLedger.__table__.columns}
    assert cols == ALLOWED_COLUMNS


def test_no_identity_or_content_columns():
    cols = {c.name for c in SavingsLedger.__table__.columns}
    assert cols & FORBIDDEN_COLUMNS == set()


def test_build_ledger_row_copies_only_allowed_fields():
    body = SavingsIngest(minutes_saved=12, tokens_saved=3400, event_type="measured_recurrence")
    row = build_ledger_row(body)
    assert isinstance(row, SavingsLedger)
    assert row.minutes_saved == 12
    assert row.tokens_saved == 3400
    assert row.event_type == "measured_recurrence"
    for forbidden in FORBIDDEN_COLUMNS:
        assert getattr(row, forbidden, None) is None
