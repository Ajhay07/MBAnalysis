"""Engineering Dimension Extraction & Manufacturing Calculation Engine.

Separate from (and does not modify) the existing deterministic OCR/BOM pipeline in
app.services/app.providers - it consumes that pipeline's output as input evidence and layers
MB Metallic Bellows' own manufacturing formulas on top. See README.md in this directory for
the full architecture, formula documentation, and integration notes.
"""
