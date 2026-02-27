"""Tag trend detection service.

Compares trace counts per tag over rolling 7-day windows to detect
emerging topics (Principle 10 — Stigmergy). Tags with growth_rate > 2.0
and at least 3 traces in the current period are marked as trending.
"""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Minimum traces in current period to qualify as trending
MIN_TRENDING_COUNT = 3
# Minimum growth rate (current / prior) to qualify as trending
MIN_GROWTH_RATE = 2.0


async def detect_tag_trends(session: AsyncSession) -> int:
    """Compute tag trends by comparing last 7 days vs prior 7 days.

    Upserts into tag_trends table. Returns count of trending tags detected.
    """
    now = datetime.now(timezone.utc)
    period_end = now
    period_start = now - timedelta(days=7)
    prior_start = period_start - timedelta(days=7)

    # Count traces per tag in current period and prior period
    result = await session.execute(
        text(
            """
            WITH current_period AS (
                SELECT tg.name AS tag_name, COUNT(DISTINCT t.id) AS cnt
                FROM tags tg
                JOIN trace_tags tt ON tt.tag_id = tg.id
                JOIN traces t ON t.id = tt.trace_id
                WHERE t.created_at >= :period_start AND t.created_at < :period_end
                GROUP BY tg.name
            ),
            prior_period AS (
                SELECT tg.name AS tag_name, COUNT(DISTINCT t.id) AS cnt
                FROM tags tg
                JOIN trace_tags tt ON tt.tag_id = tg.id
                JOIN traces t ON t.id = tt.trace_id
                WHERE t.created_at >= :prior_start AND t.created_at < :period_start
                GROUP BY tg.name
            )
            SELECT
                COALESCE(c.tag_name, p.tag_name) AS tag_name,
                COALESCE(c.cnt, 0) AS count_current,
                COALESCE(p.cnt, 0) AS count_prior
            FROM current_period c
            FULL OUTER JOIN prior_period p ON c.tag_name = p.tag_name
            WHERE COALESCE(c.cnt, 0) > 0 OR COALESCE(p.cnt, 0) > 0
            """
        ),
        {
            "period_start": period_start,
            "period_end": period_end,
            "prior_start": prior_start,
        },
    )
    rows = result.all()

    trending_count = 0
    for row in rows:
        tag_name = row.tag_name
        count_current = row.count_current
        count_prior = row.count_prior

        growth_rate = count_current / max(count_prior, 1)
        is_trending = growth_rate > MIN_GROWTH_RATE and count_current >= MIN_TRENDING_COUNT

        if is_trending:
            trending_count += 1

        # Upsert into tag_trends
        await session.execute(
            text(
                """
                INSERT INTO tag_trends (id, tag_name, period_start, period_end,
                    trace_count_period, trace_count_prior, growth_rate, is_trending)
                VALUES (gen_random_uuid(), :tag_name, :period_start, :period_end,
                    :count_current, :count_prior, :growth_rate, :is_trending)
                ON CONFLICT (tag_name, period_end)
                DO UPDATE SET
                    trace_count_period = :count_current,
                    trace_count_prior = :count_prior,
                    growth_rate = :growth_rate,
                    is_trending = :is_trending
                """
            ),
            {
                "tag_name": tag_name,
                "period_start": period_start,
                "period_end": period_end,
                "count_current": count_current,
                "count_prior": count_prior,
                "growth_rate": growth_rate,
                "is_trending": is_trending,
            },
        )

    if trending_count > 0:
        log.info("tag_trends_detected", trending_count=trending_count, tags_evaluated=len(rows))

    return trending_count
