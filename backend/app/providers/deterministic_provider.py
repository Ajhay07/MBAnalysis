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

try:
    import fitz  # pymupdf
except Exception:  # pragma: no cover
    fitz = None

from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.schemas.analysis import AnalysisResult, Ambiguity, ComponentCandidate, DimensionFinding, TitleBlock
from app.services.bom_table_extractor import extract_bom_table
from app.services.drawing_detail_extractor import extract_detail_dimensions, match_panel_to_description
from app.services.paddle_ocr import OcrRegion, run_page_ocr

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
# "WO No. 9374" / "W.O. No.: 9374" - the work order this drawing was issued for, distinct from
# the drawing's own drawing_number (e.g. "3C/25812/MB/25-26"). Seen verbatim on the WO 9374
# family of drawings, printed as a note rather than in the formal title-block grid.
_WO_NUMBER_RE = re.compile(r"\bW\.?O\.?\s*No\.?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{1,19})", re.IGNORECASE)

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

# ASTM ("A ###") and Indian Standard ("IS ####") material designations - these show up on every
# MB drawing's BOM table (A 240 TYP 304, A 516 Gr.70, IS 2062 E250 Gr.BR, IS 1367 CL 6.8, ...)
# but match neither the colloquial keyword list above nor _MATERIAL_RE (which needs an explicit
# "MATERIAL:"-style label on the same line, never a bare standard number in running text).
# Deliberately permissive about what follows the base "A ###"/"IS ####" code - a grade code
# ("E250"), TYP/Gr./CL suffix with or without the period real drawings are inconsistent about,
# and an optional trailing "/ 6.0" (seen on "CL 6.8 / 6.0") - but the base code alone is enough
# for _parse_materials to report the spec as present, even when the exact suffix can't be
# fully captured.
_ENGINEERING_STEEL_RE = re.compile(
    r"\b(?:A|IS)\s?\d{3,4}"
    r"(?:\s+[A-Z]\d{2,4})?"
    r"(?:\s*(?:TYP|GR|CL)\.?\s?[A-Z0-9.]+)?"
    r"(?:\s*/\s*\d+(?:\.\d+)?)?",
    re.IGNORECASE,
)


# "QUANTITY" / "SIZE ( NB )" labels sit on their own line, with the value 1-3 lines below
# (see the real title-block text dump for WO-9374-family drawings: "QUANTITY\n08 Nos.\n...").
# Line-local regexes (like _REV_RE etc. above) can't see across that line break, so this is a
# small forward-scan instead: find the label line, then take the first following line that
# itself looks like a bare value for that field.
_QUANTITY_LABEL_RE = re.compile(r"^QUANTITY\b", re.IGNORECASE)
_QUANTITY_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*NOS\.?", re.IGNORECASE)
_NB_LABEL_RE = re.compile(r"^SIZE\s*\(\s*NB\s*\)", re.IGNORECASE)
_NB_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*MM\b", re.IGNORECASE)
_LABEL_SCAN_AHEAD = 3  # how many following lines to check for the value


def _scan_label_value(lines: list[str], label_re: "re.Pattern", value_re: "re.Pattern") -> float | None:
    for i, line in enumerate(lines):
        if not label_re.search(line.strip()):
            continue
        # The value is sometimes on the same line as the label, sometimes on one of the next
        # _LABEL_SCAN_AHEAD lines (title blocks lay these out as stacked label/value cells).
        for candidate in [line] + lines[i + 1:i + 1 + _LABEL_SCAN_AHEAD]:
            m = value_re.search(candidate)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    return None
    return None


_NUMERIC_WORD_RE = re.compile(r"^\d+(\.\d+)?$")


