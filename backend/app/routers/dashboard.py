from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.models import Drawing, BomLineItem, AuditLog, User
from app.schemas.api import DashboardMetrics

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    drawings = db.query(Drawing).all()
    status_breakdown: dict[str, int] = {}
    for d in drawings:
        key = d.status.value if hasattr(d.status, "value") else d.status
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    line_items = db.query(BomLineItem).all()
    make_count = sum(1 for li in line_items if (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy) == "Make")
    buy_count = sum(1 for li in line_items if (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy) == "Buy")
    review_count = sum(1 for li in line_items if (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy) == "Review")

    recent = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(10).all()
    recent_activity = [{
        "entity_type": a.entity_type, "entity_id": a.entity_id, "action": a.action,
        "details": a.details, "actor": a.actor, "created_at": a.created_at.isoformat(),
    } for a in recent]

    return DashboardMetrics(
        total_drawings=len(drawings),
        status_breakdown=status_breakdown,
        total_bom_items=len(line_items),
        make_count=make_count,
        buy_count=buy_count,
        review_count=review_count,
        recent_activity=recent_activity,
    )


@router.get("/ai-status")
def ai_status(current_user: User = Depends(get_current_user)):
    settings = get_settings()
    vision_model = settings.GEMINI_MODEL if settings.ai_mode == "gemini" else settings.OPENAI_VISION_MODEL
    return {"mode": settings.ai_mode, "vision_model": vision_model}
