import os
import tempfile

import pytest

from app.services.file_validation import (
    sanitize_filename, validate_extension, validate_size, build_stored_path, FileValidationError,
    validate_content_matches_extension,
)


def test_sanitize_filename_strips_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\evil.exe") == "evil.exe"


def test_sanitize_filename_strips_unsafe_chars():
    assert sanitize_filename("my drawing (rev B)!.pdf") == "my_drawing__rev_B__.pdf"


def test_validate_extension_allows_known_types():
    assert validate_extension("part.PDF") == ".pdf"
    assert validate_extension("scan.png") == ".png"


def test_validate_extension_rejects_unknown_type():
    with pytest.raises(FileValidationError):
        validate_extension("malware.exe")


def test_validate_size_rejects_empty():
    with pytest.raises(FileValidationError):
        validate_size(0)


def test_validate_size_rejects_oversized():
    with pytest.raises(FileValidationError):
        validate_size(1024 * 1024 * 1024)


def test_build_stored_path_stays_inside_upload_dir():
    with tempfile.TemporaryDirectory() as tmp:
        stored_name, abs_path = build_stored_path(tmp, "../../etc/passwd.pdf")
        assert os.path.abspath(tmp) in abs_path
        assert ".." not in stored_name


def test_validate_content_matches_extension_accepts_real_pdf():
    validate_content_matches_extension(".pdf", b"%PDF-1.7\n...")


def test_validate_content_matches_extension_accepts_real_png():
    validate_content_matches_extension(".png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00")


def test_validate_content_matches_extension_rejects_spoofed_mime():
    # An executable renamed to look like a PDF should fail the signature check.
    with pytest.raises(FileValidationError):
        validate_content_matches_extension(".pdf", b"MZ\x90\x00\x03\x00\x00\x00")


def test_validate_content_matches_extension_rejects_script_as_image():
    with pytest.raises(FileValidationError):
        validate_content_matches_extension(".png", b"<script>alert(1)</script>")
