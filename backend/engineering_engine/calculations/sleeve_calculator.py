"""Sleeve: no formula - every dimension comes directly from the supplied indent/sleeve detail.

CORRECTED after review: the Sleeve CAD detail panel carries two concentric diameters, Ø539 and
Ø509. The auto-extractor (app.services.drawing_detail_extractor) reads them in descending order
as od=539/id=509, purely by pixel position - it has no way to know which physical feature each
one is. Cross-checking against the real WO 9374 indent (which prints Sleeve's OD as 509, not
539) shows that assumption is wrong here: 539mm is very likely Mid Pipe's own ID (559 OD - 2*10
thickness = 539, an exact match - see pipe_calculator), printed near the Sleeve detail as the
mating interface reference, not Sleeve's own OD. 509mm is Sleeve's true OD.

So this module now keeps three distinct fields, never conflated:
  - od: Sleeve's own outer diameter (509mm on WO 9374 - matches the indent)
  - thickness, length: read directly, no ambiguity
  - mid_pipe_interface_reference: the 539mm value, kept for traceability, explicitly flagged
    as unconfirmed and NOT used as Sleeve's own OD anywhere in this engine
"""
from __future__ import annotations

from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def sleeve_dimensions(
    od: float | None, thickness: float | None, length: float | None,
    mid_pipe_interface_reference: float | None = None,
    component: str = "Sleeve", detail_view: str = "Sleeve Detail",
    od_source: str = "manual", thickness_source: str = "manual", length_source: str = "manual",
) -> dict[str, DimensionResult]:
    """`od` is Sleeve's own true outer diameter (509mm on WO 9374, matching the indent's SIZE
    column - NOT the larger 539mm value the auto-extractor's descending-diameter convention
    picks up from the same detail panel). `mid_pipe_interface_reference` carries that 539mm
    value separately, for traceability, with status REVIEW_REQUIRED since its real identity
    (very likely Mid Pipe's own ID, not a Sleeve dimension at all) is not yet confirmed against
    the drawing's own dimension-reference callouts.

    `od_source`/`thickness_source`/`length_source` record where each value actually came from
    ("manual" or "ocr_detail_panel") - each defaults to "manual" (unchanged behavior for every
    existing caller that doesn't pass one), but a caller that fell back to CAD-detail-panel OCR
    evidence for thickness/length should pass "ocr_detail_panel" so that's reflected honestly
    rather than mislabeled as a manual reading."""
    sources = {"od": od_source, "thickness": thickness_source, "length": length_source}
    results: dict[str, DimensionResult] = {}
    for name, value in (("od", od), ("thickness", thickness), ("length", length)):
        if value is None:
            results[name] = missing(name, component)
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="mm", status=DimensionStatus.VERIFIED,
                component=component, detail_view=detail_view, extraction_method=sources[name],
            )
    if mid_pipe_interface_reference is not None:
        results["mid_pipe_interface_reference"] = DimensionResult(
            name="mid_pipe_interface_reference", value=mid_pipe_interface_reference, unit="mm",
            status=DimensionStatus.REVIEW_REQUIRED, component=component, detail_view=detail_view,
            extraction_method="ocr_detail_panel",
            notes=(
                "Auto-extracted from the Sleeve Detail panel as the larger of two concentric "
                "diameters (Ø539/Ø509) by pixel position, NOT by confirmed feature identity. "
                "Very likely Mid Pipe's own ID (559 OD - 2*10 thickness = 539, an exact match) "
                "printed near the Sleeve detail as a mating-interface reference - never treated "
                "as Sleeve's own OD. Confirm against the drawing's dimension references."
            ),
        )
    return results
