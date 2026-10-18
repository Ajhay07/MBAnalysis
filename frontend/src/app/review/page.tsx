"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import DrawingThumb from "@/components/DrawingThumb";
import { describeActivity, formatDateTime } from "@/lib/format";

type ReviewRow = Awaited<ReturnType<typeof api.reviewComponents>>[number];
type TabKey = "low" | "needs" | "approved";

const TABS: { key: TabKey; label: string; filter: (r: ReviewRow) => boolean }[] = [
  { key: "low", label: "Low Confidence", filter: (r) => r.low_confidence && r.verification_status !== "Verified" && r.verification_status !== "Rejected" },
  { key: "needs", label: "Needs Review", filter: (r) => r.verification_status === "Unverified" },
  { key: "approved", label: "Approved", filter: (r) => r.verification_status === "Verified" },
];

const ACTION_STYLES: Record<string, string> = {
  Make: "bg-accent text-white border-accent",
  Buy: "bg-navy text-white border-navy",
  Review: "bg-amber-500 text-white border-amber-500",
};

function confidenceColor(c: number): string {
  if (c < 0.5) return "bg-red-500";
  if (c < 0.7) return "bg-amber-400";
  return "bg-emerald-500";
}

export default function ReviewPage() {
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>("low");
  const [savingId, setSavingId] = useState<string | null>(null);

  async function load() {
    const [r, a] = await Promise.all([api.reviewComponents(), api.auditTrail()]);
    setRows(r);
    setAudit(a);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function setMakeBuy(row: ReviewRow, value: string) {
    if (row.make_buy === value) return;
    setSavingId(row.component_id);
    try {
      await api.updateComponent(row.component_id, { make_buy: value });
      setRows((prev) => prev.map((r) => (r.component_id === row.component_id ? { ...r, make_buy: value } : r)));
      setAudit(await api.auditTrail());
    } finally {
      setSavingId(null);
    }
  }

  const active = TABS.find((t) => t.key === tab)!;
  const visible = rows.filter(active.filter);

  return (
    <div className="px-8 pb-8 pt-2 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="page-title">Review &amp; Approval Center</h1>
        <p className="page-subtitle">Review AI-extracted components and resolve low-confidence items.</p>
      </div>

      <div className="card mb-5">
        <div className="flex border-b border-border px-2">
          {TABS.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? "tab-active" : ""}`} onClick={() => setTab(t.key)}>
              {t.label} ({rows.filter(t.filter).length})
            </button>
          ))}
        </div>
        <table className="w-full">
          <thead className="border-b border-border bg-surface/60">
            <tr>
              <th className="th">Drawing</th>
              <th className="th">Component</th>
              <th className="th">AI Suggestion</th>
              <th className="th w-40">Confidence</th>
              <th className="th w-56">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && (
              <tr>
                <td colSpan={5} className="td text-steel">Loading...</td>
              </tr>
            )}
            {!loading && visible.length === 0 && (
              <tr>
                <td colSpan={5} className="td text-steel">Nothing here.</td>
              </tr>
            )}
            {visible.map((r) => (
              <tr key={r.component_id} className="hover:bg-surface/50">
                <td className="td">
                  <Link href={`/drawings/${r.drawing_id}`} className="flex items-center gap-3 group">
                    <DrawingThumb id={r.drawing_id} fileType={r.file_type} className="w-14 h-11" />
                    <span className="text-xs text-steel group-hover:text-brand">{r.drawing_number}</span>
                  </Link>
                </td>
                <td className="td font-medium">{r.part_number || "—"}</td>
                <td className="td text-steel">{r.description}</td>
                <td className="td">
                  <div className="text-sm font-semibold mb-1">{Math.round(r.confidence * 100)}%</div>
                  <div className="h-1.5 w-28 rounded-full bg-border overflow-hidden">
                    <div className={`h-full ${confidenceColor(r.confidence)}`} style={{ width: `${Math.round(r.confidence * 100)}%` }} />
                  </div>
                </td>
                <td className="td">
                  <div className="flex gap-1.5">
                    {["Make", "Buy", "Review"].map((v) => (
                      <button
                        key={v}
                        disabled={savingId === r.component_id}
                        onClick={() => setMakeBuy(r, v)}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                          r.make_buy === v ? ACTION_STYLES[v] : "bg-white text-graphite border-border hover:bg-surface"
                        }`}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="text-base font-semibold px-5 pt-5 pb-3">Audit Trail</h2>
        <table className="w-full">
          <thead className="border-y border-border bg-surface/60">
            <tr>
              <th className="th">Time</th>
              <th className="th">Entity</th>
              <th className="th">Action</th>
              <th className="th">Details</th>
              <th className="th">User</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {audit.slice(0, 50).map((a) => (
              <tr key={a.id}>
                <td className="td text-steel whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                <td className="td text-steel">{a.entity_type}</td>
                <td className="td text-steel whitespace-nowrap">{a.action.replace(/_/g, " ")}</td>
                <td className="td text-steel">{describeActivity(a.entity_type, a.action, a.details)}</td>
                <td className="td text-steel">{a.actor || "system"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
