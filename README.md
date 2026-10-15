# Engineering Drawing Intelligence & BOM System

AI-assisted engineering drawing analysis and BOM generation. Upload a drawing, run analysis
(real OpenAI vision model, or built-in demo mode with no API key), review extracted components,
generate a versioned BOM, classify Buy/Make/Review, and export CSV/Excel reports.

**This has not been validated against real engineering drawings.** It was built and tested
against synthetic demo drawings only. Before trusting it on production drawings, validate the
AI provider's output accuracy against a sample of your own real drawings.

## Architecture

```
/backend   FastAPI + SQLAlchemy + Pydantic + SQLite (default) / Postgres (optional)
  app/
    models/        SQLAlchemy ORM models (Drawing, Analysis, Component, Bom, BomLineItem, ...)
    schemas/        Pydantic request/response + AI result schemas
    providers/      DrawingAnalysisProvider interface: OpenAIVisionProvider, DemoProvider
    services/       calculations, OCR/preprocessing, classification, BOM generation, exports,
                    file validation/security, the analysis pipeline
    routers/        FastAPI route modules (auth, drawings, analyses, boms, procurement,
                    calculations, dashboard, review, demo)
    auth.py         get_current_user / require_role() FastAPI dependencies
    security.py     password hashing (passlib/bcrypt) + JWT issuing/verification (python-jose)
  tests/            pytest suite (72 tests)
  create_admin.py   bootstraps the first admin user from ADMIN_EMAIL/ADMIN_PASSWORD
  seed.py           seeds 3 demo projects into the DB
  generate_seed_assets.py  generates the SVG sample drawings in seed_assets/
  alembic/          versioned migrations - `alembic upgrade head` is the documented schema path
                    (see "Authentication Setup" below); create_all() remains only as a dev
                    convenience fallback so a fresh checkout still boots if migrations haven't
                    been run yet

/frontend  Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + lucide-react
  src/app/            dashboard, drawing library, drawing viewer/workspace, review center,
                      procurement, calculations pages
  src/lib/api.ts      typed fetch client (proxied to the backend via Next.js rewrites)
  src/components/     Sidebar, status/make-buy/demo badges
```

### AI provider adapter pattern
`app/providers/base.py` defines `DrawingAnalysisProvider` (abstract). Two implementations:
- `OpenAIVisionProvider` — real vision-model call via the official `openai` SDK. Used only when
  `OPENAI_API_KEY` is set. Model name is configurable via `OPENAI_VISION_MODEL`.
- `DemoProvider` — returns clearly-labeled (`[DEMO]`) precomputed results, no network call, no
  key required. Used automatically whenever `OPENAI_API_KEY` is absent, or if the OpenAI
  provider fails to initialize, so the app never crashes for lack of a key.

`app/providers/__init__.py: get_provider()` is the single place that decides which one to use.

### OCR vs. AI Vision Interpretation — these are two distinct stages

**OCR text extraction** (`app/services/paddle_ocr.py`) and **AI visual interpretation**
(`app/providers/*`) are deliberately separate concerns, never conflated:

| | OCR (this phase) | AI vision interpretation |
|---|---|---|
| What it does | Extracts raw text + bounding boxes from pixels | Identifies components, quantities, dimensions, materials |
| Engine | PaddleOCR — local, CPU, free | OpenAI vision model, or the Demo provider |
| Needs an API key? | **No, never** | Only `OpenAIVisionProvider`; Demo provider needs none |
| Job stage | `JobStage.OCR` | `JobStage.VISION_ANALYSIS` |
| Can succeed alone? | Yes — a drawing can reach "OCR completed" with **zero** AI-identified components if no AI provider is configured | No — it consumes OCR's text as additional context, but invents nothing not actually read |

A drawing never gets fabricated components/dimensions from the OCR layer — OCR only ever
produces text + confidence + bounding boxes; interpreting that into BOM line items is entirely
the provider's job (real OpenAI vision call, or clearly-labeled `[DEMO]` synthetic data).

