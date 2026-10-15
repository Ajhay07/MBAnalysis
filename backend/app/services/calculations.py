"""Deterministic engineering calculation engine.

Every function returns a plain dict with: inputs, formula, result, assumptions, warnings.
No randomness, no external calls - pure math, unit-tested.
"""
from __future__ import annotations

import math
from typing import Optional


def _result(inputs: dict, formula: str, result: float | dict, assumptions: list[str] | None = None,
            warnings: list[str] | None = None) -> dict:
    return {
        "inputs": inputs,
        "formula": formula,
        "result": result,
        "assumptions": assumptions or [],
        "warnings": warnings or [],
    }


def gear_ratio(driver_teeth: float, driven_teeth: float) -> dict:
    inputs = {"driver_teeth": driver_teeth, "driven_teeth": driven_teeth}
    warnings = []
    if driver_teeth <= 0 or driven_teeth <= 0:
        warnings.append("Tooth counts must be positive; result may be invalid.")
        ratio = 0.0
    else:
        ratio = driven_teeth / driver_teeth
    return _result(inputs, "ratio = driven_teeth / driver_teeth", ratio,
                    ["Simple two-gear mesh, no idler compounding."], warnings)


def gear_module(pitch_diameter: float, number_of_teeth: float) -> dict:
    inputs = {"pitch_diameter": pitch_diameter, "number_of_teeth": number_of_teeth}
    warnings = []
    if number_of_teeth <= 0:
        warnings.append("Number of teeth must be positive.")
        module = 0.0
    else:
        module = pitch_diameter / number_of_teeth
    return _result(inputs, "module = pitch_diameter / number_of_teeth", module,
                    ["Standard involute spur gear, module per ISO convention (mm/tooth)."], warnings)


def cylindrical_volume(diameter: float, height: float) -> dict:
    inputs = {"diameter": diameter, "height": height}
    warnings = []
    if diameter < 0 or height < 0:
        warnings.append("Diameter and height must be non-negative.")
    radius = diameter / 2
    volume = math.pi * radius ** 2 * height
    return _result(inputs, "volume = pi * (diameter/2)^2 * height", volume,
                    ["Solid right circular cylinder, no bore subtracted."], warnings)


def rectangular_volume(length: float, width: float, height: float) -> dict:
    inputs = {"length": length, "width": width, "height": height}
    warnings = []
    if length < 0 or width < 0 or height < 0:
        warnings.append("Dimensions must be non-negative.")
    volume = length * width * height
    return _result(inputs, "volume = length * width * height", volume,
                    ["Solid rectangular prism."], warnings)


def mass_from_volume(volume_mm3: float, density_g_cm3: float) -> dict:
    inputs = {"volume_mm3": volume_mm3, "density_g_cm3": density_g_cm3}
    warnings = []
    if volume_mm3 < 0 or density_g_cm3 < 0:
        warnings.append("Volume and density must be non-negative.")
    volume_cm3 = volume_mm3 / 1000.0
    mass_g = volume_cm3 * density_g_cm3
    return _result(inputs, "mass_g = (volume_mm3 / 1000) * density_g_cm3", mass_g,
                    ["Volume supplied in mm^3, density in g/cm^3, result in grams."], warnings)


def raw_stock_volume(bounding_length: float, bounding_width: float, bounding_height: float,
                      machining_allowance_mm: float = 0.0) -> dict:
    inputs = {
        "bounding_length": bounding_length,
        "bounding_width": bounding_width,
        "bounding_height": bounding_height,
        "machining_allowance_mm": machining_allowance_mm,
    }
    warnings = []
    if min(bounding_length, bounding_width, bounding_height) < 0:
        warnings.append("Bounding dimensions must be non-negative.")
    l = bounding_length + 2 * machining_allowance_mm
    w = bounding_width + 2 * machining_allowance_mm
    h = bounding_height + 2 * machining_allowance_mm
    volume = l * w * h
    return _result(
        inputs,
        "volume = (L + 2*allowance) * (W + 2*allowance) * (H + 2*allowance)",
        volume,
        ["Rectangular raw stock; allowance applied symmetrically on each face."],
        warnings,
    )


_LENGTH_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}


def convert_length(value: float, from_unit: str, to_unit: str) -> dict:
    inputs = {"value": value, "from_unit": from_unit, "to_unit": to_unit}
    warnings = []
    fu, tu = from_unit.lower(), to_unit.lower()
    if fu not in _LENGTH_TO_MM or tu not in _LENGTH_TO_MM:
        warnings.append(f"Unsupported unit. Supported units: {list(_LENGTH_TO_MM)}")
        return _result(inputs, "n/a", 0.0, [], warnings)
    mm = value * _LENGTH_TO_MM[fu]
    converted = mm / _LENGTH_TO_MM[tu]
    return _result(inputs, "value_mm = value * factor(from); result = value_mm / factor(to)",
                    converted, [f"Conversion factors relative to millimetres: {_LENGTH_TO_MM}"], warnings)