def _embedded_text_numeric_regions(pdf_path: str, page_number: int) -> list[OcrRegion]:
    """Bare numeric words (e.g. a BOM table's QTY column digits) read from the PDF's own
    embedded text layer via PyMuPDF, with bounding boxes scaled into the SAME pixel coordinate
    space the rasterized-image OCR regions use (zoom = Settings.PDF_RENDER_DPI / 72, identical
    to app.services.analysis_pipeline.rasterize_pdf_pages' own rasterization) so they can be
    spatially matched against item/label regions exactly like any other OcrRegion. Restricted to
    numeric-only tokens (never a word) - this is a supplement for missing body-cell digits, not
    a general substitute for image OCR, so it can't introduce a false header-label match or a
    duplicate of text the image OCR pass already found correctly. Returns [] for a non-PDF
    source, an unreadable page, or any PyMuPDF error - never raises into the caller."""
    if fitz is None:
        return []
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
        doc.close()
    except Exception:
        return []
    zoom = get_settings().PDF_RENDER_DPI / 72.0
    regions: list[OcrRegion] = []
    for x0, y0, x1, y1, word, *_rest in words:
        text = (word or "").strip()
        if not _NUMERIC_WORD_RE.match(text):
            continue
        regions.append(OcrRegion(
            text=text, confidence=1.0,
            bbox=[[x0 * zoom, y0 * zoom], [x1 * zoom, y0 * zoom], [x1 * zoom, y1 * zoom], [x0 * zoom, y1 * zoom]],
        ))
    return regions


def _parse_drawing_quantity_and_nb(ocr_text: str) -> tuple[float | None, float | None]:
    """Reads the drawing's own "QUANTITY" (how many assemblies this drawing covers) and
    "SIZE ( NB )" (nominal bore) title-block fields, when printed. Returns (None, None) for
    either value it can't confidently find - never guessed, only ever a value actually read
    next to its own label."""
    lines = ocr_text.splitlines()
    quantity = _scan_label_value(lines, _QUANTITY_LABEL_RE, _QUANTITY_VALUE_RE)
    nb_size = _scan_label_value(lines, _NB_LABEL_RE, _NB_VALUE_RE)
    return quantity, nb_size


