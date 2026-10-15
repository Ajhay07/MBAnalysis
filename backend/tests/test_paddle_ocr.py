"""Tests for the PaddleOCR adapter (app.services.paddle_ocr).

Unit tests mock the PaddleOCR engine for deterministic, fast runs (no model download/inference
during normal `pytest -q`). A real-inference smoke test is gated behind RUN_REAL_OCR_TESTS=1
since it downloads model weights on first run and does genuine CPU inference.
"""
import os

import numpy as np
import pytest

from app.services import paddle_ocr
from app.services.paddle_ocr import PageOcrResult, run_page_ocr


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Each test controls engine state explicitly instead of sharing the real singleton."""
    monkeypatch.setattr(paddle_ocr, "_engine", None)
    monkeypatch.setattr(paddle_ocr, "_engine_init_failed", False)
    yield
    paddle_ocr._engine = None
    paddle_ocr._engine_init_failed = False


class _FakeEngine:
    def __init__(self, result):
        self._result = result

    def ocr(self, image, cls=True):
        return self._result


def _mock_engine(monkeypatch, result):
    fake = _FakeEngine(result)
    monkeypatch.setattr(paddle_ocr, "_get_engine", lambda: fake)
    return fake


def test_run_page_ocr_happy_path(monkeypatch):
    _mock_engine(monkeypatch, [[
        [[[10, 10], [100, 10], [100, 30], [10, 30]], ("BRACKET-100", 0.95)],
        [[[10, 40], [100, 40], [100, 60], [10, 60]], ("QTY 4", 0.91)],
    ]])
    image = np.ones((100, 200, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=3)

    assert isinstance(result, PageOcrResult)
    assert result.configured is True
    assert result.page_number == 3
    assert result.text == "BRACKET-100\nQTY 4"
    assert len(result.regions) == 2
    assert result.regions[0].confidence == pytest.approx(0.95)
    assert result.regions[0].bbox == [[10.0, 10.0], [100.0, 10.0], [100.0, 30.0], [10.0, 30.0]]
    assert not result.low_confidence_regions


def test_run_page_ocr_empty_result_handled_gracefully(monkeypatch):
    _mock_engine(monkeypatch, [None])
    image = np.ones((50, 50, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=1)

    assert result.configured is True
    assert result.regions == []
    assert result.text == ""
    assert any("no text" in w.lower() for w in result.warnings)


def test_run_page_ocr_low_confidence_flagged_not_silently_accepted(monkeypatch):
    _mock_engine(monkeypatch, [[
        [[[0, 0], [10, 0], [10, 10], [0, 10]], ("smudge?", 0.22)],
    ]])
    image = np.ones((20, 20, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=1)

    assert result.configured is True
    assert len(result.low_confidence_regions) == 1
    assert any("low-confidence" in w.lower() for w in result.warnings)


def test_run_page_ocr_engine_exception_returns_structured_error(monkeypatch):
    class _Boom:
        def ocr(self, image, cls=True):
            raise RuntimeError("engine blew up")

    monkeypatch.setattr(paddle_ocr, "_get_engine", lambda: _Boom())
    image = np.ones((20, 20, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=1)

    assert result.configured is False
    assert "engine blew up" in result.error


def test_run_page_ocr_malformed_image_does_not_crash(monkeypatch):
    _mock_engine(monkeypatch, [[]])
    result = run_page_ocr(np.array([]), page_number=1)
    assert result.configured is False
    assert result.error


def test_run_page_ocr_none_image_does_not_crash(monkeypatch):
    _mock_engine(monkeypatch, [[]])
    result = run_page_ocr(None, page_number=2)
    assert result.configured is False
    assert result.page_number == 2


def test_run_page_ocr_engine_unavailable_is_graceful_not_fatal(monkeypatch):
    monkeypatch.setattr(paddle_ocr, "_get_engine", lambda: None)
    image = np.ones((20, 20, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=1)
    assert result.configured is False
    assert "not installed" in result.error.lower() or "not available" in result.error.lower()


def test_run_page_ocr_disabled_via_settings_short_circuits(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("OCR_ENABLED", "false")
    get_settings.cache_clear()
    try:
        image = np.ones((20, 20, 3), dtype=np.uint8) * 255
        result = run_page_ocr(image, page_number=1)
        assert result.configured is False
        assert "OCR_ENABLED" in result.warnings[0]
    finally:
        get_settings.cache_clear()


def test_exact_duplicate_consecutive_lines_collapsed_not_fuzzy_deduped(monkeypatch):
    _mock_engine(monkeypatch, [[
        [[[0, 0], [10, 0], [10, 10], [0, 10]], ("M8x1.25", 0.9)],
        [[[0, 12], [10, 12], [10, 22], [0, 22]], ("M8x1.25", 0.9)],
        [[[0, 24], [10, 24], [10, 34], [0, 34]], ("M8x1.26", 0.9)],
    ]])
    image = np.ones((50, 50, 3), dtype=np.uint8) * 255
    result = run_page_ocr(image, page_number=1)
    # Exact duplicate collapsed...
    assert result.text.count("M8x1.25") == 1
    # ...but a near-duplicate (different value) is kept, not fuzzy-deduped away.
    assert "M8x1.26" in result.text


@pytest.mark.skipif(os.environ.get("RUN_REAL_OCR_TESTS") != "1",
                     reason="Set RUN_REAL_OCR_TESTS=1 to run real local PaddleOCR inference "
                            "(downloads model weights on first run; slow).")
def test_real_paddleocr_inference_on_generated_image():
    """Genuine, unmocked PaddleOCR inference against a synthetic drawing-like image. Proves the
    adapter is really wired to the PaddleOCR engine, not just to mocks."""
    import cv2

    paddle_ocr._engine = None
    paddle_ocr._engine_init_failed = False

    img = np.ones((200, 700, 3), dtype=np.uint8) * 255
    cv2.putText(img, "BRACKET-100 QTY 4 DIA 12.5mm", (20, 110),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2, cv2.LINE_AA)

    result = run_page_ocr(img, page_number=1)
    assert result.configured is True
    assert result.regions, "expected at least one real recognized text region"
    assert "BRACKET" in result.text.upper()
    assert result.regions[0].confidence > 0.5
