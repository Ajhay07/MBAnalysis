# Engineering Dimension Extraction & Manufacturing Calculation Engine

Separate from, and does not modify, the existing deterministic OCR/BOM pipeline
(`app/services/paddle_ocr.py`, `app/services/bom_table_extractor.py`,
`app/services/drawing_detail_extractor.py`). This package consumes that pipeline's output as
raw evidence and layers MB Metallic Bellows' own manufacturing formulas on top of it.

**Status: local-only.** Built and tested on the `feature/geometry-based-dimensions` branch per
instruction - not merged to `main`, not deployed. Run it yourself with:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m pytest engineering_engine/tests -q      # 41 unit tests
python -m engineering_engine.main                 # prints the WO 9374 JSON to stdout
```

Sample output for WO 9374 is saved at `engineering_engine/sample_output/wo9374.json`.

## Why this exists

The main app's existing extractor reads dimensions directly off the CAD drawing's text/OCR.
That works well for OD/ID (they carry an unambiguous Ø marker) and poorly for Thickness/Length
on this drawing family (no reliable textual signal - confirmed across many attempts this
session). Investigating WO 9374's actual manufacturing calculation notes revealed the deeper
reason: **most of the indent sheet's dimensions were never meant to be read off the drawing at
all - they're calculated** from a handful of CAD inputs using MB's own formulas. Bellows'
"1765mm length" isn't printed anywhere; it's `(OD * 3.14) + 10`. This package implements that
calculation layer.

## Architecture

```
CAD Drawing (PDF) → extraction/ → RawComponentEvidence → calculations/ → DimensionResult
                                                                 ↓
                                                   validation/ (status, BOM qty, discrepancies)
                                                                 ↓
                                                   output/indent_generator.py → JSON
```

```
engineering_engine/
    extraction/
        pdf_extractor.py     # wraps the EXISTING app.services pipeline (reused, not rebuilt)
        ocr_extractor.py     # thin re-export of app.services.paddle_ocr
        cad_extractor.py     # native DXF path - NOT IMPLEMENTED, no .dxf supplied yet
        dimension_parser.py  # priority-chain entry point + numeric parsing helper
    calculations/
        bellows_calculator.py, shroud_calculator.py, pipe_calculator.py,
        sleeve_calculator.py, flange_calculator.py, packaging_calculator.py
        rules_loader.py      # loads rules/manufacturing_rules.json
    rules/
        manufacturing_rules.json   # every allowance/formula constant, with approval_status
    validation/
        dimension_validator.py  # DimensionStatus enum + DimensionResult dataclass
        bom_validator.py        # qty_per_assembly * assemblies, + discrepancy flagging
        calculation_validator.py  # compares a result to a reference value, never forces a match
    output/
        indent_generator.py  # assembles DimensionResults into the spec's JSON shape
    tests/                   # 41 unit tests, one file per calculator + a reference-table pass
    sample_output/wo9374.json
    main.py                  # builds + prints the WO 9374 indent JSON
