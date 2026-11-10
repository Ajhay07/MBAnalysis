from __future__ import annotations

"""Deterministic extraction of per-component SIZE dimensions from a drawing's labeled DETAIL
panels (e.g. "SLEEVE DETAIL", "END PIPE DETAIL", "HOUSING FLANGE DETAIL") - the panels MB
Metallic Bellows drawings use to dimension each BOM component separately, since their main
BILL OF MATERIAL table (app.services.bom_table_extractor) only carries DESCRIPTION/MATERIAL/QTY,
never SIZE, for this drawing family (confirmed directly from real production drawings: WO-9374,
WO-25848 and others - the BOM table has no SIZE column; dimensions live in these detail panels
instead).

Deliberately conservative, same philosophy as bom_table_extractor and reference_bom_service:
- A DETAIL panel is only recognized when its own label text literally reads "<NAME> DETAIL"
  (optionally suffixed "-A"/"-B"/etc for a weld-detail variant) - generic unlabeled callouts
  ("DETAIL-A" with no component name) are never guessed at.
- Numeric tokens found near a label are assigned to OD/ID/Thk/L/PCD/etc. only when the token is
  itself explicitly labeled (either an adjacent "OD"/"ID"/"THK"/"L" text region, or an inline
  "OD559" style token) or unambiguous by convention (a lone Ø-prefixed diameter, a lone small
  decimal as wall thickness). Anything left over is still returned - under generic dim_N keys -
  rather than silently dropped, so a human reviewer can see exactly what was found and confirm
  it; nothing here is ever treated as final/verified without that confirmation.
"""

import re
from dataclasses import dataclass, field

try:
    import fitz  # pymupdf
except Exception:  # pragma: no cover
    fitz = None

# "<NAME> DETAIL" or "<NAME> DETAIL-A" / "<NAME> DETAIL 'B'" - NAME must be non-empty, so a bare
# "DETAIL-A" weld/section callout (no component name) is excluded by construction. An optional
# leading item-number marker ("[01] BELLOW DETAIL", "01. BELLOW DETAIL") is stripped first -
# confirmed on a real drawing (3I/26160A) where this exact "[01] " prefix otherwise blocked the
# whole match, since "[" isn't a valid NAME character.
_DETAIL_LABEL_LEADING_MARKER_RE = re.compile(r"^(?:\[\d+\]|\d+[.)])\s+")
# The trailing variant-suffix group allows more than one char so a roman-numeral suffix like
# "DETAIL-II" (confirmed on a real drawing, 3I/26160A: "BRACKET DETAIL-I" / "BRACKET DETAIL-II")
# matches fully, not just "DETAIL-I" with a dangling unmatched "I".
_DETAIL_LABEL_RE = re.compile(
    r"^(?P<name>[A-Z0-9/&\-]+(?:\s+[A-Z0-9/&\-]+)*)\s+DETAIL(?:\s*-?\s*['\"]?[A-Z0-9]+['\"]?)?$"
)

# Explicit dimension-label aliases that may appear as their own OCR region next to a value.
_DIM_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "od": ("OD", "O.D", "O/D"),
    "id": ("ID", "I.D", "I/D"),
    "thk": ("THK", "TK", "THICKNESS", "T"),
    "l": ("L", "LENGTH", "LG"),
    "pcd": ("PCD",),
    "noh": ("NOH", "NO OF HOLES", "NO. OF HOLES"),
    "hole_dia": ("HOLE DIA", "HOLE", "HOLEO"),  # "HOLEØ" normalizes to "HOLEO" below
}
_ALL_LABEL_TOKENS = {alias: key for key, aliases in _DIM_LABEL_ALIASES.items() for alias in aliases}

