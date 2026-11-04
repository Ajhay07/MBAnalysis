"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Scan, RotateCcw, RotateCw, Maximize2, ClipboardList, Download, AlertTriangle } from "lucide-react";
import { api, Drawing, Analysis, Bom, BomTree, drawingFileUrl, drawingPagePreviewUrl, Component, BomLineItem, JobRecord, OcrPageEvidence, OcrRegion, ReferenceBomResponse, Indent, indentPdfUrl } from "@/lib/api";
import { StatusBadge, MakeBuyBadge, QuantityBasisBadge, AssumptionNote, CatalogMatchBadge, StockAvailabilityBadge, CalcResultBadge } from "@/components/Badges";
import BomPanel from "@/components/BomPanel";
import InventoryAvailabilityPanel from "@/components/InventoryAvailabilityPanel";
import ReferenceBomPanel from "@/components/ReferenceBomPanel";
import PageLayout, { AsideSection, AsideItem } from "@/components/PageLayout";
import { FileText } from "lucide-react";

// Mirrors backend/app/services/indent_service.py:format_size_text - same key order/labels, so
// the SIZE shown here matches what ends up on the generated indent sheet. "" (not "n/a") when
// there's nothing extracted yet, so it's visually distinct from a genuinely empty-but-checked
// dimensions dict.
const SIZE_KEY_ORDER = ["od", "id", "thk", "l", "length", "width", "height", "dia", "pcd", "hole_dia", "noh", "size"];
const SIZE_KEY_LABELS: Record<string, string> = {
  od: "OD", id: "ID", thk: "Thk", l: "L", length: "L", width: "W", height: "H",
  dia: "Dia", pcd: "PCD", hole_dia: "Hole Ø", noh: "No. of Holes", size: "",
};
function formatSizeText(dimensions: Record<string, unknown> | null | undefined): string {
  if (!dimensions) return "";
  const parts: string[] = [];
  const seen = new Set<string>();
  for (const key of SIZE_KEY_ORDER) {
    const value = dimensions[key];
    if (value !== undefined && value !== null && value !== "") {
      const label = SIZE_KEY_LABELS[key] ?? key;
      parts.push(label ? `${label} ${value}` : String(value));
      seen.add(key);
    }
  }
  for (const [key, value] of Object.entries(dimensions)) {
    if (!seen.has(key) && key.startsWith("dim_") && value !== undefined && value !== null && value !== "") {
      parts.push(String(value));
    }
  }
  return parts.join("  ");
}

// Mirrors backend/app/services/calc_engine_service.py:format_bellows_or_shroud_size_text - "L x
// W x T"-style text (MB's own convention for these two component types - see the physical
// indent sheet) from a component's own calc_result, when it has one. Only the dimensions
// actually computed appear; a missing one (e.g. Bellows' width, which this drawing family never
// prints anywhere extractable) is simply left out rather than padded with a placeholder.
function formatCalcSizeText(calcResult: Component["calc_result"]): string {
  const dims = calcResult?.final_proposed_dimensions as Record<string, unknown> | undefined;
  if (!dims) return "";
  return (["length", "width", "thickness"] as const)
    .map((k) => dims[k])
    .filter((v) => v !== null && v !== undefined)
    .join(" x ");
}

// What the Size field actually shows: for Bellows/Shroud, MB's own Length x Width x Thickness
// reading (from the manufacturing formula - see compute_bellows_or_shroud_result) once it has
// one, since the plain OD/Thk/L extraction below is the wrong shape entirely for these two
// sheet-metal parts; every other component type (and a Bellows/Shroud with nothing calculated
// yet) keeps the plain extracted-dimensions text, same as always.
function displaySizeText(c: Component): string {
  return formatCalcSizeText(c.calc_result) || formatSizeText(c.dimensions);
}

// Every editable field on this page (Description, Size, Material, Qty, Calc Inputs) saves on
// blur, not on Enter - there is no separate "save"/"calculate" button anywhere. Pressing Enter
// in a plain, form-less <input> does nothing in a browser by default (no submit, no blur), so
// without this a reviewer who types a value and presses Enter sees no save happen at all and no
// indication why - confirmed as a real point of confusion, not just a missing nicety. Blurring
// the field on Enter reuses the existing onBlur handler as the one save path, rather than
// duplicating the save logic here.
function blurOnEnter(e: React.KeyboardEvent<HTMLInputElement>) {
  if (e.key === "Enter") e.currentTarget.blur();
}

// Client-side mirror of engineering_engine.routing.registry's BELLOWS/SHROUD alias match - only
// these two component types have a real manufacturing formula (see
// app.services.calc_engine_service.compute_bellows_or_shroud_result), so only they get the
// editable Calc Inputs field. Good enough as a UI gate (the backend is the real authority and
// simply does nothing for any other component type); doesn't need to be exact.
function isBellowsOrShroud(description: string): boolean {
  const d = description.toUpperCase();
  return d.includes("BELLOW") || d.includes("SHROUD");
}

// calc_inputs as "key=value key=value" text, editable in one field rather than one input per
// parameter - e.g. "od=559 num_plies=1 ply_thickness_mm=0.6". Mirrors how Size already edits
// `dimensions` as one free-text field. Recognized keys (see compute_bellows_or_shroud_result):
// od, thickness, width (override an extracted/reference value), num_plies, ply_thickness_mm,
// pitch_mm, convolution_depth_mm, number_of_convolutions (feed the width formula when no width
// is already known).
function formatCalcInputsText(calcInputs: Record<string, unknown> | null | undefined): string {
  if (!calcInputs) return "";
  return Object.entries(calcInputs)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
}
function parseCalcInputsText(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const token of text.trim().split(/\s+/)) {
    const [key, raw] = token.split("=");
    if (!key || raw === undefined) continue;
    const value = parseFloat(raw);
    if (!Number.isNaN(value)) out[key] = value;
  }
  return out;
}

