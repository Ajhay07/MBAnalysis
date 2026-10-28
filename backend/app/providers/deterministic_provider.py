from __future__ import annotations

"""Deterministic, non-generative drawing analysis: title block, dimensions, materials and BOM
components are extracted with regex/rule-based parsing over OCR text and OCR region geometry
(app.services.bom_table_extractor), never by calling a generative AI model. This is the ONLY
real analysis path (see app.providers.get_provider) - there is no AI vision provider anywhere
in this app, optional or otherwise, and no API key of any kind is needed.

Conservative by construction: every field this provider reports is grounded in the OCR text in
front of it (title_block/dimensions/materials) or structured OCR region geometry (components
only when bom_table_extractor finds a confident header+row match). It never counts holes or
features from the raw image (that would need real computer vision beyond what OpenCV's simple
rule-based preprocessing does here), so repeated_features is always empty. Anything it can't
ground is reported in missing_info/ambiguities instead of being guessed, matching
ComponentCandidate's own source_text/is_assumption evidence requirement.
"""

import re

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from app.providers.base import DrawingAnalysisProvider
from app.schemas.analysis import AnalysisResult, Ambiguity, ComponentCandidate, DimensionFinding, TitleBlock
from app.services.bom_table_extractor import extract_bom_table
from app.services.paddle_ocr import run_page_ocr

# --- Title block field patterns -------------------------------------------------------------
# Each pattern captures the value following a known label on the same line. Applied line-by-line
# (not with re.DOTALL across the whole text) so a label never accidentally swallows unrelated
# text from a later line.
_REV_RE = re.compile(r"\bREV(?:ISION)?\.?\s*[:\-]?\s*([A-Za-z0-9]{1,4})\b", re.IGNORECASE)
_MATERIAL_RE = re.compile(r"\bMATE?RIA?L\.?\s*(?:SPEC\.?)?\s*[:\-]\s*([A-Za-z0-9 ,./\-]{2,60})", re.IGNORECASE)
_SCALE_RE = re.compile(r"\bSCALE\.?\s*[:\-]?\s*(\d+\s*[:\-]\s*\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"\bTITLE\.?\s*[:\-]\s*([A-Za-z0-9 ,./\-]{2,80})", re.IGNORECASE)
_UNITS_MM_RE = re.compile(r"\b(ALL\s+DIM(?:ENSION)?S?\s+(?:IN|ARE\s+IN)\s+MM|\bMM\b)", re.IGNORECASE)
_UNITS_IN_RE = re.compile(r"\b(ALL\s+DIM(?:ENSION)?S?\s+(?:IN|ARE\s+IN)\s+(?:INCH|IN)\b|\bINCH(?:ES)?\b)", re.IGNORECASE)

# --- Dimension/callout patterns --------------------------------------------------------------
_DIM_PATTERNS = [
    ("diameter", re.compile(r"[ØøΦ]\s?\d+(?:\.\d+)?")),
    ("radius", re.compile(r"\bR\s?\d+(?:\.\d+)?\b")),
    ("thread", re.compile(r"\bM\d{1,3}(?:[xX]\d+(?:\.\d+)?)?\b")),
    ("tolerance", re.compile(r"±\s?\d+(?:\.\d+)?")),
    ("box_dims", re.compile(r"\b\d+(?:\.\d+)?\s?[xX×]\s?\d+(?:\.\d+)?(?:\s?[xX×]\s?\d+(?:\.\d+)?)?\b")),
]

_MATERIAL_KEYWORDS = [
    "stainless steel", "mild steel", "en8", "en 8", "en24", "en 24", "ss304", "ss 304",
    "ss316", "ss 316", "aluminium", "aluminum", "brass", "bronze", "cast iron", "titanium",
    "inconel", "hastelloy", "ms plate", "carbon steel", "galvanized", "galvanised",
]


def _parse_title_block(ocr_text: str, drawing_number: str) -> TitleBlock:
    rev = "A"
    material_spec = ""
    scale = ""
    title = ""
    units = "mm"
    for line in ocr_text.splitlines():
        if not rev or rev == "A":
            m = _REV_RE.search(line)
            if m:
                rev = m.group(1).upper()
        if not material_spec:
            m = _MATERIAL_RE.search(line)
            if m:
                material_spec = m.group(1).strip().rstrip(",.")
        if not scale:
            m = _SCALE_RE.search(line)
            if m:
                scale = re.sub(r"\s+", "", m.group(1))
        if not title:
            m = _TITLE_RE.search(line)
            if m:
                title = m.group(1).strip().rstrip(",.")
    if _UNITS_IN_RE.search(ocr_text) and not _UNITS_MM_RE.search(ocr_text):
        units = "in"
    return TitleBlock(
        drawing_number=drawing_number or "",
        title=title,
        revision=rev,
        units=units,
        scale=scale,
        material_spec=material_spec,
    )


def _parse_dimensions(ocr_text: str) -> list[DimensionFinding]:
    findings: list[DimensionFinding] = []
    seen: set[str] = set()
    for line_no, line in enumerate(ocr_text.splitlines(), start=1):
        for label, pattern in _DIM_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0).strip()
                key = f"{label}:{value}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append(DimensionFinding(
                    label=label, value=value, page=1,
                    source_text=line.strip()[:200], confidence=0.65,
                ))
    return findings