```

**Separation of concerns, as required**: every function in `calculations/` is pure - plain
numbers in, a `DimensionResult` out. No file I/O, no OCR, no knowledge of where its inputs came
from. You can unit-test the whole formula layer (`engineering_engine/tests/`) without a PDF,
a database, or the rest of the app.

## Extraction priority chain (section 6 of the spec)

Implemented in `extraction/dimension_parser.get_component_evidence()`:
1. Native CAD dimension entity - `cad_extractor.py`, **not implemented** (no DXF file supplied
   to build or validate against; raises `NotImplementedError`, which the dispatcher catches).
2. PDF vector text / dimension annotations - covered by `pdf_extractor.py`.
3. OCR with spatial association - also `pdf_extractor.py` (the existing pipeline already
   merges PyMuPDF's embedded text with PaddleOCR region data).
4. Approved engineering calculation - `calculations/*.py`.
5. Manual verification - not a code path; it's what a `REVIEW_REQUIRED`/`MISSING` status in
   the output is asking a human to do. `main.py`'s `MANUAL_INPUTS` dict is this in practice for
   WO 9374: every value the automated pipeline can't reliably get is transcribed there,
   labeled `extraction_method: "manual"`.

## Formula documentation

All constants below live in `rules/manufacturing_rules.json`, not hardcoded in the calculators.

| Component | Formula | Status for WO 9374 |
|---|---|---|
| Bellows length | `(OD * 3.14) + 10` | **Approved.** OD 559 → 1765.26mm → rounds to 1765mm, matches the indent exactly. |
| Bellows width | `((0.57*q) + (2*w)) * N + 100` | **Blocked on inputs.** `q` (pitch) and `w` (depth) are not reliably extractable from the CAD profile. Reports `MISSING`, never reverse-engineered to hit the indent's 340mm. |
| Bellows thickness | `plies * ply_thickness` | **Verified**, not calculated - both numbers come from one CAD callout ("1 ply x 0.6mm"), not independently derived. |
| Bellows convolution count | parsed from "5+5 NO. OF CONVOLUTES" → N=10 | `REVIEW_REQUIRED` - MB's counting convention for "5+5" is not yet confirmed. |
| Shroud base length | `OD * 3.14` | **Approved**, geometric fact only. OD 683 → 2144.62mm. |
| Shroud final length | `base_length + allowance` | **Unapproved.** `allowance_mm` is `null` in the rules file. The indent's 2190mm exceeds the base circumference by 45.38mm - reported as a flagged gap, never auto-applied. |
| Mid/End Pipe ID | `OD - (2 * thickness)` | **Approved**, standard pipe geometry. Mid Pipe: 559-20=539. End Pipe: same. |
| Sleeve | no formula | All four fields (OD 539, blank-diameter 509, thickness 1.5, length 150) kept as **separate named fields** - the indent's "509" (used for the blank calculation) is never assumed to be the drawing's true OD or bore ID without checking the dimension reference. |
| Housing Flange | no formula | Direct pass-through (OD 810, ID 562, thickness 25, PCD 734, hole Ø34). Hole count is cross-checked between drawing and indent sources and flagged on any mismatch or when only one source is available. |
| Limit Rod length | `cad_length + 15` | **Pending approval.** Always `REVIEW_REQUIRED` while pending; never applied to any other component. |
| Collar | no formula | Must be sourced from "Detail B" specifically - anything not explicitly tagged that way is flagged `REVIEW_REQUIRED` even if a number is present. |
| Wooden Box length | `assembly_length + 250mm` | **Approved for length only.** Breadth/width come from the approved packaging layout, never this formula. |
| Shroud Support, M8 Bolt & Nut, Filler Wire, Electrode, Stiffener | none | Specs/quantities pass through from the drawing/BOM as-is - no formula invented for these, per the spec's explicit instruction. |

## BOM quantity discrepancy found

`validation/bom_validator.py` flags, without resolving: WO 9374's CAD BOM gives M8 Bolt & Nut
as 8 per assembly (→ 32 for 4 assemblies), but the indent sheet prints **48**. Both numbers are
kept in the output (`total_quantity: 32`, `reference_indent_quantity: 48`,
`quantity_discrepancy: true`) - the engine never silently picks one.

## Validation statuses

`VERIFIED` (directly read, cross-checked) / `CALCULATED` (approved formula, all inputs present)
/ `REVIEW_REQUIRED` (inferred, discrepant, unapproved/pending allowance, or ambiguous) /
`MISSING` (a required input is absent). A `DimensionResult` with status `MISSING` is enforced
(at construction time) to never carry a value, and every other status is enforced to always
carry one - see `validation/dimension_validator.py`'s `__post_init__`.

## What's still open / needs your input

- **Bellows sheet width (340mm)**: needs the convolution pitch (`q`) and depth (`w`) read off
  the CAD convolution profile - not something the current extractor can get reliably. If these
  are written anywhere on the drawing in a form OCR could read, point me at them; otherwise
  this stays a manual-entry field.
- **Shroud's 45.38mm allowance**: needs MB to confirm whether this is a real, standard
  allowance (and its value) or specific to WO 9374.
- **Limit Rod's +15mm**: needs confirmation of the operation it accounts for and whether it's
  a standing rule or WO 9374-specific.
- **Convolution counting convention**: does "5+5" really mean N=10 for the sheet-width formula,
  or does MB count it differently?
- **M8 Bolt & Nut quantity**: 32 (CAD BOM) vs 48 (indent) - needs a human to say which is right
  for WO 9374 and whether the CAD BOM or the indent was wrong.

## Integration notes

This package is additive - nothing in `app/` was changed to build it. To wire it into the real
upload/analyze flow later: `extraction/pdf_extractor.extract_components()` is the integration
point that already reuses the production OCR pipeline; a router could call
`main.build_wo9374_components()`-style logic (generalized beyond the WO 9374 hardcoded inputs)
after a drawing's BOM is generated, and surface `REVIEW_REQUIRED`/`MISSING` results in the
existing Components/Indent UI the same way `requires_confirmation` already works today.
