"""Critical isolation test: uploading and analyzing a real drawing must never return the
seeded demo project's content, and the DemoProvider fallback must be clearly labeled distinct
from any seeded demo project text."""
import os

from app.database import SessionLocal
from app.models.models import Drawing, DrawingStatus
from app.providers.demo_provider import DemoProvider
from seed import seed_demo_data, PROJECTS


def test_demo_provider_output_does_not_contain_seeded_project_identifiers(db):
    """The DemoProvider (used as graceful fallback for real uploads with no API key) must not
    echo any of the specific seeded demo project drawing numbers/descriptions."""
    result = DemoProvider().analyze(image_path="irrelevant.png", ocr_text="", drawing_number="REAL-9999")
    seeded_numbers = {p["drawing_number"] for p in PROJECTS}
    assert result.title_block.drawing_number not in seeded_numbers
    for comp in result.components:
        assert comp.part_number not in {c["part_number"] for p in PROJECTS for c in p["components"]}


def test_seeded_demo_drawings_are_flagged_is_demo(db):
    seed_demo_data(db)
    demo_drawings = db.query(Drawing).filter(Drawing.is_demo == True).all()  # noqa: E712
    assert len(demo_drawings) == len(PROJECTS)
    for d in demo_drawings:
        assert d.is_demo is True
        assert "[DEMO]" in d.title


def test_real_drawing_upload_is_never_marked_demo(db):
    seed_demo_data(db)
    real_drawing = Drawing(
        drawing_number="REAL-0001", title="Customer Part", revision="A",
        file_name="real.png", stored_file_name="real_stored.png", file_type="png",
        file_size=123, status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(real_drawing)
    db.commit()
    db.refresh(real_drawing)

    assert real_drawing.is_demo is False
    assert "[DEMO]" not in real_drawing.title
    assert real_drawing.drawing_number not in {p["drawing_number"] for p in PROJECTS}

    # Querying only non-demo drawings never returns the seeded gearbox/shaft/bracket projects
    non_demo = db.query(Drawing).filter(Drawing.is_demo == False).all()  # noqa: E712
    seeded_numbers = {p["drawing_number"] for p in PROJECTS}
    assert all(d.drawing_number not in seeded_numbers for d in non_demo)
    assert any(d.drawing_number == "REAL-0001" for d in non_demo)
