---
title: MBAnalysis Backend
emoji: 📐
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
---

# MBAnalysis Backend (Hugging Face Space)

FastAPI backend for MB Metallic Bellows' drawing-intelligence app, running as a Docker Space.
See `DEPLOYMENT.hf-spaces.md` (repo root, one level up) for the full step-by-step setup -
creating the Space, wiring up Supabase for the database and file storage, and pointing the
Vercel frontend at this Space's URL.

Nothing in `app/` or `engineering_engine/` is Spaces-specific - this is the same backend that
ran on Railway. Only two things differ here:
- The Dockerfile runs as a non-root user (required by Spaces; harmless on Railway too).
- `DATABASE_URL`/`SUPABASE_URL`/`SUPABASE_SERVICE_KEY` point at Supabase instead of a local
  SQLite file + local disk, since a free Space has no persistent storage of its own - see
  `app/services/supabase_storage.py`.
