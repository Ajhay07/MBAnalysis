"""The generalized routing pipeline:
  Drawing Input -> Drawing Extraction -> Component Identification -> Component Classification
  -> Parameter Mapping -> Manufacturing Rule Selection -> Dimension Calculation
  -> Engineering Validation -> BOM Quantity Calculation -> Indent JSON Generation

`process_work_order()` is the single entry point. It never branches on a work-order number or
any drawing-specific condition - every decision is driven by WorkOrderInputs (what this WO's
indent needs) and ComponentSpec classification (what kind of component each entry is). A new
work order is a new WorkOrderInputs object, never a code change here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engineering_engine.extraction.dimension_parser import get_component_evidence
from engineering_engine.extraction.pdf_extractor import RawComponentEvidence
from engineering_engine.output.indent_generator import ComponentOutput, generate_indent_json
from engineering_engine.routing import component_builders  # noqa: F401 - import side effect: populates REGISTRY
from engineering_engine.routing.registry import classify_component
from engineering_engine.routing.work_order_inputs import ComponentInput, WorkOrderInputs


@dataclass
class RoutingDiagnostics:
    """Everything the router noticed about the classification/extraction process itself,
    separate from any one component's own dimensions - surfaced in the JSON output's own
    `diagnostics` block rather than buried inside a component entry."""
    extraction_available: bool = True
    extraction_error: str = ""
    unclassified_components: list[str] = field(default_factory=list)   # in WorkOrderInputs but no spec matched
    unaccounted_cad_rows: list[str] = field(default_factory=list)      # found in the CAD BOM but not in WorkOrderInputs
    duplicate_spec_matches: dict[str, list[str]] = field(default_factory=dict)  # spec_id -> [descriptions], len>1

    def to_dict(self) -> dict:
        return {
            "extraction_available": self.extraction_available,
            "extraction_error": self.extraction_error or None,
            "unclassified_components": self.unclassified_components,
            "unaccounted_cad_rows": self.unaccounted_cad_rows,
            "duplicate_spec_matches": {k: v for k, v in self.duplicate_spec_matches.items() if len(v) > 1},
        }


def _find_evidence(evidence: dict[str, RawComponentEvidence], description: str) -> RawComponentEvidence | None:
    """Exact key match first, then substring either direction - same conservative tolerance
    used throughout this app for OCR-truncated descriptions (e.g. "SLEEV" for "SLEEVE")."""
    key = description.strip().upper()
    if key in evidence:
        return evidence[key]
    for ev_key, ev in evidence.items():
        if ev_key in key or key in ev_key:
            return ev
    return None


def _build_unclassified(comp_input: ComponentInput) -> ComponentOutput:
    """A component in WorkOrderInputs that no registered spec could classify - reported as its
    own entry (status REVIEW_REQUIRED, via an empty dimensions dict) rather than silently
    dropped, so an unknown/new component type is always visible in the output."""
    from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus
    note = DimensionResult(
        name="classification", value="UNCLASSIFIED", unit="", status=DimensionStatus.REVIEW_REQUIRED,
        component=comp_input.description,
        notes="No registered ComponentSpec matched this description - add one to the registry, or confirm the spelling/alias.",
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions={"classification": note},
        reference_dimensions=comp_input.reference_dimensions,
    )


def build_components(inputs: WorkOrderInputs) -> tuple[list[ComponentOutput], RoutingDiagnostics]:
    """The classification + calculation pass, without JSON formatting - exposed separately so
    callers that want the raw ComponentOutput objects (e.g. further processing, or backward
    compatibility with code written against the pre-routing-layer interface) don't have to
    round-trip through JSON. process_work_order() below is the normal entry point."""
    diagnostics = RoutingDiagnostics()

    evidence: dict[str, RawComponentEvidence] = {}
    if inputs.pdf_path:
        try:
            evidence = get_component_evidence(inputs.pdf_path)
        except Exception as exc:  # pragma: no cover - degrades to manual-only, never crashes the run
            diagnostics.extraction_available = False
            diagnostics.extraction_error = str(exc)

    components: list[ComponentOutput] = []
    matched_evidence_keys: set[str] = set()
    spec_matches: dict[str, list[str]] = {}

    for comp_input in inputs.components:
        spec = None
        if comp_input.spec_identifier:
            from engineering_engine.routing.registry import REGISTRY
            spec = REGISTRY.get(comp_input.spec_identifier)
        if spec is None:
            spec = classify_component(comp_input.description)

        if spec is None:
            diagnostics.unclassified_components.append(comp_input.description)
            components.append(_build_unclassified(comp_input))
            continue

        spec_matches.setdefault(spec.identifier, []).append(comp_input.description)

        ev = _find_evidence(evidence, comp_input.description)
        if ev is not None:
            for ev_key in evidence:
                if evidence[ev_key] is ev:
                    matched_evidence_keys.add(ev_key)
                    break

        components.append(spec.builder(ev, comp_input, inputs.assembly_quantity))

    diagnostics.duplicate_spec_matches = spec_matches
    diagnostics.unaccounted_cad_rows = [
        ev.description for key, ev in evidence.items() if key not in matched_evidence_keys
    ]
    return components, diagnostics


def process_work_order(inputs: WorkOrderInputs) -> dict:
    components, diagnostics = build_components(inputs)
    output = generate_indent_json(inputs.work_order, inputs.assembly_quantity, components)
    output["diagnostics"] = diagnostics.to_dict()
    return output
