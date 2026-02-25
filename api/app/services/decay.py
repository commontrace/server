"""Temporal decay service for trace ranking.

Implements time-based relevance decay inspired by memory consolidation in
cognitive neuroscience. Frontend knowledge decays faster than infrastructure
knowledge, just as procedural memories are more stable than episodic ones.

The decay factor is applied during search ranking so stale traces naturally
sink without being deleted — mimicking graceful forgetting.
"""

import math
from datetime import datetime, timezone
from typing import Optional


# Domain-specific half-life rules (days).
# Frontend frameworks churn faster; infrastructure knowledge is more stable.
HALF_LIFE_RULES: dict[str, int] = {
    # Frontend — fast churn
    "react": 180,
    "vue": 180,
    "next": 180,
    "nuxt": 180,
    "svelte": 180,
    "angular": 180,
    "tailwind": 270,
    "css": 270,
    # Backend — moderate stability
    "fastapi": 365,
    "django": 365,
    "flask": 365,
    "express": 365,
    "rails": 365,
    "spring": 365,
    "node": 365,
    "python": 365,
    "javascript": 365,
    "typescript": 365,
    "rust": 365,
    "go": 365,
    # Infrastructure — high stability
    "docker": 730,
    "kubernetes": 730,
    "postgres": 730,
    "redis": 730,
    "nginx": 730,
    "linux": 730,
    "terraform": 730,
    "aws": 548,
    "gcp": 548,
}

DEFAULT_HALF_LIFE_DAYS = 365


def compute_half_life(tag_names: list[str]) -> int:
    """Compute the half-life for a trace based on its tags.

    Uses the minimum half-life across all matching tags (most volatile
    domain wins). Falls back to DEFAULT_HALF_LIFE_DAYS if no tags match.
    """
    matched = [HALF_LIFE_RULES[t] for t in tag_names if t in HALF_LIFE_RULES]
    if matched:
        return min(matched)
    return DEFAULT_HALF_LIFE_DAYS


def temporal_decay_factor(
    created_at: datetime,
    last_retrieved_at: Optional[datetime],
    half_life_days: Optional[int],
) -> float:
    """Compute temporal decay factor for search ranking.

    Uses exponential decay with a Hebbian twist: retrieval resets the
    freshness clock (recently-used knowledge stays fresh).

    Returns a float in [0.3, 1.0]:
    - 1.0 = just created/retrieved
    - 0.3 = floor (timeless knowledge never fully disappears)
    """
    half_life = half_life_days or DEFAULT_HALF_LIFE_DAYS

    # Hebbian: use the most recent activity as freshness anchor
    anchor = last_retrieved_at if last_retrieved_at else created_at

    # Ensure timezone-aware comparison
    now = datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)

    age_days = (now - anchor).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0

    # Exponential decay: factor = 2^(-age/half_life)
    raw = math.pow(2, -age_days / half_life)

    # Floor at 0.3 — timeless knowledge never fully disappears
    return max(0.3, raw)
