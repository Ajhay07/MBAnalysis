import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex


class DrawingStatus(str, enum.Enum):
    UPLOADED = "Uploaded"
    QUEUED = "Queued"
    PROCESSING = "Processing"
    NEEDS_REVIEW = "NeedsReview"
    REVIEWED = "Reviewed"
    BOM_GENERATED = "BOMGenerated"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class MakeBuy(str, enum.Enum):
    MAKE = "Make"
    BUY = "Buy"
    REVIEW = "Review"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Drawing(Base):
    __tablename__ = "drawings"

    id = Column(String, primary_key=True, default=gen_id)
    drawing_number = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="")
    revision = Column(String, nullable=False, default="A")
    file_name = Column(String, nullable=False)
    stored_file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    units = Column(String, default="mm")
    scale = Column(String, default="")
    status = Column(SAEnum(DrawingStatus), default=DrawingStatus.UPLOADED, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(Text, nullable=True)

    analyses = relationship("Analysis", back_populates="drawing", cascade="all, delete-orphan")
    boms = relationship("Bom", back_populates="drawing", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="drawing", cascade="all, delete-orphan",
                         order_by="Job.created_at")

    @property
    def _latest_job(self):
        return max(self.jobs, key=lambda j: j.created_at, default=None) if self.jobs else None

    @property
    def job_stage(self) -> str | None:
        job = self._latest_job
        if not job:
            return None
        return job.stage.value if hasattr(job.stage, "value") else job.stage

    @property
    def job_retry_count(self) -> int | None:
        job = self._latest_job
        return job.retry_count if job else None

    @property
    def job_failure_reason(self) -> str | None:
        job = self._latest_job
        return job.failure_reason if job else None


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=gen_id)
    drawing_id = Column(String, ForeignKey("drawings.id"), nullable=False)
    version = Column(Integer, default=1)
    provider = Column(String, default="demo")
    title_block = Column(JSON, default=dict)
    dimensions = Column(JSON, default=list)
    materials = Column(JSON, default=list)
    raw_ocr_text = Column(Text, default="")
    overall_confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    drawing = relationship("Drawing", back_populates="analyses")
    components = relationship("Component", back_populates="analysis", cascade="all, delete-orphan")
    reference_bom_tables = relationship(
        "ReferenceBomTable", back_populates="analysis", cascade="all, delete-orphan")

    @property
    def page_count(self) -> int:
        """Highest source_page across this analysis's components (and recorded dimensions),
        i.e. how many pages the frontend should let the user page through. Derived, not
        persisted - no migration needed since it is computed from existing data."""
        pages = [c.source_page or 1 for c in self.components]
        pages.extend(d.get("page", 1) for d in (self.dimensions or []) if isinstance(d, dict))
        return max(pages) if pages else 1


class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, default=gen_id)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=False)
    parent_component_id = Column(String, ForeignKey("components.id"), nullable=True)
    part_number = Column(String, default="")
    description = Column(String, default="")
    category = Column(String, default="")
    quantity = Column(Float, default=1)
    material = Column(String, default="")
    grade = Column(String, default="")
    dimensions = Column(JSON, default=dict)
    tolerances = Column(JSON, default=dict)
    gear_specs = Column(JSON, default=dict)
    make_buy = Column(SAEnum(MakeBuy), default=MakeBuy.REVIEW)
    confidence = Column(Float, default=0.0)
    verification_status = Column(String, default="Unverified")  # Unverified/Verified/Rejected
    source_page = Column(Integer, default=1)
    source_region = Column(JSON, default=dict)  # bbox
    source_text = Column(Text, default="")
    quantity_basis = Column(String, default="assumed", nullable=True)  # explicit_callout/counted_feature/assumed
    component_type = Column(String, default="purchased", nullable=True)  # raw_material/purchased/manufactured/assembly
    parent_part_number = Column(String, nullable=True)
    is_assumption = Column(Boolean, default=False, nullable=True)
    assumption_text = Column(Text, default="", nullable=True)

    analysis = relationship("Analysis", back_populates="components")


class ReferenceBomTable(Base):
    """A detected printed BOM table on a drawing page (app.services.reference_bom_service's
    OCR-layout heuristic). Strictly read-only evidence - kept entirely separate from, and
    never overwritten/reconciled by, the geometry-derived candidate Component rows. Used only
    to compute an on-demand discrepancy report for a human reviewer."""
    __tablename__ = "reference_bom_tables"

    id = Column(String, primary_key=True, default=gen_id)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=False)
    page_number = Column(Integer, default=1)
    matched_headers = Column(JSON, default=list)
    bbox = Column(JSON, default=dict)
    raw_text = Column(Text, default="")
    row_count_estimate = Column(Integer, default=0)
    detected_at = Column(DateTime, default=datetime.utcnow)

    analysis = relationship("Analysis", back_populates="reference_bom_tables")


class Bom(Base):
    __tablename__ = "boms"

    id = Column(String, primary_key=True, default=gen_id)
    drawing_id = Column(String, ForeignKey("drawings.id"), nullable=False)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String, default="Draft")  # Draft/Approved/Rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    drawing = relationship("Drawing", back_populates="boms")
    line_items = relationship("BomLineItem", back_populates="bom", cascade="all, delete-orphan")


