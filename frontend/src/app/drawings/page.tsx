"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Upload, Search, Trash2, RefreshCw, Eye } from "lucide-react";
import { api, Drawing } from "@/lib/api";
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

  async function handleDelete(id: string) {
    await api.deleteDrawing(id);
    setConfirmDeleteId(null);
    load();
  }

  async function handleReprocess(id: string) {
    await api.analyzeDrawing(id);
    load();
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Drawing Library</h1>
        <button className="btn-primary" onClick={() => setShowUpload(true)}>
          <Upload size={16} /> Upload Drawing
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
            className="w-full pl-9 pr-3 py-2 border border-border rounded-industrial text-sm"
            placeholder="Search by drawing number or title..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select
          className="border border-border rounded-industrial text-sm px-3 py-2"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
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

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface text-steel text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2.5">Drawing #</th>
              <th className="text-left px-4 py-2.5">Title</th>
              <th className="text-left px-4 py-2.5">Rev</th>
              <th className="text-left px-4 py-2.5">Status</th>
              <th className="text-left px-4 py-2.5">Updated</th>
              <th className="text-right px-4 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-steel">
                  Loading...
                </td>
              </tr>
            )}
            {!loading && drawings.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-steel">
                  No drawings yet. Upload one or load the demo project.
                </td>
              </tr>
            )}
            {drawings.map((d) => (
              <tr key={d.id} className="hover:bg-surface/60">
                <td className="px-4 py-2.5 font-mono text-xs">{d.drawing_number}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    {d.title}
                    {d.is_demo && <DemoBadge />}
                  </div>
                </td>
                <td className="px-4 py-2.5">{d.revision}</td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={d.status} />
                </td>
                <td className="px-4 py-2.5 text-steel-light text-xs">
                  {new Date(d.updated_at).toLocaleString()}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-2">
                    <Link href={`/drawings/${d.id}`} className="btn-secondary !px-2 !py-1" title="View">
                      <Eye size={14} />
                    </Link>
                    <button
                      className="btn-secondary !px-2 !py-1"
                      title="Reprocess"
                      onClick={() => handleReprocess(d.id)}
                    >
                      <RefreshCw size={14} />
                    </button>
                    <button
                      className="btn-secondary !px-2 !py-1 hover:!bg-red-50 hover:!text-red-700"
                      title="Delete"
                      onClick={() => setConfirmDeleteId(d.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
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
      <h2 className="text-sm font-semibold mb-3">Upload Drawing</h2>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs text-steel mb-1">Drawing Number *</label>
          <input
            className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
            value={drawingNumber}
            onChange={(e) => setDrawingNumber(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-steel mb-1">Title</label>
          <input
            className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-steel mb-1">Revision</label>
          <input
            className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-steel mb-1">File (PDF, PNG, JPG, TIFF) *</label>
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full text-sm"
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
