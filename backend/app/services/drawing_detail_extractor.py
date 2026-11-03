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
# Wider allowance used ONLY for tokens that already look unmistakably like a diameter callout
# (see is_diameter_token in _assign_to_panels below) - recovers real OD/ID values on a
# grid-laid-out drawing (confirmed against WO-9374: Housing Flange's own Ø810/Ø559 sit 183-261px
# from its label) without reopening the door to general notes/material-grade contamination,
# which plain numbers and free text are still held to the tight band above for.
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
        # A token that is itself unmistakably a diameter callout (real Ø symbol, or the
        # confirmed OCR misread of it) is distinctive enough - unlike a bare plain number or
        # free text - that it's safe to look further for it than for anything else: real
        # OD/ID values on a grid-laid-out drawing (WO-9374) have been confirmed up to ~260px
        # from their panel's own label, well past where plain numbers/notes text would be
        # trusted. Anything else keeps the tight default band.
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


def _parse_panel_dimensions(panel_regions: list, label_region=None) -> tuple[dict, list[str], float]:
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
    for value, _region in remaining_diameters[:2]:
        key = "od" if "od" not in dimensions else ("id" if "id" not in dimensions else None)
        if key:
            dimensions[key] = value

    # Best-effort fallback for leftover unlabeled plain numbers, by explicit request: unlike
    # OD/ID (which have a reliable Ø marker), a bare Thk/L number has no such signal on these
    # drawings - this is a genuine guess, not a confident reading, and is LOWER CONFIDENCE than
    # everything above. Picks the candidate(s) nearest the panel's own label (the only ordering
    # principle available without real dimension-line geometry) rather than panel_regions'
    # incidental scan order, which at least maximizes the chance of being right. Always surfaced
    # alongside its raw source token so a reviewer can see what it was guessed from, and the
    # caller (extract_detail_dimensions) always marks the whole panel needs_confirmation=True
    # regardless - this is pre-filling the edit box, never a substitute for checking it.
    leftover_plain = [(v, r) for v, r in plain_values if id(r) not in used_value_ids]
    if label_region is not None:
        leftover_plain.sort(key=lambda vr: _distance(vr[1].bbox, label_region.bbox))
    for value, _region in leftover_plain:
        fv = float(value)
        if "." in value and fv < 20 and "thk" not in dimensions:
            dimensions["thk"] = value
        elif "l" not in dimensions and fv == int(fv) and fv >= 1:
            dimensions["l"] = value

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
        dimensions, raw_tokens, confidence = _parse_panel_dimensions(panel_regions, label_region)
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
