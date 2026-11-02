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
# "DETAIL-A" weld/section callout (no component name) is excluded by construction.
_DETAIL_LABEL_RE = re.compile(
    r"^(?P<name>[A-Z0-9/&\-]+(?:\s+[A-Z0-9/&\-]+)*)\s+DETAIL(?:\s*-?\s*['\"]?[A-Z0-9]['\"]?)?$"
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
_DIAMETER_RE = re.compile(r"^[ØøΦ]\s?(\d+(?:\.\d+)?)$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")

# How far below/right of a label region (in OCR pixel space) counts as "this label's panel".
# MB drawing panels in the observed layout run roughly 250-400px tall; 450 gives headroom
# without routinely bleeding into the next panel down.
PANEL_SEARCH_BAND_PX = 450
PANEL_X_SLACK_PX = 350


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
        norm = _normalize(region.text or "")
        if not norm or "DETAIL" not in norm:
            continue
        m = _DETAIL_LABEL_RE.match(norm)
        if m:
            labels.append((region, m.group("name").strip()))
    return labels


def _assign_to_panels(regions, labels: list[tuple]) -> dict:
    """Nearest-label assignment: every non-label region within PANEL_SEARCH_BAND_PX below (and
    PANEL_X_SLACK_PX across) its closest label goes into that label's panel. A region equidistant
    or out of range of every label is left out entirely - never force-assigned to a guess."""
    label_regions = {id(r) for r, _ in labels}
    panels: dict[int, list] = {id(r): [] for r, _ in labels}
    for region in regions:
        if id(region) in label_regions:
            continue
        text = (region.text or "").strip()
        if not text:
            continue
        best_label = None
        best_dist = None
        for label_region, _name in labels:
            dy = _y_center(region.bbox) - _y_center(label_region.bbox)
            dx = abs(_x_center(region.bbox) - _x_center(label_region.bbox))
            if dy < -5 or dy > PANEL_SEARCH_BAND_PX or dx > PANEL_X_SLACK_PX:
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
    value_tokens: list = []
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
            value_tokens.append((text.strip(), region))

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

    # Convention-based fallback for anything left unlabeled: Ø values -> od, then id (by
    # descending size, the usual OD-before-ID drawing convention); a single remaining small
    # decimal -> thk; one remaining plain integer -> l. Everything else stays generic (dim_N)
    # so it is still visible to a reviewer instead of being dropped.
    remaining_diameters = [(v, r) for v, r in diameter_values]
    remaining_diameters.sort(key=lambda vr: -float(vr[0]))
    for value, _region in remaining_diameters:
        if "od" not in dimensions:
            dimensions["od"] = value
        elif "id" not in dimensions:
            dimensions["id"] = value
        else:
            dimensions.setdefault(f"dim_{len(dimensions) + 1}", value)

    leftover_plain = [
        (v, r) for v, r in plain_values if id(r) not in used_value_ids
    ]
    for value, _region in leftover_plain:
        fv = float(value)
        if "." in value and fv < 10 and "thk" not in dimensions:
            dimensions["thk"] = value
        elif "l" not in dimensions and fv == int(fv) and fv >= 1:
            dimensions["l"] = value
        else:
            dimensions[f"dim_{len(dimensions) + 1}"] = value

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return dimensions, raw_tokens, avg_conf


def extract_detail_dimensions(regions) -> list[DetailPanel]:
    """`regions` is a list of app.services.paddle_ocr.OcrRegion (text, confidence, bbox).
    Returns one DetailPanel per recognized "<NAME> DETAIL" label found on the page, with
    whatever dimensions could be confidently parsed nearby. Returns [] when no such panel is
    found - never fabricates a panel or a dimension that isn't backed by an OCR token."""
    if not regions:
        return []
    labels = _find_detail_labels(regions)
    if not labels:
        return []
    panel_regions_by_label = _assign_to_panels(regions, labels)

    results: list[DetailPanel] = []
    for label_region, component_name in labels:
        panel_regions = panel_regions_by_label.get(id(label_region), [])
        dimensions, raw_tokens, confidence = _parse_panel_dimensions(panel_regions)
        has_generic_only = dimensions and all(k.startswith("dim_") for k in dimensions)
        results.append(DetailPanel(
            label_text=label_region.text.strip(),
            component_name=component_name,
            dimensions=dimensions,
            raw_tokens=raw_tokens,
            confidence=confidence,
            needs_confirmation=(not dimensions) or has_generic_only,
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
