"""Memory temperature classification service.

Classifies traces into temperature tiers based on retrieval patterns,
trust trajectory, and age. Replaces binary is_stale with a graduated
signal for search ranking.

Inspired by DroidClaw's temperature classification:
  HOT    — actively useful, recently retrieved
  WARM   — moderately active or newly created
  COOL   — aging but not forgotten
  COLD   — neglected or distrusted
  FROZEN — effectively stale (replaces is_stale=True)
"""

import enum
from datetime import datetime, timezone
from typing import Optional


class MemoryTemperature(str, enum.Enum):
    HOT = "HOT"
    WARM = "WARM"
    COOL = "COOL"
    COLD = "COLD"
    FROZEN = "FROZEN"


# Search ranking multipliers per temperature
TEMPERATURE_MULTIPLIERS: dict[str, float] = {
    MemoryTemperature.HOT: 1.15,
    MemoryTemperature.WARM: 1.05,
    MemoryTemperature.COOL: 1.0,
    MemoryTemperature.COLD: 0.85,
    MemoryTemperature.FROZEN: 0.7,
}


def classify_temperature(
    created_at: datetime,
    last_retrieved_at: Optional[datetime],
    retrieval_count: int,
    trust_score: float,
    depth_score: int,
) -> MemoryTemperature:
    """Classify a trace's memory temperature.

    Trust checks run first as a floor — a heavily downvoted trace can't be HOT
    just because it was recently retrieved (it was probably being downvoted).
    """
    now = datetime.now(timezone.utc)

    anchor_created = created_at
    if anchor_created.tzinfo is None:
        anchor_created = anchor_created.replace(tzinfo=timezone.utc)

    age_days = max(1.0, (now - anchor_created).total_seconds() / 86400.0)

    # Days since last retrieval (None = never retrieved)
    days_since_retrieval: Optional[float] = None
    if last_retrieved_at is not None:
        lr = last_retrieved_at
        if lr.tzinfo is None:
            lr = lr.replace(tzinfo=timezone.utc)
        days_since_retrieval = (now - lr).total_seconds() / 86400.0

    # Retrieval frequency: retrievals per day
    retrieval_freq = retrieval_count / age_days

    # FROZEN: trust < -1 AND (never retrieved OR not retrieved in 180+ days)
    if trust_score < -1:
        if days_since_retrieval is None or days_since_retrieval > 180:
            return MemoryTemperature.FROZEN

    # COLD: trust < 0 (regardless of retrieval)
    if trust_score < 0:
        return MemoryTemperature.COLD

    # COLD: not retrieved in 90+ days
    if days_since_retrieval is not None and days_since_retrieval > 90:
        return MemoryTemperature.COLD
    if days_since_retrieval is None and age_days > 90:
        return MemoryTemperature.COLD

    # HOT: high retrieval frequency OR very recent retrieval
    if retrieval_freq > 0.1:
        return MemoryTemperature.HOT
    if days_since_retrieval is not None and days_since_retrieval <= 7:
        return MemoryTemperature.HOT

    # WARM: retrieved in last 30 days
    if days_since_retrieval is not None and days_since_retrieval <= 30:
        return MemoryTemperature.WARM

    # COOL: retrieved in 30-90 day range
    if days_since_retrieval is not None and days_since_retrieval <= 90:
        return MemoryTemperature.COOL

    # New traces (< 30 days) with no retrievals get benefit of the doubt
    if age_days <= 30:
        return MemoryTemperature.WARM

    return MemoryTemperature.COOL


def get_temperature_multiplier(temperature: Optional[str]) -> float:
    """Get the search ranking multiplier for a temperature.

    Returns 1.0 for None or unrecognized values (backward-compatible).
    """
    if temperature is None:
        return 1.0
    return TEMPERATURE_MULTIPLIERS.get(temperature, 1.0)
