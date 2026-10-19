"""MB Metallic Bellows branded Bill of Materials PDF.

Letterhead (MB logo block, company name, address), a sky-blue title band with an orange rule,
black section bars, a striped line-item table, a cost summary, sign-off boxes and a
certification footer, styled after mbmetallicbellows.com.
"""
from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.models import Bom, Drawing
from app.services.export_service import bom_to_dataframe

COMPANY = {
    "name": "METALLIC BELLOWS PVT LTD",
    "legal": "MB Metallic Bellows Pvt Ltd",
    "tagline": "Manufacturers of Bellows Expansion Joints",
    "address": [
        "Plot # 47 & 48, SIPCOT Industrial",
        "Growth Center, Oragadam,",
        "Chennai - 602105, India",
        "info@mbmetallicbellows.com",
        "+91 44 29590111 / 12",
    ],
    "certs": "ISO 9001:2015  ·  ASME U-Stamp  ·  PED Enabled",
}

SKY_LEFT = colors.HexColor("#0a8fd8")
SKY_RIGHT = colors.HexColor("#33c6f6")
ORANGE = colors.HexColor("#f39200")
INK = colors.HexColor("#111111")
NAVY = colors.HexColor("#0f2340")
GREY = colors.HexColor("#5a6576")
RULE = colors.HexColor("#c9d2dd")
STRIPE = colors.HexColor("#eef7fd")

PAGE_W, PAGE_H = A4
MARGIN = 36
HEADER_H = 138
FOOTER_H = 58

MAKE_BUY_COLOURS = {"Make": NAVY, "Buy": colors.HexColor("#d96f00"), "Review": colors.HexColor("#b7791f")}


def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


CELL = _style("cell")
CELL_BOLD = _style("cellBold", fontName="Helvetica-Bold")
CELL_RIGHT = _style("cellRight", alignment=2)
LABEL = _style("label", fontName="Helvetica-Bold", textColor=GREY, fontSize=8)
VALUE = _style("value", fontSize=9)
NOTE = _style("note", fontSize=7.5, leading=10, textColor=GREY)


def _draw_logo(c, x: float, y: float, w: float = 60, h: float = 50) -> None:
    """The MB mark: a silver ribbed block (like a bellows) with heavy black 'MB' lettering."""
    c.saveState()
    steps = 24
    for i in range(steps):
        t = i / (steps - 1)
        shade = 0.93 - 0.28 * (1 - abs(2 * t - 1))
        c.setFillColorRGB(shade, shade + 0.01, shade + 0.02)
        c.rect(x + w * i / steps, y, w / steps + 0.3, h, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#8c949c"))
    c.setLineWidth(0.4)
    for i in range(1, 20):
        c.line(x + w * i / 20, y + 2, x + w * i / 20, y + h - 2)
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 31)
    c.drawCentredString(x + w / 2, y + h / 2 - 11, "MB")
    c.restoreState()


