"""
Pydantic schemas for authentication and user management.
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    email: str
    password: str
    name: str 
    role: str
    tenant_id: Optional[str] = None
    department_id: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    role: str
    tenant_id: Optional[str] = None
    department_id: Optional[str] = None
    is_active: bool = True


class UserResponse(BaseModel):
    uid: str
    email: str
    name: str
    role: str
    tenant_id: Optional[str] = None
