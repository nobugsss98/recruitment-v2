# TalentFlow Frontend

Dark, animated React console for the recruitment platform. Consumes the
recruitment-v2 backend API (base URL from `VITE_API_URL`).

## Stack

Vite 5 · React 18 · TypeScript (strict) · Tailwind CSS · framer-motion ·
react-router-dom v6 · @tanstack/react-query v5 · axios · recharts · sonner.

## Environment

| Variable        | Default                 | Description                        |
| --------------- | ----------------------- | ---------------------------------- |
| `VITE_API_URL`  | `http://localhost:8000` | Backend API base URL (no trailing slash) |

Copy `.env.example` to `.env` and adjust for your backend host.

## Run locally

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies nothing — the app calls `VITE_API_URL` directly, so make
sure the backend allows the browser origin (CORS).

## Build

```bash
npm run build      # tsc --noEmit && vite build → dist/
npm run preview    # serve dist/ locally
```

## Docker (production)

```bash
docker build --build-arg VITE_API_URL=https://api.example.com -t talentflow-frontend .
docker run -p 8080:80 talentflow-frontend
```

Multi-stage build: `node:22-alpine` compiles the app, `nginx:1.27-alpine` serves
`dist/` with SPA fallback (`nginx.conf`) and long-term caching for `/assets`.

## Routes & roles

| Route                    | hr | interviewer | ceo |
| ------------------------ | -- | ----------- | --- |
| `/` Dashboard            | ✅ | ✅          | ✅  |
| `/jobs/:id` Job detail   | ✅ | read-only   | ✅  |
| `/jobs/:id/screening`    | ✅ | ✅          | —   |
| `/interviews`            | ✅ | ✅          | —   |
| `/executive`             | ✅ | —           | ✅  |

Auth: JWT access + refresh tokens in `localStorage`. Axios attaches
`Authorization: Bearer <token>` and, on a single 401, refreshes once
(single-flight across concurrent requests) before retrying; if refresh fails the
session is cleared and the user is sent to `/login`.

## API notes

- `POST /jobs/{id}/clone-form` requires a `GoogleFormQuestionSet` body — the UI
  first calls `POST /jobs/{id}/generate-form-questions`, previews the questions,
  then clones.
- `POST /interviews/{id}/recording` is multipart with `recording` (file) +
  `interview_date` (the UI stamps today's date).
- `POST /applications/{id}/hr-override` needs `hr_username` — the UI sends the
  signed-in user's full name.
- Executive queue is aggregated client-side: one
  `GET /jobs/{id}/applications?pipeline_status=pending_ceo_decision` per job.
