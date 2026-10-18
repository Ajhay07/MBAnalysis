from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models.models import Supplier, CatalogComponent, BomLineItem, Bom, User
from app.schemas.api import SupplierIn, SupplierOut, CatalogComponentIn, CatalogComponentOut
from app.services.purchase_requirements import build_purchase_requirements

router = APIRouter(prefix="/api/procurement", tags=["procurement"])

editor = require_role("admin", "engineer")


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Supplier).all()


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db),
                     current_user: User = Depends(editor)):
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: str, payload: SupplierIn, db: Session = Depends(get_db),
                     current_user: User = Depends(editor)):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    for k, v in payload.model_dump().items():
        setattr(supplier, k, v)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(editor)):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    db.delete(supplier)
    db.commit()
    return {"ok": True}


@router.get("/catalog", response_model=list[CatalogComponentOut])
def list_catalog(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(CatalogComponent).all()


@router.post("/catalog", response_model=CatalogComponentOut)
def create_catalog_item(payload: CatalogComponentIn, db: Session = Depends(get_db),
                         current_user: User = Depends(editor)):
    item = CatalogComponent(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/catalog/{item_id}")
def delete_catalog_item(item_id: str, db: Session = Depends(get_db),
                         current_user: User = Depends(editor)):
    item = db.query(CatalogComponent).get(item_id)
    if not item:
        raise HTTPException(404, "Catalog item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/catalog/import-csv")
async def import_catalog_csv(file: UploadFile = File(...), db: Session = Depends(get_db),
                              current_user: User = Depends(editor)):
    contents = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(contents))
    created = 0
    for row in reader:
        price = row.get("unit_price") or None
        stock = row.get("stock_quantity") or None
        db.add(CatalogComponent(
            part_number=row.get("part_number", ""),
            description=row.get("description", ""),
            category=row.get("category", ""),
            unit_price=float(price) if price else None,
            currency=row.get("currency") or None,
            stock_quantity=float(stock) if stock else None,
        ))
        created += 1
    db.commit()
    return {"created": created}


@router.get("/catalog/export-csv")
def export_catalog_csv(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(CatalogComponent).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["part_number", "description", "category", "unit_price", "currency", "stock_quantity"])
    for item in items:
        writer.writerow([item.part_number, item.description, item.category, item.unit_price or "",
                          item.currency or "", item.stock_quantity if item.stock_quantity is not None else ""])
    return Response(content=buf.getvalue(), media_type="text/csv",
                     headers={"Content-Disposition": 'attachment; filename="catalog_export.csv"'})


@router.get("/catalog/usage")
def catalog_usage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """For every catalog component: its id/part number plus how many BOM line items and
    components across all drawings have been cross-referenced to it (app.services.
    catalog_matching) and the total quantity required. This is the reference list a reviewer
    uses to tell, at a glance, which known parts the OCR/vision pipeline has already
    recognized in uploaded drawings - and how many of each are needed - versus parts still
    sitting in Review with no catalog match."""
    items = db.query(CatalogComponent).all()
    result = []
    for item in items:
        lines = db.query(BomLineItem).filter(BomLineItem.catalog_component_id == item.id).all()
        result.append({
            "catalog_component_id": item.id,
            "part_number": item.part_number,
            "description": item.description,
            "category": item.category,
            "unit_price": item.unit_price,
            "currency": item.currency,
            "stock_quantity": item.stock_quantity,
            "matched_line_item_count": len(lines),
            "total_quantity": sum(li.quantity or 0 for li in lines),
        })
    return result


@router.get("/purchase-requirements/{drawing_id}")
def purchase_requirements_for_drawing(drawing_id: str, db: Session = Depends(get_db),
                                       current_user: User = Depends(get_current_user)):
    """Purchase-requirements report for a drawing's latest BOM: Buy items (with quantity,
    material/grade, matched catalog price/stock, estimated cost), Make items (quantity,
    material/grade/spec), and anything still in Review - see
    app.services.purchase_requirements for how each field is derived."""
    bom = db.query(Bom).filter(Bom.drawing_id == drawing_id).order_by(Bom.version.desc()).first()
    if not bom:
        return {"bom_id": None, "buy": [], "make": [], "review": [],
                "summary": {"buy_item_count": 0, "make_item_count": 0, "review_item_count": 0,
                            "estimated_total_cost": None, "buy_items_missing_price": 0,
                            "is_partial_estimate": False}}
    return build_purchase_requirements(db, bom)


@router.get("/by-drawing/{drawing_id}")
def procurement_view_for_drawing(drawing_id: str, db: Session = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Buy/Make/Review grouping derived from the latest BOM for a drawing."""
    bom = db.query(Bom).filter(Bom.drawing_id == drawing_id).order_by(Bom.version.desc()).first()
    if not bom:
        return {"buy": [], "make": [], "review": []}
    catalog_by_id = {c.id: c for c in db.query(CatalogComponent).all()}
    groups = {"buy": [], "make": [], "review": []}
    for li in bom.line_items:
        key = (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy).lower()
        catalog_item = catalog_by_id.get(li.catalog_component_id) if li.catalog_component_id else None
        groups.setdefault(key, []).append({
            "id": li.id, "part_number": li.part_number, "description": li.description,
            "quantity": li.quantity, "material": li.material, "unit_cost": li.unit_cost,
            "catalog_component_id": li.catalog_component_id,
            "catalog_part_number": catalog_item.part_number if catalog_item else None,
        })
    return groups
