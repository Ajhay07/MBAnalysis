const BASE = "";

// Auth token transport is an httpOnly cookie set by the backend on login (see backend/app/auth.py
// for the full rationale) - the browser attaches it automatically on every same-origin request
// via the Next.js rewrite proxy, so no Authorization header needs adding here. The one thing this
// client does need to handle is a 401: it means "not logged in (or session expired)", and every
// page in the app assumes a logged-in user, so we bounce to /login rather than let each page
// handle it individually. /api/auth/me and /api/auth/login are exempt - AuthContext calls those
// itself to *determine* auth state, and a 401 there is an expected, handled outcome, not a reason
// to redirect.
function isAuthProbePath(path: string): boolean {
  return (
    path.startsWith("/api/auth/me") ||
    path.startsWith("/api/auth/login") ||
    path.startsWith("/api/auth/demo-login")
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (res.status === 401 && !isAuthProbePath(path)) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Request failed ${res.status}: ${text}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return res.json();
  }
  return undefined as unknown as T;
}

export interface Drawing {
  id: string;
  drawing_number: string;
  title: string;
  revision: string;
  file_name: string;
  file_type: string;
  file_size: number;
  units: string;
  scale: string;
  status: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
  job_stage?: string | null;
  job_retry_count?: number | null;
  job_failure_reason?: string | null;
}

export interface JobRecord {
  id: string;
  job_type: string;
  status: string;
  stage: string;
  retry_count: number;
  failure_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  analysis_id: string | null;
}

export interface Component {
  id: string;
  part_number: string;
  description: string;
  category: string;
  quantity: number;
  material: string;
  grade: string;
  dimensions: Record<string, unknown>;
  tolerances: Record<string, unknown>;
  gear_specs: Record<string, unknown>;
  make_buy: string;
  confidence: number;
  verification_status: string;
  source_page: number;
  source_region: Record<string, unknown>;
  source_text: string;
  parent_component_id?: string | null;
  // Geometry-driven BOM generation fields (see backend bom_candidate_service.py /
  // analysis_pipeline.py): how this candidate's quantity was determined, what kind of
  // component it is, its parent assembly's part number (if any), and - when the value is an
  // engineering assumption rather than evidence read directly off the drawing - a flag plus a
  // human-readable explanation. Optional because older persisted Components (pre-migration
  // d4e5f6a7b8c9) may not have these set.
  quantity_basis?: "explicit_callout" | "counted_feature" | "assumed" | string | null;
  component_type?: "raw_material" | "purchased" | "manufactured" | "assembly" | string | null;
  parent_part_number?: string | null;
  is_assumption?: boolean | null;
  assumption_text?: string | null;
  // Set by app.services.catalog_matching during the analysis pipeline when this component's
  // part number/description matched a known Source Catalog row closely enough. Null means no
  // confident match - never implies one.
  catalog_component_id?: string | null;
  catalog_match_score?: number | null;
}

export interface Analysis {
  id: string;
  drawing_id: string;
  version: number;
  provider: string;
  title_block: Record<string, unknown>;
  dimensions: unknown[];
  materials: string[];
  raw_ocr_text: string;
  overall_confidence: number;
  created_at: string;
  page_count: number;
  components: Component[];
}

export interface BomLineItem {
  id: string;
  part_number: string;
  description: string;
  category: string;
  quantity: number;
  material: string;
  make_buy: string;
  unit_cost?: number | null;
  parent_line_item_id?: string | null;
  component_id?: string | null;
}

export interface Bom {
  id: string;
  drawing_id: string;
  analysis_id: string;
  version: number;
  status: string;
  created_at: string;
  line_items: BomLineItem[];
}

export interface BomTreeNode {
  id: string;
  part_number: string;
  description: string;
  category: string;
  quantity: number;
  total_quantity: number | null;
  material: string;
  make_buy: string;
  unit_cost?: number | null;
  parent_line_item_id?: string | null;
  component_id?: string | null;
  level: number;
  children: BomTreeNode[];
}

