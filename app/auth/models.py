"""Pydantic models for auth request/response payloads."""
from __future__ import annotations
from pydantic import BaseModel


class VerifyInviteRequest(BaseModel):
    invite_code: str


class VerifyInviteResponse(BaseModel):
    valid: bool
    message: str = ""


class RegisterRequest(BaseModel):
    invite_code: str
    username: str
    exam_region: str
    grade: str = ""
    school: str = ""


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    access_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str
    role: str = "user"
