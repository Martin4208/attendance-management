from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import MemberResponse
from app.models import Membership
from app.dependencies import require_role
from app.queries import list_members

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["members"])


@router.get("/members", response_model=list[MemberResponse])
def get_members(
    membership: Membership = Depends(require_role("member")), 
    db: Session = Depends(get_db)
):
    return list_members(db, membership.tenant_id)

