from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models.models import Analysis, Component, AuditLog, Bom, User
from app.schemas.api import AnalysisOut, ComponentOut, ComponentUpdate, BomOut
from app.services.bom_service import generate_bom_from_analysis
from app.services.calc_engine_service import run_component_calculation

router = APIRouter(prefix="/api/analyses", tags=["analyses"])

editor = require_role("admin", "engineer")


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


@router.patch("/components/{component_id}", response_model=ComponentOut)
def update_component(component_id: str, payload: ComponentUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(editor)):
    component = db.query(Component).get(component_id)
    if not component:
        raise HTTPException(404, "Component not found")
    before = {"make_buy": component.make_buy.value if hasattr(component.make_buy, "value") else component.make_buy,
              "verification_status": component.verification_status}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.add(AuditLog(entity_type="component", entity_id=component_id, action="updated",
                     details={"before": before, "after": payload.model_dump(exclude_unset=True)},
                     actor=current_user.email))
    db.commit()
    db.refresh(component)
    return component


@router.post("/components/{component_id}/calculate", response_model=ComponentOut)
def calculate_component(component_id: str, db: Session = Depends(get_db),
                         current_user: User = Depends(editor)):
    """Runs this component through the engineering_engine (classification + the matching
    calculator), using its current calc_inputs as manual readings, and persists the result on
    calc_spec_identifier/calc_result. Never 404s into a calculation failure - an unclassified
    or missing-input component still gets a result dict (status UNCLASSIFIED/MISSING/etc.),
    same convention the engine itself uses rather than raising."""
    component = db.query(Component).get(component_id)
    if not component:
        raise HTTPException(404, "Component not found")
    result = run_component_calculation(component)
    component.calc_spec_identifier = result.get("spec_identifier")
    component.calc_result = result
    db.add(AuditLog(entity_type="component", entity_id=component_id, action="calculated",
                     details={"spec_identifier": component.calc_spec_identifier, "status": result.get("status")},
                     actor=current_user.email))
    db.commit()
    db.refresh(component)
    return component


@router.post("/{analysis_id}/approve")
def approve_analysis(analysis_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(editor)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    from app.models.models import Drawing, DrawingStatus
    drawing = db.query(Drawing).get(analysis.drawing_id)
    if drawing:
        drawing.status = DrawingStatus.REVIEWED
    db.add(AuditLog(entity_type="analysis", entity_id=analysis_id, action="approved", details={},
                     actor=current_user.email))
    db.commit()
    return {"ok": True}


@router.post("/{analysis_id}/generate-bom", response_model=BomOut)
def generate_bom(analysis_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(editor)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    bom = generate_bom_from_analysis(db, analysis, actor=current_user.email)
    return bom
