from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Analysis, Component, AuditLog, Bom
from app.schemas.api import AnalysisOut, ComponentOut, ComponentUpdate, BomOut
from app.services.bom_service import generate_bom_from_analysis

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


@router.patch("/components/{component_id}", response_model=ComponentOut)
def update_component(component_id: str, payload: ComponentUpdate, db: Session = Depends(get_db)):
    component = db.query(Component).get(component_id)
    if not component:
        raise HTTPException(404, "Component not found")
    before = {"make_buy": component.make_buy.value if hasattr(component.make_buy, "value") else component.make_buy,
              "verification_status": component.verification_status}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.add(AuditLog(entity_type="component", entity_id=component_id, action="updated",
                     details={"before": before, "after": payload.model_dump(exclude_unset=True)}))
    db.commit()
    db.refresh(component)
    return component


@router.post("/{analysis_id}/approve")
def approve_analysis(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    from app.models.models import Drawing, DrawingStatus
    drawing = db.query(Drawing).get(analysis.drawing_id)
    if drawing:
        drawing.status = DrawingStatus.REVIEWED
    db.add(AuditLog(entity_type="analysis", entity_id=analysis_id, action="approved", details={}))
    db.commit()
    return {"ok": True}


@router.post("/{analysis_id}/generate-bom", response_model=BomOut)
def generate_bom(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    bom = generate_bom_from_analysis(db, analysis)
    return bom
