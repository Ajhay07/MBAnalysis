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
    # Deliberately a cheap, import-only check - NOT is_paddleocr_available(), which
    # constructs the real PaddleOCR engine (downloads/loads model weights over the network,
    # can take a while on first run). An earlier version of this hook called that eagerly at
    # boot and it was the wrong call: it made the container slow to become healthy during a
    # redeploy, and Railway killing a slow-starting container mid-construction is exactly what
    # produced a PaddlePaddle C++ "FatalError: Termination signal is detected" trace in the
    # logs (that's PaddlePaddle's own SIGTERM handler, not evidence of a real crash - but a
    # real side effect of starting the engine eagerly here). The engine stays lazy, built on
    # the first real OCR request as originally designed; this only logs whether the import
    # itself succeeded, which needs no network call and can't block startup.
    from app.services.paddle_ocr import PaddleOCR
    if PaddleOCR is not None:
        logger.info("PaddleOCR import OK - OCR engine will be constructed on first real use.")
    else:
        logger.error(
            "PaddleOCR could NOT be imported on this server - every analysis will come back "
            "with zero components (see the import exception logged just above, if any)."
        )


@app.get("/api/health")
def health():
    # Also import-only (see the startup hook above for why): never triggers the slow,
    # network-dependent engine construction from a health-check request.
    from app.services.paddle_ocr import PaddleOCR
    return {
        "status": "ok",
        "ai_mode": settings.ai_mode,
        # True only means the paddleocr package imported - it does not guarantee the engine
        # will construct successfully too (that happens lazily on first real OCR request, and
        # can still fail independently; see app/services/paddle_ocr.py's own logging for that).
        "paddleocr_importable": PaddleOCR is not None,
    }
