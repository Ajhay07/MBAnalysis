from __future__ import annotations

import os

import numpy as np
from sqlalchemy.orm import Session

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import fitz  # pymupdf
except Exception:  # pragma: no cover
    fitz = None

from app.config import get_settings
from app.models.models import Analysis, Component, Drawing, DrawingStatus, AuditLog, Job
from app.providers import get_provider
from app.schemas.analysis import AnalysisResult
from app.services.classification import classify_component
from app.services.ocr import run_ocr

# Target raster resolution for PDF pages: PyMuPDF's default is 72 DPI (zoom 1.0). A zoom of
# ~2.5-4.0 lands in the 180-290 DPI range, which is what both OCR and vision models need to
# read small title-block text reliably.
PDF_RASTER_ZOOM = 3.0


class PdfProcessingError(Exception):
    """Raised for any PDF that cannot be turned into analyzable pages (corrupt, encrypted,
    empty). Caught by run_analysis and turned into a clean Failed status + reason, never a
    raw 500."""


def drawing_abspath(drawing: Drawing) -> str:
    settings = get_settings()
    return os.path.abspath(os.path.join(settings.UPLOAD_DIR, drawing.stored_file_name))


def page_preview_path(drawing: Drawing, page_number: int) -> str:
    """Absolute path for a stored per-page raster preview of a (possibly multi-page) drawing.
    Single-page image uploads (PNG/JPG/TIFF) never go through this - the original file itself
    is page 1."""
    settings = get_settings()
    stem = os.path.splitext(drawing.stored_file_name)[0]
    return os.path.abspath(os.path.join(settings.UPLOAD_DIR, f"{stem}_page{page_number}.png"))


def _bgr_from_pixmap(pix) -> np.ndarray:
    """Converts a PyMuPDF pixmap (RGB or RGBA) to an OpenCV-style BGR numpy array."""
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def rasterize_pdf_pages(path: str, drawing: Drawing) -> list[tuple[int, np.ndarray | None, str]]:
    """Opens a PDF and returns one (page_number, bgr_image_or_None, embedded_text) tuple per
    page, writing a PNG preview for each page alongside the original file. Raises
    PdfProcessingError for any PDF that cannot be processed (corrupt, encrypted, empty) so the
    caller can mark the Analysis Failed with a clear reason instead of a 500."""
    if fitz is None:  # pragma: no cover - depends on optional dependency being installed
        raise PdfProcessingError("PDF support (pymupdf) is not installed on this server.")

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfProcessingError(f"Could not open PDF (file may be corrupt): {exc}") from exc

    try:
        if doc.is_encrypted:
            # doc.authenticate("") would succeed for PDFs "encrypted" with an empty owner
            # password but no real restriction; a genuinely password-protected file fails it.
            if not doc.authenticate(""):
                raise PdfProcessingError("Password-protected PDF not supported.")

        page_count = doc.page_count
        if page_count == 0:
            raise PdfProcessingError("PDF has no pages.")

        pages: list[tuple[int, np.ndarray | None, str]] = []
        matrix = fitz.Matrix(PDF_RASTER_ZOOM, PDF_RASTER_ZOOM)
        for i in range(page_count):
            page = doc.load_page(i)
            page_number = i + 1
            embedded_text = page.get_text() or ""

            image_bgr: np.ndarray | None = None
            try:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                preview_path = page_preview_path(drawing, page_number)
                pix.save(preview_path)
                if cv2 is not None:
                    image_bgr = _bgr_from_pixmap(pix)
            except Exception:
                image_bgr = None

            pages.append((page_number, image_bgr, embedded_text))
        return pages
    finally:
        doc.close()


def _load_image_array(path: str) -> np.ndarray | None:
    if cv2 is None:
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return None  # handled separately via rasterize_pdf_pages
    img = cv2.imread(path)
    return img


def _persist_result(
    db: Session, drawing: Drawing, analysis: Analysis, result: AnalysisResult, page_override: int | None,
) -> list[Component]:
    """Persists one provider result's components against an already-created Analysis row.
    page_override, when given, forces source_page to the true physical page the image came
    from (the provider has no way to know this - it only ever sees a single rasterized page)."""
    components = []
    for comp in result.components:
        make_buy = comp.make_buy if comp.make_buy in ("Make", "Buy", "Review") else classify_component(
            comp.category, comp.description, comp.confidence)
        component = Component(
            analysis_id=analysis.id,
            part_number=comp.part_number,
            description=comp.description,
            category=comp.category,
            quantity=comp.quantity,
            material=comp.material,
            grade=comp.grade,
            dimensions=comp.dimensions,
            tolerances=comp.tolerances,
            gear_specs=comp.gear_specs,
            make_buy=make_buy,
            confidence=comp.confidence,
            verification_status=comp.verification_status,
            source_page=page_override if page_override is not None else comp.source_page,
            source_region=comp.source_region,
            source_text=comp.source_text,
        )
        db.add(component)
        components.append(component)
    return components


