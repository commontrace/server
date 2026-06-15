from pydantic import BaseModel, ConfigDict, Field
from app.models.savings_ledger import SavingsLedger

ALLOWED_EVENT_TYPES = {"measured_recurrence", "proxy_consumption"}


class SavingsIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutes_saved: int = Field(ge=0, le=120)
    tokens_saved: int = Field(ge=0, le=5_000_000)
    event_type: str = Field(min_length=1, max_length=40)


class SavingsIngestResponse(BaseModel):
    status: str = "ok"


class OutboundImpactResponse(BaseModel):
    tokens_saved_for_others: int = 0
    minutes_saved_for_others: int = 0
    trace_count: int = 0


def build_ledger_row(body: SavingsIngest) -> SavingsLedger:
    return SavingsLedger(
        minutes_saved=body.minutes_saved,
        tokens_saved=body.tokens_saved,
        event_type=body.event_type,
    )
