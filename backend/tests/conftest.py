import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "mbanalysis_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["UPLOAD_DIR"] = os.path.join(tempfile.gettempdir(), "mbanalysis_test_uploads")
os.environ.setdefault("AI_PROVIDER", "")
# Fixed test secret: deterministic, avoids the "generate a random dev secret" warning noise on
# every test run. Never reused outside tests.
os.environ.setdefault("JWT_SECRET", "test-only-secret-do-not-use-in-real-deployments")

if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

from app.database import Base, engine, SessionLocal  # noqa: E402
import app.models  # noqa: E402
from app.models.models import User, UserRole  # noqa: E402
from app.security import hash_password  # noqa: E402

Base.metadata.create_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture
def make_user(db):
    """Creates a user with a known plaintext password and returns (user, plain_password)."""

    def _make(role: UserRole = UserRole.VIEWER, password: str = "correct-horse-battery"):
        email = f"{role.value}-{uuid.uuid4().hex[:8]}@example.com"
        user = User(email=email, hashed_password=hash_password(password), role=role, is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, password

    return _make
