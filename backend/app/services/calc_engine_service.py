"""Bridges a single Component row to the engineering_engine (backend/engineering_engine)
classification + calculation pipeline.

This is deliberately narrower than engineering_engine.routing.pipeline.process_work_order():
that entry point is for a whole work order (a list of ComponentInputs plus an optional CAD
PDF to pull OD/ID evidence from). Here we only have one Component at a time, reviewed through
the normal analysis UI, with no PDF re-extraction (that already happened earlier in the
analysis pipeline - app.services.*). So this calls the same registry/classification and the
same per-component builder functions directly, using:
  - Component.description  -> what classify_component() matches against
  - Component.calc_inputs  -> the manual readings a reviewer has typed in (ComponentInput.manual)
  - Component.dimensions   -> treated as this component's reference/indent dimensions, for the
                               builder's own comparison logic (e.g. shroud's reference length)
  - Component.quantity     -> quantity_per_assembly

No CAD evidence (RawComponentEvidence) is passed - builder() always receives None for it here,
so any dimension that depends on OCR'd CAD evidence (e.g. Bellows/Shroud OD) will come back
MISSING or REVIEW_REQUIRED unless the reviewer has supplied it manually via calc_inputs.
"""
from __future__ import annotations

import re

from engineering_engine.calculations import bellows_calculator, shroud_calculator
from engineering_engine.extraction.dimension_parser import parse_numeric
from engineering_engine.routing import component_builders  # noqa: F401 - populates REGISTRY on import
from engineering_engine.routing.registry import REGISTRY, classify_component
from engineering_engine.routing.work_order_inputs import ComponentInput
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def run_component_calculation(component) -> dict:
    """Classifies `component` (unless it already carries a confirmed calc_spec_identifier)
    and runs it through that spec's builder/calculator. Returns a dict with a top-level
    `spec_identifier` (None when unclassified) plus the engine's own ComponentOutput.to_dict()
    fields (final_proposed_dimensions, dimensions_by_source, status, etc.) - this is what gets
    stored verbatim as Component.calc_result. Never raises for an unclassified or
    missing-input component; that's surfaced as a status, not an exception, same convention
    the engine itself follows."""
    spec = REGISTRY.get(component.calc_spec_identifier) if component.calc_spec_identifier else None
    if spec is None:
        spec = classify_component(component.description or "")

    if spec is None:
        return {
            "spec_identifier": None,
            "status": "UNCLASSIFIED",
            "message": (
                "No registered engineering_engine component spec matched this description - "
                "set calc_spec_identifier explicitly to override, or confirm the spelling."
            ),
        }

    comp_input = ComponentInput(
        description=component.description or "",
        material=component.material or "",
        manual=component.calc_inputs or {},
        reference_dimensions=component.dimensions or {},
        quantity_per_assembly=component.quantity,
    )
    # assembly_quantity=1: there is no work-order-level assembly quantity in a single-component
    # review context, so quantity_per_assembly is surfaced as-is rather than multiplied.
    output = spec.builder(None, comp_input, 1.0)
    result = output.to_dict()
    result["spec_identifier"] = spec.identifier
    return result


# --- Automatic Bellows/Shroud calculation for indent generation ------------------------------
# Only these two component types have a real manufacturing FORMULA in this engine (blank
# length/thickness from OD+ply-count; base circumference from OD) - every other registered
# component (Sleeve, Pipes, Housing Flange, Collar, Limit Rod, consumables, ...) is a direct
# CAD-detail reading with no formula to apply, so indent_service just displays whatever was
# extracted for those (see indent_service.lines_from_bom / format_size_text). This runs
# automatically at indent-generation time - no manual "Calculate" step - using only what the
# existing OCR pipeline could find on the component's own `dimensions`/`source_text`.

_PLY_TEXT_RE = re.compile(r"(\d+)\s*ply\s*x\s*([\d.]+)\s*mm", re.IGNORECASE)


def parse_bellows_ply_text(*texts: str | None) -> tuple[int | None, float | None]:
    """Looks for a "<N>ply x <thickness>mm" callout (e.g. "1ply x 0.6 mm", seen verbatim on
    WO 9374's Bellow Detail panel) across any of the given free-text fields - a component's own
    source_text (the raw BOM row) and assumption_text (which carries a detail panel's raw OCR
    tokens when SIZE was extracted from a panel - see app.providers.deterministic_provider).
    Returns (None, None), never a guess, when no such callout is found anywhere."""
    for text in texts:
        if not text:
            continue
        m = _PLY_TEXT_RE.search(text)
        if m:
            return int(m.group(1)), float(m.group(2))
    return None, None


def compute_bellows_or_shroud_result(component) -> dict | None:
    """Returns an engine-computed result dict for a Bellows or Shroud component, or None for
    anything else (including a Bellows/Shroud the engine couldn't compute enough of - callers
    fall back to the plain extracted-dimensions display in that case, same as every other
    component type). Never raises - a missing input just means fewer fields in the result."""
    spec = classify_component(component.description or "")
    if spec is None or spec.identifier not in ("BELLOWS", "SHROUD"):
        return None

    dims = component.dimensions or {}
    od = parse_numeric(dims.get("od"))
    width = parse_numeric(dims.get("width"))

    if spec.identifier == "BELLOWS":
        length_result = bellows_calculator.calculate_blank_length(od)
        num_plies, ply_thickness = parse_bellows_ply_text(component.source_text, component.assumption_text)
        thickness_result = bellows_calculator.calculate_thickness(num_plies, ply_thickness)
        results = {"length": length_result, "thickness": thickness_result}
    else:  # SHROUD
        base_length = shroud_calculator.calculate_base_circumference(od)
        length_result = shroud_calculator.calculate_final_length(base_length.value)
        thickness_value = parse_numeric(dims.get("thk"))
        thickness_result = (
            DimensionResult(name="thickness", value=thickness_value, unit="mm", status=DimensionStatus.VERIFIED,
                             component="Shroud", extraction_method="ocr_detail_panel")
            if thickness_value is not None else missing("thickness", "Shroud")
        )
        results = {"length": length_result, "thickness": thickness_result}

    if width is not None:
        results["width"] = DimensionResult(
            name="width", value=width, unit="mm", status=DimensionStatus.VERIFIED,
            component=spec.identifier.title(), extraction_method="ocr_detail_panel",
        )

    if all(r.status == DimensionStatus.MISSING for r in results.values()):
        return None  # nothing computable - let the caller fall back to plain extracted dimensions

    return {
        "spec_identifier": spec.identifier,
        "status": "CALCULATED" if any(r.status == DimensionStatus.CALCULATED for r in results.values()) else "REVIEW_REQUIRED",
        "final_proposed_dimensions": {name: r.value for name, r in results.items()},
        "dimension_detail": {name: r.to_dict() for name, r in results.items()},
    }


def format_bellows_or_shroud_size_text(result: dict) -> str:
    """"1765 x 340 x 0.6"-style size text (Length x Width x Thickness, MB's own convention for
    these two component types - see the physical indent sheet) from a
    compute_bellows_or_shroud_result() dict. Only the dimensions actually computed appear;
    nothing is padded with a placeholder for a value the engine couldn't produce."""
    dims = result.get("final_proposed_dimensions", {})
    parts = [dims[k] for k in ("length", "width", "thickness") if dims.get(k) is not None]
    return " x ".join(f"{v:g}" if isinstance(v, (int, float)) else str(v) for v in parts)
