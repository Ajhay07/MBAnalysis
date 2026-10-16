from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ViewType(BaseModel):
    """One drawing view observed on a page (front/side/top/section/isometric/unknown)."""
    view_type: str = "unknown"
    page: int = 1
    source_region: dict = Field(default_factory=dict)


class RepeatedFeature(BaseModel):
    """A geometric feature (hole, slot, etc.) observed repeated N times on the drawing.
    This is the deterministic basis for fastener/bushing quantity candidates - never
    another AI guess, but a direct count the vision step reported with evidence."""
    feature_type: str = ""
    count: int = 0
    page: int = 1
    source_region: dict = Field(default_factory=dict)
    source_text: str = ""
    is_assumption: bool = False
    assumption_text: str = ""

    @model_validator(mode="after")
    def _require_evidence(self):
        if not self.source_text and not self.is_assumption:
            raise ValueError("RepeatedFeature requires source_text evidence or is_assumption+assumption_text")
        if self.is_assumption and not self.assumption_text:
            raise ValueError("is_assumption=True requires assumption_text")
        return self


class Ambiguity(BaseModel):
    """An explicit flag the vision step raised: missing dimension, conflicting callout, etc.
    Never silently resolved - surfaced to the reviewer."""
    description: str
    page: int = 1
    source_region: dict = Field(default_factory=dict)


class TitleBlock(BaseModel):
    drawing_number: str = ""
    title: str = ""
    revision: str = "A"
    units: str = "mm"
    scale: str = ""
    material_spec: str = ""


class DimensionFinding(BaseModel):
    label: str
    value: str
    tolerance: str | None = None
    page: int = 1
    source_text: str = ""
    confidence: float = 0.0


class ComponentCandidate(BaseModel):
    part_number: str = ""
    description: str = ""
    category: str = ""
    quantity: float = 1
    material: str = ""
    grade: str = ""
    dimensions: dict = Field(default_factory=dict)
    tolerances: dict = Field(default_factory=dict)
    gear_specs: dict = Field(default_factory=dict)
    make_buy: str = "Review"
    confidence: float = 0.0
    verification_status: str = "Unverified"
    source_page: int = 1
    source_region: dict = Field(default_factory=dict)
    source_text: str = ""
    # Richer geometry/annotation fields (quantity-basis + component classification).
    quantity_basis: str = "assumed"  # "explicit_callout" | "counted_feature" | "assumed"
    component_type: str = "purchased"  # "raw_material" | "purchased" | "manufactured" | "assembly"
    parent_part_number: str | None = None
    is_assumption: bool = False
    assumption_text: str = ""

    @model_validator(mode="after")
    def _require_evidence(self):
        if not self.source_text and not self.is_assumption:
            raise ValueError("ComponentCandidate requires source_text evidence or is_assumption+assumption_text")
        if self.is_assumption and not self.assumption_text:
            raise ValueError("is_assumption=True requires assumption_text")
        return self


class AnalysisResult(BaseModel):
    provider: str
    title_block: TitleBlock
    dimensions: list[DimensionFinding] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    raw_ocr_text: str = ""
    overall_confidence: float = 0.0
    # New richer geometry/annotation-driven fields (step 2 of BOM-source-change spec).
    view_types: list[ViewType] = Field(default_factory=list)
    repeated_features: list[RepeatedFeature] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
