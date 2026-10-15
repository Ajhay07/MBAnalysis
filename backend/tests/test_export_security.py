import pandas as pd

from app.services.export_service import neutralize_formula, sanitize_dataframe, dataframe_to_csv_bytes


def test_neutralize_formula_prefixes_dangerous_leading_chars():
    assert neutralize_formula("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"
    assert neutralize_formula("+1+1") == "'+1+1"
    assert neutralize_formula("-1+1") == "'-1+1"
    assert neutralize_formula("@SUM(A1)") == "'@SUM(A1)"


def test_neutralize_formula_leaves_normal_values_untouched():
    assert neutralize_formula("Bracket-Steel") == "Bracket-Steel"
    assert neutralize_formula(42) == 42
    assert neutralize_formula(None) is None


def test_sanitize_dataframe_neutralizes_formula_cells():
    df = pd.DataFrame({"Description": ["=HYPERLINK(\"http://evil\")", "Normal Part"]})
    out = sanitize_dataframe(df)
    assert out["Description"].iloc[0].startswith("'=")
    assert out["Description"].iloc[1] == "Normal Part"


def test_csv_export_neutralizes_formula_injection():
    df = pd.DataFrame({"Part Number": ["=1+1", "ABC-123"]})
    csv_bytes = dataframe_to_csv_bytes(df)
    text = csv_bytes.decode("utf-8")
    assert "'=1+1" in text
    assert "ABC-123" in text
