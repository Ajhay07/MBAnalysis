from app.models.models import Drawing, Analysis, Component, DrawingStatus, MakeBuy
from app.services.bom_service import generate_bom_from_analysis


def _make_analysis(db):
    drawing = Drawing(drawing_number="T-1", title="Test Drawing", revision="A",
                       file_name="t.png", stored_file_name="t_stored.png", file_type="png",
                       file_size=10, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=["Steel"],
                         overall_confidence=0.8)
    db.add(analysis)
    db.flush()
    c1 = Component(analysis_id=analysis.id, part_number="P1", description="Part one",
                    category="Shaft", quantity=1, material="Steel", make_buy=MakeBuy.MAKE,
                    confidence=0.9, verification_status="Verified")
    db.add(c1)
    db.flush()
    c2 = Component(analysis_id=analysis.id, part_number="P2", description="Part two",
                    category="Bearing", quantity=2, material="", make_buy=MakeBuy.BUY,
                    confidence=0.95, verification_status="Verified",
                    parent_component_id=c1.id)
    db.add(c2)
    db.commit()
    db.refresh(analysis)
    return drawing, analysis


def test_generate_bom_creates_line_items_matching_components(db):
    drawing, analysis = _make_analysis(db)
    bom = generate_bom_from_analysis(db, analysis)
    assert bom.id
    assert len(bom.line_items) == 2
    part_numbers = {li.part_number for li in bom.line_items}
    assert part_numbers == {"P1", "P2"}


def test_generate_bom_preserves_parent_child_relationship(db):
    drawing, analysis = _make_analysis(db)
    bom = generate_bom_from_analysis(db, analysis)
    child = next(li for li in bom.line_items if li.part_number == "P2")
    parent = next(li for li in bom.line_items if li.part_number == "P1")
    assert child.parent_line_item_id == parent.id


def test_generate_bom_sets_drawing_status_bom_generated(db):
    drawing, analysis = _make_analysis(db)
    generate_bom_from_analysis(db, analysis)
    db.refresh(drawing)
    assert drawing.status == DrawingStatus.BOM_GENERATED


def test_generate_bom_versions_increment(db):
    drawing, analysis = _make_analysis(db)
    bom1 = generate_bom_from_analysis(db, analysis)
    bom2 = generate_bom_from_analysis(db, analysis)
    assert bom2.version == bom1.version + 1
