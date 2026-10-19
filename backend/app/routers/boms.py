from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models.models import Bom, BomLineItem, Drawing, AuditLog, User
from app.schemas.api import BomOut, BomLineItemUpdate
from app.services.bom_service import would_create_cycle, recompute_rollup, build_bom_tree
from app.services.bom_pdf import bom_to_pdf_bytes
from app.services.export_service import (
    bom_to_dataframe, purchase_list_dataframe, material_summary_dataframe,
    dataframe_to_csv_bytes, dataframe_to_excel_bytes,
    bom_export_filename, purchase_list_filename, material_summary_filename,
)

router = APIRouter(prefix="/api/boms", tags=["boms"])

editor = require_role("admin", "engineer")


@router.get("/{bom_id}", response_model=BomOut)
def get_bom(bom_id: str, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    return bom


@router.get("/by-drawing/{drawing_id}", response_model=list[BomOut])
def list_boms_for_drawing(drawing_id: str, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    return db.query(Bom).filter(Bom.drawing_id == drawing_id).order_by(Bom.version.desc()).all()


@router.patch("/line-items/{line_item_id}")
def update_line_item(line_item_id: str, payload: BomLineItemUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(editor)):
    line = db.query(BomLineItem).get(line_item_id)
    if not line:
        raise HTTPException(404, "Line item not found")
    updates = payload.model_dump(exclude_unset=True)
    if "parent_line_item_id" in updates:
        new_parent_id = updates["parent_line_item_id"]
        if new_parent_id is not None:
            parent = db.query(BomLineItem).filter(
                BomLineItem.id == new_parent_id, BomLineItem.bom_id == line.bom_id
            ).first()
            if parent is None:
                raise HTTPException(400, "Parent line item not found in this BOM")
        if would_create_cycle(db, line.bom_id, line.id, new_parent_id):
            raise HTTPException(400, "This parent assignment would create a circular BOM reference")
    for field, value in updates.items():
        setattr(line, field, value)
    db.add(AuditLog(entity_type="bom_line_item", entity_id=line_item_id, action="updated",
                     details=updates, actor=current_user.email))
    db.flush()
    recompute_rollup(db, line.bom_id)
    db.commit()
    db.refresh(line)
    return {"ok": True}


@router.get("/{bom_id}/tree")
def get_bom_tree(bom_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    return {"bom_id": bom.id, "nodes": build_bom_tree(db, bom)}


@router.post("/{bom_id}/approve")
def approve_bom(bom_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(editor)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    bom.status = "Approved"
    db.add(AuditLog(entity_type="bom", entity_id=bom_id, action="approved", details={},
                     actor=current_user.email))
    db.commit()
    return {"ok": True}


@router.post("/{bom_id}/reject")
def reject_bom(bom_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(editor)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    bom.status = "Rejected"
    db.add(AuditLog(entity_type="bom", entity_id=bom_id, action="rejected", details={},
                     actor=current_user.email))
    db.commit()
    return {"ok": True}


def _respond_file(content: bytes, filename: str, media_type: str) -> Response:
    return Response(content=content, media_type=media_type,
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{bom_id}/export/bom.csv")
def export_bom_csv(bom_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = bom_to_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), bom_export_filename(drawing, "csv"), "text/csv")


@router.get("/{bom_id}/export/bom.xlsx")
def export_bom_xlsx(bom_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = bom_to_dataframe(bom)
    return _respond_file(dataframe_to_excel_bytes(df), bom_export_filename(drawing, "xlsx"),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{bom_id}/export/bom.pdf")
def export_bom_pdf(bom_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    return _respond_file(bom_to_pdf_bytes(bom, drawing), bom_export_filename(drawing, "pdf"),
                          "application/pdf")


@router.get("/{bom_id}/export/purchase-list.csv")
def export_purchase_list_csv(bom_id: str, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = purchase_list_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), purchase_list_filename(drawing, "csv"), "text/csv")


@router.get("/{bom_id}/export/material-summary.csv")
def export_material_summary_csv(bom_id: str, db: Session = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = material_summary_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), material_summary_filename(drawing, "csv"), "text/csv")