# An inline token that already carries its own label, e.g. "OD559", "ID 509", "Ø539".
_INLINE_LABELED_RE = re.compile(
    r"^(OD|ID|THK|TK|PCD|L)\s*[:\-]?\s*(\d+(?:\.\d+)?)$"
)
# PaddleOCR has repeatedly been observed misreading the "Ø" diameter glyph as a bare digit "0"
# (confirmed on two separate real drawings, WO-9347 and WO-9374: "Ø 219" -> "0 219", "Ø 559" ->
# "0 559") - accepted alongside the real symbol. A bare leading "0" is only treated this way
# when followed by a space and a plausible-sized value (3+ digits, i.e. an actual OD/ID callout,
# not an ordinary small measurement that happens to start with a literal "0 ...").
_DIAMETER_RE = re.compile(r"^(?:[ØøΦ]|0(?=\s))\s?(\d{2,}(?:\.\d+)?)$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
# Ceiling for "this unlabeled number is plausibly a wall Thickness" in the Thk/L magnitude
# heuristic below - generous above every real thickness seen (0.5-15mm) while staying well
# under real lengths (125mm+), so it can't itself misclassify a genuine L as Thk.
_THK_MAX_PLAUSIBLE_MM = 50.0
# Two diameters printed this far apart (in Y) are treated as NOT a genuine OD/ID pair for the
# same feature - see the diameter-pairing block in _parse_panel_dimensions for the real-drawing
# evidence behind this (Housing Flange's real pair sits ~13.5pt apart; Sleeve's own real OD sits
# 60+pt from an unrelated second Ø reading).
_DIAMETER_PAIR_MAX_Y_GAP_PT = 30.0

# How far below/right of a label region (in OCR pixel space) counts as "this label's panel".
# Tuned against two different real production drawings, which pull in OPPOSITE directions:
# - 3I/26160A (dense layout): even a 150/150 window still let general-notes fragments and
#   material-grade cells leak in (see _is_noise_text/_looks_like_material_grade below) -
#   wider only made it worse.
# - 3C/25812/MB/25-26 (grid layout, WO-9374): dimensions for a given panel sit BOTH above and
#   below its label and up to ~260px away, since adjacent panel labels can sit as little as
#   ~60px apart - a wider window recovers real OD values here, but at the cost of exactly the
#   contamination the other drawing demonstrated.
# Deliberately kept TIGHT despite that cost: a missed real dimension leaves a panel empty,
# correctly prompting manual confirmation; a wrongly-admitted one looks like real data and is
# the one thing this whole system is built to never produce (see 9347.pdf's "Bellow got
# assigned a real-looking but wrong OD" finding earlier in this drawing family's own history).
# Content-based filtering (_is_noise_text, _looks_like_material_grade, known_descriptions) is
# the real second line of defense, independent of this radius.
PANEL_SEARCH_BAND_PX = 150
PANEL_X_SLACK_PX = 150
# Wider allowance used for any numeric token (see is_numeric_token in _assign_to_panels below) -
# recovers real OD/ID/Thk/L values on a grid-laid-out drawing without reopening the door to
# general notes/material-grade contamination, which free text is still held to the tight band
# above for. Confirmed against WO-9374: Housing Flange's Ø810/Ø559 sit 183-261px from its label,
# and Mid Pipe's own genuine Thk "10" / L "150" sit 219px / 332px away.
_DIAMETER_SEARCH_BAND_PX = 280
_DIAMETER_X_SLACK_PX = 220

# Content-based exclusion, independent of distance: a candidate token is never treated as part
# of a panel's dimensions if it's unmistakably NOT a dimension callout - a long free-text
# sentence (general notes, product-spec paragraphs routinely sit near a panel purely by page
# layout), or a bare word that's actually a BOM-table structural term (DESCRIPTION/MATERIAL/QTY/
# etc. - see bom_table_extractor.HEADER_TOKENS) or title-block field label (QUANTITY, SIZE(OD),
# ITEM CODE...) rather than this component's own measurement. Confirmed necessary directly
# against the same real drawing: even at the full original window, a "BELLOW DETAIL" panel's
# matched region list included the company address and the word "DESCRIPTION" itself.
_NOISE_WORD_COUNT_THRESHOLD = 4
_NOISE_EXACT_TOKENS = {
    "DESCRIPTION", "MATERIAL", "QTY", "QUANTITY", "ITEM", "ITEM NO", "PART NO",
    "SIZE", "SIZE(OD)", "SIZE (OD)", "SIZE(NB)", "SIZE (NB)", "ITEM CODE", "MATERIAL CODE",
    "DRAWING NUMBER", "SCALE", "TITLE", "CUSTOMER", "NO",
}
# A label-style fragment ("GENERAL NOTES:-", "NOTE :-", "Min DFT: 40 TO 50 MICRON") almost
# always carries a colon on these drawings; a real dimension callout never does. Confirmed on
# a real drawing (3I/26160A) where "GENERAL NOTES:-" otherwise leaked into a panel's tokens.
_NOISE_COLON_RE = re.compile(r"[:：]")
# Common MB material-grade patterns ("A 240 TYP 304", "A 240 Gr. 304", "SS 304", "IS 2062 E250
# BR") - these are MATERIAL cells, never a component's own dimension, and have been observed
# leaking into a panel's candidates on a dense sheet purely by proximity to other BOM columns.
_MATERIAL_GRADE_RE = re.compile(
    r"^(A\s?\d{2,4}\s?(TYP|GR)|SS\s?\d{3}|IS\s?\d{3,4}|EN\s?\d{1,3})\b", re.IGNORECASE
)


def _is_noise_text(norm: str) -> bool:
    if norm in _NOISE_EXACT_TOKENS:
        return True
    if _NOISE_COLON_RE.search(norm):
        return True
    if _MATERIAL_GRADE_RE.match(norm):
        return True
    if len(norm.split()) > _NOISE_WORD_COUNT_THRESHOLD:
        return True
    return False


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().upper().replace(".", "").split())


