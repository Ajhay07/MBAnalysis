from __future__ import annotations

import pytest

from app.providers.demo_provider import DemoProvider
from app.schemas.analysis import ComponentCandidate, RepeatedFeature
from app.services.bom_candidate_service import (
    build_candidate_bom,
    candidates_from_repeated_features,
    missing_info_report,
)


def test_repeated_feature_yields_quantity_derived_fastener_candidate():
    result = DemoProvider().analyze(image_path="x", ocr_text="", drawing_number="DEMO-1")
    candidates = candidates_from_repeated_features(result)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.quantity == 6
    assert c.quantity_basis == "counted_feature"
    assert c.component_type == "purchased"
    assert c.source_text  # evidence present


def test_build_candidate_bom_merges_provider_components_and_derived_fasteners():
    result = DemoProvider().analyze(image_path="x", ocr_text="", drawing_number="DEMO-1")
    merged = build_candidate_bom(result)
    assert len(merged) == len(result.components) + 1


def test_missing_info_report_includes_ambiguities():
    result = DemoProvider().analyze(image_path="x", ocr_text="", drawing_number="DEMO-1")
    report = missing_info_report(result)
    assert any("Ambiguity" in r for r in report)
    assert any("Surface finish" in r for r in report)


def test_component_candidate_rejects_entry_with_no_evidence_and_no_assumption_flag():
    with pytest.raises(ValueError):
        ComponentCandidate(description="mystery part", source_text="", is_assumption=False)


def test_component_candidate_allows_explicit_assumption_with_text():
    c = ComponentCandidate(description="assumed qty 1", is_assumption=True, assumption_text="no callout visible")
    assert c.is_assumption is True


def test_repeated_feature_rejects_entry_with_no_evidence():
    with pytest.raises(ValueError):
        RepeatedFeature(feature_type="through_hole", count=4, source_text="", is_assumption=False)


def test_non_fastener_feature_type_is_not_turned_into_a_candidate():
    result = DemoProvider().analyze(image_path="x", ocr_text="", drawing_number="DEMO-1")
    result.repeated_features[0].feature_type = "decorative_groove"
    assert candidates_from_repeated_features(result) == []
