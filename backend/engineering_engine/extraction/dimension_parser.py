"""Small shared parsing helpers + the extraction PRIORITY CHAIN from the spec:
  1. Native CAD dimension entity (cad_extractor.py - geometry-based, see its own docstring
     for why it only ever fills cad_raw_tokens/cad_confidence, never dimensions{})
  2. PDF vector text / dimension annotations
  3. OCR result with spatial association
  4. Approved engineering calculation (handled by engineering_engine.calculations, not here)
  5. Manual verification if information is missing

Steps 2-3 are both covered by pdf_extractor.py today (the existing deterministic pipeline
already combines PyMuPDF's embedded text with PaddleOCR region data). cad_extractor.py is
a SEPARATE CAD file (DWG/DXF) that pdf_extractor.py never reads, and cad_extractor.py never
reads the BOM table pdf_extractor.py relies on for row descriptions/material/qty - so this
is a MERGE, not an either/or fallback: pdf_extractor's dict stays authoritative for which
components exist at all, and cad_extractor's findings (when a cad_path is supplied and
extraction succeeds) are attached onto the matching row for cross-checking, never used to
replace or override an OCR-derived dimension value.
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


def get_component_evidence(
    pdf_path: str, page_number: int = 1, cad_path: str | None = None
) -> dict[str, RawComponentEvidence]:
    """Priority chain entry point. Always runs the PDF vector-text + OCR pipeline
    (pdf_extractor) - it's the only source that reads the BOM table, so it's the only
    source that can say which components exist. When `cad_path` points at a real DWG/DXF,
    also runs cad_extractor.py and attaches its findings (cad_confidence/cad_raw_tokens)
    onto whichever row's description matches the CAD label, purely as additional
    evidence for a reviewer - it never overwrites an OCR-derived dimension value. Manual
    verification (priority 5) is not a code path - it's what a REVIEW_REQUIRED/MISSING
    result in the output asks a human to do."""
    evidence = pdf_extractor.extract_components(pdf_path, page_number=page_number)
    if not cad_path:
        return evidence

    try:
        cad_evidence = cad_extractor.extract_cad_dimensions(cad_path)
    except Exception:
        # No CAD evidence available (unsupported file, converter not configured, bad
        # file, etc.) - the OCR-derived evidence above is still valid and complete on
        # its own, so this is a silent no-op, not a failure of extraction overall.
        return evidence

    for description, row in evidence.items():
        for cad_description, cad_row in cad_evidence.items():
            if cad_description in description or description in cad_description:
                row.cad_confidence = cad_row.cad_confidence
                row.cad_raw_tokens = cad_row.cad_raw_tokens
                break
    return evidence