function OcrOverlay({
  evidence,
  selected,
  onSelect,
}: {
  evidence: OcrPageEvidence;
  selected: OcrRegion | null;
  onSelect: (r: OcrRegion) => void;
}) {
  // bbox coordinates are in the page image's native pixel space, and the image is rendered at
  // native size (max-w-none) inside a wrapper that itself gets the zoom CSS transform - so no
  // extra scaling is needed here, boxes line up 1:1 with the underlying <img>.
  return (
    <div className="absolute inset-0 pointer-events-none">
      {evidence.regions.map((r, i) => {
        const xs = r.bbox.map((p) => p[0]);
        const ys = r.bbox.map((p) => p[1]);
        const x = Math.min(...xs);
        const y = Math.min(...ys);
        const w = Math.max(...xs) - x;
        const h = Math.max(...ys) - y;
        const isSelected = selected === r;
        return (
          <div
            key={i}
            onClick={() => onSelect(r)}
            className="absolute pointer-events-auto cursor-pointer"
            style={{
              left: x,
              top: y,
              width: Math.max(w, 2),
              height: Math.max(h, 2),
              border: `2px solid ${isSelected ? "#2563eb" : r.low_confidence ? "#d97706" : "#16a34a"}`,
              backgroundColor: isSelected ? "rgba(37,99,235,0.15)" : r.low_confidence ? "rgba(217,119,6,0.12)" : "transparent",
            }}
            title={`${r.text} (${(r.confidence * 100).toFixed(0)}%)`}
          />
        );
      })}
    </div>
  );
}

