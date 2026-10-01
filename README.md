# DataRopes Recruitment Tool v2

Modernized full-stack rebuild of the Recruitment SOP tool.

- **Backend**: FastAPI (Python 3.12) — see `backend/README.md`
- **Frontend**: React 18 + Vite + TypeScript — see `frontend/README.md`

## Quick start

1. Copy `.env.example` files and fill in credentials:
   - `backend/.env` — Supabase, Gemini, Google Forms, JWT secret
   - `frontend/.env` — `VITE_API_URL`
2. Run migrations in `supabase/migrations/` against your Supabase project.
3. Seed the first HR admin: `python -m scripts.seed_admin` (from `backend/`, with `ADMIN_EMAIL` / `ADMIN_PASSWORD` set).
4. Backend: `uvicorn app.main:app --reload` (from `backend/`)
5. Frontend: `npm run dev` (from `frontend/`)

Or run everything with Docker Compose from the repo root:

```bash
docker compose up --build
```

## Repo layout

- `backend/` — FastAPI API, JWT auth + RBAC, structured logging, audit trail, pytest suite
- `frontend/` — React SPA with animated dark UI, role-gated pages
- `supabase/migrations/` — Postgres schema migrations (base tables, users + audit_logs)
