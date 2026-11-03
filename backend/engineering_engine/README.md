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
python -m pytest engineering_engine/tests -q      # 66 unit tests
python -m engineering_engine.main                 # WO 9374, via the generalized routing pipeline
```

Sample output: `engineering_engine/sample_output/wo9374.json`,
`wo_simple_001.json`, `wo_edge_cases_002.json` (the two synthetic fixtures).

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
WorkOrderInputs (routing/work_order_inputs.py)
        ↓
routing/pipeline.py: for each ComponentInput →
    extraction/pdf_extractor.py → RawComponentEvidence (OD/ID, if a PDF was supplied)
        ↓
    routing/registry.classify_component() → ComponentSpec (or UNCLASSIFIED)
        ↓
    routing/component_builders.py → calls the matching calculations/*.py function(s)
        ↓
    validation/ → DimensionResult(s) with status, BOM qty + discrepancy checking
        ↓
output/indent_generator.py → one JSON per work order, + a diagnostics block
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
        bom_validator.py        # qty_per_assembly * assemblies, + discrepancy/reference-only qty
        calculation_validator.py  # compares a result to a reference value, never forces a match
    output/
        indent_generator.py  # assembles DimensionResults into the JSON shape (+ by-source breakdown)
    routing/                 # NEW: the generalized pipeline (see below)
        registry.py           # ComponentSpec catalog + classify_component()
        component_builders.py # one adapter per spec, calls the EXISTING calculators
        work_order_inputs.py  # WorkOrderInputs/ComponentInput - how a new WO is defined
        pipeline.py            # process_work_order() - the single entry point
    fixtures/                 # NEW: synthetic WorkOrderInputs for routing tests
        wo_simple_001.py, wo_edge_cases_002.py
    tests/                   # 66 unit tests: calculators, validation, registry, routing pipeline
    sample_output/           # wo9374.json, wo_simple_001.json, wo_edge_cases_002.json
    main.py                  # WO 9374 as a WorkOrderInputs, run through routing.pipeline
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

## Generalized routing layer (this revision)

**Status: implemented and tested, local-only.** `main.py` no longer contains any WO-9374-
specific logic - it defines WO 9374 as a `WorkOrderInputs` object and runs it through the same
generalized pipeline any other work order uses. Two synthetic fixtures (`fixtures/
wo_simple_001.py`, `fixtures/wo_edge_cases_002.py`) prove the routing logic itself generalizes;
WO 9374 remains the only real-drawing-verified case (see "Generalization status" further down
for what that distinction actually means).

```
Drawing Input (PDF path, optional)
    │
    ▼
Drawing Extraction          extraction/pdf_extractor.py - reuses app.services' OCR pipeline,
    │                        unmodified. Degrades to "no evidence" if unavailable, never crashes.
    ▼
Component Identification    routing/pipeline.py matches each WorkOrderInputs entry's
    │                        description to CAD-extracted evidence by substring (OCR-tolerant)
    ▼
Component Classification    routing/registry.classify_component() - alias match against the
    │                        14-entry ComponentSpec registry. None -> reported as UNCLASSIFIED,
    │                        never dropped, never guessed.
    ▼
Parameter Mapping           routing/component_builders.py - one adapter per spec, pulls od/id
    │                        from evidence, everything else from WorkOrderInputs.manual
    ▼
Manufacturing Rule Selection  implicit in which builder/calculator ran - rules themselves come
    │                        from rules/manufacturing_rules.json, same file regardless of WO
    ▼
