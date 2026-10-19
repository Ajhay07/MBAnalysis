"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ShoppingCart, Settings, Eye, Coins, Pencil, FileText } from "lucide-react";
import { api, Drawing } from "@/lib/api";
import { CatalogMatchBadge, StockAvailabilityBadge } from "@/components/Badges";
import PageLayout, { AsideSection, AsideItem } from "@/components/PageLayout";

function specText(dimensions: any, tolerances: any): string {
  const parts: string[] = [];
  if (dimensions && typeof dimensions === "object") {
    for (const [k, v] of Object.entries(dimensions)) {
      if (v !== null && v !== undefined && v !== "") parts.push(`${k.replace(/_/g, " ")}: ${v}`);
    }
  }
  if (tolerances && typeof tolerances === "object") {
    for (const [k, v] of Object.entries(tolerances)) {
      if (v !== null && v !== undefined && v !== "") parts.push(`${k.replace(/_/g, " ")} tol: ${v}`);
    }
  }
  return parts.join(", ");
}

type Requirements = Awaited<ReturnType<typeof api.purchaseRequirements>>;
type TabKey = "buy" | "make" | "review";

function KpiCard({ icon, label, value, note }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; note?: React.ReactNode;
}) {
  return (
    <div className="card px-5 py-4 flex items-center gap-4">
      <div className="text-brand shrink-0">{icon}</div>
      <div className="min-w-0">
        <div className="text-sm text-steel">{label}</div>
        <div className="text-[28px] font-bold text-graphite leading-tight">{value}</div>
        {note}
      </div>
    </div>
  );
}