export interface BomTree {
  bom_id: string;
  nodes: BomTreeNode[];
}

export interface DashboardMetrics {
  total_drawings: number;
  status_breakdown: Record<string, number>;
  total_bom_items: number;
  make_count: number;
  buy_count: number;
  review_count: number;
  recent_activity: {
    entity_type: string; entity_id: string; action: string; created_at: string;
    details?: Record<string, unknown> | null; actor?: string | null;
  }[];
}

export interface OcrRegion {
  text: string;
  confidence: number;
  bbox: number[][];
  low_confidence: boolean;
}

export interface OcrPageEvidence {
  page_number: number;
  configured: boolean;
  error: string | null;
  confidence_threshold: number;
  regions: OcrRegion[];
  image_width: number | null;
  image_height: number | null;
}

export interface AvailabilityLine {
  bom_line_item_id: string;
  part_number: string;
  description: string;
  material: string;
  grade: string;
  unit: string;
  required_quantity: number | null;
  on_hand: number;
  reserved: number;
  quarantined: number;
  usable_available: number;
  this_job_allocation: number;
  net_shortage: number | null;
  status: "AVAILABLE" | "PARTIALLY_AVAILABLE" | "OUT_OF_STOCK" | "REVIEW_REQUIRED";
  explanation: string;
  matched_lot_ids: string[];
  supplier_name: string | null;
  lead_time_days: number | null;
}

export interface AvailabilityReport {
  bom_id: string;
  production_quantity: number;
  summary: Record<string, number>;
  lines: AvailabilityLine[];
}

export interface RequisitionLine {
  id: string;
  material_code: string;
  description: string;
  quantity: number;
  unit: string;
  supplier_id: string | null;
  catalog_component_id: string | null;
  unit_cost: number | null;
}

export interface Requisition {
  id: string;
  bom_id: string;
  status: string;
  created_at: string;
  created_by: string;
  approved_at: string | null;
  approved_by: string | null;
  lines: RequisitionLine[];
}

export interface ReferenceBomTableEntry {
  page_number: number;
  matched_headers: string[];
  bbox: Record<string, number>;
  raw_text: string;
  row_count_estimate: number;
}

export interface ReferenceBomDiscrepancy {
  reference_row_count_estimate: number;
  candidate_component_count: number;
  count_mismatch: boolean;
  candidate_descriptions_not_found_in_reference_text: string[];
  candidate_part_numbers_not_found_in_reference_text: string[];
}

export interface ReferenceBomResponse {
  detected: boolean;
  tables: ReferenceBomTableEntry[];
  discrepancy: ReferenceBomDiscrepancy | null;
}

export interface IndentLine {
  id: string;
  sl_no: number;
  mtl_spec: string;
  size_text: string;
  wt_qty: number | null;
  unit: string;
  bom_line_item_id: string | null;
  indent_rule_id: string | null;
  source: "bom_line" | "rule" | "manual" | string;
  requires_confirmation: boolean;
  note: string;
}

export interface Indent {
  id: string;
  bom_id: string;
  drawing_id: string;
  version: number;
  wo_number: string;
  party_name: string;
  required_on: string;
  serial_no: string;
  indent_date: string;
  assembly_quantity: number;
  status: "Draft" | "Approved" | "Rejected" | string;
  created_at: string;
  approved_by: string | null;
  approved_at: string | null;
  lines: IndentLine[];
}

export interface IndentGenerateRequest {
  assembly_quantity: number;
  wo_number?: string;
  party_name?: string;
  required_on?: string;
  serial_no?: string;
  indent_date?: string;
  rule_ids?: string[];
}

