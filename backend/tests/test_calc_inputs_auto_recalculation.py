"""PATCH /api/analyses/components/{id} now recomputes a Bellows/Shroud component's calc_result
automatically on every edit - calc_inputs, dimensions, or anything else - so a reviewer
correcting a length/width/thickness input sees the calculation update with no separate
Calculate step. calc_inputs always wins over whatever was OCR-extracted into `dimensions`."""
import uuid

from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy, User, UserRole
from app.security import create_access_token, hash_password


def _editor(db):
    email = f"engineer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bellows_component(db, dimensions=None, calc_inputs=None):
    drawing = Drawing(drawing_number="9374", title="Universal Expansion Joint", revision="A",
                       file_name="9374.pdf", stored_file_name="9374_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.85)
    db.add(analysis)
    db.flush()
    component = Component(
        analysis_id=analysis.id, description="Bellows", material="A 240 TYP 304", quantity=2,
        dimensions=dimensions or {}, make_buy=MakeBuy.BUY, confidence=0.85,
        verification_status="Unverified", source_text="BELLOWS", calc_inputs=calc_inputs or {},
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def test_editing_the_od_via_calc_inputs_updates_the_calculated_length_automatically(db, client):
    component = _bellows_component(db, dimensions={"od": "559"})
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"calc_inputs": {"num_plies": 1, "ply_thickness_mm": 0.6}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["calc_result"]["final_proposed_dimensions"]["length"] == 1765  # from OD 559
    assert body["calc_result"]["final_proposed_dimensions"]["thickness"] == 0.6  # from the new calc_inputs


def test_calc_inputs_od_override_wins_over_extracted_dimensions_and_recalculates(db, client):
    """A reviewer correcting a bad OCR OD reading via calc_inputs must change the calculated
    length on the very next edit - no stale value left over from the wrong OD."""
    component = _bellows_component(db, dimensions={"od": "999"})  # wrong/garbled OCR reading
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"calc_inputs": {"od": 559}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["calc_result"]["final_proposed_dimensions"]["length"] == 1765

    # Edit again with a different OD - the calculation must update again, automatically.
    resp2 = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"calc_inputs": {"od": 683}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["calc_result"]["final_proposed_dimensions"]["length"] != 1765


def test_bellows_width_formula_only_runs_when_no_width_already_known(db, client):
    component = _bellows_component(db, dimensions={"od": "559"})
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"calc_inputs": {"pitch_mm": 30, "convolution_depth_mm": 20, "number_of_convolutions": 10}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    width = resp.json()["calc_result"]["final_proposed_dimensions"]["width"]
    assert width == round(((0.57 * 30) + (2 * 20)) * 10 + 100, 2)
    assert resp.json()["calc_result"]["dimension_detail"]["width"]["status"] == "REVIEW_REQUIRED"


def test_bellows_width_number_of_convolutions_autofills_from_cad_callout(db, client):
    # Regression: a reviewer who only knows pitch_mm/convolution_depth_mm (the two genuinely
    # unextractable values) was still required to separately retype number_of_convolutions by
    # hand, even though it's already right there on the drawing's own "5+5 NO. OF CONVOLUTES"
    # callout - exactly the kind of manual-input friction parse_bellows_ply_text already solves
    # for num_plies/ply_thickness_mm. Confirmed against the real WO 9374 drawing's own wording.
    component = _bellows_component(
        db, dimensions={"od": "559"},
    )
    component.assumption_text = (
        "SIZE taken from drawing panel 'BELLOW  DETAIL' (raw tokens: Ø 559, 5+5 NO. OF "
        "CONVOLUTES) - confirm before use."
    )
    db.add(component)
    db.commit()
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"calc_inputs": {"pitch_mm": 20, "convolution_depth_mm": 6.3}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["calc_result"]["final_proposed_dimensions"]["width"] == 340.0


def test_editing_a_sleeve_description_never_populates_calc_result(db, client):
    """Sleeve has no formula - editing it must never backfill calc_spec_identifier/calc_result,
    unlike Bellows/Shroud."""
    drawing = Drawing(drawing_number="9374", title="x", revision="A", file_name="x.pdf",
                       stored_file_name="x_stored.pdf", file_type="pdf", file_size=1,
                       status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test", title_block={},
                         dimensions=[], materials=[], overall_confidence=0.8)
    db.add(analysis)
    db.flush()
    sleeve = Component(analysis_id=analysis.id, description="Sleeve", quantity=1, dimensions={},
                        make_buy=MakeBuy.BUY, confidence=0.8, verification_status="Unverified",
                        source_text="SLEEVE")
    db.add(sleeve)
    db.commit()
    db.refresh(sleeve)

    user = _editor(db)
    token = create_access_token(user.id, user.role.value)
    resp = client.patch(
        f"/api/analyses/components/{sleeve.id}",
        json={"material": "A 240 Gr. 304"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert not resp.json()["calc_result"]  # {} (the column's own default) - never backfilled
    assert resp.json()["calc_spec_identifier"] is None
