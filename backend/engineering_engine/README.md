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

## Corrections from code review (this revision)

1. **Sleeve OD was wrong.** The auto-extractor reads two concentric diameters off the Sleeve
   Detail panel (Ø539/Ø509) and picks the larger as "od" purely by pixel position - it has no
   way to know which is which. The real indent gives Sleeve's OD as **509**, not 539. 539 is
   very likely Mid Pipe's own ID (559 - 2×10 = 539, an exact match) printed near the Sleeve
   detail as a mating-interface reference. Fixed: `od=509` (manual, matching the indent),
   `mid_pipe_interface_reference=539` kept as its own field, always `REVIEW_REQUIRED`, never
   used as Sleeve's OD anywhere.
2. **Filler Wire (84), Electrode (282), Stiffener (16) quantities were silently dropped**
   because the CAD BOM has no per-assembly figure for them. Fixed: `bom_validator.
   reference_only_quantity()` preserves the indent's own quantity even with no calculated side.
3. **Wooden Box's `assembly_length` (588.2mm) was reverse-engineered from the indent's own 33"
   reference** (`33*25.4 - 250`) - exactly the circular reasoning this engine must never do.
   Fixed: no assembly length is supplied; the calculated length is honestly `MISSING`, and
   33×33×25" is reported only under `reference_indent_dimensions`, never as if calculated.
4. **Limit Rod's `cad_length` (595mm) is also not an independent reading** - WO 9374 has no
   Limit Rod CAD detail panel at all, so 595 was derived the same way (610 - 15). Per explicit
   instruction this calculation IS preserved (595+15=610 matches the indent, stays
   `REVIEW_REQUIRED`) - but `calculate_limit_rod_length(..., cad_length_is_inferred=True)` now
   says so plainly in the result's own notes, so it's never mistaken for a verified input.
5. **Output structure extended** (`output/indent_generator.py`): every component now reports
   `final_proposed_dimensions` (the engine's own best values), `dimensions_by_source` (grouped
   by cad_extracted/ocr_extracted/manufacturing_calculated/manually_supplied), and
   `reference_indent_dimensions` (the indent's own figures, kept structurally separate - e.g.
   Bellows width's 340mm reference next to its `MISSING` calculated value, Shroud's 2190mm next
   to the calculated 2144.62mm). Source dimensions are never overwritten by calculated ones.

## Dimension source audit (point 8 of the review)

**No native CAD/DXF extraction exists in this codebase at all** - `cad_extractor.py` always
raises `NotImplementedError` (no .dxf file has ever been supplied). Everything this engine
calls "auto-extracted" is **OCR** (PaddleOCR reading the rasterized PDF's detail panels via
`app.services.drawing_detail_extractor`), not native vector dimension entities. That
distinction matters: OCR can misread digits and has no ground truth to check itself against,
which is exactly what produced the Sleeve OD bug above.

