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
    job_stage: str | None = None
    job_retry_count: int | None = None
    job_failure_reason: str | None = None

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
    quantity_basis: str | None = None
    component_type: str | None = None
    parent_part_number: str | None = None
    is_assumption: bool | None = None
    assumption_text: str | None = None
    catalog_component_id: str | None = None
    catalog_match_score: float | None = None

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
    page_count: int = 1
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
    total_quantity: float | None = None
    material: str
    make_buy: str
    unit_cost: float | None = None
    parent_line_item_id: str | None = None
    component_id: str | None = None
    catalog_component_id: str | None = None

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
    parent_line_item_id: str | None = None


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
    stock_quantity: float | None = None


class CatalogComponentOut(CatalogComponentIn):
    id: str
    model_config = {"from_attributes": True}


class InventoryLotIn(BaseModel):
    material_code: str | None = None
    material: str = ""
    grade: str = ""
    description: str = ""
    unit: str = "ea"
    on_hand_qty: float = 0
    reserved_qty: float = 0
    quarantined_qty: float = 0
    location: str | None = None
    lot_number: str | None = None
    supplier_id: str | None = None


class InventoryLotOut(BaseModel):
    id: str
    material_code: str | None = None
    material: str
    grade: str
    description: str
    unit: str
    on_hand_qty: float
    reserved_qty: float
    quarantined_qty: float
    location: str | None = None
    lot_number: str | None = None
    supplier_id: str | None = None
    is_demo: bool

    model_config = {"from_attributes": True}


class AvailabilityLineOut(BaseModel):
    bom_line_item_id: str
    part_number: str
    description: str
    material: str
    grade: str
    unit: str
    required_quantity: float | None = None
    on_hand: float
    reserved: float
    quarantined: float
    usable_available: float
    this_job_allocation: float
    net_shortage: float | None = None
    status: str
    explanation: str
    matched_lot_ids: list[str] = []
    supplier_name: str | None = None
    lead_time_days: int | None = None


class AvailabilityReportOut(BaseModel):
    bom_id: str
    production_quantity: float
    summary: dict[str, int]
    lines: list[AvailabilityLineOut]


class RequisitionLineOut(BaseModel):
    id: str
    material_code: str
    description: str
    quantity: float
    unit: str
    supplier_id: str | None = None
    catalog_component_id: str | None = None
    unit_cost: float | None = None

    model_config = {"from_attributes": True}


class RequisitionOut(BaseModel):
    id: str
    bom_id: str
    status: str
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    lines: list[RequisitionLineOut] = []

    model_config = {"from_attributes": True}


class AllocationIn(BaseModel):
    bom_id: str
    inventory_lot_id: str
    quantity: float


class AllocationOut(BaseModel):
    id: str
    inventory_lot_id: str
    bom_id: str
    quantity: float
    status: str

    model_config = {"from_attributes": True}


class IndentLineOut(BaseModel):
    id: str
    sl_no: int
    mtl_spec: str
    size_text: str
    wt_qty: float | None = None
    unit: str
    bom_line_item_id: str | None = None
    indent_rule_id: str | None = None
    source: str
    requires_confirmation: bool
    note: str

    model_config = {"from_attributes": True}


class IndentOut(BaseModel):
    id: str
    bom_id: str
    drawing_id: str
    version: int
    wo_number: str
    party_name: str
    required_on: str
    serial_no: str
    indent_date: str
    assembly_quantity: float
    status: str
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    lines: list[IndentLineOut] = []

    model_config = {"from_attributes": True}


class IndentGenerateRequest(BaseModel):
    assembly_quantity: float
    wo_number: str = ""
    party_name: str = ""
    required_on: str = ""
    serial_no: str = ""
    indent_date: str = ""
    rule_ids: list[str] = []


class IndentRuleIn(BaseModel):
    name: str
    mtl_spec: str = ""
    size_text: str = ""
    unit: str = "Pcs"
    formula: str = "manual_required"  # fixed_qty | per_assembly | manual_required
    value: float | None = None
    notes: str = ""
    active: bool = True


class IndentRuleOut(BaseModel):
    id: str
    name: str
    mtl_spec: str
    size_text: str
    unit: str
    formula: str
    value: float | None = None
    notes: str
    active: bool
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardMetrics(BaseModel):
    total_drawings: int
    status_breakdown: dict[str, int]
    total_bom_items: int
    make_count: int
    buy_count: int
    review_count: int
    recent_activity: list[dict]