Dimension Calculation       calculations/*.py - UNCHANGED, called by the builders
    ▼
Engineering Validation      validation/dimension_validator.py - UNCHANGED
    ▼
BOM Quantity Calculation    validation/bom_validator.py - UNCHANGED (+ new reference_only_
    │                        quantity() for components with no per-assembly figure)
    ▼
Indent JSON Generation      output/indent_generator.py - UNCHANGED, + a new top-level
                             "diagnostics" block (unclassified/unaccounted/duplicate matches)
```

### Component registry (14 entries, per the spec's list)

| Identifier | Aliases (examples) | Calculator | Required parameters |
|---|---|---|---|
| BELLOWS | BELLOW, BELLOWS | `bellows_calculator` | od |
| SHROUD | SHROUD | `shroud_calculator` | od |
| MID_PIPE | MID PIPE, MIDPIPE | `pipe_calculator` | od, thickness |
| END_PIPE | END PIPE, ENDPIPE | `pipe_calculator` | od, thickness |
| SLEEVE | SLEEVE, SLEEV (OCR-truncated) | `sleeve_calculator` | od |
| HOUSING_FLANGE | HOUSING FLANGE, FLANGE | `flange_calculator.housing_flange_dimensions` | od, id, thickness, pcd, hole_diameter |
| LIMIT_ROD | LIMIT ROD | `flange_calculator.calculate_limit_rod_length` | cad_length |
| COLLAR | COLLAR | `flange_calculator.collar_dimensions` | diameter, length |
| SHROUD_SUPPORT | SHROUD SUPPORT | pass-through | size |
| STIFFENER | STIFFENER | pass-through | size |
| WOODEN_BOX | WOODEN BOX, PACKING/PACKAGING BOX | `packaging_calculator` | assembly_length_mm |
| BOLTS_AND_NUTS | NUT AND LOCKNUT, BOLT AND NUT, M8 BOLT, ... | pass-through | size |
| FILLER_WIRE | FILLER WIRE | pass-through | size |
| ELECTRODE | ELECTRODE | pass-through | size |

Full detail (optional parameters, extraction sources, validation requirements) is available
programmatically via `routing.registry.list_registered_components()`.

### How classification works

`classify_component()` normalizes the BOM row's description (uppercase, "&"→"AND", periods
stripped) and matches it against every spec's aliases - exact match first, then substring
either direction (tolerating OCR truncation like "SLEEV"), with the LONGEST matching alias
winning ties. A genuinely tied match, or no match at all, returns `None` - the row is reported
as `UNCLASSIFIED` in the output, never silently dropped or guessed into the wrong spec.

### How a new work order is added

A new work order is a new `WorkOrderInputs` object (see `fixtures/wo_simple_001.py` for a
minimal example) - never a code change to `routing/`. It needs: a work order name, assembly
quantity, optional CAD PDF path, and a list of `ComponentInput` entries (description, material,
manual parameter readings, reference indent values, and quantity). Run it with:

```python
from engineering_engine.routing.pipeline import process_work_order
output = process_work_order(my_work_order_inputs)
```

### Multi-component-type test results

```
$ python -m pytest engineering_engine/tests -q
66 passed in ~18s   (43 existing calculator/validation tests + 23 new routing/registry tests)

$ python -m pytest -q    # full backend suite, from backend/
257 passed, 2 skipped    (191 existing app tests + 66 engineering_engine tests)
```

Covers every scenario the review asked for: multiple work orders (WO 9374 + 2 synthetic),
different component combinations (4-component vs. 15-component BOMs), component
classification (exact/truncated/unknown/ambiguous), rule selection (same unapproved-Shroud-
allowance rule applied identically across two different work orders - proving it's not WO-
9374-specific), missing parameters, unapproved allowances, duplicate component
classification (two BOM rows -> one spec, kept as separate output entries), BOM quantity
discrepancies (both the real WO 9374 one and a synthetic one), unknown components, and
explicit-override routing for ambiguous/mis-OCR'd descriptions.

## Corrections from code review (previous revision)

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

**The routing layer described above is now built and tested** - `main.py` is a `WorkOrderInputs`
definition run through the same `routing.pipeline.process_work_order()` any work order uses; no
WO-9374-specific branching exists anywhere in `routing/`. That is real, tested generalization of
the ROUTING logic (classification, rule selection, duplicate/unknown handling, output shape).

**What is still NOT generalized - be precise about this distinction:**
- **Extraction accuracy beyond OD/ID remains exactly where it was.** The routing layer changes
  *how* a Thickness/Length/PCD/etc. gets into the system (now a `ComponentInput.manual` field on
  a `WorkOrderInputs` object, not a hardcoded dict) - it does not make those values any more
  extractable than they were. For a genuinely new drawing, someone still has to supply those
  manually, exactly as WO 9374's own `wo_9374_inputs()` does.
- **Only one real drawing (WO 9374) has been run through this**, end to end, with its result
  checked against a real indent sheet. The two new fixtures (`fixtures/wo_simple_001.py`,
  `fixtures/wo_edge_cases_002.py`) are **synthetic** - built specifically to exercise routing
  edge cases (unknown component, missing parameter, duplicate classification, quantity
  discrepancy), not derived from real drawings. They prove the routing code path works
  correctly; they do NOT prove this generalizes to real-world new drawings, which may have
  component names, layouts, or conventions the 14-entry registry/alias list hasn't seen yet.
- `extraction/pdf_extractor.extract_components()` itself is unchanged by this work - it already
  ran against a different real work order (247.pdf) during the main app's own testing earlier
  this session, so the OCR/BOM-table layer underneath the routing layer was already somewhat
  drawing-independent; this revision doesn't add to that, it just wires it in generically.

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
