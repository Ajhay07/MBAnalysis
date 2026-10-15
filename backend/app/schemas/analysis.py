from __future__ import annotations

from pydantic import BaseModel, Field


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


class AnalysisResult(BaseModel):
    provider: str
    title_block: TitleBlock
    dimensions: list[DimensionFinding] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    raw_ocr_text: str = ""
    overall_confidence: float = 0.0
