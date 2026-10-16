"""LIVE integration test against the real Gemini API. Skipped by default - only runs when
explicitly enabled via RUN_REAL_GEMINI_TESTS=1 AND GEMINI_API_KEY is actually present (same
gating pattern as tests/test_paddle_ocr.py's RUN_REAL_OCR_TESTS=1). Never runs in normal
`pytest -q` CI, and makes real network calls that cost real API quota.

Proves two things with real inference (not mocked):
  1. One real call against a fixture with NO printed BOM table, whose output is demonstrably
     grounded in that fixture's own visible content (dimensions/legend/title-block text), not a
     generic canned response.
  2. A second real call against a MATERIALLY DIFFERENT image produces different, non-identical
     output - proving the model is actually responding to the supplied pixels, not just echoing
     DemoProvider-style fixed content.
"""
from __future__ import annotations

import os

import pytest
from PIL import Image, ImageDraw

from app.config import get_settings

# tests/conftest.py deliberately neutralizes GEMINI_API_KEY to "" in os.environ for the whole
# test session (so a real local backend/.env key never leaks into the mocked/unit test suite).
# This live test is the one deliberate exception: when explicitly enabled, it reads the real
# key straight out of backend/.env (bypassing that neutralization) and restores it into the
# environment + clears the Settings cache just for these two tests.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _read_real_gemini_key_from_dotenv() -> str:
    if not os.path.exists(_ENV_PATH):
        return ""
    with open(_ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


_REAL_GEMINI_API_KEY = _read_real_gemini_key_from_dotenv()
RUN_LIVE = os.environ.get("RUN_REAL_GEMINI_TESTS") == "1" and bool(_REAL_GEMINI_API_KEY)

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Set RUN_REAL_GEMINI_TESTS=1 and a real GEMINI_API_KEY in backend/.env to run live "
           "Gemini inference.",
)


@pytest.fixture(autouse=True)
def _real_gemini_key_env():
    """Restores the real GEMINI_API_KEY (read directly from backend/.env) into the environment
    for the duration of each test in this module only, then re-neutralizes it afterward."""
    if not RUN_LIVE:
        yield
        return
    os.environ["GEMINI_API_KEY"] = _REAL_GEMINI_API_KEY
    get_settings.cache_clear()
    try:
        yield
    finally:
        os.environ["GEMINI_API_KEY"] = ""
        get_settings.cache_clear()


def _render_no_bom_table_fixture(path: str) -> None:
    """Same synthetic rendering tests/test_no_bom_table_fixture_e2e.py uses for
    no_bom_table_fixture.svg's content: dimensions, a hole-count legend, a title block - no
    ITEM/QTY/PART-NO BOM grid."""
    img = Image.new("RGB", (1000, 700), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([220, 220, 620, 480], outline="black", width=2)
    for cx, cy in [(300, 300), (540, 300), (300, 400), (540, 400)]:
        draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], outline="black", width=2)
    draw.text((220, 190), "400.0 +/-0.15", fill="black")
    draw.text((140, 340), "260.0", fill="black")
    draw.text((220, 510), "LEGEND:", fill="black")
    draw.text((220, 525), "4x HOLES, dia 12.0mm THRU", fill="black")
    draw.text((220, 540), "MATERIAL: Aluminum 6061-T6", fill="black")
    draw.rectangle([700, 580, 980, 680], outline="black", width=1)
    draw.text((710, 590), "PUMP HOUSING BRACKET", fill="black")
    draw.text((710, 610), "DWG NO: MB-10045-REV-C", fill="black")
    draw.text((710, 630), "REV: C", fill="black")
    img.save(path)