def _y_center(bbox) -> float:
    ys = [p[1] for p in bbox]
    return sum(ys) / len(ys) if ys else 0.0


def _x_center(bbox) -> float:
    xs = [p[0] for p in bbox]
    return sum(xs) / len(xs) if xs else 0.0


def _distance(a_bbox, b_bbox) -> float:
    dx = _x_center(a_bbox) - _x_center(b_bbox)
    dy = _y_center(a_bbox) - _y_center(b_bbox)
    return (dx * dx + dy * dy) ** 0.5


@dataclass
class DetailPanel:
    label_text: str
    component_name: str  # normalized, e.g. "SLEEVE", "END PIPE"
    dimensions: dict = field(default_factory=dict)
    raw_tokens: list = field(default_factory=list)
    confidence: float = 0.0
    needs_confirmation: bool = True


def _find_detail_labels(regions) -> list[tuple]:
    """Returns [(region, component_name)] for every region whose text matches "<NAME> DETAIL"."""
    labels = []
    for region in regions:
        raw = _DETAIL_LABEL_LEADING_MARKER_RE.sub("", (region.text or "").strip())
        norm = _normalize(raw)
        if not norm or "DETAIL" not in norm:
            continue
        m = _DETAIL_LABEL_RE.match(norm)
        if m:
            labels.append((region, m.group("name").strip()))
    return labels


def _assign_to_panels(regions, labels: list[tuple], exclude_texts: set[str] | None = None) -> dict:
    """Nearest-label assignment: every non-label region within PANEL_SEARCH_BAND_PX below (and
    PANEL_X_SLACK_PX across) its closest label goes into that label's panel. A region equidistant
    or out of range of every label is left out entirely - never force-assigned to a guess.

    exclude_texts (normalized, optional) lets the caller pass in text that is DEFINITELY not
    this panel's own dimension data - typically other BOM components' own descriptions, which
    have been observed leaking into a panel's matched region list purely by page proximity on a
    crowded drawing (a different component's name is never that component's own dimension)."""
    exclude_texts = exclude_texts or set()
    label_regions = {id(r) for r, _ in labels}
    panels: dict[int, list] = {id(r): [] for r, _ in labels}
    for region in regions:
        if id(region) in label_regions:
            continue
        text = (region.text or "").strip()
        if not text:
            continue
        norm = _normalize(text)
        if _is_noise_text(norm) or norm in exclude_texts:
            continue
        # Widening this band for plain numbers too (not just diameters) was tried and reverted:
        # it was meant to recover genuine far-away Thk/L values (confirmed real on WO-9374 - Mid
        # Pipe's own "10"/"150" sit 219px/332px from its label) but in practice let MORE
        # unrelated nearby numbers compete for the same few dimension slots, making the
        # magnitude-based guess below worse, not better (Mid Pipe went from one wrong field to
        # two). A token that is itself unmistakably a diameter callout (Ø symbol, or its
        # confirmed OCR misread) stays on the wide band - that one's distinctive enough that
        # widening the search for it doesn't flood it with ambiguous plain-number competitors.
        is_diameter_token = bool(_DIAMETER_RE.match(text))
        y_limit = _DIAMETER_SEARCH_BAND_PX if is_diameter_token else PANEL_SEARCH_BAND_PX
        x_limit = _DIAMETER_X_SLACK_PX if is_diameter_token else PANEL_X_SLACK_PX
        best_label = None
        best_dist = None
        for label_region, _name in labels:
            dy = abs(_y_center(region.bbox) - _y_center(label_region.bbox))
            dx = abs(_x_center(region.bbox) - _x_center(label_region.bbox))
            if dy > y_limit or dx > x_limit:
                continue
            dist = _distance(region.bbox, label_region.bbox)
            if best_dist is None or dist < best_dist:
                best_dist, best_label = dist, label_region
        if best_label is not None:
            panels[id(best_label)].append(region)
    return panels


