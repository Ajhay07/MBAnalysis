import math

from app.services import calculations as calc


def test_gear_ratio_basic():
    r = calc.gear_ratio(20, 60)
    assert r["result"] == 3.0
    assert r["warnings"] == []


def test_gear_ratio_zero_teeth_warns():
    r = calc.gear_ratio(0, 60)
    assert r["result"] == 0.0
    assert r["warnings"]


def test_gear_module():
    r = calc.gear_module(96, 48)
    assert r["result"] == 2.0


def test_cylindrical_volume_exact():
    r = calc.cylindrical_volume(diameter=10, height=20)
    expected = math.pi * 5 ** 2 * 20
    assert math.isclose(r["result"], expected, rel_tol=1e-9)


def test_rectangular_volume_exact():
    r = calc.rectangular_volume(length=10, width=5, height=2)
    assert r["result"] == 100.0


def test_mass_from_volume():
    # 1000 mm^3 = 1 cm^3, at density 7.85 g/cm3 (steel) -> 7.85 g
    r = calc.mass_from_volume(volume_mm3=1000, density_g_cm3=7.85)
    assert math.isclose(r["result"], 7.85, rel_tol=1e-9)


def test_raw_stock_volume_with_allowance():
    r = calc.raw_stock_volume(bounding_length=100, bounding_width=50, bounding_height=10,
                               machining_allowance_mm=1.0)
    expected = (100 + 2) * (50 + 2) * (10 + 2)
    assert r["result"] == expected


def test_convert_length_mm_to_in():
    r = calc.convert_length(25.4, "mm", "in")
    assert math.isclose(r["result"], 1.0, rel_tol=1e-9)


def test_convert_length_unsupported_unit_warns():
    r = calc.convert_length(1, "mm", "furlong")
    assert r["warnings"]