def _parse_title_block(ocr_text: str, drawing_number: str) -> TitleBlock:
    rev = "A"
    material_spec = ""
    scale = ""
    title = ""
    units = "mm"
    wo_number = ""
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
        if not wo_number:
            m = _WO_NUMBER_RE.search(line)
            if m:
                wo_number = m.group(1).strip().rstrip(",.")
    if _UNITS_IN_RE.search(ocr_text) and not _UNITS_MM_RE.search(ocr_text):
        units = "in"
    drawing_quantity, nb_size_mm = _parse_drawing_quantity_and_nb(ocr_text)
    return TitleBlock(
        drawing_number=drawing_number or "",
        title=title,
        revision=rev,
        units=units,
        scale=scale,
        material_spec=material_spec,
        drawing_quantity=drawing_quantity,
        nb_size_mm=nb_size_mm,
        wo_number=wo_number,
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
    # Bare ASTM/IS standard designations in running text (A 240 TYP 304, IS 2062 E250 Gr.BR,
    # ...) - no "MATERIAL:" label needed, see _ENGINEERING_STEEL_RE's own docstring. Scanned
    # over the whole text (not line-by-line) since a BOM table's material cell can legitimately
    # wrap, unlike the label-anchored patterns above.
    for m in _ENGINEERING_STEEL_RE.finditer(ocr_text):
        value = re.sub(r"\s+", " ", m.group(0)).strip().rstrip(",.")
        if value and value not in found:
            found.append(value)
    return found


def _rows_to_components(rows, page_number: int, detail_panels=None) -> list[ComponentCandidate]:
    """detail_panels (see app.services.drawing_detail_extractor) supplies SIZE dimensions pulled
    from the drawing's own "<NAME> DETAIL" panels when the printed BOM table has no SIZE column
    of its own (the common case for this drawing family). A row's own table-provided `size` text
    always wins when present; the detail-panel match is only used to fill the gap, and is never
    treated as fully verified - a match built from generic dim_N keys (or no match at all) keeps
    the component flagged for review via is_assumption/assumption_text."""
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

        dimensions: dict = {"size": row.size} if row.size else {}
        needs_dimension_confirmation = False
        # Always consult the matching detail panel, even when the BOM table's own SIZE cell
        # already gave us something - a SIZE cell often carries only OD (or a partial/garbled
        # reading), while the "<NAME> DETAIL" panel's structured od/id/thk/l/pcd/... dict is the
        # one place Thickness and Length actually show up. Previously this panel lookup was
        # skipped entirely whenever `dimensions` was already non-empty, which silently dropped
        # Thickness/Length for every component whose BOM row had ANY size text - the fix is to
        # merge the panel's keys in (never overwriting a key the BOM table itself already gave),
        # not to replace or skip.
        panel = match_panel_to_description(description, detail_panels) if detail_panels else None
        if panel is not None and panel.dimensions:
            added_keys = [key for key in panel.dimensions if key not in dimensions]
            for key, value in panel.dimensions.items():
                dimensions.setdefault(key, value)
            if added_keys:
                needs_dimension_confirmation = panel.needs_confirmation

        is_assumption = qty_value is None or needs_dimension_confirmation
        assumption_parts = []
        if qty_value is None:
            assumption_parts.append(
                "Row found in BOM table but no numeric quantity cell could be read - confirm before use."
            )
        if needs_dimension_confirmation:
            assumption_parts.append(
                f"SIZE taken from drawing panel '{panel.label_text}' (raw tokens: "
                f"{', '.join(panel.raw_tokens) or 'none'}) - confirm before use."
            )

        components.append(ComponentCandidate(
            part_number=row.part_no,
            description=description,
            category="",  # left for classify_component() in the pipeline to assign
            quantity=qty_value if qty_value is not None else 1,
            material=row.material,
            dimensions=dimensions,
            make_buy="Review",
            confidence=max(0.5, min(0.85, row.confidence)) if row.confidence else 0.6,
            verification_status="Unverified",
            source_page=page_number,
            source_text=row.raw_text[:300],
            quantity_basis="explicit_callout" if qty_value is not None else "assumed",
            component_type="purchased",
            is_assumption=is_assumption,
            assumption_text=" ".join(assumption_parts),
        ))
    return components


class DeterministicProvider(DrawingAnalysisProvider):
    """No API key, no network call, no generative model. See module docstring."""

    name = "deterministic"

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str,
                pdf_path: str | None = None, page_number: int = 1) -> AnalysisResult:
        title_block = _parse_title_block(ocr_text, drawing_number)
        dimensions = _parse_dimensions(ocr_text)
        materials = _parse_materials(ocr_text)

        components: list[ComponentCandidate] = []
        ambiguities: list[Ambiguity] = []
        missing_info: list[str] = []

        regions = self._regions_for(image_path, pdf_path=pdf_path, page_number=page_number)
        table = extract_bom_table(regions) if regions else None
        known_descriptions = [row.description for row in table.rows if row.description] if table else []
        detail_panels = extract_detail_dimensions(regions, known_descriptions) if regions else []
        if table and table.rows:
            components = _rows_to_components(table.rows, page_number=1, detail_panels=detail_panels)
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

    def _regions_for(self, image_path: str, pdf_path: str | None = None, page_number: int = 1):
        """Re-runs OCR to get region/bbox geometry (not just the flattened text string the
        pipeline already passed in) so BOM-table columns can be located. A second OCR pass per
        page is the simplest way to get this without changing the shared provider interface
        every other provider also implements; PaddleOCR's own engine is a cached singleton
        (see app.services.paddle_ocr), so the repeat cost is the per-image inference call only,
        not re-loading the model.

        Also merges in word-level regions read straight from the PDF's own embedded text layer
        (PyMuPDF), when `pdf_path` is given - traced directly to a real quantity-extraction bug
        on a production drawing: PaddleOCR's region detection over the rasterized image
        completely missed every digit in the BOM table's QTY strip (too small/low-contrast at
        render DPI to detect as its own region), even though the SAME PDF's embedded text layer
        reads them correctly (this is exactly why `ocr_text`/raw_ocr_text - built from
        page.get_text(), not from these regions - already contained the right numbers while the
        structured, region-based BOM/detail-panel extraction never saw them). Restricted to bare
        numeric tokens only (see _embedded_text_numeric_regions) so it can only ever supplement
        a missing body-row digit - it can never contribute a new header-label match, so it can't
        change how/whether a table or detail panel is found, only whether a QTY cell inside an
        already-found one is read."""
        regions: list = []
        if cv2 is not None:
            try:
                image = cv2.imread(image_path)
            except Exception:
                image = None
            if image is not None:
                try:
                    result = run_page_ocr(image, page_number=1)
                    regions = list(result.regions)
                except Exception:
                    regions = []
        if pdf_path:
            regions = regions + _embedded_text_numeric_regions(pdf_path, page_number)
        return regions
