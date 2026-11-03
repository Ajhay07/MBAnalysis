"""Per-component manufacturing calculators. Each function is pure: explicit numeric inputs in,
a dict of DimensionResult out - no file I/O, no OCR, no knowledge of how its inputs were
obtained (extracted, calculated upstream, or typed in by a reviewer). This is the "calculation
engine must be independent and reusable" requirement - every function here is unit-testable
with plain numbers, no drawing or PDF required.
"""
