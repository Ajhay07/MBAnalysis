"use client";

import { useEffect, useState } from "react";
import { api, Drawing } from "@/lib/api";
import { MakeBuyBadge } from "@/components/Badges";

export default function ProcurementPage() {
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [groups, setGroups] = useState<{ buy: any[]; make: any[]; review: any[] } | null>(null);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<any[]>([]);

  useEffect(() => {
    api.listDrawings().then((ds) => {
      setDrawings(ds);
      if (ds.length) setSelected(ds[0].id);
    });
    api.listSuppliers().then(setSuppliers);
    api.listCatalog().then(setCatalog);
  }, []);

  useEffect(() => {
    if (selected) api.procurementByDrawing(selected).then(setGroups);
  }, [selected]);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Procurement / Purchase List</h1>

      <div className="mb-4">
        <label className="text-xs text-steel mr-2">Drawing:</label>
        <select
          className="border border-border rounded-industrial text-sm px-3 py-2"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {drawings.map((d) => (
            <option key={d.id} value={d.id}>
              {d.drawing_number} - {d.title}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        {(["make", "buy", "review"] as const).map((key) => (
          <div key={key} className="card p-4">
            <h2 className="text-sm font-semibold mb-2 flex items-center justify-between capitalize">
              {key}
              <MakeBuyBadge value={key[0].toUpperCase() + key.slice(1)} />
            </h2>
            <div className="space-y-2">
              {(groups?.[key] || []).length === 0 && <div className="text-xs text-steel">None</div>}
              {(groups?.[key] || []).map((item: any) => (
                <div key={item.id} className="text-sm border-b border-border pb-1.5">
                  <div className="font-mono text-xs">{item.part_number}</div>
                  <div>{item.description}</div>
                  <div className="text-xs text-steel-light">
                    Qty {item.quantity} &middot; Unit cost: {item.unit_cost ?? "—"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-3">Suppliers ({suppliers.length})</h2>
          <ul className="text-sm divide-y divide-border">
            {suppliers.map((s) => (
              <li key={s.id} className="py-2">
                <div className="font-medium">{s.name}</div>
                <div className="text-xs text-steel-light">{s.email || "no contact on file"}</div>
              </li>
            ))}
            {suppliers.length === 0 && <li className="py-2 text-steel text-sm">No suppliers yet.</li>}
          </ul>
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-3">Component Catalog ({catalog.length})</h2>
          <ul className="text-sm divide-y divide-border">
            {catalog.map((c) => (
              <li key={c.id} className="py-2 flex justify-between">
                <span className="font-mono text-xs">{c.part_number}</span>
                <span className="text-xs text-steel-light">{c.unit_price != null ? `$${c.unit_price}` : "price n/a"}</span>
              </li>
            ))}
            {catalog.length === 0 && <li className="py-2 text-steel text-sm">No catalog items yet. Import via CSV.</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
