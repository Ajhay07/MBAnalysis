"""Component registry: one ComponentSpec per component type the engine knows how to handle,
and classify_component() - the single place a BOM row's printed description is matched to a
spec. No work-order number or drawing-specific condition appears anywhere in this module;
classification is driven only by the component's own name text, same conservative substring-
match convention already used elsewhere in this app (app.services.drawing_detail_extractor.
match_panel_to_description).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().upper().replace(".", "").replace("&", "AND").split())


@dataclass
class ComponentSpec:
    identifier: str                         # canonical key, e.g. "BELLOWS"
    aliases: tuple[str, ...]                 # normalized alias strings matched against a BOM row's description
    required_parameters: tuple[str, ...]     # parameter names the calculator needs to produce a non-MISSING result
    optional_parameters: tuple[str, ...] = ()
    extraction_sources: tuple[str, ...] = () # documentation: where each parameter can realistically come from
    calculator: str = ""                     # documentation: which engineering_engine.calculations module/function
    validation_requirements: str = ""        # documentation: what must hold for this component's result to be trusted
    builder: Callable | None = None          # set by component_builders.register_all() - the actual adapter function

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "aliases": list(self.aliases),
            "required_parameters": list(self.required_parameters),
            "optional_parameters": list(self.optional_parameters),
            "extraction_sources": list(self.extraction_sources),
            "calculator": self.calculator,
            "validation_requirements": self.validation_requirements,
        }


REGISTRY: dict[str, ComponentSpec] = {}


def register(spec: ComponentSpec) -> ComponentSpec:
    """Adds `spec` to the registry (builder is attached separately by component_builders.py,
    which imports this module - keeps the calculator-calling code out of the registry itself,
    so the registry stays a plain catalog, not an engine)."""
    REGISTRY[spec.identifier] = spec
    return spec


def classify_component(raw_description: str) -> ComponentSpec | None:
    """Matches a BOM row's printed description to a registered ComponentSpec by normalized
    alias substring match (either direction, tolerating OCR truncation like "SLEEV" for
    "SLEEVE" - confirmed necessary on a real drawing this session). Returns None - never a
    guessed/best-effort spec - when nothing matches confidently; the caller is expected to
    report this as an unknown/unclassified component rather than drop it.

    Ambiguous matches (more than one spec's alias overlaps) are resolved by preferring the
    LONGEST matching alias - same tie-break already used by match_panel_to_description - since
    a longer, more specific alias match is more likely correct than a short, generic one."""
    norm = _normalize(raw_description)
    if not norm:
        return None

    exact = [spec for spec in REGISTRY.values() if norm in spec.aliases]
    if len(exact) == 1:
        return exact[0]

    def best_alias_len(spec: ComponentSpec) -> int:
        matches = [a for a in spec.aliases if a in norm or norm in a]
        return max((len(a) for a in matches), default=0)

    candidates = [spec for spec in REGISTRY.values() if best_alias_len(spec) > 0]
    if not candidates:
        return None
    candidates.sort(key=best_alias_len, reverse=True)
    if len(candidates) > 1 and best_alias_len(candidates[0]) == best_alias_len(candidates[1]):
        return None  # genuinely ambiguous (tied) - never guess between two equally-good matches
    return candidates[0]


def list_registered_components() -> list[dict]:
    return [spec.to_dict() for spec in REGISTRY.values()]
