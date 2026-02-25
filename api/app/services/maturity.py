"""Maturity service for adaptive knowledge lifecycle management.

Adjusts system behavior based on the current scale of the knowledge base.
Small collections need gentler decay; large collections need stricter curation.

Tiers inspired by developmental stages in cognitive science:
- SEED: Early-stage, nurture everything
- GROWING: Medium-scale, moderate curation
- MATURE: Large-scale, aggressive curation
"""

import enum

import structlog
from sqlalchemy import func, select

from app.models.trace import Trace

log = structlog.get_logger()


class MaturityTier(str, enum.Enum):
    SEED = "seed"          # < 1,000 traces
    GROWING = "growing"    # 1,000 - 100,000 traces
    MATURE = "mature"      # > 100,000 traces


# Tier boundaries
_SEED_CEILING = 1_000
_GROWING_CEILING = 100_000


async def get_trace_count(session) -> int:
    """Get total trace count from the database."""
    result = await session.execute(select(func.count(Trace.id)))
    return result.scalar_one()


async def get_maturity_tier(session) -> MaturityTier:
    """Determine the current maturity tier based on trace count."""
    count = await get_trace_count(session)
    if count < _SEED_CEILING:
        return MaturityTier.SEED
    elif count < _GROWING_CEILING:
        return MaturityTier.GROWING
    else:
        return MaturityTier.MATURE


def get_validation_threshold(tier: MaturityTier) -> int:
    """Number of confirmations needed to validate a trace.

    Small collections need just 1 vote; large collections need 3.
    """
    return {
        MaturityTier.SEED: 1,
        MaturityTier.GROWING: 2,
        MaturityTier.MATURE: 3,
    }[tier]


def should_apply_temporal_decay(tier: MaturityTier) -> bool:
    """Whether temporal decay should be active at this scale.

    Disabled in SEED tier to avoid penalizing the only knowledge available.
    """
    return tier != MaturityTier.SEED


def get_decay_multiplier(tier: MaturityTier) -> float:
    """Trust decay multiplier for the consolidation worker.

    Stronger decay at scale to prevent trust inflation.
    """
    return {
        MaturityTier.SEED: 1.0,       # No decay
        MaturityTier.GROWING: 0.995,   # ~16% annual
        MaturityTier.MATURE: 0.990,    # ~30% annual
    }[tier]
