"use client";

import { useEffect, useState } from "react";
import { Cog, Settings2, Cylinder, Box, Weight, Package, Ruler, type LucideIcon } from "lucide-react";
import { api } from "@/lib/api";

type CalcKey = "gear-ratio" | "gear-module" | "cylindrical-volume" | "rectangular-volume" | "mass" | "raw-stock-volume" | "convert-length";
type Field = { name: string; label: string; type?: string; default?: string };
type CalcDef = { key: CalcKey; label: string; icon: LucideIcon; fields: Field[] };

const FORMS: CalcDef[] = [
  { key: "gear-ratio", label: "Gear Ratio", icon: Cog, fields: [
    { name: "driver_teeth", label: "Driver Teeth", default: "20" },
    { name: "driven_teeth", label: "Driven Teeth", default: "80" },
  ] },
  { key: "gear-module", label: "Gear Module", icon: Settings2, fields: [
    { name: "pitch_diameter", label: "Pitch Diameter (mm)", default: "96" },
    { name: "number_of_teeth", label: "Number of Teeth", default: "48" },
  ] },
  { key: "cylindrical-volume", label: "Cylindrical Volume", icon: Cylinder, fields: [
    { name: "diameter", label: "Diameter (mm)", default: "100" },
    { name: "height", label: "Height (mm)", default: "200" },
  ] },
  { key: "rectangular-volume", label: "Rectangular Volume", icon: Box, fields: [
    { name: "length", label: "Length (mm)", default: "300" },
    { name: "width", label: "Width (mm)", default: "200" },
    { name: "height", label: "Height (mm)", default: "50" },
  ] },
  { key: "mass", label: "Mass from Volume", icon: Weight, fields: [
    { name: "volume_mm3", label: "Volume (mm³)", default: "1000000" },
    { name: "density_g_cm3", label: "Density (g/cm³)", default: "7.85" },
  ] },
  { key: "raw-stock-volume", label: "Raw Stock Volume", icon: Package, fields: [
    { name: "bounding_length", label: "Length (mm)", default: "300" },
    { name: "bounding_width", label: "Width (mm)", default: "200" },
    { name: "bounding_height", label: "Height (mm)", default: "50" },
    { name: "machining_allowance_mm", label: "Allowance (mm)", default: "2" },
  ] },
  { key: "convert-length", label: "Unit Conversion", icon: Ruler, fields: [
    { name: "value", label: "Value", default: "1" },
    { name: "from_unit", label: "From (mm/cm/m/in/ft)", type: "text", default: "in" },
    { name: "to_unit", label: "To", type: "text", default: "mm" },
  ] },
];

const defaults = (f: CalcDef) => Object.fromEntries(f.fields.map((x) => [x.name, x.default ?? ""]));

function payloadFor(f: CalcDef, values: Record<string, string>) {
  const payload: Record<string, unknown> = {};
  for (const field of f.fields) {
    const raw = values[field.name] ?? "";
    payload[field.name] = field.type === "text" ? raw : parseFloat(raw) || 0;
  }
  return payload;
}

function fmt(n: number, digits = 3): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: digits });
}

/** Headline + one-line explanation for a calculation result, per calculator type. */
function presentResult(key: CalcKey, result: any, values: Record<string, string>): { main: string; sub: string } {
  if (typeof result !== "number") return { main: JSON.stringify(result), sub: "" };
  switch (key) {
    case "gear-ratio":
      if (result === 0) return { main: "—", sub: "Enter positive tooth counts" };
      return {
        main: `${result.toFixed(2)} : 1`,
        sub: result >= 1 ? `Output rotates ${result.toFixed(2)} times slower` : `Output rotates ${(1 / result).toFixed(2)} times faster`,
      };
    case "gear-module":
      return { main: `${fmt(result)} mm`, sub: "Module = pitch diameter / teeth" };
    case "cylindrical-volume":
    case "rectangular-volume":
    case "raw-stock-volume":
      return { main: `${fmt(Math.round(result), 0)} mm³`, sub: `≈ ${fmt(result / 1e6)} L` };
    case "mass":
      return { main: `${fmt(result)} g`, sub: `≈ ${fmt(result / 1000)} kg` };
    case "convert-length":
      return { main: `${fmt(result, 4)} ${values.to_unit || ""}`.trim(), sub: `${values.value || 0} ${values.from_unit || ""} converted` };
  }
}

function useCalc(def: CalcDef) {
  const [values, setValues] = useState<Record<string, string>>(() => defaults(def));
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  async function run(v = values) {
    setLoading(true);
    try {
      setResult(await api.calc(def.key, payloadFor(def, v)));
    } finally {
      setLoading(false);
    }
  }
  return { values, setValues, result, setResult, loading, run };
}