**OCR engine: PaddleOCR** (`app/services/paddle_ocr.py`)
- Pinned to `paddleocr==2.7.3` + `paddlepaddle==2.6.2` (CPU-only, no GPU package). Newer
  `paddleocr==2.9.x`/`3.x` were evaluated and rejected: their bundled formula/table-recognition
  augmentation path unconditionally imports `albumentations -> albucore -> torch`, pulling in a
  multi-hundred-MB unrelated GPU-adjacent stack (and, on this Windows/Python 3.10 combination,
  a broken `torch` DLL load) for plain text-region OCR that never needs it. 2.7.3 has no such
  import and installs clean.
- The `PaddleOCR` engine object is an expensive singleton — constructed once (lazily, on first
  real use) and reused for every page/request, never rebuilt per call.
- Uses the `.ocr(image, cls=True)` API (2.x result shape: a list of
  `[bbox, (text, confidence)]` lines per page). Returns a structured `PageOcrResult` per page:
  recognized text regions (text + confidence 0-1 + 4-point bounding box), page number, and any
  warnings/errors — never raises; engine failures, empty results, and malformed images all
  degrade to a structured error instead of crashing the pipeline.
- Low-confidence regions (below `OCR_CONFIDENCE_THRESHOLD`, default 0.5) are flagged in
  `warnings`, not silently accepted — they still flow through to the existing
  confidence/verification-status fields on `Component`/`Analysis` for manual review.
- **Preprocessing** (`preprocess_image`, reusing the proven CLAHE/deskew approach from the prior
  pytesseract-era adapter) is configurable per step: `OCR_PREPROCESS_CLAHE` (contrast, default
  on), `OCR_PREPROCESS_DESKEW` (default **off** — verified empirically that the
  minimum-area-rect angle estimate is unreliable on sparse/high-aspect text and can rotate
  otherwise-straight text into worse recognition; turn it on for genuinely skewed scans),
  `OCR_PREPROCESS_DENOISE` (default off — thresholding/denoising is never applied
  unconditionally, since it destroys thin dimension lines and decimal points).
- **Model download**: PaddleOCR downloads its detection/recognition/classification model
  weights to `~/.paddleocr` on first real use (a few MB, one-time, requires network access).
  After that, every OCR call runs fully offline/locally — no paid API, no network call.
- Config (see `.env.example`): `OCR_ENABLED` (default true), `OCR_LANGUAGE` (default `en`),
  `OCR_USE_GPU` (default false — CPU only, no GPU packages installed), `PDF_RENDER_DPI`
  (default 288, feeds `rasterize_pdf_pages`'s zoom factor), `OCR_CONFIDENCE_THRESHOLD`
  (default 0.5).
- **Windows install note**: `paddlepaddle` installs cleanly from plain PyPI on Windows/CPU/
  Python 3.10 (`pip install paddlepaddle==2.6.2`) — no special index needed. `paddleocr==2.7.3`
  declares `opencv-python`/`opencv-contrib-python` as dependencies, which conflict with this
  project's `opencv-python-headless` pin (both ship a `cv2` binary extension, and reinstalling
  it over a running `cv2` import — e.g. a live `uvicorn` dev server — fails on Windows with
  `OSError: [WinError 5] Access is denied: ...cv2.pyd`). Install it with `--no-deps`, then add
  only the submodules actually needed for inference (`pip install --no-deps paddleocr==2.7.3 &&
  pip install pyclipper imgaug lmdb requests` is sufficient in practice — no `opencv-python`,
  no `torch`). See `backend/requirements.txt` for the exact pinned versions.
- **Known limitations** (be honest about these): PaddleOCR's general-purpose PP-OCRv3/v4
  models are trained on natural/document text, not dense technical drawings — expect lower
  accuracy on tightly-packed dimension callouts, GD&T symbols, and rotated/vertical text than on
  a clean title block. DPI tuning (`PDF_RENDER_DPI`) matters a lot in practice; 288 is a
  reasonable default but very dense drawings may need higher. Always treat OCR output as
  evidence for the AI vision step and for manual review, not as a verified ground truth.

