"""Associates a callout label (e.g. "SHROUD DETAIL") with nearby dimension text, using
geometry_analyzer's clusters, with explicit confidence gating.

Validated against the real WO 9374 indent sheet (see geometry_analyzer.py for the entity
counts this is based on): the nearest isolated cluster to "MID PIPE  DETAIL" contains
exactly its real values (559, 10, 150); the nearest isolated cluster to "END PIPE  DETAIL"
contains exactly its real values (10, 125). "SHROUD DETAIL"'s nearest isolated cluster
contains only its width (170) - its OD (683) and thickness (2) sit in other, separate
small clusters nearby, not the nearest one. That's reported as a plain incomplete result
(fewer raw_tokens), not a special "low confidence" guess - this module never tries to
decide FOR a reviewer whether a result is "enough"; it reports only what it geometrically
found, and per the "never fabricate" rule that governs this whole engine, nothing further
is inferred or merged in from a second-best cluster just because the first one came up
short.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engineering_engine.extraction.geometry_analyzer import Cluster, TextEntity

MAX_LABEL_DISTANCE = 20.0  # drawing units: how far the nearest cluster may be from its label
GIANT_CLUSTER_SIZE = 50  # clusters at/above this size are shared-view outlines, never a callout box
MAX_CALLOUT_EXTENT = 80.0  # a cluster spanning more than this (sheet border/frame) is never a
                            # callout box either, however few segments it's made of - a 4-line
                            # rectangle that spans the whole sheet is still "giant"


@dataclass
class LabelAssociation:
    label: str
    confidence: str  # "high" | "none" (a geometric match was found, or it wasn't -
                      # "high" never implies the result is semantically complete, see
                      # module docstring)
    reason: str
    raw_tokens: list[str] = field(default_factory=list)


def _is_giant(c: Cluster) -> bool:
    return c.size >= GIANT_CLUSTER_SIZE or (c.x1 - c.x0) > MAX_CALLOUT_EXTENT or (c.y1 - c.y0) > MAX_CALLOUT_EXTENT


def associate_label(label: TextEntity, clusters: list[Cluster], texts: list[TextEntity]) -> LabelAssociation:
    """Assigns a label to its single nearest non-giant cluster (validated against the real
    drawing: a callout's own small cluster is reliably the nearest one, even though other
    small clusters - unrelated dimension fragments elsewhere on the sheet - also happen to
    sit within MAX_LABEL_DISTANCE much of the time), then gathers every text within range
    of THAT one cluster only."""
    candidates = [c for c in clusters if not _is_giant(c)]
    scored = sorted(
        ((c, c.distance_to_point(label.x, label.y)) for c in candidates),
        key=lambda cd: cd[1],
    )
    scored = [(c, d) for c, d in scored if d <= MAX_LABEL_DISTANCE]
    if not scored:
        return LabelAssociation(label.text, "none", "no isolated cluster within range")

    nearest_cluster, nearest_dist = scored[0]
    tokens = [
        t.text
        for t in texts
        if t.text != label.text and nearest_cluster.distance_to_point(t.x, t.y) <= MAX_LABEL_DISTANCE
    ]
    return LabelAssociation(
        label.text, "high", f"nearest isolated cluster {nearest_cluster.id} at distance {nearest_dist:.1f}", tokens
    )
