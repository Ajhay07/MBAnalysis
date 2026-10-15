from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import calculations as calc

router = APIRouter(prefix="/api/calculations", tags=["calculations"])


class GearRatioIn(BaseModel):
    driver_teeth: float
    driven_teeth: float


class GearModuleIn(BaseModel):
    pitch_diameter: float
    number_of_teeth: float


class CylinderVolumeIn(BaseModel):
    diameter: float
    height: float


class RectVolumeIn(BaseModel):
    length: float
    width: float
    height: float


class MassIn(BaseModel):
    volume_mm3: float
    density_g_cm3: float


class RawStockIn(BaseModel):
    bounding_length: float
    bounding_width: float
    bounding_height: float
    machining_allowance_mm: float = 0.0


class ConvertIn(BaseModel):
    value: float
    from_unit: str
    to_unit: str


@router.post("/gear-ratio")
def gear_ratio(payload: GearRatioIn):
    return calc.gear_ratio(payload.driver_teeth, payload.driven_teeth)


@router.post("/gear-module")
def gear_module(payload: GearModuleIn):
    return calc.gear_module(payload.pitch_diameter, payload.number_of_teeth)


@router.post("/cylindrical-volume")
def cylindrical_volume(payload: CylinderVolumeIn):
    return calc.cylindrical_volume(payload.diameter, payload.height)


@router.post("/rectangular-volume")
def rectangular_volume(payload: RectVolumeIn):
    return calc.rectangular_volume(payload.length, payload.width, payload.height)


@router.post("/mass")
def mass(payload: MassIn):
    return calc.mass_from_volume(payload.volume_mm3, payload.density_g_cm3)


@router.post("/raw-stock-volume")
def raw_stock_volume(payload: RawStockIn):
    return calc.raw_stock_volume(payload.bounding_length, payload.bounding_width,
                                  payload.bounding_height, payload.machining_allowance_mm)


@router.post("/convert-length")
def convert_length(payload: ConvertIn):
    return calc.convert_length(payload.value, payload.from_unit, payload.to_unit)
