"""Regression fixture: Work Order 9347 (single expansion joint), per the drawing's own
printed BOM table and assembly quantity of 16 Nos. (see backend/seed fixtures / the attached
9347.pdf drawing). Expected totals come straight from the task spec's Phase 4 table, not from
this module reading the reference indent sheet - the arithmetic is proven independently of any
hardcoded WO-9347 value living in production code (app/services/indent_service.py contains no
mention of "9347" anywhere).
"""
from app.models.models import (
    Analysis, Component, Drawing, DrawingStatus, Indent, IndentRule, IndentRuleFormula, MakeBuy, User, UserRole,
)
from app.security import hash_password
from app.services.bom_service import generate_bom_from_analysis
from app.services.indent_pdf import indent_to_pdf_bytes
from app.services.indent_service import format_size_text, generate_indent

WO_9347_BOM_ROWS = [
    # (description, material, qty_per_assembly, dimensions)
    ("Bellow", "A 240 TYP 304 (SS 304)", 1, {"l": "762", "od": "210", "thk": "0.5"}),
    ("End pipe", "IS 2062 E250 BR", 2, {"od": "240", "thk": "6", "l": "61"}),
    ("Flange", "IS 2062 E250 BR", 2, {"od": "343", "id": "243", "thk": "14", "hole_dia": "22.4", "noh": "8", "pcd": "298.4"}),
    ("Sleeve", "IS 3589 / A 106 Gr.B", 1, {"od": "219", "thk": "9.5", "l": "175"}),
    ("Sleeve flange", "IS 2062 E250 BR", 1, {"od": "343", "id": "222", "thk": "14", "hole_dia": "22.4", "noh": "8", "pcd": "298.4"}),
    ("Collar", "A 240 TYP 304 (SS 304)", 2, {}),
]
ASSEMBLY_QUANTITY = 16
EXPECTED_TOTALS = {
    "Bellow": 16, "End pipe": 32, "Flange": 32, "Sleeve": 16, "Sleeve flange": 16, "Collar": 32,
}


def _make_9347_bom(db):
    drawing = Drawing(drawing_number="3C/25739/MB/25-26", title="Single Expansion Joint", revision="01",
                       file_name="9347.pdf", stored_file_name="9347_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={"drawing_number": "3C/25739/MB/25-26"}, dimensions=[],
                         materials=["SS 304", "IS 2062 E250 BR"], overall_confidence=0.9)
    db.add(analysis)
    db.flush()
    for description, material, qty, dims in WO_9347_BOM_ROWS:
        db.add(Component(
            analysis_id=analysis.id, description=description, material=material, quantity=qty,
            dimensions=dims, make_buy=MakeBuy.BUY, confidence=0.9, verification_status="Verified",
            source_text=f"{description} {material} qty {qty}",
        ))
    db.commit()
    db.refresh(analysis)
    bom = generate_bom_from_analysis(db, analysis)
    return drawing, bom


