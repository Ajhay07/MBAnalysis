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
  return path.startsWith("/api/auth/me") || path.startsWith("/api/auth/login");
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
  recent_activity: { entity_type: string; entity_id: string; action: string; created_at: string }[];
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

  loadDemo: () => request<{ ok: boolean; created: number }>("/api/demo/load", { method: "POST" }),
  resetDemo: () => request<{ ok: boolean }>("/api/demo/reset", { method: "POST" }),
  demoStatus: () => request<{ demo_drawings: number; loaded: boolean }>("/api/demo/status"),

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

export function bomExportUrl(bomId: string, kind: "bom.csv" | "bom.xlsx" | "purchase-list.csv" | "material-summary.csv"): string {
  return `/api/boms/${bomId}/export/${kind}`;
}
