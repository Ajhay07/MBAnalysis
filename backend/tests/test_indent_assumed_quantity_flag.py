"""Regression: a component whose BOM-table QTY cell couldn't be OCR'd gets quantity_basis
"assumed" and a fallback per-assembly quantity of 1 (app.providers.deterministic_provider), but
that 1 is a placeholder, not a real reading. Before this fix, app.services.indent_service
multiplied it through (1 x assembly_quantity) and printed the result as if it were confirmed -
e.g. every single row on a drawing whose BOM table failed to OCR showing the SAME
"<assembly_quantity> Nos", indistinguishable from a real count. Now those lines are flagged
requires_confirmation=True (and get the PDF's orange TBD-style highlight), same as a quantity
that's missing outright."""
import uuid

from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy, User, UserRole
from app.security import hash_password
from app.services.bom_service import generate_bom_from_analysis
from app.services.indent_pdf import indent_to_pdf_bytes
from app.services.indent_service import generate_indent


def _editor(db):
    email = f"engineer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bom_with_assumed_and_confirmed_quantities(db):
    drawing = Drawing(drawing_number="9374", title="Universal Expansion Joint", revision="A",
                       file_name="9374.pdf", stored_file_name="9374_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.85)
    db.add(analysis)
    db.flush()
    # quantity=1 for BOTH, but only one of them actually means "one per assembly" - the other
    # is the fallback value a failed QTY-cell read leaves behind (quantity_basis default).
    unread_qty = Component(
        analysis_id=analysis.id, description="Mid Pipe", material="", quantity=1,
        dimensions={"od": "559"}, make_buy=MakeBuy.BUY, confidence=0.85, verification_status="Unverified",
        source_text="MID PIPE", is_assumption=True,
        assumption_text="Row found in BOM table but no numeric quantity cell could be read - confirm before use.",
    )
    confirmed_qty = Component(
        analysis_id=analysis.id, description="Collar", material="A 240 TYP 304", quantity=1,
        dimensions={}, make_buy=MakeBuy.BUY, confidence=0.9, verification_status="Verified",
        source_text="COLLAR qty 1", quantity_basis="explicit_callout",
    )
    db.add_all([unread_qty, confirmed_qty])
    db.commit()
    db.refresh(analysis)
    bom = generate_bom_from_analysis(db, analysis)
    return drawing, bom


def test_assumed_quantity_line_is_flagged_for_confirmation(db):
    drawing, bom = _bom_with_assumed_and_confirmed_quantities(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)

    mid_pipe_line = next(li for li in indent.lines if li.mtl_spec.startswith("Mid Pipe"))
    assert mid_pipe_line.wt_qty == 4  # still shown, never hidden - just flagged
    assert mid_pipe_line.requires_confirmation is True
    assert "could not be read" in mid_pipe_line.note


def test_confirmed_quantity_line_is_not_flagged(db):
    drawing, bom = _bom_with_assumed_and_confirmed_quantities(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)

    collar_line = next(li for li in indent.lines if li.mtl_spec.startswith("Collar"))
    assert collar_line.wt_qty == 4
    assert collar_line.requires_confirmation is False
    assert collar_line.note == ""


def test_pdf_still_renders_with_mixed_assumed_and_confirmed_lines(db):
    drawing, bom = _bom_with_assumed_and_confirmed_quantities(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=4, wo_number="9374", actor=user.email)
    pdf_bytes = indent_to_pdf_bytes(indent)
    assert pdf_bytes.startswith(b"%PDF")
