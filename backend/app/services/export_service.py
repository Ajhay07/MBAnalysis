from __future__ import annotations

import io

import pandas as pd

from app.models.models import Bom, Drawing


def bom_export_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_BOM.{ext}"


def purchase_list_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_PurchaseList.{ext}"


def material_summary_filename(drawing: Drawing, ext: str) -> str:
    safe_num = (drawing.drawing_number or "DRAWING").replace(" ", "_")
    return f"{safe_num}_Rev{drawing.revision}_MaterialSummary.{ext}"


def bom_to_dataframe(bom: Bom) -> pd.DataFrame:
    rows = [{
        "Part Number": li.part_number,
        "Description": li.description,
        "Category": li.category,
        "Quantity": li.quantity,
        "Material": li.material,
        "Make/Buy": li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy,
        "Unit Cost": li.unit_cost,
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
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return buf.getvalue()
