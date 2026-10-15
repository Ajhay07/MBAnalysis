import os

from app.providers import get_provider
from app.providers.demo_provider import DemoProvider


def test_get_provider_returns_demo_when_no_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    provider = get_provider()
    assert isinstance(provider, DemoProvider)
    get_settings.cache_clear()


def test_demo_provider_analyze_never_crashes_without_key():
    provider = DemoProvider()
    result = provider.analyze(image_path="nonexistent.png", ocr_text="", drawing_number="X-1")
    assert result.provider == "demo"
    assert result.components
