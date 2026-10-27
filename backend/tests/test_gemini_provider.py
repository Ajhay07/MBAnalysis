"""Mocked unit tests for GeminiVisionProvider (deterministic, fast, no real network - the real
Gemini SDK client is never constructed in these tests). Mirrors the coverage pattern used for
OpenAIVisionProvider's retry/auth/schema behavior. A separate, explicitly-gated live test
(RUN_REAL_GEMINI_TESTS=1) exercises the real API - see test_gemini_live.py."""
from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("GEMINI_API_KEY", "")  # see tests/conftest.py


def _fake_image_file() -> str:
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d7636060600000000500010d0a2db40000000049454e44ae426082"
    )
    path = os.path.join(tempfile.gettempdir(), "gemini_test_fixture.png")
    with open(path, "wb") as f:
        f.write(png_bytes)
    return path


VALID_PAYLOAD = {
    "provider": "gemini",
    "title_block": {"drawing_number": "GEM-1", "title": "Test Part", "revision": "A",
                     "units": "mm", "scale": "1:1", "material_spec": "Steel"},
    "dimensions": [],
    "materials": ["Steel"],
    "components": [
        {
            "part_number": "GEM-COMP-1", "description": "Bracket", "category": "Structural",
            "quantity": 1, "material": "Steel", "make_buy": "Make", "confidence": 0.8,
            "verification_status": "Unverified", "source_page": 1,
            "source_text": "seen in title block", "quantity_basis": "explicit_callout",
            "component_type": "manufactured",
        },
    ],
    "raw_ocr_text": "",
    "overall_confidence": 0.8,
    "view_types": [],
    "repeated_features": [],
    "ambiguities": [],
    "missing_info": [],
}


def _make_provider(monkeypatch, api_key="test-key"):
    monkeypatch.setenv("GEMINI_API_KEY", api_key)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.providers.gemini_provider import GeminiVisionProvider
    provider = GeminiVisionProvider.__new__(GeminiVisionProvider)
    provider.settings = get_settings()
    provider.model = provider.settings.GEMINI_MODEL
    provider.client = MagicMock()
    return provider


def _response_with_text(payload: dict, finish_reason="STOP"):
    candidate = SimpleNamespace(finish_reason=finish_reason)
    return SimpleNamespace(text=json.dumps(payload), candidates=[candidate])


def test_successful_response_parses_into_shared_schema(monkeypatch):
    provider = _make_provider(monkeypatch)
    provider.client.models.generate_content = MagicMock(return_value=_response_with_text(VALID_PAYLOAD))

    result = provider.analyze(image_path=_fake_image_file(), ocr_text="OCR text", drawing_number="GEM-1")

    assert result.provider == "gemini"
    assert result.title_block.drawing_number == "GEM-1"
    assert len(result.components) == 1
    assert result.components[0].part_number == "GEM-COMP-1"
    assert result.components[0].quantity_basis == "explicit_callout"
    provider.client.models.generate_content.assert_called_once()


def test_auth_error_raises_provider_auth_error(monkeypatch):
    from google.genai import errors as genai_errors
    from app.providers.openai_provider import ProviderAuthError

    provider = _make_provider(monkeypatch)
    exc = genai_errors.ClientError(code=401, response_json={"error": {"message": "bad key"}})
    provider.client.models.generate_content = MagicMock(side_effect=exc)

    with pytest.raises(ProviderAuthError):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")
    # Auth errors fail fast - never retried.
    assert provider.client.models.generate_content.call_count == 1


def test_malformed_json_response_rejected_cleanly(monkeypatch):
    from app.providers.openai_provider import ProviderTransientError

    provider = _make_provider(monkeypatch)
    bad_response = SimpleNamespace(text="not valid json {{{", candidates=[SimpleNamespace(finish_reason="STOP")])
    provider.client.models.generate_content = MagicMock(return_value=bad_response)

    with pytest.raises(ProviderTransientError):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")


