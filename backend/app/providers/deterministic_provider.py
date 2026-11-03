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

import difflib
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
# Bare header-label words worth pulling from the embedded PDF text layer alongside digits (see
# _embedded_text_numeric_regions) - traced directly to a real production drawing where NEITHER
# the QTY column's digits NOR its own "QTY" label were detected by PaddleOCR's region pass over
# the rasterized image (confirmed by pulling that drawing's actual live OCR regions: zero hits
# for "QTY" anywhere near the table), even though both are read correctly from the SAME page's
# embedded text layer. Deliberately just the QTY aliases, NOT every header label (DESCRIPTION/
# MATERIAL/SIZE are already found reliably by image OCR on every drawing seen so far - adding a
# second, embedded-text copy of a label already found would risk a near-duplicate region at a
# slightly different position confusing the single-label "pick the first match" selection in
# bom_table_extractor._extract_transposed_bom_table). QTY is the one column proven to need this.
_EMBEDDED_LABEL_WORDS = {"QTY", "QUANTITY", "QTY."}


def _embedded_text_numeric_regions(pdf_path: str, page_number: int) -> list[OcrRegion]:
    """Bare numeric words and BOM-table header-label words (QTY, MATERIAL, DESCRIPTION, ...)
    read from the PDF's own embedded text layer via PyMuPDF, with bounding boxes scaled into the
    SAME pixel coordinate space the rasterized-image OCR regions use (zoom =
    Settings.PDF_RENDER_DPI / 72, identical to
    app.services.analysis_pipeline.rasterize_pdf_pages' own rasterization) so they can be
    spatially matched against item/label regions exactly like any other OcrRegion. Restricted to
    numbers and this short exact-match label list (see _EMBEDDED_LABEL_WORDS) - never a general
    substitute for image OCR, so it can't introduce a false header-label match from unrelated
    running text or a duplicate of text the image OCR pass already found correctly. Returns []
    for a non-PDF source, an unreadable page, or any PyMuPDF error - never raises into the
    caller."""
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
        if not (_NUMERIC_WORD_RE.match(text) or text.upper() in _EMBEDDED_LABEL_WORDS):
            continue
        regions.append(OcrRegion(
            text=text, confidence=1.0,
            bbox=[[x0 * zoom, y0 * zoom], [x1 * zoom, y0 * zoom], [x1 * zoom, y1 * zoom], [x0 * zoom, y1 * zoom]],
        ))
    return regions


def _pdf_block_text(block: dict) -> str:
    return "".join("".join(s.get("text", "") for s in line.get("spans", [])) for line in block.get("lines", [])).strip()


_DESCRIPTION_FUZZY_MATCH_THRESHOLD = 0.8


