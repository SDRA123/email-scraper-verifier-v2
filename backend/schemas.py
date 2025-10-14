from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    is_admin: Optional[bool] = False
    is_active: Optional[bool] = True

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class EmailDataResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
    verified: bool = False
    status: Optional[str] = None
    
    class Config:
        from_attributes = True

class VerificationResult(BaseModel):
    email: str
    is_valid: bool
    reason: Optional[str] = None