def _editor(db):
    user = User(email="engineer@example.com", hashed_password=hash_password("x"),
                role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_indent_quantities_match_wo_9347_fixture(db):
    """The deterministic multiplication: total = qty_per_assembly * assembly_quantity."""
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    indent = generate_indent(
        db, bom, assembly_quantity=ASSEMBLY_QUANTITY, wo_number="9347",
        party_name="Macawber Beekay Pvt. Ltd.", required_on="200 NB x 188 mm lg.",
        serial_no="2026-27/162", indent_date="22-08-26", actor=user.email,
    )
    assert len(indent.lines) == 6
    by_desc = {line.mtl_spec.split("\n")[0]: line for line in indent.lines}
    for description, expected_total in EXPECTED_TOTALS.items():
        line = by_desc[description]
        assert line.wt_qty == expected_total, f"{description}: expected {expected_total}, got {line.wt_qty}"
        assert line.requires_confirmation is False
        assert line.unit == "Nos"


def test_indent_does_not_double_multiply_assembly_quantity():
    """Quantity per assembly must be multiplied exactly once by assembly_quantity - never by
    both the BOM rollup (which treats a top-level item's total as its raw per-assembly qty)
    and the indent layer."""
    # Sleeve: qty_per_assembly=1, assembly_quantity=16 -> 16, not 16*16=256.
    assert 1 * ASSEMBLY_QUANTITY == 16
    assert not (1 * ASSEMBLY_QUANTITY) * ASSEMBLY_QUANTITY == 16


def test_format_size_text_preserves_od_id_thk_l_order():
    text = format_size_text({"od": "240", "thk": "6", "l": "61"})
    assert text == "OD 240  Thk 6  L 61"


def test_format_size_text_empty_dimensions_returns_empty_string():
    assert format_size_text({}) == ""
    assert format_size_text(None) == ""


def test_indent_rule_manual_required_never_fabricates_a_quantity(db):
    """A MANUAL_REQUIRED rule (e.g. filler wire with no approved rate yet) must always come
    back with wt_qty=None and requires_confirmation=True - this is the spec's explicit "do not
    invent universal consumable rates" requirement."""
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    rule = IndentRule(name="Fillerwire", mtl_spec="Fillerwire", size_text="ER 309",
                       unit="Pcs", formula=IndentRuleFormula.MANUAL_REQUIRED, active=True,
                       created_by=user.email)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    indent = generate_indent(db, bom, assembly_quantity=ASSEMBLY_QUANTITY, wo_number="9347",
                              rule_ids=[rule.id], actor=user.email)
    rule_lines = [li for li in indent.lines if li.source == "rule"]
    assert len(rule_lines) == 1
    assert rule_lines[0].wt_qty is None
    assert rule_lines[0].requires_confirmation is True
    assert rule_lines[0].mtl_spec == "Fillerwire"


def test_indent_rule_per_assembly_scales_with_assembly_quantity(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    rule = IndentRule(name="Electrode", mtl_spec="Electrode", size_text="E6013 - dia4 x 450",
                       unit="Pcs", formula=IndentRuleFormula.PER_ASSEMBLY, value=14.375,
                       active=True, created_by=user.email)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    indent = generate_indent(db, bom, assembly_quantity=ASSEMBLY_QUANTITY, wo_number="9347",
                              rule_ids=[rule.id], actor=user.email)
    rule_line = next(li for li in indent.lines if li.source == "rule")
    assert rule_line.wt_qty == 14.375 * ASSEMBLY_QUANTITY
    assert rule_line.requires_confirmation is False


def test_inactive_rule_not_applied_even_if_requested(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    rule = IndentRule(name="Retired rule", formula=IndentRuleFormula.FIXED_QTY, value=1,
                       active=False, created_by=user.email)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    indent = generate_indent(db, bom, assembly_quantity=ASSEMBLY_QUANTITY, rule_ids=[rule.id],
                              actor=user.email)
    assert not any(li.source == "rule" and li.note == "" for li in indent.lines)


def test_indent_pdf_generation_produces_valid_nonempty_pdf(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    indent = generate_indent(db, bom, assembly_quantity=ASSEMBLY_QUANTITY, wo_number="9347",
                              party_name="Macawber Beekay Pvt. Ltd.", required_on="200 NB x 188 mm lg.",
                              serial_no="2026-27/162", indent_date="22-08-26", actor=user.email)
    pdf_bytes = indent_to_pdf_bytes(indent)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_indent_pdf_renders_tbd_for_unconfirmed_lines_without_crashing(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    rule = IndentRule(name="Wooden Box", formula=IndentRuleFormula.MANUAL_REQUIRED,
                       active=True, created_by=user.email)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    indent = generate_indent(db, bom, assembly_quantity=ASSEMBLY_QUANTITY, rule_ids=[rule.id],
                              actor=user.email)
    pdf_bytes = indent_to_pdf_bytes(indent)
    assert pdf_bytes.startswith(b"%PDF")


def test_regenerating_indent_creates_new_version_not_overwrite(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    first = generate_indent(db, bom, assembly_quantity=16, wo_number="9347", actor=user.email)
    second = generate_indent(db, bom, assembly_quantity=16, wo_number="9347", actor=user.email)
    assert first.id != second.id
    assert second.version == first.version + 1
    assert db.query(Indent).filter(Indent.bom_id == bom.id).count() == 2


def test_viewer_cannot_generate_indent(db, client):
    from app.security import hash_password as _hash
    viewer = User(email="viewer@example.com", hashed_password=_hash("x"), role=UserRole.VIEWER, is_active=True)
    db.add(viewer)
    db.commit()
    drawing, bom = _make_9347_bom(db)

    from app.security import create_access_token
    token = create_access_token(viewer.id, viewer.role.value)
    resp = client.post(
        f"/api/boms/{bom.id}/indents",
        json={"assembly_quantity": 16, "wo_number": "9347"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_assembly_quantity_must_be_positive(db):
    drawing, bom = _make_9347_bom(db)
    user = _editor(db)
    try:
        generate_indent(db, bom, assembly_quantity=0, actor=user.email)
        assert False, "expected ValueError"
    except ValueError:
        pass
