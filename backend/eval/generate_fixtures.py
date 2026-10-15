"""Generates synthetic OCR evaluation fixtures (images + multi-page PDF + ground truth JSON).

Run once with: python eval/generate_fixtures.py
Writes into eval/ocr_dataset/synthetic/. Safe to re-run (overwrites deterministically).

These are SYNTHETIC fixtures only - rendered title blocks / BOM tables / dimension callouts,
not real engineering drawings. Keep them in synthetic/, never real/.
"""
from __future__ import annotations

import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ocr_dataset", "synthetic")


def _font(size: int):
    for candidate in (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _blank(w=1000, h=700):
    img = Image.new("RGB", (w, h), "white")
    return img, ImageDraw.Draw(img)


def make_fixture_01_titleblock_dimensions():
    """Title block + dimension callouts with decimals, diameter symbol, tolerance."""
    img, d = _blank()
    f_big = _font(28)
    f_mid = _font(22)
    d.rectangle([20, 20, 980, 680], outline="black", width=2)
    d.text((40, 40), "DRAWING NO: MB-10045-REV-C", font=f_big, fill="black")
    d.text((40, 90), "TITLE: Pump Housing Bracket", font=f_mid, fill="black")
    d.text((40, 130), "REVISION: C   SCALE: 1:2   UNITS: mm", font=f_mid, fill="black")
    d.line([30, 170, 970, 170], fill="black", width=2)
    d.text((40, 200), "BORE DIAMETER: \u00d812.5mm  +/-0.1mm TOLERANCE", font=f_mid, fill="black")
    d.text((40, 250), "OVERALL LENGTH: 45.25mm", font=f_mid, fill="black")
    d.text((40, 300), "WALL THICKNESS: 3.75mm \u00b10.05mm", font=f_mid, fill="black")
    d.text((40, 350), "MATERIAL: Aluminum 6061-T6", font=f_mid, fill="black")
    path = os.path.join(OUT, "fixture_01_titleblock_dimensions.png")
    img.save(path)
    gt = {
        "full_text": (
            "DRAWING NO: MB-10045-REV-C\nTITLE: Pump Housing Bracket\n"
            "REVISION: C   SCALE: 1:2   UNITS: mm\n"
            "BORE DIAMETER: \u00d812.5mm  +/-0.1mm TOLERANCE\n"
            "OVERALL LENGTH: 45.25mm\nWALL THICKNESS: 3.75mm \u00b10.05mm\n"
            "MATERIAL: Aluminum 6061-T6"
        ),
        "critical_fields": {
            "drawing_number": "MB-10045-REV-C",
            "dimension": "45.25mm",
            "tolerance": "\u00b10.05mm",
            "diameter": "\u00d812.5mm",
        },
        "notes": "Title block + dimension callouts; tests decimals, diameter symbol, tolerance.",
    }
    with open(os.path.join(OUT, "fixture_01_titleblock_dimensions.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
    return path


def make_fixture_02_bom_table():
    """Small BOM-style table."""
    img, d = _blank()
    f_mid = _font(22)
    f_small = _font(18)
    d.text((40, 30), "BILL OF MATERIALS", font=f_mid, fill="black")
    rows = [
        ("ITEM", "PART NO", "DESCRIPTION", "QTY"),
        ("1", "BRK-200", "Mounting Bracket", "4"),
        ("2", "SHF-305", "Drive Shaft 10.0mm", "1"),
        ("3", "BRG-6204", "Ball Bearing 6204-2RS", "2"),
        ("4", "SCR-M6X20", "Hex Screw M6x20", "8"),
    ]
    y = 90
    for row in rows:
        d.text((40, y), f"{row[0]:<6}{row[1]:<14}{row[2]:<26}{row[3]}", font=f_small, fill="black")
        y += 36
    path = os.path.join(OUT, "fixture_02_bom_table.png")
    img.save(path)
    gt = {
        "full_text": "BILL OF MATERIALS\n" + "\n".join(
            f"{r[0]:<6}{r[1]:<14}{r[2]:<26}{r[3]}" for r in rows
        ),
        "critical_fields": {
            "part_number": "BRG-6204",
            "dimension": "10.0mm",
            "quantity": "8",
        },
        "notes": "Small BOM table; tests fixed-width tabular text recognition.",
    }
    with open(os.path.join(OUT, "fixture_02_bom_table.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
    return path


def make_fixture_03_small_text_dense():
    """Small font size + dense multi-value callouts (stresses small-text recognition)."""
    img, d = _blank()
    f_small = _font(14)
    d.text((40, 30), "NOTES (SMALL TEXT):", font=_font(20), fill="black")
    lines = [
        "1. ALL DIMENSIONS IN MILLIMETERS UNLESS NOTED.",
        "2. BREAK ALL SHARP EDGES 0.25mm MAX.",
        "3. HOLE A: \u00d86.35mm +0.05/-0.00mm",
        "4. HOLE B: \u00d83.20mm \u00b10.02mm",
        "5. SURFACE FINISH: 1.6 Ra MICRONS",
        "6. TOLERANCE UNLESS SPECIFIED: \u00b10.1mm",
        "7. DRAWING NO: MB-20391-A",
    ]
    y = 70
    for ln in lines:
        d.text((40, y), ln, font=f_small, fill="black")
        y += 26
    path = os.path.join(OUT, "fixture_03_small_text_dense.png")
    img.save(path)
    gt = {
        "full_text": "NOTES (SMALL TEXT):\n" + "\n".join(lines),
        "critical_fields": {
            "drawing_number": "MB-20391-A",
            "dimension": "\u00d86.35mm",
            "tolerance": "\u00b10.1mm",
        },
        "notes": "Small (14pt) dense text with multiple tolerance/diameter callouts.",
    }
    with open(os.path.join(OUT, "fixture_03_small_text_dense.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
    return path


def make_fixture_04_multipage_pdf():
    """2-page PDF: page 1 title block, page 2 dimension/tolerance callouts."""
    import fitz  # pymupdf

    p1_png = os.path.join(OUT, "_tmp_mp_page1.png")
    p2_png = os.path.join(OUT, "_tmp_mp_page2.png")

    img1, d1 = _blank()
    f_big = _font(28)
    d1.text((40, 40), "DRAWING NO: MB-30077-REV-B", font=f_big, fill="black")
    d1.text((40, 90), "TITLE: Gearbox Output Shaft", font=_font(22), fill="black")
    img1.save(p1_png)

    img2, d2 = _blank()
    d2.text((40, 40), "PAGE 2 - DIMENSIONS", font=_font(26), fill="black")
    d2.text((40, 100), "SHAFT DIAMETER: \u00d822.00mm +0.02/-0.00mm", font=_font(22), fill="black")
    d2.text((40, 150), "KEYWAY WIDTH: 6.25mm \u00b10.03mm", font=_font(22), fill="black")
    img2.save(p2_png)

    doc = fitz.open()
    for png in (p1_png, p2_png):
        with Image.open(png) as im:
            w, h = im.width, im.height
        page = doc.new_page(width=w, height=h)
        page.insert_image(page.rect, filename=png)
    pdf_path = os.path.join(OUT, "fixture_04_multipage.pdf")
    doc.save(pdf_path)
    doc.close()
    os.remove(p1_png)
    os.remove(p2_png)

    gt = {
        "pages": {
            "1": {
                "full_text": "DRAWING NO: MB-30077-REV-B\nTITLE: Gearbox Output Shaft",
                "critical_fields": {"drawing_number": "MB-30077-REV-B"},
            },
            "2": {
                "full_text": "PAGE 2 - DIMENSIONS\nSHAFT DIAMETER: \u00d822.00mm +0.02/-0.00mm\n"
                              "KEYWAY WIDTH: 6.25mm \u00b10.03mm",
                "critical_fields": {"dimension": "6.25mm", "diameter": "\u00d822.00mm",
                                     "tolerance": "\u00b10.03mm"},
            },
        },
        "notes": "Multi-page PDF; tests per-page rasterization + OCR across pages.",
    }
    with open(os.path.join(OUT, "fixture_04_multipage.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
    return pdf_path


def make_fixture_05_rotated_text():
    """Mildly rotated/skewed text block (tests deskew toggle)."""
    img, d = _blank()
    layer = Image.new("RGBA", (700, 150), (255, 255, 255, 255))
    ld = ImageDraw.Draw(layer)
    ld.text((10, 50), "DRAWING NO: MB-40012-A  DIA \u00d89.50mm \u00b10.08mm", font=_font(24), fill="black")
    rotated = layer.rotate(4, expand=True, fillcolor=(255, 255, 255, 255))
    img.paste(rotated, (100, 250), rotated)
    path = os.path.join(OUT, "fixture_05_rotated_text.png")
    img.convert("RGB").save(path)
    gt = {
        "full_text": "DRAWING NO: MB-40012-A  DIA \u00d89.50mm \u00b10.08mm",
        "critical_fields": {
            "drawing_number": "MB-40012-A",
            "diameter": "\u00d89.50mm",
            "tolerance": "\u00b10.08mm",
        },
        "notes": "Text rotated ~4 degrees; used to compare OCR_PREPROCESS_DESKEW on vs off.",
    }
    with open(os.path.join(OUT, "fixture_05_rotated_text.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
    return path


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    made = [
        make_fixture_01_titleblock_dimensions(),
        make_fixture_02_bom_table(),
        make_fixture_03_small_text_dense(),
        make_fixture_04_multipage_pdf(),
        make_fixture_05_rotated_text(),
    ]
    for m in made:
        print("wrote", m)
