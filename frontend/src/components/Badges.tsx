"use client";

import { useState } from "react";

export function DemoBadge() {
  return <span className="badge-demo">Demo Data</span>;
}

const STATUS_STYLES: Record<string, string> = {
  Uploaded: "bg-steel-light/20 text-steel",
  Queued: "bg-blue-100 text-blue-700",
  Processing: "bg-blue-100 text-blue-700",
  NeedsReview: "bg-amber-100 text-amber-800",
  Reviewed: "bg-emerald-100 text-emerald-800",
  BOMGenerated: "bg-emerald-100 text-emerald-800",
  Failed: "bg-red-100 text-red-700",
  Cancelled: "bg-gray-100 text-gray-600",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

const MAKEBUY_STYLES: Record<string, string> = {
  Make: "bg-graphite/10 text-graphite",
  Buy: "bg-accent-light text-accent-dark",
  Review: "bg-amber-100 text-amber-800",
};

export function MakeBuyBadge({ value }: { value: string }) {
  const cls = MAKEBUY_STYLES[value] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {value}
    </span>
  );
}

const AVAILABILITY_STYLES: Record<string, string> = {
  AVAILABLE: "bg-emerald-100 text-emerald-800",
  PARTIALLY_AVAILABLE: "bg-amber-100 text-amber-800",
  OUT_OF_STOCK: "bg-red-100 text-red-700",
  REVIEW_REQUIRED: "bg-blue-100 text-blue-700",
};

const AVAILABILITY_LABELS: Record<string, string> = {
  AVAILABLE: "Available",
  PARTIALLY_AVAILABLE: "Partial",
  OUT_OF_STOCK: "Out of Stock",
  REVIEW_REQUIRED: "Review Required",
};

export function AvailabilityBadge({ status }: { status: string }) {
  const cls = AVAILABILITY_STYLES[status] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {AVAILABILITY_LABELS[status] || status}
    </span>
  );
}

const QUANTITY_BASIS_STYLES: Record<string, string> = {
  explicit_callout: "bg-emerald-100 text-emerald-800",
  counted_feature: "bg-blue-100 text-blue-700",
  assumed: "bg-amber-100 text-amber-800",
};

/** Three visual states for how a candidate component's quantity was determined (see
 * backend/app/services/bom_candidate_service.py): read directly off an explicit callout,
 * counted from a repeated geometric feature (shows the count when available), or an
 * unsupported assumption. Never silently presents an assumption as if it were evidence. */
export function QuantityBasisBadge({
  basis,
  count,
}: {
  basis?: string | null;
  count?: number | null;
}) {
  const key = basis || "assumed";
  const cls = QUANTITY_BASIS_STYLES[key] || "bg-gray-100 text-gray-600";
  let label: string;
  if (key === "explicit_callout") label = "Explicit";
  else if (key === "counted_feature") label = count ? `Counted (${count}x)` : "Counted";
  else label = "Assumed";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}
      title={`Quantity basis: ${key.replace(/_/g, " ")}`}
    >
      {label}
    </span>
  );
}

/** Expandable note surfacing is_assumption + assumption_text, reusing the same click-to-
 * inspect interaction pattern as the OCR Evidence overlay's region detail (click to reveal the
 * detail inline rather than a tooltip-only hover, which doesn't work well on touch). Renders
 * nothing when the candidate isn't actually flagged as an assumption. */
export function AssumptionNote({
  isAssumption,
  text,
}: {
  isAssumption?: boolean | null;
  text?: string | null;
}) {
  const [open, setOpen] = useState(false);
  if (!isAssumption) return null;
  return (
    <span className="inline-block">
      <button
        type="button"
        className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold leading-none"
        onClick={() => setOpen((o) => !o)}
        title="This value is an assumption, not direct evidence - click for detail"
        aria-label="Assumption detail"
      >
        !
      </button>
      {open && (
        <span className="block mt-1 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 max-w-xs">
          {text || "Flagged as an assumption; no further detail recorded."}
        </span>
      )}
    </span>
  );
}
