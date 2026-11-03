"""Regression: GET /api/boms/by-drawing/{id} must return the most RECENT BOM first, not the
one with the highest version number. app.services.bom_service.generate_bom_from_analysis scopes
`version` PER ANALYSIS (how many BOMs already exist for that same analysis), restarting at 1
every time a new analysis is generated from - so a BOM regenerated twice from an OLDER analysis
(version 2) can easily have a higher version number than the very latest analysis's first-ever
BOM (version 1). Sorting by version alone let the frontend's "most recent BOM" (boms[0], see
ensureBom() in the drawing review page) silently keep serving a stale, pre-fix BOM even after a
newer, corrected re-analysis and a fresh BOM for it both existed - confirmed as the real cause
behind a user still seeing old data after every earlier fix in this session."""
import time
import uuid

from app.models.models import Analysis, Component, Drawing, DrawingStatus, MakeBuy, User, UserRole
from app.security import hash_password
from app.services.bom_service import generate_bom_from_analysis


def _editor(db):
    email = f"engineer-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, hashed_password=hash_password("x"), role=UserRole.ENGINEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _analysis(db, drawing, description):
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test", title_block={},
                         dimensions=[], materials=[], overall_confidence=0.85)
    db.add(analysis)
    db.flush()
    db.add(Component(analysis_id=analysis.id, description=description, quantity=1, dimensions={},
                      make_buy=MakeBuy.BUY, confidence=0.85, verification_status="Unverified",
                      source_text=description))
    db.commit()
    db.refresh(analysis)
    return analysis


def test_most_recently_created_bom_is_listed_first_even_with_a_lower_version_number(db):
    drawing = Drawing(drawing_number="9374", title="x", revision="A", file_name="9374.pdf",
                       stored_file_name="9374_stored.pdf", file_type="pdf", file_size=1,
                       status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    user = _editor(db)

    old_analysis = _analysis(db, drawing, "OLD-ANALYSIS-BELLOWS")
    # Regenerated twice from the SAME (old) analysis - version climbs to 2, well before the new
    # analysis below even exists.
    generate_bom_from_analysis(db, old_analysis, actor=user.email)
    stale_bom_v2 = generate_bom_from_analysis(db, old_analysis, actor=user.email)
    assert stale_bom_v2.version == 2

    time.sleep(0.01)  # guarantee a distinct created_at ordering on a fast test DB
    new_analysis = _analysis(db, drawing, "NEW-ANALYSIS-BELLOWS")
    fresh_bom_v1 = generate_bom_from_analysis(db, new_analysis, actor=user.email)
    assert fresh_bom_v1.version == 1  # lower version number, but the genuinely newer BOM

    boms = (
        db.query(type(stale_bom_v2))
        .filter(type(stale_bom_v2).drawing_id == drawing.id)
        .order_by(type(stale_bom_v2).created_at.desc())
        .all()
    )
    assert boms[0].id == fresh_bom_v1.id
    assert boms[0].analysis_id == new_analysis.id


def test_by_drawing_endpoint_returns_the_newest_analysis_bom_first(db, client):
    drawing = Drawing(drawing_number="9374", title="x", revision="A", file_name="9374.pdf",
                       stored_file_name="9374_stored.pdf", file_type="pdf", file_size=1,
                       status=DrawingStatus.NEEDS_REVIEW)
    db.add(drawing)
    db.flush()
    user = _editor(db)
    from app.security import create_access_token
    token = create_access_token(user.id, user.role.value)

    old_analysis = _analysis(db, drawing, "OLD-ANALYSIS-BELLOWS")
    generate_bom_from_analysis(db, old_analysis, actor=user.email)
    generate_bom_from_analysis(db, old_analysis, actor=user.email)  # stale v2

    time.sleep(0.01)
    new_analysis = _analysis(db, drawing, "NEW-ANALYSIS-BELLOWS")
    fresh = generate_bom_from_analysis(db, new_analysis, actor=user.email)  # fresh v1

    resp = client.get(f"/api/boms/by-drawing/{drawing.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    boms = resp.json()
    assert boms[0]["id"] == fresh.id
    assert boms[0]["analysis_id"] == new_analysis.id
