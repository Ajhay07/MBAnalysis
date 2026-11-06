"""app.services.supabase_storage: a best-effort backup of uploaded drawing files to Supabase
Storage, which exists only for hosting platforms with no persistent local disk (e.g. a free
Hugging Face Space). When SUPABASE_URL/SUPABASE_SERVICE_KEY aren't set (the default - matches
Railway/local dev, which have their own persistent storage), every function must be a true
no-op: no network calls, never raises, behaves exactly as if this module didn't exist."""
from __future__ import annotations

import os

from app.services import supabase_storage


def test_is_configured_false_by_default():
    assert supabase_storage.is_configured() is False


def test_upload_is_a_silent_noop_when_not_configured(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: calls.append((a, k)))
    local = tmp_path / "x.pdf"
    local.write_bytes(b"pdf bytes")
    supabase_storage.upload_drawing_file(str(local), "x.pdf")
    assert calls == []  # httpx.post never called


def test_download_returns_true_without_network_when_file_already_local(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("httpx.get", lambda *a, **k: calls.append((a, k)))
    local = tmp_path / "x.pdf"
    local.write_bytes(b"already here")
    assert supabase_storage.download_drawing_file("x.pdf", str(local)) is True
    assert calls == []


def test_download_returns_false_when_not_configured_and_file_missing(tmp_path):
    missing = tmp_path / "missing.pdf"
    assert supabase_storage.download_drawing_file("missing.pdf", str(missing)) is False
    assert not os.path.exists(missing)


def test_upload_never_raises_on_network_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(supabase_storage, "is_configured", lambda: True)
    monkeypatch.setattr(supabase_storage, "get_settings", lambda: _FakeSettings())

    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("httpx.post", _boom)

    local = tmp_path / "x.pdf"
    local.write_bytes(b"pdf bytes")
    supabase_storage.upload_drawing_file(str(local), "x.pdf")  # must not raise


def test_download_never_raises_on_network_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(supabase_storage, "is_configured", lambda: True)
    monkeypatch.setattr(supabase_storage, "get_settings", lambda: _FakeSettings())

    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("httpx.get", _boom)

    local = tmp_path / "missing.pdf"
    result = supabase_storage.download_drawing_file("missing.pdf", str(local))  # must not raise
    assert result is False


def test_download_writes_fetched_bytes_to_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(supabase_storage, "is_configured", lambda: True)
    monkeypatch.setattr(supabase_storage, "get_settings", lambda: _FakeSettings())

    class _FakeResponse:
        status_code = 200
        content = b"fetched pdf bytes"

    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse())

    local = tmp_path / "subdir" / "x.pdf"
    result = supabase_storage.download_drawing_file("x.pdf", str(local))
    assert result is True
    assert local.read_bytes() == b"fetched pdf bytes"


def test_download_returns_false_on_non_200_status(tmp_path, monkeypatch):
    monkeypatch.setattr(supabase_storage, "is_configured", lambda: True)
    monkeypatch.setattr(supabase_storage, "get_settings", lambda: _FakeSettings())

    class _FakeResponse:
        status_code = 404
        content = b""

    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse())

    local = tmp_path / "x.pdf"
    assert supabase_storage.download_drawing_file("x.pdf", str(local)) is False
    assert not local.exists()


class _FakeSettings:
    SUPABASE_URL = "https://example.supabase.co"
    SUPABASE_SERVICE_KEY = "fake-key"
    SUPABASE_STORAGE_BUCKET = "drawings"
