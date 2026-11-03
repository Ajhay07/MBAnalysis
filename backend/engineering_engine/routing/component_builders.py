"""One adapter function per registered component - each calls the EXISTING calculators
(engineering_engine.calculations.*) with parameters pulled from CAD-extracted evidence and/or
a work order's manual inputs, and assembles a ComponentOutput. No manufacturing math lives
here; this module is purely "which calculator, called with which arguments."

Every builder has the same signature so the router can call whichever one a ComponentSpec
points to without any per-component branching of its own:
    builder(evidence: RawComponentEvidence | None, comp_input: ComponentInput,
            assembly_quantity: float) -> ComponentOutput
"""
from __future__ import annotations

from engineering_engine.calculations import (
    bellows_calculator, flange_calculator, packaging_calculator, pipe_calculator, shroud_calculator,
    sleeve_calculator,
)
from engineering_engine.extraction.dimension_parser import parse_numeric
from engineering_engine.extraction.pdf_extractor import RawComponentEvidence
from engineering_engine.output.indent_generator import ComponentOutput
from engineering_engine.routing.registry import ComponentSpec, register
from engineering_engine.routing.work_order_inputs import ComponentInput
from engineering_engine.validation.bom_validator import calculate_total_quantity, reference_only_quantity
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus


def _evidence_value(evidence: RawComponentEvidence | None, key: str) -> float | None:
    if evidence is None:
        return None
    return parse_numeric(evidence.dimensions.get(key))


def _quantity(comp_input: ComponentInput, assembly_quantity: float):
    """Shared quantity logic: a real per-assembly figure multiplies normally (with discrepancy
    checking against any reference); a component with ONLY a reference quantity (no per-
    assembly figure available) preserves that reference instead of being dropped - see
    bom_validator.reference_only_quantity (added specifically because Filler Wire/Electrode/
    Stiffener were being silently lost this way)."""
    if comp_input.quantity_per_assembly is not None:
        return calculate_total_quantity(
            comp_input.description, comp_input.quantity_per_assembly, assembly_quantity,
            comp_input.reference_indent_quantity,
        )
    if comp_input.reference_indent_quantity is not None:
        return reference_only_quantity(comp_input.description, comp_input.reference_indent_quantity)
    return None


def _manual_result(name: str, value, component: str, unit: str = "mm", notes: str = "",
                    extraction_method: str = "manual") -> DimensionResult | None:
    if value is None:
        return None
    return DimensionResult(
        name=name, value=value, unit=unit, status=DimensionStatus.VERIFIED, component=component,
        extraction_method=extraction_method,
        notes=notes or ("Manually supplied for this work order." if extraction_method == "manual" else ""),
    )


