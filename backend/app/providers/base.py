from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.analysis import AnalysisResult


class DrawingAnalysisProvider(ABC):
    """Abstract interface every analysis backend (OpenAI vision, demo, future providers)
    must implement. Keeps the AI vendor fully swappable behind one contract."""

    name: str = "base"

    @abstractmethod
    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        ...