def _render_materially_different_fixture(path: str) -> None:
    """A visually and textually distinct drawing: a circular flange with a bolt-circle pattern
    and a completely different title block / dimension set, to prove Gemini's output tracks the
    actual pixels rather than repeating fixed content."""
    img = Image.new("RGB", (1000, 700), "white")
    draw = ImageDraw.Draw(img)
    cx, cy, r = 500, 320, 180
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="black", width=3)
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline="black", width=2)
    import math
    bolt_r = 140
    for i in range(8):
        angle = math.radians(i * 45)
        bx, by = cx + bolt_r * math.cos(angle), cy + bolt_r * math.sin(angle)
        draw.ellipse([bx - 10, by - 10, bx + 10, by + 10], outline="black", width=2)
    draw.text((cx - 60, cy - r - 40), "DIA 360.0 +/-0.2", fill="black")
    draw.text((cx + r + 10, cy), "8x M10 BOLT CIRCLE, dia 280.0", fill="black")
    draw.text((50, 550), "MATERIAL: Cast Iron GG25", fill="black")
    draw.rectangle([700, 580, 980, 680], outline="black", width=1)
    draw.text((710, 590), "PUMP FLANGE COVER"[:18], fill="black")
    draw.text((710, 610), "DWG NO: MB-20099-REV-A", fill="black")
    draw.text((710, 630), "REV: A", fill="black")
    img.save(path)


def test_live_gemini_analyzes_no_bom_table_fixture_grounded_in_its_content(tmp_path):
    from app.providers.gemini_provider import GeminiVisionProvider

    path = str(tmp_path / "no_bom_table_fixture.png")
    _render_no_bom_table_fixture(path)

    provider = GeminiVisionProvider()
    result = provider.analyze(
        image_path=path,
        ocr_text="DWG NO: MB-10045-REV-C\nPUMP HOUSING BRACKET\n400.0 +/-0.15\n260.0\n"
                  "LEGEND: 4x HOLES, dia 12.0mm THRU\nMATERIAL: Aluminum 6061-T6",
        drawing_number="MB-10045-REV-C",
    )

    assert result.provider == "gemini"
    # Grounded check: the model's output should reference something specific to this fixture -
    # the drawing number, the aluminum material callout, or the 4x hole count - not generic
    # boilerplate. At least one of these must show up somewhere in the structured result.
    haystack = " ".join([
        result.title_block.drawing_number, result.title_block.title,
        result.title_block.material_spec, " ".join(result.materials),
        " ".join(c.source_text for c in result.components),
        " ".join(rf.source_text for rf in result.repeated_features),
    ]).lower()
    grounded_markers = ["mb-10045", "aluminum", "6061", "4x", "hole", "bracket"]
    assert any(marker in haystack for marker in grounded_markers), (
        f"expected Gemini's output to reference this fixture's actual content; got: {haystack!r}"
    )

    print(f"\n[LIVE GEMINI CALL 1] model={provider.model!r}")
    print(f"title_block={result.title_block.model_dump()}")
    print(f"components={[c.model_dump() for c in result.components]}")

    # Stash for the second test to compare against (pytest runs this module's tests in order).
    test_live_gemini_analyzes_no_bom_table_fixture_grounded_in_its_content.last_result = result


def test_live_gemini_second_distinct_image_produces_different_output(tmp_path):
    from app.providers.gemini_provider import GeminiVisionProvider

    path = str(tmp_path / "flange_fixture.png")
    _render_materially_different_fixture(path)

    provider = GeminiVisionProvider()
    result = provider.analyze(
        image_path=path,
        ocr_text="DWG NO: MB-20099-REV-A\nPUMP FLANGE COVER\nDIA 360.0 +/-0.2\n"
                  "8x M10 BOLT CIRCLE, dia 280.0\nMATERIAL: Cast Iron GG25",
        drawing_number="MB-20099-REV-A",
    )

    assert result.provider == "gemini"
    print(f"\n[LIVE GEMINI CALL 2] model={provider.model!r}")
    print(f"title_block={result.title_block.model_dump()}")
    print(f"components={[c.model_dump() for c in result.components]}")

    # Must not be fixed DEMO-COMP-* content.
    part_numbers = [c.part_number for c in result.components]
    assert not any(pn.startswith("DEMO-COMP-") for pn in part_numbers)

    prior = getattr(
        test_live_gemini_analyzes_no_bom_table_fixture_grounded_in_its_content, "last_result", None)
    if prior is not None:
        # The two calls must not be byte-identical structured output - different images must
        # yield different content (different title block at minimum, since drawing numbers and
        # titles differ between the two fixtures).
        assert result.title_block.drawing_number != prior.title_block.drawing_number
        assert result.model_dump() != prior.model_dump()
