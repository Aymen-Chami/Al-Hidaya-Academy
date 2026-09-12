# Al-Hidaya-Academy

Sunday School class sign-up system for Al Hidayah Academy.

| Part | Where | Status |
|---|---|---|
| Frontend (React 19 + Vite) | `src/` | Wired to the API: accounts (email code + password), family sign-up with per-child status, teacher claims, class management, Principal approval queue, people admin. |
| Backend (FastAPI + PostgreSQL) | `backend/` | Accounts, roles (family / teacher / management / principal), server-enforced seats and waitlists, approval workflow, email. See [backend/README.md](backend/README.md). |
| Docker | `docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.tls.yml`, `backend/Dockerfile`, `web.Dockerfile`, `nginx/`, `caddy/` | Dev stack (API with hot reload + Postgres + Mailpit) and a production stack (Caddy for HTTPS → nginx serving the React build → API → Postgres). |

## Quick start

```bash
cp .env.example .env
docker compose up -d --build                        # API :8000 (docs at /api/docs), Mailpit :8025, Postgres :55432
docker compose exec api python -m app.cli seed      # optional demo data (password: Password123!)
npm install && npm run dev                          # frontend on :5173 (proxies /api to the API)
```

Production-like on your machine (nginx + React build + API, no dev overrides, no TLS):

```bash
docker compose -f docker-compose.yml up -d --build  # http://localhost:8080
```

Demo accounts after `seed` (password `Password123!`): `principal@example.com`, `manager@example.com`,
`teacher1@example.com`, `family1@example.com` (more in `backend/README.md`). Sign-up and password-reset
codes are emailed; in development they land in Mailpit at http://localhost:8025.

## Production

Caddy terminates HTTPS in front of nginx and renews the certificate itself:

```bash
cp .env.production.example .env   # secrets, PUBLIC_DOMAIN, SMTP relay
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

```
internet ──443──> caddy ──> web (nginx) ──> api (FastAPI) ──> db (Postgres)
```

Only Caddy is published; nginx, the API and the database stay on the internal Docker network.
Full walkthrough for a fresh AWS box — DNS, the first Principal account, email, backups:
**[DEPLOY.md](DEPLOY.md)**.

## Frontend structure

| Where | What |
|---|---|
| `src/api/client.js` | `fetch` wrapper: same-origin `/api/v1`, cookie session, throws `ApiError` with the server's message. |
| `src/api/endpoints.js` | One function per backend endpoint, grouped by audience (auth, catalog, family, teacher, admin). |
| `src/auth/` | Session state (`GET /auth/me`), login/logout, role helpers. A 401 anywhere drops back to logged-out. |
| `src/lib/hooks.js` | `useResource` (load + poll while the tab is visible), `useAction` (busy state + toast + refresh), hash router. |
| `src/ClassSignupApp.jsx` | App shell: routes, role-aware nav, account menu, toasts. |
| `src/views/` | One file per screen: sign-up sheet, auth, my children, teacher, classes, approvals, people, schedule. |
| `src/components/ui.jsx` | Presentational pieces (period cards, empty/error/loading states, pills, confirm strip…). |

Routes are hash-based (`#/manage`, `#/approvals`, …) so refreshes and deep links work with the
nginx SPA fallback. Every business rule stays on the server; the UI only reflects its state.

---

## Frontend notes (Vite template)

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).
