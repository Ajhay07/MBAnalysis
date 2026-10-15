"""PDF rasterization and multi-page analysis pipeline tests. All PDFs are generated on the
fly with reportlab/pymupdf - no binary fixtures are committed to the repo."""
import io
import os

import fitz
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.models.models import Drawing, DrawingStatus
from app.services.analysis_pipeline import run_analysis, page_preview_path, PdfProcessingError


def _make_drawing(db, stored_file_name: str, file_type: str = "pdf") -> Drawing:
    drawing = Drawing(
        drawing_number=f"PDF-{stored_file_name}",
        title="Test PDF Drawing",
        revision="A",
        file_name=stored_file_name,
        stored_file_name=stored_file_name,
        file_type=file_type,
        file_size=1,
        status=DrawingStatus.UPLOADED,
        is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def _write(settings, stored_name: str, data: bytes) -> str:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, stored_name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _reportlab_pdf_bytes(num_pages: int, text_per_page: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(num_pages):
        c.setFont("Helvetica", 18)
        c.drawString(72, 700, text_per_page[i])
        c.showPage()
    c.save()
    return buf.getvalue()


def test_three_page_pdf_produces_per_page_components_with_correct_page_numbers(db):
    settings = get_settings()
    pdf_bytes = _reportlab_pdf_bytes(3, ["Page One Title Block", "Page Two Detail", "Page Three Notes"])
    stored_name = "multi_page_test.pdf"
    _write(settings, stored_name, pdf_bytes)
    drawing = _make_drawing(db, stored_name)

    analysis = run_analysis(db, drawing)

    assert drawing.status in (DrawingStatus.NEEDS_REVIEW, DrawingStatus.REVIEWED)
    assert analysis.page_count == 3
    pages_seen = sorted({c.source_page for c in analysis.components})
    # DemoProvider (no OPENAI_API_KEY in test env) returns exactly one component per call, and
    # the pipeline calls it once per page, so we should see one component per page number.
    assert pages_seen == [1, 2, 3]

    # Each page's rasterized preview must be stored on disk for the frontend pager.
    for page_number in (1, 2, 3):
        assert os.path.exists(page_preview_path(drawing, page_number))


def test_pdf_with_embedded_text_is_captured_directly_not_solely_via_ocr(db):
    settings = get_settings()
    pdf_bytes = _reportlab_pdf_bytes(1, ["UNIQUE-EMBEDDED-TEXT-MARKER-12345"])
    stored_name = "embedded_text_test.pdf"
    _write(settings, stored_name, pdf_bytes)
    drawing = _make_drawing(db, stored_name)

    analysis = run_analysis(db, drawing)

    assert "UNIQUE-EMBEDDED-TEXT-MARKER-12345" in analysis.raw_ocr_text


def test_corrupt_pdf_fails_cleanly_with_reason_no_unhandled_exception(db):
    settings = get_settings()
    stored_name = "corrupt_test.pdf"
    _write(settings, stored_name, b"%PDF-1.4 this is not actually a valid pdf structure \x00\x01\x02")
    drawing = _make_drawing(db, stored_name)

    with pytest.raises(PdfProcessingError):
        run_analysis(db, drawing)

    db.refresh(drawing)
    assert drawing.status == DrawingStatus.FAILED
    assert drawing.error_message
    assert "corrupt" in drawing.error_message.lower() or "could not open" in drawing.error_message.lower()


def test_encrypted_pdf_rejected_cleanly_with_reason_mentioning_password(db):
    settings = get_settings()
    stored_name = "encrypted_test.pdf"
    src = _reportlab_pdf_bytes(1, ["Secret Page"])
    doc = fitz.open(stream=src, filetype="pdf")
    path = os.path.join(settings.UPLOAD_DIR, stored_name)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="supersecret", owner_pw="ownersecret")
    doc.close()
    drawing = _make_drawing(db, stored_name)

    with pytest.raises(PdfProcessingError) as excinfo:
        run_analysis(db, drawing)

    assert "password" in str(excinfo.value).lower() or "encrypt" in str(excinfo.value).lower()
    db.refresh(drawing)
    assert drawing.status == DrawingStatus.FAILED
    assert drawing.error_message
    assert "password" in drawing.error_message.lower() or "encrypt" in drawing.error_message.lower()


_ZERO_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
    b"xref\n0 3\n0000000000 65535 f \n"
    b"trailer << /Size 3 /Root 1 0 R >>\n"
    b"startxref\n0\n%%EOF"
)


def test_zero_page_pdf_fails_with_reason(db):
    settings = get_settings()
    stored_name = "zero_page_test.pdf"
    _write(settings, stored_name, _ZERO_PAGE_PDF)
    drawing = _make_drawing(db, stored_name)

    with pytest.raises(PdfProcessingError) as excinfo:
        run_analysis(db, drawing)
    assert "no pages" in str(excinfo.value).lower()
    db.refresh(drawing)
    assert drawing.status == DrawingStatus.FAILED
