"use client";

import { useState } from "react";
import { RefreshCcw, ChevronDown, ChevronRight, ShoppingCart } from "lucide-react";
import { api, AvailabilityReport, Requisition } from "@/lib/api";
import { AvailabilityBadge } from "@/components/Badges";
import { useAuth } from "@/lib/auth-context";

export interface InventoryAvailabilityPanelProps {
  bomId: string;
}

export default function InventoryAvailabilityPanel({ bomId }: InventoryAvailabilityPanelProps) {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "engineer";

  const [productionQty, setProductionQty] = useState(1);
  const [report, setReport] = useState<AvailabilityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [requisitionMsg, setRequisitionMsg] = useState<string | null>(null);
  const [creatingFor, setCreatingFor] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.getAvailability(bomId, productionQty);
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load availability.");
    } finally {
      setLoading(false);
    }
  }

  async function createRequisition() {
    setCreatingFor(bomId);
    setRequisitionMsg(null);
    try {
      const req: Requisition = await api.draftRequisition(bomId, productionQty);
      setRequisitionMsg(
        `Draft requisition ${req.id.slice(0, 8)} ready with ${req.lines.length} line(s) - status ${req.status}.`
      );
    } catch (e) {
      setRequisitionMsg(e instanceof Error ? e.message : "Failed to create requisition.");
    } finally {
      setCreatingFor(null);
    }
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const hasShortages =
    report && report.lines.some((l) => (l.status === "PARTIALLY_AVAILABLE" || l.status === "OUT_OF_STOCK"));

  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-sm font-semibold">Inventory Availability</h2>
        <div className="flex items-center gap-2">
          <label className="text-xs text-steel">Production qty</label>
          <input
            type="number"
            min={0.01}
            step="1"
            className="w-20 text-xs border border-border rounded px-1.5 py-1"
            value={productionQty}
            onChange={(e) => setProductionQty(Math.max(0.01, parseFloat(e.target.value) || 1))}
          />
          <button className="btn-secondary !px-2 !py-1 text-xs" disabled={loading} onClick={refresh}>
            <RefreshCcw size={13} className={loading ? "animate-spin" : ""} /> Refresh Availability
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3 mb-3">
          {error}
        </div>
      )}

      {!report && !error && !loading && (
        <div className="text-sm text-steel text-center py-4">
          Set a production quantity and click &quot;Refresh Availability&quot; to compare this BOM
          against current inventory.
        </div>
      )}

      {report && (
        <>
          <div className="flex gap-2 mb-3 flex-wrap text-xs">
            {Object.entries(report.summary).map(([status, count]) => (
              <span key={status} className="flex items-center gap-1 border border-border rounded-industrial px-2 py-1">
                <AvailabilityBadge status={status} /> {count}
              </span>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-steel border-b border-border text-left">
                  <th className="py-1 pr-2 font-medium">Part</th>
                  <th className="py-1 pr-2 font-medium">Required</th>
                  <th className="py-1 pr-2 font-medium">On Hand</th>
                  <th className="py-1 pr-2 font-medium">Reserved</th>
                  <th className="py-1 pr-2 font-medium">Quarantined</th>
                  <th className="py-1 pr-2 font-medium">Usable</th>
                  <th className="py-1 pr-2 font-medium">This Job</th>
                  <th className="py-1 pr-2 font-medium">Shortage</th>
                  <th className="py-1 pr-2 font-medium">Unit</th>
                  <th className="py-1 pr-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {report.lines.map((line) => {
                  const isExpanded = expanded.has(line.bom_line_item_id);
                  return (
                    <>
                      <tr key={line.bom_line_item_id} className="border-b border-border/60">
                        <td className="py-1.5 pr-2 font-mono text-xs whitespace-nowrap">
                          <button
                            className="inline-flex items-center gap-1"
                            onClick={() => toggle(line.bom_line_item_id)}
                          >
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            {line.part_number || "(no part number)"}
                          </button>
                        </td>
                        <td className="py-1.5 pr-2">{line.required_quantity ?? "n/a"}</td>
                        <td className="py-1.5 pr-2">{line.on_hand}</td>
                        <td className="py-1.5 pr-2">{line.reserved}</td>
                        <td className="py-1.5 pr-2">{line.quarantined}</td>
                        <td className="py-1.5 pr-2">{line.usable_available}</td>
                        <td className="py-1.5 pr-2">{line.this_job_allocation}</td>
                        <td className="py-1.5 pr-2">{line.net_shortage ?? "n/a"}</td>
                        <td className="py-1.5 pr-2 text-xs text-steel">{line.unit}</td>
                        <td className="py-1.5 pr-2">
                          <AvailabilityBadge status={line.status} />
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-[#f8f7f2]">
                          <td colSpan={10} className="py-2 px-3 text-xs text-steel">
                            <div>{line.description}</div>
                            <div className="mt-1">{line.explanation}</div>
                            <div className="mt-1 text-steel-light">
                              Material: {line.material || "n/a"} {line.grade && `(${line.grade})`} &middot;
                              {" "}Lots matched: {line.matched_lot_ids.length}
                              {line.supplier_name && <> &middot; Supplier: {line.supplier_name}</>}
                              {line.lead_time_days != null && <> &middot; Lead time: {line.lead_time_days}d</>}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
            {report.lines.length === 0 && (
              <div className="text-sm text-steel text-center py-4">No BOM line items to check.</div>
            )}
          </div>

          {canEdit && hasShortages && (
            <div className="mt-3 flex items-center gap-2">
              <button
                className="btn-primary !px-2 !py-1 text-xs"
                disabled={creatingFor === bomId}
                onClick={createRequisition}
              >
                <ShoppingCart size={13} /> Create Draft Requisition
              </button>
            </div>
          )}
          {requisitionMsg && <div className="mt-2 text-xs text-emerald-700">{requisitionMsg}</div>}
        </>
      )}
    </div>
  );
}
