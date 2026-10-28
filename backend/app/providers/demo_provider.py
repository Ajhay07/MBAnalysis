from __future__ import annotations

from app.providers.base import DrawingAnalysisProvider
from app.schemas.analysis import (
    AnalysisResult, TitleBlock, DimensionFinding, ComponentCandidate,
    ViewType, RepeatedFeature, Ambiguity,
)


class DemoProvider(DrawingAnalysisProvider):
    """Returns realistic, clearly-labeled precomputed analysis results.
    Used only for the seeded showcase project (set AI_PROVIDER=demo) - DeterministicProvider is
    the real no-key default (see app.providers.get_provider). Never used for a real uploaded
    drawing's persisted analysis path (see services.analysis_pipeline)."""

    name = "demo"

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        return AnalysisResult(
            provider="demo",
            title_block=TitleBlock(
                drawing_number=drawing_number or "DEMO-0000",
                title="[DEMO] Generic Precomputed Part",
                revision="A",
                units="mm",
                scale="1:2",
                material_spec="See BOM",
            ),
            dimensions=[
                DimensionFinding(label="[DEMO] Overall Length", value="120.0", tolerance="+/-0.1",
                                  page=1, source_text="demo placeholder", confidence=0.5),
            ],
            materials=["[DEMO] Steel, Generic"],
            components=[
                ComponentCandidate(
                    part_number="DEMO-COMP-1",
                    description="[DEMO] Placeholder component (no real drawing analyzed)",
                    category="Generic",
                    quantity=1,
                    material="Steel",
                    make_buy="Review",
                    confidence=0.4,
                    verification_status="Unverified",
                    source_page=1,
                    source_text="demo placeholder - not derived from an uploaded drawing",
                    quantity_basis="explicit_callout",
                    component_type="manufactured",
                ),
                ComponentCandidate(
                    part_number="DEMO-COMP-2",
                    description="[DEMO] Hex bolt, M6x20 (from counted hole pattern)",
                    category="Fastener",
                    quantity=6,
                    material="Steel",
                    make_buy="Buy",
                    confidence=0.6,
                    verification_status="Unverified",
                    source_page=1,
                    source_text="demo placeholder - 6 identical through-holes counted on page 1",
                    quantity_basis="counted_feature",
                    component_type="purchased",
                ),
            ],
            raw_ocr_text=ocr_text,
            overall_confidence=0.45,
            view_types=[
                ViewType(view_type="front", page=1, source_region={"x": 0, "y": 0, "w": 100, "h": 100}),
                ViewType(view_type="isometric", page=1, source_region={"x": 100, "y": 0, "w": 100, "h": 100}),
            ],
            repeated_features=[
                RepeatedFeature(
                    feature_type="through_hole",
                    count=6,
                    page=1,
                    source_region={"x": 10, "y": 10, "w": 80, "h": 80},
                    source_text="demo placeholder - 6 identical holes visible in front view",
                ),
            ],
            ambiguities=[
                Ambiguity(description="[DEMO] Material grade callout partially illegible on title block", page=1),
            ],
            missing_info=["[DEMO] Surface finish not specified for DEMO-COMP-1"],
        )
