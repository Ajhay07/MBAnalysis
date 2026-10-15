from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain str rather than pydantic's EmailStr: EmailStr requires the extra `email-validator`
    # dependency, which isn't otherwise part of this project's stack. Format validity isn't a
    # security boundary here (the password check is what matters); a non-existent email simply
    # won't match any stored user and login will fail with 401 either way.
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str = "viewer"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