const byKey = (k: CalcKey) => FORMS.find((f) => f.key === k)!;

export default function CalculationsPage() {
  const [active, setActive] = useState<CalcKey>("gear-ratio");
  const form = byKey(active);
  const main = useCalc(form);
  const cyl = useCalc(byKey("cylindrical-volume"));
  const rect = useCalc(byKey("rectangular-volume"));

  useEffect(() => {
    main.run();
    cyl.run();
    rect.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function select(key: CalcKey) {
    const next = byKey(key);
    const v = defaults(next);
    setActive(key);
    main.setValues(v);
    main.setResult(null);
    api.calc(key, payloadFor(next, v)).then(main.setResult);
  }

  const shown = main.result ? presentResult(active, main.result.result, main.values) : null;

  return (
    <div className="px-8 pb-8 pt-2 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="page-title">Engineering Calculation Engine</h1>
        <p className="page-subtitle">Quickly compute common engineering parameters.</p>
      </div>

      <div className="grid grid-cols-[230px_1fr] gap-5 mb-6">
        <div className="card p-2 h-fit">
          {FORMS.map((f) => {
            const Icon = f.icon;
            const on = active === f.key;
            return (
              <button
                key={f.key}
                onClick={() => select(f.key)}
                className={`w-full flex items-center gap-3 text-left text-sm px-3 py-2.5 rounded-industrial transition-colors ${
                  on ? "bg-brand-light text-brand font-semibold" : "text-steel hover:bg-surface hover:text-graphite"
                }`}
              >
                <Icon size={17} />
                {f.label}
              </button>
            );
          })}
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-semibold mb-5">{form.label}</h2>
          <div className="grid grid-cols-[1fr_260px] gap-6">
            <div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                {form.fields.map((f) => (
                  <div key={f.name}>
                    <label className="block text-xs font-medium text-steel mb-1">{f.label}</label>
                    <input
                      type={f.type === "text" ? "text" : "number"}
                      className="input"
                      value={main.values[f.name] ?? ""}
                      onChange={(e) => main.setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>
              <button className="btn-accent !px-8" disabled={main.loading} onClick={() => main.run()}>
                {main.loading ? "Calculating..." : "Calculate"}
              </button>
            </div>
            <div className="rounded-industrial bg-surface border border-border p-5 flex flex-col justify-center">
              <div className="text-xs text-steel mb-1">{form.label}</div>
              <div className="text-4xl font-bold text-graphite break-words">{shown?.main ?? "—"}</div>
              <div className="text-xs text-steel mt-2">{shown?.sub}</div>
            </div>
          </div>

          {main.result && (main.result.formula || main.result.warnings?.length > 0) && (
            <div className="mt-5 pt-4 border-t border-border text-xs space-y-1.5">
              <div>
                <span className="text-steel">Formula: </span>
                <span className="font-mono">{main.result.formula}</span>
              </div>
              {main.result.assumptions?.length > 0 && (
                <div className="text-steel-light">Assumptions: {main.result.assumptions.join(" ")}</div>
              )}
              {main.result.warnings?.map((w: string, i: number) => (
                <div key={i} className="text-amber-700">⚠ {w}</div>
              ))}
            </div>
          )}
        </div>
      </div>

      <h2 className="text-base font-semibold mb-3">Other Calculations</h2>
      <div className="grid grid-cols-2 gap-5">
        <QuickCalc def={byKey("cylindrical-volume")} calc={cyl} />
        <QuickCalc def={byKey("rectangular-volume")} calc={rect} />
      </div>
    </div>
  );
}

function QuickCalc({ def, calc }: { def: CalcDef; calc: ReturnType<typeof useCalc> }) {
  const Icon = def.icon;
  const shown = calc.result ? presentResult(def.key, calc.result.result, calc.values) : null;
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4 text-brand">
        <Icon size={20} />
        <h3 className="text-sm font-semibold text-graphite">{def.label}</h3>
      </div>
      <div className={`grid gap-3 mb-4 ${def.fields.length > 2 ? "grid-cols-3" : "grid-cols-2"}`}>
        {def.fields.map((f) => (
          <div key={f.name}>
            <label className="block text-[11px] text-steel mb-1">{f.label}</label>
            <input
              type="number"
              className="input"
              value={calc.values[f.name] ?? ""}
              onChange={(e) => calc.setValues((v) => ({ ...v, [f.name]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      <div className="text-2xl font-bold text-graphite">{shown?.main ?? "—"}</div>
      <div className="text-xs text-steel mb-4">{shown?.sub}</div>
      <button className="btn-secondary !px-8" disabled={calc.loading} onClick={() => calc.run()}>
        {calc.loading ? "Calculating..." : "Calculate"}
      </button>
    </div>
  );
}
