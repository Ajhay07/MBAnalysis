from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.analysis import AnalysisResult


class DrawingAnalysisProvider(ABC):
    """Abstract interface every analysis backend (deterministic, demo, and any optional AI
    vision provider a deployment chooses to add back) must implement."""

    name: str = "base"

    @abstractmethod
    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        ...


class ProviderAuthError(Exception):
    """A provider's credentials are missing/invalid/rejected. Never retried - fails the
    analysis immediately with a clear reason."""


class ProviderTransientError(Exception):
    """A provider call failed in a way that might succeed on a later attempt (timeout, rate
    limit, malformed/blocked response, etc.). The caller (app.services.analysis_pipeline)
    still fails the Analysis/Job for this attempt, but the distinction from ProviderAuthError
    is what the UI's "Retry Analysis" action is for."""
