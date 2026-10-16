"""Regression test: bom_candidate_service.build_candidate_bom() is actually wired into the
real analysis pipeline (not just unit-tested in isolation). Runs run_analysis() end-to-end
against the demo provider and confirms the persisted Component rows include a
quantity_basis="counted_feature" entry derived from the provider's repeated_features data."""
import os

from app.config import get_settings
from app.models.models import Analysis, Component, Drawing, DrawingStatus
from app.services.analysis_pipeline import run_analysis


def _make_drawing(db, name: str = "candidate_bom_wiring.png") -> Drawing:
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
        drawing_number=f"CANDBOM-{name}", title="Candidate BOM Wiring Test", revision="A",
        file_name=name, stored_file_name=name, file_type="png", file_size=len(png_bytes),
        status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def test_pipeline_persists_counted_feature_component_from_demo_provider(db):
    drawing = _make_drawing(db)
    analysis = run_analysis(db, drawing)

    components = db.query(Component).filter(Component.analysis_id == analysis.id).all()
    assert components, "pipeline persisted no components at all"

    counted = [c for c in components if c.quantity_basis == "counted_feature"]
    assert counted, (
        "expected at least one persisted Component with quantity_basis='counted_feature' "
        "derived from the demo provider's repeated_features (6x through_hole) via "
        "bom_candidate_service.build_candidate_bom() - got basis values: "
        f"{[c.quantity_basis for c in components]}"
    )

    # The geometry-derived candidate (from candidates_from_repeated_features, part_number="")
    # is distinct evidence from the provider's own directly-proposed DEMO-COMP-2, which also
    # happens to carry quantity_basis="counted_feature" - both should be present, proving the
    # service's merge (provider components + geometry-derived) actually ran.
    geometry_derived = [c for c in counted if c.part_number == ""]
    assert geometry_derived, "expected a geometry-derived candidate (empty part_number) from repeated_features"
    assert geometry_derived[0].quantity == 6
    assert geometry_derived[0].is_assumption is False
    assert geometry_derived[0].component_type == "purchased"
