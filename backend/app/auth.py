"""Auth dependencies: get_current_user and the require_role() factory.

Token transport: an httpOnly cookie named `access_token`, set by POST /api/auth/login.
Chosen over localStorage because the frontend's existing api client (frontend/src/lib/api.ts)
already calls the backend through Next.js's `rewrites()` proxy, so every browser request lands
on the *same origin* (localhost:3000) as far as the browser is concerned - the proxy forwards
Set-Cookie transparently. That means:
  - No code in api.ts has to read/attach a token to every request; the browser does it.
  - The token is never reachable from page JavaScript (httpOnly), so an XSS bug can't exfiltrate
    it the way it could with localStorage.
  - No CORS credentials dance is needed since nothing crosses an origin boundary.
See README "Authentication Setup" for the full writeup, including the tradeoff this implies
(a cookie-based session is harder to use from a non-browser API client; for that case this
dependency also accepts a normal `Authorization: Bearer <token>` header, which is what the
test suite uses for simplicity).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User
from app.security import decode_access_token

COOKIE_NAME = "access_token"


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).get(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_role(*allowed_roles: str):
    """Dependency factory: raises 403 unless the current user's role is one of allowed_roles.
    Still requires a valid session first (reuses get_current_user), so an unauthenticated
    request gets 401, and an authenticated-but-wrong-role request gets 403."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        role = user.role.value if hasattr(user.role, "value") else user.role
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
        return user

    return _dependency
