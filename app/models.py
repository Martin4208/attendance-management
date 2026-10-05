import uuid
from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, CheckConstraint, Text, text, DateTime, ForeignKey, func, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "user_limit IS NULL OR user_limit > 0",
            name="plans_user_limit_positive",
        ),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, unique=True)
    user_limit: Mapped[int | None]
    
    
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))   # plans.id への外部キー
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )  # timestamptz、DBの now() がデフォルト
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'admin', 'owner')", name="memberships_role_check"),
        UniqueConstraint("tenant_id", "user_id", name="memberships_tenant_user_uq")
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        CheckConstraint("clock_out_time IS NULL OR clock_out_time > clock_in_time", name="attendance_out_after_in"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],                      # このテーブル側のカラム
            ["memberships.tenant_id", "memberships.user_id"],                      # memberships 側のカラム
            name="attendance_membership_fk",
        ),
        Index(
            "attendance_tenant_user_in_idx",
            "tenant_id", "user_id", "clock_in_time",                   # 月別検索用の3カラム
        ),
        Index(
            "attendance_one_open_uq",
            "tenant_id", "user_id",
            unique=True,
            postgresql_where=text("clock_out_time IS NULL AND deleted_at IS NULL"),      # 退勤前で、削除されていない行だけ
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    clock_in_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_out_time: Mapped[datetime | None] =mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    after: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


Index("users_email_lower_uq", func.lower(User.email), unique=True)
Index("audit_tenant_created_idx", AuditLog.tenant_id, AuditLog.created_at.desc())
Index("audit_tenant_target_idx", AuditLog.tenant_id, AuditLog.target_type, AuditLog.target_id)