from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class DrawingOut(BaseModel):
    id: str
    drawing_number: str
    title: str
    revision: str
    file_name: str
    file_type: str
    file_size: int
    units: str
    scale: str
    status: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ComponentOut(BaseModel):
    id: str
    part_number: str
    description: str
    category: str
    quantity: float
    material: str
    grade: str
    dimensions: dict
    tolerances: dict
    gear_specs: dict
    make_buy: str
    confidence: float
    verification_status: str
    source_page: int
    source_region: dict
    source_text: str
    parent_component_id: str | None = None

    model_config = {"from_attributes": True}


class AnalysisOut(BaseModel):
    id: str
    drawing_id: str
    version: int
    provider: str
    title_block: dict
    dimensions: list
    materials: list
    raw_ocr_text: str
    overall_confidence: float
    created_at: datetime
    components: list[ComponentOut] = []

    model_config = {"from_attributes": True}


class ComponentUpdate(BaseModel):
    part_number: str | None = None
    description: str | None = None
    category: str | None = None
    quantity: float | None = None
    material: str | None = None
    grade: str | None = None
    make_buy: str | None = None
    verification_status: str | None = None


class BomLineItemOut(BaseModel):
    id: str
    part_number: str
    description: str
    category: str
    quantity: float
    material: str
    make_buy: str
    unit_cost: float | None = None
    parent_line_item_id: str | None = None
    component_id: str | None = None

    model_config = {"from_attributes": True}


class BomOut(BaseModel):
    id: str
    drawing_id: str
    analysis_id: str
    version: int
    status: str
    created_at: datetime
    line_items: list[BomLineItemOut] = []

    model_config = {"from_attributes": True}


class BomLineItemUpdate(BaseModel):
    part_number: str | None = None
    description: str | None = None
    category: str | None = None
    quantity: float | None = None
    material: str | None = None
    make_buy: str | None = None
    unit_cost: float | None = None


class SupplierIn(BaseModel):
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


class SupplierOut(SupplierIn):
    id: str
    model_config = {"from_attributes": True}


class CatalogComponentIn(BaseModel):
    part_number: str
    description: str = ""
    category: str = ""
    supplier_id: str | None = None
    unit_price: float | None = None
    currency: str | None = None


class CatalogComponentOut(CatalogComponentIn):
    id: str
    model_config = {"from_attributes": True}


class DashboardMetrics(BaseModel):
    total_drawings: int
    status_breakdown: dict[str, int]
    total_bom_items: int
    make_count: int
    buy_count: int
    review_count: int
    recent_activity: list[dict]
