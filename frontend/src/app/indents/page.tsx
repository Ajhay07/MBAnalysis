"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, ClipboardList, PlusCircle, Download, AlertTriangle } from "lucide-react";
import { api, Bom, Drawing, Indent } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import PageLayout, { AsideSection, AsideItem, SectionCard } from "@/components/PageLayout";

function IndentStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Draft: "bg-[#e3e7ee] text-navy",
    Approved: "bg-[#dcf3e6] text-[#14804a]",
    Rejected: "bg-[#fde2e1] text-[#b42318]",
  };
  return (
    <span className={`text-[12px] font-semibold px-2.5 py-0.5 rounded-full ${map[status] || "bg-surface text-steel"}`}>
      {status}
    </span>
  );
}

export default function IndentsPage() {
  const { user } = useAuth();
  const canGenerate = user?.role === "admin" || user?.role === "engineer";

  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selectedDrawing, setSelectedDrawing] = useState<string>("");
  const [boms, setBoms] = useState<Bom[]>([]);
  const [selectedBom, setSelectedBom] = useState<string>("");
  const [indents, setIndents] = useState<Indent[]>([]);
  const [loadingIndents, setLoadingIndents] = useState(false);
  const [indentsError, setIndentsError] = useState<string | null>(null);

  const [form, setForm] = useState({
    assembly_quantity: "", wo_number: "", party_name: "", required_on: "", serial_no: "", indent_date: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    api.listDrawings().then((ds) => {
      setDrawings(ds);
      const withBom = ds.find((d) => d.status === "BOMGenerated" || d.status === "Reviewed");
      if (withBom) setSelectedDrawing(withBom.id);
    });
  }, []);

  useEffect(() => {
    if (!selectedDrawing) {
      setBoms([]);
      setSelectedBom("");
      return;
    }
    api.listBomsForDrawing(selectedDrawing).then((bs) => {
      setBoms(bs);
      setSelectedBom(bs[0]?.id || "");
    });
  }, [selectedDrawing]);

  const refreshIndents = (bomId: string) => {
    setLoadingIndents(true);
    setIndentsError(null);
    api
      .listIndentsForBom(bomId)
      .then(setIndents)
      .catch((e) => setIndentsError(e.message || "Failed to load indents"))
      .finally(() => setLoadingIndents(false));
  };

  useEffect(() => {
    if (selectedBom) refreshIndents(selectedBom);
    else setIndents([]);
  }, [selectedBom]);

  const selectedDrawingObj = drawings.find((d) => d.id === selectedDrawing);
  const selectedBomObj = boms.find((b) => b.id === selectedBom);

  const submit = async () => {
    if (!selectedBom) return;
    const qty = parseFloat(form.assembly_quantity);
    if (!qty || qty <= 0) {
      setSubmitError("Assembly quantity must be a positive number.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.generateIndent(selectedBom, {
        assembly_quantity: qty,
        wo_number: form.wo_number.trim(),
        party_name: form.party_name.trim(),
        required_on: form.required_on.trim(),
        serial_no: form.serial_no.trim(),
        indent_date: form.indent_date.trim(),
      });
      setForm({ assembly_quantity: "", wo_number: "", party_name: "", required_on: "", serial_no: "", indent_date: "" });
      refreshIndents(selectedBom);
    } catch (e: any) {
      setSubmitError(e.message || "Failed to generate indent.");
    } finally {
      setSubmitting(false);
    }
  };

  const aside = (
    <AsideSection title="Drawings">
      <div className="space-y-1">
        {drawings.map((d) => (
          <AsideItem
            key={d.id}
            icon={FileText}
            label={d.drawing_number}
            count={d.revision ? `Rev ${d.revision}` : undefined}
            active={d.id === selectedDrawing}
            onClick={() => setSelectedDrawing(d.id)}
          />
        ))}
        {drawings.length === 0 && <p className="px-3 text-sm text-steel">No drawings yet.</p>}
      </div>
    </AsideSection>
  );

  return (
    <PageLayout
      aside={aside}
      title="Indent Sheets"
      subtitle={selectedDrawingObj ? `${selectedDrawingObj.drawing_number} · ${selectedDrawingObj.title}` : "Generate and review MB Metallic Bellows indent sheets."}
    >
      <SectionCard
        tone="blue"
        index="01"
        title="Select BOM"
        description="Pick the drawing's BOM this indent sheet will be generated from."
      >
        <div className="p-5 flex items-end gap-4">
          <label className="block flex-1">
            <span className="block text-[14px] text-graphite mb-1.5">BOM version</span>
            <select className="input" value={selectedBom} onChange={(e) => setSelectedBom(e.target.value)}>
              {boms.length === 0 && <option value="">No BOM generated for this drawing yet</option>}
              {boms.map((b) => (
                <option key={b.id} value={b.id}>
                  v{b.version} · {b.status} · {b.line_items.length} line items
                </option>
              ))}
            </select>
          </label>
        </div>
      </SectionCard>

      {!selectedBom && (
        <div className="card p-6 text-steel text-sm mb-7">
          Select a drawing with a generated BOM to continue. BOMs are created from the drawing&apos;s
          Review Center after analysis.
        </div>
      )}

      {selectedBom && canGenerate && (
        <SectionCard
          tone="orange"
          index="02"
          title="Generate Indent"
          description="Quantities are computed deterministically: qty per assembly × assembly quantity. Nothing here is estimated by AI."
        >
          <div className="p-5 grid grid-cols-3 gap-4">
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">Assembly Quantity *</span>
              <input className="input" type="number" min="0" step="any" placeholder="e.g. 16"
                value={form.assembly_quantity}
                onChange={(e) => setForm({ ...form, assembly_quantity: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">W.O. No.</span>
              <input className="input" placeholder="e.g. 9347" value={form.wo_number}
                onChange={(e) => setForm({ ...form, wo_number: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">Party&apos;s Name</span>
              <input className="input" value={form.party_name}
                onChange={(e) => setForm({ ...form, party_name: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">Required On</span>
              <input className="input" placeholder="e.g. 200 NB x 188 mm lg." value={form.required_on}
                onChange={(e) => setForm({ ...form, required_on: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">SL.No.</span>
              <input className="input" value={form.serial_no}
                onChange={(e) => setForm({ ...form, serial_no: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-[14px] text-graphite mb-1.5">Date</span>
              <input className="input" placeholder="DD-MM-YY" value={form.indent_date}
                onChange={(e) => setForm({ ...form, indent_date: e.target.value })} />
            </label>
          </div>
          {submitError && (
            <div className="mx-5 mb-4 flex items-start gap-2 rounded-industrial border border-[#f3c7c5] bg-[#fde2e1] px-4 py-3 text-sm text-[#b42318]">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {submitError}
            </div>
          )}
          <div className="px-5 pb-5">
            <button className="btn-primary flex items-center gap-2" onClick={submit} disabled={submitting}>
              <PlusCircle size={16} /> {submitting ? "Generating…" : "Generate Indent"}
            </button>
          </div>
        </SectionCard>
      )}

      {selectedBom && (
        <SectionCard
          tone="navy"
          index={canGenerate ? "03" : "02"}
          title="Generated Indents"
          count={indents.length}
          description={`BOM v${selectedBomObj?.version ?? "—"} — every regeneration creates a new version; nothing is overwritten.`}
        >
          {loadingIndents && <div className="p-5 text-steel text-sm">Loading…</div>}
          {indentsError && (
            <div className="m-5 flex items-start gap-2 rounded-industrial border border-[#f3c7c5] bg-[#fde2e1] px-4 py-3 text-sm text-[#b42318]">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {indentsError}
            </div>
          )}
          {!loadingIndents && !indentsError && (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">Version</th>
                  <th className="th">W.O. No.</th>
                  <th className="th">Party</th>
                  <th className="th text-right">Assembly Qty</th>
                  <th className="th">Status</th>
                  <th className="th">Created</th>
                  <th className="th text-right w-32">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {indents.map((ind) => (
                  <tr key={ind.id}>
                    <td className="td font-medium">v{ind.version}</td>
                    <td className="td">{ind.wo_number || "—"}</td>
                    <td className="td">{ind.party_name || "—"}</td>
                    <td className="td text-right">{ind.assembly_quantity}</td>
                    <td className="td"><IndentStatusBadge status={ind.status} /></td>
                    <td className="td text-steel text-xs">{new Date(ind.created_at).toLocaleString()}</td>
                    <td className="td">
                      <div className="flex justify-end gap-1.5">
                        <Link href={`/indents/${ind.id}`} className="btn-icon" title="View indent">
                          <ClipboardList size={14} />
                        </Link>
                        <a href={`/api/indents/${ind.id}/pdf`} className="btn-icon" title="Download PDF">
                          <Download size={14} />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
                {indents.length === 0 && (
                  <tr><td colSpan={7} className="td text-steel">No indents generated for this BOM yet.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </SectionCard>
      )}
    </PageLayout>
  );
}
