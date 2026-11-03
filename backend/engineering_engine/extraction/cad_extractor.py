"""Native CAD dimension-entity extraction (highest-priority source per the extraction
priority order in the spec: native CAD dimension entity > PDF vector text > OCR > calculation
> manual).

NOT IMPLEMENTED: no DXF/native-CAD file was supplied for WO 9374 (only a PDF), so there is
nothing to validate this against - per the "never invent, never guess" rule that governs this
whole engine, this module deliberately raises rather than pretending to support a format it
has not been tested against. If/when a .dxf export becomes available, this is where an
ezdxf-based reader belongs (reading DIMENSION entities directly, which carry their own
measurement text and don't need any of the OCR/positional heuristics pdf_extractor.py relies
on) - wire it into dimension_parser.priority_chain() as the first source tried.
"""
from __future__ import annotations


def extract_cad_dimensions(dxf_path: str):
    raise NotImplementedError(
        "No DXF/native-CAD extraction path is implemented yet - no .dxf file was supplied to "
        "build or validate one against. Falls back to pdf_extractor.py (PDF vector text + OCR) "
        "for all current work orders, which only ever has PDF drawings available."
    )
