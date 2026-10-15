from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.models import User, UserRole
from app.schemas.auth import LoginRequest, Token, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
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


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Same error for "no such user" and "wrong password" - don't leak which one it was.
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    settings = get_settings()
    role = user.role.value if hasattr(user.role, "value") else user.role
    token = create_access_token(subject=user.id, role=role)
    _set_auth_cookie(response, token)
    return Token(access_token=token, expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post("/demo-login", response_model=Token)
def demo_login(response: Response, db: Session = Depends(get_db)):
    """Public, unauthenticated endpoint for the login page's "Try the demo" button.

    Logs the visitor in as a fixed, server-side-known read-only viewer account - no password is
    ever generated, stored in a way anyone could read, or transmitted by the frontend. The demo
    account is lazily created on first call (idempotent: subsequent calls reuse the same row) and
    is always UserRole.VIEWER, which every mutating endpoint in this app already rejects via
    require_role("admin", "engineer") (see app/auth.py require_role + its usage in
    analyses/boms/demo/drawings/procurement routers). That role gate is the actual security
    boundary here, not secrecy of a password - this endpoint intentionally has none to leak.
    Not rate-limited at the app layer; acceptable for a public demo login that only ever yields a
    read-only session, but put a reverse-proxy/WAF rate limit in front of it if abuse becomes a
    concern.
    """
    settings = get_settings()
    demo_email = settings.DEMO_EMAIL or "demo@mbanalysis.local"

    user = db.query(User).filter(User.email == demo_email).first()
    if user is None:
        user = User(
            email=demo_email,
            # Random, never persisted anywhere readable, never sent to the client, and never
            # checked by anything (this endpoint doesn't take a password) - it only exists
            # because the `hashed_password` column is NOT NULL. Nobody can log in as this
            # account through the normal /login form.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role=UserRole.VIEWER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="Demo account is disabled")
    elif user.role != UserRole.VIEWER:
        # Defensive: if an admin ever manually promoted this row, refuse rather than hand out an
        # elevated session through an unauthenticated endpoint.
        raise HTTPException(status_code=403, detail="Demo account misconfigured")

    role = user.role.value if hasattr(user.role, "value") else user.role
    token = create_access_token(subject=user.id, role=role)
    _set_auth_cookie(response, token)
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
