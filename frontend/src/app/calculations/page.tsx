"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type CalcKey = "gear-ratio" | "gear-module" | "cylindrical-volume" | "rectangular-volume" | "mass" | "raw-stock-volume" | "convert-length";

const FORMS: { key: CalcKey; label: string; fields: { name: string; label: string; type?: string }[] }[] = [
  { key: "gear-ratio", label: "Gear Ratio", fields: [{ name: "driver_teeth", label: "Driver Teeth" }, { name: "driven_teeth", label: "Driven Teeth" }] },
  { key: "gear-module", label: "Gear Module", fields: [{ name: "pitch_diameter", label: "Pitch Diameter (mm)" }, { name: "number_of_teeth", label: "Number of Teeth" }] },
  { key: "cylindrical-volume", label: "Cylindrical Volume", fields: [{ name: "diameter", label: "Diameter (mm)" }, { name: "height", label: "Height (mm)" }] },
  { key: "rectangular-volume", label: "Rectangular Volume", fields: [{ name: "length", label: "Length (mm)" }, { name: "width", label: "Width (mm)" }, { name: "height", label: "Height (mm)" }] },
  { key: "mass", label: "Mass from Volume", fields: [{ name: "volume_mm3", label: "Volume (mm^3)" }, { name: "density_g_cm3", label: "Density (g/cm^3)" }] },
  { key: "raw-stock-volume", label: "Raw Stock Volume", fields: [{ name: "bounding_length", label: "Bounding Length" }, { name: "bounding_width", label: "Bounding Width" }, { name: "bounding_height", label: "Bounding Height" }, { name: "machining_allowance_mm", label: "Machining Allowance (mm)" }] },
  { key: "convert-length", label: "Unit Conversion", fields: [{ name: "value", label: "Value" }, { name: "from_unit", label: "From Unit (mm/cm/m/in/ft)", type: "text" }, { name: "to_unit", label: "To Unit", type: "text" }] },
];

export default function CalculationsPage() {
  const [active, setActive] = useState<CalcKey>("gear-ratio");
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const form = FORMS.find((f) => f.key === active)!;

  async function run() {
    setLoading(true);
    try {
      const payload: Record<string, unknown> = {};
      for (const f of form.fields) {
        const raw = values[f.name] ?? "";
        payload[f.name] = f.type === "text" ? raw : parseFloat(raw) || 0;
      }
      const res = await api.calc(active, payload);
      setResult(res);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Engineering Calculation Engine</h1>
      <div className="grid grid-cols-4 gap-6">
        <div className="col-span-1">
          <ul className="space-y-1">
            {FORMS.map((f) => (
              <li key={f.key}>
                <button
                  className={`w-full text-left text-sm px-3 py-2 rounded-industrial ${
                    active === f.key ? "bg-accent-light text-accent-dark font-medium" : "hover:bg-surface text-steel"
                  }`}
                  onClick={() => {
                    setActive(f.key);
                    setResult(null);
                    setValues({});
                  }}
                >
                  {f.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="col-span-3 card p-5">
          <h2 className="text-sm font-semibold mb-4">{form.label}</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            {form.fields.map((f) => (
              <div key={f.name}>
                <label className="block text-xs text-steel mb-1">{f.label}</label>
                <input
                  type={f.type === "text" ? "text" : "number"}
                  className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
                  value={values[f.name] || ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <button className="btn-primary" disabled={loading} onClick={run}>
            {loading ? "Calculating..." : "Calculate"}
          </button>

          {result && (
            <div className="mt-5 border-t border-border pt-4 text-sm space-y-2">
              <div>
                <span className="text-steel">Result: </span>
                <span className="font-semibold text-accent-dark">
                  {typeof result.result === "object" ? JSON.stringify(result.result) : result.result}
                </span>
              </div>
              <div>
                <span className="text-steel">Formula: </span>
                <span className="font-mono text-xs">{result.formula}</span>
              </div>
              {result.assumptions?.length > 0 && (
                <div>
                  <span className="text-steel">Assumptions: </span>
                  <ul className="list-disc list-inside text-xs text-steel-light">
                    {result.assumptions.map((a: string, i: number) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.warnings?.length > 0 && (
                <div className="text-amber-700 text-xs">
                  {result.warnings.map((w: string, i: number) => (
                    <div key={i}>⚠ {w}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
