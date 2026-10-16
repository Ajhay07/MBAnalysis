"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Plus, Sparkles, RotateCcw } from "lucide-react";
import { api, DashboardMetrics } from "@/lib/api";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [aiMode, setAiMode] = useState<string>("demo");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

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

  const statusData = metrics
    ? Object.entries(metrics.status_breakdown).map(([status, count]) => ({ status, count }))
    : [];
  const makeBuyData = metrics
    ? [
        { name: "Make", count: metrics.make_count },
        { name: "Buy", count: metrics.buy_count },
        { name: "Review", count: metrics.review_count },
      ]
    : [];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-graphite">Operations Dashboard</h1>
          <p className="text-sm text-steel mt-0.5">
            AI mode:{" "}
            <span className={`font-medium ${aiMode === "openai" || aiMode === "gemini" ? "text-emerald-700" : "text-accent-dark"}`}>
              {aiMode === "gemini" ? "Gemini Vision" : aiMode === "openai" ? "OpenAI Vision" : "Demo (no API key configured)"}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await api.loadDemo();
              await load();
              setBusy(false);
            }}
          >
            <Sparkles size={16} /> Load Demo Project
          </button>
          <button
            className="btn-secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await api.resetDemo();
              await load();
              setBusy(false);
            }}
          >
            <RotateCcw size={16} /> Reset Demo Data
          </button>
          <Link href="/drawings?upload=1" className="btn-primary">
            <Plus size={16} /> Analyze New Drawing
          </Link>
        </div>
      </div>

      {loading || !metrics ? (
        <div className="text-steel text-sm">Loading metrics...</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-6">
            <StatCard label="Drawings" value={metrics.total_drawings} />
            <StatCard label="BOM Line Items" value={metrics.total_bom_items} />
            <StatCard label="Make" value={metrics.make_count} accent />
            <StatCard label="Buy" value={metrics.buy_count} accent />
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="card p-5">
              <h2 className="text-sm font-semibold mb-3">Drawing Status Breakdown</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={statusData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e1dc" />
                  <XAxis dataKey="status" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#d2601a" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="card p-5">
              <h2 className="text-sm font-semibold mb-3">Make / Buy / Review</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={makeBuyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e1dc" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#5b6166" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-5">
            <h2 className="text-sm font-semibold mb-3">Recent Activity</h2>
            <ul className="divide-y divide-border">
              {metrics.recent_activity.length === 0 && (
                <li className="py-3 text-sm text-steel">No activity yet.</li>
              )}
              {metrics.recent_activity.map((a, i) => (
                <li key={i} className="py-2 text-sm flex justify-between">
                  <span>
                    <span className="font-medium">{a.entity_type}</span> {a.action}
                  </span>
                  <span className="text-steel-light text-xs">{new Date(a.created_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="card p-5">
      <div className="text-xs uppercase tracking-wide text-steel font-medium">{label}</div>
      <div className={`text-3xl font-semibold mt-1 ${accent ? "text-accent" : "text-graphite"}`}>{value}</div>
    </div>
  );
}
