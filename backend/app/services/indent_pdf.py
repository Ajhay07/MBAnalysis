"""Renders a generated Indent as a PDF matching the layout of MB Metallic Bellows' physical
indent sheet form (W.O. No. / Date / Party's Name / Required On / SL.No. header block, a
Sl.No. / MTL SPEC / SIZE / WT/QTY table, Authorised-by + Indentor sign-off). Reuses the MB
logo block from app.services.bom_pdf so the two documents share one letterhead mark.
"""
from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.models import Indent
from app.services.bom_pdf import COMPANY, _draw_logo

INK = colors.HexColor("#111111")
GREY = colors.HexColor("#5a6576")
RULE = colors.HexColor("#111111")
STRIPE = colors.HexColor("#f4f6f9")
WARN_BG = colors.HexColor("#fff3e0")
WARN_TEXT = colors.HexColor("#b7791f")

PAGE_W, PAGE_H = A4
MARGIN = 40


def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


CELL = _style("indentCell")
CELL_BOLD = _style("indentCellBold", fontName="Helvetica-Bold")
CELL_RIGHT = _style("indentCellRight", alignment=2)
LABEL = _style("indentLabel", fontName="Helvetica-Bold", fontSize=9)
VALUE = _style("indentValue", fontSize=10)
WARN = _style("indentWarn", fontSize=7.5, textColor=WARN_TEXT, fontName="Helvetica-Oblique")


def _p(text, style=CELL) -> Paragraph:
    if text in (None, ""):
        return Paragraph("—", style)
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _fmt_qty(value, unit: str) -> str:
    if value is None:
        return "TBD"
    return f"{value:g} {unit}".strip()


def indent_to_pdf_bytes(indent: Indent) -> bytes:
    """Renders the indent. Any line with requires_confirmation=True prints "TBD" in WT/QTY
    with an orange highlight instead of a fabricated number - this must stay visible on the
    printed/exported form, not just in the review UI."""
    buf = io.BytesIO()
    generated = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    content_w = PAGE_W - 2 * MARGIN
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 40,
        title=f"Indent Sheet WO {indent.wo_number}", author=COMPANY["legal"],
    )
    story: list = []

    # Letterhead: logo + title, mirroring the physical pink form's top band.
    header = Table(
        [[
            "",  # logo drawn directly on canvas below (needs raw coordinates)
            Paragraph(f"<b>W.O. No.: {escape(indent.wo_number or '—')}</b>", _style("wo", fontSize=13)),
            Paragraph("<b>INDENT SHEET</b>", _style("title", fontSize=16, alignment=1)),
            Paragraph(f"Date: {escape(indent.indent_date or '—')}", VALUE),
        ]],
        colWidths=[66, content_w * 0.28, content_w * 0.34, content_w - 66 - content_w * 0.62],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 0), (3, 0), "RIGHT"),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))

    meta_rows = [
        [_p("PARTY'S NAME:", LABEL), _p(indent.party_name, VALUE),
         _p("SL.No.:", LABEL), _p(indent.serial_no, VALUE)],
        [_p("REQUIRED ON:", LABEL), _p(indent.required_on, VALUE),
         _p("ASSEMBLY QTY:", LABEL), _p(f"{indent.assembly_quantity:g}", VALUE)],
    ]
    meta = Table(meta_rows, colWidths=[86, content_w - 86 - 90 - 90, 90, 90])
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, -1), (-1, -1), 1, RULE),
    ]))
    story += [meta, Spacer(1, 10)]

    header_style = _style("indentHead", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white)
    rows = [[Paragraph(h, header_style) for h in ["Sl.No.", "MTL SPEC", "SIZE", "WT/QTY"]]]
    any_unconfirmed = False
    for line in indent.lines:
        if line.requires_confirmation:
            any_unconfirmed = True
        qty_style = CELL_RIGHT
        rows.append([
            _p(line.sl_no, CELL_BOLD),
            _p(line.mtl_spec),
            _p(line.size_text),
            _p(_fmt_qty(line.wt_qty, line.unit), qty_style),
        ])
    widths = [40, content_w * 0.34, content_w * 0.36, content_w - 40 - content_w * 0.70]
    table = Table(rows, colWidths=widths, repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BOX", (0, 0), (-1, -1), 1, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, line in enumerate(indent.lines, start=1):
        if line.requires_confirmation:
            ts.append(("BACKGROUND", (0, i), (-1, i), WARN_BG))
        elif i % 2 == 0:
            ts.append(("BACKGROUND", (0, i), (-1, i), STRIPE))
    table.setStyle(TableStyle(ts))
    story += [table if len(rows) > 1 else _p("No line items on this indent."), Spacer(1, 10)]

    if any_unconfirmed:
        story.append(_p(
            "Rows highlighted above show \"TBD\" because no approved quantity rule or extracted "
            "value is on file - confirm these before this indent is issued for procurement.",
            WARN,
        ))
        story.append(Spacer(1, 10))

    sign_w = content_w / 2 - 8
    sign_cells = [[
        Paragraph("<b>Authorised by</b><br/>MB / PRD. Fo 3/0<br/><br/><br/>________________________", CELL),
        Paragraph("<b>Indentor</b><br/><br/><br/><br/>________________________", CELL),
    ]]
    signs = Table(sign_cells, colWidths=[sign_w, sign_w])
    signs.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(signs)

    def decor(c, doc_):
        c.saveState()
        _draw_logo(c, MARGIN, PAGE_H - MARGIN - 50, w=54, h=44)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 6.5)
        c.drawString(MARGIN, 20, f"Generated {generated} by Engineering Drawing Intelligence & BOM System.")
        c.drawRightString(PAGE_W - MARGIN, 20, f"Page {doc_.page}")
        c.restoreState()

    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return buf.getvalue()
