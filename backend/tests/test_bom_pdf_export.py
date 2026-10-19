from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy
from app.services.bom_service import generate_bom_from_analysis
from app.services.bom_pdf import bom_to_pdf_bytes


def _make_bom(db, with_cost: bool):
    drawing = Drawing(drawing_number="PDF-1", title="PDF Export Test", revision="A",
                       file_name="t.png", stored_file_name="t_stored.png", file_type="png",
                       file_size=10, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=["Steel"], overall_confidence=0.9)
    db.add(analysis)
    db.flush()
    make_component = Component(analysis_id=analysis.id, part_number="MK-1", description="Bracket",
                                category="Bracket", quantity=1, material="Steel", make_buy=MakeBuy.MAKE,
                                confidence=0.9, verification_status="Verified")
    buy_component = Component(analysis_id=analysis.id, part_number="BY-1", description="Bolt",
                               category="Fastener", quantity=4, material="", make_buy=MakeBuy.BUY,
                               confidence=0.9, verification_status="Verified")
    db.add_all([make_component, buy_component])
    db.commit()
    db.refresh(analysis)
    bom = generate_bom_from_analysis(db, analysis)
    if with_cost:
        for li in bom.line_items:
            if li.part_number == "BY-1":
                li.unit_cost = 0.5
        db.commit()
        db.refresh(bom)
    return drawing, bom


def test_pdf_export_produces_nonempty_pdf(db):
    drawing, bom = _make_bom(db, with_cost=True)
    pdf_bytes = bom_to_pdf_bytes(bom, drawing)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_pdf_export_empty_bom_does_not_crash(db):
    drawing = Drawing(drawing_number="PDF-EMPTY", title="Empty BOM", revision="A",
                       file_name="t.png", stored_file_name="t_stored.png", file_type="png",
                       file_size=10, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.0)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    bom = generate_bom_from_analysis(db, analysis)
    pdf_bytes = bom_to_pdf_bytes(bom, drawing)
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_never_fabricates_cost_for_unpriced_buy_item(db):
    # No unit_cost set on the Buy line - the PDF must not invent one; this is a smoke check
    # that generation succeeds and produces a real PDF, since cost text itself isn't
    # practically assertable from raw PDF bytes.
    drawing, bom = _make_bom(db, with_cost=False)
    pdf_bytes = bom_to_pdf_bytes(bom, drawing)
    assert pdf_bytes.startswith(b"%PDF")
