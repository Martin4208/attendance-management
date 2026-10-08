from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import AuditLog, Membership
from app.queries import paginate, parse_cursor
from app.schemas import AuditLogListOut

router = APIRouter(prefix="/tenants/{tenant_id}/audit-logs", tags=["audit-logs"])


@router.get("", response_model=AuditLogListOut)
def list_audit_logs(
    membership: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
):
    cursor_key = parse_cursor(cursor)
    stmt = select(AuditLog).where(AuditLog.tenant_id == membership.tenant_id)
    return paginate(db, stmt, AuditLog.created_at, AuditLog.id, limit, cursor_key)