"""Generalized routing pipeline tests: multiple work orders, different component combinations,
missing parameters, unapproved allowances, duplicate component classification, BOM quantity
discrepancies, unknown components. WO 9374 serves as the regression test (run through the NEW
generalized pipeline, compared against the already-verified reference values); the other two
are synthetic fixtures (see engineering_engine/fixtures/) - real-world generalization is NOT
claimed from synthetic fixtures alone, only that the routing logic itself behaves correctly.
"""
from engineering_engine.fixtures import wo_edge_cases_002, wo_simple_001
from engineering_engine.main import wo_9374_inputs
from engineering_engine.routing.pipeline import build_components, process_work_order
from engineering_engine.routing.work_order_inputs import ComponentInput, WorkOrderInputs
from engineering_engine.validation.dimension_validator import DimensionStatus


def _dims(output, name):
    return next(c for c in output["components"] if c["name"] == name)


# --- WO 9374 regression, through the generalized pipeline ---------------------------------

def test_wo9374_regression_matches_previously_verified_values():
    output = process_work_order(wo_9374_inputs())
    assert output["work_order"] == "9374"
    bellows = _dims(output, "Bellows")
    assert bellows["final_proposed_dimensions"]["length"] == 1765
    assert bellows["final_proposed_dimensions"]["thickness"] == 0.6
    sleeve = _dims(output, "Sleeve")
    assert sleeve["final_proposed_dimensions"]["od"] == 509
    assert sleeve["final_proposed_dimensions"]["mid_pipe_interface_reference"] == 539.0
    mid_pipe = _dims(output, "Mid Pipe")
    assert mid_pipe["final_proposed_dimensions"]["id"] == 539.0
    m8 = _dims(output, "M8 Bolt & Nut")
    assert m8["total_quantity"] == 32
    assert m8["reference_indent_quantity"] == 48
    assert m8["quantity_discrepancy"] is True


def test_wo9374_duplicate_spec_match_reported_not_merged():
    output = process_work_order(wo_9374_inputs())
    names = [c["name"] for c in output["components"]]
    # Nut & Locknut and M8 Bolt & Nut both classify as BOLTS_AND_NUTS but remain SEPARATE entries.
    assert "Nut & Locknut" in names and "M8 Bolt & Nut" in names
    assert output["diagnostics"]["duplicate_spec_matches"].get("BOLTS_AND_NUTS") == ["Nut & Locknut", "M8 Bolt & Nut"]


# --- Multiple work orders / different component combinations -------------------------------

def test_simple_work_order_has_different_component_combination_than_wo9374():
    output = process_work_order(wo_simple_001.inputs())
    names = {c["name"] for c in output["components"]}
    assert names == {"Bellows", "Sleeve", "End Pipe", "Shroud"}  # no Mid Pipe, Housing Flange, Limit Rod, Collar
    assert output["assembly_quantity"] == 10
    assert output["work_order"] == "SIMPLE-001"


def test_simple_work_order_quantities_scale_by_its_own_assembly_quantity():
    output = process_work_order(wo_simple_001.inputs())
    end_pipe = _dims(output, "End Pipe")
    assert end_pipe["total_quantity"] == 20  # 2 per assembly * 10 assemblies, not WO 9374's 4


def test_extraction_unavailable_degrades_gracefully_not_a_crash():
    # wo_simple_001 has pdf_path=None - no OCR evidence at all. Every OD-dependent dimension
    # must come back MISSING, never a crash and never a guessed value.
    output = process_work_order(wo_simple_001.inputs())
    bellows = _dims(output, "Bellows")
    assert bellows["dimension_detail"]["od"]["status"] == "MISSING"
    assert bellows["dimension_detail"]["length"]["status"] == "MISSING"  # formula needs od
    assert output["diagnostics"]["extraction_available"] is True  # no pdf_path means no attempt, not a failure
    assert output["diagnostics"]["unaccounted_cad_rows"] == []


# --- Missing parameters / unapproved allowances --------------------------------------------

def test_missing_required_parameter_reports_missing_with_component_name():
    output = process_work_order(wo_edge_cases_002.inputs())
    mid_pipe = _dims(output, "Mid Pipe")
    assert "thickness" in mid_pipe["missing_inputs"]
    assert "id" in mid_pipe["missing_inputs"]  # id formula needs thickness too
    assert mid_pipe["status"] == "MISSING"


