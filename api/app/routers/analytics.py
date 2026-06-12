"""Analytics router — aggregate-only metrics for the owner dashboard.

All endpoints are unauthenticated and return aggregate data only. No PII
(emails, raw IPs, individual API keys) is surfaced. The dashboard URL is
unlisted on the public site but anyone with the URL can view the numbers.

Endpoints:
  GET /api/v1/analytics/summary
  GET /api/v1/analytics/timeline?days=30
  GET /api/v1/analytics/top-tags?limit=20
  GET /api/v1/analytics/top-traces?limit=20
  GET /api/v1/analytics/top-contributors?limit=20
  GET /api/v1/analytics/geo
  GET /api/v1/analytics/platforms
  GET /api/v1/analytics/triggers
  GET /api/v1/analytics/topics?limit=20
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select, text

from app.dependencies import DbSession
from app.models.amendment import Amendment
from app.models.retrieval_log import RetrievalLog
from app.models.trace import Trace
from app.models.user import User
from app.models.vote import Vote

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/summary")
async def get_summary(db: DbSession) -> dict:
    """Top-level totals plus 7-day / 30-day deltas."""
    now = _utcnow()
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d1 = now - timedelta(days=1)

    async def _scalar(stmt) -> int:
        result = await db.execute(stmt)
        return int(result.scalar() or 0)

    total_users = await _scalar(select(func.count()).select_from(User))
    users_7d = await _scalar(
        select(func.count()).select_from(User).where(User.created_at >= d7)
    )
    users_30d = await _scalar(
        select(func.count()).select_from(User).where(User.created_at >= d30)
    )
    users_with_email = await _scalar(
        select(func.count()).select_from(User).where(User.email.is_not(None))
    )

    # Daily active = users seen in last 24h (requires last_seen_at populated)
    dau = await _scalar(
        select(func.count()).select_from(User).where(User.last_seen_at >= d1)
    )
    wau = await _scalar(
        select(func.count()).select_from(User).where(User.last_seen_at >= d7)
    )
    mau = await _scalar(
        select(func.count()).select_from(User).where(User.last_seen_at >= d30)
    )

    total_traces = await _scalar(select(func.count()).select_from(Trace))
    traces_7d = await _scalar(
        select(func.count()).select_from(Trace).where(Trace.created_at >= d7)
    )
    traces_30d = await _scalar(
        select(func.count()).select_from(Trace).where(Trace.created_at >= d30)
    )

    total_votes = await _scalar(select(func.count()).select_from(Vote))
    votes_7d = await _scalar(
        select(func.count()).select_from(Vote).where(Vote.created_at >= d7)
    )

    total_amendments = await _scalar(select(func.count()).select_from(Amendment))
    amendments_7d = await _scalar(
        select(func.count()).select_from(Amendment).where(Amendment.created_at >= d7)
    )

    # Search activity from retrieval_logs (30-day rolling, pruned by worker)
    searches_7d = await _scalar(
        select(func.count(func.distinct(RetrievalLog.search_session_id)))
        .where(RetrievalLog.retrieved_at >= d7)
    )
    searches_30d = await _scalar(
        select(func.count(func.distinct(RetrievalLog.search_session_id)))
        .where(RetrievalLog.retrieved_at >= d30)
    )
    retrievals_7d = await _scalar(
        select(func.count()).select_from(RetrievalLog).where(
            RetrievalLog.retrieved_at >= d7
        )
    )

    # Total cumulative retrievals (from traces.retrieval_count)
    total_retrievals_result = await db.execute(
        select(func.coalesce(func.sum(Trace.retrieval_count), 0))
    )
    total_retrievals = int(total_retrievals_result.scalar() or 0)

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": total_users,
            "with_email": users_with_email,
            "new_7d": users_7d,
            "new_30d": users_30d,
            "dau": dau,
            "wau": wau,
            "mau": mau,
        },
        "traces": {
            "total": total_traces,
            "new_7d": traces_7d,
            "new_30d": traces_30d,
            "total_retrievals": total_retrievals,
        },
        "votes": {
            "total": total_votes,
            "new_7d": votes_7d,
        },
        "amendments": {
            "total": total_amendments,
            "new_7d": amendments_7d,
        },
        "searches": {
            "distinct_sessions_7d": searches_7d,
            "distinct_sessions_30d": searches_30d,
            "retrievals_7d": retrievals_7d,
        },
    }


@router.get("/timeline")
async def get_timeline(
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Daily counts for signups, traces, votes, searches over N days."""
    now = _utcnow()
    since = now - timedelta(days=days)

    async def _daily(table_name: str, ts_col: str, filter_sql: str = "") -> dict:
        # Use raw SQL with date_trunc — fast and DB-agnostic-ish for postgres
        sql = text(
            f"SELECT date_trunc('day', {ts_col}) AS day, COUNT(*) AS n "
            f"FROM {table_name} "
            f"WHERE {ts_col} >= :since {filter_sql} "
            f"GROUP BY day ORDER BY day ASC"
        )
        result = await db.execute(sql, {"since": since})
        return {row[0].date().isoformat(): int(row[1]) for row in result.fetchall()}

    signups = await _daily("users", "created_at")
    traces = await _daily("traces", "created_at")
    votes = await _daily("votes", "created_at")
    # retrieval_logs: unique search sessions per day
    sql = text(
        "SELECT date_trunc('day', retrieved_at) AS day, "
        "COUNT(DISTINCT search_session_id) AS n "
        "FROM retrieval_logs WHERE retrieved_at >= :since "
        "GROUP BY day ORDER BY day ASC"
    )
    res = await db.execute(sql, {"since": since})
    searches = {row[0].date().isoformat(): int(row[1]) for row in res.fetchall()}

    # Build full date series so missing days appear as 0
    series = []
    for i in range(days, -1, -1):
        d = (now - timedelta(days=i)).date().isoformat()
        series.append(
            {
                "date": d,
                "signups": signups.get(d, 0),
                "traces": traces.get(d, 0),
                "votes": votes.get(d, 0),
                "search_sessions": searches.get(d, 0),
            }
        )

    return {"days": days, "series": series}


