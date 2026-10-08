import uuid

from fastapi import HTTPException
from sqlalchemy import select, tuple_, func
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, Membership, User, Plan, Tenant
from app.pagination import decode_cursor, encode_cursor


def list_members(db: Session, tenant_id: uuid.UUID):
    stmt = (
        select(User.id.label("user_id"), User.name, User.email, Membership.role)
        .select_from(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.deleted_at.is_(None),
            User.deleted_at.is_(None),
        )
        .order_by(Membership.created_at, Membership.id)
    )
    return db.execute(stmt).all()


def parse_cursor(cursor: str | None):
    """cursor を (時刻, id) に戻す。壊れていれば 422。"""
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid cursor")


def attendance_stmt(tenant_id, user_id):
    """ある人の、削除されていない勤怠を探すクエリ(並び順・件数はまだ付けない)。"""
    return select(AttendanceRecord).where(
        AttendanceRecord.tenant_id == tenant_id,
        AttendanceRecord.user_id == user_id,
        AttendanceRecord.deleted_at.is_(None),
    )


def paginate(db, stmt, time_col, id_col, limit, cursor_key):
    """(時刻, id) の降順で cursor 方式のページを返す。"""
    if cursor_key is not None:
        stmt = stmt.where(tuple_(time_col, id_col) < tuple_(cursor_key[0], cursor_key[1]))
    stmt = stmt.order_by(time_col.desc(), id_col.desc()).limit(limit + 1)

    rows = db.execute(stmt).scalars().all()
    has_next = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_next:
        last = rows[-1]  # 余分な1件を捨てたあとの最後の行
        next_cursor = encode_cursor(getattr(last, time_col.key), last.id)

    return {"items": rows, "next_cursor": next_cursor}


def get_active_membership(db, tenant_id, user_id):
    return db.execute(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def check_user_limit(db, tenant_id):
    """プランの人数上限に達していたら 403。数えるのは deleted_at IS NULL の所属だけ。"""
    tenant = db.get(Tenant, tenant_id)
    plan = db.get(Plan, tenant.plan_id)
    if plan.user_limit is None:
        return
    count = db.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.deleted_at.is_(None))
    ).scalar_one()
    if count >= plan.user_limit:
        raise HTTPException(status_code=403, detail="Plan user limit reached")


def ensure_not_last_owner(db, tenant_id):
    """owner が 1 人以下なら 409。削除と降格の両方から呼ぶ。

    owner の行を FOR UPDATE でロックしてから数える。同時に 2 人の owner を
    外そうとしても、後から来た側はロックが解けるまで待ち、最新の状態で数え直す。
    """
    owners = db.execute(
        select(Membership)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.role == "owner",
            Membership.deleted_at.is_(None),
        )
        .with_for_update()
    ).scalars().all()
    if len(owners) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last owner")