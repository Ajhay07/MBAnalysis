"""Tests for the geometry-based CAD extraction path (geometry_analyzer, dimension_associator,
cad_extractor). Synthetic-geometry tests run always and don't need ODA File Converter or any
real drawing file. The integration test replays the exact scenario found by hand against the
real WO 9374 DWG, and is skipped unless that file + ODA File Converter are available locally
(this repo does not ship the customer's real CAD file)."""
from __future__ import annotations

import os

import pytest

from engineering_engine.extraction import dwg_converter
from engineering_engine.extraction.dimension_associator import associate_label
from engineering_engine.extraction.geometry_analyzer import Cluster, TextEntity, _cluster_segments

# --- synthetic geometry: no DWG/ODA required -------------------------------------------


def test_touching_segments_form_one_cluster():
    # a small closed square, drawn as 4 touching LINE segments
    segs = [
        ((0, 0), (10, 0)),
        ((10, 0), (10, 10)),
        ((10, 10), (0, 10)),
        ((0, 10), (0, 0)),
    ]
    clusters = _cluster_segments(segs, tol=0.5)
    assert len(clusters) == 1
    assert clusters[0].size == 4


def test_disjoint_segments_form_separate_clusters():
    near = [((0, 0), (5, 0)), ((5, 0), (5, 5)), ((5, 5), (0, 5)), ((0, 5), (0, 0))]
    far = [((100, 100), (105, 100)), ((105, 100), (105, 105)), ((105, 105), (100, 105)), ((100, 105), (100, 100))]
    clusters = _cluster_segments(near + far, tol=0.5)
    assert len(clusters) == 2
    assert {c.size for c in clusters} == {4, 4}


def test_cluster_below_min_size_is_dropped():
    tiny = [((0, 0), (1, 0))]  # single segment, below MIN_CLUSTER_SIZE
    clusters = _cluster_segments(tiny, tol=0.5)
    assert clusters == []


# --- dimension_associator: confidence gating --------------------------------------------


def _cluster(cid, x0, y0, x1, y1, size):
    return Cluster(id=cid, x0=x0, y0=y0, x1=x1, y1=y1, size=size)


def test_isolated_cluster_is_high_confidence():
    label = TextEntity(x=0, y=0, text="MID PIPE  DETAIL")
    values = [TextEntity(x=12, y=0, text="559"), TextEntity(x=13, y=1, text="10"), TextEntity(x=14, y=2, text="150")]
    isolated = _cluster(1, x0=10, y0=-2, x1=16, y1=4, size=20)
    far_giant = _cluster(2, x0=200, y0=200, x1=400, y1=400, size=322)  # shared assembly outline
    result = associate_label(label, [isolated, far_giant], [label, *values])
    assert result.confidence == "high"
    assert set(result.raw_tokens) == {"559", "10", "150"}


def test_only_nearest_clusters_tokens_are_gathered_not_a_farther_ones():
    label = TextEntity(x=0, y=0, text="MID PIPE  DETAIL")
    nearest = _cluster(1, x0=6, y0=-1, x1=8, y1=1, size=6)
    farther = _cluster(2, x0=35, y0=-1, x1=37, y1=1, size=7)  # out of range of the label itself
    v_near = TextEntity(x=7, y=0, text="559")
    v_far = TextEntity(x=36, y=0, text="999")  # belongs to a different, unrelated callout
    result = associate_label(label, [nearest, farther], [label, v_near, v_far])
    assert result.confidence == "high"
    assert result.raw_tokens == ["559"]


def test_sparse_sheet_spanning_frame_is_never_chosen():
    # a 4-segment rectangle that spans almost the whole sheet (e.g. a title block border) -
    # too few segments to trip GIANT_CLUSTER_SIZE, but its bounding box contains the label,
    # so a naive bbox-distance check would wrongly call it "distance 0, nearest, isolated".
    label = TextEntity(x=56, y=157, text="MID PIPE  DETAIL")
    sheet_frame = _cluster(1, x0=6, y0=15, x1=205, y1=283, size=4)
    real_callout = _cluster(2, x0=62, y0=155, x1=92, y1=170, size=12)
    result = associate_label(label, [sheet_frame, real_callout], [label])
    assert result.confidence == "high"  # sheet_frame must be excluded by MAX_CALLOUT_EXTENT


def test_no_cluster_in_range_is_none():
    label = TextEntity(x=0, y=0, text="SLEEVE DETAIL")
    distant = _cluster(1, x0=500, y0=500, x1=510, y1=510, size=10)
    result = associate_label(label, [distant], [label])
    assert result.confidence == "none"
    assert result.raw_tokens == []


def test_giant_cluster_is_never_chosen_even_if_nearest():
    label = TextEntity(x=0, y=0, text="BELLOW  DETAIL")
    giant = _cluster(1, x0=1, y0=0, x1=50, y1=50, size=322)  # nearest, but shared assembly outline
    small = _cluster(2, x0=15, y0=0, x1=17, y1=2, size=10)
    result = associate_label(label, [giant, small], [label])
    assert result.confidence == "high"  # must have skipped the giant cluster


# --- real-file integration test (skipped unless available locally) --------------------

REAL_DWG_PATH = os.environ.get("MBANALYSIS_TEST_DWG_PATH", "")
ODA_EXE_PATH = os.environ.get("MBANALYSIS_ODA_EXE_PATH", "")


@pytest.mark.skipif(
    not (REAL_DWG_PATH and os.path.exists(REAL_DWG_PATH) and ODA_EXE_PATH and os.path.exists(ODA_EXE_PATH)),
    reason="Needs MBANALYSIS_TEST_DWG_PATH (real WO 9374 DWG) and MBANALYSIS_ODA_EXE_PATH set "
    "locally - this repo does not ship the customer's real CAD file.",
)
def test_real_wo9374_dwg_mid_and_end_pipe_recovered_correctly():
    from engineering_engine.extraction.cad_extractor import extract_cad_dimensions

    dwg_converter.configure_oda_converter(ODA_EXE_PATH)
    result = extract_cad_dimensions(REAL_DWG_PATH)

    def has(tokens, substr):
        return any(substr in t for t in tokens)

    mid_pipe = result["MID PIPE"]
    assert mid_pipe.cad_confidence == "high"
    assert has(mid_pipe.cad_raw_tokens, "559")  # OD, printed as "Ø 559"
    assert "10" in mid_pipe.cad_raw_tokens
    assert "150" in mid_pipe.cad_raw_tokens

    end_pipe = result["END PIPE"]
    assert end_pipe.cad_confidence == "high"
    assert "10" in end_pipe.cad_raw_tokens
    assert "125" in end_pipe.cad_raw_tokens

    # Shroud is the documented incomplete case: its nearest cluster captures only SOME
    # of its real values (its other values sit in separate, farther clusters that this
    # single-nearest-cluster assignment deliberately does not reach into) - this must
    # come back as a real but partial result, never a guessed/merged-in value for the
    # fields the nearest cluster didn't happen to contain.
    shroud = result["SHROUD"]
    assert shroud.cad_confidence == "high"
    assert has(shroud.cad_raw_tokens, "683")  # OD recovered from its nearest cluster
    assert "2" not in shroud.cad_raw_tokens  # thickness not in that same cluster - left absent, not guessed