def _parse_panel_dimensions(panel_regions: list) -> tuple[dict, list[str], float]:
    dimensions: dict = {}
    raw_tokens: list[str] = []
    confidences: list[float] = []
    label_tokens: list = []
    diameter_values: list[tuple] = []  # (value_str, region)
    plain_values: list[tuple] = []

    for region in panel_regions:
        text = (region.text or "").strip()
        norm = _normalize(text)
        if not norm:
            continue
        raw_tokens.append(text)
        confidences.append(getattr(region, "confidence", 0.0) or 0.0)

        inline = _INLINE_LABELED_RE.match(norm.replace(" ", ""))
        if inline:
            key = _ALL_LABEL_TOKENS.get(inline.group(1), inline.group(1).lower())
            dimensions.setdefault(key, inline.group(2))
            continue
        if norm in _ALL_LABEL_TOKENS:
            label_tokens.append((region, _ALL_LABEL_TOKENS[norm]))
            continue
        dia = _DIAMETER_RE.match(text.strip())
        if dia:
            diameter_values.append((dia.group(1), region))
            continue
        if _PLAIN_NUMBER_RE.match(text.strip()):
            plain_values.append((text.strip(), region))

    # Pair explicit labels (OD/ID/THK/L/...) with the nearest still-unused value region.
    used_value_ids: set = set()
    for label_region, key in label_tokens:
        if key in dimensions:
            continue
        candidates = [
            (val, region) for val, region in plain_values
            if id(region) not in used_value_ids
        ]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda vr: _distance(vr[1].bbox, label_region.bbox))
        dimensions[key] = nearest[0]
        used_value_ids.add(id(nearest[1]))

    # Ø values -> od, then id (by descending size, the usual OD-before-ID drawing convention) -
    # this IS a reliable, well-evidenced convention (confirmed on two real drawings: every
    # diameter-shaped OCR token on these sheets was a genuine OD/ID of the component it was
    # nearest to). A third+ diameter is ambiguous (which feature is it?) and is left out rather
    # than guessed.
    remaining_diameters = [(v, r) for v, r in diameter_values]
    remaining_diameters.sort(key=lambda vr: -float(vr[0]))
    if len(remaining_diameters) >= 2:
        gap = abs(_y_center(remaining_diameters[0][1].bbox) - _y_center(remaining_diameters[1][1].bbox))
        if gap > _DIAMETER_PAIR_MAX_Y_GAP_PT:
            # Two diameters that genuinely both belong to the SAME feature (a real OD/ID pair)
            # are printed close together on these drawings (confirmed on a real drawing: Housing
            # Flange's own OD=810/ID=559 sit under 15pt apart) - two diameters this far apart are
            # far more likely two UNRELATED values that each merely landed in this panel's
            # candidate set (confirmed on a real drawing: Sleeve's own OD=509 sits 60+pt from a
            # second, unrelated Ø reading nowhere near it) than a genuine pair for one feature.
            # Keep only whichever one sits closest to this panel's OTHER already-accepted values
            # (it belongs to the same cluster the diameter pairing above can't see) - that one
            # real diameter, not a fabricated guess at which of the two is "right".
            other_y = [_y_center(region.bbox) for _val, region in plain_values]
            if other_y:
                centroid_y = sum(other_y) / len(other_y)
                remaining_diameters = [min(
                    remaining_diameters[:2], key=lambda vr: abs(_y_center(vr[1].bbox) - centroid_y)
                )]
            else:
                remaining_diameters = remaining_diameters[:1]
    for value, _region in remaining_diameters[:2]:
        key = "od" if "od" not in dimensions else ("id" if "id" not in dimensions else None)
        if key:
            dimensions[key] = value

    # Best-effort fallback for leftover unlabeled plain numbers, by explicit request: unlike
    # OD/ID (which have a reliable Ø marker), a bare Thk/L number has no textual signal on these
    # drawings - this is a genuine guess, not a confident reading, and is LOWER CONFIDENCE than
    # everything above. Classified by MAGNITUDE, not number format (a previous "decimal -> Thk,
    # integer -> L" version missed Mid Pipe's real Thk entirely, since it's a plain integer "10"
    # not a decimal) - wall thickness is always much smaller than overall length for these
    # cylindrical components, confirmed on every real example seen (Sleeve Thk 1.5-9.5 vs L
    # 150-175; Mid/End Pipe Thk 10 vs L 125-150): the smallest remaining candidate under
    # _THK_MAX_PLAUSIBLE_MM is Thk. L is the LARGEST remaining candidate, not merely the next-
    # smallest - confirmed necessary on a real drawing (Shroud): a third, unrelated leftover
    # number can land between Thk and the real L in sorted order, and "next-smallest" would pick
    # that unrelated middle value over the real (larger) L. Always surfaced alongside its raw
    # source token so a reviewer can see what it was guessed from, and the caller
    # (extract_detail_dimensions) always marks the whole panel needs_confirmation=True regardless
    # - this is pre-filling the edit box, never a substitute for checking it.
    leftover_plain = sorted(
        ((float(v), v, r) for v, r in plain_values if id(r) not in used_value_ids),
        key=lambda t: t[0],
    )
    if leftover_plain and leftover_plain[0][0] <= _THK_MAX_PLAUSIBLE_MM and "thk" not in dimensions:
        dimensions["thk"] = leftover_plain[0][1]
        leftover_plain = leftover_plain[1:]
    if leftover_plain and "l" not in dimensions:
        dimensions["l"] = max(leftover_plain, key=lambda t: t[0])[1]

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return dimensions, raw_tokens, avg_conf


