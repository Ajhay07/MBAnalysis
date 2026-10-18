"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, Search, Trash2, RefreshCw, Eye, MoreVertical } from "lucide-react";
import { api, Drawing } from "@/lib/api";
import DrawingThumb from "@/components/DrawingThumb";
import { DemoBadge, StatusBadge } from "@/components/Badges";

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
    <div className="px-8 pb-8 pt-2 max-w-[1200px]">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="page-title">Drawing Library</h1>
          <p className="page-subtitle">Manage and search engineering drawings.</p>
        </div>
        <button className="btn-primary !py-2.5" onClick={() => setShowUpload(true)}>
          <Plus size={16} /> Upload Drawing
        </button>
      </div>

      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onUploaded={load} setError={setError} />
      )}
      {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-3">{error}</div>}

      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-2.5 text-steel-light" />
          <input
            className="input !pl-9"
            placeholder="Search by drawing number, title or keyword..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select className="input !w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {["Uploaded", "Queued", "Processing", "NeedsReview", "Reviewed", "BOMGenerated", "Failed", "Cancelled"].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            )
          )}
        </select>
      </div>

      <div className="card">
        <table className="w-full">
          <thead className="border-b border-border bg-surface/60">
            <tr>
              <th className="th w-10">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all" />
              </th>
              <th className="th w-24">Preview</th>
              <th className="th">Title</th>
              <th className="th w-16">Rev</th>
              <th className="th w-36">Status</th>
              <th className="th w-36">Updated</th>
              <th className="th w-28 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && (
              <tr>
                <td colSpan={7} className="td text-center text-steel">Loading...</td>
              </tr>
            )}
            {!loading && drawings.length === 0 && (
              <tr>
                <td colSpan={7} className="td text-center text-steel">
                  No drawings yet. Upload one or load the demo project.
                </td>
              </tr>
            )}
            {drawings.map((d) => {
              const updated = new Date(d.updated_at);
              return (
                <tr key={d.id} className="hover:bg-surface/50">
                  <td className="td">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggleOne(d.id)}
                      aria-label={`Select ${d.drawing_number}`}
                    />
                  </td>
                  <td className="td">
                    <DrawingThumb id={d.id} fileType={d.file_type} />
                  </td>
                  <td className="td">
                    <Link href={`/drawings/${d.id}`} className="font-semibold text-graphite hover:text-brand">
                      {d.drawing_number}
                    </Link>
                    <div className="flex items-center gap-2 text-xs text-steel mt-0.5">
                      {d.title}
                      {d.is_demo && <DemoBadge />}
                    </div>
                  </td>
                  <td className="td text-steel">{d.revision}</td>
                  <td className="td">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="td text-xs text-steel leading-tight">
                    <div>{updated.toLocaleDateString("en-GB")}</div>
                    <div>{updated.toLocaleTimeString("en-GB")}</div>
                  </td>
                  <td className="td">
                    <div className="flex justify-end gap-2">
                      <Link href={`/drawings/${d.id}`} className="btn-icon" title="View">
                        <Eye size={15} />
                      </Link>
                      <div className="relative" ref={menuId === d.id ? menuRef : undefined}>
                        <button
                          className="btn-icon"
                          title="More actions"
                          onClick={() => setMenuId((m) => (m === d.id ? null : d.id))}
                        >
                          <MoreVertical size={15} />
                        </button>
                        {menuId === d.id && (
                          <div className="absolute right-0 mt-1 w-40 card py-1 z-30">
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
      <h2 className="text-base font-semibold mb-4">Upload Drawing</h2>
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
