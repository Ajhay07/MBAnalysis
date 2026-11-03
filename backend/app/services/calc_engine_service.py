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

from engineering_engine.routing import component_builders  # noqa: F401 - populates REGISTRY on import
from engineering_engine.routing.registry import REGISTRY, classify_component
from engineering_engine.routing.work_order_inputs import ComponentInput


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