def test_invalid_schema_response_rejected_cleanly(monkeypatch):
    from app.providers.openai_provider import ProviderTransientError

    provider = _make_provider(monkeypatch)
    # Component missing both source_text and is_assumption - violates the shared schema's
    # evidence-required validator.
    invalid_payload = dict(VALID_PAYLOAD)
    invalid_payload["components"] = [{
        "part_number": "X", "description": "y", "category": "z", "quantity": 1,
        "source_text": "", "is_assumption": False,
    }]
    provider.client.models.generate_content = MagicMock(
        return_value=_response_with_text(invalid_payload))

    with pytest.raises(ProviderTransientError):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")


def test_safety_blocked_response_rejected_cleanly(monkeypatch):
    from app.providers.openai_provider import ProviderTransientError

    provider = _make_provider(monkeypatch)
    blocked_response = SimpleNamespace(text="", candidates=[])
    provider.client.models.generate_content = MagicMock(return_value=blocked_response)

    with pytest.raises(ProviderTransientError):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")


def test_rate_limit_error_retries_then_raises_transient(monkeypatch):
    from google.genai import errors as genai_errors
    from app.providers.openai_provider import ProviderTransientError
    # Gemini has its own (more generous) retry budget - see app/providers/gemini_provider.py -
    # deliberately not the same constant as OpenAI's, so this imports from gemini_provider.
    from app.providers.gemini_provider import MAX_TRANSIENT_RETRIES

    provider = _make_provider(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda *_: None)  # don't actually wait in tests
    exc = genai_errors.ClientError(code=429, response_json={"error": {"message": "rate limited"}})
    provider.client.models.generate_content = MagicMock(side_effect=exc)

    with pytest.raises(ProviderTransientError):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")

    assert provider.client.models.generate_content.call_count == MAX_TRANSIENT_RETRIES + 1


def test_rate_limit_error_succeeds_after_transient_retry(monkeypatch):
    provider = _make_provider(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    from google.genai import errors as genai_errors
    exc = genai_errors.ClientError(code=503, response_json={"error": {"message": "server busy"}})
    provider.client.models.generate_content = MagicMock(
        side_effect=[exc, _response_with_text(VALID_PAYLOAD)])

    result = provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")

    assert result.provider == "gemini"
    assert provider.client.models.generate_content.call_count == 2


def test_daily_quota_exhausted_fails_fast_without_retrying(monkeypatch):
    """A 429 RESOURCE_EXHAUSTED tied to a *per-day* quota (Free Tier's
    GenerateRequestsPerDayPerProjectPerModel limit) must raise immediately on the first
    attempt - retrying it can only burn more of an already-exhausted daily quota during a
    multi-hour retryDelay, unlike an ordinary short-lived 429 (see
    test_rate_limit_error_retries_then_raises_transient, which does retry)."""
    from google.genai import errors as genai_errors
    from app.providers.openai_provider import ProviderTransientError

    provider = _make_provider(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda *_: None)  # would fail the test if ever called
    exc = genai_errors.ClientError(
        code=429,
        response_json={
            "error": {
                "message": "You exceeded your current quota, please check your plan and "
                "billing details.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [{
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaValue": "20",
                    }],
                }, {
                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                    "retryDelay": "70949s",
                }],
            },
        },
    )
    provider.client.models.generate_content = MagicMock(side_effect=exc)

    with pytest.raises(ProviderTransientError, match="daily request quota"):
        provider.analyze(image_path=_fake_image_file(), ocr_text="", drawing_number="GEM-1")

    # Fails on the very first attempt - never retried.
    assert provider.client.models.generate_content.call_count == 1


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.providers.gemini_provider import GeminiVisionProvider

    with pytest.raises(RuntimeError):
        GeminiVisionProvider()
    get_settings.cache_clear()


def test_get_provider_prefers_gemini_when_both_keys_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.providers import get_provider
    from app.providers.gemini_provider import GeminiVisionProvider

    provider = get_provider()
    assert isinstance(provider, GeminiVisionProvider)
    get_settings.cache_clear()
