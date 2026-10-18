from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from app.models.models import Bom, Drawing

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_formula(value):
    """Defuses spreadsheet formula injection: a cell value beginning with
    =,+,-,@ (or tab/CR) is interpreted as a formula by Excel/LibreOffice/Sheets
    when the exported CSV/XLSX is opened. Prefix with a single quote so it is
    treated as plain text, matching the standard CSV-injection mitigation."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.map(neutralize_formula)


def bom_export_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_BOM.{ext}"


def purchase_list_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_PurchaseList.{ext}"


def material_summary_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_MaterialSummary.{ext}"


def _bom_levels(bom: Bom) -> dict[str, int]:
    """Depth of each line item: 0 for top-level, incrementing per nesting level.
    Guards against malformed/cyclic parent chains instead of looping forever."""
    by_id = {li.id: li for li in bom.line_items}
    levels: dict[str, int] = {}

    def depth(item_id: str, trail: set[str]) -> int:
        if item_id in levels:
            return levels[item_id]
        if item_id in trail:
            return 0
        item = by_id.get(item_id)
        if item is None or not item.parent_line_item_id or item.parent_line_item_id not in by_id:
            levels[item_id] = 0
            return 0
        d = 1 + depth(item.parent_line_item_id, trail | {item_id})
        levels[item_id] = d
        return d

    for li in bom.line_items:
        depth(li.id, set())
    return levels


def bom_to_dataframe(bom: Bom) -> pd.DataFrame:
    levels = _bom_levels(bom)
    part_numbers = {li.id: li.part_number for li in bom.line_items}
    rows = [{
        "Level": levels.get(li.id, 0),
        "Part Number": li.part_number,
        "Description": ("  " * levels.get(li.id, 0)) + li.description,
        "Category": li.category,
        "Quantity": li.quantity,
        "Total Quantity": li.total_quantity,
        "Material": li.material,
        "Make/Buy": li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy,
        "Unit Cost": li.unit_cost,
        "Parent Item Number": part_numbers.get(li.parent_line_item_id, "") if li.parent_line_item_id else "",
        "Parent Line Item": li.parent_line_item_id or "",
    } for li in bom.line_items]
    return pd.DataFrame(rows)


def purchase_list_dataframe(bom: Bom) -> pd.DataFrame:
    df = bom_to_dataframe(bom)
    if df.empty:
        return df
    return df[df["Make/Buy"].isin(["Buy", "Review"])].copy()


def material_summary_dataframe(bom: Bom) -> pd.DataFrame:
    df = bom_to_dataframe(bom)
    if df.empty:
        return df
    summary = df.groupby("Material", dropna=False)["Quantity"].sum().reset_index()
    return summary


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    sanitize_dataframe(df).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sanitize_dataframe(df).to_excel(writer, index=False, sheet_name="Sheet1")
    return buf.getvalue()


def bom_to_pdf_bytes(bom: Bom, drawing: Drawing) -> bytes:
    """Renders a printable Bill of Materials PDF: drawing header/title block, the full line-item
    table (indented by assembly level, same data as the CSV/Excel export), and an estimated
    total purchase cost summed only over Buy lines that actually have a unit cost - never
    fabricates a price for a line that has none."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Bill of Materials &mdash; {drawing.drawing_number}", styles["Title"]))
    story.append(Paragraph(drawing.title or "", styles["Heading3"]))
    story.append(Spacer(1, 10))

    meta_rows = [
        ["Drawing Number", drawing.drawing_number, "Revision", drawing.revision],
        ["Units", drawing.units or "", "Scale", drawing.scale or ""],
        ["BOM Version", str(bom.version), "Status", bom.status],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "", ""],
    ]
    meta_table = Table(meta_rows, colWidths=[1.3 * inch, 2.2 * inch, 1.1 * inch, 1.9 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    df = bom_to_dataframe(bom)
    header = ["Part Number", "Description", "Qty", "Total Qty", "Material", "Make/Buy", "Unit Cost", "Line Cost"]
    rows = [header]
    total_cost = 0.0
    has_any_cost = False
    for _, r in df.iterrows():
        qty = r["Quantity"] or 0
        unit_cost = r["Unit Cost"]
        line_cost = unit_cost * qty if unit_cost is not None and pd.notna(unit_cost) else None
        if line_cost is not None:
            total_cost += line_cost
            has_any_cost = True
        rows.append([
            r["Part Number"] or "",
            r["Description"] or "",
            str(qty),
            str(r["Total Quantity"]) if pd.notna(r["Total Quantity"]) else "",
            r["Material"] or "",
            r["Make/Buy"] or "",
            f"${unit_cost:.2f}" if unit_cost is not None and pd.notna(unit_cost) else "—",
            f"${line_cost:.2f}" if line_cost is not None else "—",
        ])

    if not df.empty:
        table = Table(rows, colWidths=[0.95 * inch, 1.75 * inch, 0.5 * inch, 0.65 * inch,
                                        1.1 * inch, 0.6 * inch, 0.7 * inch, 0.75 * inch],
                       repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ALIGN", (2, 0), (3, -1), "RIGHT"),
            ("ALIGN", (6, 0), (7, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No line items.", styles["Normal"]))

    story.append(Spacer(1, 14))
    buy_rows = df[df["Make/Buy"] == "Buy"] if not df.empty else df
    buy_missing_price = int(buy_rows["Unit Cost"].isna().sum()) if not buy_rows.empty else 0
    if has_any_cost:
        cost_label = f"Estimated Total Purchase Cost: ${total_cost:.2f}"
        if buy_missing_price:
            cost_label += f" (partial — {buy_missing_price} Buy item(s) have no catalog price)"
    else:
        cost_label = "Estimated Total Purchase Cost: — (no priced items)"
    story.append(Paragraph(cost_label, styles["Heading4"]))

    doc.build(story)
    return buf.getvalue()
