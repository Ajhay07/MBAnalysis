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
