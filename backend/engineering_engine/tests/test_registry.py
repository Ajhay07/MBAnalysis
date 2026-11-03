"""Component registry + classification tests - no PDF, no pipeline, just the matching logic."""
from engineering_engine.routing import component_builders  # noqa: F401 - registers specs
from engineering_engine.routing.registry import REGISTRY, classify_component, list_registered_components


def test_all_fourteen_components_are_registered():
    expected = {
        "BELLOWS", "SHROUD", "MID_PIPE", "END_PIPE", "SLEEVE", "HOUSING_FLANGE", "LIMIT_ROD",
        "COLLAR", "SHROUD_SUPPORT", "STIFFENER", "WOODEN_BOX", "BOLTS_AND_NUTS", "FILLER_WIRE",
        "ELECTRODE",
    }
    assert set(REGISTRY.keys()) == expected


def test_every_spec_has_a_builder_attached():
    for spec in REGISTRY.values():
        assert spec.builder is not None, f"{spec.identifier} has no builder"


def test_list_registered_components_returns_plain_dicts():
    listing = list_registered_components()
    assert len(listing) == 14
    assert all(isinstance(d, dict) and "identifier" in d for d in listing)


def test_classify_exact_alias_match():
    assert classify_component("BELLOWS").identifier == "BELLOWS"
    assert classify_component("Mid Pipe").identifier == "MID_PIPE"


def test_classify_tolerates_ocr_truncation():
    # Confirmed real-world necessity this session: "SLEEVE" OCR'd as "SLEEV".
    assert classify_component("SLEEV").identifier == "SLEEVE"


def test_classify_unknown_component_returns_none():
    assert classify_component("Gasket") is None
    assert classify_component("Random Widget XYZ") is None


def test_classify_empty_or_blank_returns_none():
    assert classify_component("") is None
    assert classify_component(None) is None


def test_classify_bolts_and_nuts_variants():
    assert classify_component("Nut & Locknut").identifier == "BOLTS_AND_NUTS"
    assert classify_component("M8 Bolt & Nut").identifier == "BOLTS_AND_NUTS"
    assert classify_component("M10 Bolt & Nut").identifier == "BOLTS_AND_NUTS"


def test_classify_never_confuses_mid_pipe_and_end_pipe():
    # Ambiguous-dimension-mapping regression: these must never cross-classify.
    assert classify_component("Mid Pipe").identifier == "MID_PIPE"
    assert classify_component("End Pipe").identifier == "END_PIPE"
    assert classify_component("MID PIPE DETAIL") is not None
    assert classify_component("MID PIPE DETAIL").identifier == "MID_PIPE"


def test_classify_housing_flange_not_confused_with_sleeve_flange_style_names():
    # "FLANGE" alone is a HOUSING_FLANGE alias; a compound name should still resolve sensibly
    # rather than silently picking the wrong spec.
    assert classify_component("Housing Flange").identifier == "HOUSING_FLANGE"
