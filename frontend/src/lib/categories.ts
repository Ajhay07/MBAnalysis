/** Drawing families, derived from the drawing title (first match wins, most specific first). */
export const CATEGORY_RULES: { key: string; label: string; match: RegExp }[] = [
  { key: "expansion", label: "Expansion Joints", match: /expansion\s*joint/i },
  { key: "bellows", label: "Bellows", match: /bellows/i },
  { key: "brackets", label: "Brackets", match: /bracket/i },
  { key: "shafts", label: "Shafts", match: /shaft/i },
  { key: "assemblies", label: "Assemblies", match: /assembl/i },
];

export function drawingCategory(title: string): string {
  return CATEGORY_RULES.find((r) => r.match.test(title))?.key ?? "other";
}

export const STATUS_OPTIONS: [string, string][] = [
  ["", "All statuses"],
  ["Uploaded", "Uploaded"],
  ["Queued", "Queued"],
  ["Processing", "Processing"],
  ["NeedsReview", "Analyzed"],
  ["Reviewed", "Reviewed"],
  ["BOMGenerated", "BOM Generated"],
  ["Failed", "Failed"],
];
