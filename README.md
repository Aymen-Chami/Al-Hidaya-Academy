# Al-Hidaya-Academy

Sunday School class sign-up system for Al Hidayah Academy.

| Part | Where | Status |
|---|---|---|
| Frontend (React 19 + Vite) | `src/` | Prototype UI. Still uses `localStorage` and shared passcodes. |
| Backend (FastAPI + PostgreSQL) | `backend/` | Accounts, roles (family / teacher / management / principal), server-enforced seats and waitlists, approval workflow, email. See [backend/README.md](backend/README.md). |
| Docker | `docker-compose.yml`, `docker-compose.override.yml`, `backend/Dockerfile`, `web.Dockerfile`, `nginx/` | Dev stack (API with hot reload + Postgres + Mailpit) and a production-like stack (nginx serving the React build and proxying `/api`). |

## Quick start

```bash
cp .env.example .env
docker compose up -d --build                        # API :8000 (docs at /api/docs), Mailpit :8025, Postgres :55432
docker compose exec api python -m app.cli seed      # optional demo data (password: Password123!)
npm install && npm run dev                          # frontend on :5173 (proxies /api to the API)
```

Production-like (nginx + React build + API, no dev overrides):

```bash
docker compose -f docker-compose.yml up -d --build  # http://localhost:8080
```

Next step: wire the React UI to the API. That means replacing the `window.storage` shim and the
passcode panel with the account and enrollment endpoints, and adding the Principal's approval
dashboard.

---

## Frontend notes (Vite template)

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).
