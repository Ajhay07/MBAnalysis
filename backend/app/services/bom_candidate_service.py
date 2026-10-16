from __future__ import annotations

"""Deterministic BOM-candidate generation from richer vision+OCR evidence.

This is intentionally NOT another AI call: given an AnalysisResult (which already
carries the vision provider's structured observations - components, repeated
features, ambiguities), this module derives additional candidate BOM entries and
annotates every entry with how its quantity was determined, never inventing values
beyond what the evidence supports.
"""

from app.schemas.analysis import AnalysisResult, ComponentCandidate, RepeatedFeature

# Feature types that plausibly correspond to a fastener/bushing per-instance, so a
# repeated-feature count can seed a quantity candidate. Conservative allowlist -
# anything else is left for human review rather than guessed at.
FASTENER_LIKE_FEATURES = {"through_hole", "tapped_hole", "counterbore", "bolt_hole", "pin_hole"}


def candidates_from_repeated_features(analysis: AnalysisResult) -> list[ComponentCandidate]:
    """Turns repeated-feature counts (e.g. "6 identical through-holes") into fastener
    quantity candidates, flagged as calculated-from-geometry (not explicit)."""
    out: list[ComponentCandidate] = []
    for feat in analysis.repeated_features:
        if feat.feature_type not in FASTENER_LIKE_FEATURES or feat.count <= 0:
            continue
        out.append(
            ComponentCandidate(
                part_number="",
                description=f"Fastener (qty derived from {feat.count}x {feat.feature_type} pattern)",
                category="Fastener",
                quantity=float(feat.count),
                component_type="purchased",
                quantity_basis="counted_feature",
                confidence=min(0.7, 0.3 + 0.05 * feat.count),
                verification_status="Unverified",
                source_page=feat.page,
                source_region=feat.source_region,
                source_text=feat.source_text,
                is_assumption=feat.is_assumption,
                assumption_text=feat.assumption_text,
            )
        )
    return out


def build_candidate_bom(analysis: AnalysisResult) -> list[ComponentCandidate]:
    """Merges the provider's directly-proposed components with the geometry-derived
    fastener candidates into one candidate list. Never mutates `analysis`."""
    return list(analysis.components) + candidates_from_repeated_features(analysis)


def missing_info_report(analysis: AnalysisResult) -> list[str]:
    """Honest incompleteness surface: combines the provider's own missing_info list
    with ambiguity descriptions, so a partial/incomplete BOM never silently presents
    as complete."""
    report = list(analysis.missing_info)
    report.extend(f"Ambiguity (page {a.page}): {a.description}" for a in analysis.ambiguities)
    return report