export interface IndentRule {
  id: string;
  name: string;
  mtl_spec: string;
  size_text: string;
  unit: string;
  formula: "fixed_qty" | "per_assembly" | "manual_required" | string;
  value: number | null;
  notes: string;
  active: boolean;
  created_by: string;
  created_at: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  role: "admin" | "engineer" | "viewer";
  is_active: boolean;
  created_at: string;
}

export const api = {
  health: () => request<{ status: string; ai_mode: string }>("/api/health"),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; expires_in_minutes: number }>(
      "/api/auth/login",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }
    ),
  demoLogin: () =>
    request<{ access_token: string; token_type: string; expires_in_minutes: number }>(
      "/api/auth/demo-login",
      { method: "POST" }
    ),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => request<CurrentUser>("/api/auth/me"),
  dashboardMetrics: () => request<DashboardMetrics>("/api/dashboard/metrics"),
  aiStatus: () => request<{ mode: string; vision_model: string }>("/api/dashboard/ai-status"),

  listDrawings: (params?: { q?: string; status?: string; page?: number; page_size?: number }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.status) sp.set("status", params.status);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.page_size) sp.set("page_size", String(params.page_size));
    const qs = sp.toString();
    return request<Drawing[]>(`/api/drawings${qs ? `?${qs}` : ""}`);
  },
  getDrawing: (id: string) => request<Drawing>(`/api/drawings/${id}`),
  deleteDrawing: (id: string) => request<{ ok: boolean }>(`/api/drawings/${id}`, { method: "DELETE" }),
  uploadDrawing: (formData: FormData) =>
    request<Drawing>("/api/drawings", { method: "POST", body: formData }),
  analyzeDrawing: (id: string) => request<Analysis>(`/api/drawings/${id}/analyze`, { method: "POST" }),
  reprocessDrawing: (id: string) => request<Analysis>(`/api/drawings/${id}/reprocess`, { method: "POST" }),
  listDrawingJobs: (id: string) => request<JobRecord[]>(`/api/drawings/${id}/jobs`),
  listAnalyses: (id: string) => request<Analysis[]>(`/api/drawings/${id}/analyses`),
  getPageOcrEvidence: (id: string, pageNumber: number) =>
    request<OcrPageEvidence>(`/api/drawings/${id}/pages/${pageNumber}/ocr`),
  getReferenceBom: (drawingId: string, analysisId: string) =>
    request<ReferenceBomResponse>(`/api/drawings/${drawingId}/analyses/${analysisId}/reference-bom`),

  getAnalysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),
  updateComponent: (id: string, payload: Partial<Component>) =>
    request<Component>(`/api/analyses/components/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  approveAnalysis: (id: string) => request<{ ok: boolean }>(`/api/analyses/${id}/approve`, { method: "POST" }),
  generateBom: (analysisId: string) =>
    request<Bom>(`/api/analyses/${analysisId}/generate-bom`, { method: "POST" }),

  listBomsForDrawing: (drawingId: string) => request<Bom[]>(`/api/boms/by-drawing/${drawingId}`),
  getBom: (id: string) => request<Bom>(`/api/boms/${id}`),
  getBomTree: (id: string) => request<BomTree>(`/api/boms/${id}/tree`),
  updateBomLineItem: (id: string, payload: Partial<BomLineItem>) =>
    request<{ ok: boolean }>(`/api/boms/line-items/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  approveBom: (id: string) => request<{ ok: boolean }>(`/api/boms/${id}/approve`, { method: "POST" }),
  rejectBom: (id: string) => request<{ ok: boolean }>(`/api/boms/${id}/reject`, { method: "POST" }),

  reviewQueue: () => request<any[]>("/api/review/queue"),
  reviewComponents: () =>
    request<{
      component_id: string; drawing_id: string; drawing_number: string; drawing_title: string;
      file_type: string; part_number: string; description: string; category: string; quantity: number;
      confidence: number; low_confidence: boolean; verification_status: string; make_buy: string;
    }[]>("/api/review/components"),
  auditTrail: (entityType?: string, entityId?: string) => {
    const sp = new URLSearchParams();
    if (entityType) sp.set("entity_type", entityType);
    if (entityId) sp.set("entity_id", entityId);
    const qs = sp.toString();
    return request<any[]>(`/api/review/audit-trail${qs ? `?${qs}` : ""}`);
  },

  procurementByDrawing: (drawingId: string) =>
    request<{ buy: any[]; make: any[]; review: any[] }>(`/api/procurement/by-drawing/${drawingId}`),
  listSuppliers: () => request<any[]>("/api/procurement/suppliers"),
  listCatalog: () => request<any[]>("/api/procurement/catalog"),
  catalogUsage: () => request<any[]>("/api/procurement/catalog/usage"),
  createCatalogItem: (payload: {
    part_number: string; description?: string; category?: string; unit_price?: number | null;
    currency?: string | null; stock_quantity?: number | null;
  }) =>
    request<any>("/api/procurement/catalog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  purchaseRequirements: (drawingId: string) =>
    request<{
      bom_id: string | null; buy: any[]; make: any[]; review: any[];
      summary: {
        buy_item_count: number; make_item_count: number; review_item_count: number;
        estimated_total_cost: number | null; buy_items_missing_price: number;
        is_partial_estimate: boolean;
      };
    }>(`/api/procurement/purchase-requirements/${drawingId}`),

  loadDemo: () => request<{ ok: boolean; created: number }>("/api/demo/load", { method: "POST" }),
  resetDemo: () => request<{ ok: boolean }>("/api/demo/reset", { method: "POST" }),
  demoStatus: () => request<{ demo_drawings: number; loaded: boolean }>("/api/demo/status"),

  getAvailability: (bomId: string, productionQuantity: number) =>
    request<AvailabilityReport>(
      `/api/inventory/availability/${bomId}?production_quantity=${productionQuantity}`
    ),
  draftRequisition: (bomId: string, productionQuantity: number) =>
    request<Requisition>(
      `/api/inventory/requisitions/draft?bom_id=${bomId}&production_quantity=${productionQuantity}`,
      { method: "POST" }
    ),
  listRequisitionsForBom: (bomId: string) =>
    request<Requisition[]>(`/api/inventory/requisitions/by-bom/${bomId}`),
  approveRequisition: (id: string) =>
    request<Requisition>(`/api/inventory/requisitions/${id}/approve`, { method: "POST" }),
  rejectRequisition: (id: string) =>
    request<Requisition>(`/api/inventory/requisitions/${id}/reject`, { method: "POST" }),

  listIndentsForBom: (bomId: string) => request<Indent[]>(`/api/boms/${bomId}/indents`),
  generateIndent: (bomId: string, payload: IndentGenerateRequest) =>
    request<Indent>(`/api/boms/${bomId}/indents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getIndent: (id: string) => request<Indent>(`/api/indents/${id}`),
  approveIndent: (id: string) => request<Indent>(`/api/indents/${id}/approve`, { method: "POST" }),
  rejectIndent: (id: string) => request<Indent>(`/api/indents/${id}/reject`, { method: "POST" }),
  listIndentRules: () => request<IndentRule[]>("/api/indent-rules"),

  calc: (endpoint: string, payload: Record<string, unknown>) =>
    request<any>(`/api/calculations/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};

export function drawingFileUrl(id: string): string {
  return `/api/drawings/${id}/file`;
}

export function drawingPagePreviewUrl(id: string, pageNumber: number): string {
  return `/api/drawings/${id}/pages/${pageNumber}/preview`;
}

export function indentPdfUrl(indentId: string): string {
  return `/api/indents/${indentId}/pdf`;
}

export function bomExportUrl(
  bomId: string,
  kind: "bom.csv" | "bom.xlsx" | "bom.pdf" | "purchase-list.csv" | "material-summary.csv"
): string {
  return `/api/boms/${bomId}/export/${kind}`;
}
