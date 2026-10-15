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
  tests/            pytest suite (49 tests)
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

### OCR
`app/services/ocr.py` wraps `pytesseract` + OpenCV preprocessing (CLAHE contrast boost, deskew
via minimum-area-rect, upscaling for small images — real working logic, not stubs). If the
Tesseract binary isn't installed, `is_tesseract_available()` returns `False` and OCR is skipped
gracefully (empty text, explanatory message) rather than crashing the app. **Windows install:**
https://github.com/UB-Mannheim/tesseract/wiki — install, then ensure `tesseract.exe` is on PATH.

### Background jobs
A lightweight `Job` row (Pending/Running/Done/Failed) is written synchronously around the
analysis pipeline — no Redis/Celery. This is a deliberate scope decision: single-process FastAPI
+ BackgroundTasks/synchronous execution is sufficient for a local/demo deployment and keeps setup
to `pip install` only. For production/multi-worker deployments, swap in a real task queue.

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
63/63 tests passing at time of writing (file validation, calculation engine exactness,
Make/Buy/Review classification, BOM generation from a seeded analysis, demo-data isolation,
AI-provider-missing-key fallback, hierarchical BOM cycle/rollup/tree tests, PDF rasterization
and multi-page analysis (`tests/test_pdf_pipeline.py`: 3-page PDF -> per-page components,
embedded-text capture, corrupt PDF, password-protected PDF, zero-page PDF - all synthetic PDFs
generated on the fly with reportlab/pymupdf, no binary fixtures committed), plus
`tests/test_auth.py`: login success/failure, token validation (missing/invalid/expired),
protected-route 401s, role-gated 403s, and that the audit trail records the real authenticated
actor).

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
- Background jobs are synchronous-in-request rather than a true async queue (see above).
- BOM tree editing supports qty/material/make-buy inline; re-parenting a line item (drag-and-drop
  into a different parent) still has to go through the API directly — the tree UI doesn't yet
  expose a drag target for it, though the cycle-safe backend endpoint fully supports it.
- This has not been validated against real engineering drawings — only synthetic demo drawings.

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