def _page_decor(drawing: Drawing, bom: Bom, generated: str):
    def draw(c, doc):
        c.saveState()
        top = PAGE_H - 22

        # Letterhead
        _draw_logo(c, MARGIN, top - 52)
        c.setFillColor(INK)
        c.setFont("Helvetica", 15)
        c.drawString(MARGIN + 72, top - 24, COMPANY["name"], charSpace=1.2)
        c.setFillColor(ORANGE)
        c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(MARGIN + 72, top - 40, COMPANY["tagline"])
        c.setFillColor(GREY)
        c.setFont("Helvetica", 7.5)
        for i, line in enumerate(COMPANY["address"]):
            c.drawRightString(PAGE_W - MARGIN, top - 6 - i * 10, line)

        # Sky-blue title band, full bleed, with an orange rule underneath
        band_y, band_h = top - 96, 32
        strips = 80
        for i in range(strips):
            t = i / (strips - 1)
            r = SKY_LEFT.red + (SKY_RIGHT.red - SKY_LEFT.red) * t
            g = SKY_LEFT.green + (SKY_RIGHT.green - SKY_LEFT.green) * t
            b = SKY_LEFT.blue + (SKY_RIGHT.blue - SKY_LEFT.blue) * t
            c.setFillColorRGB(r, g, b)
            c.rect(PAGE_W * i / strips, band_y, PAGE_W / strips + 0.5, band_h, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(MARGIN, band_y + 10.5, "BILL OF MATERIALS", charSpace=1.2)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(PAGE_W - MARGIN, band_y + 12,
                          f"DWG {drawing.drawing_number}   ·   REV {drawing.revision}   ·   BOM v{bom.version}")
        c.setFillColor(ORANGE)
        c.rect(0, band_y - 3, PAGE_W, 3, stroke=0, fill=1)

        if drawing.is_demo:
            c.saveState()
            c.setFillColor(colors.HexColor("#0a8fd8"))
            c.setFillAlpha(0.06)
            c.setFont("Helvetica-Bold", 86)
            c.translate(PAGE_W / 2, PAGE_H / 2 - 40)
            c.rotate(32)
            c.drawCentredString(0, 0, "DEMO DATA")
            c.restoreState()

        # Footer
        c.setStrokeColor(SKY_LEFT)
        c.setLineWidth(1.2)
        c.line(MARGIN, FOOTER_H - 14, PAGE_W - MARGIN, FOOTER_H - 14)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGIN, FOOTER_H - 26, COMPANY["legal"])
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GREY)
        c.drawCentredString(PAGE_W / 2, FOOTER_H - 26, COMPANY["certs"])
        c.drawRightString(PAGE_W - MARGIN, FOOTER_H - 26, f"Page {doc.page}")
        c.setFont("Helvetica", 6.5)
        c.drawString(MARGIN, FOOTER_H - 37,
                     f"Generated {generated} by Engineering Drawing Intelligence & BOM System. "
                     "Unit costs come from the source catalog; '—' means no catalog price on file.")
        c.restoreState()

    return draw


def _section_bar(text: str, width: float) -> Table:
    t = Table([[text]], colWidths=[width], rowHeights=[20])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _p(text, style=CELL) -> Paragraph:
    return Paragraph(escape(str(text)) if text not in (None, "") else "—", style)


def _fmt_qty(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:g}"


