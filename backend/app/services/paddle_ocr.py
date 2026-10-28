"""PaddleOCR adapter: local, free, no-API-key text extraction.

This is a DISTINCT processing stage from the deterministic interpretation that follows it
(app.providers.deterministic_provider / demo provider). OCR only extracts raw text + bounding
boxes from pixels; it never invents components, quantities, or dimensions - that interpretation
is the provider's job. A drawing can be "OCR completed" with zero components if no printed BOM
table is found (JobStage.OCR vs JobStage.VISION_ANALYSIS - a stage-name holdover from this
pipeline's history - already encodes this distinction).

The PaddleOCR engine is expensive to construct (loads detection/recognition/classification
models) so it is created ONCE as a module-level singleton and reused across every page/request,
never per-call. Model weights download to ~/.paddleocr on first use; after that everything runs
fully offline with no network calls and no paid API.
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("app.services.paddle_ocr")

# Compatibility shim, applied before anything imports paddleocr/imgaug.
#
# NumPy 2.0 removed `np.sctypes` outright. imgaug (a transitive runtime dependency pulled in
# by paddleocr for its data-augmentation pipeline - see backend/Dockerfile) still calls
# `np.sctypes["float"]` directly at import time in imgaug/imgaug.py, and imgaug has not been
# updated for NumPy 2.0. We used to fight pip's resolver to keep the whole environment pinned
# below NumPy 2.0, but that pin cannot hold without --no-deps on imgaug too: modern
# scikit-image/opencv-python releases (imgaug's own unpinned transitive deps) now REQUIRE
# NumPy >= 2.0 themselves, so pip's resolver upgrades numpy regardless, and forcibly
# downgrading it back afterward (`pip install --force-reinstall numpy==1.26.4` once those
# heavy C-extension packages are already unpacked) crashed the Docker build outright with a
# native "free(): invalid pointer" / PaddlePaddle SIGABRT - a much worse failure than the one
# it was trying to fix. The robust fix is to let numpy resolve to whatever pip naturally
# picks (2.x) and polyfill the one attribute imgaug actually needs, matching NumPy 1.x's own
# definition exactly. This is the documented community workaround for this exact breakage.
if not hasattr(np, "sctypes"):
    np.sctypes = {  # type: ignore[attr-defined]
        "int": [np.int8, np.int16, np.int32, np.int64],
        "uint": [np.uint8, np.uint16, np.uint32, np.uint64],
        "float": [np.float16, np.float32, np.float64],
        "complex": [np.complex64, np.complex128],
        "others": [bool, object, bytes, str, np.void],
    }

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    from paddleocr import PaddleOCR
except Exception as exc:  # pragma: no cover - optional dependency may not be installed
    PaddleOCR = None
    # This used to be swallowed completely with no log line at all, which is exactly why a
    # real "PaddleOCR not installed" report in production (the deterministic provider's only
    # OCR source) had no accompanying stack trace anywhere - `railway logs` showed nothing
    # pointing at paddleocr, even though every page OCR call was silently failing. Logging the
    # real import exception here means it now shows up in server logs at startup, not just as
    # a generic per-request error string.
    logger.error(
        "PaddleOCR import failed at startup - OCR (and therefore all real BOM-table "
        "extraction) will be unavailable until this is fixed: %s\n%s",
        exc, traceback.format_exc(),
    )

from app.config import get_settings


@dataclass
class OcrRegion:
    """One detected text region: recognized text, confidence (0-1), and its quadrilateral
    bounding box as [[x,y], [x,y], [x,y], [x,y]] in image pixel coordinates."""
    text: str
    confidence: float
    bbox: list[list[float]]


@dataclass
class PageOcrResult:
    """Structured OCR output for a single page/image. Kept separate from the analysis
    pipeline's evidence schema (Component/Analysis source_page/confidence/bbox fields) - this
    is the raw OCR layer's output, which the pipeline then feeds into that schema."""
    page_number: int
    regions: list[OcrRegion] = field(default_factory=list)
    configured: bool = True
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Concatenated recognized text, in detection order, with exact-duplicate
        consecutive lines collapsed (no aggressive fuzzy dedup)."""
        lines = [r.text for r in self.regions if r.text and r.text.strip()]
        deduped: list[str] = []
        for line in lines:
            if not deduped or deduped[-1].strip() != line.strip():
                deduped.append(line)
        return "\n".join(deduped)

    @property
    def low_confidence_regions(self) -> list[OcrRegion]:
        threshold = get_settings().OCR_CONFIDENCE_THRESHOLD
        return [r for r in self.regions if r.confidence < threshold]


_engine = None
_engine_init_failed = False


def _get_engine():
    """Module-level singleton. Constructed once on first real use and reused forever after -
    never per-page/per-request (model load alone takes several seconds)."""
    global _engine, _engine_init_failed
    if _engine is not None or _engine_init_failed:
        return _engine
    if PaddleOCR is None:
        _engine_init_failed = True
        return None
    settings = get_settings()
    try:
        _engine = PaddleOCR(
            use_angle_cls=True,
            lang=settings.OCR_LANGUAGE,
            use_gpu=settings.OCR_USE_GPU,
            show_log=False,
        )
    except Exception as exc:
        _engine_init_failed = True
        _engine = None
        logger.error(
            "PaddleOCR engine construction failed (module imported fine, but instantiating "
            "it - which downloads/loads model weights - did not): %s\n%s",
            exc, traceback.format_exc(),
        )
    return _engine


def is_paddleocr_available() -> bool:
    return _get_engine() is not None


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Deskew + CLAHE contrast enhancement, reusing the same conservative approach already
    proven in the pytesseract-era adapter (ocr.py): it does not threshold/denoise
    unconditionally, since that destroys thin dimension lines and decimal points on dense
    technical drawings. The original image is never mutated - callers keep it available too."""
    if cv2 is None:
        return image
    settings = get_settings()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    enhanced = gray
    if settings.OCR_PREPROCESS_CLAHE:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

    result = enhanced
    if settings.OCR_PREPROCESS_DESKEW:
        thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        angle = 0.0
        if coords.size > 0:
            rect_angle = cv2.minAreaRect(coords)[-1]
            angle = -(90 + rect_angle) if rect_angle < -45 else -rect_angle
        (h, w) = enhanced.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        result = cv2.warpAffine(enhanced, matrix, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)

    if settings.OCR_PREPROCESS_DENOISE:
        result = cv2.fastNlMeansDenoising(result, h=10)

    return result


