"""PATCH /api/analyses/components/{id} - dimensions is a reviewer-editable field so a human can
fill in SIZE by hand for a drawing whose layout the automated extractors can't read (dimensions
placed directly on the main view, no labeled "<NAME> DETAIL" panel - see
app.services.drawing_detail_extractor and app.schemas.api.ComponentUpdate.dimensions)."""
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


def _component_with_no_dimensions(db):
    drawing = Drawing(drawing_number="9347", title="Single Expansion Joint", revision="A",
                       file_name="9347.pdf", stored_file_name="9347_stored.pdf", file_type="pdf",
                       file_size=1000, status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="deterministic",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.6)
    db.add(analysis)
    db.flush()
    component = Component(analysis_id=analysis.id, description="Sleeve", material="IS 3589 / A 106 Gr.B",
                           quantity=1, dimensions={}, make_buy=MakeBuy.REVIEW, confidence=0.6,
                           verification_status="Unverified", source_text="Sleeve")
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def test_reviewer_can_manually_set_dimensions_on_a_component(db, client):
    component = _component_with_no_dimensions(db)
    user = _editor(db)
    token = create_access_token(user.id, user.role.value)
    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"dimensions": {"size": "OD 219  Thk 9.5"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["dimensions"] == {"size": "OD 219  Thk 9.5"}

    db.refresh(component)
    assert component.dimensions == {"size": "OD 219  Thk 9.5"}


def test_viewer_cannot_edit_component_dimensions(db, client):
    component = _component_with_no_dimensions(db)
    viewer = User(email="viewer-dims@example.com", hashed_password=hash_password("x"),
                  role=UserRole.VIEWER, is_active=True)
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    token = create_access_token(viewer.id, viewer.role.value)
    resp = client.patch(
        f"/api/analyses/components/{component.id}",
        json={"dimensions": {"size": "OD 219"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
