from __future__ import annotations

"""Deterministic BOM-table ROW extraction from raw OCR regions.

app.services.reference_bom_service already detects WHETHER a page's OCR regions look like a
BOM table (header-token clustering) and keeps that detection read-only, by design, for
reference/comparison purposes - it deliberately never emits structured per-row data. This
module is the row-and-column extraction step that actually turns a detected table into
structured rows (item/qty/part_no/description/material), which app.providers.deterministic_
provider needs to produce real ComponentCandidate entries without ever calling a generative
model. It is a separate module (not a change to reference_bom_service) so the existing,
already-tested detection/comparison behavior there is untouched.

Kept intentionally conservative: if the header row can't be confidently identified, or a body
row can't be matched to a column, nothing is fabricated - the row (or the whole table) is
simply left out, and the caller is expected to flag that in missing_info/ambiguities rather
than inventing a component.
"""

from dataclasses import dataclass, field

# Same token families as reference_bom_service.HEADER_TOKENS, but this module also needs each
# header hit's own x-range (to assign body-row cells to the right column), so it keeps its own
# copy rather than importing private internals from that module.
HEADER_TOKENS = {
    "item_no": ("ITEM", "ITEM NO", "ITEM NO.", "SL NO", "SL.NO", "SL NO.", "NO."),
    "qty": ("QTY", "QUANTITY", "QTY.", "QTY REQD", "WT/QTY", "WT QTY"),
    "part_no": ("PART NO", "PART NUMBER", "P/N", "PART NO."),
    "description": ("DESCRIPTION", "DESC", "MTL SPEC", "MATERIAL SPEC"),
    "material": ("MATERIAL", "MATL"),
    "size": ("SIZE",),
}

MIN_DISTINCT_HEADER_TOKENS = 3
HEADER_ROW_BAND_PX = 40
BODY_SEARCH_BAND_PX = 1200
ROW_BUCKET_PX = 18
# A body-cell is assigned to a header column only if its x-center falls within the column's
# own span, expanded by this many pixels on each side (OCR boxes rarely align perfectly).
COLUMN_SLACK_PX = 25


@dataclass
class BomRow:
    item_no: str = ""
    qty: str = ""
    part_no: str = ""
    description: str = ""
    material: str = ""
    size: str = ""
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class BomTableExtraction:
    header_columns: list[str] = field(default_factory=list)
    rows: list[BomRow] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.strip().upper().replace(".", " ").split())


def _y_center(bbox) -> float:
    ys = [p[1] for p in bbox]
    return sum(ys) / len(ys) if ys else 0.0


def _x_center(bbox) -> float:
    xs = [p[0] for p in bbox]
    return sum(xs) / len(xs) if xs else 0.0


def _x_span(bbox) -> tuple[float, float]:
    xs = [p[0] for p in bbox]
    return (min(xs), max(xs)) if xs else (0.0, 0.0)


def extract_bom_table(regions) -> BomTableExtraction | None:
    """`regions` is a list of app.services.paddle_ocr.OcrRegion (text, confidence, bbox).
    Returns None when no table header can be confidently identified; otherwise the header
    columns found and every body row successfully assembled beneath them."""
    if not regions:
        return None

    hits: dict[str, object] = {}
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
    y_centers = [_y_center(r.bbox) for r in header_regions]
    if max(y_centers) - min(y_centers) > HEADER_ROW_BAND_PX:
        # Same "tightest cluster" fallback as reference_bom_service.detect_reference_bom_table.
        sorted_hits = sorted(hits.items(), key=lambda kv: _y_center(kv[1].bbox))
        best_cluster: list = []
        for i in range(len(sorted_hits)):
            cluster = [sorted_hits[i]]
            base_y = _y_center(sorted_hits[i][1].bbox)
            for j in range(i + 1, len(sorted_hits)):
                if _y_center(sorted_hits[j][1].bbox) - base_y <= HEADER_ROW_BAND_PX:
                    cluster.append(sorted_hits[j])
            if len(cluster) > len(best_cluster):
                best_cluster = cluster
        if len(best_cluster) < MIN_DISTINCT_HEADER_TOKENS:
            return None
        hits = dict(best_cluster)
        header_regions = list(hits.values())
        y_centers = [_y_center(r.bbox) for r in header_regions]

    header_y = sum(y_centers) / len(y_centers)
    columns = {cat: _x_span(region.bbox) for cat, region in hits.items()}
    # Order columns left-to-right so a body row's cells are matched in natural reading order.
    ordered_columns = sorted(columns.items(), key=lambda kv: kv[1][0])

    body_regions = [
        r for r in regions
        if header_y + 5 < _y_center(r.bbox) <= header_y + BODY_SEARCH_BAND_PX
    ]
    if not body_regions:
        return BomTableExtraction(header_columns=[c for c, _ in ordered_columns], rows=[])

    # Group body regions into rows by y-bucket, then assign each region in a row to the
    # nearest header column whose x-span it falls within (with slack).
    buckets: dict[int, list] = {}
    for r in body_regions:
        bucket = round(_y_center(r.bbox) / ROW_BUCKET_PX)
        buckets.setdefault(bucket, []).append(r)

    rows: list[BomRow] = []
    for bucket in sorted(buckets.keys()):
        row_regions = sorted(buckets[bucket], key=lambda r: _x_center(r.bbox))
        cells: dict[str, list[str]] = {cat: [] for cat, _ in ordered_columns}
        confidences: list[float] = []
        for region in row_regions:
            rx = _x_center(region.bbox)
            best_cat, best_dist = None, None
            for cat, (x0, x1) in ordered_columns:
                if x0 - COLUMN_SLACK_PX <= rx <= x1 + COLUMN_SLACK_PX:
                    dist = 0.0
                else:
                    dist = min(abs(rx - x0), abs(rx - x1))
                if best_dist is None or dist < best_dist:
                    best_dist, best_cat = dist, cat
            if best_cat is not None and region.text and region.text.strip():
                cells[best_cat].append(region.text.strip())
                confidences.append(region.confidence)

        raw_text = " | ".join(region.text for region in row_regions if region.text)
        if not raw_text.strip():
            continue
        row = BomRow(
            item_no=" ".join(cells.get("item_no", [])),
            qty=" ".join(cells.get("qty", [])),
            part_no=" ".join(cells.get("part_no", [])),
            description=" ".join(cells.get("description", [])),
            material=" ".join(cells.get("material", [])),
            size=" ".join(cells.get("size", [])),
            raw_text=raw_text,
            confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        )
        # A row that produced nothing beyond whatever stray text clustered into the band
        # (no quantity AND no description/part number) is not a real BOM line - drop it
        # rather than persisting a blank/junk component.
        if row.qty or row.part_no or row.description or row.material:
            rows.append(row)

    return BomTableExtraction(header_columns=[c for c, _ in ordered_columns], rows=rows)
