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
    avatar_url: Optional[str] = None


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    username: str
    avatar_url: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    is_active: bool
    social_provider: Optional[str] = None

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    username: Optional[Annotated[str, Field(min_length=2, max_length=20)]] = None
    email: Optional[EmailStr] = None
    password: Optional[Annotated[str, Field(min_length=8, max_length=100)]] = None
    current_password: Optional[str] = None


class DeleteRequest(BaseModel):
    password: Optional[str] = None


class GoogleLoginRequest(BaseModel):
    access_token: str


class GoogleLoginResponse(TokenResponse):
    is_new_user: bool = False


class EmailCheckResponse(BaseModel):
    available: bool


class UsernameCheckResponse(BaseModel):
    available: bool


class FindUsernameRequest(BaseModel):
    email: EmailStr


class FindUsernameResponse(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordResponse(BaseModel):
    temp_password: str
