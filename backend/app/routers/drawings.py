from __future__ import annotations

import os

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.config import get_settings
from app.database import get_db
from app.models.models import Drawing, DrawingStatus, Analysis, AuditLog, User
from app.schemas.api import DrawingOut, AnalysisOut
from app.services.analysis_pipeline import run_analysis, drawing_abspath, page_preview_path, PdfProcessingError
from app.services.file_validation import (
    FileValidationError, validate_extension, validate_size, build_stored_path,
    validate_content_matches_extension,
)

router = APIRouter(prefix="/api/drawings", tags=["drawings"])

editor = require_role("admin", "engineer")


@router.post("", response_model=DrawingOut)
async def upload_drawing(
    file: UploadFile = File(...),
    drawing_number: str = Form(...),
    title: str = Form(""),
    revision: str = Form("A"),
    db: Session = Depends(get_db),
    current_user: User = Depends(editor),
):
    settings = get_settings()
    try:
        ext = validate_extension(file.filename)
        contents = await file.read()
        validate_size(len(contents))
        validate_content_matches_extension(ext, contents[:16])
        stored_name, abs_path = build_stored_path(settings.UPLOAD_DIR, file.filename)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    with open(abs_path, "wb") as f:
        f.write(contents)

    drawing = Drawing(
        drawing_number=drawing_number,
        title=title,
        revision=revision,
        file_name=os.path.basename(file.filename),
        stored_file_name=stored_name,
        file_type=ext.lstrip("."),
        file_size=len(contents),
        status=DrawingStatus.UPLOADED,
        is_demo=False,
    )
    db.add(drawing)
    db.add(AuditLog(entity_type="drawing", entity_id=drawing.id if drawing.id else "pending",
                     action="uploaded", details={"file_name": file.filename},
                     actor=current_user.email))
    db.commit()
    db.refresh(drawing)
    return drawing


@router.get("", response_model=list[DrawingOut])
def list_drawings(
    q: str | None = None,
    status: str | None = None,
    sort: str = "created_at_desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Drawing)
    if q:
        like = f"%{q}%"
        query = query.filter((Drawing.drawing_number.ilike(like)) | (Drawing.title.ilike(like)))
    if status:
        query = query.filter(Drawing.status == status)
    sort_map = {
        "created_at_desc": Drawing.created_at.desc(),
        "created_at_asc": Drawing.created_at.asc(),
        "drawing_number_asc": Drawing.drawing_number.asc(),
    }
    query = query.order_by(sort_map.get(sort, Drawing.created_at.desc()))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.get("/{drawing_id}", response_model=DrawingOut)
def get_drawing(drawing_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    drawing = db.query(Drawing).get(drawing_id)
    if not drawing:
        raise HTTPException(404, "Drawing not found")
    return drawing


@router.get("/{drawing_id}/file")
def get_drawing_file(drawing_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    drawing = db.query(Drawing).get(drawing_id)
    if not drawing:
        raise HTTPException(404, "Drawing not found")
    path = drawing_abspath(drawing)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path, filename=drawing.file_name)


@router.delete("/{drawing_id}")
def delete_drawing(drawing_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(editor)):
    drawing = db.query(Drawing).get(drawing_id)
    if not drawing:
        raise HTTPException(404, "Drawing not found")
    path = drawing_abspath(drawing)
    db.delete(drawing)
    db.add(AuditLog(entity_type="drawing", entity_id=drawing_id, action="deleted", details={},
                     actor=current_user.email))
    db.commit()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return {"ok": True}


@router.post("/{drawing_id}/analyze", response_model=AnalysisOut)
def analyze_drawing(drawing_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(editor)):
    drawing = db.query(Drawing).get(drawing_id)
    if not drawing:
        raise HTTPException(404, "Drawing not found")
    drawing.status = DrawingStatus.QUEUED
    db.commit()
    try:
        analysis = run_analysis(db, drawing, actor=current_user.email)
    except PdfProcessingError as exc:
        # run_analysis already marked the Drawing Failed with this reason and committed it;
        # surface it as a clean 422 rather than an unhandled 500.
        raise HTTPException(status_code=422, detail=str(exc))
    return analysis


@router.get("/{drawing_id}/pages/{page_number}/preview")
def get_drawing_page_preview(drawing_id: str, page_number: int, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Per-page raster preview for multi-page PDFs (page 1..N). Non-PDF single-page drawings
    only ever have page 1, which is the original uploaded file itself - use /file for those."""
    drawing = db.query(Drawing).get(drawing_id)
    if not drawing:
        raise HTTPException(404, "Drawing not found")
    path = page_preview_path(drawing, page_number)
    if not os.path.exists(path):
        raise HTTPException(404, "Page preview not found")
    return FileResponse(path, media_type="image/png")


@router.get("/{drawing_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(drawing_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return db.query(Analysis).filter(Analysis.drawing_id == drawing_id).order_by(
        Analysis.version.desc()).all()