export default function ProcurementPage() {
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [requirements, setRequirements] = useState<Requirements | null>(null);
  const [tab, setTab] = useState<TabKey>("buy");
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [catalogUsage, setCatalogUsage] = useState<any[]>([]);
  const [newItem, setNewItem] = useState({ part_number: "", description: "", unit_price: "", stock_quantity: "" });
  const [savingItem, setSavingItem] = useState(false);

  const refreshCatalog = () => {
    api.catalogUsage().then(setCatalogUsage);
  };

  useEffect(() => {
    api.listDrawings().then((ds) => {
      setDrawings(ds);
      const withBom = ds.find((d) => d.status === "Reviewed" || d.status === "BOMGenerated");
      if (ds.length) setSelected((withBom || ds[0]).id);
    });
    api.listSuppliers().then(setSuppliers);
    refreshCatalog();
  }, []);

  useEffect(() => {
    if (selected) api.purchaseRequirements(selected).then(setRequirements);
  }, [selected]);

  const addCatalogItem = async () => {
    if (!newItem.part_number.trim()) return;
    setSavingItem(true);
    try {
      await api.createCatalogItem({
        part_number: newItem.part_number.trim(),
        description: newItem.description.trim(),
        unit_price: newItem.unit_price ? parseFloat(newItem.unit_price) : null,
        stock_quantity: newItem.stock_quantity ? parseFloat(newItem.stock_quantity) : null,
      });
      setNewItem({ part_number: "", description: "", unit_price: "", stock_quantity: "" });
      refreshCatalog();
      if (selected) api.purchaseRequirements(selected).then(setRequirements);
    } finally {
      setSavingItem(false);
    }
  };

  const summary = requirements?.summary;
  const buy = requirements?.buy || [];
  const make = requirements?.make || [];
  const review = requirements?.review || [];
  const drawingHref = selected ? `/drawings/${selected}` : "/drawings";

  const materialGrade = (item: any) => [item.material, item.grade].filter(Boolean).join(" / ") || "—";

  const makeTable = (
    <table className="w-full">
      <thead className="border-b border-border bg-surface/60">
        <tr>
          <th className="th">Part Number</th>
          <th className="th">Description</th>
          <th className="th">Material / Grade</th>
          <th className="th">Spec</th>
          <th className="th text-right">Qty</th>
          <th className="th text-right w-24">Actions</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {make.map((item) => (
          <tr key={item.line_item_id}>
            <td className="td font-medium whitespace-nowrap">{item.part_number}</td>
            <td className="td">{item.description}</td>
            <td className="td text-steel">{materialGrade(item)}</td>
            <td className="td text-steel text-xs">{specText(item.dimensions, item.tolerances) || "—"}</td>
            <td className="td text-right">{item.quantity}</td>
            <td className="td">
              <div className="flex justify-end gap-1.5">
                <Link href={drawingHref} className="btn-icon" title="View drawing">
                  <FileText size={14} />
                </Link>
                <Link href={drawingHref} className="btn-icon" title="Edit in BOM">
                  <Pencil size={14} />
                </Link>
              </div>
            </td>
          </tr>
        ))}
        {make.length === 0 && (
          <tr><td colSpan={6} className="td text-steel">None</td></tr>
        )}
      </tbody>
    </table>
  );

  const selectedDrawing = drawings.find((d) => d.id === selected);

  const aside = (
    <>
      <AsideSection title="Drawings">
        <div className="space-y-1">
          {drawings.map((d) => (
            <AsideItem
              key={d.id}
              icon={FileText}
              label={d.drawing_number}
              count={d.revision ? `Rev ${d.revision}` : undefined}
              active={d.id === selected}
              onClick={() => setSelected(d.id)}
            />
          ))}
        </div>
      </AsideSection>
      <div className="mx-3 border-t border-border" />
      <AsideSection title="Requirements">
        <div className="space-y-1">
          <AsideItem icon={ShoppingCart} label="Items to Buy" count={buy.length} active={tab === "buy"} onClick={() => setTab("buy")} />
          <AsideItem icon={Settings} label="Make In-House" count={make.length} active={tab === "make"} onClick={() => setTab("make")} />
          <AsideItem icon={Eye} label="Needs Review" count={review.length} active={tab === "review"} onClick={() => setTab("review")} />
        </div>
      </AsideSection>
    </>
  );

  return (
    <PageLayout
      aside={aside}
      title="Procurement / Purchase Requirements"
      subtitle={selectedDrawing ? `${selectedDrawing.drawing_number} · ${selectedDrawing.title}` : "Manage items to buy, make in-house, or review."}
    >

      {summary && (
        <div className="grid grid-cols-4 gap-4 mb-5">
          <KpiCard icon={<ShoppingCart size={30} strokeWidth={1.75} />} label="Buy items" value={summary.buy_item_count} />
          <KpiCard icon={<Settings size={30} strokeWidth={1.75} />} label="Make items" value={summary.make_item_count} />
          <KpiCard icon={<Eye size={30} strokeWidth={1.75} />} label="Review items" value={summary.review_item_count} />
          <KpiCard
            icon={<Coins size={30} strokeWidth={1.75} />}
            label="Estimated purchase cost"
            value={summary.estimated_total_cost != null ? `$${summary.estimated_total_cost.toFixed(2)}` : "—"}
            note={summary.is_partial_estimate && (
              <div className="text-[11px] text-amber-700">Partial — {summary.buy_items_missing_price} unpriced</div>
            )}
          />
        </div>
      )}

      <div className="card mb-5">
        <div className="flex border-b border-border px-2">
          <button className={`tab ${tab === "buy" ? "tab-active" : ""}`} onClick={() => setTab("buy")}>
            Items to Buy ({buy.length})
          </button>
          <button className={`tab ${tab === "make" ? "tab-active" : ""}`} onClick={() => setTab("make")}>
            Make In-House ({make.length})
          </button>
          <button className={`tab ${tab === "review" ? "tab-active" : ""}`} onClick={() => setTab("review")}>
            Review ({review.length})
          </button>
        </div>

        {tab === "buy" && (
          <table className="w-full">
            <thead className="border-b border-border bg-surface/60">
              <tr>
                <th className="th">Part Number</th>
                <th className="th">Description</th>
                <th className="th">Material / Grade</th>
                <th className="th text-right">Qty</th>
                <th className="th text-right">Unit Price</th>
                <th className="th text-right">Est. Cost</th>
                <th className="th">Stock</th>
                <th className="th text-right w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {buy.map((item) => (
                <tr key={item.line_item_id}>
                  <td className="td">
                    <div className="font-medium whitespace-nowrap">{item.part_number}</div>
                    {item.catalog_component_id && (
                      <div className="mt-1">
                        <CatalogMatchBadge catalogPartNumber={item.part_number} />
                      </div>
                    )}
                  </td>
                  <td className="td">{item.description}</td>
                  <td className="td text-steel">{materialGrade(item)}</td>
                  <td className="td text-right">{item.quantity}</td>
                  <td className="td text-right">{item.unit_price != null ? `$${item.unit_price}` : "—"}</td>
                  <td className="td text-right">{item.estimated_cost != null ? `$${item.estimated_cost.toFixed(2)}` : "—"}</td>
                  <td className="td"><StockAvailabilityBadge status={item.availability} /></td>
                  <td className="td">
                    <div className="flex justify-end gap-1.5">
                      <Link href={drawingHref} className="btn-icon" title="Raise purchase requisition (BOM → Inventory Availability)">
                        <ShoppingCart size={14} />
                      </Link>
                      <Link href={drawingHref} className="btn-icon" title="Edit in BOM">
                        <Pencil size={14} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
              {buy.length === 0 && (
                <tr><td colSpan={8} className="td text-steel">None</td></tr>
              )}
            </tbody>
          </table>
        )}

        {tab === "make" && makeTable}

        {tab === "review" && (
          <table className="w-full">
            <thead className="border-b border-border bg-surface/60">
              <tr>
                <th className="th">Part Number</th>
                <th className="th">Description</th>
                <th className="th text-right">Qty</th>
                <th className="th text-right w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {review.map((item) => (
                <tr key={item.line_item_id}>
                  <td className="td font-medium">{item.part_number}</td>
                  <td className="td">{item.description}</td>
                  <td className="td text-right">{item.quantity}</td>
                  <td className="td">
                    <div className="flex justify-end">
                      <Link href={drawingHref} className="btn-icon" title="Decide Make/Buy in BOM">
                        <Pencil size={14} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
              {review.length === 0 && (
                <tr><td colSpan={4} className="td text-steel">Nothing needs a Make/Buy decision.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {tab !== "make" && (
        <div className="card mb-5">
          <h2 className="section-title px-5 pt-5 pb-3">Items to Manufacture In-House ({make.length})</h2>
          {makeTable}
        </div>
      )}

      <div className="card mb-5">
        <div className="px-5 pt-5 pb-3">
          <h2 className="section-title">Source Catalog ({catalogUsage.length})</h2>
          <p className="text-xs text-steel mt-0.5">
            Reference list of known parts — price, stock, and how many BOM lines the OCR/vision pipeline matched to each.
          </p>
        </div>
        <table className="w-full">
          <thead className="border-y border-border bg-surface/60">
            <tr>
              <th className="th">Component ID</th>
              <th className="th">Part Number</th>
              <th className="th">Description</th>
              <th className="th text-right">Unit Price</th>
              <th className="th text-right">Stock</th>
              <th className="th text-right">Matched Lines</th>
              <th className="th text-right">Qty Needed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {catalogUsage.map((u) => (
              <tr key={u.catalog_component_id}>
                <td className="td font-mono text-xs text-steel">{u.catalog_component_id.slice(0, 12)}…</td>
                <td className="td font-medium">{u.part_number}</td>
                <td className="td">{u.description}</td>
                <td className="td text-right">{u.unit_price != null ? `$${u.unit_price}` : "—"}</td>
                <td className="td text-right">{u.stock_quantity != null ? u.stock_quantity : "—"}</td>
                <td className="td text-right">{u.matched_line_item_count}</td>
                <td className="td text-right">{u.total_quantity}</td>
              </tr>
            ))}
            {catalogUsage.length === 0 && (
              <tr><td colSpan={7} className="td text-steel">No catalog items yet. Add one below.</td></tr>
            )}
          </tbody>
        </table>

        <div className="border-t border-border p-5">
          <h3 className="text-sm font-semibold mb-3">Add Catalog Item</h3>
          <div className="flex gap-3">
            <input className="input" placeholder="Part number" value={newItem.part_number}
              onChange={(e) => setNewItem({ ...newItem, part_number: e.target.value })} />
            <input className="input" placeholder="Description" value={newItem.description}
              onChange={(e) => setNewItem({ ...newItem, description: e.target.value })} />
            <input className="input !w-40" placeholder="Unit price" type="number" value={newItem.unit_price}
              onChange={(e) => setNewItem({ ...newItem, unit_price: e.target.value })} />
            <input className="input !w-40" placeholder="Stock quantity" type="number" value={newItem.stock_quantity}
              onChange={(e) => setNewItem({ ...newItem, stock_quantity: e.target.value })} />
            <button className="btn-primary whitespace-nowrap" onClick={addCatalogItem}
              disabled={savingItem || !newItem.part_number.trim()}>
              {savingItem ? "Adding…" : "Add Item"}
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="section-title px-5 pt-5 pb-3">Suppliers ({suppliers.length})</h2>
        <ul className="divide-y divide-border border-t border-border">
          {suppliers.map((s) => (
            <li key={s.id} className="px-5 py-3">
              <div className="text-sm font-medium">{s.name}</div>
              <div className="text-xs text-steel-light">{s.email || "no contact on file"}</div>
            </li>
          ))}
          {suppliers.length === 0 && <li className="px-5 py-3 text-steel text-sm">No suppliers yet.</li>}
        </ul>
      </div>
    </PageLayout>
  );
}
