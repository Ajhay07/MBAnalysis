import os
import tempfile

import pytest

from app.services.file_validation import (
    sanitize_filename, validate_extension, validate_size, build_stored_path, FileValidationError,
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
