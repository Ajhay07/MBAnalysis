from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.providers.demo_provider import DemoProvider


def get_provider() -> DrawingAnalysisProvider:
    settings = get_settings()
    if settings.OPENAI_API_KEY:
        try:
            from app.providers.openai_provider import OpenAIVisionProvider
            return OpenAIVisionProvider()
        except Exception:
            # Falls back gracefully to demo mode if the OpenAI provider cannot init
            # (e.g. missing package, bad key format) - app must never crash.
            return DemoProvider()
    return DemoProvider()
