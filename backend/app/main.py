from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import drawings, analyses, boms, procurement, calculations, dashboard, review, demo

settings = get_settings()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Engineering Drawing Intelligence & BOM System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
