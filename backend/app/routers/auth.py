from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.models import User
from app.schemas.auth import LoginRequest, Token, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Same error for "no such user" and "wrong password" - don't leak which one it was.
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    settings = get_settings()
    role = user.role.value if hasattr(user.role, "value") else user.role
    token = create_access_token(subject=user.id, role=role)

    # httpOnly cookie is the transport the frontend relies on (see app/auth.py docstring).
    # secure=False because local dev runs on plain http://localhost; flip to True behind TLS.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return Token(access_token=token, expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post("/logout")
def logout(response: Response):
    # Bearer/JWT tokens are stateless - there is no server-side session to revoke, so "logout"
    # is just clearing the cookie that carries the token. A token taken out of the cookie
    # (e.g. copied manually) before logout remains valid until it expires; this is a documented
    # limitation of the simple re-login-on-expiry approach (see README), not a bug.
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
