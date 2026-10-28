from app.providers import get_provider
from app.providers.demo_provider import DemoProvider
from app.providers.deterministic_provider import DeterministicProvider


def _clear(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()


def test_get_provider_returns_deterministic_by_default(monkeypatch):
    """No generative AI model is used anywhere in this app - see app.providers.get_provider's
    docstring. Deterministic (PyMuPDF text + PaddleOCR regions + rule-based parsing) is the
    only real analysis path."""
    monkeypatch.setenv("AI_PROVIDER", "")
    _clear(monkeypatch)
    provider = get_provider()
    assert isinstance(provider, DeterministicProvider)
    _clear(monkeypatch)


def test_get_provider_returns_demo_when_explicitly_requested(monkeypatch):
    """AI_PROVIDER=demo forces the seeded-showcase placeholder provider (used by the demo
    project only) - the only override get_provider recognizes at all."""
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
    """No provider in this app has an API key setting at all - this one must never raise."""
    provider = DeterministicProvider()
    result = provider.analyze(image_path="nonexistent.png", ocr_text="", drawing_number="X-1")
    assert result.provider == "deterministic"
