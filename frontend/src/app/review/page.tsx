"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { MakeBuyBadge } from "@/components/Badges";

export default function ReviewPage() {
  const [queue, setQueue] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const [q, a] = await Promise.all([api.reviewQueue(), api.auditTrail()]);
    setQueue(q);
    setAudit(a);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Review &amp; Approval Center</h1>

      <div className="card p-5 mb-6">
        <h2 className="text-sm font-semibold mb-3">
          Low-Confidence / Ambiguous Queue {!loading && `(${queue.length})`}
        </h2>
        {loading && <div className="text-sm text-steel">Loading...</div>}
        {!loading && queue.length === 0 && (
          <div className="text-sm text-steel">Nothing pending review.</div>
        )}
        <div className="divide-y divide-border">
          {queue.map((item) => (
            <div key={item.component_id} className="py-3 flex items-center justify-between text-sm">
              <div>
                <div className="font-mono text-xs text-steel">{item.drawing_number}</div>
                <div className="font-medium">{item.description || item.part_number}</div>
              </div>
              <div className="flex items-center gap-3">
                <MakeBuyBadge value={item.make_buy} />
                <span className="text-xs text-steel-light">{(item.confidence * 100).toFixed(0)}%</span>
                <Link href={`/drawings/${item.drawing_id}`} className="btn-secondary !px-2 !py-1 text-xs">
                  Review
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold mb-3">Audit Trail</h2>
        <table className="w-full text-sm">
          <thead className="text-xs text-steel uppercase">
            <tr>
              <th className="text-left py-1">Entity</th>
              <th className="text-left py-1">Action</th>
              <th className="text-left py-1">When</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {audit.map((a) => (
              <tr key={a.id}>
                <td className="py-1.5">
                  {a.entity_type} <span className="text-steel-light font-mono text-xs">{a.entity_id.slice(0, 8)}</span>
                </td>
                <td className="py-1.5">{a.action}</td>
                <td className="py-1.5 text-steel-light text-xs">{new Date(a.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
