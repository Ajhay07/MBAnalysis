"use client";

import { ReferenceBomResponse } from "@/lib/api";

export interface ReferenceBomPanelProps {
  reference: ReferenceBomResponse;
}

/** Secondary, clearly-subordinate panel summarizing a detected printed reference BOM table
 * (app.services.reference_bom_service) versus the independently generated candidate BOM. Only
 * rendered by the caller when `detected` is true - when no table is detected, nothing should
 * be shown (never implies a table should exist). Deliberately small/muted styling - this is
 * read-only comparison evidence for a human to review, not a reconciled or primary view. */
export default function ReferenceBomPanel({ reference }: ReferenceBomPanelProps) {
  if (!reference.detected) return null;
  const d = reference.discrepancy;

  return (
    <div className="border border-border rounded-industrial p-3 mb-4 bg-[#f8f7f2] text-xs">
      <div className="font-semibold text-steel mb-1">
        Reference BOM table detected ({reference.tables.length} page
        {reference.tables.length === 1 ? "" : "s"})
      </div>
      <p className="text-steel-light mb-2">
        A printed ITEM/QTY/PART-NO table was found on the drawing. This is read-only comparison
        evidence - it is never auto-reconciled with the candidate components above.
      </p>
      {reference.tables.map((t) => (
        <div key={t.page_number} className="mb-1">
          Page {t.page_number}: headers {t.matched_headers.join(", ")} &middot; ~{t.row_count_estimate} row
          {t.row_count_estimate === 1 ? "" : "s"} estimated
        </div>
      ))}
      {d && (
        <div className="mt-2 border-t border-border/60 pt-2">
          <div className={d.count_mismatch ? "text-amber-800 font-medium" : "text-steel"}>
            {d.count_mismatch
              ? `Row-count mismatch: reference ~${d.reference_row_count_estimate} vs. candidate ${d.candidate_component_count}.`
              : `Row count matches candidate components (${d.candidate_component_count}).`}
          </div>
          {d.candidate_descriptions_not_found_in_reference_text.length > 0 && (
            <div className="mt-1">
              Candidate descriptions not found in reference text:{" "}
              {d.candidate_descriptions_not_found_in_reference_text.join("; ")}
            </div>
          )}
          {d.candidate_part_numbers_not_found_in_reference_text.length > 0 && (
            <div className="mt-1">
              Candidate part numbers not found in reference text:{" "}
              {d.candidate_part_numbers_not_found_in_reference_text.join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
