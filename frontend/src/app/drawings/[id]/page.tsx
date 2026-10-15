"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { ZoomIn, ZoomOut, PlayCircle, CheckCircle2, FileSpreadsheet } from "lucide-react";
import { api, Drawing, Analysis, drawingFileUrl, Component } from "@/lib/api";
import { DemoBadge, StatusBadge, MakeBuyBadge } from "@/components/Badges";

export default function DrawingViewerPage() {
  const params = useParams();
  const id = params?.id as string;
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [activeAnalysis, setActiveAnalysis] = useState<Analysis | null>(null);
  const [zoom, setZoom] = useState(1);
  const [busy, setBusy] = useState(false);
  const [bomMsg, setBomMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const d = await api.getDrawing(id);
    setDrawing(d);
    const a = await api.listAnalyses(id);
    setAnalyses(a);
    setActiveAnalysis(a[0] || null);
  }, [id]);

  useEffect(() => {
    if (id) load();
  }, [id, load]);

  async function runAnalysis() {
    setBusy(true);
    try {
      await api.analyzeDrawing(id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!activeAnalysis) return;
    await api.approveAnalysis(activeAnalysis.id);
    load();
  }

  async function generateBom() {
    if (!activeAnalysis) return;
    setBusy(true);
    try {
      const bom = await api.generateBom(activeAnalysis.id);
      setBomMsg(`BOM v${bom.version} generated with ${bom.line_items.length} line items.`);
    } finally {
      setBusy(false);
    }
  }

  async function updateComponent(c: Component, patch: Partial<Component>) {
    await api.updateComponent(c.id, patch);
    load();
  }

  if (!drawing) {
    return <div className="p-8 text-steel text-sm">Loading drawing...</div>;
  }

  return (
    <div className="flex h-screen">
      {/* Left pane: preview */}
      <div className="w-1/2 border-r border-border bg-white flex flex-col">
        <div className="h-14 border-b border-border flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs">{drawing.drawing_number}</span>
            <StatusBadge status={drawing.status} />
            {drawing.is_demo && <DemoBadge />}
          </div>
          <div className="flex items-center gap-1">
            <button className="btn-secondary !px-2 !py-1" onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}>
              <ZoomOut size={14} />
            </button>
            <span className="text-xs w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button className="btn-secondary !px-2 !py-1" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
              <ZoomIn size={14} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto bg-[#f2f1ec] flex items-center justify-center p-6">
          {["pdf"].includes(drawing.file_type) ? (
            <embed src={drawingFileUrl(drawing.id)} type="application/pdf" className="w-full h-full" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={drawingFileUrl(drawing.id)}
              alt={drawing.title}
              style={{ transform: `scale(${zoom})`, transformOrigin: "center" }}
              className="max-w-none transition-transform"
            />
          )}
        </div>
      </div>

      {/* Right pane: analysis workspace */}
      <div className="w-1/2 overflow-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-semibold">{drawing.title || drawing.drawing_number}</h1>
            <p className="text-xs text-steel">
              Rev {drawing.revision} &middot; {drawing.units} &middot; Scale {drawing.scale || "n/a"}
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" disabled={busy} onClick={runAnalysis}>
              <PlayCircle size={15} /> {analyses.length ? "Re-run Analysis" : "Run Analysis"}
            </button>
          </div>
        </div>

        {drawing.error_message && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3">
            {drawing.error_message}
          </div>
        )}

        {!activeAnalysis && (
          <div className="card p-6 text-sm text-steel text-center">
            No analysis yet. Click &quot;Run Analysis&quot; to extract the title block, dimensions, and
            component candidates ({drawing.is_demo ? "demo data" : "using configured AI provider"}).
          </div>
        )}

        {activeAnalysis && (
          <>
            <div className="card p-4 mb-4">
              <h2 className="text-sm font-semibold mb-2 flex items-center justify-between">
                Title Block
                <span className="text-xs font-normal text-steel-light">
                  provider: {activeAnalysis.provider} &middot; confidence{" "}
                  {(activeAnalysis.overall_confidence * 100).toFixed(0)}%
                </span>
              </h2>
              <dl className="grid grid-cols-2 gap-y-1 text-sm">
                {Object.entries(activeAnalysis.title_block).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-steel capitalize">{k.replace(/_/g, " ")}</dt>
                    <dd className="font-medium">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="card p-4 mb-4">
              <h2 className="text-sm font-semibold mb-2">Materials</h2>
              <div className="flex flex-wrap gap-2">
                {activeAnalysis.materials.length === 0 && <span className="text-sm text-steel">None detected.</span>}
                {activeAnalysis.materials.map((m, i) => (
                  <span key={i} className="text-xs bg-surface border border-border rounded-full px-2 py-1">
                    {m}
                  </span>
                ))}
              </div>
            </div>

            <div className="card p-4 mb-4">
              <h2 className="text-sm font-semibold mb-3">Component Candidates ({activeAnalysis.components.length})</h2>
              <div className="space-y-3">
                {activeAnalysis.components.map((c) => (
                  <div key={c.id} className="border border-border rounded-industrial p-3">
                    <div className="flex items-center justify-between mb-1">
                      <div className="font-mono text-xs">{c.part_number || "(no part number)"}</div>
                      <div className="flex items-center gap-2">
                        <MakeBuyBadge value={c.make_buy} />
                        <span className="text-xs text-steel-light">{(c.confidence * 100).toFixed(0)}% conf.</span>
                      </div>
                    </div>
                    <div className="text-sm">{c.description}</div>
                    <div className="text-xs text-steel mt-1">
                      {c.category} &middot; Qty {c.quantity} &middot; {c.material || "material n/a"}
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                      <select
                        className="text-xs border border-border rounded px-2 py-1"
                        value={c.make_buy}
                        onChange={(e) => updateComponent(c, { make_buy: e.target.value })}
                      >
                        <option>Make</option>
                        <option>Buy</option>
                        <option>Review</option>
                      </select>
                      <select
                        className="text-xs border border-border rounded px-2 py-1"
                        value={c.verification_status}
                        onChange={(e) => updateComponent(c, { verification_status: e.target.value })}
                      >
                        <option>Unverified</option>
                        <option>Verified</option>
                        <option>Rejected</option>
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <button className="btn-secondary" onClick={approve}>
                <CheckCircle2 size={15} /> Approve Analysis
              </button>
              <button className="btn-primary" disabled={busy} onClick={generateBom}>
                <FileSpreadsheet size={15} /> Generate BOM
              </button>
            </div>
            {bomMsg && <div className="mt-3 text-sm text-emerald-700">{bomMsg}</div>}
          </>
        )}
      </div>
    </div>
  );
}
