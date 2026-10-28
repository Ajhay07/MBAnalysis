from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.providers.demo_provider import DemoProvider
from app.providers.deterministic_provider import DeterministicProvider


def get_provider() -> DrawingAnalysisProvider:
    """Precedence: AI_PROVIDER env override (explicit opt-in) > Deterministic (standard path,
    always available, no key/network/quota required) > Demo (only if DeterministicProvider
    itself fails to construct, which should not happen since it has no external dependency).

    The standard indent-sheet workflow must not depend on a generative AI model (missing keys,
    exhausted quotas, and provider outages must never block it - see
    app.providers.deterministic_provider's module docstring), so Deterministic is now the
    default even when GEMINI_API_KEY/OPENAI_API_KEY happen to be set in the environment.
    Gemini/OpenAI remain available, but only when explicitly selected via AI_PROVIDER=gemini
    or AI_PROVIDER=openai, for drawings whose BOM the deterministic table extractor can't read
    (e.g. no printed BOM table) and a human reviewer wants AI-assisted interpretation instead."""
    settings = get_settings()
    requested = (settings.AI_PROVIDER or "").strip().lower()

    if requested == "gemini" and settings.GEMINI_API_KEY:
        try:
            from app.providers.gemini_provider import GeminiVisionProvider
            return GeminiVisionProvider()
        except Exception:
            # Falls back to the deterministic provider if Gemini cannot init (e.g. missing
            # package, bad key format) - app must never crash, and never silently falls back
            # to fabricated demo content for a real upload.
            return DeterministicProvider()
    if requested == "openai" and settings.OPENAI_API_KEY:
        try:
            from app.providers.openai_provider import OpenAIVisionProvider
            return OpenAIVisionProvider()
        except Exception:
            return DeterministicProvider()
    if requested == "demo":
        return DemoProvider()

    try:
        return DeterministicProvider()
    except Exception:  # pragma: no cover - no external dependency to fail on construction
        return DemoProvider()
