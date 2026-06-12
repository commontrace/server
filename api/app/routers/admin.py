"""Admin router — detailed per-user analytics, gated by X-Admin-Token header.

All endpoints here return PII (emails, individual signups, per-user timelines).
Protected by a shared-secret token compared in constant time against
settings.admin_dashboard_token. If the token env var is empty, all admin
endpoints return 503 — defense in depth so a misconfigured deploy cannot
leak data.

Endpoints:
  GET /api/v1/admin/health
  GET /api/v1/admin/users/recent?limit=100
  GET /api/v1/admin/users/{user_id}
  GET /api/v1/admin/signups/timeline?days=30
  GET /api/v1/admin/sessions/recent?limit=200
  GET /api/v1/admin/traces/recent?limit=50
  GET /api/v1/admin/votes/recent?limit=100
  GET /api/v1/admin/funnel
  POST /api/v1/admin/invitations
  POST /api/v1/admin/contributors/{user_id}
  DELETE /api/v1/admin/users/{user_id}
"""

import hmac
import uuid

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import settings
from app.dependencies import DbSession, hash_api_key
from app.routers.invitations import generate_invite_code
from app.services.pattern_synthesis import SYSTEM_USER_ID

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _check_token(x_admin_token: str | None) -> None:
    if not settings.admin_dashboard_token:
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard disabled. Set ADMIN_DASHBOARD_TOKEN env var.",
        )
    if not x_admin_token or not hmac.compare_digest(
        x_admin_token, settings.admin_dashboard_token
    ):
        raise HTTPException(status_code=401, detail="Invalid admin token")


class AdminInvitationMint(BaseModel):
    count: int = Field(1, ge=1, le=100)
    door: str = Field("founding", pattern="^(founding|vouched)$")
    note: str | None = Field(None, max_length=255)


class AdminContributorGrant(BaseModel):
    door: str = Field("earned", pattern="^(earned|founding)$")


@router.get("/health")
async def admin_health(x_admin_token: str | None = Header(default=None)) -> dict:
    _check_token(x_admin_token)
    return {"status": "ok", "admin": True}


