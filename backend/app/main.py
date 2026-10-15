from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import drawings, analyses, boms, procurement, calculations, dashboard, review, demo, auth
from app.security import get_jwt_secret

settings = get_settings()

# Fail loud here (not on first login) if JWT_SECRET is required but unset - see
# app/security.py:get_jwt_secret for the development-vs-everything-else policy.
get_jwt_secret()

# Documented path: run `alembic upgrade head` before starting the app.
# create_all() below remains only as a dev convenience fallback so a fresh
# checkout still boots if migrations haven't been run; it is a no-op once
# alembic has already created the tables (create_all never drops/alters
# existing tables), so it never fights with migration-managed schemas.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Engineering Drawing Intelligence & BOM System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(drawings.router)
app.include_router(analyses.router)
app.include_router(boms.router)
app.include_router(procurement.router)
app.include_router(calculations.router)
app.include_router(dashboard.router)
app.include_router(review.router)
app.include_router(demo.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_mode": settings.ai_mode}
