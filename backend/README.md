# Al Hidayah Academy — Sign-up API

FastAPI + PostgreSQL backend for the Sunday School sign-up system. It replaces the prototype's
`localStorage` + shared passcodes with real accounts, server-enforced seat limits, and a
Principal approval workflow. The prototype (`src/ClassSignupApp.jsx`) is the behaviour spec.

- **Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 17, uv.
- **Docs:** interactive API docs at `/api/docs` (disabled when `ENV=production`).

## Quick start (Docker)

From the repository root:

```bash
cp .env.example .env                      # dev defaults work as-is
docker compose up -d --build              # db + migrations + API (hot reload) + Mailpit
docker compose exec api python -m app.cli seed          # demo users/classes (password: Password123!)
```

| What | Where |
|---|---|
| API | http://localhost:8000/api/v1 |
| Swagger UI | http://localhost:8000/api/docs |
| Mailpit (all outgoing email) | http://localhost:8025 |
| Postgres | `localhost:55432` (user/db `alhidaya`, password from `.env`) |

The React app runs on the host with `npm run dev` (http://localhost:5173). Vite proxies `/api` to
the API, so everything is same-origin and the session cookie works. To serve the built React app
through nginx instead: `docker compose --profile web up -d` (http://localhost:8080).

**First Principal on a fresh database:**

```bash
docker compose exec api python -m app.cli bootstrap-principal --email you@school.org --first-name Amina --last-name Rahman
```

Then sign up with that email (you'll get a code in Mailpit) to choose a password. The account
keeps its Principal role. After that, the Principal creates staff accounts from the API
(`POST /api/v1/admin/users`).

## Running tests

Tests run against a real Postgres. A `<db>_test` database is created and migrated
automatically, and truncated before each test.

```bash
docker compose exec api pytest                  # inside the dev container
# or on the host (needs the dev db on :55432):
cd backend && uv sync && uv run pytest
RUN_SLOW=1 uv run pytest -k long                # + 40 long randomized runs
uv run ruff check . && uv run ruff format --check .
```

After every test, conftest checks all of the enrollment invariants listed below.

What the suite covers:
- **Races.** 20 parallel sign-ups for the last seat must produce exactly one success. A control
  test with the lock removed must overbook, which proves the race test can fail.
- **Fuzzing.** Seeded random sequences of operations.
- **RBAC matrix.** Every route is tested for every role. A new route with no access rule fails the build.
- **Privacy.** Each audience's responses are checked for the fields they may contain.
- **Migrations.** `alembic check` finds no drift, and upgrade → downgrade → upgrade round-trips cleanly.

## Architecture

```
app/
  main.py              app factory, routers, error handlers, Origin check, outbox worker (lifespan)
  cli.py               bootstrap-principal | seed | check-invariants
  core/                settings, clock, security (argon2, tokens, HMAC codes), CSRF/Origin middleware
  db/                  engine + session factory, naming conventions
  models/              SQLAlchemy tables (users, students, classes, enrollments, waitlist_entries,
                       sessions, email_codes, outbox_emails, audit_events)
  schemas/             Pydantic models, one module per audience (public/family/teacher/admin/auth)
  api/routes/          HTTP layer — thin; delegates to services
  services/auth/       sign-up codes, sessions, login/reset flows
  services/engine/     the enrollment engine: every seat/waitlist/class/teacher mutation
  services/queries/    read models per audience (catalog, family overview, teacher board, admin)
  services/notify/     transactional email outbox, templates, SMTP/console/memory backends, worker
migrations/            Alembic (hand-reviewed; partial unique indexes back the invariants)
tests/
```

### The enrollment engine (`services/engine/`)

Every mutation that touches seats runs inside `engine_tx()`. That is one transaction whose first
statement is `pg_advisory_xact_lock(...)`, a single global lock.

**Why one global lock?**
- Writes are rare and quick at this scale, so serializing them costs nothing.
- Every check-then-write becomes race-free and deadlock-free: last seat, one class per period,
  waitlist cascades that span several classes.
- Partial unique indexes in Postgres are a second line of defence.

**Writing inside the engine.** The engine writes with explicit Core statements in a fixed order,
for example deleting the old enrollment before inserting the new one. SQLAlchemy's ORM flush would
reorder those and trip the unique indexes.

**Emails and audit entries** are queued in the same transaction, so they exist only if the change
committed.

**Invariants** (`engine/invariants.py`, also `python -m app.cli check-invariants`):

| # | Rule | Enforced by |
|---|---|---|
| I1 | Pending + approved enrollments ≤ class capacity | engine lock |
| I2 | ≤ 1 pending/approved enrollment per child per period (`year` is its own bucket) | unique index |
| I3 | ≤ 1 enrollment row per child per class (re-applying revives the rejected row) | unique constraint |
| I4 | A child is never enrolled in and waitlisted on the same class | engine |
| I5 | A class with a free seat has an empty waitlist | engine |
| I6 | A child's waitlist ranks (1st/2nd/3rd) are unique | unique index |
| I7 | A teacher has ≤ 1 class per period; a "locked" class has a teacher | unique index + check |
| I8 | `enrollments.period` always equals its class's period | composite FK, `ON UPDATE CASCADE` |

### Business rules

**Roles**

| Role | Can do |
|---|---|
| `family` | Manage own children; sign up, drop, join waitlists, rank choices. |
| `teacher` | Claim one unclaimed published class per period; drop own claim unless staff-assigned ("locked"); see own rosters. |
| `management` | Class CRUD, publish, reorder, assign teachers, add/remove children. Read-only view of everything, including the approval queue. |
| `principal` | Everything Management can do, plus approve/reject enrollments, create staff accounts, change roles, deactivate users, delete children, read the audit log. |

Any account can register children, since staff are often parents too.

**Enrollment**
- A sign-up starts **Pending** and holds its seat until the Principal decides. There is no expiry timer.
- Only published classes with a teacher accept sign-ups.
- A child can hold one class per period, plus one "All Periods" (`year`) class.
- Rejecting an enrollment frees the seat. The family may re-apply later, which reuses the same row.
- When staff add a child directly, it is **Pending** if Management did it and **Approved** if the Principal did.

**Waitlists**
- Joining is allowed only when the class is full.
- A child may wait for classes in a period where they already hold one.
- Ranks are 1st/2nd/3rd or unranked. Queue order is rank first, then join order.

**Promotion (a seat opens)**
- The top of the waitlist moves in.
- If that child already holds another class in the same period, they are *switched* out of it. That frees a seat there, which can cascade.
- A switched **approved** enrollment stays approved.
- The child's same-period waitlist entries ranked *below* the one that got them in are removed.
  Without this, they could later be pulled out of their 1st choice into their 2nd.
- The class keeps filling until it is full or its waitlist is empty. The prototype promoted only one child per pass.

**Class edits**
- Capacity can't go below the seats already held (409).
- A period change is refused if any teacher or child would be double-booked; the response lists who (409).
- Deleting a class emails affected families.

**Privacy**
- The public schedule (`GET /classes`) shows seat counts and the teacher's "First L." label only — never children's names.
- Teachers see their own rosters without family contact details.
- Staff views include family contact details, for cross-checking payments.

### Auth

**Sign-up** takes three calls:
1. `POST /auth/signup/request-code` always returns 202, so the response never reveals whether an email has an account.
2. `POST /auth/signup/verify-code` returns a single-use completion token.
3. `POST /auth/signup/complete` sets the password, creates the account and logs in.

**Codes**
- 6 digits, stored only as an HMAC.
- Valid for 15 minutes, with 5 attempts (counted atomically).
- One request per 60 s and at most 5 per hour, per email.

**Sessions**
- An opaque random token, stored as SHA-256.
- Sent in an `HttpOnly; SameSite=Lax` cookie. With `COOKIE_SECURE=true`, the cookie is also `Secure` and uses the `__Host-` prefix.
- Lasts 30 days and can be revoked: logout, password reset and deactivation all sign the user out.
- State-changing requests must come from the same origin or an `ALLOWED_ORIGINS` origin.

**Passwords**
- Hashed with Argon2, in a worker thread.
- Unknown emails get a dummy verification, so response timing doesn't reveal them.
- Failed logins back off exponentially.
- nginx rate-limits `/api/v1/auth/*` per IP.

**Email** goes through a transactional outbox (`outbox_emails`):
- A background worker in the API process sends it over SMTP.
- Failures retry with backoff.
- Codes are removed from a row once its email is sent.

## API map (`/api/v1`)

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Auth | `POST /auth/signup/{request-code,verify-code,complete}` · `POST /auth/login` · `POST /auth/logout` · `POST /auth/password-reset/{request-code,verify-code,complete}` · `GET/PATCH /auth/me` · `POST /auth/me/password` |
| Public | `GET /classes` · `GET /classes/{id}` |
| Family | `GET/POST /me/students` · `PATCH/DELETE /me/students/{id}` · `GET /me/overview` · `POST /enrollments` · `DELETE /enrollments/{id}` · `POST /waitlist` · `PATCH/DELETE /waitlist/{id}` |
| Teacher | `GET /teacher/classes` · `POST/DELETE /teacher/classes/{id}/claim` |
| Admin: classes | `GET/POST /admin/classes` · `GET/PATCH/DELETE /admin/classes/{id}` · `POST …/move` · `PUT/DELETE …/teacher` · `POST …/enrollments` · `DELETE /admin/enrollments/{id}` · `DELETE /admin/waitlist/{id}` |
| Admin: people | `GET/POST /admin/students` · `PATCH/DELETE /admin/students/{id}` · `GET/POST /admin/users` · `PATCH /admin/users/{id}` · `POST /admin/users/{id}/revoke-sessions` · `GET /admin/audit` |
| Approvals | `GET /admin/enrollments?status=&class_id=&period=` · `POST /admin/enrollments/{id}/approve` · `POST /admin/enrollments/{id}/reject` · `POST /admin/enrollments/approve-bulk` |

Errors always look like `{"error": {"code": "CLASS_FULL", "message": "…", "details": …}}`.
Branch on `code`; `message` is human-readable. The exact access rules per role live in
`tests/test_rbac.py`.

## Production

1. **Serve over HTTPS.** Put TLS in front of the `web` service (a load balancer, Caddy, or certbot).
2. **Set these in `.env`:**
   - `ENV=production`
   - `COOKIE_SECURE=true`
   - a random `SECRET_KEY` of 32+ characters: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `APP_BASE_URL=https://your-domain`
   - `ALLOWED_ORIGINS=https://your-domain`
   - a strong `POSTGRES_PASSWORD`
3. **Configure SMTP** with your provider's relay. For SendGrid: `smtp.sendgrid.net:587`, `SMTP_STARTTLS=true`, username `apikey`. Set SPF/DKIM on the sending domain.
4. **Start the stack** without the dev overrides:
   ```bash
   docker compose -f docker-compose.yml up -d --build
   ```
   The `migrate` service applies migrations before the API starts. The API image runs as a non-root user.
5. **Create the first Principal:**
   ```bash
   docker compose -f docker-compose.yml exec api python -m app.cli bootstrap-principal --email … --first-name … --last-name …
   ```
6. **Back up the `pgdata` volume**, e.g. with `pg_dump` on a schedule.

**New migrations:** after changing the models, run
`docker compose exec api alembic revision --autogenerate -m "…"`. Review the generated file,
especially partial indexes, then apply it with `alembic upgrade head`.
