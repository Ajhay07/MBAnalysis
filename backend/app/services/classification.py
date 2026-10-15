"""Deterministic Buy/Make/Review classification used when a component candidate doesn't
already carry an AI-suggested classification, or to validate/normalize one."""
from __future__ import annotations

BUY_CATEGORY_KEYWORDS = {
    "bearing", "fastener", "bolt", "screw", "nut", "washer", "o-ring", "seal",
    "gasket", "bushing", "spring", "motor", "coupling", "sensor", "connector",
}
MAKE_CATEGORY_KEYWORDS = {
    "shaft", "housing", "bracket", "plate", "gear", "custom", "machined", "weldment",
}


def classify_component(category: str, description: str, confidence: float) -> str:
    text = f"{category} {description}".lower()
    if confidence < 0.4:
        return "Review"
    for kw in BUY_CATEGORY_KEYWORDS:
        if kw in text:
            return "Buy"
    for kw in MAKE_CATEGORY_KEYWORDS:
        if kw in text:
            return "Make"
    return "Review"
