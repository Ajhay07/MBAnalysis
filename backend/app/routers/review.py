from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Component, Analysis, Drawing, AuditLog

router = APIRouter(prefix="/api/review", tags=["review"])

CONFIDENCE_THRESHOLD = 0.6


@router.get("/queue")
def review_queue(db: Session = Depends(get_db)):
    rows = (
        db.query(Component, Analysis, Drawing)
        .join(Analysis, Component.analysis_id == Analysis.id)
        .join(Drawing, Analysis.drawing_id == Drawing.id)
        .filter((Component.confidence < CONFIDENCE_THRESHOLD) |
                (Component.verification_status == "Unverified"))
        .all()
    )
    return [{
        "component_id": c.id,
        "drawing_id": d.id,
        "drawing_number": d.drawing_number,
        "part_number": c.part_number,
        "description": c.description,
        "confidence": c.confidence,
        "verification_status": c.verification_status,
        "make_buy": c.make_buy.value if hasattr(c.make_buy, "value") else c.make_buy,
    } for c, a, d in rows]


@router.get("/audit-trail")
def audit_trail(entity_type: str | None = None, entity_id: str | None = None,
                 db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    rows = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return [{
        "id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "action": r.action,
        "details": r.details, "actor": r.actor, "created_at": r.created_at.isoformat(),
    } for r in rows]