def extract_detail_dimensions(regions, known_descriptions: list[str] | None = None) -> list[DetailPanel]:
    """`regions` is a list of app.services.paddle_ocr.OcrRegion (text, confidence, bbox).
    Returns one DetailPanel per recognized "<NAME> DETAIL" label found on the page, with
    whatever dimensions could be confidently parsed nearby. Returns [] when no such panel is
    found - never fabricates a panel or a dimension that isn't backed by an OCR token.

    known_descriptions (optional) is the drawing's own BOM row descriptions (from
    bom_table_extractor) - excluded from every panel's candidate tokens, since any of them
    appearing inside ANOTHER component's panel window is page-layout noise, not that
    component's own dimension (see _assign_to_panels's exclude_texts docstring)."""
    if not regions:
        return []
    labels = _find_detail_labels(regions)
    if not labels:
        return []
    exclude_texts = {_normalize(d) for d in (known_descriptions or [])}
    panel_regions_by_label = _assign_to_panels(regions, labels, exclude_texts=exclude_texts)

    results: list[DetailPanel] = []
    for label_region, component_name in labels:
        panel_regions = panel_regions_by_label.get(id(label_region), [])
        dimensions, raw_tokens, confidence = _parse_panel_dimensions(panel_regions)
        results.append(DetailPanel(
            label_text=label_region.text.strip(),
            component_name=component_name,
            dimensions=dimensions,
            raw_tokens=raw_tokens,
            confidence=confidence,
            # Always True, even when dimensions were found: this is heuristic pixel-proximity
            # evidence, not a verified reading - every value it produces needs a human to check
            # it against the actual drawing before it's trusted (see format_size_text's "size"
            # passthrough and the editable Size field in the Components tab).
            needs_confirmation=True,
        ))
    return results


