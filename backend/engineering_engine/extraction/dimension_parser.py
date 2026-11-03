"""Small shared parsing helpers + the extraction PRIORITY CHAIN from the spec:
  1. Native CAD dimension entity (cad_extractor - not implemented, no DXF available)
  2. PDF vector text / dimension annotations
  3. OCR result with spatial association
  4. Approved engineering calculation (handled by engineering_engine.calculations, not here)
  5. Manual verification if information is missing

Steps 2-3 are both covered by pdf_extractor.py today (the existing deterministic pipeline
already combines PyMuPDF's embedded text with PaddleOCR region data) - this module exposes a
single `get_component_evidence()` entry point that tries cad_extractor.py first (currently
always unavailable) and falls back to pdf_extractor.py, so a future DXF path slots in without
any calculator code needing to change.
"""
from __future__ import annotations

from engineering_engine.extraction import cad_extractor, pdf_extractor
from engineering_engine.extraction.pdf_extractor import RawComponentEvidence


def parse_numeric(value) -> float | None:
    """Best-effort float parse of a raw extracted dimension cell. Returns None (never 0, never
    a guess) for anything that doesn't cleanly parse - e.g. an OCR misread like 'O 559' that
    slipped through without going via drawing_detail_extractor's own Ø-handling, or a
    size-column free-text cell with units/annotations mixed in."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return None


def get_component_evidence(pdf_path: str, page_number: int = 1) -> dict[str, RawComponentEvidence]:
    """Priority chain entry point: tries native CAD (cad_extractor) first, falls back to the
    PDF vector-text + OCR pipeline (pdf_extractor). Manual verification (priority 5) is not a
    code path - it's what a REVIEW_REQUIRED/MISSING result in the output asks a human to do."""
    try:
        return cad_extractor.extract_cad_dimensions(pdf_path)  # always raises today
    except NotImplementedError:
        return pdf_extractor.extract_components(pdf_path, page_number=page_number)
