import os

from app.providers import get_provider
from app.providers.demo_provider import DemoProvider
from app.providers.deterministic_provider import DeterministicProvider


def _clear(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()


def test_get_provider_returns_deterministic_by_default_with_no_keys(monkeypatch):
    """The standard path requires no AI key at all - see app.providers.get_provider's
    docstring for why Deterministic (not Demo) is now the no-configuration default."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AI_PROVIDER", "")
    _clear(monkeypatch)
    provider = get_provider()
    assert isinstance(provider, DeterministicProvider)
    _clear(monkeypatch)


def test_get_provider_returns_deterministic_even_when_gemini_key_is_set(monkeypatch):
    """A Gemini/OpenAI key being present in the environment must not silently pull the
    standard workflow back onto a generative model - AI_PROVIDER must be set explicitly."""
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    monkeypatch.setenv("AI_PROVIDER", "")
    _clear(monkeypatch)
    provider = get_provider()
    assert isinstance(provider, DeterministicProvider)
    _clear(monkeypatch)


def test_get_provider_honors_explicit_ai_provider_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    _clear(monkeypatch)
    provider = get_provider()
    assert provider.name == "gemini"
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "")
    _clear(monkeypatch)


def test_get_provider_returns_demo_when_explicitly_requested(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    _clear(monkeypatch)
    provider = get_provider()
    assert isinstance(provider, DemoProvider)
    monkeypatch.setenv("AI_PROVIDER", "")
    _clear(monkeypatch)


def test_demo_provider_analyze_never_crashes_without_key():
    provider = DemoProvider()
    result = provider.analyze(image_path="nonexistent.png", ocr_text="", drawing_number="X-1")
    assert result.provider == "demo"
    assert result.components


def test_deterministic_provider_never_requires_any_api_key():
    """Operation without any Gemini/OpenAI key: the deterministic provider has no API key
    setting at all and must never raise for its absence."""
    provider = DeterministicProvider()
    result = provider.analyze(image_path="nonexistent.png", ocr_text="", drawing_number="X-1")
    assert result.provider == "deterministic"
