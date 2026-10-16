from __future__ import annotations

"""Reference BOM table detection: a heuristic over raw OCR regions (app.services.paddle_ocr)
that flags when a page's text layout looks like a printed Bill-of-Materials table (the kind of
grid many mechanical drawings carry in a corner, with an ITEM/QTY/PART NO/DESCRIPTION header
row). This is DELIBERATELY separate from bom_candidate_service's geometry-derived candidate
BOM: a detected reference table is read-only evidence for comparison, never written into
Component rows and never auto-reconciled with them.

Kept intentionally simple: it looks for several header-like tokens whose OCR regions sit at
similar y-coordinates (a row), and estimates how many further rows sit below them. It does not
attempt real table-structure parsing (column splitting, cell OCR correction, etc.) - that would
require far more OCR fidelity than a heuristic should assume. It fails toward NOT detecting
(never fabricates a table that is not visually there) rather than over-eagerly flagging one.
"""

from dataclasses import dataclass

# Header tokens that, in combination, are strong evidence of a BOM table's header row. A single
# hit is not enough (e.g. "QTY" might appear in a lone dimension callout); requiring several
# distinct tokens roughly aligned in a row is a much more reliable signal.
HEADER_TOKENS = {
    "ITEM": ("ITEM", "ITEM NO", "ITEM NO.", "NO."),
    "QTY": ("QTY", "QUANTITY", "QTY.", "QTY REQD"),
    "PART_NO": ("PART NO", "PART NUMBER", "P/N", "PART NO."),
    "DESCRIPTION": ("DESCRIPTION", "DESC"),
    "MATERIAL": ("MATERIAL", "MATL"),
}

MIN_DISTINCT_HEADER_TOKENS = 3
# Header cells printed on one physical table row should have bbox y-centers within this many
# pixels of each other (generous enough to tolerate OCR's slightly uneven box heights).
HEADER_ROW_BAND_PX = 40
# How far below the header row to look for further table rows.
BODY_SEARCH_BAND_PX = 600
# Rows of body text are grouped by rounding their y-center to this bucket size.
ROW_BUCKET_PX = 18


def _normalize(text: str) -> str:
    return " ".join(text.strip().upper().replace(".", " ").split())


def _bbox_y_center(bbox: list[list[float]]) -> float:
    ys = [p[1] for p in bbox]
    return sum(ys) / len(ys) if ys else 0.0


def _bbox_x_center(bbox: list[list[float]]) -> float:
    xs = [p[0] for p in bbox]
    return sum(xs) / len(xs) if xs else 0.0


def _bbox_union(bboxes: list[list[list[float]]]) -> dict:
    xs = [p[0] for b in bboxes for p in b]
    ys = [p[1] for b in bboxes for p in b]
    if not xs or not ys:
        return {}
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


@dataclass
class ReferenceBomDetection:
    detected: bool
    page_number: int
    matched_headers: list[str]
    bbox: dict
    raw_text: str
    row_count_estimate: int


def detect_reference_bom_table(regions, page_number: int = 1) -> ReferenceBomDetection | None:
    """`regions` is a list of app.services.paddle_ocr.OcrRegion (or any object with .text,
    .confidence, .bbox). Returns None when no table-like header row is found; otherwise a
    ReferenceBomDetection with the matched header tokens, a bounding box covering the header
    row, the raw OCR text of the detected table area, and a best-effort row count estimate."""
    if not regions:
        return None

    hits: dict[str, tuple] = {}  # token-category -> (region, normalized text)
    for region in regions:
        norm = _normalize(region.text or "")
        if not norm:
            continue
        for category, aliases in HEADER_TOKENS.items():
            if category in hits:
                continue
            if any(norm == alias or norm.startswith(alias) for alias in aliases):
                hits[category] = region

    if len(hits) < MIN_DISTINCT_HEADER_TOKENS:
        return None

    header_regions = list(hits.values())
    y_centers = [_bbox_y_center(r.bbox) for r in header_regions]
    if max(y_centers) - min(y_centers) > HEADER_ROW_BAND_PX:
        # Matched tokens are scattered around the page (e.g. a stray "MATERIAL: Aluminum"
        # title-block callout + an unrelated "QTY" elsewhere) rather than one header row.
        # Keep only the tightest cluster of tokens and re-check the threshold.
        y_centers_sorted = sorted(zip(y_centers, hits.items()), key=lambda t: t[0])
        best_cluster: list = []
        for i in range(len(y_centers_sorted)):
            cluster = [y_centers_sorted[i]]
            for j in range(i + 1, len(y_centers_sorted)):
                if y_centers_sorted[j][0] - cluster[0][0] <= HEADER_ROW_BAND_PX:
                    cluster.append(y_centers_sorted[j])
            if len(cluster) > len(best_cluster):
                best_cluster = cluster
        if len(best_cluster) < MIN_DISTINCT_HEADER_TOKENS:
            return None
        hits = {k: v for _, (k, v) in best_cluster}
        header_regions = list(hits.values())
        y_centers = [_bbox_y_center(r.bbox) for r in header_regions]

    header_y = sum(y_centers) / len(y_centers)

    # Estimate body rows: regions below the header band, within a reasonable x-range overlap
    # with the header row's horizontal span, grouped into row buckets.
    header_bbox = _bbox_union([r.bbox for r in header_regions])
    body_regions = [
        r for r in regions
        if header_y + 5 < _bbox_y_center(r.bbox) <= header_y + BODY_SEARCH_BAND_PX
        and header_bbox.get("x0", 0) - 20 <= _bbox_x_center(r.bbox) <= header_bbox.get("x1", 1e9) + 20
    ]
    row_buckets = {round(_bbox_y_center(r.bbox) / ROW_BUCKET_PX) for r in body_regions}

    all_table_regions = header_regions + body_regions
    all_table_regions.sort(key=lambda r: (_bbox_y_center(r.bbox), _bbox_x_center(r.bbox)))
    raw_text = "\n".join(r.text for r in all_table_regions if r.text)

    return ReferenceBomDetection(
        detected=True,
        page_number=page_number,
        matched_headers=sorted(hits.keys()),
        bbox=_bbox_union([r.bbox for r in all_table_regions]),
        raw_text=raw_text,
        row_count_estimate=len(row_buckets),
    )


def compute_discrepancy(reference_row_count: int, candidate_component_count: int,
                         reference_text: str, candidate_descriptions: list[str],
                         candidate_part_numbers: list[str]) -> dict:
    """Read-only comparison between a detected reference BOM table and the independently
    generated candidate Component rows for the same Analysis. Never reconciles anything -
    purely reports counts and simple substring presence mismatches for a human to review."""
    ref_norm = _normalize(reference_text)
    desc_only_in_reference = []
    for desc in candidate_descriptions:
        token = _normalize(desc)
        if token and token not in ref_norm:
            desc_only_in_reference.append(desc)

    pn_not_in_reference = [pn for pn in candidate_part_numbers if pn and pn.upper() not in ref_norm]

    return {
        "reference_row_count_estimate": reference_row_count,
        "candidate_component_count": candidate_component_count,
        "count_mismatch": reference_row_count != candidate_component_count,
        "candidate_descriptions_not_found_in_reference_text": desc_only_in_reference,
        "candidate_part_numbers_not_found_in_reference_text": pn_not_in_reference,
    }
