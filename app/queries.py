import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, Membership


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
