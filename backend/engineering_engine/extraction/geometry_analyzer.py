"""Geometry-based clustering of LINE/LWPOLYLINE/HATCH-boundary segments into connected
shapes ("clusters"), used to associate callout labels (e.g. "SHROUD DETAIL") with nearby
dimension text when a drawing carries no native DIMENSION entities.

This is a real, non-hypothetical situation, not an edge case: the real WO 9374 DWG has
1089 LINE, 394 LWPOLYLINE, 265 TEXT and 157 HATCH entities, and zero DIMENSION/CIRCLE
entities - every "size" on the drawing is a hand-placed TEXT label near hand-drawn
geometry, not an associative CAD dimension.

Validated against WO 9374's real indent sheet via dimension_associator.py: this
clustering fully recovers Mid Pipe (OD 559, Thk 10, L 150) and End Pipe (Thk 10, L 125).
It does NOT fully recover Shroud (OD 683, thickness 2) - see dimension_associator.py's
module docstring for why that's a genuine ambiguity in the drawing, not a bug here.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from ezdxf import bbox as ezbbox

CONNECT_TOL = 0.5  # drawing units; segment endpoints within this distance are "touching"
MIN_CLUSTER_SIZE = 4  # drop degenerate 1-3 segment noise (e.g. a single tick mark)


@dataclass
class TextEntity:
    x: float
    y: float
    text: str


@dataclass
class Cluster:
    id: int
    x0: float
    y0: float
    x1: float
    y1: float
    size: int  # number of segments in this connected group

    def distance_to_point(self, x: float, y: float) -> float:
        dx = max(self.x0 - x, 0.0, x - self.x1)
        dy = max(self.y0 - y, 0.0, y - self.y1)
        return math.hypot(dx, dy)


def _text_centroid(entity) -> tuple[float, float]:
    """Rotation-correct centroid via the entity's true bounding box. Using the raw
    TEXT.dxf.insert point is wrong for rotated text (e.g. 270 degrees) - insert is only
    the baseline START of the string, which for a long vertical label is 20+ drawing
    units away from its visual center. That single bug was enough to make every
    distance-based match involving a rotated label wrong during manual investigation."""
    try:
        box = ezbbox.extents([entity])
        return (box.extmin.x + box.extmax.x) / 2, (box.extmin.y + box.extmax.y) / 2
    except Exception:
        return entity.dxf.insert.x, entity.dxf.insert.y


def extract_texts(msp) -> list[TextEntity]:
    out = []
    for e in msp:
        if e.dxftype() == "TEXT" and e.dxf.text.strip():
            x, y = _text_centroid(e)
            out.append(TextEntity(x=x, y=y, text=e.dxf.text.strip()))
    return out


def _segments(msp) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in msp:
        if e.dxftype() == "LINE":
            segs.append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
        elif e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            segs.extend(zip(pts, pts[1:]))
        elif e.dxftype() == "HATCH":
            for path in e.paths:
                pts = [(v[0], v[1]) for v in getattr(path, "vertices", [])]
                segs.extend(zip(pts, pts[1:]))
    return segs


def cluster_geometry(msp, tol: float = CONNECT_TOL) -> list[Cluster]:
    """Union-find clustering of all LINE/LWPOLYLINE/HATCH-boundary segments by endpoint
    proximity. Returns one Cluster (with size >= MIN_CLUSTER_SIZE) per connected group."""
    return _cluster_segments(_segments(msp), tol=tol)


def _cluster_segments(
    segs: list[tuple[tuple[float, float], tuple[float, float]]], tol: float = CONNECT_TOL
) -> list[Cluster]:
    parent = list(range(len(segs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    bucket_size = max(tol * 4, 1e-6)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)

    def key(p: tuple[float, float]) -> tuple[int, int]:
        return (round(p[0] / bucket_size), round(p[1] / bucket_size))

    for i, (a, b) in enumerate(segs):
        buckets[key(a)].append(i)
        buckets[key(b)].append(i)

    for i, (a, b) in enumerate(segs):
        for pt in (a, b):
            kx, ky = key(pt)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in buckets.get((kx + dx, ky + dy), ()):
                        if j == i:
                            continue
                        oa, ob = segs[j]
                        if (
                            math.hypot(pt[0] - oa[0], pt[1] - oa[1]) <= tol
                            or math.hypot(pt[0] - ob[0], pt[1] - ob[1]) <= tol
                        ):
                            union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(segs)):
        groups[find(i)].append(i)

    clusters = []
    for cid, idxs in groups.items():
        if len(idxs) < MIN_CLUSTER_SIZE:
            continue
        xs: list[float] = []
        ys: list[float] = []
        for i in idxs:
            a, b = segs[i]
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
        clusters.append(Cluster(id=cid, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), size=len(idxs)))
    return clusters
