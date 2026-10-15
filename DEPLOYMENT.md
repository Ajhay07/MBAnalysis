# Deployment

## Live URLs

- Frontend (Vercel): https://mbanalysis-frontend.vercel.app
- Backend (Railway): https://mbanalysis-backend-production.up.railway.app
  - Health check: `/api/health`
  - API docs (Swagger): `/docs`

## Hosting setup

- **Railway project:** `mbanalysis-backend` (workspace: Ajhay's Projects), service `mbanalysis-backend`.
  Deployed via the `railway` CLI (`railway up`) from `backend/`, building `backend/Dockerfile`.
  Not connected to GitHub auto-deploy — redeploys are triggered manually (see below).
- **Vercel project:** `mbanalysis-frontend` (scope: ajhay07s-projects). Linked to the
  `Ajhay07/MBAnalysis` GitHub repo during `vercel link`, deployed via `vercel --prod` from
  `frontend/`. Because a GitHub repo is linked, Vercel may also auto-deploy on pushes to `main`
  once the GitHub integration is fully enabled from the Vercel dashboard — check
  Project Settings -> Git on vercel.com if you want to confirm/disable this.

## Persistent data (Railway volume)

A Railway volume (`mbanalysis-backend-volume`, 500MB, mounted at `/data`) is attached to the
backend service. This is what makes data survive restarts/redeploys on Railway's otherwise
ephemeral filesystem:

- `DATABASE_URL=sqlite:////data/mbanalysis.db` — the SQLite DB file
- `UPLOAD_DIR=/data/uploads` — uploaded drawing files
- `HOME=/data` — PaddleOCR has no dedicated cache-dir setting; it always downloads model
  weights to `$HOME/.paddleocr`, so `HOME` is pointed at the volume to keep that cache warm
  across redeploys (avoids a slow re-download on every new deployment).

This was verified: after changing `ALLOWED_ORIGINS` (which triggers a Railway redeploy), the
demo drawings loaded before the redeploy were still present afterwards.

## Backend container

`backend/Dockerfile` installs system libs needed by OpenCV/PaddleOCR
(`libgomp1 libglib2.0-0 libsm6 libxext6 libxrender1 libgl1`), then replicates the documented
safe install order from `backend/requirements.txt` / README ("OCR vs. AI Vision
Interpretation"): install everything except `paddleocr` normally, then
`pip install --no-deps paddleocr==2.7.3`, then `pip install pyclipper imgaug lmdb requests`.

`backend/docker-entrypoint.sh` runs at container **start** (not build time, since the volume
isn't mounted yet during build): `alembic upgrade head`, then `python create_admin.py`
(idempotent — only creates an admin if the users table is empty), then
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` (Railway injects `$PORT`).

## Environment variables set on Railway (`mbanalysis-backend` service)

| Variable | Notes |
|---|---|
| `JWT_SECRET` | Randomly generated (`secrets.token_hex(32)`). Not reproduced here — retrieve with `railway variables` if you need it (you generally don't; it's only read by the server). |
| `ADMIN_EMAIL` | `admin@mbanalysis.local` |
| `ADMIN_PASSWORD` | Randomly generated, reasonably strong. Retrieve with `railway variables` to actually log in, or reset it (see "Rotating secrets" below). |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | `sqlite:////data/mbanalysis.db` (on the volume) |
| `UPLOAD_DIR` | `/data/uploads` (on the volume) |
| `HOME` | `/data` (so PaddleOCR's model cache lands on the volume) |
| `ALLOWED_ORIGINS` | `https://mbanalysis-frontend.vercel.app,https://mbanalysis-frontend-r0h24u3z6-ajhay07s-projects.vercel.app` |
| `MAX_UPLOAD_MB` | `25` |
| `ALLOWED_EXTENSIONS` | `.pdf,.png,.jpg,.jpeg,.tif,.tiff` |
| `OCR_ENABLED` / `OCR_LANGUAGE` / `OCR_USE_GPU` / `PDF_RENDER_DPI` / `OCR_CONFIDENCE_THRESHOLD` / `OCR_PREPROCESS_DESKEW` / `OCR_PREPROCESS_CLAHE` / `OCR_PREPROCESS_DENOISE` | Same defaults as `backend/.env.example` |
| `OPENAI_API_KEY` | **Left unset.** App runs in demo mode (`ai_mode: "demo"` from `/api/health`) — no OpenAI calls, no cost. |

### Adding a real OpenAI key later

```
cd backend
railway variables --set "OPENAI_API_KEY=sk-..."
```
This triggers an automatic redeploy; `ai_mode` will switch to `"openai"` on `/api/health` once
it's back online.

### Rotating `JWT_SECRET` / admin password

```
cd backend
railway variables --set "JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')"
```
Rotating `JWT_SECRET` invalidates all existing login sessions (expected — same as a restart in
dev mode). To reset the admin password, since `create_admin.py` refuses to run once any user
exists, either delete the `users` row via a one-off script/shell on the service, or add a
proper password-reset/admin-management endpoint later.

## Environment variables set on Vercel (`mbanalysis-frontend` project, Production)

| Variable | Value |
|---|---|
| `BACKEND_URL` | `https://mbanalysis-backend-production.up.railway.app` — read by `frontend/next.config.mjs`'s rewrite of `/api/*` |

## Redeploying after future code changes

**Backend:**
```
cd backend
railway up --detach
```
(No GitHub auto-deploy is wired up for the backend; this must be run manually, or you can wire
up Railway's GitHub integration from the Railway dashboard if you'd prefer push-to-deploy.)

**Frontend:**
```
cd frontend
vercel --prod
```
(A GitHub repo is linked via `vercel link`; Vercel may also deploy automatically on pushes to
`main` depending on the Git integration settings in the Vercel dashboard.)

## Public demo login ("Try the demo")

The login page (`frontend/src/app/login/page.tsx`) has a second, visually distinct button below
the real email/password form: **"Try the demo (read-only)"**. It calls a public, unauthenticated
backend endpoint, `POST /api/auth/demo-login` (`backend/app/routers/auth.py`), which logs the
visitor in as a fixed account (`demo@mbanalysis.local` by default, overridable via the
`DEMO_EMAIL` env var) with role **`viewer`**.

- **No password exists for this account.** The endpoint takes no credentials — it lazily creates
  the demo user (idempotent; a no-op if it already exists) with a random, never-stored,
  never-transmitted password purely to satisfy the `hashed_password` NOT NULL column, then issues
  the same httpOnly JWT cookie the normal `/api/auth/login` flow issues. There is nothing to leak
  or guess, which is the point: it's not "a weak demo password", it's "no password at all".
- **Why `viewer` and not `engineer`:** every mutating endpoint in the app (approving/rejecting
  BOMs, editing components, deleting drawings, loading/resetting demo data, generating BOMs) is
  already gated by `require_role("admin", "engineer")` in `app/auth.py`. `viewer` is excluded by
  that gate, so a visitor who clicks the demo button gets full read access to the 3 seeded demo
  projects (drawings, BOM trees, procurement data, calculations) but any mutation attempt returns
  **403 Forbidden** — verified live (see below), not just inferred from reading the code.
- **The owner's real admin account and password are completely unaffected** — this feature only
  adds a second, strictly-less-privileged login path; the existing `/api/auth/login` form,
  `ADMIN_EMAIL`/`ADMIN_PASSWORD`, and `create_admin.py` bootstrap are untouched.
- Live verification performed against the production Railway backend
  (`https://mbanalysis-backend-production.up.railway.app`):
  - `POST /api/auth/demo-login` → 200, sets cookie, `GET /api/auth/me` → `role: "viewer"`.
  - `GET /api/demo/status` as the demo viewer → `{"demo_drawings": 3, "loaded": true}` (the demo
    data was already loaded in production from the prior deployment session).
  - `GET /api/dashboard/metrics`, `GET /api/drawings` as the demo viewer → 200, real data
    returned (read access works).
  - `POST /api/demo/load`, `DELETE /api/drawings/{id}`, `POST /api/boms/{id}/approve` as the demo
    viewer → all **403 Forbidden** (mutation blocked, as intended).
- Not rate-limited at the application layer (same as the real login endpoint). Put a
  reverse-proxy/WAF rate limit on `/api/auth/demo-login` in front of Railway if abuse becomes a
  concern — it can only ever mint read-only sessions, so the worst case is noisy traffic, not a
  privilege or data-integrity issue.
- Minor follow-up (not yet done): the dashboard still renders the "Load Demo Project" / "Reset
  Demo Data" buttons for a viewer session — clicking them correctly fails with 403, but hiding
  them client-side for `role === "viewer"` would be a cleaner UX polish.

## Known limitations / things to keep an eye on

- **Cold start / OCR model download:** the very first OCR call after a fresh deploy (empty
  volume) downloads PaddleOCR's detection/recognition/classification model weights before
  answering — this can take a noticeably long time and the first request may feel like it
  hung. Subsequent requests reuse the cached weights under `/data/.paddleocr`. Consider
  pre-warming the cache in the Docker build (running a dummy OCR call during `docker build`) if
  this first-request latency becomes a problem in practice.
- **Railway volume size:** 500MB. SQLite DB + uploaded drawings + the PaddleOCR model cache all
  share this volume. Monitor usage (`railway volume list`) and resize if needed.
- **Single-instance SQLite:** fine for this deployment's scale, but note SQLite doesn't support
  multiple concurrent writers across replicas — don't scale the Railway service beyond 1
  instance without migrating to Postgres first (the app already supports swapping
  `DATABASE_URL` to Postgres, per `.env.example`).
- **No GitHub auto-deploy for the backend** — deploys are via `railway up` from a local
  checkout. If you want push-to-deploy, connect the GitHub repo in the Railway dashboard.