def _pdf_block_text(block: dict) -> str:
    return "".join(
        "".join(s.get("text", "") for s in line.get("spans", [])) for line in block.get("lines", [])
    ).strip()


# How far outside a label's OWN bounding-box Y-range a value may still sit and be considered
# that label's own panel content. Confirmed against the real WO 9374 drawing: every genuine
# dimension value for a panel sits within ~10pt of that panel's own label bbox's y0/y1 (the
# label and its detail-view box are roughly the same height) - a handful sit just outside by
# single digits (e.g. a diameter callout drawn right at the box's edge).
_PDF_PANEL_Y_MARGIN_PT = 20.0
# How far to the right of a label's own left edge (x0) a value may sit and still be considered
# that label's own panel content - the Y-range check alone isn't enough, since an UNRELATED
# generic, unnamed detail callout elsewhere on the sheet (a weld-detail "DETAIL-'A'" etc., never
# itself recognized as a named panel) can still fall inside a named label's Y-range purely by
# coincidence while sitting much further across the page. Confirmed against the real WO 9374
# drawing: every genuine value for a named panel sits within ~120pt to the right of its own
# label's x0 (never to its left), while that unrelated weld-detail noise sits 230pt+ away.
_PDF_PANEL_X_OFFSET_PT = (-10.0, 160.0)


