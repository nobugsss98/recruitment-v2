# DataRopes Recruitment Tool — Backend (v2)

FastAPI backend for the recruitment SOP tool: job setup, Google Forms cloning,
AI screening sync, numbered interview rounds with local MP3 storage, and CEO
final decisions. This v2 adds JWT authentication with role-based access
control, structured JSON logging, and an audit trail.

## Requirements

- Python 3.12
- A Supabase project (hosted Postgres) with the migrations applied
- Google Cloud credentials (only for form cloning / sync)

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in values. All settings live in
`app/config.py` (pydantic-settings):

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini text generation / screening |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Text model ID |
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Server-only service-role key (never expose to browsers) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | — | Service-account JSON for Drive/Forms |
| `GOOGLE_OAUTH_CLIENT_FILE` | — | OAuth desktop-app client JSON (takes priority when set) |
| `GOOGLE_OAUTH_TOKEN_FILE` | — | Cached OAuth refresh token |
| `GOOGLE_FORM_TEMPLATE_ID` | — | Drive template containing the résumé-upload question |
| `GOOGLE_DRIVE_FOLDER_ID` | — | Optional destination folder for cloned forms |
| `RECORDINGS_DIR` | `./backend/recordings` | Interview recordings root (relative to repo root) |
| `JWT_SECRET_KEY` | — | **Required** for auth; sign access/refresh tokens |
| `ACCESS_TOKEN_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | First HR admin for `scripts.seed_admin` |

## Database migrations

Apply the SQL files in `../supabase/migrations/` to your Supabase project in
filename order (Supabase CLI or SQL editor):

1. `20260928000000_init_recruitment_schema.sql` — jobs, candidates, applications, interviews, enums, dashboard views, RLS
2. `20260930000000_add_form_submission_data.sql` — form answers + per-job response idempotency
3. `20261001000000_auth_audit.sql` — `users` + `audit_logs` (RLS enabled, service-role policies only)

## Seed the first HR admin

```bash
ADMIN_EMAIL=hr@example.com ADMIN_PASSWORD='change-me-please' python -m scripts.seed_admin
```

Idempotent: exits 0 without changes if the email already exists. Writes an
audit entry on creation.

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`GET /health` returns `{"status":"ok"}` without credentials.

## Tests

```bash
python -m pytest
```

The suite uses fake Supabase, Gemini, Drive, and Forms clients — no real
credentials needed.

## Auth & RBAC

- `POST /api/v1/auth/login` — email + password → `{access_token, refresh_token, token_type, user}`
- `POST /api/v1/auth/refresh` — refresh token → new token pair (rotated)
- `GET /api/v1/auth/me` — current user

Roles: `hr` | `interviewer` | `ceo` (see `app/api/deps.py`).

| Endpoints | Who |
|---|---|
| Create/update jobs, generate-jd, generate-form-questions, clone-form, linkedin-blurb, sync, hr-override, move-to-ceo, schedule interview, delete interview, recording upload | `hr` only |
| final-decision | `ceo` only |
| List jobs, job applications, candidate history, dossier, interview list, interview feedback PATCH | any authenticated role |

## Logging & audit

- structlog JSON logs via `app/utils/logging.py`; every response carries an
  `X-Request-ID` header (client-supplied value is echoed).
- Logged: request lifecycle, login success/failure, sync runs (counts only),
  AI calls (model name + latency, never prompt text), errors with context.
  Secrets and raw resume text are never logged.
- `app/services/audit.py` writes to `audit_logs` on: job created, sync run,
  HR override, interview scheduled, final decision, login, user creation.
  Audit writes are best-effort and never break the main flow.

## Layout

```
backend/
  app/
    main.py                 # FastAPI entrypoint (CORS, request-ID middleware)
    config.py               # pydantic-settings
    api/
      router.py             # /health + /api/v1 assembly
      deps.py               # get_current_user, require_roles(...)
      v1/                   # auth, jobs, candidates, applications, interviews
    database/crud/          # all DB access (jobs, candidates, interviews, users, audit)
    schemas/                # Pydantic v2 models (unknown fields rejected)
    prompts/                # jd, screening, form-question prompt builders
    services/
      ai/                   # TextAIProvider contract + Gemini adapter (store=False)
      supabase_service.py   # lazy Supabase client
      google_forms.py       # Drive clone + Forms API
      form_sync_service.py  # paginated sync, anonymize, AI screen, idempotent
      local_media_service.py# recording storage/verification
      auth_service.py       # bcrypt + JWT
      audit.py              # audit trail writer
    utils/                  # file_handler, anonymizer, logging
  scripts/seed_admin.py     # first HR admin (idempotent)
  tests/                    # pytest suite (fake clients)
  Dockerfile
  requirements.txt
  .env.example
```