def run_page_ocr(image: np.ndarray | None, page_number: int = 1) -> PageOcrResult:
    """Runs PaddleOCR against a single page image (BGR or grayscale numpy array). Never raises -
    any engine exception, malformed image, or missing dependency is converted into a structured
    PageOcrResult(configured=False, error=...) so the analysis pipeline can continue (and the
    existing Job retry mechanism can retry the whole page) instead of crashing."""
    settings = get_settings()
    if not settings.OCR_ENABLED:
        return PageOcrResult(page_number=page_number, configured=False,
                              warnings=["OCR_ENABLED is false; OCR skipped."])
    if image is None:
        return PageOcrResult(page_number=page_number, configured=False,
                              warnings=["No raster image available for this page."])
    if not isinstance(image, np.ndarray) or image.size == 0 or image.ndim not in (2, 3):
        return PageOcrResult(page_number=page_number, configured=False,
                              error="Malformed or empty image array.")

    engine = _get_engine()
    if engine is None:
        return PageOcrResult(
            page_number=page_number,
            configured=False,
            error=(
                "PaddleOCR is not installed/available on this server. Install paddleocr + "
                "paddlepaddle (see README). AI vision analysis and demo mode still work."
            ),
        )

    try:
        processed = preprocess_image(image)
        raw = engine.ocr(processed, cls=True)
    except Exception as exc:
        return PageOcrResult(page_number=page_number, configured=False, error=str(exc))

    regions: list[OcrRegion] = []
    warnings: list[str] = []
    # PaddleOCR 2.x `.ocr()` returns a list (one entry per input image) of lists of
    # [bbox, (text, confidence)] lines. A page with no detected text yields [None] or [].
    pages = raw or []
    page_lines = pages[0] if pages and pages[0] else []
    for line in page_lines:
        try:
            bbox, (text, confidence) = line
        except Exception:
            continue
        confidence = float(confidence)
        regions.append(OcrRegion(text=text, confidence=confidence,
                                  bbox=[[float(x), float(y)] for x, y in bbox]))
        if confidence < settings.OCR_CONFIDENCE_THRESHOLD:
            warnings.append(f"Low-confidence region ({confidence:.2f}): {text!r}")

    if not regions:
        warnings.append("OCR returned no text regions for this page.")

    return PageOcrResult(page_number=page_number, regions=regions, configured=True,
                          warnings=warnings)
