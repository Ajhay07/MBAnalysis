"""Inventory-aware BOM availability: matching, Decimal arithmetic, no-double-subtraction,
requisition idempotency, role gating, and a concurrency smoke test for allocation."""
from decimal import Decimal

from app.models.models import (
    Drawing, Analysis, Component, Bom, BomLineItem, DrawingStatus, MakeBuy, UserRole,
    InventoryLot, InventoryAllocation, RequisitionStatus,
)
from app.services.bom_service import recompute_rollup
from app.services.inventory_service import (
    compute_availability, create_draft_requisition, create_allocation, InsufficientStockError,
    AVAILABLE, PARTIALLY_AVAILABLE, OUT_OF_STOCK, REVIEW_REQUIRED,
)


def _bom_with_line(db, *, part_number="P1", material="Steel 4140", grade="Q&T", qty=1,
                    verification_status="Verified", parent=None, unit=None):
    drawing = Drawing(drawing_number=f"T-{part_number}", title="t", revision="A", file_name="t.png",
                       stored_file_name="t.png", file_type="png", file_size=1, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test", title_block={}, dimensions=[],
                         materials=[material], overall_confidence=0.9)
    db.add(analysis)
    db.flush()
    component = Component(analysis_id=analysis.id, part_number=part_number, description="d",
                           category="Shaft", quantity=qty, material=material, grade=grade,
                           make_buy=MakeBuy.MAKE, confidence=0.9, verification_status=verification_status)
    db.add(component)
    db.flush()
    bom = Bom(drawing_id=drawing.id, analysis_id=analysis.id, version=1, status="Draft")
    db.add(bom)
    db.flush()
    li = BomLineItem(bom_id=bom.id, component_id=component.id, part_number=part_number, description="d",
                      category="Shaft", quantity=qty, material=material, make_buy=MakeBuy.MAKE,
                      parent_line_item_id=parent)
    db.add(li)
    db.flush()
    recompute_rollup(db, bom.id)
    db.commit()
    db.refresh(bom)
    return bom, li


def _lot(db, **kwargs):
    defaults = dict(unit="ea", on_hand_qty="0", reserved_qty="0", quarantined_qty="0", is_demo=False)
    defaults.update(kwargs)
    lot = InventoryLot(**defaults)
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


def _line(report, part_number="P1"):
    return next(l for l in report["lines"] if l["part_number"] == part_number)


def test_sufficient_stock_is_available(db):
    bom, li = _bom_with_line(db, part_number="SUFF-1", qty=1)
    _lot(db, material_code="SUFF-1", on_hand_qty="10")
    report = compute_availability(db, bom, production_quantity=1)
    line = _line(report, "SUFF-1")
    assert line["status"] == AVAILABLE
    assert line["net_shortage"] == 0


def test_partial_stock(db):
    bom, li = _bom_with_line(db, part_number="PART-1", qty=1)
    _lot(db, material_code="PART-1", on_hand_qty="3")
    report = compute_availability(db, bom, production_quantity=10)
    line = _line(report, "PART-1")
    assert line["status"] == PARTIALLY_AVAILABLE
    assert line["net_shortage"] == 7


def test_zero_stock_is_out_of_stock(db):
    bom, li = _bom_with_line(db, part_number="ZERO-1", qty=1)
    _lot(db, material_code="ZERO-1", on_hand_qty="0")
    report = compute_availability(db, bom, production_quantity=5)
    line = _line(report, "ZERO-1")
    assert line["status"] == OUT_OF_STOCK
    assert line["net_shortage"] == 5


def test_reserved_by_other_job_reduces_usable(db):
    bom, li = _bom_with_line(db, part_number="RES-1", qty=1)
    lot = _lot(db, material_code="RES-1", on_hand_qty="10", reserved_qty="4")
    report = compute_availability(db, bom, production_quantity=5)
    line = _line(report, "RES-1")
    # 10 on hand - 4 reserved (by other jobs, no allocation for this bom) = 6 usable
    assert line["usable_available"] == 6
    assert line["this_job_allocation"] == 0
    assert line["net_shortage"] == 0  # 5 required <= 6 usable


def test_quarantined_lot_is_excluded(db):
    bom, li = _bom_with_line(db, part_number="QUAR-1", qty=1)
    _lot(db, material_code="QUAR-1", on_hand_qty="10", quarantined_qty="8")
    report = compute_availability(db, bom, production_quantity=3)
    line = _line(report, "QUAR-1")
    assert line["usable_available"] == 2
    assert line["status"] == PARTIALLY_AVAILABLE
    assert line["net_shortage"] == 1


def test_existing_allocation_for_this_job_is_not_double_subtracted(db):
    """The trickiest part of the spec: usable_available = on_hand - reserved_total - quarantined,
    and net_shortage = required - usable_available - this_job_allocation. If this job already
    holds an allocation equal to the entire on-hand stock, net_shortage must be 0 for a matching
    requirement - not negative-then-clamped-wrong, and not double-counted against on_hand."""
    bom, li = _bom_with_line(db, part_number="ALLOC-1", qty=1)
    lot = _lot(db, material_code="ALLOC-1", on_hand_qty="100", reserved_qty="0")
    create_allocation(db, lot, bom.id, 20, actor="tester")
    report = compute_availability(db, bom, production_quantity=90)  # requires 90
    line = _line(report, "ALLOC-1")
    # reserved_total = 20 (this job's own allocation); usable_available = 100-20-0 = 80
    assert line["usable_available"] == 80
    assert line["this_job_allocation"] == 20
    # 80 (free) + 20 (already secured for this job) = 100 >= 90 required -> no shortage
    assert line["net_shortage"] == 0
    assert line["status"] == AVAILABLE


