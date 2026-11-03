"""Housing Flange (pass-through + discrepancy flagging), Limit Rod (pending-approval length
allowance), and Collar (must come from Detail B, never the overall assembly view) - grouped
here as they're all "read from a specific CAD detail, little or no formula" components.
"""
from __future__ import annotations

from engineering_engine.calculations.rules_loader import load_rules
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def housing_flange_dimensions(
    od: float | None, id_: float | None, thickness: float | None, pcd: float | None,
    hole_diameter: float | None, hole_count_drawing: int | None = None, hole_count_indent: int | None = None,
    component: str = "Housing Flange", detail_view: str = "Housing Flange Detail",
) -> dict[str, DimensionResult]:
    """All five core dimensions are direct CAD-detail readings (VERIFIED), no formula. A
    mismatch between the drawing's own printed hole count and the indent's is flagged as its
    own REVIEW_REQUIRED result - never silently resolved in either direction."""
    fields = {"od": od, "id": id_, "thickness": thickness, "pcd": pcd, "hole_diameter": hole_diameter}
    results: dict[str, DimensionResult] = {}
    for name, value in fields.items():
        if value is None:
            results[name] = missing(name, component)
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="mm", status=DimensionStatus.VERIFIED,
                component=component, detail_view=detail_view, extraction_method="ocr_detail_panel",
            )
    if hole_count_drawing is not None and hole_count_indent is not None:
        if hole_count_drawing != hole_count_indent:
            results["hole_count"] = DimensionResult(
                name="hole_count", value=f"drawing={hole_count_drawing}, indent={hole_count_indent}",
                unit="count", status=DimensionStatus.REVIEW_REQUIRED, component=component, detail_view=detail_view,
                extraction_method="ocr_detail_panel",
                notes="Drawing and indent disagree on hole count - flagged, not auto-corrected either way.",
            )
        else:
            results["hole_count"] = DimensionResult(
                name="hole_count", value=hole_count_drawing, unit="count", status=DimensionStatus.VERIFIED,
                component=component, detail_view=detail_view, extraction_method="ocr_detail_panel",
            )
    elif hole_count_drawing is not None or hole_count_indent is not None:
        results["hole_count"] = DimensionResult(
            name="hole_count", value=hole_count_drawing or hole_count_indent, unit="count",
            status=DimensionStatus.REVIEW_REQUIRED, component=component, detail_view=detail_view,
            extraction_method="ocr_detail_panel",
            notes="Only one of drawing/indent hole count was supplied - the other should be checked.",
        )
    else:
        results["hole_count"] = missing("hole_count", component)
    return results


def calculate_limit_rod_length(
    cad_length: float | None, component: str = "Limit Rod", cad_length_is_inferred: bool = False,
) -> DimensionResult:
    """final_length = cad_length + allowance_mm (15mm, pending_approval per manufacturing_
    rules.json). Always REVIEW_REQUIRED while pending - never silently treated as final, and
    never applied to any component other than Limit Rod.

    `cad_length_is_inferred`: WO 9374 has no Limit Rod CAD detail panel at all, so there is no
    independent raw-length reading to apply the allowance to - only the indent's own final
    figure (610mm) is known. When True, `cad_length` was itself derived by subtracting the
    15mm allowance back out of that final figure (610-15=595) rather than read independently -
    the formula and result are still reported (per explicit instruction to preserve them), but
    the note says so plainly so this is never mistaken for an independently-verified input."""
    if cad_length is None:
        return missing("length", component, "cad_length input required")
    rule = load_rules()["limit_rod"]["length_allowance"]
    value = cad_length + rule["allowance_mm"]
    notes = f"Allowance is {rule['approval_status']}: {rule['source']}"
    if cad_length_is_inferred:
        notes += (
            " cad_length itself is NOT an independent CAD reading - WO 9374 has no Limit Rod "
            "detail panel; it was derived by subtracting the allowance back out of the indent's "
            "own final length (610 - 15 = 595), pending a genuine raw CAD measurement."
        )
    return DimensionResult(
        name="length", value=value, unit="mm", status=DimensionStatus.REVIEW_REQUIRED,
        component=component, extraction_method="calculated",
        formula="cad_length + allowance_mm", inputs={"cad_length": cad_length, "allowance_mm": rule["allowance_mm"]},
        notes=notes,
    )


def collar_dimensions(
    diameter: float | None, length: float | None, source_detail: str | None,
    component: str = "Collar",
) -> dict[str, DimensionResult]:
    """Must come from Detail B's own annotations, never derived from the overall assembly
    view - `source_detail` documents where each value actually came from, and anything not
    explicitly sourced from "Detail B" is flagged REVIEW_REQUIRED even if a number is present,
    per the manufacturing instruction."""
    status = DimensionStatus.VERIFIED if source_detail == "Detail B" else DimensionStatus.REVIEW_REQUIRED
    notes = "" if source_detail == "Detail B" else (
        f"Source detail is {source_detail!r}, not confirmed as 'Detail B' - manufacturing "
        "instruction requires Collar dimensions to come specifically from Detail B, never the "
        "overall assembly view."
    )
    results: dict[str, DimensionResult] = {}
    for name, value in (("diameter", diameter), ("length", length)):
        if value is None:
            results[name] = missing(name, component)
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="mm", status=status, component=component,
                detail_view=source_detail or "", extraction_method="ocr_detail_panel", notes=notes,
            )
    return results
