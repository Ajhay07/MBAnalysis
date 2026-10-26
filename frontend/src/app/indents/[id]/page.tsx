"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Download, Check, X, AlertTriangle } from "lucide-react";
import { api, Indent, indentPdfUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import PageLayout, { SectionCard } from "@/components/PageLayout";

function IndentStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Draft: "bg-[#e3e7ee] text-navy",
    Approved: "bg-[#dcf3e6] text-[#14804a]",
    Rejected: "bg-[#fde2e1] text-[#b42318]",
  };
  return (
    <span className={`text-[13px] font-semibold px-3 py-1 rounded-full ${map[status] || "bg-surface text-steel"}`}>
      {status}
    </span>
  );
}

export default function IndentDetailPage() {
  const params = useParams();
  const id = String(params.id);
  const { user } = useAuth();
  const canApprove = user?.role === "admin" || user?.role === "engineer";

  const [indent, setIndent] = useState<Indent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .getIndent(id)
      .then(setIndent)
      .catch((e) => setError(e.message || "Failed to load indent"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const act = async (action: "approve" | "reject") => {
    setActing(true);
    setActionError(null);
    try {
      const updated = action === "approve" ? await api.approveIndent(id) : await api.rejectIndent(id);
      setIndent(updated);
    } catch (e: any) {
      setActionError(e.message || `Failed to ${action} indent.`);
    } finally {
      setActing(false);
    }
  };

  const aside = (
    <div className="px-3">
      <Link href="/indents" className="flex items-center gap-2 text-sm text-graphite hover:text-accent">
        <ArrowLeft size={16} /> Back to Indent Sheets
      </Link>
    </div>
  );

  if (loading) {
    return (
      <PageLayout aside={aside} title="Indent Sheet">
        <div className="card p-6 text-steel text-sm">Loading…</div>
      </PageLayout>
    );
  }

  if (error || !indent) {
    return (
      <PageLayout aside={aside} title="Indent Sheet">
        <div className="card p-6 flex items-start gap-2 text-sm text-[#b42318]">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {error || "Indent not found."}
        </div>
      </PageLayout>
    );
  }

  const anyUnconfirmed = indent.lines.some((l) => l.requires_confirmation);

  return (
    <PageLayout
      aside={aside}
      title={`Indent Sheet — W.O. ${indent.wo_number || "—"}`}
      subtitle={`Version ${indent.version} · BOM ${indent.bom_id.slice(0, 8)}…`}
    >
      <SectionCard
        tone="blue"
        index="01"
        title="Indent Details"
        right={<IndentStatusBadge status={indent.status} />}
      >
        <dl className="grid grid-cols-3 gap-x-8 gap-y-4 p-5 text-sm">
          <div><dt className="text-steel">W.O. No.</dt><dd className="font-medium">{indent.wo_number || "—"}</dd></div>
          <div><dt className="text-steel">Date</dt><dd className="font-medium">{indent.indent_date || "—"}</dd></div>
          <div><dt className="text-steel">SL.No.</dt><dd className="font-medium">{indent.serial_no || "—"}</dd></div>
          <div><dt className="text-steel">Party&apos;s Name</dt><dd className="font-medium">{indent.party_name || "—"}</dd></div>
          <div><dt className="text-steel">Required On</dt><dd className="font-medium">{indent.required_on || "—"}</dd></div>
          <div><dt className="text-steel">Assembly Quantity</dt><dd className="font-medium">{indent.assembly_quantity}</dd></div>
          <div><dt className="text-steel">Created</dt><dd className="font-medium">{new Date(indent.created_at).toLocaleString()}</dd></div>
          {indent.approved_by && (
            <div><dt className="text-steel">Approved by</dt><dd className="font-medium">{indent.approved_by}</dd></div>
          )}
        </dl>
        <div className="px-5 pb-5 flex flex-wrap items-center gap-3">
          <a href={indentPdfUrl(indent.id)} className="btn-primary flex items-center gap-2">
            <Download size={16} /> Download PDF
          </a>
          {canApprove && indent.status === "Draft" && (
            <>
              <button className="btn-secondary flex items-center gap-2" onClick={() => act("approve")} disabled={acting}>
                <Check size={16} /> Approve
              </button>
              <button
                className="flex items-center gap-2 border-2 border-[#b42318] text-[#b42318] rounded-md px-4 py-2 text-sm font-semibold hover:bg-[#fde2e1] disabled:opacity-50"
                onClick={() => act("reject")} disabled={acting}
              >
                <X size={16} /> Reject
              </button>
            </>
          )}
        </div>
        {actionError && (
          <div className="mx-5 mb-5 flex items-start gap-2 rounded-industrial border border-[#f3c7c5] bg-[#fde2e1] px-4 py-3 text-sm text-[#b42318]">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {actionError}
          </div>
        )}
      </SectionCard>

      {anyUnconfirmed && (
        <div className="mb-7 flex items-start gap-2 rounded-industrial border border-[#f3c7c5] bg-[#fff3e0] px-4 py-3 text-sm text-[#b7791f]">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          One or more rows below have no approved quantity yet (shown as TBD) — confirm these before this
          indent is issued for procurement.
        </div>
      )}

      <SectionCard tone="navy" index="02" title="Line Items" count={indent.lines.length}>
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Sl.No.</th>
              <th className="th">MTL SPEC</th>
              <th className="th">SIZE</th>
              <th className="th text-right">WT/QTY</th>
              <th className="th">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {indent.lines.map((line) => (
              <tr key={line.id} className={line.requires_confirmation ? "bg-[#fff3e0]" : undefined}>
                <td className="td font-medium">{line.sl_no}</td>
                <td className="td whitespace-pre-line">{line.mtl_spec || "—"}</td>
                <td className="td">{line.size_text || "—"}</td>
                <td className="td text-right">
                  {line.requires_confirmation ? (
                    <span className="font-semibold text-[#b7791f]">TBD</span>
                  ) : (
                    `${line.wt_qty ?? "—"} ${line.unit}`
                  )}
                </td>
                <td className="td text-steel text-xs">
                  {line.source === "bom_line" ? "BOM line" : line.source === "rule" ? "Indent rule" : "Manual"}
                  {line.note && <div className="text-[#b7791f] mt-0.5">{line.note}</div>}
                </td>
              </tr>
            ))}
            {indent.lines.length === 0 && (
              <tr><td colSpan={5} className="td text-steel">No line items on this indent.</td></tr>
            )}
          </tbody>
        </table>
      </SectionCard>
    </PageLayout>
  );
}