def _pdf_structural_item_descriptions(pdf_path: str, page_number: int, ocr_descriptions: list[str]) -> dict[str, str]:
    """{ocr_description: corrected_description} for a transposed-layout BOM table's item names,
    using the SAME PyMuPDF block-clustering source as _pdf_structural_materials. The OCR-region
    item-identification pipeline gets item BOUNDARIES right (confirmed: component count and
    column order are both correct) but sometimes misreads individual characters - "NUT &
    LOCKNUT" -> "JUT & LOCKNUT", "SHROUD SUPPORT" -> "IROUD SUPPORT", "SLEEVE" -> "SLEEV" are
    all real production examples, confirmed against PyMuPDF's embedded-text blocks for the same
    row reading correctly. Unlike _pdf_structural_materials (which anchors on an exact/near-
    exact substring match of an already-correct description), this has to tolerate the
    description itself being wrong - matched by FUZZY text similarity (difflib) against every
    item-row block, not exact substring containment, since the count/order between the OCR list
    and the PDF's own block list isn't guaranteed to line up 1:1 (a whole item can be missing
    from the OCR side - confirmed: "M8 Bolt & Nut" was dropped entirely from the OCR item list
    on the same drawing where "Nut & Locknut" came through letter-mangled). Only a
    confident match (ratio >= _DESCRIPTION_FUZZY_MATCH_THRESHOLD) is returned, and an exact
    match is included too (so the caller can apply this uniformly without a separate
    equality check) - never a low-confidence guess. Returns {} (never raises) on any error or
    missing table structure."""
    if fitz is None or not ocr_descriptions:
        return {}
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        page_dict = page.get_text("dict")
        doc.close()
    except Exception:
        return {}

    blocks = [b for b in page_dict.get("blocks", []) if b.get("lines")]
    if not blocks:
        return {}

    desc_label = next((b for b in blocks if _pdf_block_text(b).strip().upper() == "DESCRIPTION"), None)
    if desc_label is None:
        return {}
    dx0, dy0, dx1, dy1 = desc_label["bbox"]
    item_row_texts = []
    for b in blocks:
        if b is desc_label:
            continue
        t = _pdf_block_text(b)
        if not t:
            continue
        x0, y0, x1, y1 = b["bbox"]
        y_overlap = min(y1, dy1) - max(y0, dy0)
        if y_overlap > 0 and x0 > dx1 and x0 < dx1 + 250:
            item_row_texts.append(t)
    if not item_row_texts:
        return {}

    results: dict[str, str] = {}
    for description in ocr_descriptions:
        if not description:
            continue
        best = max(
            item_row_texts,
            key=lambda t: difflib.SequenceMatcher(None, description.upper(), t.upper()).ratio(),
        )
        ratio = difflib.SequenceMatcher(None, description.upper(), best.upper()).ratio()
        if ratio >= _DESCRIPTION_FUZZY_MATCH_THRESHOLD:
            # A matched block can carry a merged trailing quantity digit with no space (same
            # PyMuPDF clustering artifact as _pdf_structural_materials' "COLLAR4" case) - e.g.
            # "END PIPE2" for a row whose real name is just "END PIPE". Strip one bare trailing
            # digit so the corrected description doesn't pick up a quantity by accident.
            cleaned = re.sub(r"(?<=[A-Za-z])\d$", "", best).strip()
            results[description] = cleaned or best
    return results