def build_bellows(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    od = _evidence_value(evidence, "od")
    length_result = bellows_calculator.calculate_blank_length(od)
    thickness_result = (
        bellows_calculator.calculate_thickness(m.get("num_plies"), m.get("ply_thickness_mm"))
        if m.get("num_plies") is not None or m.get("ply_thickness_mm") is not None
        else DimensionResult("thickness", None, "mm", DimensionStatus.MISSING, "Bellows")
    )
    n, convolution_result = bellows_calculator.interpret_convolution_count(m.get("convolution_text"))
    width_result = bellows_calculator.calculate_sheet_width(m.get("pitch_q"), m.get("depth_w"), n)
    od_result = (
        DimensionResult("od", od, "mm", DimensionStatus.VERIFIED, "Bellows", extraction_method="ocr_detail_panel",
                         notes="OD read from the CAD Bellow Detail (Ø marker).")
        if od is not None else DimensionResult("od", None, "mm", DimensionStatus.MISSING, "Bellows")
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material,
        dimensions={"od": od_result, "length": length_result, "width": width_result,
                    "thickness": thickness_result, "convolution_count": convolution_result},
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_shroud(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    # Manual OD takes precedence when supplied (e.g. no CAD PDF available for this work order);
    # otherwise falls back to CAD-extracted evidence, same pattern as Sleeve's manual-first od.
    od = m.get("od") if m.get("od") is not None else _evidence_value(evidence, "od")
    base_length = shroud_calculator.calculate_base_circumference(od)
    reference_length = comp_input.reference_dimensions.get("length")
    final_length = shroud_calculator.calculate_final_length(base_length.value, reference_length)
    dims = {"base_length": base_length, "length": final_length}
    width_r = _manual_result("width", m.get("width"), "Shroud")
    thickness = m.get("thickness")
    if thickness is None:
        thickness = _evidence_value(evidence, "thk")
    thickness_source = "manual" if m.get("thickness") is not None else "ocr_detail_panel"
    thickness_r = _manual_result(
        "thickness", thickness, "Shroud", extraction_method=thickness_source,
        notes="" if thickness_source == "manual" else "Read from the CAD detail panel.",
    )
    if width_r:
        dims["width"] = width_r
    if thickness_r:
        dims["thickness"] = thickness_r
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_pipe(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    """Shared by Mid Pipe and End Pipe - identical formula (see pipe_calculator), the only
    difference is which component name/evidence is passed in.

    Thickness and length are manual-first (a reviewer's typed-in reading always wins), falling
    back to the CAD detail panel's own OCR-extracted "thk"/"l" fields (drawing_detail_extractor.
    DIMENSION_LABELS) when no manual value was supplied - previously these two were manual-only
    even when the drawing's own detail panel already carried them, same gap OD/ID never had."""
    m = comp_input.manual
    od = _evidence_value(evidence, "od")
    thickness = m.get("thickness")
    thickness_source = "manual"
    if thickness is None:
        thickness = _evidence_value(evidence, "thk")
        thickness_source = "ocr_detail_panel"
    length = m.get("length")
    length_source = "manual"
    if length is None:
        length = _evidence_value(evidence, "l")
        length_source = "ocr_detail_panel"
    dims = pipe_calculator.pipe_dimensions(
        od, thickness, length, comp_input.description,
        detail_view=f"{comp_input.description} Detail",
        extraction_methods={"thickness": thickness_source, "length": length_source},
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_sleeve(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    """OD is manual-by-default (see sleeve_calculator.py's own docstring for why the auto-
    extracted value from this detail panel can't be trusted as OD without confirmation) -
    falls back to the CAD-extracted `id` field (the smaller of the panel's two diameters) only
    when no manual OD was supplied, since that's the one more likely to be the true OD on a
    thin-wall sleeve (the larger value is more often a neighboring component's own reference -
    confirmed on WO 9374). Always still flagged for review either way."""
    m = comp_input.manual
    od = m.get("od")
    od_source = "manual"
    if od is None:
        od = _evidence_value(evidence, "id")
        od_source = "ocr_detail_panel"
    interface_reference = m.get("mid_pipe_interface_reference")
    if interface_reference is None:
        interface_reference = _evidence_value(evidence, "od")
    # Thickness/length: manual-first, falling back to the Sleeve Detail panel's own OCR'd
    # "thk"/"l" fields when no manual reading was supplied - same fallback pattern as Pipe.
    thickness = m.get("thickness")
    thickness_source = "manual"
    if thickness is None:
        thickness = _evidence_value(evidence, "thk")
        thickness_source = "ocr_detail_panel"
    length = m.get("length")
    length_source = "manual"
    if length is None:
        length = _evidence_value(evidence, "l")
        length_source = "ocr_detail_panel"
    dims = sleeve_calculator.sleeve_dimensions(
        od, thickness, length, mid_pipe_interface_reference=interface_reference,
        od_source=od_source, thickness_source=thickness_source, length_source=length_source,
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_housing_flange(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    od = _evidence_value(evidence, "od")
    # Thickness: manual-first, falling back to the detail panel's own OCR'd "thk" field - same
    # fallback as Pipe/Sleeve, for a drawing where thickness IS printed on the detail panel.
    thickness = m.get("thickness")
    if thickness is None:
        thickness = _evidence_value(evidence, "thk")
    dims = flange_calculator.housing_flange_dimensions(
        od, m.get("id"), thickness, m.get("pcd"), m.get("hole_diameter"),
        hole_count_drawing=m.get("hole_count_drawing"), hole_count_indent=m.get("hole_count_indent"),
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_limit_rod(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    length_result = flange_calculator.calculate_limit_rod_length(
        m.get("cad_length"), cad_length_is_inferred=bool(m.get("cad_length_is_inferred")),
    )
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions={"length": length_result},
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_collar(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    dims = flange_calculator.collar_dimensions(m.get("diameter"), m.get("length"), m.get("source_detail"))
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_wooden_box(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    m = comp_input.manual
    length_result = packaging_calculator.calculate_box_length(m.get("assembly_length_mm"))
    bw = packaging_calculator.box_breadth_and_width(m.get("breadth"), m.get("width"))
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material,
        dimensions={"length": length_result, **bw},
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def build_passthrough(evidence, comp_input: ComponentInput, assembly_quantity: float) -> ComponentOutput:
    """No manufacturing formula applies - size/spec passes straight through from the work
    order's manual input, per the spec's explicit instruction not to invent a formula for
    these (Shroud Support, Stiffener, Bolts and Nuts, Filler Wire, Electrode)."""
    m = comp_input.manual
    size = m.get("size")
    dims = {"size": _manual_result("size", size, comp_input.description, unit="")} if size else {}
    return ComponentOutput(
        name=comp_input.description, material=comp_input.material, dimensions=dims,
        reference_dimensions=comp_input.reference_dimensions,
        quantity=_quantity(comp_input, assembly_quantity),
    )


def register_all() -> None:
    """Idempotent - calling this more than once just re-registers the same specs. Called once
    at module import time (bottom of this file) so `from engineering_engine.routing import
    registry; registry.REGISTRY` is populated as soon as component_builders is imported."""
    register(ComponentSpec(
        identifier="BELLOWS", aliases=("BELLOW", "BELLOWS"),
        required_parameters=("od",), optional_parameters=("num_plies", "ply_thickness_mm", "pitch_q", "depth_w", "convolution_text"),
        extraction_sources=("od: ocr_detail_panel (Ø marker)", "thickness/width inputs: manual"),
        calculator="calculations.bellows_calculator", builder=build_bellows,
        validation_requirements="length CALCULATED when od present; width MISSING without pitch_q/depth_w (never fabricated)",
    ))
    register(ComponentSpec(
        identifier="SHROUD", aliases=("SHROUD",),
        required_parameters=("od",), optional_parameters=("width", "thickness"),
        extraction_sources=("od: ocr_detail_panel",), calculator="calculations.shroud_calculator",
        builder=build_shroud, validation_requirements="final length REVIEW_REQUIRED unless an approved allowance is configured",
    ))
    register(ComponentSpec(
        identifier="MID_PIPE", aliases=("MID PIPE", "MIDPIPE"),
        required_parameters=("od", "thickness"), optional_parameters=("length",),
        extraction_sources=("od: ocr_detail_panel", "thickness/length: manual"),
        calculator="calculations.pipe_calculator", builder=build_pipe,
    ))
    register(ComponentSpec(
        identifier="END_PIPE", aliases=("END PIPE", "ENDPIPE"),
        required_parameters=("od", "thickness"), optional_parameters=("length",),
        extraction_sources=("od: ocr_detail_panel", "thickness/length: manual"),
        calculator="calculations.pipe_calculator", builder=build_pipe,
    ))
    register(ComponentSpec(
        identifier="SLEEVE", aliases=("SLEEVE", "SLEEV"),
        required_parameters=("od",), optional_parameters=("thickness", "length", "mid_pipe_interface_reference"),
        extraction_sources=("od: manual (NOT trusted from OCR - see sleeve_calculator.py)",),
        calculator="calculations.sleeve_calculator", builder=build_sleeve,
        validation_requirements="od defaults to manual input; falls back to the panel's smaller diameter, always flagged",
    ))
    register(ComponentSpec(
        identifier="HOUSING_FLANGE", aliases=("HOUSING FLANGE", "FLANGE"),
        required_parameters=("od", "id", "thickness", "pcd", "hole_diameter"), optional_parameters=("hole_count_drawing", "hole_count_indent"),
        extraction_sources=("od: ocr_detail_panel", "rest: manual"),
        calculator="calculations.flange_calculator.housing_flange_dimensions", builder=build_housing_flange,
    ))
    register(ComponentSpec(
        identifier="LIMIT_ROD", aliases=("LIMIT ROD",),
        required_parameters=("cad_length",), extraction_sources=("cad_length: manual (no CAD detail panel on WO 9374)",),
        calculator="calculations.flange_calculator.calculate_limit_rod_length", builder=build_limit_rod,
        validation_requirements="always REVIEW_REQUIRED - 15mm allowance is pending_approval",
    ))
    register(ComponentSpec(
        identifier="COLLAR", aliases=("COLLAR",),
        required_parameters=("diameter", "length"), optional_parameters=("source_detail",),
        extraction_sources=("manual, must be sourced from Detail B",),
        calculator="calculations.flange_calculator.collar_dimensions", builder=build_collar,
        validation_requirements="REVIEW_REQUIRED unless source_detail == 'Detail B'",
    ))
    register(ComponentSpec(
        identifier="SHROUD_SUPPORT", aliases=("SHROUD SUPPORT",),
        required_parameters=("size",), calculator="(none - pass-through)", builder=build_passthrough,
    ))
    register(ComponentSpec(
        identifier="STIFFENER", aliases=("STIFFENER",),
        required_parameters=("size",), calculator="(none - pass-through)", builder=build_passthrough,
    ))
    register(ComponentSpec(
        identifier="WOODEN_BOX", aliases=("WOODEN BOX", "PACKING BOX", "PACKAGING BOX"),
        required_parameters=("assembly_length_mm",), optional_parameters=("breadth", "width"),
        extraction_sources=("no independent source yet - see README 'Generalization status'",),
        calculator="calculations.packaging_calculator", builder=build_wooden_box,
        validation_requirements="length MISSING unless a genuine (non-reverse-engineered) assembly length is supplied",
    ))
    register(ComponentSpec(
        identifier="BOLTS_AND_NUTS", aliases=("NUT AND LOCKNUT", "NUT LOCKNUT", "BOLT AND NUT", "BOLT NUT", "M8 BOLT", "NUT", "BOLT"),
        required_parameters=("size",), calculator="(none - pass-through)", builder=build_passthrough,
    ))
    register(ComponentSpec(
        identifier="FILLER_WIRE", aliases=("FILLER WIRE", "FILLERWIRE"),
        required_parameters=("size",), calculator="(none - pass-through)", builder=build_passthrough,
    ))
    register(ComponentSpec(
        identifier="ELECTRODE", aliases=("ELECTRODE",),
        required_parameters=("size",), calculator="(none - pass-through)", builder=build_passthrough,
    ))


register_all()
