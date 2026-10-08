from datetime import datetime
import uuid
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, AwareDatetime, model_validator

class SignupRequest(BaseModel):
    tenant_name: str
    user_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    

class SignupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    role: Literal["owner", "admin", "member"]
    
    
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    
class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    
    
class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    email: EmailStr
    

class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    user_id: uuid.UUID
    name: str
    email: EmailStr
    role: Literal["owner", "admin", "member"]
    
    
class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    clock_in_time: datetime
    clock_out_time: datetime | None


class AttendanceListOut(BaseModel):
    items: list[AttendanceOut]
    next_cursor: str | None
    
    
class AttendanceUpdateIn(BaseModel):
    clock_in_time: AwareDatetime | None = None
    clock_out_time: AwareDatetime | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if self.clock_in_time is None and self.clock_out_time is None:
            raise ValueError("No changes were made")
        return self
    

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str
    before: dict | None
    after: dict | None
    created_at: datetime


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    next_cursor: str | None
    

class MemberAddIn(BaseModel):
    email: EmailStr
    role: Literal["member", "admin", "owner"] = "member"


class MemberRoleIn(BaseModel):
    role: Literal["member", "admin", "owner"]
    