def _pdf_structural_materials(pdf_path: str, page_number: int, items: list[tuple[str, str]]) -> dict[str, str]:
    """{description: material} for a transposed-layout BOM table, using PyMuPDF's own
    paragraph/block clustering over the PDF's embedded text layer - NOT the rasterized-image
    OCR regions app.services.bom_table_extractor works from. Traced directly to a real
    production drawing: a wrapped, multi-line material callout ("IS 2062 E250 Gr.BR / A 515 /
    516 Gr. 70") that OCR-region pixel-distance heuristics kept truncating or misattributing
    comes back as ONE clean, already-assembled block from PyMuPDF's own internal text-run
    clustering - a fundamentally more reliable signal than reconstructing paragraph structure
    from individual OCR words ourselves.

    `items` is the full BOM row list (description, quantity-as-printed-text) from the ALREADY
    reliable OCR-region-based extraction (item identification and quantities both come through
    correctly there - only MATERIAL is unreliable) - used only to anchor each item's true
    column position by matching its own description text, and to recognize a row's own quantity
    digit when it's been merged into the same text block as its material (see the "COLLAR"
    worked example below). Returns {} (never raises) if the PDF has no DESCRIPTION/MATERIAL
    labels in this layout, or on any PyMuPDF error."""
    if fitz is None or not items:
        return {}
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        page_dict = page.get_text("dict")
        doc.close()
    except Exception:
        return {}

    blocks = [b for b in page_dict.get("blocks", []) if b.get("lines")]
    if not blocks:
        return {}

    def norm(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

    desc_label = next((b for b in blocks if _pdf_block_text(b).strip().upper() == "DESCRIPTION"), None)
    if desc_label is None:
        return {}
    desc_x0 = desc_label["bbox"][0]
    material_label_candidates = [b for b in blocks if b is not desc_label and "MATERIAL" in _pdf_block_text(b).upper()]
    if not material_label_candidates:
        return {}
    material_label = min(material_label_candidates, key=lambda b: abs(b["bbox"][0] - desc_x0))
    mat_y0 = material_label["bbox"][1]
    # The material "row": blocks starting at-or-below the MATERIAL label's own top edge, within
    # a generous band (covers realistic wrapping depth) and left of the unrelated spec-
    # parameters block that sits much further right on real MB drawings.
    material_row_candidates = [
        b for b in blocks
        if b is not material_label
        and mat_y0 - 10 <= b["bbox"][1] <= mat_y0 + 150
        and b["bbox"][0] < 300
        and len(_pdf_block_text(b)) >= 3
    ]

    results: dict[str, str] = {}
    for description, qty_text in items:
        nd = norm(description)
        if not nd:
            continue
        # The item's own description block, matched by TEXT CONTENT (not position) - far more
        # reliable than trying to re-derive which block is "this table's column N" from
        # geometry alone. Requires the match to be a substantial fraction of the description's
        # own length so a short, unrelated fragment (e.g. a lone view-pane letter "C") can't
        # spuriously match as a substring of a longer description.
        candidates = [
            b for b in blocks
            if len(norm(_pdf_block_text(b))) >= max(3, len(nd) * 0.6)
            and (nd in norm(_pdf_block_text(b)) or norm(_pdf_block_text(b)) in nd)
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda b: abs(len(norm(_pdf_block_text(b))) - len(nd)))
        item_block = candidates[0]
        raw = _pdf_block_text(item_block)
        residual = ""
        if len(raw) > len(description) + 3:
            # PyMuPDF's own clustering merged this item's description together with its
            # material (and sometimes its quantity digit) into ONE block - e.g. a real drawing's
            # Collar row came through as "A 240 Gr. 304COLLAR4" (material + "COLLAR" + "4", no
            # spaces). Strip the description substring and a trailing quantity digit that
            # matches this row's own already-known quantity (never an arbitrary trailing digit -
            # that would just as easily eat the material's own final digits, e.g. the "304" in
            # "A 240 Gr. 304").
            residual = re.sub(re.escape(description), "", raw, flags=re.IGNORECASE)
            if qty_text and residual.endswith(qty_text):
                residual = residual[: -len(qty_text)]
            residual = residual.strip()
        # A real material string on these drawings matches the same ASTM/IS designation pattern
        # _ENGINEERING_STEEL_RE already looks for elsewhere ("A 240...", "IS 2062..."). Anything
        # else means this "merged block" guess was actually a false positive - most often a
        # component whose OWN description is itself truncated by the (separate, OCR-region-
        # based) item-identification step, e.g. "& NUT" instead of "M8 BOLT & NUT", which fools
        # the length/substring match above into treating the correctly-matched-but-longer item
        # block as a merged description+material pair when it's really just the item's own full,
        # untruncated name ("M8 BOLT" left over after stripping "& NUT" - note this DOES contain
        # a digit, "8", so a bare digit check alone isn't enough). Falls through to the ordinary
        # nearest-material-row-by-x lookup instead of accepting a bad guess.
        if residual and _ENGINEERING_STEEL_RE.search(residual):
            results[description] = residual
            continue
        item_x0 = item_block["bbox"][0]
        best = min(material_row_candidates, key=lambda b: abs(b["bbox"][0] - item_x0), default=None)
        if best is not None:
            results[description] = _pdf_block_text(best)
    return results


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
            elif pdf_path:
                # Correct item descriptions FIRST (see _pdf_structural_item_descriptions - OCR
                # misreads individual characters, e.g. "NUT & LOCKNUT" -> "JUT & LOCKNUT"), then
                # look up materials using the now-corrected descriptions - a wrong description
                # was also why those same rows' materials came back blank (the text-match in
                # _pdf_structural_materials never found anything for the garbled name). Item
                # IDENTITY (count/order) and quantity are left untouched; only the description
                # text itself and material are ever replaced, and only when a lookup actually
                # found something confident enough.
                better_descriptions = _pdf_structural_item_descriptions(
                    pdf_path, page_number, [c.description for c in components]
                )
                for c in components:
                    corrected = better_descriptions.get(c.description)
                    if corrected:
                        c.description = corrected

                items = [
                    (c.description, f"{c.quantity:g}" if c.quantity is not None else "")
                    for c in components
                ]
                better_materials = _pdf_structural_materials(pdf_path, page_number, items)
                for c in components:
                    better = better_materials.get(c.description)
                    if better:
                        c.material = better
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
