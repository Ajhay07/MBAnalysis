"""Native CAD (DWG/DXF) dimension-adjacent text extraction, via direct geometry analysis
rather than native DIMENSION entities - because real MB drawings (confirmed on WO 9374's
actual DWG) don't carry any: every "size" is a hand-placed TEXT label near hand-drawn
geometry. See geometry_analyzer.py and dimension_associator.py for how a callout label
(e.g. "SHROUD DETAIL") gets matched to its nearby dimension text, and why ambiguous
matches are deliberately reported empty rather than guessed.

IMPORTANT SCOPE LIMIT, stated plainly rather than implied: this module does NOT assign
semantic dimension keys (od/id/thk/l/pcd) to the raw tokens it finds. Which raw number on
a given panel means "OD" vs "thickness" vs "length" depends on that component type's own
layout convention, and getting that right generically (not just for the six component
types already reasoned about by hand against WO 9374's known reference values) hasn't
been built. Promoting a raw token into dimensions{} without that would be exactly the
kind of fabricated/guessed value this whole engine is built to avoid. So dimensions{} is
always returned empty here; raw_tokens carries everything found, gated by confidence, for
a human reviewer or a future semantic-mapping layer to use.

Tested against the real WO 9374 DWG (converted via ODA File Converter) and cross-checked
against the real indent sheet: Mid Pipe and End Pipe each get "high" confidence with
exactly the correct values present in raw_tokens; Shroud correctly gets "low" confidence
(ambiguous geometry) rather than a guess. See tests/test_cad_extractor.py.
"""
from __future__ import annotations

from engineering_engine.extraction import dwg_converter
from engineering_engine.extraction.dimension_associator import associate_label
from engineering_engine.extraction.geometry_analyzer import cluster_geometry, extract_texts
from engineering_engine.extraction.pdf_extractor import RawComponentEvidence

DETAIL_SUFFIX = "DETAIL"


def extract_cad_dimensions(cad_path: str) -> dict[str, RawComponentEvidence]:
    """Returns {normalized_description: RawComponentEvidence} for every "<NAME> DETAIL"
    callout label found via geometry clustering. `dimensions` is always {} (see module
    docstring); `cad_raw_tokens` and `cad_confidence` carry what was actually found.

    Raises (never swallows) on a genuine failure to read the file - RuntimeError if DWG
    conversion isn't available, ValueError for an unsupported extension, or whatever
    ezdxf raises for a corrupt file - so callers can tell "no CAD evidence available"
    apart from "CAD evidence says nothing is here"."""
    doc = dwg_converter.load_drawing(cad_path)
    msp = doc.modelspace()
    clusters = cluster_geometry(msp)
    texts = extract_texts(msp)
    labels = [t for t in texts if t.text.strip().upper().endswith(DETAIL_SUFFIX)]

    out: dict[str, RawComponentEvidence] = {}
    for label in labels:
        assoc = associate_label(label, clusters, texts)
        description = label.text[: -len(DETAIL_SUFFIX)].strip().rstrip("-").strip()
        if not description:
            continue
        out[description.upper()] = RawComponentEvidence(
            description=description,
            detail_panel_label=label.text,
            cad_confidence=assoc.confidence,
            cad_raw_tokens=assoc.raw_tokens,
        )
    return out