def run_analysis(db: Session, drawing: Drawing, actor: str = "system") -> Analysis:
    """Full pipeline: OCR -> AI provider (OpenAI vision or demo) -> persist versioned analysis
    with components. Never substitutes seeded demo content for a real drawing - the provider
    is invoked fresh against this drawing's own file every time.

    Multi-page PDFs are rasterized page by page (embedded text is also extracted per page) and
    each page is fed through OCR + the provider independently, with every resulting component's
    source_page set to that page's true physical page number."""
    job = Job(drawing_id=drawing.id, job_type="analysis", status="Running")
    db.add(job)
    drawing.status = DrawingStatus.PROCESSING
    db.commit()

    try:
        path = drawing_abspath(drawing)
        ext = os.path.splitext(path)[1].lower()
        provider = get_provider()

        all_dimensions: list[dict] = []
        all_materials: list[str] = []
        all_ocr_text: list[str] = []
        confidences: list[float] = []
        title_block = None
        provider_name = provider.name
        pending_components: list = []  # list of (AnalysisResult, page_number)

        if ext == ".pdf":
            pages = rasterize_pdf_pages(path, drawing)
            for page_number, image, embedded_text in pages:
                ocr_text = embedded_text
                if image is not None:
                    ocr_result = run_ocr(image)
                    # Scanned pages have no embedded text; OCR output fills the gap. When both
                    # exist, keep the embedded text (more accurate) but still run OCR so nothing
                    # is skipped, and append anything OCR found that the text layer didn't.
                    if ocr_result.text and ocr_result.text.strip() not in (embedded_text or ""):
                        ocr_text = (embedded_text + "\n" + ocr_result.text).strip() if embedded_text else ocr_result.text

                page_result = provider.analyze(
                    image_path=page_preview_path(drawing, page_number),
                    ocr_text=ocr_text,
                    drawing_number=drawing.drawing_number,
                )
                if title_block is None:
                    title_block = page_result.title_block
                all_dimensions.extend(
                    {**d.model_dump(), "page": page_number} for d in page_result.dimensions
                )
                all_materials.extend(m for m in page_result.materials if m not in all_materials)
                all_ocr_text.append(f"--- Page {page_number} ---\n{ocr_text}")
                confidences.append(page_result.overall_confidence)
                pending_components.append((page_result, page_number))
            if title_block is None:
                # Should not happen (page_count==0 already raises), but keep a safe fallback.
                from app.schemas.analysis import TitleBlock
                title_block = TitleBlock(drawing_number=drawing.drawing_number)
        else:
            image = _load_image_array(path)
            ocr_text = ""
            if image is not None:
                ocr_result = run_ocr(image)
                ocr_text = ocr_result.text

            result = provider.analyze(
                image_path=path, ocr_text=ocr_text,
                drawing_number=drawing.drawing_number,
            )
            title_block = result.title_block
            all_dimensions = [d.model_dump() for d in result.dimensions]
            all_materials = list(result.materials)
            all_ocr_text = [result.raw_ocr_text or ocr_text]
            confidences = [result.overall_confidence]
            pending_components.append((result, None))

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        version = db.query(Analysis).filter(Analysis.drawing_id == drawing.id).count() + 1
        analysis = Analysis(
            drawing_id=drawing.id,
            version=version,
            provider=provider_name,
            title_block=title_block.model_dump(),
            dimensions=all_dimensions,
            materials=all_materials,
            raw_ocr_text="\n\n".join(all_ocr_text),
            overall_confidence=overall_confidence,
        )
        db.add(analysis)
        db.flush()

        all_components: list[Component] = []
        for page_result, page_number in pending_components:
            all_components.extend(_persist_result(db, drawing, analysis, page_result, page_number))

        needs_review = any(c.confidence < 0.6 for c in all_components) or not all_components
        drawing.status = DrawingStatus.NEEDS_REVIEW if needs_review else DrawingStatus.REVIEWED
        job.status = "Done"
        db.add(AuditLog(entity_type="drawing", entity_id=drawing.id, action="analyzed",
                         details={"provider": provider_name, "analysis_id": analysis.id},
                         actor=actor))
        db.commit()
        db.refresh(analysis)
        return analysis
    except PdfProcessingError as exc:
        drawing.status = DrawingStatus.FAILED
        drawing.error_message = str(exc)
        job.status = "Failed"
        job.error_message = str(exc)
        db.commit()
        raise
    except Exception as exc:
        drawing.status = DrawingStatus.FAILED
        drawing.error_message = str(exc)
        job.status = "Failed"
        job.error_message = str(exc)
        db.commit()
        raise
