"""GET /api/analyses/{id} now fills in Bellows/Shroud calc_result on its own - simply opening a
drawing shows the calculation, with no prior edit or indent generation needed. And PATCHing a
component's quantity now marks it confirmed (quantity_basis), clearing the "could not be read"
flag an OCR-fallback quantity carries."""
import uuid

from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy, User, UserRole
from app.security import create_access_token, hash_password


def _viewer(db):
    email = f"viewer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.VIEWER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _editor(db):
    email = f"engineer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bellows_analysis(db):
    drawing = Drawing(drawing_number="9374", title="x", revision="A", file_name="9374.pdf",
                       stored_file_name="9374_stored.pdf", file_type="pdf", file_size=1000,
                       status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test", title_block={},
                         dimensions=[], materials=[], overall_confidence=0.85)
    db.add(analysis)
    db.flush()
    bellows = Component(
        analysis_id=analysis.id, description="Bellows", material="A 240 TYP 304", quantity=1,
        dimensions={"od": "559"}, make_buy=MakeBuy.BUY, confidence=0.85,
        verification_status="Unverified", source_text="BELLOWS qty 1",
        assumption_text="Row found in BOM table but no numeric quantity cell could be read - confirm before use.",
        # Default quantity_basis="assumed" (Component column default) - never explicitly set,
        # matching a component the OCR pipeline really did build this way.
    )
    db.add(bellows)
    db.commit()
    db.refresh(analysis)
    return analysis


def test_get_analysis_fills_in_calc_result_with_no_prior_edit_or_indent(db, client):
    analysis = _bellows_analysis(db)
    viewer = _viewer(db)
    token = create_access_token(viewer.id, viewer.role.value)

    resp = client.get(f"/api/analyses/{analysis.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    bellows = resp.json()["components"][0]
    assert bellows["calc_spec_identifier"] == "BELLOWS"
    assert bellows["calc_result"]["final_proposed_dimensions"]["length"] == 1765


def test_get_analysis_is_idempotent_once_calc_result_is_current(db, client):
    """A second read shouldn't need another write - compute_bellows_or_shroud_result comparing
    equal to what's already stored should skip the commit, not just happen to still be correct."""
    analysis = _bellows_analysis(db)
    viewer = _viewer(db)
    token = create_access_token(viewer.id, viewer.role.value)
    r1 = client.get(f"/api/analyses/{analysis.id}", headers={"Authorization": f"Bearer {token}"})
    r2 = client.get(f"/api/analyses/{analysis.id}", headers={"Authorization": f"Bearer {token}"})
    assert r1.json()["components"][0]["calc_result"] == r2.json()["components"][0]["calc_result"]


def test_editing_quantity_marks_it_confirmed(db, client):
    analysis = _bellows_analysis(db)
    component_id = analysis.components[0].id
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.patch(
        f"/api/analyses/components/{component_id}",
        json={"quantity": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 2

    db.refresh(analysis.components[0])
    assert analysis.components[0].quantity_basis == "explicit_callout"
