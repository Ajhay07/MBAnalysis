import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "mbanalysis_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["UPLOAD_DIR"] = os.path.join(tempfile.gettempdir(), "mbanalysis_test_uploads")
os.environ.setdefault("OPENAI_API_KEY", "")

if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

from app.database import Base, engine, SessionLocal  # noqa: E402
import app.models  # noqa: E402

Base.metadata.create_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
