"""Password hashing + JWT issuing/verification.

Library choices (documented per project convention of explaining adapter-style decisions):
- passlib[bcrypt] for password hashing: industry-standard, handles salting and future algorithm
  migration (`deprecated="auto"`) without us hand-rolling anything. Pinned alongside
  bcrypt==4.0.1 in requirements.txt - passlib 1.7.4's bcrypt backend probes an attribute bcrypt
  removed in 4.1+, so a newer bcrypt breaks hashing outright. See requirements.txt comment.
- python-jose[cryptography] for JWT: simple encode/decode API, already a common FastAPI pairing,
  avoids pulling in a full OAuth2 server library for what is just a signed-expiry-claim token.
"""
from __future__ import annotations

import secrets
import warnings
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_cached_jwt_secret: str | None = None


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Malformed/legacy hash - treat as non-matching rather than raising.
        return False


def get_jwt_secret() -> str:
    """Resolve the signing secret, failing loud outside development if unset.

    - If JWT_SECRET is set in the environment/.env, always use it (any environment).
    - If unset AND ENVIRONMENT == "development": generate a random secret once per process
      and warn loudly. This keeps `uvicorn --reload` usable with zero config for local demo
      use, at the documented cost that every process restart invalidates all existing sessions
      (everyone has to log in again) since the signing key changed.
    - If unset in any non-development environment: raise immediately. Silently generating a
      secret in what's supposed to be a real deployment would mean tokens stop validating on
      every restart/redeploy and, worse, nobody would notice the app never had a real secret.
    """
    global _cached_jwt_secret
    if _cached_jwt_secret is not None:
        return _cached_jwt_secret

    settings = get_settings()
    if settings.JWT_SECRET:
        _cached_jwt_secret = settings.JWT_SECRET
        return _cached_jwt_secret

    if settings.ENVIRONMENT == "development":
        generated = secrets.token_hex(32)
        warnings.warn(
            "JWT_SECRET is not set. Generating a random development-only secret for this "
            "process. All issued tokens will stop validating the next time the server "
            "restarts (everyone will need to log in again). Set JWT_SECRET in backend/.env "
            "for a stable secret across restarts.",
            stacklevel=2,
        )
        _cached_jwt_secret = generated
        return _cached_jwt_secret

    raise RuntimeError(
        "JWT_SECRET must be set when ENVIRONMENT is not 'development'. Generate one with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\" and set it in your "
        "environment or backend/.env."
    )


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, get_jwt_secret(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
