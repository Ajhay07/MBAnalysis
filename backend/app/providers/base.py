from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.analysis import AnalysisResult


class DrawingAnalysisProvider(ABC):
    """Abstract interface every analysis backend (deterministic, demo, and any optional AI
    vision provider a deployment chooses to add back) must implement."""

    name: str = "base"

    @abstractmethod
    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str,
                pdf_path: str | None = None, page_number: int = 1) -> AnalysisResult:
        # pdf_path/page_number: the ORIGINAL PDF (not the rasterized preview image_path) and
        # which page, when the source is a PDF - lets a provider that wants word-level position
        # data read it straight from the PDF's own embedded text layer (PyMuPDF), which is often
        # far more complete than an image-OCR pass over the same page (see
        # app.providers.deterministic_provider._regions_for). Optional and provider-specific;
        # a provider that has no use for it (an AI vision provider working from image_path
        # alone) just ignores it.
        ...


class ProviderAuthError(Exception):
    """A provider's credentials are missing/invalid/rejected. Never retried - fails the
    analysis immediately with a clear reason."""


class ProviderTransientError(Exception):
    """A provider call failed in a way that might succeed on a later attempt (timeout, rate
    limit, malformed/blocked response, etc.). The caller (app.services.analysis_pipeline)
    still fails the Analysis/Job for this attempt, but the distinction from ProviderAuthError
    is what the UI's "Retry Analysis" action is for."""