@router.get("/users/recent")
async def users_recent(
    db: DbSession,
    limit: int = Query(100, ge=1, le=500),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Recent signups with email + telemetry detail."""
    _check_token(x_admin_token)
    sql = text(
        "SELECT id, email, display_name, country_code, platform, skill_version, "
        "install_source, reputation_score, is_moderator, created_at, last_seen_at "
        "FROM users ORDER BY created_at DESC LIMIT :lim"
    )
    rows = (await db.execute(sql, {"lim": limit})).fetchall()
    return {
        "users": [
            {
                "id": str(r[0]),
                "email": r[1],
                "display_name": r[2],
                "country_code": r[3],
                "platform": r[4],
                "skill_version": r[5],
                "install_source": r[6],
                "reputation_score": float(r[7] or 0),
                "is_moderator": bool(r[8]),
                "created_at": r[9].isoformat() if r[9] else None,
                "last_seen_at": r[10].isoformat() if r[10] else None,
            }
            for r in rows
        ]
    }


@router.get("/users/{user_id}")
async def user_detail(
    user_id: str,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Full per-user view: profile + traces + votes + amendments counts."""
    _check_token(x_admin_token)
    user_row = (await db.execute(
        text(
            "SELECT id, email, display_name, country_code, platform, skill_version, "
            "install_source, reputation_score, is_moderator, created_at, last_seen_at, "
            "updated_at FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    )).fetchone()
    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    counts_row = (await db.execute(
        text(
            "SELECT "
            "(SELECT COUNT(*) FROM traces WHERE contributor_id = :uid) AS traces, "
            "(SELECT COUNT(*) FROM votes  WHERE voter_id       = :uid) AS votes, "
            "(SELECT COUNT(*) FROM amendments WHERE submitter_id = :uid) AS amendments, "
            "(SELECT COALESCE(SUM(retrieval_count),0) FROM traces "
            "  WHERE contributor_id = :uid) AS total_retrievals"
        ),
        {"uid": user_id},
    )).fetchone()

    traces_rows = (await db.execute(
        text(
            "SELECT id, title, retrieval_count, trust_score, created_at "
            "FROM traces WHERE contributor_id = :uid ORDER BY created_at DESC LIMIT 50"
        ),
        {"uid": user_id},
    )).fetchall()

    return {
        "user": {
            "id": str(user_row[0]),
            "email": user_row[1],
            "display_name": user_row[2],
            "country_code": user_row[3],
            "platform": user_row[4],
            "skill_version": user_row[5],
            "install_source": user_row[6],
            "reputation_score": float(user_row[7] or 0),
            "is_moderator": bool(user_row[8]),
            "created_at": user_row[9].isoformat() if user_row[9] else None,
            "last_seen_at": user_row[10].isoformat() if user_row[10] else None,
            "updated_at": user_row[11].isoformat() if user_row[11] else None,
        },
        "counts": {
            "traces": int(counts_row[0]),
            "votes": int(counts_row[1]),
            "amendments": int(counts_row[2]),
            "total_retrievals": int(counts_row[3]),
        },
        "recent_traces": [
            {
                "id": str(r[0]),
                "title": r[1],
                "retrieval_count": int(r[2] or 0),
                "trust_score": float(r[3] or 0),
                "created_at": r[4].isoformat() if r[4] else None,
            }
            for r in traces_rows
        ],
    }


@router.get("/signups/timeline")
async def signups_timeline(
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Daily signups with email-vs-anonymous breakdown + country split."""
    _check_token(x_admin_token)
    # days bound via int() to prevent SQL injection in INTERVAL literal
    sql_str = (
        "SELECT date_trunc('day', created_at) AS day, "
        "COUNT(*) AS total, "
        "COUNT(email) AS with_email, "
        "COUNT(country_code) AS with_country "
        f"FROM users WHERE created_at >= NOW() - INTERVAL '{int(days)} days' "
        "GROUP BY day ORDER BY day ASC"
    )
    rows = (await db.execute(text(sql_str))).fetchall()
    return {
        "days": days,
        "series": [
            {
                "date": r[0].date().isoformat(),
                "total": int(r[1]),
                "with_email": int(r[2]),
                "with_country": int(r[3]),
            }
            for r in rows
        ],
    }


@router.get("/sessions/recent")
async def sessions_recent(
    db: DbSession,
    limit: int = Query(200, ge=1, le=1000),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Recent skill session activity from trigger_stats reports."""
    _check_token(x_admin_token)
    sql = text(
        "SELECT id, session_id, stats_json, reported_at FROM trigger_stats "
        "ORDER BY reported_at DESC LIMIT :lim"
    )
    rows = (await db.execute(sql, {"lim": limit})).fetchall()
    return {
        "sessions": [
            {
                "id": str(r[0]),
                "session_id": r[1],
                "stats": r[2],
                "reported_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]
    }


@router.get("/traces/recent")
async def traces_recent(
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Recent contributions with contributor email."""
    _check_token(x_admin_token)
    sql = text(
        "SELECT t.id, t.title, t.status, t.created_at, t.retrieval_count, "
        "t.trust_score, t.somatic_intensity, t.impact_level, "
        "u.email, u.display_name, u.country_code "
        "FROM traces t LEFT JOIN users u ON t.contributor_id = u.id "
        "ORDER BY t.created_at DESC LIMIT :lim"
    )
    rows = (await db.execute(sql, {"lim": limit})).fetchall()
    return {
        "traces": [
            {
                "id": str(r[0]),
                "title": r[1],
                "status": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "retrieval_count": int(r[4] or 0),
                "trust_score": float(r[5] or 0),
                "somatic_intensity": float(r[6] or 0),
                "impact_level": r[7],
                "contributor_email": r[8],
                "contributor_display_name": r[9],
                "contributor_country": r[10],
            }
            for r in rows
        ]
    }


@router.get("/votes/recent")
async def votes_recent(
    db: DbSession,
    limit: int = Query(100, ge=1, le=500),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Recent votes with voter email + trace title."""
    _check_token(x_admin_token)
    sql = text(
        "SELECT v.id, v.vote_type, v.created_at, "
        "u.email, u.display_name, "
        "t.id AS trace_id, t.title AS trace_title "
        "FROM votes v "
        "JOIN users u ON v.voter_id = u.id "
        "JOIN traces t ON v.trace_id = t.id "
        "ORDER BY v.created_at DESC LIMIT :lim"
    )
    rows = (await db.execute(sql, {"lim": limit})).fetchall()
    return {
        "votes": [
            {
                "id": str(r[0]),
                "vote_type": r[1],
                "created_at": r[2].isoformat() if r[2] else None,
                "voter_email": r[3],
                "voter_display_name": r[4],
                "trace_id": str(r[5]),
                "trace_title": r[6],
            }
            for r in rows
        ]
    }


@router.get("/funnel")
async def funnel(
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Acquisition + activation funnel.

    Stages:
      installs        = users with platform set
      pinged          = users with last_seen_at set (skill has heartbeated)
      pinged_7d       = users seen in last 7 days
      contributed     = users with ≥1 trace
      voted           = users with ≥1 vote
      amended         = users with ≥1 amendment
    """
    _check_token(x_admin_token)
    sql = text(
        "SELECT "
        "(SELECT COUNT(*) FROM users) AS total_users, "
        "(SELECT COUNT(*) FROM users WHERE platform IS NOT NULL) AS installs, "
        "(SELECT COUNT(*) FROM users WHERE last_seen_at IS NOT NULL) AS pinged, "
        "(SELECT COUNT(*) FROM users WHERE last_seen_at >= NOW() - INTERVAL '7 days') AS pinged_7d, "
        "(SELECT COUNT(DISTINCT contributor_id) FROM traces WHERE contributor_id IS NOT NULL) AS contributed, "
        "(SELECT COUNT(DISTINCT voter_id) FROM votes) AS voted, "
        "(SELECT COUNT(DISTINCT submitter_id) FROM amendments) AS amended"
    )
    row = (await db.execute(sql)).fetchone()
    return {
        "stages": {
            "total_users": int(row[0]),
            "installs": int(row[1]),
            "pinged": int(row[2]),
            "pinged_7d": int(row[3]),
            "contributed": int(row[4]),
            "voted": int(row[5]),
            "amended": int(row[6]),
        }
    }


@router.post("/invitations", status_code=201)
async def admin_mint_invitations(
    body: AdminInvitationMint,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Mint founding/vouched invitation codes (admin only).

    Codes are attributed to the oldest moderator account so lineage always
    points at a real user. Raw codes are returned exactly once.
    """
    _check_token(x_admin_token)

    row = (
        await db.execute(
            text(
                "SELECT id FROM users WHERE is_moderator = true "
                "ORDER BY created_at ASC LIMIT 1"
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="No moderator account exists to attribute invitations to",
        )
    created_by = row[0]

    codes = []
    for _ in range(body.count):
        raw_code = generate_invite_code()
        await db.execute(
            text(
                "INSERT INTO invitations (id, code_hash, created_by, door, note) "
                "VALUES (:id, :code_hash, :created_by, :door, :note)"
            ),
            {
                "id": uuid.uuid4(),
                "code_hash": hash_api_key(raw_code),
                "created_by": created_by,
                "door": body.door,
                "note": body.note,
            },
        )
        codes.append(raw_code)
    await db.commit()

    return {"codes": codes, "door": body.door, "count": len(codes)}


@router.post("/contributors/{user_id}", status_code=200)
async def admin_grant_contributor(
    user_id: str,
    body: AdminContributorGrant,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Grant contributor status directly — the earned door (Wanted Board
    quest reviewed by a Keeper) or founding door for hand-picked contributors."""
    _check_token(x_admin_token)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user id")

    row = (
        await db.execute(
            text(
                "UPDATE users SET can_contribute = true, entry_door = :door, "
                "invites_remaining = GREATEST(invites_remaining, 2) "
                "WHERE id = :uid RETURNING id, invites_remaining"
            ),
            {"door": body.door, "uid": uid},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()

    return {"user_id": str(row[0]), "door": body.door, "invites_remaining": row[1]}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    db: DbSession,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Delete an account that never participated — probe/junk signups only.

    Refuses (409) for moderators and for any user something still references:
    traces, votes, amendments, domain reputation, invitations created or
    redeemed, accounts they invited. Real participants are never deletable
    this way.
    """
    _check_token(x_admin_token)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user id")

    if uid == SYSTEM_USER_ID:
        raise HTTPException(
            status_code=409, detail="System account cannot be deleted"
        )

    user_row = (
        await db.execute(
            text("SELECT is_moderator FROM users WHERE id = :uid"),
            {"uid": uid},
        )
    ).first()
    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user_row[0]:
        raise HTTPException(
            status_code=409, detail="Moderator accounts cannot be deleted"
        )

    refs_row = (
        await db.execute(
            text(
                "SELECT "
                "(SELECT COUNT(*) FROM traces WHERE contributor_id = :uid), "
                "(SELECT COUNT(*) FROM votes WHERE voter_id = :uid), "
                "(SELECT COUNT(*) FROM amendments WHERE submitter_id = :uid), "
                "(SELECT COUNT(*) FROM contributor_domain_reputation "
                "  WHERE contributor_id = :uid), "
                "(SELECT COUNT(*) FROM invitations WHERE created_by = :uid), "
                "(SELECT COUNT(*) FROM invitations WHERE redeemed_by = :uid), "
                "(SELECT COUNT(*) FROM users WHERE invited_by = :uid)"
            ),
            {"uid": uid},
        )
    ).fetchone()
    labels = (
        "traces",
        "votes",
        "amendments",
        "domain_reputation",
        "invitations_created",
        "invitations_redeemed",
        "invitees",
    )
    refs = {label: int(n) for label, n in zip(labels, refs_row) if int(n)}
    if refs:
        raise HTTPException(
            status_code=409,
            detail=f"User has activity and cannot be deleted: {refs}",
        )

    row = (
        await db.execute(
            text("DELETE FROM users WHERE id = :uid RETURNING id, email"),
            {"uid": uid},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()

    return {"deleted": str(row[0]), "email": row[1]}