export default function DrawingViewerPage() {
  const params = useParams();
  const id = params?.id as string;
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [activeAnalysis, setActiveAnalysis] = useState<Analysis | null>(null);
  const [zoom, setZoom] = useState(1);
  const [busy, setBusy] = useState(false);
  const [bomMsg, setBomMsg] = useState<string | null>(null);
  const [bom, setBom] = useState<Bom | null>(null);
  const [bomTree, setBomTree] = useState<BomTree | null>(null);
  const [page, setPage] = useState(1);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [showJobDetails, setShowJobDetails] = useState(false);
  const [showOcrEvidence, setShowOcrEvidence] = useState(false);
  const [ocrEvidence, setOcrEvidence] = useState<OcrPageEvidence | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState<OcrRegion | null>(null);
  const [referenceBom, setReferenceBom] = useState<ReferenceBomResponse | null>(null);
  const [catalogById, setCatalogById] = useState<Record<string, any>>({});
  // Only used when the drawing's own title block has no QUANTITY field (OCR couldn't find it -
  // title_block.drawing_quantity is null) - a local, unsaved override so each component's total
  // quantity can still be shown/calculated here, without waiting for the Generate Indent Sheet
  // form (which has its own, separately-saved assembly_quantity for the actual indent run).
  const [manualAssemblyQty, setManualAssemblyQty] = useState<string>("");
  const [allDrawings, setAllDrawings] = useState<Drawing[]>([]);
  const [tab, setTab] = useState<"info" | "components" | "bom">("info");
  // Single-action indent workflow: the user just wants "upload -> Indent Sheet", not a
  // separate manual "Approve Analysis" then "Generate BOM" review step surfaced as its own
  // thing. The BOM still gets generated (indent generation and inventory availability both
  // depend on it), but it happens automatically behind "Generate Indent Sheet" rather than as
  // a button the user has to click on its own - the inline form below collects only what a
  // BOM genuinely can't contain on its own (assembly quantity, W.O. number, etc.).
  const [showIndentForm, setShowIndentForm] = useState(false);
  const [indentForm, setIndentForm] = useState({
    assembly_quantity: "", wo_number: "", party_name: "", required_on: "", serial_no: "", indent_date: "",
  });
  const [indentSubmitting, setIndentSubmitting] = useState(false);
  const [indentError, setIndentError] = useState<string | null>(null);
  const [generatedIndent, setGeneratedIndent] = useState<Indent | null>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);

  const fitToView = useCallback((size = imgSize) => {
    const box = canvasRef.current;
    if (!box || !size) return setZoom(1);
    const fit = Math.min((box.clientWidth - 48) / size.w, (box.clientHeight - 48) / size.h);
    setZoom(Math.max(0.1, Math.min(4, Math.round(fit * 100) / 100)));
  }, [imgSize]);

  function onImageLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const size = { w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight };
    if (!imgSize) fitToView(size);
    setImgSize(size);
  }

  const load = useCallback(async () => {
    const d = await api.getDrawing(id);
    setDrawing(d);
    const a = await api.listAnalyses(id);
    setAnalyses(a);
    setActiveAnalysis(a[0] || null);
    setPage(1);
    const boms = await api.listBomsForDrawing(id);
    const latestBom = boms[0] || null;
    setBom(latestBom);
    setBomTree(latestBom ? await api.getBomTree(latestBom.id) : null);
    setJobs(await api.listDrawingJobs(id));
    const catalog = await api.listCatalog();
    setCatalogById(Object.fromEntries(catalog.map((c: any) => [c.id, c])));
    setAllDrawings(await api.listDrawings());
  }, [id]);

  async function reprocess() {
    setBusy(true);
    try {
      await api.reprocessDrawing(id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (id) load();
  }, [id, load]);

  useEffect(() => {
    if (!id || !activeAnalysis) {
      setReferenceBom(null);
      return;
    }
    let cancelled = false;
    api
      .getReferenceBom(id, activeAnalysis.id)
      .then((r) => {
        if (!cancelled) setReferenceBom(r);
      })
      .catch(() => {
        if (!cancelled) setReferenceBom(null);
      });
    return () => {
      cancelled = true;
    };
  }, [id, activeAnalysis]);

  useEffect(() => {
    if (!showOcrEvidence || !id) return;
    let cancelled = false;
    setOcrLoading(true);
    setSelectedRegion(null);
    api
      .getPageOcrEvidence(id, page)
      .then((evidence) => {
        if (!cancelled) setOcrEvidence(evidence);
      })
      .catch(() => {
        if (!cancelled) setOcrEvidence(null);
      })
      .finally(() => {
        if (!cancelled) setOcrLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showOcrEvidence, id, page]);

  async function runAnalysis() {
    setBusy(true);
    try {
      await api.analyzeDrawing(id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  /** The BOM a real indent needs always exists by the time this runs, but the user never has
   * to click a separate "Generate BOM" button to get there - this reuses the current one (any
   * BOM already generated for THIS analysis) or generates it silently on demand.
   *
   * Regression fix: this used to reuse `bom` whenever one existed at all, with no check that it
   * came from the CURRENT analysis - so re-running analysis (e.g. after a drawing-extraction
   * fix) never refreshed the BOM an indent actually gets built from, silently feeding every
   * subsequent indent stale data (wrong quantities, missing dimensions, ...) forever, however
   * many times the analysis itself was redone. Now regenerates whenever bom.analysis_id doesn't
   * match the active analysis, not just when there's no BOM at all. */
  async function ensureBom(): Promise<Bom> {
    if (bom && bom.analysis_id === activeAnalysis?.id) return bom;
    if (!activeAnalysis) throw new Error("No analysis to generate a BOM from yet.");
    const generated = await api.generateBom(activeAnalysis.id);
    setBomMsg(`BOM v${generated.version} generated with ${generated.line_items.length} line items.`);
    setBom(generated);
    setBomTree(await api.getBomTree(generated.id));
    return generated;
  }

  async function submitIndent() {
    const qty = parseFloat(indentForm.assembly_quantity);
    if (!qty || qty <= 0) {
      setIndentError("Assembly quantity must be a positive number.");
      return;
    }
    setIndentSubmitting(true);
    setIndentError(null);
    try {
      if (activeAnalysis && drawing && drawing.status === "NeedsReview") {
        await api.approveAnalysis(activeAnalysis.id);
      }
      const targetBom = await ensureBom();
      const indent = await api.generateIndent(targetBom.id, {
        assembly_quantity: qty,
        wo_number: indentForm.wo_number.trim(),
        party_name: indentForm.party_name.trim(),
        required_on: indentForm.required_on.trim(),
        serial_no: indentForm.serial_no.trim(),
        indent_date: indentForm.indent_date.trim(),
      });
      setGeneratedIndent(indent);
      await load();
    } catch (e: any) {
      setIndentError(e.message || "Failed to generate indent sheet.");
    } finally {
      setIndentSubmitting(false);
    }
  }

  async function updateComponent(c: Component, patch: Partial<Component>) {
    await api.updateComponent(c.id, patch);
    load();
  }


  async function updateBomLineItem(lineItemId: string, patch: Partial<BomLineItem>) {
    if (!bom) return;
    await api.updateBomLineItem(lineItemId, patch);
    const [freshBom, freshTree] = await Promise.all([api.getBom(bom.id), api.getBomTree(bom.id)]);
    setBom(freshBom);
    setBomTree(freshTree);
  }

  if (!drawing) {
    return <div className="p-8 text-steel text-sm">Loading drawing...</div>;
  }

  const pageCount = activeAnalysis?.page_count ?? 1;
  const components = activeAnalysis?.components ?? [];
  // The drawing's own "QUANTITY" title-block field (how many assemblies this drawing covers -
  // see app.providers.deterministic_provider._parse_drawing_quantity_and_nb), read the same way
  // the Generate Indent Sheet button already defaults assembly_quantity from it. Lets each
  // component show its own TOTAL quantity (formula #5: quantity_per_assembly * assemblies),
  // live, without waiting for an indent to be generated.
  const parsedTitleBlockQty = (activeAnalysis?.title_block as Record<string, unknown> | undefined)?.drawing_quantity as
    | number
    | null
    | undefined;
  const manualQtyParsed = parseFloat(manualAssemblyQty);
  const assemblyQuantity = parsedTitleBlockQty ?? (Number.isNaN(manualQtyParsed) ? null : manualQtyParsed);

  function catalogStatus(c: Component): string {
    const cat = c.catalog_component_id ? catalogById[c.catalog_component_id] : null;
    if (!cat || cat.stock_quantity == null) return "Unknown";
    if (cat.stock_quantity <= 0) return "Out of Stock";
    if (cat.stock_quantity < c.quantity) return "Low Stock";
    return "In Stock";
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else viewerRef.current?.requestFullscreen();
  }

  const titleBlockRows: [string, string][] = activeAnalysis
    ? Object.entries(activeAnalysis.title_block).map(([k, v]) => [k.replace(/_/g, " "), String(v)])
    : [
        ["drawing number", drawing.drawing_number],
        ["title", drawing.title],
        ["revision", drawing.revision],
        ["units", drawing.units],
        ["scale", drawing.scale || "n/a"],
      ];

  const aside = (
    <>
      <AsideSection title="Drawings">
        <div className="space-y-1">
          {allDrawings.map((d) => (
            <AsideItem key={d.id} icon={FileText} label={d.drawing_number} count={`Rev ${d.revision}`}
              active={d.id === drawing.id} href={`/drawings/${d.id}`} />
          ))}
        </div>
      </AsideSection>
      <div className="mx-3 border-t border-border" />
      <AsideSection title="This Drawing">
        <dl className="px-3 grid grid-cols-[96px_1fr] gap-y-2 text-[14px]">
          <dt className="text-steel">Status</dt><dd><StatusBadge status={drawing.status} /></dd>
          <dt className="text-steel">Revision</dt><dd className="text-graphite">{drawing.revision}</dd>
          <dt className="text-steel">Scale</dt><dd className="text-graphite">{drawing.scale || "n/a"}</dd>
          <dt className="text-steel">Units</dt><dd className="text-graphite">{drawing.units}</dd>
          <dt className="text-steel">File</dt><dd className="text-graphite truncate" title={drawing.file_name}>{drawing.file_name}</dd>
          <dt className="text-steel">Components</dt><dd className="text-graphite">{components.length}</dd>
          <dt className="text-steel">BOM</dt><dd className="text-graphite">{bom ? `v${bom.version} · ${bom.status}` : "Not generated"}</dd>
        </dl>
      </AsideSection>
    </>
  );

  return (
    <PageLayout
      aside={aside}
      breadcrumb={[{ label: "Drawing Library", href: "/drawings" }, { label: drawing.drawing_number }]}
      title={drawing.drawing_number}
      subtitle={drawing.title}
      heroExtra={
        <div className="flex items-center gap-2 mt-2.5">
          <StatusBadge status={drawing.status} />
          {drawing.is_demo && (
            <span className="inline-flex items-center px-3 py-1 rounded-md text-[14px] font-medium bg-accent-light text-accent-dark">
              DEMO DATA
            </span>
          )}
          {drawing.status === "Failed" && (
            <button
              className="text-xs underline text-red-700"
              onClick={() => setShowJobDetails((s) => !s)}
              title={drawing.job_failure_reason || drawing.error_message || "Processing failed"}
            >
              processing details{drawing.job_retry_count ? ` (retry ${drawing.job_retry_count})` : ""}
            </button>
          )}
          <button
            className="btn-secondary !py-1.5 !px-3.5 !text-sm ml-2"
            disabled={busy}
            onClick={drawing.status === "Failed" ? reprocess : runAnalysis}
          >
            <RotateCw size={15} /> {drawing.status === "Failed" ? "Retry Analysis" : analyses.length ? "Re-run Analysis" : "Run Analysis"}
          </button>
        </div>
      }
    >

      <div className="flex gap-5 h-[calc(100vh-345px)] min-h-[520px]">
        {/* Left: drawing viewer */}
        <div ref={viewerRef} className="flex-[1.25] min-w-0 card flex flex-col overflow-hidden bg-white">
          <div className="h-12 border-b border-border flex items-center justify-between px-3">
            <div className="flex items-center gap-1.5">
              <button className="btn-icon" title="Fit to view" onClick={() => fitToView()}>
                <Scan size={15} />
              </button>
              <button className="btn-icon" title="Zoom out" onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}>
                <ZoomOut size={15} />
              </button>
              <button className="btn-icon" title="Zoom in" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
                <ZoomIn size={15} />
              </button>
              <button className="btn-icon" title="Reset zoom" onClick={() => setZoom(1)}>
                <RotateCcw size={15} />
              </button>
              <select
                className="input !w-24 !py-1.5 ml-1"
                value={zoom}
                onChange={(e) => setZoom(parseFloat(e.target.value))}
              >
                {[0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4].concat([0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4].includes(zoom) ? [] : [zoom]).map((z) => (
                  <option key={z} value={z}>
                    {Math.round(z * 100)}%
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                className={`text-xs px-2.5 py-1.5 rounded-industrial border font-medium ${showOcrEvidence ? "bg-ink text-white border-ink" : "border-border text-steel hover:text-graphite"}`}
                onClick={() => setShowOcrEvidence((s) => !s)}
                title="Toggle raw OCR text-region overlay (distinct from AI-interpreted components)"
              >
                OCR Evidence
              </button>
              <button className="btn-icon" title="Full screen" onClick={toggleFullscreen}>
                <Maximize2 size={15} />
              </button>
            </div>
          </div>
          <div ref={canvasRef} className="flex-1 overflow-auto bg-[#eef1f5] flex p-6">
            {drawing.file_type === "pdf" && pageCount > 1 ? (
              <div style={imgSize ? { width: imgSize.w * zoom, height: imgSize.h * zoom } : undefined} className="relative shrink-0 m-auto">
              <div style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }} className="relative inline-block">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={drawingPagePreviewUrl(drawing.id, page)}
                  alt={`${drawing.title || drawing.drawing_number} - page ${page}`}
                  className="max-w-none block bg-white shadow-industrial"
                  onLoad={onImageLoad}
                />
                {showOcrEvidence && ocrEvidence && <OcrOverlay evidence={ocrEvidence} selected={selectedRegion} onSelect={setSelectedRegion} />}
              </div>
              </div>
            ) : drawing.file_type === "pdf" ? (
              <embed src={drawingFileUrl(drawing.id)} type="application/pdf" className="w-full h-full" />
            ) : (
              <div style={imgSize ? { width: imgSize.w * zoom, height: imgSize.h * zoom } : undefined} className="relative shrink-0 m-auto">
              <div style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }} className="relative inline-block">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={drawingFileUrl(drawing.id)} alt={drawing.title} className="max-w-none block bg-white shadow-industrial" onLoad={onImageLoad} />
                {showOcrEvidence && ocrEvidence && <OcrOverlay evidence={ocrEvidence} selected={selectedRegion} onSelect={setSelectedRegion} />}
              </div>
              </div>
            )}
          </div>
          {showOcrEvidence && (
            <div className="border-t border-border p-3 bg-white text-xs max-h-56 overflow-auto">
              <div className="font-semibold mb-2 flex items-center justify-between">
                <span>Raw OCR Evidence (page {page}) &mdash; not human-reviewed</span>
                {ocrEvidence && <span className="text-steel-light font-normal">threshold {(ocrEvidence.confidence_threshold * 100).toFixed(0)}%</span>}
              </div>
              {ocrLoading && <div className="text-steel">Loading OCR regions...</div>}
              {!ocrLoading && ocrEvidence && !ocrEvidence.configured && (
                <div className="text-red-700">{ocrEvidence.error || "OCR not available."}</div>
              )}
              {!ocrLoading && ocrEvidence?.configured && ocrEvidence.regions.length === 0 && (
                <div className="text-steel">No text regions detected on this page.</div>
              )}
              {selectedRegion ? (
                <div className="border border-border rounded p-2 bg-surface">
                  <div className="font-mono">{selectedRegion.text}</div>
                  <div className="text-steel-light mt-1">
                    confidence {(selectedRegion.confidence * 100).toFixed(0)}%
                    {selectedRegion.low_confidence && <span className="text-amber-700 font-semibold"> &middot; needs review</span>}
                    {" "}&middot; page {page} &middot; bbox {JSON.stringify(selectedRegion.bbox)}
                  </div>
                </div>
              ) : (
                ocrEvidence?.configured && ocrEvidence.regions.length > 0 && (
                  <div className="text-steel">Click a highlighted region above to inspect it.</div>
                )
              )}
              {ocrEvidence && ocrEvidence.regions.some((r) => r.low_confidence) && (
                <div className="mt-2">
                  <div className="font-semibold text-amber-800">Needs review ({ocrEvidence.regions.filter((r) => r.low_confidence).length})</div>
                  <ul className="list-disc list-inside">
                    {ocrEvidence.regions.filter((r) => r.low_confidence).map((r, i) => (
                      <li key={i} className="cursor-pointer hover:underline" onClick={() => setSelectedRegion(r)}>
                        {r.text} ({(r.confidence * 100).toFixed(0)}%)
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {drawing.file_type === "pdf" && pageCount > 1 && (
            <div className="h-11 border-t border-border flex items-center justify-center gap-3">
              <button className="btn-icon" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <ChevronLeft size={14} />
              </button>
              <span className="text-xs">
                Page {page} of {pageCount}
              </span>
              <button className="btn-icon" disabled={page >= pageCount} onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>

        {/* Right: tabbed analysis panel */}
        <div className="flex-1 min-w-[380px] card flex flex-col overflow-hidden">
          <div className="flex border-b border-border px-2">
            <button className={`tab ${tab === "info" ? "tab-active" : ""}`} onClick={() => setTab("info")}>
              Information
            </button>
            <button className={`tab ${tab === "components" ? "tab-active" : ""}`} onClick={() => setTab("components")}>
              Components ({components.length})
            </button>
            <button className={`tab ${tab === "bom" ? "tab-active" : ""}`} onClick={() => setTab("bom")}>
              BOM{bom ? ` v${bom.version}` : ""}
            </button>
          </div>

          <div className="flex-1 overflow-auto p-5">
            {showJobDetails && jobs.length > 0 && (
              <div className="mb-4 border border-border rounded p-3 bg-surface text-xs space-y-2">
                <div className="font-semibold">Processing details</div>
                {jobs.map((j) => (
                  <div key={j.id} className="flex justify-between gap-2 border-b border-border/50 pb-1 last:border-0">
                    <span className="font-mono">{j.stage}</span>
                    <span>{j.status}</span>
                    <span>retry {j.retry_count}</span>
                    {j.failure_reason && <span className="text-red-700 truncate max-w-[50%]" title={j.failure_reason}>{j.failure_reason}</span>}
                  </div>
                ))}
              </div>
            )}

            {drawing.error_message && (
              <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3">
                {drawing.error_message}
              </div>
            )}

            {tab === "info" && (
              <>
                <section className="mb-5">
                  <h2 className="text-sm font-semibold mb-2 flex items-center justify-between">
                    Drawing Information
                    {activeAnalysis && (
                      <span className="text-[11px] font-normal text-steel-light">
                        {activeAnalysis.provider} &middot; {(activeAnalysis.overall_confidence * 100).toFixed(0)}% conf.
                      </span>
                    )}
                  </h2>
                  <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm">
                    {titleBlockRows.map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="text-steel capitalize">{k}</dt>
                        <dd className="text-graphite">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </section>

                {activeAnalysis && (
                  <section className="mb-5">
                    <h2 className="text-sm font-semibold mb-2">Materials</h2>
                    <div className="flex flex-wrap gap-2">
                      {activeAnalysis.materials.length === 0 && <span className="text-sm text-steel">None detected.</span>}
                      {activeAnalysis.materials.map((m, i) => (
                        <span key={i} className="text-xs bg-surface border border-border rounded-full px-2.5 py-1">
                          {m}
                        </span>
                      ))}
                    </div>
                  </section>
                )}

                {!activeAnalysis && (
                  <div className="border border-dashed border-border rounded-industrial p-6 text-sm text-steel text-center">
                    No analysis yet. Click &quot;Run Analysis&quot; to extract the title block, dimensions, and
                    component candidates ({drawing.is_demo ? "demo data" : "deterministic OCR + rules by default; see provider on the result"}).
                  </div>
                )}

                {activeAnalysis && (
                  <section>
                    <h2 className="text-sm font-semibold mb-1">Interpreted Components ({components.length})</h2>
                    <p className="text-xs text-steel-light mb-3">
                      AI-interpreted values, human-gated by Verified/Unverified/Rejected and Make/Buy/Review.
                    </p>
                    {parsedTitleBlockQty == null && (
                      <div className="flex items-center gap-1.5 mb-3 text-xs">
                        <span className="text-steel">
                          Assembly qty not found on the drawing - set it to see each component&apos;s total quantity:
                        </span>
                        <input
                          type="number"
                          step="any"
                          className="input !w-20 !py-0.5 !px-1.5 !text-xs"
                          placeholder="e.g. 4"
                          value={manualAssemblyQty}
                          onChange={(e) => setManualAssemblyQty(e.target.value)}
                        />
                      </div>
                    )}
                    <div className="space-y-3">
                      {components.map((c) => {
                        const cat = c.catalog_component_id ? catalogById[c.catalog_component_id] : null;
                        return (
                          <div key={c.id} className="border border-border rounded-industrial p-3">
                            <div className="flex items-center justify-between mb-1">
                              <div className="font-semibold text-sm">{c.part_number || "(no part number)"}</div>
                              <div className="flex items-center gap-2">
                                <QuantityBasisBadge basis={c.quantity_basis} count={c.quantity} />
                                <AssumptionNote isAssumption={c.is_assumption} text={c.assumption_text} />
                                <MakeBuyBadge value={c.make_buy} />
                                <span className="text-xs text-steel-light">{(c.confidence * 100).toFixed(0)}%</span>
                              </div>
                            </div>
                            <input
                              key={`desc:${c.id}:${c.description}`}
                              type="text"
                              className="input !w-full !py-0.5 !px-1.5 !text-sm !font-normal"
                              defaultValue={c.description}
                              onKeyDown={blurOnEnter}
                              onBlur={(e) => {
                                const text = e.target.value.trim();
                                if (text && text !== c.description) updateComponent(c, { description: text });
                              }}
                            />
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="text-xs text-steel w-9 shrink-0">Size:</span>
                              <input
                                key={`size:${c.id}:${displaySizeText(c)}`}
                                type="text"
                                className="input !w-auto !py-0.5 !px-1.5 !text-xs flex-1"
                                placeholder="not extracted - enter manually, e.g. OD 219  Thk 9.5"
                                defaultValue={displaySizeText(c)}
                                title={formatCalcSizeText(c.calc_result) ? "Length x Width x Thickness, from the Bellows/Shroud formula below - edit Calc: to change it." : undefined}
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const text = e.target.value.trim();
                                  if (text !== displaySizeText(c)) {
                                    updateComponent(c, { dimensions: text ? { size: text } : {} });
                                  }
                                }}
                              />
                            </div>
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="text-xs text-steel w-9 shrink-0">Material:</span>
                              <input
                                key={`material:${c.id}:${c.material}`}
                                type="text"
                                className="input !w-auto !py-0.5 !px-1.5 !text-xs flex-1"
                                placeholder="material n/a"
                                defaultValue={c.material}
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const text = e.target.value.trim();
                                  if (text !== c.material) updateComponent(c, { material: text });
                                }}
                              />
                            </div>
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="text-xs text-steel w-9 shrink-0">Qty:</span>
                              <input
                                key={`qty:${c.id}:${c.quantity}`}
                                type="number"
                                step="any"
                                className="input !w-20 !py-0.5 !px-1.5 !text-xs"
                                defaultValue={c.quantity}
                                title="Quantity per assembly - editing this confirms it (clears the 'quantity could not be read' flag on any indent generated from it)."
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const value = parseFloat(e.target.value);
                                  if (!Number.isNaN(value) && value !== c.quantity) updateComponent(c, { quantity: value });
                                }}
                              />
                              {c.quantity_basis === "assumed" && (
                                <span className="text-xs text-amber-600" title="Could not be read from the drawing's BOM table - this is a placeholder, not a confirmed reading.">
                                  unconfirmed
                                </span>
                              )}
                              {assemblyQuantity != null ? (
                                <span className="text-xs text-steel-light" title={`${c.quantity} per assembly × ${assemblyQuantity} assemblies - the figure this prints on the generated indent's WT/QTY column.`}>
                                  = {c.quantity * assemblyQuantity} total
                                </span>
                              ) : (
                                <span className="text-xs text-steel-light" title="The drawing's own assembly quantity (title block QUANTITY field) wasn't found - set it on Generate Indent Sheet to see each component's total.">
                                  (set assembly qty to total)
                                </span>
                              )}
                            </div>
                            {isBellowsOrShroud(c.description) && (
                              <div className="flex items-center gap-1.5 mt-1">
                                <span className="text-xs text-steel w-9 shrink-0" title="Overrides for the Bellows/Shroud formula, e.g. od=559 num_plies=1 ply_thickness_mm=0.6 - editing this recalculates automatically.">Calc:</span>
                                <input
                                  key={`calc:${c.id}:${formatCalcInputsText(c.calc_inputs)}`}
                                  type="text"
                                  className="input !w-auto !py-0.5 !px-1.5 !text-xs flex-1 font-mono"
                                  placeholder="od=559 num_plies=1 ply_thickness_mm=0.6"
                                  defaultValue={formatCalcInputsText(c.calc_inputs)}
                                  onKeyDown={blurOnEnter}
                                  onBlur={(e) => {
                                    const text = e.target.value.trim();
                                    if (text !== formatCalcInputsText(c.calc_inputs)) {
                                      updateComponent(c, { calc_inputs: parseCalcInputsText(text) });
                                    }
                                  }}
                                />
                              </div>
                            )}
                            {c.calc_result && (
                              // Recalculated automatically on every edit above (Calc Inputs,
                              // Size, Material - see app.services.calc_engine_service /
                              // app.routers.analyses.update_component). Read-only here.
                              <div className="flex items-center gap-1.5 mt-1.5">
                                <CalcResultBadge result={c.calc_result} />
                                <span className="text-xs text-steel-light">
                                  {Object.entries(c.calc_result.final_proposed_dimensions || {})
                                    .filter(([, v]) => v !== null && v !== undefined)
                                    .map(([k, v]) => `${k}: ${v}`)
                                    .join("  ·  ")}
                                </span>
                              </div>
                            )}
                            <div className="text-xs text-steel mt-1">
                              {c.category}
                              {pageCount > 1 && (
                                <>
                                  {" "}&middot;{" "}
                                  <button className="underline hover:text-ink" onClick={() => setPage(c.source_page || 1)}>
                                    Page {c.source_page || 1}
                                  </button>
                                </>
                              )}
                            </div>
                            {cat && (
                              <div className="flex items-center gap-2 mt-1.5">
                                <CatalogMatchBadge catalogPartNumber={cat.part_number} />
                                <span className="text-xs text-steel">
                                  {cat.unit_price != null ? `$${cat.unit_price}` : "price n/a"}
                                </span>
                                <StockAvailabilityBadge status={catalogStatus(c)} />
                              </div>
                            )}
                            <div className="flex items-center gap-2 mt-2">
                              <select
                                className="input !w-auto !py-1 !text-xs"
                                value={c.make_buy}
                                onChange={(e) => updateComponent(c, { make_buy: e.target.value })}
                              >
                                <option>Make</option>
                                <option>Buy</option>
                                <option>Review</option>
                              </select>
                              <select
                                className="input !w-auto !py-1 !text-xs"
                                value={c.verification_status}
                                onChange={(e) => updateComponent(c, { verification_status: e.target.value })}
                              >
                                <option>Unverified</option>
                                <option>Verified</option>
                                <option>Rejected</option>
                              </select>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}
              </>
            )}

            {tab === "components" && (
              <>
                {components.length === 0 ? (
                  <div className="text-sm text-steel">No components extracted yet.</div>
                ) : (
                  <table className="w-full mb-5">
                    <thead className="border-b border-border">
                      <tr>
                        <th className="th !px-2">Part</th>
                        <th className="th !px-2">Description</th>
                        <th className="th !px-2">Material</th>
                        <th className="th !px-2">Size</th>
                        <th className="th !px-2 text-right">Qty</th>
                        <th className="th !px-2">Make/Buy</th>
                        <th className="th !px-2">Catalog</th>
                        <th className="th !px-2">Calc</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {components.map((c) => {
                        const cat = c.catalog_component_id ? catalogById[c.catalog_component_id] : null;
                        return (
                          <tr key={c.id}>
                            <td className="td !px-2 font-medium whitespace-nowrap">{c.part_number || "—"}</td>
                            <td className="td !px-2 text-steel">
                              <input
                                key={`desc:${c.id}:${c.description}`}
                                type="text"
                                className="input !w-36 !py-0.5 !px-1.5 !text-xs"
                                defaultValue={c.description}
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const text = e.target.value.trim();
                                  if (text && text !== c.description) updateComponent(c, { description: text });
                                }}
                              />
                            </td>
                            <td className="td !px-2 text-steel">
                              <input
                                key={`material:${c.id}:${c.material}`}
                                type="text"
                                className="input !w-32 !py-0.5 !px-1.5 !text-xs"
                                placeholder="material n/a"
                                defaultValue={c.material}
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const text = e.target.value.trim();
                                  if (text !== c.material) updateComponent(c, { material: text });
                                }}
                              />
                            </td>
                            <td className="td !px-2 text-steel">
                              <input
                                key={`size:${c.id}:${displaySizeText(c)}`}
                                type="text"
                                className="input !w-32 !py-0.5 !px-1.5 !text-xs"
                                placeholder="not extracted"
                                defaultValue={displaySizeText(c)}
                                title={formatCalcSizeText(c.calc_result) ? "Length x Width x Thickness, from the Bellows/Shroud formula - edit Calc: to change it." : undefined}
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const text = e.target.value.trim();
                                  if (text !== displaySizeText(c)) {
                                    updateComponent(c, { dimensions: text ? { size: text } : {} });
                                  }
                                }}
                              />
                            </td>
                            <td className="td !px-2 text-right">
                              <input
                                key={`qty:${c.id}:${c.quantity}`}
                                type="number"
                                step="any"
                                className="input !w-16 !py-0.5 !px-1.5 !text-xs text-right"
                                defaultValue={c.quantity}
                                title="Quantity per assembly - editing this confirms it."
                                onKeyDown={blurOnEnter}
                                onBlur={(e) => {
                                  const value = parseFloat(e.target.value);
                                  if (!Number.isNaN(value) && value !== c.quantity) updateComponent(c, { quantity: value });
                                }}
                              />
                              {c.quantity_basis === "assumed" && (
                                <div className="text-xs text-amber-600 whitespace-nowrap">unconfirmed</div>
                              )}
                              {assemblyQuantity != null && (
                                <div className="text-xs text-steel-light whitespace-nowrap" title={`${c.quantity} per assembly × ${assemblyQuantity} assemblies`}>
                                  = {c.quantity * assemblyQuantity} total
                                </div>
                              )}
                            </td>
                            <td className="td !px-2"><MakeBuyBadge value={c.make_buy} /></td>
                            <td className="td !px-2">
                              {cat ? (
                                <div className="flex items-center gap-1.5">
                                  <CatalogMatchBadge catalogPartNumber={cat.part_number} />
                                  <StockAvailabilityBadge status={catalogStatus(c)} />
                                </div>
                              ) : (
                                <span className="text-xs text-steel-light">No match</span>
                              )}
                            </td>
                            <td className="td !px-2">
                              {isBellowsOrShroud(c.description) ? (
                                <>
                                  <input
                                    key={`calc:${c.id}:${formatCalcInputsText(c.calc_inputs)}`}
                                    type="text"
                                    className="input !w-40 !py-0.5 !px-1.5 !text-xs font-mono"
                                    placeholder="od=559 num_plies=1 ply_thickness_mm=0.6"
                                    defaultValue={formatCalcInputsText(c.calc_inputs)}
                                    title="Overrides for the Bellows/Shroud formula - editing recalculates automatically."
                                    onKeyDown={blurOnEnter}
                                    onBlur={(e) => {
                                      const text = e.target.value.trim();
                                      if (text !== formatCalcInputsText(c.calc_inputs)) {
                                        updateComponent(c, { calc_inputs: parseCalcInputsText(text) });
                                      }
                                    }}
                                  />
                                  {c.calc_result && (
                                    <div className="mt-1">
                                      <CalcResultBadge result={c.calc_result} />
                                      <div className="text-xs text-steel-light mt-1 whitespace-nowrap">
                                        {Object.entries(c.calc_result.final_proposed_dimensions || {})
                                          .filter(([, v]) => v !== null && v !== undefined)
                                          .map(([k, v]) => `${k}: ${v}`)
                                          .join("  ·  ")}
                                      </div>
                                    </div>
                                  )}
                                </>
                              ) : (
                                <span className="text-xs text-steel-light" title="Only Bellows/Shroud have a calculated value.">
                                  n/a
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
                {referenceBom && <ReferenceBomPanel reference={referenceBom} />}
              </>
            )}

            {tab === "bom" && (
              <>
                {bomMsg && <div className="mb-3 text-sm text-emerald-700">{bomMsg}</div>}
                {bom && activeAnalysis && bom.analysis_id !== activeAnalysis.id && (
                  // The analysis has moved on (re-run, or a newer version) since this BOM was
                  // built - e.g. after a drawing-extraction fix got a better quantity/dimension
                  // read, re-running analysis alone never touches an already-generated BOM, so
                  // without this it would keep showing stale data indefinitely with no visible
                  // sign anything was wrong. See ensureBom()'s own fix for the indent-generation
                  // side of this same staleness bug.
                  <div className="mb-3 flex items-center justify-between gap-3 border border-amber-300 bg-amber-50 rounded-industrial px-3 py-2 text-sm">
                    <span className="text-amber-800">
                      This BOM was generated from an earlier analysis. Re-run Analysis results since then aren&apos;t reflected here yet.
                    </span>
                    <button
                      className="btn-accent !py-1 !px-3 !text-xs shrink-0"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          const generated = await api.generateBom(activeAnalysis.id);
                          setBomMsg(`BOM v${generated.version} generated with ${generated.line_items.length} line items.`);
                          setBom(generated);
                          setBomTree(await api.getBomTree(generated.id));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Refresh BOM
                    </button>
                  </div>
                )}
                {bom ? (
                  <>
                    <BomPanel bom={bom} tree={bomTree} onUpdate={updateBomLineItem} />
                    <InventoryAvailabilityPanel bomId={bom.id} />
                  </>
                ) : (
                  <div className="border border-dashed border-border rounded-industrial p-6 text-sm text-steel text-center mb-4">
                    No BOM yet - one is generated automatically the moment you fill in the
                    indent details below and click &quot;Generate Indent Sheet&quot;.
                  </div>
                )}

                {showIndentForm && (
                  <div className="card p-4 mt-4">
                    <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                      <ClipboardList size={15} /> Generate Indent Sheet
                    </h3>
                    <p className="text-xs text-steel mb-3">
                      Quantities are computed deterministically: qty per assembly &times; assembly
                      quantity. Nothing here is estimated by AI.
                    </p>
                    <div className="grid grid-cols-3 gap-3">
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">Assembly Quantity *</span>
                        <input className="input" type="number" min="0" step="any" placeholder="e.g. 16"
                          value={indentForm.assembly_quantity}
                          onChange={(e) => setIndentForm({ ...indentForm, assembly_quantity: e.target.value })} />
                      </label>
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">W.O. No.</span>
                        <input className="input" placeholder="e.g. 9347" value={indentForm.wo_number}
                          onChange={(e) => setIndentForm({ ...indentForm, wo_number: e.target.value })} />
                      </label>
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">Party&apos;s Name</span>
                        <input className="input" value={indentForm.party_name}
                          onChange={(e) => setIndentForm({ ...indentForm, party_name: e.target.value })} />
                      </label>
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">Required On</span>
                        <input className="input" placeholder="e.g. 200 NB x 188 mm lg." value={indentForm.required_on}
                          onChange={(e) => setIndentForm({ ...indentForm, required_on: e.target.value })} />
                      </label>
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">SL.No.</span>
                        <input className="input" value={indentForm.serial_no}
                          onChange={(e) => setIndentForm({ ...indentForm, serial_no: e.target.value })} />
                      </label>
                      <label className="block">
                        <span className="block text-xs text-graphite mb-1">Date</span>
                        <input className="input" placeholder="DD-MM-YY" value={indentForm.indent_date}
                          onChange={(e) => setIndentForm({ ...indentForm, indent_date: e.target.value })} />
                      </label>
                    </div>
                    {indentError && (
                      <div className="mt-3 flex items-start gap-2 rounded-industrial border border-[#f3c7c5] bg-[#fde2e1] px-4 py-3 text-sm text-[#b42318]">
                        <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {indentError}
                      </div>
                    )}
                    <button className="btn-accent mt-3" disabled={indentSubmitting} onClick={submitIndent}>
                      <ClipboardList size={15} /> {indentSubmitting ? "Generating..." : "Generate"}
                    </button>

                    {generatedIndent && (
                      <div className="mt-4 border-t border-border pt-3 flex items-center justify-between gap-3">
                        <span className="text-sm text-emerald-700">
                          Indent v{generatedIndent.version} generated with {generatedIndent.lines.length} line items.
                        </span>
                        <a href={indentPdfUrl(generatedIndent.id)} target="_blank" rel="noreferrer"
                          className="flex items-center gap-1.5 text-xs border border-border rounded-industrial px-2.5 py-1.5 bg-white hover:bg-surface">
                          <Download size={12} /> Download PDF
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {activeAnalysis && (
            <div className="border-t border-border p-4 bg-white">
              <button
                className="btn-accent w-full"
                disabled={busy}
                onClick={() => {
                  setTab("bom");
                  const tb = (activeAnalysis?.title_block ?? {}) as Record<string, unknown>;
                  const drawingQty = tb.drawing_quantity;
                  const nbSize = tb.nb_size_mm;
                  const woNumber = tb.wo_number as string | undefined;
                  setIndentForm((f) => ({
                    ...f,
                    assembly_quantity: f.assembly_quantity || (drawingQty != null ? String(drawingQty) : ""),
                    required_on: f.required_on || (nbSize != null ? `${nbSize} NB` : ""),
                    wo_number: f.wo_number || woNumber || "",
                  }));
                  setShowIndentForm(true);
                }}
              >
                <ClipboardList size={15} /> Generate Indent Sheet
              </button>
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
