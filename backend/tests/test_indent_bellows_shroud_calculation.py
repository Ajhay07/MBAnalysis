"""Bellows and Shroud are the only two component types with a real manufacturing FORMULA in
engineering_engine (blank length/thickness from OD+ply-count; base circumference from OD) -
generate_indent() now runs it automatically (no manual "Calculate" step) and uses its
"L x W x T" output as the SIZE text for just these two component types, matching the physical
indent sheet's own convention (see WO 9374's indent: Bellows "1765 x 340 x 0.6"). Every other
component type keeps the plain extracted od/id/thk/l display - there's no formula to apply."""
import uuid

from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy, User, UserRole
from app.security import hash_password
from app.services.bom_service import generate_bom_from_analysis
from app.services.indent_service import generate_indent


def _editor(db):
    email = f"engineer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _wo9374_style_bom(db):
    drawing = Drawing(drawing_number="9374", title="Universal Expansion Joint", revision="A",
                       file_name="9374.pdf", stored_file_name="9374_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.85)
    db.add(analysis)
    db.flush()
    bellows = Component(
        analysis_id=analysis.id, description="Bellows", material="A 240 TYP 304", quantity=2,
        dimensions={"od": "559", "width": "340"}, make_buy=MakeBuy.BUY, confidence=0.85,
        verification_status="Unverified", source_text="BELLOWS",
        assumption_text="SIZE taken from drawing panel 'BELLOW DETAIL' (raw tokens: 0 559, 1ply x 0.6 mm) - confirm before use.",
    )
    sleeve = Component(
        analysis_id=analysis.id, description="Sleeve", material="A 240 Gr. 304", quantity=2,
        dimensions={"od": "509", "thk": "1.5", "l": "150"}, make_buy=MakeBuy.BUY, confidence=0.85,
        verification_status="Unverified", source_text="SLEEVE",
    )
    db.add_all([bellows, sleeve])
    db.commit()
    db.refresh(analysis)
    bom = generate_bom_from_analysis(db, analysis)
    return drawing, bom, bellows, sleeve


def test_bellows_size_text_uses_the_calculated_length_width_thickness(db):
    drawing, bom, bellows, sleeve = _wo9374_style_bom(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)

    bellows_line = next(li for li in indent.lines if li.mtl_spec.startswith("Bellows"))
    # od=559 -> (559*3.14)+10 = 1765.26 -> rounds to 1765, matching the real WO 9374 indent.
    assert bellows_line.size_text == "1765 x 340 x 0.6"


def test_sleeve_size_text_is_plain_extracted_dimensions_not_a_formula(db):
    """Sleeve has no calculator (per engineering_engine.calculations.sleeve_calculator's own
    docstring: every dimension is a direct reading) - its indent SIZE must stay the plain
    OD/Thk/L extraction, untouched by compute_bellows_or_shroud_result."""
    drawing, bom, bellows, sleeve = _wo9374_style_bom(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)

    sleeve_line = next(li for li in indent.lines if li.mtl_spec.startswith("Sleeve"))
    assert sleeve_line.size_text == "OD 509  Thk 1.5  L 150"


def test_bellows_calc_result_persisted_on_the_component_automatically(db):
    """No manual 'Calculate' step - generating the indent is what runs and persists it."""
    drawing, bom, bellows, sleeve = _wo9374_style_bom(db)
    user = _editor(db)
    generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)

    db.refresh(bellows)
    assert bellows.calc_spec_identifier == "BELLOWS"
    assert bellows.calc_result["final_proposed_dimensions"]["length"] == 1765
    assert bellows.calc_result["final_proposed_dimensions"]["thickness"] == 0.6

    db.refresh(sleeve)
    assert sleeve.calc_spec_identifier is None  # never touched - no formula applies to Sleeve