@router.get("/top-tags")
async def get_top_tags(
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Most-used tags by trace count (proxy for popularity)."""
    sql = text(
        "SELECT t.name, COUNT(tt.trace_id) AS n "
        "FROM tags t JOIN trace_tags tt ON t.id = tt.tag_id "
        "GROUP BY t.name ORDER BY n DESC LIMIT :lim"
    )
    result = await db.execute(sql, {"lim": limit})
    return {
        "tags": [{"name": row[0], "trace_count": int(row[1])} for row in result.fetchall()]
    }


@router.get("/top-traces")
async def get_top_traces(
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Most-retrieved traces (by retrieval_count counter)."""
    stmt = (
        select(
            Trace.id,
            Trace.title,
            Trace.retrieval_count,
            Trace.trust_score,
            Trace.created_at,
        )
        .order_by(Trace.retrieval_count.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return {
        "traces": [
            {
                "id": str(row[0]),
                "title": row[1],
                "retrieval_count": int(row[2] or 0),
                "trust_score": float(row[3] or 0),
                "created_at": row[4].isoformat() if row[4] else None,
            }
            for row in result.fetchall()
        ]
    }


@router.get("/top-contributors")
async def get_top_contributors(
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Top contributors by trace count. Surfaces display_name only — no emails."""
    sql = text(
        "SELECT COALESCE(u.display_name, 'anon-' || LEFT(u.id::text, 8)) AS name, "
        "u.reputation_score, COUNT(t.id) AS trace_count, "
        "COALESCE(SUM(t.retrieval_count), 0) AS total_retrievals "
        "FROM users u JOIN traces t ON t.contributor_id = u.id "
        "GROUP BY u.id, u.display_name, u.reputation_score "
        "ORDER BY trace_count DESC LIMIT :lim"
    )
    result = await db.execute(sql, {"lim": limit})
    return {
        "contributors": [
            {
                "name": row[0],
                "reputation_score": float(row[1] or 0),
                "trace_count": int(row[2]),
                "total_retrievals": int(row[3]),
            }
            for row in result.fetchall()
        ]
    }


@router.get("/geo")
async def get_geo(db: DbSession) -> dict:
    """Country-level distribution of users. NULL == unknown."""
    sql = text(
        "SELECT COALESCE(country_code, 'unknown') AS cc, COUNT(*) AS n "
        "FROM users GROUP BY cc ORDER BY n DESC"
    )
    result = await db.execute(sql)
    rows = result.fetchall()
    return {
        "countries": [{"code": row[0], "users": int(row[1])} for row in rows]
    }


@router.get("/platforms")
async def get_platforms(db: DbSession) -> dict:
    """Breakdown by platform + skill_version."""
    sql_p = text(
        "SELECT COALESCE(platform, 'unknown'), COUNT(*) FROM users "
        "GROUP BY platform ORDER BY 2 DESC"
    )
    sql_v = text(
        "SELECT COALESCE(skill_version, 'unknown'), COUNT(*) FROM users "
        "GROUP BY skill_version ORDER BY 2 DESC LIMIT 20"
    )
    sql_s = text(
        "SELECT COALESCE(install_source, 'unknown'), COUNT(*) FROM users "
        "GROUP BY install_source ORDER BY 2 DESC LIMIT 20"
    )
    rp = (await db.execute(sql_p)).fetchall()
    rv = (await db.execute(sql_v)).fetchall()
    rs = (await db.execute(sql_s)).fetchall()
    return {
        "platforms": [{"name": r[0], "users": int(r[1])} for r in rp],
        "versions": [{"name": r[0], "users": int(r[1])} for r in rv],
        "sources": [{"name": r[0], "users": int(r[1])} for r in rs],
    }


@router.get("/triggers")
async def get_triggers(db: DbSession) -> dict:
    """Aggregate trigger effectiveness across all reported skill sessions."""
    sql = text(
        "SELECT stats_json FROM trigger_stats "
        "WHERE reported_at >= NOW() - INTERVAL '30 days'"
    )
    result = await db.execute(sql)
    rows = result.fetchall()

    agg: dict[str, dict] = {}
    sessions = 0
    for (stats,) in rows:
        sessions += 1
        if not isinstance(stats, dict):
            continue
        for trigger, vals in stats.items():
            if not isinstance(vals, dict):
                continue
            slot = agg.setdefault(trigger, {"fired": 0, "consumed": 0})
            slot["fired"] += int(vals.get("fired", vals.get("total", 0)) or 0)
            slot["consumed"] += int(vals.get("consumed", 0) or 0)

    triggers = []
    for name, vals in sorted(agg.items(), key=lambda x: -x[1]["fired"]):
        fired = vals["fired"]
        consumed = vals["consumed"]
        rate = (consumed / fired) if fired > 0 else 0.0
        triggers.append(
            {
                "name": name,
                "fired": fired,
                "consumed": consumed,
                "consumption_rate": round(rate, 3),
            }
        )

    return {"sessions_reported": sessions, "triggers": triggers}


@router.get("/topics")
async def get_topics(db: DbSession, limit: int = Query(20, ge=1, le=50)) -> dict:
    """Ambient presence: per-tag activity counters, trailing 7 days (spec §4.4).

    Aggregate-only — tag names and counts, nothing user-identifying.
    """
    since = _utcnow() - timedelta(days=7)

    retrieval_sql = text(
        "SELECT tg.name, COUNT(*) AS retrievals "
        "FROM retrieval_logs rl "
        "JOIN trace_tags tt ON tt.trace_id = rl.trace_id "
        "JOIN tags tg ON tg.id = tt.tag_id "
        "WHERE rl.retrieved_at >= :since "
        "GROUP BY tg.name"
    )
    new_traces_sql = text(
        "SELECT tg.name, COUNT(DISTINCT t.id) AS new_traces "
        "FROM traces t "
        "JOIN trace_tags tt ON tt.trace_id = t.id "
        "JOIN tags tg ON tg.id = tt.tag_id "
        "WHERE t.created_at >= :since "
        "GROUP BY tg.name"
    )
    retrieval_rows = (await db.execute(retrieval_sql, {"since": since})).fetchall()
    new_trace_rows = (await db.execute(new_traces_sql, {"since": since})).fetchall()
    retrievals = {r[0]: int(r[1]) for r in retrieval_rows}
    new_traces = {r[0]: int(r[1]) for r in new_trace_rows}

    topics = [
        {
            "tag": tag,
            "retrievals_7d": retrievals.get(tag, 0),
            "new_traces_7d": new_traces.get(tag, 0),
        }
        for tag in set(retrievals) | set(new_traces)
    ]
    topics.sort(key=lambda x: (-x["retrievals_7d"], -x["new_traces_7d"], x["tag"]))
    return {"window_days": 7, "topics": topics[:limit]}
