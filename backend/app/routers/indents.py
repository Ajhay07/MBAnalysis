from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models.models import AuditLog, Bom, Indent, IndentRule, IndentStatus, User
from app.schemas.api import IndentGenerateRequest, IndentOut, IndentRuleIn, IndentRuleOut
from app.services.indent_pdf import indent_to_pdf_bytes
from app.services.indent_service import generate_indent

router = APIRouter(tags=["indents"])

editor = require_role("admin", "engineer")


@router.post("/api/boms/{bom_id}/indents", response_model=IndentOut)
def create_indent(bom_id: str, payload: IndentGenerateRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(editor)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    try:
        indent = generate_indent(
            db, bom,
            assembly_quantity=payload.assembly_quantity,
            wo_number=payload.wo_number,
            party_name=payload.party_name,
            required_on=payload.required_on,
            serial_no=payload.serial_no,
            indent_date=payload.indent_date,
            rule_ids=payload.rule_ids,
            actor=current_user.email,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return indent


@router.get("/api/boms/{bom_id}/indents", response_model=list[IndentOut])
def list_indents_for_bom(bom_id: str, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    return db.query(Indent).filter(Indent.bom_id == bom_id).order_by(Indent.version.desc()).all()


@router.get("/api/indents/{indent_id}", response_model=IndentOut)
def get_indent(indent_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    indent = db.query(Indent).get(indent_id)
    if not indent:
        raise HTTPException(404, "Indent not found")
    return indent


@router.get("/api/indents/{indent_id}/pdf")
def download_indent_pdf(indent_id: str, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    indent = db.query(Indent).get(indent_id)
    if not indent:
        raise HTTPException(404, "Indent not found")
    pdf_bytes = indent_to_pdf_bytes(indent)
    filename = f"indent_WO{indent.wo_number or indent.id}_v{indent.version}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/indents/{indent_id}/approve", response_model=IndentOut)
def approve_indent(indent_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(editor)):
    """Marks the indent Approved. Does not create a PurchaseRequisition or place any order -
    that remains a separate, explicitly authorized action under /api/procurement."""
    indent = db.query(Indent).get(indent_id)
    if not indent:
        raise HTTPException(404, "Indent not found")
    if indent.status != IndentStatus.DRAFT:
        raise HTTPException(409, f"Indent is already {indent.status}")
    from datetime import datetime
    indent.status = IndentStatus.APPROVED
    indent.approved_by = current_user.email
    indent.approved_at = datetime.utcnow()
    db.add(AuditLog(entity_type="indent", entity_id=indent.id, action="approved",
                     details={}, actor=current_user.email))
    db.commit()
    db.refresh(indent)
    return indent


@router.post("/api/indents/{indent_id}/reject", response_model=IndentOut)
def reject_indent(indent_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(editor)):
    indent = db.query(Indent).get(indent_id)
    if not indent:
        raise HTTPException(404, "Indent not found")
    if indent.status != IndentStatus.DRAFT:
        raise HTTPException(409, f"Indent is already {indent.status}")
    indent.status = IndentStatus.REJECTED
    db.add(AuditLog(entity_type="indent", entity_id=indent.id, action="rejected",
                     details={}, actor=current_user.email))
    db.commit()
    db.refresh(indent)
    return indent


# --- Indent rules (admin-configured consumable/packaging requirements) ---

rules_admin = require_role("admin")


@router.get("/api/indent-rules", response_model=list[IndentRuleOut])
def list_indent_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(IndentRule).order_by(IndentRule.name).all()


@router.post("/api/indent-rules", response_model=IndentRuleOut)
def create_indent_rule(payload: IndentRuleIn, db: Session = Depends(get_db),
                        current_user: User = Depends(rules_admin)):
    rule = IndentRule(**payload.model_dump(), created_by=current_user.email)
    db.add(rule)
    db.flush()
    db.add(AuditLog(entity_type="indent_rule", entity_id=rule.id, action="created",
                     details=payload.model_dump(), actor=current_user.email))
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/api/indent-rules/{rule_id}", response_model=IndentRuleOut)
def update_indent_rule(rule_id: str, payload: IndentRuleIn, db: Session = Depends(get_db),
                        current_user: User = Depends(rules_admin)):
    rule = db.query(IndentRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Indent rule not found")
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    db.add(AuditLog(entity_type="indent_rule", entity_id=rule.id, action="updated",
                     details=payload.model_dump(), actor=current_user.email))
    db.commit()
    db.refresh(rule)
    return rule
