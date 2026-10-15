"""Bootstraps the first admin user from ADMIN_EMAIL / ADMIN_PASSWORD in the environment/.env.

Run once after migrations (`alembic upgrade head`):
    python create_admin.py

Safe to re-run: it only creates a user when the users table is completely empty, so it will
never silently reset an existing admin's password or create a second admin by accident. If you
need to add more users (engineer/viewer accounts) afterwards, do it from an authenticated admin
session once the API is running (no bulk-create endpoint is exposed yet - see README).
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.database import SessionLocal, Base, engine
from app.models.models import User, UserRole
from app.security import hash_password


def main() -> int:
    settings = get_settings()
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        print("ADMIN_EMAIL and ADMIN_PASSWORD must both be set in backend/.env before running "
              "this script. Leave them unset only if you don't want a bootstrap admin yet.")
        return 1

    # Dev convenience fallback, same as main.py - a no-op if `alembic upgrade head` already ran.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing_count = db.query(User).count()
        if existing_count > 0:
            print(f"Users table already has {existing_count} user(s); refusing to bootstrap "
                  "again. Delete the users table/row manually if you really want to re-seed, "
                  "or create additional users through the API instead.")
            return 1

        admin = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Created admin user: {settings.ADMIN_EMAIL}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
