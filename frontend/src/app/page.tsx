"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, CartesianGrid, Cell, LabelList, PieChart, Pie, Tooltip,
} from "recharts";
import { Plus, Sparkles, RotateCcw, MoreHorizontal } from "lucide-react";
import { api, DashboardMetrics } from "@/lib/api";
import { describeActivity, formatDateTime } from "@/lib/format";
import PageHeader from "@/components/PageHeader";

const STATUS_BUCKETS: { label: string; statuses: string[]; color: string }[] = [
  { label: "Uploaded", statuses: ["Uploaded", "Queued", "Processing"], color: "#b9c2cc" },
  { label: "Analyzed", statuses: ["NeedsReview"], color: "#3f4f63" },
  { label: "Reviewed", statuses: ["Reviewed"], color: "#1f6feb" },
  { label: "Approved", statuses: ["BOMGenerated"], color: "#0e1d30" },
];

const MIX_COLORS = { Make: "#0e1d30", Buy: "#1f6feb", Review: "#b9c2cc" };

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [aiMode, setAiMode] = useState<string>("demo");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  async function load() {
    setLoading(true);
    const [m, ai] = await Promise.all([api.dashboardMetrics(), api.aiStatus()]);
    setMetrics(m);
    setAiMode(ai.mode);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  async function demoAction(fn: () => Promise<unknown>) {
    setMenuOpen(false);
    setBusy(true);
    try {
      await fn();
      await load();
    } finally {
      setBusy(false);
    }
  }

  const statusData = metrics
    ? [
        ...STATUS_BUCKETS.map((b) => ({
          label: b.label,
          color: b.color,
          count: b.statuses.reduce((n, s) => n + (metrics.status_breakdown[s] || 0), 0),
        })),
        ...(metrics.status_breakdown.Failed
          ? [{ label: "Failed", color: "#dc2626", count: metrics.status_breakdown.Failed }]
          : []),
      ]
    : [];
  const mixData = metrics
    ? [
        { name: "Make", value: metrics.make_count },
        { name: "Buy", value: metrics.buy_count },
        { name: "Review", value: metrics.review_count },
      ]
    : [];
  const mixTotal = mixData.reduce((n, d) => n + d.value, 0);

  return (
    <div className="px-8 pb-10">
      <PageHeader
        breadcrumb={[{ label: "Overview" }]}
        title="Operations Dashboard"
        subtitle="Turn engineering drawings into accurate BOMs and procurement plans."
        actions={
          <>
            <div className="relative" ref={menuRef}>
              <button className="btn-icon !w-12 !h-12" disabled={busy} onClick={() => setMenuOpen((o) => !o)} title="Demo data &amp; AI mode">
                <MoreHorizontal size={20} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-64 card py-1 z-40">
                  <div className="px-4 py-2 text-xs text-steel border-b border-border">
                    AI mode:{" "}
                    <span className={aiMode === "openai" || aiMode === "gemini" ? "text-emerald-700 font-medium" : "text-accent-dark font-medium"}>
                      {aiMode === "gemini" ? "Gemini Vision" : aiMode === "openai" ? "OpenAI Vision" : "Demo (no API key)"}
                    </span>
                  </div>
                  <button
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-steel hover:bg-surface hover:text-graphite"
                    onClick={() => demoAction(api.loadDemo)}
                  >
                    <Sparkles size={15} /> Load Demo Project
                  </button>
                  <button
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-steel hover:bg-surface hover:text-graphite"
                    onClick={() => demoAction(api.resetDemo)}
                  >
                    <RotateCcw size={15} /> Reset Demo Data
                  </button>
                </div>
              )}
            </div>
            <Link href="/drawings?upload=1" className="btn-primary !px-6 !py-3 !text-base">
              <Plus size={19} /> Analyze New Drawing
            </Link>
          </>
        }
      />

      {loading || !metrics ? (
        <div className="text-steel text-sm">Loading metrics...</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-5">
            <StatCard label="Drawings" value={metrics.total_drawings} hint="Total in library" />
            <StatCard label="BOM Line Items" value={metrics.total_bom_items} hint="Extracted components" />
            <StatCard label="Make Items" value={metrics.make_count} hint="Items to manufacture" />
            <StatCard label="Buy Items" value={metrics.buy_count} hint="Items to procure" />
          </div>

          <div className="grid grid-cols-2 gap-4 mb-5">
            <div className="card p-5">
              <h2 className="text-lg font-bold mb-3">Drawing Status Breakdown</h2>
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={statusData} margin={{ top: 20, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e3e8ef" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 13, fill: "#5a6576" }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#8a94a3" }} axisLine={false} tickLine={false} />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]} maxBarSize={44}>
                    {statusData.map((d) => (
                      <Cell key={d.label} fill={d.color} />
                    ))}
                    <LabelList dataKey="count" position="top" style={{ fontSize: 12, fontWeight: 600, fill: "#0f1b2d" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card p-5">
              <h2 className="text-lg font-bold mb-3">Make / Buy / Review</h2>
              <div className="flex items-center gap-6 h-[230px]">
                <div className="relative w-[210px] h-[210px] shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={mixTotal ? mixData : [{ name: "None", value: 1 }]}
                        dataKey="value"
                        innerRadius={68}
                        outerRadius={98}
                        startAngle={90}
                        endAngle={-270}
                        stroke="none"
                      >
                        {(mixTotal ? mixData : [{ name: "None", value: 1 }]).map((d) => (
                          <Cell key={d.name} fill={MIX_COLORS[d.name as keyof typeof MIX_COLORS] || "#e3e8ef"} />
                        ))}
                      </Pie>
                      {mixTotal > 0 && <Tooltip />}
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <div className="text-3xl font-bold text-graphite">{mixTotal}</div>
                    <div className="text-xs text-steel">Total items</div>
                  </div>
                </div>
                <ul className="space-y-4 text-[15px] flex-1">
                  {mixData.map((d) => (
                    <li key={d.name} className="flex items-center justify-between">
                      <span className="flex items-center gap-2 text-steel">
                        <span className="w-3 h-3 rounded-sm" style={{ background: MIX_COLORS[d.name as keyof typeof MIX_COLORS] }} />
                        {d.name}
                      </span>
                      <span className="font-semibold text-graphite">{d.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-lg font-bold px-5 pt-5 pb-3">Recent Activity</h2>
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
                {metrics.recent_activity.length === 0 && (
                  <tr>
                    <td colSpan={5} className="td text-steel">No activity yet.</td>
                  </tr>
                )}
                {metrics.recent_activity.map((a, i) => (
                  <tr key={i}>
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
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="card p-5">
      <div className="text-[13px] uppercase tracking-wide text-graphite font-bold">{label}</div>
      <div className="text-[42px] leading-tight font-bold mt-2 text-graphite">{String(value).padStart(2, "0")}</div>
      <div className="text-sm text-steel mt-1">{hint}</div>
    </div>
  );
}
