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

    analysis = relationship("Analysis", back_populates="components")


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


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    actor = Column(String, default="system")
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=gen_id)
    drawing_id = Column(String, ForeignKey("drawings.id"), nullable=False)
    job_type = Column(String, default="analysis")
    status = Column(String, default="Pending")  # Pending/Running/Done/Failed
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