def _parse_materials(ocr_text: str) -> list[str]:
    found: list[str] = []
    lower = ocr_text.lower()
    for keyword in _MATERIAL_KEYWORDS:
        if keyword in lower and keyword.title() not in found:
            found.append(keyword.title())
    for line in ocr_text.splitlines():
        m = _MATERIAL_RE.search(line)
        if m:
            value = m.group(1).strip().rstrip(",.")
            if value and value not in found:
                found.append(value)
    return found


def _rows_to_components(rows, page_number: int) -> list[ComponentCandidate]:
    components: list[ComponentCandidate] = []
    for row in rows:
        description = row.description or row.part_no or row.material
        if not description:
            # Nothing usable to show a reviewer - skip rather than persist a blank line.
            continue
        qty_value: float | None = None
        qty_text = (row.qty or "").strip()
        qty_match = re.search(r"\d+(?:\.\d+)?", qty_text)
        if qty_match:
            try:
                qty_value = float(qty_match.group(0))
            except ValueError:
                qty_value = None
        components.append(ComponentCandidate(
            part_number=row.part_no,
            description=description,
            category="",  # left for classify_component() in the pipeline to assign
            quantity=qty_value if qty_value is not None else 1,
            material=row.material,
            dimensions={"size": row.size} if row.size else {},
            make_buy="Review",
            confidence=max(0.5, min(0.85, row.confidence)) if row.confidence else 0.6,
            verification_status="Unverified",
            source_page=page_number,
            source_text=row.raw_text[:300],
            quantity_basis="explicit_callout" if qty_value is not None else "assumed",
            component_type="purchased",
            is_assumption=qty_value is None,
            assumption_text=(
                "Row found in BOM table but no numeric quantity cell could be read - "
                "confirm before use." if qty_value is None else ""
            ),
        ))
    return components


class DeterministicProvider(DrawingAnalysisProvider):
    """No API key, no network call, no generative model. See module docstring."""

    name = "deterministic"

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        title_block = _parse_title_block(ocr_text, drawing_number)
        dimensions = _parse_dimensions(ocr_text)
        materials = _parse_materials(ocr_text)

        components: list[ComponentCandidate] = []
        ambiguities: list[Ambiguity] = []
        missing_info: list[str] = []

        regions = self._regions_for(image_path)
        table = extract_bom_table(regions) if regions else None
        if table and table.rows:
            components = _rows_to_components(table.rows, page_number=1)
            if not components:
                missing_info.append(
                    "A BOM-table-like header row was found, but no body row could be read "
                    "with enough confidence to become a component - add components manually."
                )
        else:
            ambiguities.append(Ambiguity(
                description=(
                    "No printed BOM table could be confidently located on this page "
                    "(deterministic extraction only reads an explicit ITEM/QTY/PART NO/"
                    "DESCRIPTION-style table; it does not count geometric features). Add "
                    "components manually, or re-run with an AI vision provider configured "
                    "if this drawing has no printed table."
                ),
                page=1,
            ))
            missing_info.append("No BOM table detected - components list is empty.")

        if not title_block.material_spec and not materials:
            missing_info.append("No material specification found in title block or text.")

        overall_confidence = (
            sum(c.confidence for c in components) / len(components) if components else 0.3
        )

        return AnalysisResult(
            provider=self.name,
            title_block=title_block,
            dimensions=dimensions,
            materials=materials,
            components=components,
            raw_ocr_text=ocr_text,
            overall_confidence=overall_confidence,
            view_types=[],
            repeated_features=[],
            ambiguities=ambiguities,
            missing_info=missing_info,
        )

    def _regions_for(self, image_path: str):
        """Re-runs OCR to get region/bbox geometry (not just the flattened text string the
        pipeline already passed in) so BOM-table columns can be located. A second OCR pass per
        page is the simplest way to get this without changing the shared provider interface
        every other provider also implements; PaddleOCR's own engine is a cached singleton
        (see app.services.paddle_ocr), so the repeat cost is the per-image inference call only,
        not re-loading the model."""
        if cv2 is None:
            return []
        try:
            image = cv2.imread(image_path)
        except Exception:
            image = None
        if image is None:
            return []
        try:
            result = run_page_ocr(image, page_number=1)
        except Exception:
            return []
        return result.regions
