from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import drawings, analyses, boms, procurement, calculations, dashboard, review, demo, auth, inventory, indents
from app.security import get_jwt_secret

logger = logging.getLogger("app.main")

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
    allow_origins=settings.allowed_origins_list,
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
app.include_router(inventory.router)
app.include_router(indents.router)


@app.on_event("startup")
def _log_ocr_availability() -> None:
    # OCR is the only source of BOM-table evidence for DeterministicProvider (see
    # app/services/paddle_ocr.py / app/providers/deterministic_provider.py) - if PaddleOCR
    # can't import or its engine can't construct on this host, every real analysis silently
    # comes back with zero components. That used to be invisible until a user actually hit
    # "Re-run Analysis" and opened OCR Evidence. Checking it once at boot, with the real
    # import/construction exception already logged (see paddle_ocr.py), means the cause is in
    # `railway logs` immediately after "Application startup complete" rather than buried in a
    # per-request error string. This also warms the engine (several seconds of model loading)
    # before the first real user request instead of during it.
    from app.services.paddle_ocr import is_paddleocr_available
    available = is_paddleocr_available()
    if available:
        logger.info("PaddleOCR engine ready - OCR-based BOM extraction is available.")
    else:
        logger.error(
            "PaddleOCR is NOT available on this server - every analysis will come back with "
            "zero components (see the import/construction error logged just above, if any, "
            "or app/services/paddle_ocr.py's own error string in /api/drawings/{id}/pages/"
            "{n}/ocr)."
        )


@app.get("/api/health")
def health():
    from app.services.paddle_ocr import is_paddleocr_available
    return {
        "status": "ok",
        "ai_mode": settings.ai_mode,
        # Surfaced directly in health since this is the single most common reason a real
        # drawing comes back with zero components - no need to dig through logs or OCR
        # Evidence to find out whether OCR is even available on this deployment.
        "ocr_available": is_paddleocr_available(),
    }