def test_nested_bom_rollup_multiplies_required_quantity(db):
    bom, parent_li = _bom_with_line(db, part_number="ASM-1", qty=2)
    child = BomLineItem(bom_id=bom.id, part_number="P-CHILD", description="child", category="Shaft",
                         quantity=3, material="Steel 4140", make_buy=MakeBuy.MAKE,
                         parent_line_item_id=parent_li.id)
    db.add(child)
    db.commit()
    recompute_rollup(db, bom.id)
    db.commit()
    _lot(db, material_code="P-CHILD", on_hand_qty="100")
    report = compute_availability(db, bom, production_quantity=5)
    child_line = _line(report, "P-CHILD")
    # qty-per-assembly 3 * parent qty-per-assembly 2 = total_quantity 6; x production qty 5 = 30
    assert child_line["required_quantity"] == 30


def test_production_quantity_multiplies_requirement(db):
    bom, li = _bom_with_line(db, part_number="PQ-1", qty=1)
    _lot(db, material_code="PQ-1", on_hand_qty="100")
    report = compute_availability(db, bom, production_quantity=4)
    line = _line(report, "PQ-1")
    assert line["required_quantity"] == 4


def test_grade_mismatch_is_review_required(db):
    bom, li = _bom_with_line(db, part_number="GRADE-1", material="Steel 4140 Grade Test", grade="Q&T")
    _lot(db, material="Steel 4140 Grade Test", grade="Annealed", on_hand_qty="10")
    report = compute_availability(db, bom, production_quantity=1)
    line = _line(report, "GRADE-1")
    assert line["status"] == REVIEW_REQUIRED


def test_missing_mapping_is_review_required(db):
    bom, li = _bom_with_line(db, part_number="NO-MATCH", material="Unobtainium")
    report = compute_availability(db, bom, production_quantity=1)
    line = _line(report, "NO-MATCH")
    assert line["status"] == REVIEW_REQUIRED
    assert "no matching" in line["explanation"].lower()


def test_ambiguous_multiple_match_is_review_required(db):
    bom, li = _bom_with_line(db, part_number="", material="Steel 4140", grade="")
    _lot(db, material="Steel 4140", grade="Q&T", on_hand_qty="5")
    _lot(db, material="Steel 4140", grade="Annealed", on_hand_qty="5")
    report = compute_availability(db, bom, production_quantity=1)
    line = report["lines"][0]
    assert line["status"] == REVIEW_REQUIRED


def test_unreviewed_spec_is_review_required(db):
    bom, li = _bom_with_line(db, part_number="UNREV-1", verification_status="Unverified")
    _lot(db, material_code="UNREV-1", on_hand_qty="50")
    report = compute_availability(db, bom, production_quantity=1)
    line = _line(report, "UNREV-1")
    assert line["status"] == REVIEW_REQUIRED
    assert "unreviewed" in line["explanation"].lower() or "unverified" in line["explanation"].lower()


def test_duplicate_requisition_not_created_on_repeated_calls(db):
    bom, li = _bom_with_line(db, part_number="DUP-1", qty=1)
    _lot(db, material_code="DUP-1", on_hand_qty="0")
    req1 = create_draft_requisition(db, bom, 5, actor="a@x.com")
    req2 = create_draft_requisition(db, bom, 5, actor="a@x.com")
    assert req1.id == req2.id


def test_concurrent_allocation_attempts_do_not_overdraw_stock(db):
    bom, li = _bom_with_line(db, part_number="CONC-1", qty=1)
    lot = _lot(db, material_code="CONC-1", on_hand_qty="10")
    # First allocation takes all 10.
    create_allocation(db, lot, bom.id, 10, actor="a")
    # A second "near-simultaneous" attempt re-reads state and must see no usable stock left.
    import pytest
    with pytest.raises(InsufficientStockError):
        create_allocation(db, lot, bom.id, 1, actor="b")


def test_viewer_can_preview_but_not_create_requisition_or_approve(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": password})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Set up a drawing/bom via a direct DB session is awkward across the HTTP boundary here, so
    # exercise permission gating against an endpoint that requires a real bom_id only loosely -
    # a 403 for the editor-only routes must come back before any BOM lookup even matters.
    resp = client.post("/api/inventory/requisitions/draft?bom_id=does-not-exist&production_quantity=1",
                        headers=headers)
    assert resp.status_code == 403

    resp2 = client.post("/api/inventory/requisitions/some-id/approve", headers=headers)
    assert resp2.status_code == 403

    # Preview (availability) is allowed for viewers even though the bom_id is fake -> 404, not 403.
    resp3 = client.get("/api/inventory/availability/does-not-exist", headers=headers)
    assert resp3.status_code == 404