| Component | Field | Source | How |
|---|---|---|---|
| Bellows | od | **B - OCR** | Ø marker, Bellow Detail panel |
| Bellows | length | **C - Calculated** | `(od*3.14)+10`, approved |
| Bellows | thickness | **D - Manual** | transcribed ("1 ply x 0.6mm" CAD callout) |
| Bellows | width | **MISSING** | q/w not extractable by any method |
| Bellows | convolution_count | **D - Manual** (text) → **C - Calculated** (10) | "5+5" transcribed, then parsed |
| Sleeve | od | **D - Manual** | indent SIZE column (509) - NOT trusted from OCR, see correction #1 |
| Sleeve | thickness, length | **D - Manual** | transcribed from indent |
| Sleeve | mid_pipe_interface_reference | **B - OCR** | Sleeve Detail panel, unconfirmed identity |
| Mid Pipe, End Pipe | od | **B - OCR** | Ø marker, own detail panel |
| Mid Pipe, End Pipe | thickness, length | **D - Manual** | not reliably OCR-extractable (confirmed this session) |
| Mid Pipe, End Pipe | id | **C - Calculated** | `od - 2*thickness` |
| Housing Flange | od | **B - OCR** | Ø marker, Housing Flange Detail |
| Housing Flange | id, thickness, pcd, hole_diameter, hole_count | **D - Manual** | transcribed from indent |
| Shroud | od | **B - OCR** | Ø marker, Shroud Detail |
| Shroud | base_length | **C - Calculated** | `od*3.14` |
| Shroud | length (final) | **C - Calculated, REVIEW_REQUIRED** | base_length only - allowance unapproved |
| Shroud | width, thickness | **D - Manual** | transcribed from indent |
| Limit Rod | length | **C - Calculated, REVIEW_REQUIRED** | input itself is inferred (see correction #4) - no CAD panel exists for this component at all |
| Collar | diameter, length | **D - Manual** | per instruction, must come from Detail B - not independently confirmed as sourced from Detail B specifically in this pass |
| Nut & Locknut, Shroud Support, M8 Bolt & Nut, Filler Wire, Electrode, Stiffener | size | **D - Manual** | no formula applies per spec; transcribed |
| Wooden Box | length | **MISSING** | no independent assembly-length source exists anywhere in this pipeline |
| Wooden Box | breadth, width | **D - Manual** | from indent, "approved packaging layout" not independently verified |
| All components | quantity_per_assembly | **D - Manual** (CAD BOM reference transcribed into `BOM_REFERENCE`) | not read live from the PDF per-run in this version |

**Bottom line**: only OD/ID-type diameters are genuinely automated (and that's OCR, not native
CAD parsing). Every Thickness, Length, hole/PCD spec, and all consumable specs are manually
transcribed for this WO 9374 validation run. The engine's formula layer is real and tested
independently of extraction - but today, extraction supplies only a fraction of its inputs.

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

## Generalization status (point 10 of the review: this is not just a WO 9374 reproduction tool)

**Not yet generalized.** `main.py`'s `MANUAL_INPUTS`/`BOM_REFERENCE` dicts are hardcoded to WO
9374 - this file is a validation harness proving the calculation layer is correct, not a
general-purpose "upload any drawing" entry point yet. What IS already general-purpose, because
it was built that way from the start:
- Every function in `calculations/` takes plain numbers, not a work-order name - `(OD * 3.14) +
  10` works identically for any Bellows OD.
- `rules/manufacturing_rules.json` is not WO-9374-specific; it's MB's own standing formulas.
- `extraction/pdf_extractor.extract_components()` already runs against ANY PDF with a BOM table
  and detail panels in this drawing family, not just WO 9374 - it was run earlier in this
  session against 247.pdf (a different work order) during the main app's own testing.

**To actually process a new drawing**, the remaining gap is the glue `main.py` hardcodes today:
a real integration would call `dimension_parser.get_component_evidence(new_pdf_path)`, match
each `RawComponentEvidence` to the right calculator by component name (same substring matching
already used for `find_evidence()`), and route Thickness/Length/etc. to manual-entry prompts
(not a hardcoded dict) whenever extraction can't supply them - exactly what `REVIEW_REQUIRED`/
`MISSING` statuses already exist to signal. That routing layer is the next real piece of work,
not yet built.

## Integration notes

This package is additive - the commits that built `engineering_engine/` touch only files under
that directory (`git show --stat` on commits `3c9af4b` and this review's follow-up confirms
it). Earlier commits on this same local branch did touch `app/services/drawing_detail_
extractor.py` and `bom_table_extractor.py` (the Thk/L accuracy investigation from before this
package existed) - unrelated to this engine and already covered by their own tests. The OD/ID
OCR pipeline itself (`app.services.paddle_ocr`, `bom_table_extractor`, `drawing_detail_
extractor`) is called by `pdf_extractor.py`, never modified by it. To wire this into the real upload/analyze flow later:
`extraction/pdf_extractor.extract_components()` is the integration point that already reuses
the production OCR pipeline; a router could call a generalized version of `build_wo9374_
components()` (see "Generalization status" above) after a drawing's BOM is generated, and
surface `REVIEW_REQUIRED`/`MISSING` results in the existing Components/Indent UI the same way
`requires_confirmation` already works today.

**Still local-only** (`feature/geometry-based-dimensions` branch) - not merged to `main`, not
deployed, per instruction. Will not merge or deploy without explicit approval.
