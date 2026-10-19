"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, CartesianGrid, Cell, LabelList, PieChart, Pie, Tooltip,
} from "recharts";
import {
  Sparkles, RotateCcw, MoreHorizontal, BarChart3, FileText, Layers, Settings, ShoppingCart, ArrowRight,
  Upload, ClipboardCheck, Calculator, FolderOpen, CircleDot,
} from "lucide-react";
import { api, DashboardMetrics } from "@/lib/api";
import { describeActivity, formatDateTime } from "@/lib/format";
import PageLayout, { AsideSection, AsideItem } from "@/components/PageLayout";

const STATUS_BUCKETS: { label: string; statuses: string[]; color: string }[] = [
  { label: "Uploaded", statuses: ["Uploaded", "Queued", "Processing"], color: "#c9ced6" },
  { label: "Analyzed", statuses: ["NeedsReview"], color: "#2a323d" },
  { label: "Reviewed", statuses: ["Reviewed"], color: "url(#bar-cyan)" },
  { label: "Approved", statuses: ["BOMGenerated"], color: "#f26a1b" },
];

const MIX_COLORS = { Make: "#1d64c8", Buy: "#0f2340", Review: "#cfd4da" };

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

  const statusCount = (statuses: string[]) =>
    metrics ? statuses.reduce((n, st) => n + (metrics.status_breakdown[st] || 0), 0) : 0;

  const aside = (
    <>
      <AsideSection title="Quick Actions">
        <div className="space-y-1">
          <AsideItem icon={Upload} label="Analyze New Drawing" href="/drawings?upload=1" />
          <AsideItem icon={ClipboardCheck} label="Review Queue" href="/review" />
          <AsideItem icon={ShoppingCart} label="Purchase Requirements" href="/procurement" />
          <AsideItem icon={Calculator} label="Calculations" href="/calculations" />
        </div>
      </AsideSection>
      <div className="mx-3 border-t border-border" />
      <AsideSection title="Drawing Status">
        <div className="space-y-1">
          <AsideItem icon={FolderOpen} label="All Drawings" count={metrics?.total_drawings ?? "–"} href="/drawings" active />
          {STATUS_BUCKETS.map((b) => (
            <AsideItem
              key={b.label}
              icon={CircleDot}
              label={b.label}
              count={statusCount(b.statuses)}
              href={`/drawings?status=${b.statuses[0]}`}
            />
          ))}
        </div>
      </AsideSection>
    </>
  );

  return (
    <PageLayout
      title="Operations Dashboard"
      subtitle="Turn engineering drawings into accurate BOMs and procurement plans."
      aside={aside}
    >
      <div className="flex items-center justify-end gap-3 mb-4">
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
            <Link href="/drawings?upload=1" className="btn-cta">
              <BarChart3 size={19} /> Analyze New Drawing
            </Link>
      </div>

      {loading || !metrics ? (
        <div className="text-steel text-sm">Loading metrics...</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-5">
            <StatCard icon={<FileText size={34} strokeWidth={1.6} />} label="Drawings" value={metrics.total_drawings} hint="Total in library" />
            <StatCard icon={<Layers size={34} strokeWidth={1.6} />} label="BOM Line Items" value={metrics.total_bom_items} hint="Extracted components" />
            <StatCard icon={<Settings size={34} strokeWidth={2.2} />} label="Make Items" value={metrics.make_count} hint="Items to manufacture" />
            <StatCard icon={<ShoppingCart size={34} strokeWidth={1.6} />} label="Buy Items" value={metrics.buy_count} hint="Items to procure" />
          </div>

          <div className="grid grid-cols-[1.35fr_1fr] gap-4 mb-5">
            <div className="card p-5">
              <h2 className="section-title mb-3">Drawing Status Breakdown</h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={statusData} margin={{ top: 22, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="bar-cyan" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#3b82e6" />
                      <stop offset="1" stopColor="#1d64c8" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e7ebf0" />
                  <XAxis dataKey="label" tick={{ fontSize: 13, fill: "#5a6576" }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 13, fill: "#5a6576" }} axisLine={false} tickLine={false} width={44}
                    label={{ value: "Count", angle: -90, position: "insideLeft", offset: 12, style: { fontSize: 13, fill: "#5a6576" } }} />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]} maxBarSize={104}>
                    {statusData.map((d) => (
                      <Cell key={d.label} fill={d.color} />
                    ))}
                    <LabelList dataKey="count" position="top" style={{ fontSize: 16, fontWeight: 700, fill: "#0f1b2d" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card p-5">
              <h2 className="section-title mb-3">Make / Buy / Review</h2>
              <div className="flex items-center gap-10 h-[240px] pl-6">
                <div className="relative w-[210px] h-[210px] shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={mixTotal ? mixData : [{ name: "None", value: 1 }]}
                        dataKey="value"
                        innerRadius={66}
                        outerRadius={96}
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
                    <div className="text-[32px] leading-none font-bold text-graphite">{mixTotal}</div>
                    <div className="text-[15px] text-graphite/80 mt-1">Total Items</div>
                  </div>
                </div>
                <ul className="space-y-6 text-[17px] flex-1 pr-4">
                  {mixData.map((d) => (
                    <li key={d.name} className="grid grid-cols-[1fr_48px_60px] items-center">
                      <span className="flex items-center gap-3 text-graphite">
                        <span className="w-5 h-5 rounded-full" style={{ background: MIX_COLORS[d.name as keyof typeof MIX_COLORS] }} />
                        {d.name}
                      </span>
                      <span className="font-bold text-graphite text-right">{d.value}</span>
                      <span className="text-graphite text-right">{mixTotal ? Math.round((d.value / mixTotal) * 100) : 0}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <h2 className="section-title">Recent Activity</h2>
              <Link href="/review" className="flex items-center gap-1.5 text-[17px] font-semibold text-brand hover:text-brand-dark">
                View all <ArrowRight size={19} />
              </Link>
            </div>
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
                {metrics.recent_activity.slice(0, 5).map((a, i) => (
                  <tr key={i}>
                    <td className="td !py-2.5 whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                    <td className="td !py-2.5">{a.entity_type}</td>
                    <td className="td !py-2.5 whitespace-nowrap">{a.action.replace(/_/g, " ")}</td>
                    <td className="td !py-2.5">{describeActivity(a.entity_type, a.action, a.details)}</td>
                    <td className="td !py-2.5">{a.actor || "system"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </PageLayout>
  );
}

function StatCard({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: number; hint: string }) {
  return (
    <div className="card px-7 py-5 flex items-center gap-6">
      <div className="text-brand shrink-0">{icon}</div>
      <div>
        <div className="text-[16px] font-semibold text-graphite">{label}</div>
        <div className="text-[34px] leading-tight font-extrabold text-graphite">{String(value).padStart(2, "0")}</div>
        <div className="text-[15px] text-steel">{hint}</div>
      </div>
    </div>
  );
}