def test_unapproved_allowance_stays_review_required_across_work_orders():
    # Not a WO-9374-specific fact - the SAME unapproved-allowance rule applies to a completely
    # different work order's Shroud, proving the rule selection isn't hardcoded per drawing.
    output = process_work_order(wo_edge_cases_002.inputs())
    shroud = _dims(output, "Shroud")
    assert shroud["status"] == "REVIEW_REQUIRED"
    assert shroud["dimension_detail"]["length"]["status"] == "REVIEW_REQUIRED"


# --- Duplicate component identification -----------------------------------------------------

def test_duplicate_component_identification_two_bolt_rows_both_kept_separate():
    output = process_work_order(wo_edge_cases_002.inputs())
    names = [c["name"] for c in output["components"]]
    assert "M10 Bolt & Nut" in names and "Nut & Locknut" in names
    assert names.count("M10 Bolt & Nut") == 1 and names.count("Nut & Locknut") == 1  # each its own entry
    dup = output["diagnostics"]["duplicate_spec_matches"].get("BOLTS_AND_NUTS", [])
    assert set(dup) == {"M10 Bolt & Nut", "Nut & Locknut"}


# --- BOM quantity discrepancies ---------------------------------------------------------------

def test_bom_quantity_discrepancy_flagged_for_a_synthetic_work_order():
    output = process_work_order(wo_edge_cases_002.inputs())
    collar = _dims(output, "Collar")
    assert collar["total_quantity"] == 4  # 2 per assembly * 2 assemblies
    assert collar["reference_indent_quantity"] == 6
    assert collar["quantity_discrepancy"] is True


# --- Unknown components -----------------------------------------------------------------------

def test_unknown_component_reported_not_dropped():
    output = process_work_order(wo_edge_cases_002.inputs())
    names = [c["name"] for c in output["components"]]
    assert "Gasket" in names
    gasket = _dims(output, "Gasket")
    assert gasket["status"] == "REVIEW_REQUIRED"
    assert gasket["dimension_detail"]["classification"]["value"] == "UNCLASSIFIED"
    assert "Gasket" in output["diagnostics"]["unclassified_components"]


# --- Incorrect / ambiguous dimension mapping --------------------------------------------------

def test_explicit_spec_identifier_override_bypasses_text_classification():
    # A component whose printed description wouldn't classify on its own can still be routed
    # correctly via an explicit override - lets a reviewer correct an ambiguous/wrong mapping
    # without the routing logic itself guessing.
    wo = WorkOrderInputs(
        work_order="OVERRIDE-TEST", assembly_quantity=1, pdf_path=None,
        components=[ComponentInput(description="Item 7 (see drawing note)", spec_identifier="MID_PIPE",
                                    manual={"thickness": 5, "length": 50})],
    )
    output = process_work_order(wo)
    item = output["components"][0]
    assert item["dimension_detail"]["id"]["status"] != "MISSING" or "od" in item["missing_inputs"]
    assert item["status"] in ("MISSING", "CALCULATED")  # routed through pipe_calculator, not left UNCLASSIFIED
    assert "classification" not in item["dimension_detail"]


def test_bad_explicit_spec_identifier_falls_back_to_text_classification():
    wo = WorkOrderInputs(
        work_order="BAD-OVERRIDE-TEST", assembly_quantity=1, pdf_path=None,
        components=[ComponentInput(description="Bellows", spec_identifier="NOT_A_REAL_SPEC", manual={})],
    )
    output = process_work_order(wo)
    # Falls back to classifying "Bellows" by text since the override identifier doesn't exist.
    assert output["components"][0]["status"] != "REVIEW_REQUIRED" or "classification" not in output["components"][0]["dimension_detail"]


# --- build_components() (non-JSON) path, backward-compat with the old build_wo9374_components interface ---

def test_build_components_returns_component_output_objects_directly():
    components, diagnostics = build_components(wo_9374_inputs())
    assert len(components) == 15
    assert all(hasattr(c, "to_dict") for c in components)
    assert diagnostics.duplicate_spec_matches.get("BOLTS_AND_NUTS") == ["Nut & Locknut", "M8 Bolt & Nut"]
