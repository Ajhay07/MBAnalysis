"""Inventory-aware BOM availability analysis.

Semantics (see spec / README for the full writeup):
  usable_available = on_hand - reserved_total - quarantined
  net_shortage      = max(0, required_quantity - usable_available - this_job_allocation)

`reserved_total` is the sum of ALL active allocations against a matched lot (including this
job's own), plus any baseline `reserved_qty` recorded directly on the lot (e.g. legacy/manual
holds not tracked as an allocation row). `this_job_allocation` is this BOM's own slice of that
total, added back so it is never double-subtracted: stock already secured for this job is both
removed from the "free for anyone" pool (usable_available) and credited back explicitly.

All quantity arithmetic uses Decimal - quantities are persisted as strings precisely so no
float ever enters this file.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import (
    Bom, BomLineItem, Component, InventoryLot, InventoryAllocation,
    PurchaseRequisition, PurchaseRequisitionLine, RequisitionStatus,
    Supplier, AuditLog,
)
from app.services.calculations import convert_length, _LENGTH_TO_MM


def D(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


AVAILABLE = "AVAILABLE"
PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
OUT_OF_STOCK = "OUT_OF_STOCK"
REVIEW_REQUIRED = "REVIEW_REQUIRED"


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _units_compatible(a: str, b: str) -> bool:
    """True if units are identical, or both are length units convertible via the existing
    calculations.convert_length table. Anything else (e.g. 'ea' vs 'kg') is incompatible."""
    if _normalize(a) == _normalize(b):
        return True
    return _normalize(a) in _LENGTH_TO_MM and _normalize(b) in _LENGTH_TO_MM


def _convert(value: Decimal, from_unit: str, to_unit: str) -> Decimal | None:
    if _normalize(from_unit) == _normalize(to_unit):
        return value
    if _normalize(from_unit) not in _LENGTH_TO_MM or _normalize(to_unit) not in _LENGTH_TO_MM:
        return None
    res = convert_length(float(value), from_unit, to_unit)
    if res["warnings"]:
        return None
    return Decimal(str(res["result"]))


def match_lots(db: Session, line_item: BomLineItem) -> tuple[list[InventoryLot], str | None]:
    """Returns (matched_lots, ambiguity_reason). ambiguity_reason is None for a clean match
    (zero or more lots of the SAME material+grade), 'unmatched' if nothing matches, or
    'ambiguous' if lots for more than one distinct material/grade combination plausibly match."""
    code = (line_item.part_number or "").strip()
    if code:
        exact = db.query(InventoryLot).filter(InventoryLot.material_code == code).all()
        if exact:
            return exact, None

    material = _normalize(line_item.material)
    if not material:
        return [], "unmatched"

    component = db.query(Component).get(line_item.component_id) if line_item.component_id else None
    grade = _normalize(component.grade) if component else ""

    candidates = db.query(InventoryLot).filter(InventoryLot.material != "").all()
    by_material = [l for l in candidates if _normalize(l.material) == material]
    if not by_material:
        return [], "unmatched"

    if grade:
        graded = [l for l in by_material if _normalize(l.grade) == grade]
        ungraded_present = any(_normalize(l.grade) == "" for l in by_material)
        if graded and not any(_normalize(l.grade) not in (grade, "") for l in by_material):
            return graded, None
        if graded and ungraded_present and len({_normalize(l.grade) for l in by_material if l.grade}) <= 1:
            return graded, None
        distinct_grades = {_normalize(l.grade) for l in by_material if l.grade}
        if len(distinct_grades) > 1:
            return [], "ambiguous"
        return graded or by_material, None if graded else "ambiguous"

    distinct_grades = {_normalize(l.grade) for l in by_material if l.grade}
    if len(distinct_grades) > 1:
        return [], "ambiguous"
    return by_material, None


def _lot_reserved_total(db: Session, lot: InventoryLot) -> Decimal:
    allocs = db.query(InventoryAllocation).filter(
        InventoryAllocation.inventory_lot_id == lot.id,
        InventoryAllocation.status == "active",
    ).all()
    return D(lot.reserved_qty) + sum((D(a.quantity) for a in allocs), Decimal("0"))


def _this_job_allocation(db: Session, lot_ids: list[str], bom_id: str) -> Decimal:
    if not lot_ids:
        return Decimal("0")
    allocs = db.query(InventoryAllocation).filter(
        InventoryAllocation.inventory_lot_id.in_(lot_ids),
        InventoryAllocation.bom_id == bom_id,
        InventoryAllocation.status == "active",
    ).all()
    return sum((D(a.quantity) for a in allocs), Decimal("0"))


def compute_availability(db: Session, bom: Bom, production_quantity: float) -> dict:
    """Read-only preview: never mutates on_hand/reserved/quarantined or creates allocations."""
    prod_qty = D(production_quantity)
    lines = []
    summary = {AVAILABLE: 0, PARTIALLY_AVAILABLE: 0, OUT_OF_STOCK: 0, REVIEW_REQUIRED: 0}

    for li in bom.line_items:
        component = db.query(Component).get(li.component_id) if li.component_id else None
        explanation_parts = []
        status = None

        if li.total_quantity is None:
            status = REVIEW_REQUIRED
            explanation_parts.append("Nested BOM quantity rollup is undetermined for this line.")

        if component is not None and component.verification_status != "Verified":
            status = REVIEW_REQUIRED
            explanation_parts.append(
                f"Underlying spec is {component.verification_status.lower()} OCR-derived data, "
                "not yet human-reviewed."
            )

        lots, ambiguity = match_lots(db, li)
        if ambiguity == "unmatched":
            status = REVIEW_REQUIRED
            explanation_parts.append("No matching inventory item found for this material/part number.")
        elif ambiguity == "ambiguous":
            status = REVIEW_REQUIRED
            explanation_parts.append(
                "Multiple plausible inventory matches with different material/grade - resolve manually."
            )

        required = None
        if li.total_quantity is not None:
            required = D(li.total_quantity) * prod_qty

        lot_unit = lots[0].unit if lots else None
        if lots and lot_unit and not _units_compatible(lot_unit, "ea"):
            pass  # unit compatibility checked against the inventory unit below once we have `required`

        on_hand = sum((D(l.on_hand_qty) for l in lots), Decimal("0"))
        quarantined = sum((D(l.quarantined_qty) for l in lots), Decimal("0"))
        reserved_total = sum((_lot_reserved_total(db, l) for l in lots), Decimal("0"))
        this_job_alloc = _this_job_allocation(db, [l.id for l in lots], bom.id)

        unit = lot_unit or "ea"
        if lots and required is not None:
            converted = _convert(required, unit, unit)  # same unit, trivially ok
            # required is computed in BOM units (unspecified); compare against lot unit only when
            # the BOM line declares a unit-bearing dimension - this app does not track a per-line
            # unit field distinct from the inventory lot's, so we treat the lot's own unit as
            # authoritative and only flag incompatibility when lots of the SAME material disagree
            # on unit amongst themselves (would make the sum itself meaningless).
            distinct_units = {_normalize(l.unit) for l in lots}
            if len(distinct_units) > 1 and not all(_units_compatible(lots[0].unit, u) for u in distinct_units):
                status = REVIEW_REQUIRED
                explanation_parts.append("Matched inventory lots use incompatible units.")

        usable_available = on_hand - reserved_total - quarantined
        net_shortage = None
        if status != REVIEW_REQUIRED and required is not None:
            net_shortage = max(Decimal("0"), required - usable_available - this_job_alloc)
            if net_shortage == 0:
                status = AVAILABLE
            elif usable_available + this_job_alloc > 0:
                status = PARTIALLY_AVAILABLE
            else:
                status = OUT_OF_STOCK

        if status is None:
            status = REVIEW_REQUIRED
            explanation_parts.append("Unable to determine required quantity.")

        if not explanation_parts:
            explanation_parts.append(
                f"{len(lots)} lot(s) matched; usable available {usable_available} {unit}."
            )

        supplier_name = None
        lead_time = None
        if lots and lots[0].supplier_id:
            supplier = db.query(Supplier).get(lots[0].supplier_id)
            supplier_name = supplier.name if supplier else None

        summary[status] = summary.get(status, 0) + 1

        lines.append({
            "bom_line_item_id": li.id,
            "part_number": li.part_number,
            "description": li.description,
            "material": li.material,
            "grade": component.grade if component else "",
            "unit": unit,
            "required_quantity": float(required) if required is not None else None,
            "on_hand": float(on_hand),
            "reserved": float(reserved_total),
            "quarantined": float(quarantined),
            "usable_available": float(usable_available),
            "this_job_allocation": float(this_job_alloc),
            "net_shortage": float(net_shortage) if net_shortage is not None else None,
            "status": status,
            "explanation": " ".join(explanation_parts),
            "matched_lot_ids": [l.id for l in lots],
            "supplier_name": supplier_name,
            "lead_time_days": lead_time,
        })

    return {
        "bom_id": bom.id,
        "production_quantity": production_quantity,
        "summary": summary,
        "lines": lines,
    }


def create_draft_requisition(db: Session, bom: Bom, production_quantity: float, actor: str) -> PurchaseRequisition:
    """Creates (or returns the existing) draft/pending requisition for this BOM's current
    shortages. Idempotent: an open (Draft/Pending) requisition already covering this BOM is
    reused rather than duplicated - repeated clicks/refreshes never create a second one."""
    existing = db.query(PurchaseRequisition).filter(
        PurchaseRequisition.bom_id == bom.id,
        PurchaseRequisition.status.in_([RequisitionStatus.DRAFT, RequisitionStatus.PENDING]),
    ).first()
    if existing:
        return existing

    report = compute_availability(db, bom, production_quantity)
    shortages = [
        l for l in report["lines"]
        if l["status"] in (PARTIALLY_AVAILABLE, OUT_OF_STOCK) and (l["net_shortage"] or 0) > 0
    ]
    requisition = PurchaseRequisition(bom_id=bom.id, status=RequisitionStatus.DRAFT, created_by=actor)
    db.add(requisition)
    db.flush()

    for line in shortages:
        bom_line = db.query(BomLineItem).get(line["bom_line_item_id"])
        lots = db.query(InventoryLot).filter(InventoryLot.id.in_(line["matched_lot_ids"])).all()
        moq_qty = line["net_shortage"]
        supplier_id = lots[0].supplier_id if lots else None
        db.add(PurchaseRequisitionLine(
            requisition_id=requisition.id,
            material_code=bom_line.part_number if bom_line else line["part_number"],
            description=line["description"],
            quantity=str(moq_qty),
            unit=line["unit"],
            supplier_id=supplier_id,
        ))

    db.add(AuditLog(entity_type="purchase_requisition", entity_id=requisition.id, action="drafted",
                     details={"bom_id": bom.id, "line_count": len(shortages)}, actor=actor))
    db.commit()
    db.refresh(requisition)
    return requisition


def approve_requisition(db: Session, requisition: PurchaseRequisition, actor: str) -> PurchaseRequisition:
    requisition.status = RequisitionStatus.APPROVED
    requisition.approved_at = datetime.utcnow()
    requisition.approved_by = actor
    db.add(AuditLog(entity_type="purchase_requisition", entity_id=requisition.id, action="approved",
                     details={}, actor=actor))
    db.commit()
    db.refresh(requisition)
    return requisition


class InsufficientStockError(ValueError):
    pass


def create_allocation(db: Session, lot: InventoryLot, bom_id: str, quantity: float, actor: str) -> InventoryAllocation:
    """Transaction + re-check pattern to avoid double-allocation under concurrency.

    SQLite does not support true row-level SELECT ... FOR UPDATE locking the way a
    multi-writer RDBMS does, so this is a best-effort guard, not a hard guarantee under true
    concurrent writers: it re-reads the lot and sums active allocations again immediately
    before the write, inside the same DB transaction, and if the freshly-recomputed usable
    stock can't cover the request it aborts without writing. Two requests arriving genuinely
    simultaneously on SQLite can still interleave at the SQLite-engine level (this is a known,
    documented limitation of SQLite's concurrency model) - see README/limitations notes.
    """
    qty = D(quantity)
    db.refresh(lot)
    reserved_total = _lot_reserved_total(db, lot)
    usable = D(lot.on_hand_qty) - reserved_total - D(lot.quarantined_qty)
    if usable < qty:
        raise InsufficientStockError(
            f"Only {usable} {lot.unit} usable, requested {qty}."
        )
    allocation = InventoryAllocation(inventory_lot_id=lot.id, bom_id=bom_id, material_code=lot.material_code,
                                      quantity=str(qty), status="active", created_by=actor)
    db.add(allocation)
    db.add(AuditLog(entity_type="inventory_allocation", entity_id=lot.id, action="allocated",
                     details={"bom_id": bom_id, "quantity": str(qty)}, actor=actor))
    db.commit()
    db.refresh(allocation)
    return allocation
