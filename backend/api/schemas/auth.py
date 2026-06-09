import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    username: Annotated[str, Field(min_length=1, max_length=50)]
    password: Annotated[str, Field(min_length=8, max_length=100)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_guest: bool = False
    user_id: Optional[str] = None
    username: Optional[str] = None


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    is_active: bool

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    username: Optional[Annotated[str, Field(min_length=1, max_length=50)]] = None
    password: Optional[Annotated[str, Field(min_length=8, max_length=100)]] = None
