from __future__ import annotations

import os

import numpy as np
from sqlalchemy.orm import Session

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from app.config import get_settings
from app.models.models import Analysis, Component, Drawing, DrawingStatus, AuditLog, Job
from app.providers import get_provider
from app.services.classification import classify_component
from app.services.ocr import run_ocr


def drawing_abspath(drawing: Drawing) -> str:
    settings = get_settings()
    return os.path.abspath(os.path.join(settings.UPLOAD_DIR, drawing.stored_file_name))


def _load_image_array(path: str) -> np.ndarray | None:
    if cv2 is None:
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return None  # PDF page rasterization is out of scope for this preprocessing step
    img = cv2.imread(path)
    return img


def run_analysis(db: Session, drawing: Drawing, actor: str = "system") -> Analysis:
    """Full pipeline: OCR -> AI provider (OpenAI vision or demo) -> persist versioned analysis
    with components. Never substitutes seeded demo content for a real drawing - the provider
    is invoked fresh against this drawing's own file every time."""
    job = Job(drawing_id=drawing.id, job_type="analysis", status="Running")
    db.add(job)
    drawing.status = DrawingStatus.PROCESSING
    db.commit()

    try:
        path = drawing_abspath(drawing)
        image = _load_image_array(path)
        ocr_text = ""
        if image is not None:
            ocr_result = run_ocr(image)
            ocr_text = ocr_result.text

        provider = get_provider()
        result = provider.analyze(
            image_path=path, ocr_text=ocr_text,
            drawing_number=drawing.drawing_number,
        )

        version = db.query(Analysis).filter(Analysis.drawing_id == drawing.id).count() + 1
        analysis = Analysis(
            drawing_id=drawing.id,
            version=version,
            provider=result.provider,
            title_block=result.title_block.model_dump(),
            dimensions=[d.model_dump() for d in result.dimensions],
            materials=result.materials,
            raw_ocr_text=result.raw_ocr_text,
            overall_confidence=result.overall_confidence,
        )
        db.add(analysis)
        db.flush()

        for comp in result.components:
            make_buy = comp.make_buy if comp.make_buy in ("Make", "Buy", "Review") else classify_component(
                comp.category, comp.description, comp.confidence)
            db.add(Component(
                analysis_id=analysis.id,
                part_number=comp.part_number,
                description=comp.description,
                category=comp.category,
                quantity=comp.quantity,
                material=comp.material,
                grade=comp.grade,
                dimensions=comp.dimensions,
                tolerances=comp.tolerances,
                gear_specs=comp.gear_specs,
                make_buy=make_buy,
                confidence=comp.confidence,
                verification_status=comp.verification_status,
                source_page=comp.source_page,
                source_region=comp.source_region,
                source_text=comp.source_text,
            ))

        needs_review = any(c.confidence < 0.6 for c in result.components) or not result.components
        drawing.status = DrawingStatus.NEEDS_REVIEW if needs_review else DrawingStatus.REVIEWED
        job.status = "Done"
        db.add(AuditLog(entity_type="drawing", entity_id=drawing.id, action="analyzed",
                         details={"provider": result.provider, "analysis_id": analysis.id},
                         actor=actor))
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as exc:
        drawing.status = DrawingStatus.FAILED
        drawing.error_message = str(exc)
        job.status = "Failed"
        job.error_message = str(exc)
        db.commit()
        raise
