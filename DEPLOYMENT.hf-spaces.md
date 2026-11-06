# Moving the backend off Railway: Hugging Face Spaces + Supabase

Free, persistent replacement for Railway. Two services, both free tier:
- **Hugging Face Spaces** (Docker) runs the FastAPI/PaddleOCR backend - but has no persistent
  disk on the free tier, so everything written to local disk is lost on restart/redeploy.
- **Supabase** (free tier) supplies a persistent Postgres database and file storage bucket, so
  your drawings/analyses/BOMs survive restarts even though the Space's own disk doesn't.

Do these in order - Supabase first, since the Space needs its connection details.

## 1. Create the Supabase project

1. Go to supabase.com, sign up free, "New project". Pick any name/region; save the database
   password it generates (you'll need it for `DATABASE_URL` below).
2. Once created, go to **Project Settings → Database → Connection string** (URI tab). Copy it -
   looks like `postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres`.
   This is your `DATABASE_URL`.
3. Go to **Project Settings → API**. Copy the **Project URL** (`SUPABASE_URL`) and the
   **`service_role` secret key** (`SUPABASE_SERVICE_KEY` - NOT the `anon` public key; the
   service role key is required to write files, and must never be exposed to the frontend).
4. Go to **Storage**, create a new bucket named `drawings` (private, not public - the backend
   serves files itself, nothing needs direct public bucket access).

## 2. Run migrations against Supabase once, from your own machine

```bash
cd backend
# PowerShell:
$env:DATABASE_URL = "postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres"
pip install psycopg2-binary
alembic upgrade head
```
This creates all the tables in Supabase. You only need to do this once (and again after any
future migration you add).

## 3. Create the Hugging Face Space

1. huggingface.co, sign up free, **New Space**. Pick a name, SDK = **Docker**, visibility =
   your choice (private is fine - free either way).
2. It gives you a git URL like `https://huggingface.co/spaces/<you>/<space-name>`. Clone it
   locally somewhere separate from this repo:
   ```bash
   git clone https://huggingface.co/spaces/<you>/<space-name> mbanalysis-space
   ```
3. Copy this repo's `backend/` folder contents into that clone's ROOT (not into a `backend/`
   subfolder - the Space's own Dockerfile must be at the repo root):
   ```bash
   # from the MBAnalysis repo root
   cp -r backend/. ../mbanalysis-space/
   cd ../mbanalysis-space
   git add .
   git commit -m "Deploy backend"
   git push
   ```
   Repeat this copy+push whenever you want to deploy a backend change (see the optional
   GitHub Action below to automate it).

## 4. Set the Space's secrets

In the Space's **Settings → Variables and secrets**, add these as **secrets** (not plain
variables - they're sensitive):

| Name | Value |
|---|---|
| `DATABASE_URL` | the Supabase connection string from step 1.2 |
| `SUPABASE_URL` | from step 1.3 |
| `SUPABASE_SERVICE_KEY` | from step 1.3 (the service_role key) |
| `JWT_SECRET` | any long random string (e.g. `openssl rand -hex 32`) |
| `ALLOWED_ORIGINS` | your Vercel frontend's URL, e.g. `https://mbanalysis-frontend.vercel.app` |
| `ADMIN_EMAIL` | your login email (bootstraps the first admin user on first boot) |
| `ADMIN_PASSWORD` | your login password |

`SUPABASE_STORAGE_BUCKET` only needs setting if you named the bucket something other than
`drawings`.

The Space rebuilds automatically after you save secrets or push a new commit.

## 5. Point the frontend at the new backend

In Vercel, Project Settings → Environment Variables, set `BACKEND_URL` to the Space's URL
(`https://<you>-<space-name>.hf.space`), then redeploy the frontend (or just wait for the next
push - Vercel picks up env var changes on the next deploy).

## 6. Verify

Open the Space's URL + `/api/health` in a browser - should return
`{"status":"ok","ai_mode":"deterministic","paddleocr_importable":true}`. Then open the frontend
and confirm you can log in and see your drawings (same data as before, since it's reading from
the same Supabase database the old Railway deployment would have needed anyway).

## Optional: auto-deploy from GitHub (replaces Railway's auto-deploy)

A GitHub Action that pushes `backend/` to the Space on every push to `main`, so you get the
same "push and it deploys" workflow you had on Railway:

1. On Hugging Face, go to **Settings → Access Tokens**, create a token with `write` access.
2. In the GitHub repo, **Settings → Secrets and variables → Actions**, add `HF_TOKEN` (the
   token) and `HF_SPACE` (e.g. `<you>/<space-name>`).
3. Ask Claude to add the workflow file once you're ready for this - it's a short addition and
   easiest to verify together rather than guessing your exact Space name/token setup in advance.

## What still resets on restart (and why that's OK)

Page-preview PNGs (rendered from the PDF during analysis) are NOT backed up to Supabase -
they're cheap to regenerate (the next "Re-run Analysis" recreates them) and backing them up
would mean extra network calls on every single page render for no real benefit. Everything that
actually matters - the drawings database, BOMs, indents, and the original uploaded PDF files -
lives in Supabase and survives restarts.
