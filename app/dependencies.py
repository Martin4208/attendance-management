from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import uuid

from app.database import get_db
from app.models import User, Membership
from app.security import decode_access_token

bearer = HTTPBearer()

ROLE_RANK = {"member": 1, "admin": 2, "owner": 3}

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db)
) -> User:
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    
    user = db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return user


def get_current_membership(
    tenant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Membership:
    membership = db.execute(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == current_user.id,
            Membership.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")
    return membership


def require_role(minimum: str):
    if minimum not in ROLE_RANK:
        raise ValueError(f"unknown rolw {minimum}")
    
    def checker(membership: Membership = Depends(get_current_membership)) -> Membership:
        if ROLE_RANK[membership.role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail="Forbidden")
        return membership
    
    return checker
