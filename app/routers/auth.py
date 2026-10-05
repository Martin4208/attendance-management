from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.schemas import SignupRequest, SignupResponse, LoginRequest, LoginResponse, MeResponse
from app.models import Plan, Tenant, User, Membership, AuditLog
from app.security import hash_password, verify_password, create_access_token
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    
    tenant = Tenant(name=payload.tenant_name, plan_id=plan.id)
    user = User(
        name=payload.user_name, 
        email=payload.email.lower(), 
        password_hash=hash_password(payload.password)
    )
    
    try:
        db.add_all([tenant, user])
        db.flush()
        
        membership = Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role="owner"
        )
        audit_log = AuditLog(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="tenant.create",
            target_type="tenant",
            target_id=str(tenant.id),
            after={
                "tenant_name": tenant.name,
                "plan": plan.name,
                "creator_user_id": str(user.id),
                "role": membership.role
            }
        )
        
        response = {
            "tenant_id": tenant.id, 
            "user_id": user.id, 
            "email": user.email, 
            "role": membership.role
        }
        
        db.add_all([membership, audit_log])
        
        db.commit()
    except IntegrityError as e:
        db.rollback()
        name = e.orig.diag.constraint_name
        if name == "users_email_lower_uq":
            raise HTTPException(status_code=409, detail="Email already registered")
        raise
    
    return response


@router.post("/login", response_model=LoginResponse, status_code=200)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email.lower(), User.deleted_at.is_(None))).scalar_one_or_none()
    
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or Password isn't correct", headers={"WWW-Authenticate": "Bearer"})
    
    token = create_access_token(user.id)
    return LoginResponse(access_token=token, token_type="bearer")


@router.post("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
