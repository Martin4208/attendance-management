import uuid
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict

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
    