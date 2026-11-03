"""POST /api/analyses/components/{id}/calculate - runs a Component through the
engineering_engine (backend/engineering_engine) via app.services.calc_engine_service, using
calc_inputs as manual readings, and persists calc_spec_identifier/calc_result."""
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


def _component(db, description="Sleeve", quantity=2, calc_inputs=None):
    drawing = Drawing(drawing_number="9347", title="Single Expansion Joint", revision="A",
                       file_name="9347.pdf", stored_file_name="9347_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="deterministic",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.6)
    db.add(analysis)
    db.flush()
    component = Component(analysis_id=analysis.id, description=description, material="IS 3589",
                           quantity=quantity, dimensions={}, make_buy=MakeBuy.REVIEW, confidence=0.6,
                           verification_status="Unverified", source_text=description,
                           calc_inputs=calc_inputs or {})
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def test_calculate_classifies_and_persists_calc_result(db, client):
    component = _component(db, description="Sleeve", calc_inputs={"od": 150, "thickness": 8, "length": 400})
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.post(
        f"/api/analyses/components/{component.id}/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["calc_spec_identifier"] == "SLEEVE"
    assert body["calc_result"]["spec_identifier"] == "SLEEVE"
    assert body["calc_result"]["status"] in {"VERIFIED", "CALCULATED", "REVIEW_REQUIRED"}

    db.refresh(component)
    assert component.calc_spec_identifier == "SLEEVE"
    assert component.calc_result["spec_identifier"] == "SLEEVE"


def test_calculate_on_unclassifiable_description_reports_unclassified_without_error(db, client):
    component = _component(db, description="Some Unknown Widget Nobody Registered")
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)

    resp = client.post(
        f"/api/analyses/components/{component.id}/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["calc_spec_identifier"] is None
    assert body["calc_result"]["status"] == "UNCLASSIFIED"


def test_calculate_404s_for_unknown_component(db, client):
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)
    resp = client.post(
        "/api/analyses/components/does-not-exist/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_viewer_cannot_trigger_calculation(db, client):
    component = _component(db)
    viewer = User(email="viewer-calc@example.com", hashed_password=hash_password("x"),
                  role=UserRole.VIEWER, is_active=True)
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    token = create_access_token(viewer.id, viewer.role.value)

    resp = client.post(
        f"/api/analyses/components/{component.id}/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
