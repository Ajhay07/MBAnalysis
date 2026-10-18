const ACTION_TEXT: Record<string, string> = {
  "drawing:uploaded": "New drawing uploaded",
  "drawing:analyzed": "OCR analysis completed",
  "drawing:reprocessed": "Drawing reprocessed",
  "drawing:deleted": "Drawing deleted",
  "drawing:demo_seeded": "Demo drawing seeded",
  "analysis:approved": "Analysis approved",
  "bom:generated": "BOM generated",
  "bom:approved": "BOM approved",
  "bom:rejected": "BOM rejected",
  "bom_line_item:updated": "BOM line item updated",
  "component:updated": "Component updated",
};

/** Human-readable one-liner for an audit-log row: a known entity/action phrase when there is
 * one, otherwise the row's recorded detail fields joined as key: value. */
export function describeActivity(entityType: string, action: string, details?: Record<string, unknown> | null): string {
  const known = ACTION_TEXT[`${entityType}:${action}`];
  const detailText = details && typeof details === "object"
    ? Object.entries(details)
        .filter(([k, v]) => !/(^|_)id$/.test(k) && v !== null && v !== undefined && v !== "" && typeof v !== "object")
        .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
        .join(", ")
    : "";
  if (known && detailText) return `${known} (${detailText})`;
  return known || detailText || `${entityType.replace(/_/g, " ")} ${action.replace(/_/g, " ")}`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB")}, ${d.toLocaleTimeString("en-GB")}`;
}