def bom_to_pdf_bytes(bom: Bom, drawing: Drawing) -> bytes:
    """Renders the branded BOM. The estimated total sums only Buy lines that actually carry a
    unit cost; it is labelled partial when any Buy line has none, and never invents a price."""
    buf = io.BytesIO()
    generated = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    content_w = PAGE_W - 2 * MARGIN
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=HEADER_H, bottomMargin=FOOTER_H + 6,
        title=f"BOM {drawing.drawing_number} Rev {drawing.revision}", author=COMPANY["legal"],
    )
    story: list = []

    # Drawing details
    story.append(_section_bar("DRAWING DETAILS", content_w))
    details = [
        [_p("Drawing No.", LABEL), _p(drawing.drawing_number, VALUE), _p("Revision", LABEL), _p(drawing.revision, VALUE)],
        [_p("Title", LABEL), _p(drawing.title, VALUE), _p("Scale", LABEL), _p(drawing.scale or "n/a", VALUE)],
        [_p("Units", LABEL), _p(drawing.units, VALUE), _p("BOM Version", LABEL), _p(f"v{bom.version}", VALUE)],
        [_p("BOM Status", LABEL), _p(bom.status, VALUE), _p("Generated", LABEL), _p(generated, VALUE)],
    ]
    dt = Table(details, colWidths=[78, 190, 78, content_w - 346])
    dt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f4f6f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [dt, Spacer(1, 14)]

    # Line items
    df = bom_to_dataframe(bom)
    story.append(_section_bar(f"BILL OF MATERIALS  ({len(df)} LINE ITEMS)", content_w))
    header = ["#", "Part No.", "Description", "Qty", "Total Qty", "Material", "Make / Buy", "Unit Cost", "Line Cost"]
    head_style = _style("head", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white)
    rows = [[Paragraph(h, head_style) for h in header]]
    total_cost = 0.0
    priced = 0
    counts = {"Make": 0, "Buy": 0, "Review": 0}
    buy_missing = 0
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        qty = r["Quantity"] or 0
        unit = r["Unit Cost"]
        has_unit = unit is not None and pd.notna(unit)
        line = unit * qty if has_unit else None
        mb = r["Make/Buy"] or ""
        counts[mb] = counts.get(mb, 0) + 1
        if line is not None:
            total_cost += line
            priced += 1
        elif mb == "Buy":
            buy_missing += 1
        rows.append([
            _p(i), _p(r["Part Number"], CELL_BOLD), _p(r["Description"]), _p(_fmt_qty(qty), CELL_RIGHT),
            _p(_fmt_qty(r["Total Quantity"]), CELL_RIGHT), _p(r["Material"]),
            Paragraph(escape(mb) or "—", _style(f"mb{mb}", fontName="Helvetica-Bold", textColor=MAKE_BUY_COLOURS.get(mb, INK))),
            _p(f"${unit:,.2f}" if has_unit else "—", CELL_RIGHT),
            _p(f"${line:,.2f}" if line is not None else "—", CELL_RIGHT),
        ])
    widths = [18, 76, 142, 32, 38, 78, 46, 46, content_w - 476]
    table = Table(rows, colWidths=widths, repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), SKY_LEFT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_i in range(1, len(rows)):
        if row_i % 2 == 0:
            ts.append(("BACKGROUND", (0, row_i), (-1, row_i), STRIPE))
    table.setStyle(TableStyle(ts))
    story += [table if len(rows) > 1 else _p("No line items in this BOM."), Spacer(1, 16)]

    # Summary + sign-off, side by side
    if priced:
        cost_text = f"${total_cost:,.2f}"
        cost_note = f"Partial — {buy_missing} Buy item(s) have no catalog price." if buy_missing else "All Buy items priced from the source catalog."
    else:
        cost_text, cost_note = "—", "No catalog prices on file for this BOM."
    summary_rows = [
        [_p("Make items", LABEL), _p(counts.get("Make", 0), VALUE)],
        [_p("Buy items", LABEL), _p(counts.get("Buy", 0), VALUE)],
        [_p("Needs review", LABEL), _p(counts.get("Review", 0), VALUE)],
        [_p("Est. purchase cost", LABEL), Paragraph(f"<b>{escape(cost_text)}</b>", _style("cost", fontSize=12, textColor=ORANGE))],
        [Paragraph(escape(cost_note), NOTE), ""],
    ]
    summary = Table([[_section_bar("COST SUMMARY", 236)]] + [[Table(summary_rows, colWidths=[110, 126])]], colWidths=[236])
    inner_summary = summary._cellvalues[1][0]
    inner_summary.setStyle(TableStyle([
        ("SPAN", (0, 4), (1, 4)),
        ("LINEBELOW", (0, 0), (-1, 3), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    summary.setStyle(TableStyle([("BOX", (0, 1), (-1, 1), 0.6, RULE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0)]))

    sign_w = content_w - 236 - 14
    box_w = sign_w / 3
    sign_cells = [[
        Paragraph(f"<b>{role}</b><br/><br/><br/><font color='#5a6576'>Name: ________________<br/>Sign: ________________<br/>Date: ________________</font>", CELL)
        for role in ("Prepared by", "Checked by", "Approved by")
    ]]
    signs = Table(sign_cells, colWidths=[box_w] * 3)
    signs.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    sign_block = Table([[_section_bar("SIGN-OFF", sign_w)], [signs]], colWidths=[sign_w])
    sign_block.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                    ("TOPPADDING", (0, 0), (-1, -1), 0)]))

    bottom = Table([[summary, "", sign_block]], colWidths=[236, 14, sign_w])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(bottom)

    decor = _page_decor(drawing, bom, generated)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return buf.getvalue()
