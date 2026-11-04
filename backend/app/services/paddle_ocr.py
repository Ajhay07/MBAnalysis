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
import threading
import traceback
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("app.services.paddle_ocr")

# Guards every call into the shared PaddleOCR engine singleton (see _get_engine below).
# FastAPI's sync endpoints run on a threadpool, and this app has (at least) two independent
# call sites that can each trigger a fresh OCR pass on the SAME engine instance: the analysis
# pipeline's own pass and the on-demand "OCR Evidence" endpoint
# (app.routers.drawings.get_page_ocr_regions) re-running OCR against a stored page preview -
# nothing serialized these against each other. PaddleOCR's underlying oneDNN/MKL-DNN CPU
# inference backend is NOT safe to call concurrently from multiple threads on one predictor
# instance; two overlapping calls is a known, reproducible cause of a low-level
# "could not execute a primitive descriptor" failure that looks image-specific but isn't -
# the single-threaded repro of a real failing drawing succeeded every time. This lock makes
# every `.ocr()` call strictly sequential instead of reaching for N separate engine instances
# (each one loads its own copy of the detection/recognition/classification model weights into
# memory - not worth it for a local/demo deployment's request volume).
_ocr_call_lock = threading.Lock()

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


_RETRY_MAX_SIDE_PX = 2200


def _downscale_for_retry(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Shrinks `image` so its longest side is at most _RETRY_MAX_SIDE_PX, returning the
    resized image and the scale factor applied (1.0 - already small enough - leaves it
    untouched). Used only as a fallback after a full-resolution OCR call raises; the caller
    divides returned bbox coordinates by this factor to keep them in the original image's
    pixel space."""
    if cv2 is None:
        return image, 1.0
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= _RETRY_MAX_SIDE_PX:
        return image, 1.0
    scale = _RETRY_MAX_SIDE_PX / float(longest)
    resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    return resized, scale


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

    rescale = 1.0  # multiply returned bbox coords by 1/rescale to project back to full-res space
    try:
        processed = preprocess_image(image)
        with _ocr_call_lock:
            raw = engine.ocr(processed, cls=True)
    except Exception as exc:
        # The usual cause of a "could not execute a primitive descriptor"-style failure here is
        # exactly what _ocr_call_lock above now prevents (two threads hitting the shared engine
        # at once) - but keep this downscaled retry as a second line of defense for the rarer
        # case where a specific image genuinely trips a primitive-construction limit inside the
        # detection backbone on its own. A real fallback, not a silent skip: if the retry also
        # fails, the original error is still what gets reported, never masked.
        logger.warning(
            "PaddleOCR failed on page %s at full resolution (%s); retrying downscaled: %s",
            page_number, getattr(image, "shape", "?"), exc,
        )
        try:
            downscaled, rescale = _downscale_for_retry(image)
            with _ocr_call_lock:
                raw = engine.ocr(downscaled, cls=False)
        except Exception:
            # Reported in production: once a call into this engine instance fails with a
            # oneDNN-style "could not execute a primitive" error, EVERY subsequent call on that
            # SAME long-lived singleton fails identically from then on (confirmed: 10 consecutive
            # re-analysis attempts each failed in well under a second - too fast to be a real OCR
            # attempt at all) - this engine's internal primitive cache has gotten corrupted, and
            # _get_engine()'s own "construct once, reuse forever" caching keeps serving that same
            # broken instance for the rest of this process's life. Dropping the cached engine
            # here forces the NEXT call to build a fresh one instead of being poisoned forever by
            # one bad call; _engine_init_failed is deliberately left alone, since a genuinely
            # unavailable PaddleOCR should still fail fast rather than retrying construction on
            # every single request.
            global _engine
            _engine = None
            logger.error(
                "PaddleOCR engine call failed on page %s even after a downscaled retry (%s) - "
                "dropping the cached engine instance so the next OCR call rebuilds a fresh one "
                "instead of reusing a possibly-corrupted one.", page_number, exc,
            )
            return PageOcrResult(page_number=page_number, configured=False, error=str(exc))

    regions: list[OcrRegion] = []
    warnings: list[str] = []
    if rescale != 1.0:
        warnings.append(
            "OCR succeeded only after downscaling this page (full-resolution attempt failed) - "
            "small/dense text may be less accurate than usual."
        )
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
        regions.append(OcrRegion(
            text=text, confidence=confidence,
            bbox=[[float(x) / rescale, float(y) / rescale] for x, y in bbox],
        ))
        if confidence < settings.OCR_CONFIDENCE_THRESHOLD:
            warnings.append(f"Low-confidence region ({confidence:.2f}): {text!r}")

    if not regions:
        warnings.append("OCR returned no text regions for this page.")

    return PageOcrResult(page_number=page_number, regions=regions, configured=True,
                          warnings=warnings)
