"""Tests for GET /api/drawings/{id}/pages/{page}/ocr - the OCR Evidence viewer's backend
endpoint (Phase 2). Verifies it returns raw OCR regions + the configured confidence threshold,
and that it never touches Component/verification_status (read-only, raw-OCR layer only)."""
import os

from app.config import get_settings
from app.models.models import Component, Drawing, DrawingStatus, UserRole


def _login(client, make_user):
    user, pw = make_user(role=UserRole.ENGINEER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": pw})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_png_drawing(db, name="ocr_evidence.png"):
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, name)
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d7636060600000000500010d0a2db40000000049454e44ae426082"
    )
    with open(path, "wb") as f:
        f.write(png_bytes)
    drawing = Drawing(
        drawing_number="OCR-EV-1", title="OCR Evidence Test", revision="A",
        file_name=name, stored_file_name=name, file_type="png",
        file_size=len(png_bytes), status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def test_ocr_evidence_endpoint_returns_regions_and_threshold(client, make_user, db, monkeypatch):
    headers = _login(client, make_user)
    drawing = _make_png_drawing(db)

    from app.services import paddle_ocr
    from app.services.paddle_ocr import OcrRegion, PageOcrResult

    monkeypatch.setattr(
        paddle_ocr, "run_page_ocr",
        lambda image, page_number=1: PageOcrResult(
            page_number=page_number, configured=True,
            regions=[
                OcrRegion(text="MB-10045-REV-C", confidence=0.92, bbox=[[1, 1], [50, 1], [50, 10], [1, 10]]),
                OcrRegion(text="blurry", confidence=0.31, bbox=[[1, 20], [20, 20], [20, 30], [1, 30]]),
            ],
        ),
    )
    # Patch where it's imported into the router module too.
    import app.routers.drawings as drawings_router
    monkeypatch.setattr(drawings_router, "run_page_ocr", paddle_ocr.run_page_ocr)

    resp = client.get(f"/api/drawings/{drawing.id}/pages/1/ocr", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_number"] == 1
    assert "confidence_threshold" in body
    assert len(body["regions"]) == 2
    assert body["regions"][0]["low_confidence"] is False
    assert body["regions"][1]["low_confidence"] is True


def test_ocr_evidence_endpoint_never_writes_component_verification_status(client, make_user, db, monkeypatch):
    """Reading OCR evidence must never auto-set/change any Component's verification_status -
    that stays strictly human-gated via PATCH /api/analyses/components/{id}."""
    headers = _login(client, make_user)
    drawing = _make_png_drawing(db, "no_auto_verify.png")

    before = db.query(Component).count()
    client.get(f"/api/drawings/{drawing.id}/pages/1/ocr", headers=headers)
    after = db.query(Component).count()
    assert before == after


def test_ocr_evidence_endpoint_404_for_unknown_drawing(client, make_user):
    headers = _login(client, make_user)
    resp = client.get("/api/drawings/does-not-exist/pages/1/ocr", headers=headers)
    assert resp.status_code == 404
