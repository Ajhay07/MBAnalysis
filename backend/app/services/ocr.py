"""OCR adapter. Wraps pytesseract + OpenCV preprocessing with a graceful
'not configured' failure path when the Tesseract binary isn't installed.

Windows install: https://github.com/UB-Mannheim/tesseract/wiki
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import pytesseract
    from PIL import Image
except Exception:  # pragma: no cover
    pytesseract = None
    Image = None


@dataclass
class OcrResult:
    text: str
    configured: bool
    error: str | None = None


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Deskew, boost contrast, and resize for OCR. Works on a BGR or grayscale numpy array."""
    if cv2 is None:
        return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    # Contrast enhancement via CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Deskew using the minimum-area rectangle of thresholded foreground pixels
    thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    angle = 0.0
    if coords.size > 0:
        rect_angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + rect_angle) if rect_angle < -45 else -rect_angle
    (h, w) = enhanced.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    deskewed = cv2.warpAffine(enhanced, matrix, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)

    # Resize up for small drawings to improve OCR accuracy
    scale = 2.0 if max(h, w) < 2000 else 1.0
    if scale != 1.0:
        deskewed = cv2.resize(deskewed, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return deskewed


def is_tesseract_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def run_ocr(image: np.ndarray) -> OcrResult:
    if not is_tesseract_available():
        return OcrResult(
            text="",
            configured=False,
            error=(
                "Tesseract binary not found. Install it from "
                "https://github.com/UB-Mannheim/tesseract/wiki and ensure it is on PATH, "
                "or set pytesseract.pytesseract.tesseract_cmd. OCR is skipped; AI vision "
                "analysis and demo mode still work."
            ),
        )
    try:
        processed = preprocess_image(image)
        pil_img = Image.fromarray(processed)
        text = pytesseract.image_to_string(pil_img)
        return OcrResult(text=text, configured=True)
    except Exception as exc:  # pragma: no cover - depends on local binary
        return OcrResult(text="", configured=False, error=str(exc))
