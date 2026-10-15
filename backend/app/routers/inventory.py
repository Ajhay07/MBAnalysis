from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models.models import Bom, InventoryLot, PurchaseRequisition, RequisitionStatus, User
from app.schemas.api import (
    InventoryLotIn, InventoryLotOut, AvailabilityReportOut, RequisitionOut, AllocationIn, AllocationOut,
)
from app.services.inventory_service import (
    compute_availability, create_draft_requisition, approve_requisition, create_allocation,
    InsufficientStockError,
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

editor = require_role("admin", "engineer")


def _lot_out(lot: InventoryLot) -> dict:
    return {
        "id": lot.id,
        "material_code": lot.material_code,
        "material": lot.material,
        "grade": lot.grade,
        "description": lot.description,
        "unit": lot.unit,
        "on_hand_qty": float(lot.on_hand_qty or 0),
        "reserved_qty": float(lot.reserved_qty or 0),
        "quarantined_qty": float(lot.quarantined_qty or 0),
        "location": lot.location,
        "lot_number": lot.lot_number,
        "supplier_id": lot.supplier_id,
        "is_demo": lot.is_demo,
    }


@router.get("/lots", response_model=list[InventoryLotOut])
def list_lots(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_lot_out(l) for l in db.query(InventoryLot).all()]


@router.post("/lots", response_model=InventoryLotOut)
def create_lot(payload: InventoryLotIn, db: Session = Depends(get_db), current_user: User = Depends(editor)):
    lot = InventoryLot(
        material_code=payload.material_code, material=payload.material, grade=payload.grade,
        description=payload.description, unit=payload.unit, on_hand_qty=str(payload.on_hand_qty),
        reserved_qty=str(payload.reserved_qty), quarantined_qty=str(payload.quarantined_qty),
        location=payload.location, lot_number=payload.lot_number, supplier_id=payload.supplier_id,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return _lot_out(lot)


@router.get("/availability/{bom_id}", response_model=AvailabilityReportOut)
def get_availability(bom_id: str, production_quantity: float = 1.0,
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Read-only availability preview. Never mutates inventory state."""
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    if production_quantity <= 0:
        raise HTTPException(400, "production_quantity must be positive")
    return compute_availability(db, bom, production_quantity)


@router.post("/requisitions/draft", response_model=RequisitionOut)
def draft_requisition(bom_id: str, production_quantity: float = 1.0,
                       db: Session = Depends(get_db), current_user: User = Depends(editor)):
    bom = db.query(Bom).get(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    requisition = create_draft_requisition(db, bom, production_quantity, actor=current_user.email)
    return requisition


@router.get("/requisitions/by-bom/{bom_id}", response_model=list[RequisitionOut])
def list_requisitions_for_bom(bom_id: str, db: Session = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    return db.query(PurchaseRequisition).filter(PurchaseRequisition.bom_id == bom_id).all()


@router.post("/requisitions/{requisition_id}/approve", response_model=RequisitionOut)
def approve_requisition_endpoint(requisition_id: str, db: Session = Depends(get_db),
                                  current_user: User = Depends(editor)):
    requisition = db.query(PurchaseRequisition).get(requisition_id)
    if not requisition:
        raise HTTPException(404, "Requisition not found")
    if requisition.status == RequisitionStatus.APPROVED:
        return requisition
    return approve_requisition(db, requisition, actor=current_user.email)


@router.post("/requisitions/{requisition_id}/reject", response_model=RequisitionOut)
def reject_requisition_endpoint(requisition_id: str, db: Session = Depends(get_db),
                                 current_user: User = Depends(editor)):
    requisition = db.query(PurchaseRequisition).get(requisition_id)
    if not requisition:
        raise HTTPException(404, "Requisition not found")
    requisition.status = RequisitionStatus.REJECTED
    db.commit()
    db.refresh(requisition)
    return requisition


@router.post("/allocations", response_model=AllocationOut)
def create_allocation_endpoint(payload: AllocationIn, db: Session = Depends(get_db),
                                current_user: User = Depends(editor)):
    lot = db.query(InventoryLot).get(payload.inventory_lot_id)
    if not lot:
        raise HTTPException(404, "Inventory lot not found")
    bom = db.query(Bom).get(payload.bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    try:
        allocation = create_allocation(db, lot, payload.bom_id, payload.quantity, actor=current_user.email)
    except InsufficientStockError as e:
        raise HTTPException(409, str(e))
    return {
        "id": allocation.id, "inventory_lot_id": allocation.inventory_lot_id, "bom_id": allocation.bom_id,
        "quantity": float(allocation.quantity), "status": allocation.status,
    }