def extract_detail_dimensions_from_pdf_blocks(
    blocks: list[dict], known_descriptions: list[str] | None = None,
) -> list[DetailPanel]:
    """Same detection target as extract_detail_dimensions (one DetailPanel per "<NAME> DETAIL"
    label, with whatever OD/ID/Thk/L dimensions can be confidently read nearby) but sourced from
    PyMuPDF's own `page.get_text("dict")["blocks"]` - the PDF's embedded text layer - instead of
    noisy image-region OCR.

    Exists because ordinary nearest-centroid assignment (_assign_to_panels, tuned for OCR-pixel
    geometry where a panel's values cluster tightly around its own label) turned out to actively
    MISASSIGN values on this drawing family: WO 9374 lays its detail panels out in vertical
    lanes, where a label sits at its lane's own left edge and its OWN dimension values sit well
    to the right of it (offset 45-250pt) - meanwhile a DIFFERENT lane's label can easily be
    geometrically CLOSER in raw (x, y) distance than that value's own label is (confirmed: this
    nearest-centroid logic sent Sleeve's own L=150 to the adjacent Bellow panel instead).

    Assignment here is containment-based instead: a value is assigned to the one label whose own
    bounding-box Y-RANGE (plus _PDF_PANEL_Y_MARGIN_PT) it falls inside - confirmed to cleanly
    separate every real value on the real WO 9374 drawing into its correct panel, since each
    lane's own label and its detail-view box occupy essentially the same vertical span. X is
    used only to break a tie when a value's Y literally falls inside two labels' ranges at once
    (two lanes' panels sitting at the same height)."""
    if not blocks:
        return []
    labels: list[tuple[str, tuple]] = []
    for block in blocks:
        text = _pdf_block_text(block)
        raw = _DETAIL_LABEL_LEADING_MARKER_RE.sub("", text)
        norm = _normalize(raw)
        if not norm or "DETAIL" not in norm:
            continue
        m = _DETAIL_LABEL_RE.match(norm)
        if m:
            labels.append((m.group("name").strip(), tuple(block["bbox"]), block))
    if not labels:
        return []

    exclude_texts = {_normalize(d) for d in (known_descriptions or [])}
    label_block_ids = {id(b) for _name, _bbox, b in labels}

    panel_blocks: dict[int, list[dict]] = {id(b): [] for _name, _bbox, b in labels}
    for block in blocks:
        if id(block) in label_block_ids:
            continue
        text = _pdf_block_text(block)
        if not text:
            continue
        norm = _normalize(text)
        if _is_noise_text(norm) or norm in exclude_texts:
            continue
        x0, y0, x1, y1 = block["bbox"]
        # Drawings carry their own vertical grid-reference numbers/letters along the page
        # border (e.g. "8 7 6 5 4") - PyMuPDF's own block-join sometimes concatenates a run of
        # these one-char-per-line rotated labels into what READS like a plain number (e.g. "65"
        # from lines "6" and "5"), which would otherwise be mistaken for a genuine Thk/L value.
        # That join is the real tell: it only happens across MULTIPLE separate text lines within
        # one block, which a genuine single-line dimension value never has - checking tall-vs-
        # wide bbox shape alone (an earlier version of this check) wrongly excluded ordinary
        # short single-digit values too (e.g. Shroud's own real Thk="2" block, naturally narrow
        # for a one-character line), confirmed on the real WO 9374 drawing.
        if len(block.get("lines", [])) > 1:
            continue
        cy = (y0 + y1) / 2.0
        cx = (x0 + x1) / 2.0
        containing = [
            (name, bbox, b) for name, bbox, b in labels
            if bbox[1] - _PDF_PANEL_Y_MARGIN_PT <= cy <= bbox[3] + _PDF_PANEL_Y_MARGIN_PT
            and _PDF_PANEL_X_OFFSET_PT[0] <= cx - bbox[0] <= _PDF_PANEL_X_OFFSET_PT[1]
        ]
        if not containing:
            continue
        if len(containing) > 1:
            # Two lanes' labels both claim this Y - break the tie by nearest label X (the value
            # is on one lane's side or the other, never equidistant in practice on a real sheet).
            containing.sort(key=lambda t: abs((t[1][0] + t[1][2]) / 2.0 - cx))
        _name, _bbox, label_block = containing[0]
        panel_blocks[id(label_block)].append(block)

    class _FakeRegion:
        __slots__ = ("text", "confidence", "bbox")

        def __init__(self, text: str, bbox: tuple):
            self.text = text
            self.confidence = 1.0
            x0, y0, x1, y1 = bbox
            self.bbox = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    results: list[DetailPanel] = []
    for name, _bbox, label_block in labels:
        regions = [_FakeRegion(_pdf_block_text(b), tuple(b["bbox"])) for b in panel_blocks[id(label_block)]]
        dimensions, raw_tokens, confidence = _parse_panel_dimensions(regions)
        results.append(DetailPanel(
            label_text=_pdf_block_text(label_block),
            component_name=name,
            dimensions=dimensions,
            raw_tokens=raw_tokens,
            confidence=confidence,
            # Still True: this is proximity-based evidence (containment in the label's own
            # y-range), not a verified reading - same convention as extract_detail_dimensions.
            needs_confirmation=True,
        ))
    return results


