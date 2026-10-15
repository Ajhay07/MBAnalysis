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
    routers/        FastAPI route modules (drawings, analyses, boms, procurement, calculations,
                    dashboard, review, demo)
  tests/            pytest suite (29 tests)
  seed.py           seeds 3 demo projects into the DB
  generate_seed_assets.py  generates the SVG sample drawings in seed_assets/
  alembic/          migration scaffold (SQLite works out of the box via create_all(); use
                    Alembic when you move to Postgres - see below)

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
29/29 tests passing at time of writing (file validation, calculation engine exactness,
Make/Buy/Review classification, BOM generation from a seeded analysis, demo-data isolation,
AI-provider-missing-key fallback).

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

## Known limitations

- PDF pages are not rasterized for OpenCV preprocessing/OCR in this build (image formats — PNG/
  JPG/TIFF — get full preprocessing + OCR; PDFs are stored/served/viewable but skip the
  OCR/preprocessing step). Extend `services/analysis_pipeline._load_image_array` with a PDF
  renderer (e.g. `pdf2image` + poppler) to add this.
- Multi-page drawings are supported in the data model (`source_page`) but the viewer UI does not
  yet page through multi-page PDFs.
- Supplier/catalog data has no real pricing seeded (by design — no fabricated prices).
- No authentication/multi-user support; this is a single-tenant local tool as scoped.
- Background jobs are synchronous-in-request rather than a true async queue (see above).
- Frontend BOM editing UI shows a flat list; the data model supports parent/child nesting
  (`parent_line_item_id`) but the UI does not yet render an indented tree.
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
