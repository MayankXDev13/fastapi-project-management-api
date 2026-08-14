from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from schemas.base import APIResponse


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    email: Optional[str] = None


class VerifyEmailRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class UserResponse(APIResponse):
    id: str
    email: str
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    message: str