class BomLineItem(Base):
    __tablename__ = "bom_line_items"

    id = Column(String, primary_key=True, default=gen_id)
    bom_id = Column(String, ForeignKey("boms.id"), nullable=False)
    parent_line_item_id = Column(String, ForeignKey("bom_line_items.id"), nullable=True)
    component_id = Column(String, ForeignKey("components.id"), nullable=True)
    part_number = Column(String, default="")
    description = Column(String, default="")
    category = Column(String, default="")
    quantity = Column(Float, default=1)
    material = Column(String, default="")
    make_buy = Column(SAEnum(MakeBuy), default=MakeBuy.REVIEW)
    unit_cost = Column(Float, nullable=True)
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=True)
    # `quantity` is qty-per-assembly (how many go into the direct parent, or the
    # top-level count if there is no parent). `total_quantity` is the rolled-up
    # quantity required overall across the nested assembly chain; left null when
    # the chain's multiplicity cannot be determined.
    total_quantity = Column(Float, nullable=True)

    bom = relationship("Bom", back_populates="line_items")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class CatalogComponent(Base):
    __tablename__ = "catalog_components"

    id = Column(String, primary_key=True, default=gen_id)
    part_number = Column(String, nullable=False, index=True)
    description = Column(String, default="")
    category = Column(String, default="")
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=True)
    unit_price = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    # Minimum order quantity / reorder quantity. Nullable: only populated when real catalog/
    # supplier data provides it - never fabricated for existing demo rows (see inventory spec).
    moq = Column(Float, nullable=True)
    lead_time_days = Column(Integer, nullable=True)


class RequisitionStatus(str, enum.Enum):
    DRAFT = "Draft"
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class InventoryLot(Base):
    """A physical lot/batch of material or stocked component. Quantities are stored as strings
    and parsed to Decimal at the service layer (SQLite has no native Decimal type) so arithmetic
    never silently drifts through float rounding."""
    __tablename__ = "inventory_lots"

    id = Column(String, primary_key=True, default=gen_id)
    # Matches BomLineItem.part_number / CatalogComponent.part_number for exact-code matching.
    material_code = Column(String, nullable=True, index=True)
    material = Column(String, default="")
    grade = Column(String, default="")
    description = Column(String, default="")
    unit = Column(String, default="ea")
    on_hand_qty = Column(String, default="0")
    reserved_qty = Column(String, default="0")  # total reserved across ALL jobs/allocations
    quarantined_qty = Column(String, default="0")
    location = Column(String, nullable=True)
    lot_number = Column(String, nullable=True)
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=True)
    received_date = Column(DateTime, nullable=True)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    allocations = relationship("InventoryAllocation", back_populates="lot", cascade="all, delete-orphan")


class InventoryAllocation(Base):
    """Reserves a quantity of a specific InventoryLot for a specific BOM (production run), so
    stock already secured for THIS job can be distinguished from stock held for other jobs."""
    __tablename__ = "inventory_allocations"

    id = Column(String, primary_key=True, default=gen_id)
    inventory_lot_id = Column(String, ForeignKey("inventory_lots.id"), nullable=False)
    bom_id = Column(String, ForeignKey("boms.id"), nullable=False)
    material_code = Column(String, nullable=True)
    quantity = Column(String, nullable=False)  # Decimal-as-string
    status = Column(String, default="active")  # active/released
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String, default="system")

    lot = relationship("InventoryLot", back_populates="allocations")


class PurchaseRequisition(Base):
    """Minimal requisition entity: groups shortage lines for a BOM, goes through the same
    draft -> approve/reject pattern as BOM approval, reusing require_role for gating."""
    __tablename__ = "purchase_requisitions"

    id = Column(String, primary_key=True, default=gen_id)
    bom_id = Column(String, ForeignKey("boms.id"), nullable=False)
    status = Column(SAEnum(RequisitionStatus), default=RequisitionStatus.DRAFT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String, default="system")
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)

    lines = relationship("PurchaseRequisitionLine", back_populates="requisition",
                          cascade="all, delete-orphan")


class PurchaseRequisitionLine(Base):
    __tablename__ = "purchase_requisition_lines"

    id = Column(String, primary_key=True, default=gen_id)
    requisition_id = Column(String, ForeignKey("purchase_requisitions.id"), nullable=False)
    material_code = Column(String, default="")
    description = Column(String, default="")
    quantity = Column(String, nullable=False)  # Decimal-as-string (net shortage at creation time)
    unit = Column(String, default="ea")
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=True)
    catalog_component_id = Column(String, ForeignKey("catalog_components.id"), nullable=True)
    unit_cost = Column(Float, nullable=True)

    requisition = relationship("PurchaseRequisition", back_populates="lines")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    actor = Column(String, default="system")
    created_at = Column(DateTime, default=datetime.utcnow)


class JobStage(str, enum.Enum):
    QUEUED = "queued"
    EXTRACTING_PAGES = "extracting_pages"
    OCR = "ocr"
    VISION_ANALYSIS = "vision_analysis"
    PERSISTING = "persisting"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    BOM_GENERATED = "bom_generated"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=gen_id)
    drawing_id = Column(String, ForeignKey("drawings.id"), nullable=False)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=True)
    job_type = Column(String, default="analysis")
    status = Column(String, default="Pending")  # Pending/Running/Done/Failed
    stage = Column(SAEnum(JobStage), default=JobStage.QUEUED, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    drawing = relationship("Drawing", back_populates="jobs")
