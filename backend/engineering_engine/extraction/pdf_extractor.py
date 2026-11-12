"""PDF -> raw per-component CAD evidence, by REUSING the existing deterministic pipeline
(app.services.paddle_ocr, app.services.bom_table_extractor, app.services.drawing_detail_
extractor) rather than re-implementing OCR or BOM-table parsing - per the integration
instruction to inspect the existing application and not rebuild working functionality.

This module's only job is to normalize that pipeline's output into the flat per-component
`RawComponentEvidence` shape the calculation engine (engineering_engine.calculations) expects,
and to carry forward exactly which extraction method produced each raw field (so downstream
DimensionResult.extraction_method is never guessed). It never invents a value the existing
pipeline didn't actually find - a field that extraction couldn't locate is left None, same
"never fabricate" contract as the rest of the app.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import fitz  # pymupdf

from app.services.bom_table_extractor import extract_bom_table
from app.services.drawing_detail_extractor import extract_detail_dimensions, match_panel_to_description
from app.services.paddle_ocr import run_page_ocr


@dataclass
class RawComponentEvidence:
    """Everything the existing OCR/BOM pipeline could find for one BOM row, before any
    manufacturing calculation is applied. `dimensions` keys follow drawing_detail_extractor's
    own convention (od/id/thk/l/pcd/hole_dia/noh/...); any value present here came from a real
    OCR token (see `dimension_sources`), never invented."""
    description: str                    # as printed in the BOM table, e.g. "BELLOWS"
    material: str = ""
    qty_per_assembly_text: str = ""      # raw BOM qty cell text, parsing left to the caller
    dimensions: dict = field(default_factory=dict)       # e.g. {"od": "559", "id": "509"}
    dimension_sources: dict = field(default_factory=dict)  # same keys -> "ocr_detail_panel" | "bom_table"
    detail_panel_label: str = ""         # e.g. "SLEEVE DETAIL" - which CAD view this came from
    raw_tokens: list = field(default_factory=list)       # full panel text, for REVIEW_REQUIRED context
    cad_confidence: str = ""             # "high" | "low" | "none" | "" (no CAD geometry available) -
                                          # set by cad_extractor.py, never implies anything about
                                          # dimension_sources (CAD geometry doesn't assign od/thk/l
                                          # semantics today - see cad_extractor.py)
    cad_raw_tokens: list = field(default_factory=list)   # text found near the label by CAD geometry
                                          # clustering, kept separate from raw_tokens (OCR panel text)
                                          # so the two sources are never conflated


def _rasterize_page(pdf_path: str, page_number: int = 1, dpi: int = 200):
    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    import numpy as np
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def extract_components(pdf_path: str, page_number: int = 1) -> dict[str, RawComponentEvidence]:
    """Returns {normalized_description: RawComponentEvidence} for every BOM row the existing
    extract_bom_table found, with SIZE evidence merged in from the existing detail-panel
    extractor (extract_detail_dimensions) wherever a matching panel exists. Returns {} if no
    BOM table could be confidently located - same conservative behavior as the main app."""
    image = _rasterize_page(pdf_path, page_number)
    ocr_result = run_page_ocr(image, page_number=page_number)
    if not ocr_result.configured or not ocr_result.regions:
        return {}

    table = extract_bom_table(ocr_result.regions)
    if not table or not table.rows:
        return {}

    known_descriptions = [row.description for row in table.rows if row.description]
    panels = extract_detail_dimensions(ocr_result.regions, known_descriptions)

    out: dict[str, RawComponentEvidence] = {}
    for row in table.rows:
        description = row.description or row.part_no or row.material
        if not description:
            continue
        dimensions: dict = {}
        sources: dict = {}
        detail_panel_label = ""
        raw_tokens: list = []
        if row.size:
            dimensions["size"] = row.size
            sources["size"] = "bom_table"
        panel = match_panel_to_description(description, panels)
        if panel is not None:
            detail_panel_label = panel.label_text
            raw_tokens = list(panel.raw_tokens)
            for key, value in panel.dimensions.items():
                dimensions.setdefault(key, value)
                sources.setdefault(key, "ocr_detail_panel")
        out[description.strip().upper()] = RawComponentEvidence(
            description=description,
            material=row.material,
            qty_per_assembly_text=row.qty,
            dimensions=dimensions,
            dimension_sources=sources,
            detail_panel_label=detail_panel_label,
            raw_tokens=raw_tokens,
        )
    return out
