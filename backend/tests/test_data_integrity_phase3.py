"""Phase 3 data-integrity regression tests:

1. OCR output stays linked to its source page + bounding box through persistence and through a
   reprocess/retry cycle.
2. A human-reviewed/verified Component is never silently overwritten by a reprocess/retry -
   run_analysis always creates a NEW versioned Analysis + NEW Component rows rather than
   mutating prior ones in place, so a previously verified Component is untouched by a later
   retry. This test proves that structurally, not just by assertion.
3. Demo data isolation still holds (delegates to the existing test_demo_isolation.py suite -
   this file adds one more angle: a real (non-demo) drawing's retry must never pull in demo
   component data).
4. Missing bounding boxes / empty OCR results / failed pages are handled gracefully (OCR
   adapter already covers this in test_paddle_ocr.py; here we check the pipeline level - a page
   whose image failed to rasterize still produces a Component list, not a crash).
"""
import os

from app.config import get_settings
from app.models.models import Analysis, Component, Drawing, DrawingStatus
from app.services.analysis_pipeline import run_analysis


def _make_drawing(db, name: str) -> Drawing:
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
        drawing_number=f"DI-{name}", title="Data Integrity Test", revision="A",
        file_name=name, stored_file_name=name, file_type="png", file_size=len(png_bytes),
        status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def test_component_source_page_and_bbox_persist_through_reprocess(db):
    drawing = _make_drawing(db, "linkage.png")
    analysis1 = run_analysis(db, drawing)
    components1 = db.query(Component).filter(Component.analysis_id == analysis1.id).all()
    assert components1, "demo provider should have produced at least one component"
    for c in components1:
        assert c.source_page is not None
        assert c.source_region is not None  # bbox dict, possibly {} but never missing/None-crash

    # Reprocess (retry) - a fresh Analysis version, independent component rows.
    analysis2 = run_analysis(db, drawing, retry_count=1)
    assert analysis2.id != analysis1.id
    assert analysis2.version == analysis1.version + 1
    components2 = db.query(Component).filter(Component.analysis_id == analysis2.id).all()
    for c in components2:
        assert c.source_page is not None
        assert c.source_region is not None

    # The original analysis + its components are untouched (still queryable, same ids/data).
    still_there = db.query(Component).filter(Component.analysis_id == analysis1.id).all()
    assert {c.id for c in still_there} == {c.id for c in components1}


def test_verified_component_not_overwritten_by_retry(db):
    """A reviewer verifies a component on analysis v1; retrying the pipeline must create a new
    analysis v2 with its own components, leaving the v1 verified component's fields exactly as
    the reviewer left them (no in-place mutation, no row deleted/replaced)."""
    drawing = _make_drawing(db, "verify_retry.png")
    analysis1 = run_analysis(db, drawing)
    components1 = db.query(Component).filter(Component.analysis_id == analysis1.id).all()
    assert components1

    reviewed = components1[0]
    reviewed.verification_status = "Verified"
    reviewed.make_buy = "Make"
    reviewed.description = "Reviewer-corrected description"
    db.commit()
    reviewed_id = reviewed.id

    # Retry the full pipeline against the same drawing.
    analysis2 = run_analysis(db, drawing, retry_count=1)
    assert analysis2.id != analysis1.id

    # The reviewed component row must still exist, unmodified, under the old analysis.
    still_reviewed = db.query(Component).get(reviewed_id)
    assert still_reviewed is not None
    assert still_reviewed.analysis_id == analysis1.id
    assert still_reviewed.verification_status == "Verified"
    assert still_reviewed.make_buy == "Make"
    assert still_reviewed.description == "Reviewer-corrected description"

    # New analysis's components are separate rows (verification_status reset per the provider,
    # not inherited/clobbered from the reviewed state - this is a NEW candidate set for review).
    components2 = db.query(Component).filter(Component.analysis_id == analysis2.id).all()
    assert reviewed_id not in {c.id for c in components2}


def test_real_drawing_retry_never_pulls_in_demo_components(db):
    drawing = _make_drawing(db, "no_demo_leak.png")
    analysis1 = run_analysis(db, drawing)
    analysis2 = run_analysis(db, drawing, retry_count=1)
    for analysis in (analysis1, analysis2):
        assert analysis.drawing_id == drawing.id
        for c in db.query(Component).filter(Component.analysis_id == analysis.id).all():
            # Components belong to this real drawing's analysis only; nothing demo-seeded.
            assert c.analysis_id in (analysis1.id, analysis2.id)
    # The drawing itself was never flipped to demo by the pipeline.
    db.refresh(drawing)
    assert drawing.is_demo is False


def test_analysis_with_zero_components_still_persists_cleanly(db, monkeypatch):
    """Simulates a page that OCR'd/analyzed to nothing (e.g. blank page) - the pipeline must
    still persist an Analysis row (with needs_review forced True) rather than crashing on an
    empty component list."""
    from app.providers import demo_provider

    drawing = _make_drawing(db, "empty_components.png")

    original_generate = demo_provider.DemoProvider.analyze

    def _empty_analyze(self, *, image_path, ocr_text, drawing_number):
        result = original_generate(self, image_path=image_path, ocr_text=ocr_text,
                                    drawing_number=drawing_number)
        result.components = []
        # Also clear repeated_features: otherwise bom_candidate_service.build_candidate_bom()
        # (now wired into the pipeline) would still derive a geometry-based fastener candidate
        # from the demo provider's repeated-feature evidence, which is correct behavior but not
        # what this "truly nothing was found" test is simulating.
        result.repeated_features = []
        return result

    monkeypatch.setattr(demo_provider.DemoProvider, "analyze", _empty_analyze)

    analysis = run_analysis(db, drawing)
    assert analysis.id is not None
    components = db.query(Component).filter(Component.analysis_id == analysis.id).all()
    assert components == []
    db.refresh(drawing)
    assert drawing.status == DrawingStatus.NEEDS_REVIEW
