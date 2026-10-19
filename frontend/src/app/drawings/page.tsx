"use client";

import { useEffect, useMemo, useState, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Plus, Search, Trash2, RefreshCw, Eye, MoreVertical, LayoutGrid, List,
  FolderOpen, Boxes, Layers, CornerDownRight, Cylinder, MoveHorizontal, Shapes,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api, Drawing } from "@/lib/api";
import { StatusBadge } from "@/components/Badges";
import DrawingThumb from "@/components/DrawingThumb";
import PageLayout, { AsideSection, AsideItem, AsideSelect, ClearFiltersButton } from "@/components/PageLayout";
import { drawingCategory, STATUS_OPTIONS } from "@/lib/categories";

const CATEGORY_NAV: { key: string; label: string; icon: LucideIcon }[] = [
  { key: "assemblies", label: "Assemblies", icon: Boxes },
  { key: "bellows", label: "Bellows", icon: Layers },
  { key: "brackets", label: "Brackets", icon: CornerDownRight },
  { key: "shafts", label: "Shafts", icon: Cylinder },
  { key: "expansion", label: "Expansion Joints", icon: MoveHorizontal },
  { key: "other", label: "Other", icon: Shapes },
];

const SORTS: [string, string][] = [
  ["updated_desc", "Updated (Latest)"],
  ["updated_asc", "Updated (Oldest)"],
  ["number_asc", "Drawing # (A–Z)"],
  ["title_asc", "Title (A–Z)"],
];

function fmtUpdated(iso: string) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB")}, ${d.toLocaleTimeString("en-GB")}`;
}

export default function DrawingsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-steel">Loading...</div>}>
      <DrawingsPageInner />
    </Suspense>
  );
}

