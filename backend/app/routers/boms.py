from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Bom, BomLineItem, Drawing, AuditLog
from app.schemas.api import BomOut, BomLineItemUpdate
from app.services.export_service import (
    bom_to_dataframe, purchase_list_dataframe, material_summary_dataframe,
    dataframe_to_csv_bytes, dataframe_to_excel_bytes,
    bom_export_filename, purchase_list_filename, material_summary_filename,
)

router = APIRouter(prefix="/api/boms", tags=["boms"])


@router.get("/{bom_id}", response_model=BomOut)
def get_bom(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    return bom


@router.get("/by-drawing/{drawing_id}", response_model=list[BomOut])
def list_boms_for_drawing(drawing_id: str, db: Session = Depends(get_db)):
    return db.query(Bom).filter(Bom.drawing_id == drawing_id).order_by(Bom.version.desc()).all()


@router.patch("/line-items/{line_item_id}")
def update_line_item(line_item_id: str, payload: BomLineItemUpdate, db: Session = Depends(get_db)):
    line = db.query(BomLineItem).get(line_item_id)
    if not line:
        raise HTTPException(404, "Line item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    db.add(AuditLog(entity_type="bom_line_item", entity_id=line_item_id, action="updated",
                     details=payload.model_dump(exclude_unset=True)))
    db.commit()
    db.refresh(line)
    return {"ok": True}


@router.post("/{bom_id}/approve")
def approve_bom(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    bom.status = "Approved"
    db.add(AuditLog(entity_type="bom", entity_id=bom_id, action="approved", details={}))
    db.commit()
    return {"ok": True}


@router.post("/{bom_id}/reject")
def reject_bom(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    bom.status = "Rejected"
    db.add(AuditLog(entity_type="bom", entity_id=bom_id, action="rejected", details={}))
    db.commit()
    return {"ok": True}


def _respond_file(content: bytes, filename: str, media_type: str) -> Response:
    return Response(content=content, media_type=media_type,
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{bom_id}/export/bom.csv")
def export_bom_csv(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = bom_to_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), bom_export_filename(drawing, "csv"), "text/csv")


@router.get("/{bom_id}/export/bom.xlsx")
def export_bom_xlsx(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = bom_to_dataframe(bom)
    return _respond_file(dataframe_to_excel_bytes(df), bom_export_filename(drawing, "xlsx"),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{bom_id}/export/purchase-list.csv")
def export_purchase_list_csv(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = purchase_list_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), purchase_list_filename(drawing, "csv"), "text/csv")


@router.get("/{bom_id}/export/material-summary.csv")
def export_material_summary_csv(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    drawing = db.query(Drawing).get(bom.drawing_id)
    df = material_summary_dataframe(bom)
    return _respond_file(dataframe_to_csv_bytes(df), material_summary_filename(drawing, "csv"), "text/csv")
