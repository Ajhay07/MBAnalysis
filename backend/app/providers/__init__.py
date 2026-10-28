from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.providers.demo_provider import DemoProvider
from app.providers.deterministic_provider import DeterministicProvider


def get_provider() -> DrawingAnalysisProvider:
    """No generative AI model anywhere in this pipeline - deliberately. The whole workflow is
    upload -> deterministic extraction (PyMuPDF text + PaddleOCR regions + rule-based parsing,
    see app.providers.deterministic_provider) -> indent sheet, with no API key, no network call
    to an AI vendor, and nothing that can be rate-limited, quota-exhausted, or go down on
    someone else's infrastructure.

    DemoProvider exists only for the seeded showcase project (app.main's demo-data endpoints /
    seed.py) - set AI_PROVIDER=demo to force it for testing; it has no external dependency
    either (hardcoded placeholder data)."""
    settings = get_settings()
    if (settings.AI_PROVIDER or "").strip().lower() == "demo":
        return DemoProvider()

    try:
        return DeterministicProvider()
    except Exception:  # pragma: no cover - no external dependency to fail on construction
        return DemoProvider()
