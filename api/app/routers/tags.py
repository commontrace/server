"""Tags listing endpoint.

GET /api/v1/tags -- return all distinct tag names from the database.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit
from app.models.tag import Tag
from app.models.tag_trend import TagTrend

router = APIRouter(prefix="/api/v1", tags=["tags"])


@router.get("/tags")
async def list_tags(
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> dict:
    """Return all distinct tag names from the database, sorted alphabetically.

    Returns:
        {"tags": ["fastapi", "python", "react", ...]}
    """
    result = await db.execute(select(Tag.name).order_by(Tag.name))
    tag_names = list(result.scalars().all())
    return {"tags": tag_names}


@router.get("/tags/trending")
async def list_trending_tags(
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> dict:
    """Return top 10 trending tags from the latest trend detection period.

    Trending = growth_rate > 2.0 AND >= 3 traces in the current 7-day window.
    """
    result = await db.execute(
        select(
            TagTrend.tag_name,
            TagTrend.growth_rate,
            TagTrend.trace_count_period,
            TagTrend.trace_count_prior,
            TagTrend.period_end,
        )
        .where(TagTrend.is_trending.is_(True))
        .order_by(TagTrend.growth_rate.desc())
        .limit(10)
    )
    rows = result.all()
    return {
        "trending": [
            {
                "tag": row.tag_name,
                "growth_rate": row.growth_rate,
                "trace_count": row.trace_count_period,
                "prior_count": row.trace_count_prior,
                "period_end": row.period_end.isoformat() if row.period_end else None,
            }
            for row in rows
        ]
    }