function DrawingsPageInner() {
  const searchParams = useSearchParams();
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [componentTypes, setComponentTypes] = useState<Record<string, Set<string>>>({});
  const [q, setQ] = useState("");
  const [status, setStatus] = useState(searchParams.get("status") || "");
  const [category, setCategory] = useState(searchParams.get("category") || "all");
  const [revision, setRevision] = useState("");
  const [componentType, setComponentType] = useState("");
  const [sort, setSort] = useState("updated_desc");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(searchParams.get("upload") === "1");
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, comps] = await Promise.all([
        api.listDrawings({ q: q || undefined, status: status || undefined }),
        api.reviewComponents(),
      ]);
      setDrawings(data);
      const byDrawing: Record<string, Set<string>> = {};
      for (const c of comps) {
        if (!c.category) continue;
        (byDrawing[c.drawing_id] ||= new Set()).add(c.category);
      }
      setComponentTypes(byDrawing);
    } finally {
      setLoading(false);
    }
  }, [q, status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!menuId) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuId(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuId]);

  async function handleDelete(id: string) {
    await api.deleteDrawing(id);
    setConfirmDeleteId(null);
    load();
  }

  async function handleReprocess(id: string) {
    setMenuId(null);
    await api.analyzeDrawing(id);
    load();
  }

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of drawings) {
      const k = drawingCategory(d.title);
      counts[k] = (counts[k] || 0) + 1;
    }
    return counts;
  }, [drawings]);

  const revisions = useMemo(() => Array.from(new Set(drawings.map((d) => d.revision))).sort(), [drawings]);
  const allTypes = useMemo(
    () => Array.from(new Set(Object.values(componentTypes).flatMap((s) => Array.from(s)))).sort(),
    [componentTypes],
  );

  const visible = useMemo(() => {
    const rows = drawings.filter(
      (d) =>
        (category === "all" || drawingCategory(d.title) === category) &&
        (!revision || d.revision === revision) &&
        (!componentType || componentTypes[d.id]?.has(componentType)),
    );
    const by: Record<string, (a: Drawing, b: Drawing) => number> = {
      updated_desc: (a, b) => b.updated_at.localeCompare(a.updated_at),
      updated_asc: (a, b) => a.updated_at.localeCompare(b.updated_at),
      number_asc: (a, b) => a.drawing_number.localeCompare(b.drawing_number),
      title_asc: (a, b) => a.title.localeCompare(b.title),
    };
    return [...rows].sort(by[sort]);
  }, [drawings, category, revision, componentType, componentTypes, sort]);

  function clearFilters() {
    setStatus("");
    setCategory("all");
    setRevision("");
    setComponentType("");
    setQ("");
  }

  function RowMenu({ d }: { d: Drawing }) {
    return (
      <div className="relative" ref={menuId === d.id ? menuRef : undefined}>
        <button
          className="btn-icon !w-10 !h-10 !text-graphite"
          title="More actions"
          onClick={() => setMenuId((m) => (m === d.id ? null : d.id))}
        >
          <MoreVertical size={19} />
        </button>
        {menuId === d.id && (
          <div className="absolute right-0 mt-1 w-44 card py-1 z-30">
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-steel hover:bg-surface hover:text-graphite"
              onClick={() => handleReprocess(d.id)}
            >
              <RefreshCw size={14} /> Reprocess
            </button>
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
              onClick={() => {
                setMenuId(null);
                setConfirmDeleteId(d.id);
              }}
            >
              <Trash2 size={14} /> Delete
            </button>
          </div>
        )}
      </div>
    );
  }

  const aside = (
    <>
      <AsideSection title="Categories">
        <div className="space-y-1">
          <AsideItem icon={FolderOpen} label="All Drawings" count={drawings.length} active={category === "all"} onClick={() => setCategory("all")} />
          {CATEGORY_NAV.filter((c) => c.key !== "other" || categoryCounts.other).map((c) => (
            <AsideItem
              key={c.key}
              icon={c.icon}
              label={c.label}
              count={categoryCounts[c.key] || 0}
              active={category === c.key}
              onClick={() => setCategory(c.key)}
            />
          ))}
        </div>
      </AsideSection>
      <div className="mx-3 border-t border-border" />
      <AsideSection title="Filters">
        <AsideSelect label="Status" value={status} onChange={setStatus} options={STATUS_OPTIONS} />
        <AsideSelect
          label="Revision"
          value={revision}
          onChange={setRevision}
          options={[["", "All revisions"], ...revisions.map((r): [string, string] => [r, `Rev ${r}`])]}
        />
        <AsideSelect
          label="Component Type"
          value={componentType}
          onChange={setComponentType}
          options={[["", "All types"], ...allTypes.map((t): [string, string] => [t, t])]}
        />
        <ClearFiltersButton onClick={clearFilters} />
      </AsideSection>
    </>
  );

  return (
    <PageLayout aside={aside} title="Drawing Library" subtitle="Manage and search engineering drawings.">
      <div className="flex gap-4 mb-4">
        <div className="relative flex-1">
          <Search size={19} className="absolute left-4 top-1/2 -translate-y-1/2 text-graphite/70" />
          <input
            className="input !h-12 !pl-12"
            placeholder="Search by drawing number, title, or keyword..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select className="input !h-12 !w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUS_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <div className="flex h-12 border border-border rounded-industrial overflow-hidden bg-white">
          <button
            className={`w-14 flex items-center justify-center ${view === "grid" ? "bg-[#e3e7ed] text-graphite" : "text-steel hover:bg-surface"}`}
            onClick={() => setView("grid")}
            title="Grid view"
          >
            <LayoutGrid size={20} />
          </button>
          <button
            className={`w-14 flex items-center justify-center border-l border-border ${view === "list" ? "bg-[#e3e7ed] text-graphite" : "text-steel hover:bg-surface"}`}
            onClick={() => setView("list")}
            title="List view"
          >
            <List size={20} />
          </button>
        </div>
        <button className="btn-cta !h-12" onClick={() => setShowUpload(true)}>
          <Plus size={19} /> Upload Drawing
        </button>
      </div>

      {showUpload && <UploadPanel onClose={() => setShowUpload(false)} onUploaded={load} setError={setError} />}
      {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3">{error}</div>}

      <div className="flex items-center justify-between bg-[#e9edf2] rounded-industrial px-4 py-2.5 mb-4">
        <span className="text-[15px] text-graphite">
          {loading ? "Loading..." : `${visible.length} drawing${visible.length === 1 ? "" : "s"} found`}
        </span>
        <label className="flex items-center gap-3 text-[15px] text-graphite">
          Sort by
          <select className="input !w-52 !py-1.5" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
      </div>

      {!loading && visible.length === 0 && (
        <div className="card p-10 text-center text-steel">No drawings match. Clear filters or upload a drawing.</div>
      )}

      {view === "grid" ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
          {visible.map((d) => (
            <div key={d.id} className="card p-4 hover:shadow-md transition-shadow">
              <Link href={`/drawings/${d.id}`} className="block">
                <DrawingThumb id={d.id} fileType={d.file_type} className="w-full h-[150px] p-1" />
              </Link>
              <div className="flex items-center justify-between gap-2 mt-3">
                <Link href={`/drawings/${d.id}`} className="text-[18px] font-bold text-navy hover:text-accent">
                  {d.drawing_number}
                </Link>
                <StatusBadge status={d.status} />
              </div>
              <div className="text-[15px] text-graphite/90 mt-1 truncate" title={d.title}>{d.title}</div>
              <div className="flex items-center justify-between mt-3">
                <span className="text-[14px] text-steel">
                  Rev <span className="text-graphite">{d.revision}</span>
                  <span className="mx-2.5 text-border">|</span>
                  {fmtUpdated(d.updated_at)}
                </span>
                <div className="flex gap-2">
                  <Link href={`/drawings/${d.id}`} className="btn-icon !w-10 !h-10 !text-graphite" title="View">
                    <Eye size={19} />
                  </Link>
                  <RowMenu d={d} />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card">
          <table className="w-full">
            <thead className="border-b border-border">
              <tr>
                <th className="th w-36 rounded-tl-industrial">Preview</th>
                <th className="th w-36">Drawing #</th>
                <th className="th">Title</th>
                <th className="th w-20">Rev</th>
                <th className="th w-40">Status</th>
                <th className="th w-52">Updated</th>
                <th className="th w-32 rounded-tr-industrial">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visible.map((d) => (
                <tr key={d.id} className="hover:bg-surface/40">
                  <td className="td"><DrawingThumb id={d.id} fileType={d.file_type} className="w-[104px] h-[72px] p-0.5" /></td>
                  <td className="td">
                    <Link href={`/drawings/${d.id}`} className="text-[16px] font-bold text-navy hover:text-accent">{d.drawing_number}</Link>
                  </td>
                  <td className="td">{d.title}</td>
                  <td className="td">{d.revision}</td>
                  <td className="td"><StatusBadge status={d.status} /></td>
                  <td className="td text-steel whitespace-nowrap">{fmtUpdated(d.updated_at)}</td>
                  <td className="td">
                    <div className="flex gap-2">
                      <Link href={`/drawings/${d.id}`} className="btn-icon !w-10 !h-10 !text-graphite" title="View">
                        <Eye size={19} />
                      </Link>
                      <RowMenu d={d} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="card bg-white p-6 w-96">
            <h3 className="font-semibold mb-2">Delete drawing?</h3>
            <p className="text-sm text-steel mb-4">
              This permanently removes the drawing, its analyses, and associated BOMs.
            </p>
            <div className="flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setConfirmDeleteId(null)}>
                Cancel
              </button>
              <button className="btn-primary !bg-red-600 hover:!bg-red-700" onClick={() => handleDelete(confirmDeleteId)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}

function UploadPanel({
  onClose,
  onUploaded,
  setError,
}: {
  onClose: () => void;
  onUploaded: () => void;
  setError: (s: string | null) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [drawingNumber, setDrawingNumber] = useState("");
  const [title, setTitle] = useState("");
  const [revision, setRevision] = useState("A");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!file || !drawingNumber) {
      setError("Drawing number and file are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("drawing_number", drawingNumber);
      form.append("title", title);
      form.append("revision", revision);
      await api.uploadDrawing(form);
      onUploaded();
      onClose();
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card p-5 mb-6">
      <h2 className="section-title mb-4">Upload Drawing</h2>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs font-medium text-steel mb-1">Drawing Number *</label>
          <input className="input" value={drawingNumber} onChange={(e) => setDrawingNumber(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs font-medium text-steel mb-1">Title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs font-medium text-steel mb-1">Revision</label>
          <input className="input" value={revision} onChange={(e) => setRevision(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs font-medium text-steel mb-1">File (PDF, PNG, JPG, TIFF) *</label>
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full text-sm file:mr-3 file:btn-secondary file:!py-1.5"
          />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button className="btn-primary" disabled={submitting} onClick={submit}>
          {submitting ? "Uploading..." : "Upload"}
        </button>
      </div>
    </div>
  );
}
