"""Upload security: filename sanitization, extension/size validation, path traversal protection."""
from __future__ import annotations

import os
import re
import uuid

from app.config import get_settings


class FileValidationError(Exception):
    pass


def sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = name.replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.lstrip(".")
    if not name:
        name = "file"
    return name[:200]


def validate_extension(filename: str) -> str:
    settings = get_settings()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.allowed_extensions_list:
        raise FileValidationError(
            f"File type '{ext}' not allowed. Allowed: {settings.allowed_extensions_list}"
        )
    return ext


# Magic-byte signatures for each allowed extension family. Extension on disk
# is attacker-controlled (a renamed .exe can claim to be .pdf), so content is
# sniffed independently rather than trusted from the filename alone.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
}


def validate_content_matches_extension(ext: str, header_bytes: bytes) -> None:
    """Sniffs the first bytes of the upload and rejects content whose real
    type does not match the claimed extension (defends against a disguised
    executable or script uploaded with a spoofed .pdf/.png/etc name)."""
    signatures = _MAGIC_SIGNATURES.get(ext)
    if not signatures:
        return
    if not any(header_bytes.startswith(sig) for sig in signatures):
        raise FileValidationError(
            f"File content does not match its '{ext}' extension (failed signature check)."
        )


def validate_size(size_bytes: int) -> None:
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes <= 0:
        raise FileValidationError("Empty file not allowed.")
    if size_bytes > max_bytes:
        raise FileValidationError(f"File exceeds max size of {settings.MAX_UPLOAD_MB} MB.")


def build_stored_path(upload_dir: str, original_filename: str) -> tuple[str, str]:
    """Returns (stored_file_name, absolute_path). Guards against path traversal by
    generating a fresh random name and confirming the resolved path stays inside upload_dir."""
    safe_name = sanitize_filename(original_filename)
    ext = os.path.splitext(safe_name)[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    abs_dir = os.path.abspath(upload_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.abspath(os.path.join(abs_dir, stored_name))
    if not abs_path.startswith(abs_dir + os.sep) and abs_path != abs_dir:
        raise FileValidationError("Invalid file path resolution.")
    return stored_name, abs_path
