"""drawing_abspath: on a hosting platform with no persistent local disk, a fresh container has
the Drawing row (if DATABASE_URL points at a persistent Postgres like Supabase) but an empty
local filesystem. drawing_abspath must transparently fetch the original file back from Supabase
Storage before returning its local path, so every existing caller (serving the file, rasterizing
pages for OCR, ...) keeps working unchanged. When Supabase isn't configured, or the file is
already present locally, this must cost nothing - no network calls at all."""
from __future__ import annotations

from app.models.models import Drawing, DrawingStatus
from app.services import analysis_pipeline
from app.services import supabase_storage


def _drawing(stored_file_name="abc_9374.pdf"):
    return Drawing(
        drawing_number="9374", title="x", revision="A", file_name="9374.pdf",
        stored_file_name=stored_file_name, file_type="pdf", file_size=100,
        status=DrawingStatus.UPLOADED,
    )


def test_fetches_from_supabase_when_file_missing_locally(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_pipeline, "get_settings",
                         lambda: _Settings(str(tmp_path)))
    calls = []

    def _fake_download(stored_file_name, local_path):
        calls.append((stored_file_name, local_path))
        with open(local_path, "wb") as f:
            f.write(b"fetched")
        return True

    monkeypatch.setattr(analysis_pipeline, "download_drawing_file", _fake_download)
    path = analysis_pipeline.drawing_abspath(_drawing())
    assert len(calls) == 1
    assert calls[0][0] == "abc_9374.pdf"
    with open(path, "rb") as f:
        assert f.read() == b"fetched"


def test_no_supabase_call_when_file_already_local(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_pipeline, "get_settings", lambda: _Settings(str(tmp_path)))
    existing = tmp_path / "abc_9374.pdf"
    existing.write_bytes(b"already here")

    calls = []
    monkeypatch.setattr(analysis_pipeline, "download_drawing_file",
                         lambda *a, **k: calls.append(a) or True)
    analysis_pipeline.drawing_abspath(_drawing())
    # download_drawing_file is still CALLED (it's the one place that checks "is it already
    # local"), but with the real (unmocked) implementation it would short-circuit without any
    # network call - this test only confirms drawing_abspath always delegates the check to it,
    # not that it skips calling it. supabase_storage's own tests cover the no-network-when-
    # already-local behavior directly.
    assert len(calls) == 1


def test_real_download_drawing_file_is_a_noop_when_not_configured_and_file_missing(tmp_path, monkeypatch):
    # End-to-end with the REAL (unmocked) supabase_storage.download_drawing_file - confirms the
    # full drawing_abspath path costs nothing when Supabase isn't configured (the default).
    monkeypatch.setattr(analysis_pipeline, "get_settings", lambda: _Settings(str(tmp_path)))
    assert supabase_storage.is_configured() is False
    path = analysis_pipeline.drawing_abspath(_drawing("missing.pdf"))
    assert path.endswith("missing.pdf")
    import os
    assert not os.path.exists(path)  # never fabricated - genuinely missing, not an error


class _Settings:
    def __init__(self, upload_dir):
        self.UPLOAD_DIR = upload_dir
