from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.providers.demo_provider import DemoProvider


def get_provider() -> DrawingAnalysisProvider:
    """Precedence: Gemini (if GEMINI_API_KEY is set) > OpenAI (if OPENAI_API_KEY is set) > Demo.
    Realistically only one of GEMINI_API_KEY/OPENAI_API_KEY will ever be configured in a given
    environment, but Gemini is preferred if both happen to be set since it is this project's
    current real inference path."""
    settings = get_settings()
    if settings.GEMINI_API_KEY:
        try:
            from app.providers.gemini_provider import GeminiVisionProvider
            return GeminiVisionProvider()
        except Exception:
            # Falls back gracefully to demo mode if the Gemini provider cannot init
            # (e.g. missing package, bad key format) - app must never crash.
            return DemoProvider()
    if settings.OPENAI_API_KEY:
        try:
            from app.providers.openai_provider import OpenAIVisionProvider
            return OpenAIVisionProvider()
        except Exception:
            # Falls back gracefully to demo mode if the OpenAI provider cannot init
            # (e.g. missing package, bad key format) - app must never crash.
            return DemoProvider()
    return DemoProvider()