_HOLES_PATTERN_RE = re.compile(
    r"[ØøΦ]\s?(?P<hole_dia>\d+(?:\.\d+)?)\s*[xX×]\s*0?(?P<noh>\d+)\s*NO\.?\s*OF\s*HOLES?"
    r".*?PCD\s?(?P<pcd>\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)


def extract_shared_view_flange_bolt_circle(pdf_path: str, page_number: int) -> DetailPanel | None:
    """Best-effort recovery of a flange's bolt-circle dimensions (OD, bore/ID, PCD, hole
    diameter and count) from a drawing family that has NO per-component "<NAME> DETAIL" panels
    at all (confirmed on a real drawing, WO 9347 - a "Single Expansion Joint" style MB drawing:
    its BOM table carries no SIZE column, same as the WO 9374 family extract_detail_dimensions
    serves, but unlike that family there is no labeled detail panel for ANY component either -
    every dimension lives directly on the one shared assembly/section view, with no text tying
    a given callout to a specific BOM item).

    Deliberately narrow in scope: this looks for exactly ONE recognizable pattern - a cluster of
    plain Ø-prefixed diameter values sitting near a "ØNN x MM NO OF HOLES ... PCD PPP" callout,
    which on every MB drawing seen so far is the end flange's own bolting detail (an unlabeled
    DETAIL panel never attempts to recover anything else; see module docstring's conservative
    philosophy). The caller is responsible for deciding WHICH component this belongs to (see
    app.providers.deterministic_provider.analyze: a bare "FLANGE" item is assumed over
    "SLEEVE FLANGE" when the drawing itself gives no way to tell them apart) and for keeping
    `needs_confirmation=True` (always set here) visible to a reviewer - this is a geometric
    best-effort guess, confirmed correct on WO 9347 by direct visual inspection of the rendered
    drawing, never a verified reading.

    Returns None (never raises) if the holes/PCD callout isn't found at all - a drawing with no
    such callout gets no guess, not a wrong one."""
    if fitz is None:
        return None
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        page_dict = page.get_text("dict")
        doc.close()
    except Exception:
        return None

    blocks = [b for b in page_dict.get("blocks", []) if b.get("lines")]
    if not blocks:
        return None

    holes_block = None
    holes_match = None
    for block in blocks:
        text = _pdf_block_text(block)
        m = _HOLES_PATTERN_RE.search(text)
        if m:
            holes_block = block
            holes_match = m
            break
    if holes_block is None:
        return None

    # Bare Ø-prefixed diameter values sitting in a single-line block near the holes callout (the
    # bolt-circle's own OD/bore stack, e.g. "Ø219", "Ø240", "Ø283 ± 3", "Ø343" on WO 9347) -
    # same containment-by-proximity approach as extract_detail_dimensions_from_pdf_blocks, bound
    # tightly since this is a single unlabeled cluster, not a whole lane.
    hx0, hy0, hx1, hy1 = holes_block["bbox"]
    diameters: list[tuple[float, dict]] = []
    for block in blocks:
        if block is holes_block or len(block.get("lines", [])) > 1:
            continue
        text = _pdf_block_text(block).strip()
        m = re.match(r"^[ØøΦ]\s?(\d+(?:\.\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?$", text)
        if not m:
            continue
        bx0, by0, bx1, by1 = block["bbox"]
        cy = (by0 + by1) / 2.0
        if hy0 - _PDF_PANEL_Y_MARGIN_PT * 4 <= cy <= hy1 + _PDF_PANEL_Y_MARGIN_PT * 4:
            diameters.append((float(m.group(1)), block))
    if not diameters:
        return None

    diameters.sort(key=lambda t: t[0])
    dimensions = {
        "id": f"{diameters[0][0]:g}",
        "od": f"{diameters[-1][0]:g}",
        "pcd": holes_match.group("pcd"),
        "hole_dia": holes_match.group("hole_dia"),
        "noh": holes_match.group("noh"),
    }
    # Middle values (e.g. Ø240, Ø283±3 between the Ø219 bore and Ø343 OD on WO 9347) have no
    # confirmed engineering role (raised-face diameter, recess, etc. all plausible) - kept as
    # generic dim_N keys rather than guessed at, same convention as _parse_panel_dimensions uses
    # for any value it can't confidently label.
    for i, (value, _block) in enumerate(diameters[1:-1], start=1):
        dimensions[f"dim_{i}"] = f"{value:g}"

    raw_tokens = [_pdf_block_text(b) for _v, b in diameters] + [_pdf_block_text(holes_block)]
    return DetailPanel(
        label_text=_pdf_block_text(holes_block),
        component_name="",  # caller assigns this - see docstring
        dimensions=dimensions,
        raw_tokens=raw_tokens,
        confidence=0.5,
        needs_confirmation=True,
    )


def match_panel_to_description(description: str, panels: list[DetailPanel]) -> DetailPanel | None:
    """Matches a BOM component's description (e.g. "Housing flange", "End pipe") to a detected
    DETAIL panel by normalized substring match. No fuzzy/AI matching - either the panel's
    component name is a close textual match or it is left unmatched for manual review."""
    norm_desc = _normalize(description)
    if not norm_desc:
        return None
    best = None
    for panel in panels:
        panel_name = _normalize(panel.component_name)
        if not panel_name:
            continue
        if panel_name == norm_desc or panel_name in norm_desc or norm_desc in panel_name:
            if best is None or len(panel_name) > len(_normalize(best.component_name)):
                best = panel
    return best
