import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select ,tuple_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.pagination import encode_cursor, decode_cursor
from app.schemas import AttendanceOut, AttendanceListOut, AttendanceUpdateIn
from app.models import Membership, AttendanceRecord, AuditLog
from app.dependencies import require_role
from app.queries import paginate, attendance_stmt, parse_cursor

router = APIRouter(prefix="/tenants/{tenant_id}/attendance", tags=["attendance"])


@router.post("/clock-in", response_model=AttendanceOut, status_code=201)
def clock_in(
    membership: Membership = Depends(require_role("member")), 
    db: Session = Depends(get_db)
):
    attendance_record = AttendanceRecord(
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        clock_in_time=datetime.now(timezone.utc),
    )
    db.add(attendance_record)
    
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if e.orig.diag.constraint_name == "attendance_one_open_uq":
            raise HTTPException(status_code=409, detail="Already clocked-in")
        raise
    
    db.refresh(attendance_record)
    return attendance_record


@router.post("/clock-out", response_model=AttendanceOut, status_code=200)
def clock_out(
    membership: Membership = Depends(require_role("member")), 
    db: Session = Depends(get_db)
):
    attendance_record = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.tenant_id == membership.tenant_id,
            AttendanceRecord.user_id == membership.user_id,
            AttendanceRecord.clock_out_time.is_(None),
            AttendanceRecord.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    
    if attendance_record is None:
        raise HTTPException(status_code=409, detail="No open attendance record")
    
    attendance_record.clock_out_time = datetime.now(timezone.utc)
    
    db.commit()
    
    db.refresh(attendance_record)
    return attendance_record



@router.get("", response_model=AttendanceListOut)
def list_attendances(
    membership: Membership = Depends(require_role("member")), 
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
):
    cursor_key = parse_cursor(cursor)
    stmt = attendance_stmt(membership.tenant_id, membership.user_id)
    return paginate(
        db, stmt, AttendanceRecord.clock_in_time, AttendanceRecord.id, limit, cursor_key
    )


@router.patch("/{record_id}", response_model=AttendanceOut, status_code=200)
def update_attendance_record(
    record_id: uuid.UUID,
    body: AttendanceUpdateIn,
    membership: Membership = Depends(require_role("owner")),
    db: Session = Depends(get_db)
):
    record = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.id == record_id,
            AttendanceRecord.tenant_id == membership.tenant_id,
            AttendanceRecord.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    
    if record is None:
        raise HTTPException(status_code=404, detail="No record")
    
    before = {
        "clock_in_time": record.clock_in_time.isoformat(),
        "clock_out_time": record.clock_out_time.isoformat() if record.clock_out_time is not None else None
    }    
    
    new_in = body.clock_in_time if body.clock_in_time is not None else record.clock_in_time
    new_out = body.clock_out_time if body.clock_out_time is not None else record.clock_out_time
    
    if new_out is not None and new_out <= new_in:
        raise HTTPException(status_code=422, detail="clock_out_time must be after clock_in_time")
    
    record.clock_in_time = new_in
    record.clock_out_time = new_out
    
    after = {
        "clock_in_time": new_in.isoformat(),
        "clock_out_time": new_out.isoformat() if new_out is not None else None
    }
    
    db.add(AuditLog(
        tenant_id=membership.tenant_id,
        actor_user_id=membership.user_id,
        action="attendance.update",
        target_type="attendance_record",
        target_id=str(record.id),
        before=before,
        after=after,
    ))
    
    db.commit()
    db.refresh(record)
    
    return record
