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


def _y_span(bbox) -> tuple[float, float]:
    ys = [p[1] for p in bbox]
    return (min(ys), max(ys)) if ys else (0.0, 0.0)


def _y_overlap(bbox_a, bbox_b) -> float:
    y0a, y1a = _y_span(bbox_a)
    y0b, y1b = _y_span(bbox_b)
    return min(y1a, y1b) - max(y0a, y0b)


# Pixel gap beyond which two x-sorted regions are no longer treated as the same
# transposed-table "run" - see _extract_transposed_bom_table below. Real items in one of these
# title blocks sit 3-30px apart; the gap to an unrelated field (a separate spec-parameters
# block sharing the same page, say) runs 150px+, so 100 cleanly separates the two without
# needing to hand-tune per drawing.
TRANSPOSED_RUN_GAP_PX = 100


def _contiguous_x_run(candidates: list, start_x: float) -> list:
    """candidates sorted by x-position, keeping a contiguous run starting near start_x and
    cutting at the first gap wider than TRANSPOSED_RUN_GAP_PX. Used to isolate one title-block
    sub-table's cells from an unrelated block of text sharing the same page/row band."""
    ordered = sorted(candidates, key=lambda r: _x_center(r.bbox))
    run: list = []
    prev_x1 = start_x
    for region in ordered:
        x0, x1 = _x_span(region.bbox)
        if x0 - prev_x1 > TRANSPOSED_RUN_GAP_PX:
            break
        run.append(region)
        prev_x1 = x1
    return run


def _extract_transposed_bom_table(regions) -> BomTableExtraction | None:
    """Fallback for title blocks where the BOM is laid out ROTATED: instead of one header row
    with an item per row below it, each attribute (DESCRIPTION, MATERIAL, ...) is its own
    label stacked in a narrow strip, and each COMPONENT is a column of its own to the right -
    item name, material etc. for one component all share roughly the same x-position across
    different attribute-label y-bands. This is a real, recurring MB Metallic Bellows title-
    block style (confirmed directly from a production drawing's raw OCR regions - WO-9374 -
    where the row-based extract_bom_table above correctly finds nothing, because there never
    is a single header ROW here to find).

    Deliberately conservative like the row-based path: a component with no readable
    description is not invented, and a component whose material cell can't be confidently
    matched is still returned, just with an empty material (never a guessed one).
    """
    description_label = next(
        (r for r in regions if _normalize(r.text or "") in HEADER_TOKENS["description"]),
        None,
    )
    if description_label is None:
        return None
    desc_x0, desc_x1 = _x_span(description_label.bbox)

    item_candidates = [
        r for r in regions
        if r is not description_label
        and r.text and r.text.strip()
        and _y_overlap(r.bbox, description_label.bbox) > 0
        and _x_center(r.bbox) > desc_x1
    ]
    item_regions = _contiguous_x_run(item_candidates, desc_x1)
    if not item_regions:
        return None

    # The MATERIAL label for THIS sub-table sits in the same narrow x-strip as DESCRIPTION
    # (stacked vertically below it) - a page can have other "MATERIAL ..." fields elsewhere
    # (e.g. "MATERIAL No." in an unrelated spec-parameters block), so pick whichever match is
    # closest in x to the DESCRIPTION label actually used, not just the first match.
    material_label_candidates = [
        r for r in regions
        if r is not description_label
        and any(
            _normalize(r.text or "") == alias or _normalize(r.text or "").startswith(alias)
            for alias in HEADER_TOKENS["material"]
        )
    ]
    material_by_item: dict[int, str] = {}
    if material_label_candidates:
        material_label = min(
            material_label_candidates,
            key=lambda r: abs(_x_center(r.bbox) - _x_center(description_label.bbox)),
        )
        material_value_candidates = [
            r for r in regions
            if r is not material_label
            and r not in item_regions
            and r is not description_label
            and r.text and r.text.strip()
            and _y_overlap(r.bbox, material_label.bbox) > 0
            and _x_center(r.bbox) > desc_x1
        ]
        material_values = _contiguous_x_run(material_value_candidates, desc_x1)
        for value_region in material_values:
            nearest_item = min(item_regions, key=lambda it: abs(_x_center(it.bbox) - _x_center(value_region.bbox)))
            material_by_item[id(nearest_item)] = value_region.text.strip()

    rows = [
        BomRow(
            description=item.text.strip(),
            material=material_by_item.get(id(item), ""),
            raw_text=item.text.strip(),
            confidence=item.confidence,
        )
        for item in item_regions
    ]
    return BomTableExtraction(header_columns=["description", "material"], rows=rows)


def extract_bom_table(regions) -> BomTableExtraction | None:
    """`regions` is a list of app.services.paddle_ocr.OcrRegion (text, confidence, bbox).
    Returns None when no table header can be confidently identified; otherwise the header
    columns found and every body row successfully assembled beneath them.

    Tries the normal header-row-plus-item-rows layout first; only falls back to the transposed
    "items as columns" layout (see _extract_transposed_bom_table's docstring) when NO header
    could be identified at all. A header that genuinely has zero body rows beneath/above it is
    a real, deliberately-conservative answer in its own right (same as before this fallback
    existed) - it must be returned as-is, not treated as "found nothing" and overwritten by a
    completely different table from the transposed path."""
    table = _extract_row_based_bom_table(regions)
    if table is not None:
        return table
    return _extract_transposed_bom_table(regions) if regions else None


def _extract_row_based_bom_table(regions) -> BomTableExtraction | None:
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

    # Body rows can sit either below OR above the header - don't assume one direction. Many
    # real title-block BOM tables (e.g. MB Metallic Bellows' own drawings) are built bottom-up:
    # the header row and the "BILL OF MATERIAL" caption sit at the BOTTOM of the table, with
    # item 1 directly above the header and the highest item number at the top. A one-directional
    # search (data must be below the header) silently finds zero rows on every such drawing -
    # this was traced directly to a real 0-component result on a genuine MB drawing.
    # A bare "BILL OF MATERIAL(S)" caption sitting right next to the header (common in exactly
    # this bottom-up layout) is not a row - exclude it explicitly rather than let it become a
    # junk single-cell component.
    body_regions = [
        r for r in regions
        if 5 < abs(_y_center(r.bbox) - header_y) <= BODY_SEARCH_BAND_PX
        and _normalize(r.text or "") not in ("BILL OF MATERIAL", "BILL OF MATERIALS")
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
