from __future__ import annotations

import io

import pandas as pd

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
