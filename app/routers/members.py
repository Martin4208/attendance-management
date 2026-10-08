import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import AttendanceRecord, AuditLog, Membership, User
from app.queries import (
    attendance_stmt,
    check_user_limit,
    ensure_not_last_owner,
    get_active_membership,
    list_members,
    paginate,
    parse_cursor,
)
from app.schemas import (
    AttendanceListOut,
    MemberAddIn,
    MemberResponse,
    MemberRoleIn,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["members"])


@router.get("/members", response_model=list[MemberResponse])
def get_members(
    membership: Membership = Depends(require_role("member")),
    db: Session = Depends(get_db),
):
    return list_members(db, membership.tenant_id)


@router.post("/members", response_model=MemberResponse, status_code=201)
def add_member(
    body: MemberAddIn,
    membership: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    # admin が追加できるのは member だけ。owner は全ロール
    if membership.role != "owner" and body.role != "member":
        raise HTTPException(status_code=403, detail="Not allowed to assign this role")

    user = db.execute(
        select(User).where(
            User.email == body.email.lower(), User.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="No user")

    existing = db.execute(
        select(Membership).where(
            Membership.tenant_id == membership.tenant_id,
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing is not None and existing.deleted_at is None:
        raise HTTPException(status_code=409, detail="Already a member")

    check_user_limit(db, membership.tenant_id)

    if existing is not None:
        # 外されたメンバーの再追加: INSERT ではなく復帰させる
        before = {"user_id": str(user.id), "role": existing.role, "active": False}
        existing.deleted_at = None
        existing.role = body.role
    else:
        before = None
        db.add(
            Membership(
                tenant_id=membership.tenant_id, user_id=user.id, role=body.role
            )
        )

    db.add(
        AuditLog(
            tenant_id=membership.tenant_id,
            actor_user_id=membership.user_id,
            action="member.add",
            target_type="membership",
            target_id=str(user.id),
            before=before,
            after={"user_id": str(user.id), "role": body.role, "active": True},
        )
    )

    response = {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": body.role,
    }
    try:
        db.commit()
    except IntegrityError:
        # 同時に同じ人が追加された場合(UNIQUE(tenant_id, user_id))
        db.rollback()
        raise HTTPException(status_code=409, detail="Already a member")
    return response


@router.patch("/members/{user_id}/role", response_model=MemberResponse)
def change_role(
    user_id: uuid.UUID,
    body: MemberRoleIn,
    membership: Membership = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    target = get_active_membership(db, membership.tenant_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No member")

    user = db.get(User, user_id)
    old_role = target.role

    if old_role != body.role:
        # owner を降格するときは、最後の owner でないことを確認する
        if old_role == "owner":
            ensure_not_last_owner(db, membership.tenant_id)

        target.role = body.role
        db.add(
            AuditLog(
                tenant_id=membership.tenant_id,
                actor_user_id=membership.user_id,
                action="member.role_change",
                target_type="membership",
                target_id=str(user_id),
                before={"user_id": str(user_id), "role": old_role},
                after={"user_id": str(user_id), "role": body.role},
            )
        )

    response = {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": body.role,
    }
    db.commit()
    return response


@router.delete("/members/{user_id}", status_code=204)
def remove_member(
    user_id: uuid.UUID,
    membership: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    # 判定の順: 対象がいるか(404) → 権限(403) → 最後の owner(409)
    target = get_active_membership(db, membership.tenant_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No member")

    if membership.role != "owner" and target.role != "member":
        raise HTTPException(status_code=403, detail="Not allowed to remove this member")

    if target.role == "owner":
        ensure_not_last_owner(db, membership.tenant_id)

    old_role = target.role
    target.deleted_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            tenant_id=membership.tenant_id,
            actor_user_id=membership.user_id,
            action="member.remove",
            target_type="membership",
            target_id=str(user_id),
            before={"user_id": str(user_id), "role": old_role, "active": True},
            after=None,
        )
    )
    db.commit()
    return Response(status_code=204)


@router.get("/members/{user_id}/attendance", response_model=AttendanceListOut)
def list_member_attendance(
    user_id: uuid.UUID,
    membership: Membership = Depends(require_role("owner")),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
):
    cursor_key = parse_cursor(cursor)

    target = get_active_membership(db, membership.tenant_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No member")

    stmt = attendance_stmt(membership.tenant_id, user_id)
    return paginate(
        db, stmt, AttendanceRecord.clock_in_time, AttendanceRecord.id, limit, cursor_key
    )
    