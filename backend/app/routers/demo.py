from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db, engine, Base
from app.models.models import Drawing, User

router = APIRouter(prefix="/api/demo", tags=["demo"])

editor = require_role("admin", "engineer")


@router.post("/load")
def load_demo(db: Session = Depends(get_db), current_user: User = Depends(editor)):
    from seed import seed_demo_data  # local import to avoid circulars at module load
    created = seed_demo_data(db, actor=current_user.email)
    return {"ok": True, "created": created}


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db), current_user: User = Depends(editor)):
    deleted = db.query(Drawing).filter(Drawing.is_demo == True).delete()  # noqa: E712
    db.commit()
    from seed import seed_demo_data
    created = seed_demo_data(db, actor=current_user.email)
    return {"ok": True, "deleted": deleted, "created": created}


@router.get("/status")
def demo_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    count = db.query(Drawing).filter(Drawing.is_demo == True).count()  # noqa: E712
    return {"demo_drawings": count, "loaded": count > 0}
