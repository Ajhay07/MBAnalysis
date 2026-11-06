"""Optional, best-effort backup of uploaded drawing files to Supabase Storage - exists
specifically for hosting platforms with NO persistent local disk (e.g. a free Hugging Face
Space: every restart/redeploy starts from a clean container filesystem). When
SUPABASE_URL/SUPABASE_SERVICE_KEY aren't set (e.g. local dev, or Railway with its own mounted
volume), every function here is a silent no-op - the app behaves exactly as it always has,
reading/writing local disk only.

Uses the Storage REST API directly via httpx (already a dependency for tests) rather than the
supabase-py SDK, to avoid adding another dependency with its own transitive-dependency surface
on top of the already-delicate paddleocr/numpy/opencv pin stack documented in requirements.txt.

Only the ORIGINAL uploaded drawing file is backed up here - not page-preview PNGs (regenerated
cheaply by analysis_pipeline.rasterize_pdf_pages on every analysis run, so persisting them
separately isn't worth the extra network calls) and not the database (that's Supabase Postgres,
configured via DATABASE_URL, a separate concern from this file-storage module)."""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("app.services.supabase_storage")


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _object_url(stored_file_name: str) -> str:
    settings = get_settings()
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{stored_file_name}"


def _headers() -> dict:
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"}


def upload_drawing_file(local_path: str, stored_file_name: str) -> None:
    """Best-effort: copies the just-saved local file up to Supabase Storage so it survives a
    container restart elsewhere. Never raises - a failure here must never fail the upload
    request itself (the file is already safely saved locally at this point); it's logged and
    the app carries on exactly as if Supabase weren't configured at all."""
    if not is_configured():
        return
    settings = get_settings()
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        resp = httpx.post(
            _object_url(stored_file_name),
            headers={**_headers(), "x-upsert": "true"},
            content=data,
            timeout=30.0,
        )
        resp.raise_for_status()
    except Exception:
        logger.exception(
            "Failed to back up drawing file %s to Supabase Storage bucket %s - continuing with "
            "the local copy only (it will not survive a restart on a platform with no "
            "persistent disk).", stored_file_name, settings.SUPABASE_STORAGE_BUCKET,
        )


def download_drawing_file(stored_file_name: str, local_path: str) -> bool:
    """Best-effort: fetches `stored_file_name` from Supabase Storage down to `local_path` if it
    isn't already there - the one case this matters for is a FRESH container (no persistent
    disk) that still has the Analysis/Drawing database rows (Supabase Postgres) but an empty
    local filesystem. Returns True if local_path exists after this call (whether it was already
    there or was just downloaded), False otherwise. Never raises."""
    import os
    if os.path.exists(local_path):
        return True
    if not is_configured():
        return False
    try:
        resp = httpx.get(_object_url(stored_file_name), headers=_headers(), timeout=30.0)
        if resp.status_code != 200:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception:
        logger.exception(
            "Failed to fetch drawing file %s from Supabase Storage.", stored_file_name,
        )
        return False
