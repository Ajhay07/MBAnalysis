"""Regression tests: the EXISTING inventory_service availability check (unmodified) works
correctly against a BOM built from the geometry-driven candidate-generation path (demo
provider + bom_candidate_service), not just the hand-built fixtures in test_inventory.py.

Covers:
  (a) a matched material (one with a real inventory lot) still gets correct stock/shortage
      numbers when run against a candidate-derived BOM line,
  (b) the geometry-derived fastener candidate (quantity_basis='counted_feature', no
      part_number/material_code) specifically gets REVIEW_REQUIRED, since there is nothing to
      match it against,
  (c) on_hand/reserved/quarantined quantities on the relevant InventoryLot rows are IDENTICAL
      before and after running the availability check - proving the preview never mutates
      stock, even when driven by the new candidate-generation path.
"""
import os

from app.config import get_settings
from app.models.models import (
    Bom, BomLineItem, Component, Drawing, DrawingStatus, InventoryLot, MakeBuy,
)
from app.services.analysis_pipeline import run_analysis
from app.services.bom_service import recompute_rollup
from app.services.inventory_service import compute_availability, REVIEW_REQUIRED, AVAILABLE


def _make_drawing(db, name: str = "inventory_candidate_regression.png") -> Drawing:
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, name)
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d7636060600000000500010d0a2db40000000049454e44ae426082"
    )
    with open(path, "wb") as f:
        f.write(png_bytes)
    drawing = Drawing(
        drawing_number=f"INVCAND-{name}", title="Inventory x Candidate BOM Regression",
        revision="A", file_name=name, stored_file_name=name, file_type="png", file_size=len(png_bytes),
        status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def _build_bom_from_candidate_components(db, analysis) -> Bom:
    """Mirrors how the real BOM-creation path would turn persisted candidate Components into
    BomLineItems - reuses bom_service.recompute_rollup unchanged, same as test_inventory.py."""
    bom = Bom(drawing_id=analysis.drawing_id, analysis_id=analysis.id, version=1, status="Draft")
    db.add(bom)
    db.flush()
    for comp in db.query(Component).filter(Component.analysis_id == analysis.id).all():
        db.add(BomLineItem(
            bom_id=bom.id, component_id=comp.id, part_number=comp.part_number,
            description=comp.description, category=comp.category, quantity=comp.quantity,
            material=comp.material, make_buy=comp.make_buy
            if comp.make_buy in (MakeBuy.MAKE, MakeBuy.BUY, MakeBuy.REVIEW) else MakeBuy.REVIEW,
        ))
    db.flush()
    recompute_rollup(db, bom.id)
    db.commit()
    db.refresh(bom)
    return bom


def test_availability_check_on_geometry_driven_candidate_bom(db, monkeypatch):
    # Needs the demo provider's repeated_features -> geometry-derived candidate specifically -
    # selected explicitly since DemoProvider is no longer the implicit no-key default (see
    # app.providers.get_provider).
    from app.providers.demo_provider import DemoProvider
    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: DemoProvider())

    drawing = _make_drawing(db)
    analysis = run_analysis(db, drawing)

    components = db.query(Component).filter(Component.analysis_id == analysis.id).all()
    assert components, "pipeline persisted no candidate components"

    # The geometry-derived fastener candidate: quantity_basis='counted_feature', no part_number
    # (never had a part number to begin with - bom_candidate_service.candidates_from_repeated_
    # features always sets part_number="").
    geometry_derived = [c for c in components if c.quantity_basis == "counted_feature" and c.part_number == ""]
    assert geometry_derived, "expected the geometry-derived fastener candidate to be persisted"
    geometry_component = geometry_derived[0]

    # A matched material: give the provider's directly-proposed DEMO-COMP-1 (material "Steel")
    # a real inventory lot so it has something to match against.
    matched_component = next(c for c in components if c.part_number == "DEMO-COMP-1")
    # The demo provider always marks its components Unverified (OCR-derived, not yet human-
    # reviewed); mark this one Verified so this assertion isolates the inventory-matching logic
    # (point a) from the separate "unreviewed spec forces REVIEW_REQUIRED" rule already covered
    # by tests/test_inventory.py::test_unreviewed_spec_is_review_required.
    matched_component.verification_status = "Verified"
    db.add(matched_component)
    db.commit()

    lot = InventoryLot(
        material_code=None, material="Steel", grade="", description="[TEST] Generic steel stock",
        unit="ea", on_hand_qty="25", reserved_qty="2", quarantined_qty="1", is_demo=False,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)

    # Capture stock levels BEFORE running the availability check.
    before = (lot.on_hand_qty, lot.reserved_qty, lot.quarantined_qty)

    bom = _build_bom_from_candidate_components(db, analysis)
    report = compute_availability(db, bom, production_quantity=1)

    lines_by_component_id = {}
    for li in bom.line_items:
        line = next(l for l in report["lines"] if l["bom_line_item_id"] == li.id)
        lines_by_component_id[li.component_id] = line

    # (a) matched material gets correct stock/shortage numbers.
    matched_line = lines_by_component_id[matched_component.id]
    # DEMO-COMP-1 quantity is 1; usable = on_hand(25) - reserved_total(2) - quarantined(1) = 22.
    assert matched_line["usable_available"] == 22
    assert matched_line["required_quantity"] == 1
    assert matched_line["net_shortage"] == 0
    assert matched_line["status"] == AVAILABLE

    # (b) the unmatched geometry-derived fastener candidate gets REVIEW_REQUIRED - it has no
    # material_code/part_number for match_lots() to match against (material="Steel" too, but no
    # part_number and this component is Unverified by default from the demo provider, which on
    # its own already forces REVIEW_REQUIRED - the assertion below holds either way).
    geometry_line = lines_by_component_id[geometry_component.id]
    assert geometry_line["status"] == REVIEW_REQUIRED

    # (c) on_hand/reserved/quarantined on the matched lot are UNCHANGED by the preview.
    db.refresh(lot)
    after = (lot.on_hand_qty, lot.reserved_qty, lot.quarantined_qty)
    assert before == after, (
        f"compute_availability must never mutate InventoryLot stock - before={before} after={after}"
    )
