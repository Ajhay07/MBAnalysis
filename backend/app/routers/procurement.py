from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Supplier, CatalogComponent, BomLineItem, Bom
from app.schemas.api import SupplierIn, SupplierOut, CatalogComponentIn, CatalogComponentOut

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    return db.query(Supplier).all()


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db)):
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: str, payload: SupplierIn, db: Session = Depends(get_db)):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    for k, v in payload.model_dump().items():
        setattr(supplier, k, v)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str, db: Session = Depends(get_db)):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    db.delete(supplier)
    db.commit()
    return {"ok": True}


@router.get("/catalog", response_model=list[CatalogComponentOut])
def list_catalog(db: Session = Depends(get_db)):
    return db.query(CatalogComponent).all()


@router.post("/catalog", response_model=CatalogComponentOut)
def create_catalog_item(payload: CatalogComponentIn, db: Session = Depends(get_db)):
    item = CatalogComponent(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/catalog/{item_id}")
def delete_catalog_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(CatalogComponent).get(item_id)
    if not item:
        raise HTTPException(404, "Catalog item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/catalog/import-csv")
async def import_catalog_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(contents))
    created = 0
    for row in reader:
        price = row.get("unit_price") or None
        db.add(CatalogComponent(
            part_number=row.get("part_number", ""),
            description=row.get("description", ""),
            category=row.get("category", ""),
            unit_price=float(price) if price else None,
            currency=row.get("currency") or None,
        ))
        created += 1
    db.commit()
    return {"created": created}


@router.get("/catalog/export-csv")
def export_catalog_csv(db: Session = Depends(get_db)):
    items = db.query(CatalogComponent).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["part_number", "description", "category", "unit_price", "currency"])
    for item in items:
        writer.writerow([item.part_number, item.description, item.category, item.unit_price or "",
                          item.currency or ""])
    return Response(content=buf.getvalue(), media_type="text/csv",
                     headers={"Content-Disposition": 'attachment; filename="catalog_export.csv"'})


@router.get("/by-drawing/{drawing_id}")
def procurement_view_for_drawing(drawing_id: str, db: Session = Depends(get_db)):
    """Buy/Make/Review grouping derived from the latest BOM for a drawing."""
    bom = db.query(Bom).filter(Bom.drawing_id == drawing_id).order_by(Bom.version.desc()).first()
    if not bom:
        return {"buy": [], "make": [], "review": []}
    groups = {"buy": [], "make": [], "review": []}
    for li in bom.line_items:
        key = (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy).lower()
        groups.setdefault(key, []).append({
            "id": li.id, "part_number": li.part_number, "description": li.description,
            "quantity": li.quantity, "material": li.material, "unit_cost": li.unit_cost,
        })
    return groups