**Old adapter removed**: the earlier `pytesseract`-based `app/services/ocr.py` has been deleted
and replaced entirely by the above. `pytesseract` and the Tesseract binary are no longer a
dependency of this project.

### Background jobs (Phase 13 — done)
Every analysis run is tracked by a `Job` row written synchronously around the pipeline — no
Redis/Celery/separate worker process. This remains a deliberate scope decision: single-process
FastAPI + in-process synchronous execution is sufficient for a local/demo deployment and keeps
setup to `pip install` only. For production/multi-worker deployments, swap in a real task queue
(the `Job` model and stage machine below would map directly onto one).

What *is* fully modeled now (previously a known gap): each `Job` carries `stage` (one of
`queued`, `extracting_pages`, `ocr`, `vision_analysis`, `persisting`, `needs_review`, `reviewed`,
`bom_generated`, `failed`, `cancelled`), `retry_count`, `failure_reason`/`last_error`,
`started_at`/`completed_at`, and a link to the `Analysis` it produced. The pipeline
(`app/services/analysis_pipeline.py`) advances `stage` as it moves through OCR and vision
analysis and always reaches a terminal stage — on any failure (corrupt/encrypted/empty PDF, AI
provider auth error, AI provider timeout/rate-limit/connection/server error after a bounded
retry+backoff, malformed/schema-invalid AI JSON, or any other unhandled exception) the Drawing
and Job are marked `Failed` with a specific reason, never left stuck in "Processing" and never
silently marked successful. `OpenAIVisionProvider` distinguishes auth errors (fail fast, no
retry) from transient errors (bounded retry with exponential backoff) — see
`app/providers/openai_provider.py`.

`POST /api/drawings/{id}/reprocess` retries a drawing: it increments `retry_count` and always
re-invokes the real pipeline against the drawing's own file — it never falls back to
demo/seeded content, even after a prior failure (`is_demo` stays `false` throughout). `GET
/api/drawings/{id}/jobs` returns the stage/retry/failure history, and `DrawingOut` carries
`job_stage`/`job_retry_count`/`job_failure_reason` for the latest run. The Drawing Viewer shows
a "processing details" toggle with the stage history and a "Retry Analysis" button once a
drawing has failed.

Covered by `tests/test_job_tracking.py` (success, auth-error failure, transient-error failure,
malformed-JSON failure, OCR-unavailable graceful degradation, and retry via both the service
function and the HTTP endpoint).

### Database
SQLite by default (`sqlite:///./mbanalysis.db`), zero setup. Swap to Postgres by setting
`DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname` in `backend/.env` and installing
`psycopg2-binary`. Tables are created automatically on startup via `Base.metadata.create_all()`
for simplicity; an Alembic scaffold is included under `backend/alembic/` for when you want real
versioned migrations against Postgres (`alembic revision --autogenerate -m "..."` then
`alembic upgrade head`).

## Windows setup (exact commands)

### Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# paddleocr's declared opencv-python(-contrib) deps conflict with this project's
# opencv-python-headless pin (see "OCR vs. AI Vision Interpretation" above) - install it
# separately with --no-deps, then its few genuinely-needed submodules:
pip install --no-deps paddleocr==2.7.3
pip install pyclipper imgaug lmdb requests
copy .env.example .env
python generate_seed_assets.py      # generates seed_assets/*.svg sample drawings
python seed.py                      # seeds 3 demo projects into the DB
uvicorn app.main:app --reload --port 8000
```
Backend runs at http://127.0.0.1:8000 (interactive docs at /docs).

Run tests:
```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest -q
```
72/72 tests passing at time of writing (file validation, calculation engine exactness,
Make/Buy/Review classification, BOM generation from a seeded analysis, demo-data isolation,
AI-provider-missing-key fallback, hierarchical BOM cycle/rollup/tree tests, PDF rasterization
and multi-page analysis (`tests/test_pdf_pipeline.py`: 3-page PDF -> per-page components,
embedded-text capture, corrupt PDF, password-protected PDF, zero-page PDF - all synthetic PDFs
generated on the fly with reportlab/pymupdf, no binary fixtures committed), plus
`tests/test_auth.py`: login success/failure, token validation (missing/invalid/expired),
protected-route 401s, role-gated 403s, and that the audit trail records the real authenticated
actor; `tests/test_job_tracking.py` (Phase 13): job stage/retry/failure tracking across success,
auth-error, transient-error, and malformed-AI-JSON failure modes, OCR-unavailable graceful
degradation, and retry via both the service function and the `/reprocess` HTTP endpoint;
`tests/test_e2e_workflow.py` (Phase 16): one scripted end-to-end run through the full real
stack — login, demo load, analysis fetch, BOM generation, line-item edit, BOM tree rollup,
procurement grouping cross-checked against the persisted BOM, role-gated approval, CSV/Excel
export with real exported values checked, and an audit log entry naming the real actor — plus a
second test uploading a synthetic (generated on the fly) PDF through the real upload+analyze
path with the AI provider mocked, confirming it is never demo-tagged).

### Frontend
```powershell
cd frontend
npm install
npm run dev
```
Frontend runs at http://localhost:3000 and proxies `/api/*` to the backend
(`http://127.0.0.1:8000` by default; override with `BACKEND_URL` env var).

Build/lint check:
```powershell
npm run build
npm run lint
```

## Demo mode

Click **Load Demo Project** on the dashboard (or `POST /api/demo/load`) to seed 3 synthetic
projects: a gearbox assembly, a shaft+bearing assembly, and a sheet-metal bracket. Each has a
generated SVG line-drawing preview (`backend/seed_assets/`, with title block, dimension lines,
and labels), a seeded analysis, components, and a draft BOM. Every demo drawing/title is tagged
`is_demo=True` and prefixed `[DEMO]` in the UI (orange "Demo Data" badge). **Reset Demo Data**
deletes and re-seeds them.

Demo data never leaks into a real upload: uploading your own drawing always creates a
`is_demo=False` record, and the analysis pipeline always invokes the provider fresh against that
drawing's own file — it never substitutes seeded content. See
`backend/tests/test_demo_isolation.py` for the automated check.

## What needs `OPENAI_API_KEY` vs. what doesn't

| Needs a key | Works without a key |
|---|---|
| Real AI-driven extraction of title block/dimensions/components from an uploaded drawing (`OpenAIVisionProvider`) | Everything else: dashboard, drawing library, upload/delete/reprocess, demo projects, BOM generation/editing/export, procurement view, calculation engine, review queue, audit trail |

Without a key, any "Run Analysis" on a real upload falls back to `DemoProvider`'s generic
placeholder result (clearly labeled, low confidence, routed to the review queue) instead of
fabricating realistic-looking data.

## Authentication Setup

Real authentication/authorization is implemented: email+password login, JWT sessions, three
roles (admin/engineer/viewer), and every state-changing endpoint (plus all reads) requires a
logged-in user. Demo mode does **not** bypass auth — loading/resetting demo data still requires
an admin/engineer session.

### 1. Run migrations

```powershell
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
```
This creates/updates all tables including the new `users` table (`backend/alembic/versions/
7787f60a7a82_add_users_table.py`). Verified against a genuinely empty SQLite DB (upgrade,
downgrade, re-upgrade). If your DB predates Alembic (tables already exist from the old
`create_all()`-only path), stamp the baseline first: `alembic stamp 3dc7c2a9f404`, then
`alembic upgrade head` to add just the `users` table.

### 2. Set required env vars and bootstrap the first admin

In `backend/.env` (copy from `.env.example` if you haven't):
```
JWT_SECRET=<output of: python -c "import secrets; print(secrets.token_hex(32))">
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=<a real password, not committed anywhere>
```
`JWT_SECRET` can be left blank only while `ENVIRONMENT=development` — a random secret is then
generated per process start (every restart invalidates all sessions, so set a real one for
anything beyond quick local poking). In any other `ENVIRONMENT`, the app refuses to start
without it (`app/security.py:get_jwt_secret`).

Then, once:
```powershell
python create_admin.py
```
Creates the admin user from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. Refuses to run again once any user
exists, so it can't silently reset a password — create additional users (engineer/viewer) from
an authenticated admin session via the API; there's no bulk-create endpoint yet.

### 3. Log in

Start the backend and frontend as usual, open http://localhost:3000, and you'll be redirected
to `/login`. Enter the admin email/password from step 2.

### How it works

- **Password hashing**: `passlib[bcrypt]`. Passwords are never logged or stored in plaintext.
  Pin note: `bcrypt==4.0.1` is required alongside `passlib==1.7.4` — newer bcrypt removed an
  attribute passlib's backend probes, which breaks hashing outright (see requirements.txt).
- **JWT**: `python-jose`, `HS256`, signed with `JWT_SECRET`. Access tokens expire after 240
  minutes (4 hours — long enough for a working session, short enough that a stale/leaked token
  doesn't stay valid indefinitely). There is no refresh-token flow: when a token expires, you
  simply log in again (`POST /api/auth/login`).
- **Token storage/transport**: an **httpOnly cookie** set by the backend on login, not
  `localStorage`. Chosen because the frontend's existing API client
  (`frontend/src/lib/api.ts`) already calls the backend through Next.js's `rewrites()` proxy, so
  every browser request already lands on the *same origin* — the proxy forwards `Set-Cookie`
  transparently, the browser attaches the cookie automatically on every subsequent request, and
  page JavaScript never has read access to the token (so an XSS bug can't exfiltrate it the way
  it could with `localStorage`). Verified end-to-end (login through the proxy -> cookie set ->
  subsequent proxied request authenticated -> logout clears it). The tradeoff: a cookie-based
  session is less convenient for a non-browser API client, so the same endpoints also accept a
  plain `Authorization: Bearer <token>` header (what the backend test suite uses).
- **Logout** (`POST /api/auth/logout`) just clears the cookie — JWTs are stateless, so there's
  no server-side session to revoke. A token copied out of the cookie before logout stays valid
  until it expires; this is the accepted tradeoff of the simple re-login-on-expiry design, not
  a bug.
- **Roles**: `admin` and `engineer` can create/upload/edit/delete/approve/reject everything
  (upload, reprocess, delete drawings, edit components/BOM line items, approve/reject BOM or
  analysis, supplier/catalog CRUD, demo load/reset). `viewer` is read-only — it can view every
  page, run the (non-persisted) calculation tools, and export files, but every write/approval
  endpoint returns 403. This is a stricter reading of "viewer: read-only" than just gating BOM
  approval and review verification — all mutation across the app is admin/engineer-only, with
  reads open to any logged-in user.
- **Audit trail**: every `AuditLog` row written by an authenticated action now records the real
  user's email as `actor` (previously hardcoded to `"system"`). The `"system"` default remains
  only as a fallback for anything invoked outside a request context (e.g. running `seed.py`
  directly from the command line rather than through `POST /api/demo/load`).

## PDF rasterization (done)

PDFs are no longer a second-class format. `backend/app/services/analysis_pipeline.py` opens
every uploaded PDF with `pymupdf` (`fitz`) — a **pure-pip** dependency with no external binary
required (no poppler, no system install) — and, per page:
- extracts the embedded text layer via `page.get_text()`,
- rasterizes the page at ~210-290 DPI (`fitz.Matrix(3.0, 3.0)`, well above the library default
  of 72 DPI) and runs the existing OpenCV/Tesseract OCR preprocessing on that raster, same as
  the PNG/JPG path, so scanned pages with no text layer still get OCR'd correctly,
- feeds the page through the configured provider (OpenAI vision or `DemoProvider`)
  independently, stamping every resulting component's `source_page` with that page's true
  physical page number,
- saves one PNG preview per page next to the original upload, served at
  `GET /api/drawings/{id}/pages/{page_number}/preview`, so the frontend can page through a
  multi-page PDF exactly as it looked in the original file.

Failures are handled without 500s: a corrupt file, a password-protected PDF (`doc.is_encrypted`
with no usable empty password), and a zero-page PDF are all caught as `PdfProcessingError`,
mark the `Drawing` `Failed` with a specific reason string, and surface as a `422` from
`POST /api/drawings/{id}/analyze` — never an unhandled exception. Oversized PDFs are rejected at
upload time by the existing generic `MAX_UPLOAD_MB` check (it was already extension-agnostic).

The frontend drawing viewer (`frontend/src/app/drawings/[id]/page.tsx`) shows prev/next page
navigation for any PDF whose analysis has more than one page, renders that page's raster
preview, and lets you jump straight from a component card in the right panel to the page it was
found on.

**Caveat**: embedded text and OCR text for a page are concatenated rather than deduplicated
token-by-token when both exist and disagree — acceptable for the provider's own text input, but
not a canonical "final" text layer.

## Hierarchical BOM (done)

The BOM tree endpoint (`GET /api/boms/{bom_id}/tree`, already backed by
`build_bom_tree`/cycle-safe reparenting/qty rollup from the previous milestone) now also returns
each node's `level` (0 = top-level), and `max_tree_depth()` lets the frontend decide which view
to default to.

`frontend/src/components/BomPanel.tsx` is a new, single component that renders **both** a flat
list and an indented, expand/collapsible tree from the same tree/flat API data, defaulting to
tree view when the fetched tree nests deeper than depth 1 (otherwise flat), with a toggle to
switch manually. Both views render through the exact same `Row` component and the exact same
`onUpdate(lineItemId, patch)` handler (wired to `PATCH /api/boms/line-items/{id}`) — editing
quantity, material, or Make/Buy works identically and calls identical code in either view, per
line item `total_quantity` (qty rollup) and the tree's `level`/indentation are both visible in
the UI.

## Known limitations

- Embedded-text/OCR merging on a PDF page is a simple concatenation, not a true reconciled text
  layer (see PDF rasterization section above).
- Supplier/catalog data has no real pricing seeded (by design — no fabricated prices).
- Authentication is email+password only — no SSO/OAuth, no password reset flow, no refresh
  tokens (see "Authentication Setup" above for what is implemented).
- Background jobs are synchronous-in-request rather than a true async queue/separate worker
  process (Phase 13's stage/retry/failure tracking is fully modeled on top of this; only the
  execution model — in-process vs. Redis/Celery/a real queue — remains a deliberate scope
  choice, not a bug, documented above under "Background jobs").
- BOM tree editing supports qty/material/make-buy inline; re-parenting a line item (drag-and-drop
  into a different parent) still has to go through the API directly — the tree UI doesn't yet
  expose a drag target for it, though the cycle-safe backend endpoint fully supports it.
- This has not been validated against real engineering drawings — only synthetic demo drawings.
- Phase 16's scripted end-to-end test covers one complete gearbox workflow plus one real-upload
  path; it is not a full regression suite across every possible drawing/BOM shape (the targeted
  unit/integration tests elsewhere in `tests/` cover edge cases such as cycles, multi-page PDFs,
  and corrupt files).

## Security basics implemented

- Filename sanitization + path-traversal-safe storage (`services/file_validation.py`,
  generates a fresh UUID filename inside the upload directory and verifies the resolved path
  stays inside it).
- File extension allowlist and max-size validation before any file is written to disk.
- Uploaded files are never executed; served back only via `FileResponse` with the original
  filename for download/display.
- `.env.example` ships with no real secrets.
- No real purchase orders are ever placed — procurement module only classifies/exports.
- Real authentication/authorization (hashed passwords, JWT sessions, role-gated actions) on
  every route — see "Authentication Setup" above.
