"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, Search, Trash2, RefreshCw, Eye, MoreVertical } from "lucide-react";
import { api, Drawing } from "@/lib/api";
import DrawingThumb from "@/components/DrawingThumb";
import { StatusBadge } from "@/components/Badges";
import PageHeader from "@/components/PageHeader";

const STATUS_OPTIONS: [string, string][] = [
  ["Uploaded", "Uploaded"], ["Queued", "Queued"], ["Processing", "Processing"], ["NeedsReview", "Analyzed"],
  ["Reviewed", "Reviewed"], ["BOMGenerated", "BOM Generated"], ["Failed", "Failed"], ["Cancelled", "Cancelled"],
];

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
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(searchParams.get("upload") === "1");
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [menuId, setMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listDrawings({ q: q || undefined, status: status || undefined });
      setDrawings(data);
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

  const allSelected = drawings.length > 0 && drawings.every((d) => selected.has(d.id));
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(drawings.map((d) => d.id)));
  }
  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="px-8 pb-10">
      <PageHeader
        breadcrumb={[{ label: "Drawings" }]}
        title="Drawing Library"
        subtitle="Manage and search engineering drawings."
        actions={
          <button className="btn-primary !px-6 !py-3 !text-base" onClick={() => setShowUpload(true)}>
            <Plus size={19} /> Upload Drawing
          </button>
        }
      />

      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onUploaded={load} setError={setError} />
      )}
      {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3">{error}</div>}

      <div className="flex gap-4 mb-5">
        <div className="relative flex-1">
          <Search size={20} className="absolute left-4 top-1/2 -translate-y-1/2 text-graphite/70" />
          <input
            className="input !h-14 !pl-14 !text-[15px]"
            placeholder="Search by drawing number, title, or keyword..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select className="input !h-14 !w-60" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="card overflow-visible">
        <table className="w-full">
          <thead className="border-b border-border">
            <tr>
              <th className="th w-14 !pl-5 rounded-tl-industrial">
                <input type="checkbox" className="w-[18px] h-[18px] align-middle" checked={allSelected} onChange={toggleAll} aria-label="Select all" />
              </th>
              <th className="th w-40">Preview</th>
              <th className="th w-40">Drawing #</th>
              <th className="th">Title</th>
              <th className="th w-20">Rev</th>
              <th className="th w-40">Status</th>
              <th className="th w-52">Updated</th>
              <th className="th w-36 rounded-tr-industrial">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && (
              <tr>
                <td colSpan={8} className="td text-center text-steel">Loading...</td>
              </tr>
            )}
            {!loading && drawings.length === 0 && (
              <tr>
                <td colSpan={8} className="td text-center text-steel">
                  No drawings yet. Upload one or load the demo project.
                </td>
              </tr>
            )}
            {drawings.map((d) => {
              const updated = new Date(d.updated_at);
              return (
                <tr key={d.id} className="hover:bg-surface/40">
                  <td className="td !pl-5">
                    <input
                      type="checkbox"
                      className="w-[18px] h-[18px] align-middle"
                      checked={selected.has(d.id)}
                      onChange={() => toggleOne(d.id)}
                      aria-label={`Select ${d.drawing_number}`}
                    />
                  </td>
                  <td className="td">
                    <DrawingThumb id={d.id} fileType={d.file_type} className="w-[112px] h-[84px] p-0.5" />
                  </td>
                  <td className="td">
                    <Link href={`/drawings/${d.id}`} className="text-[17px] font-bold text-graphite hover:text-brand">
                      {d.drawing_number}
                    </Link>
                  </td>
                  <td className="td text-[16px] text-graphite">{d.title}</td>
                  <td className="td text-[16px] text-graphite">{d.revision}</td>
                  <td className="td">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="td text-[16px] text-steel whitespace-nowrap">
                    {updated.toLocaleDateString("en-GB")}, {updated.toLocaleTimeString("en-GB")}
                  </td>
                  <td className="td">
                    <div className="flex gap-3">
                      <Link href={`/drawings/${d.id}`} className="btn-icon !w-12 !h-12 !text-graphite" title="View">
                        <Eye size={21} />
                      </Link>
                      <div className="relative" ref={menuId === d.id ? menuRef : undefined}>
                        <button
                          className="btn-icon !w-12 !h-12 !text-graphite"
                          title="More actions"
                          onClick={() => setMenuId((m) => (m === d.id ? null : d.id))}
                        >
                          <MoreVertical size={21} />
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
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

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
              <button
                className="btn-primary !bg-red-600 hover:!bg-red-700"
                onClick={() => handleDelete(confirmDeleteId)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
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
      <h2 className="text-lg font-bold mb-4">Upload Drawing</h2>
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
