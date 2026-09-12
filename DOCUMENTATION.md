# Al Hidayah Academy — Sunday School Sign-up

Complete reference for the class sign-up system: what it does, the rules it enforces, how it is
built, and how to run and operate it.

- **New here?** Read §1–§4. That is the whole product.
- **Maintaining the code?** §5–§10.
- **Running the server?** §13–§14, plus [DEPLOY.md](DEPLOY.md).

---

## Table of contents

1. [What it is](#1-what-it-is)
2. [Roles](#2-roles)
3. [Using the app](#3-using-the-app)
4. [The rules the system enforces](#4-the-rules-the-system-enforces)
5. [Architecture](#5-architecture)
6. [Repository layout](#6-repository-layout)
7. [The frontend](#7-the-frontend)
8. [Data model](#8-data-model)
9. [The enrollment engine](#9-the-enrollment-engine)
10. [Accounts and security](#10-accounts-and-security)
11. [Email](#11-email)
12. [API reference](#12-api-reference)
13. [Configuration](#13-configuration)
14. [Running and operating it](#14-running-and-operating-it)
15. [Limits and deferred work](#15-limits-and-deferred-work)
16. [Glossary](#16-glossary)

---

## 1. What it is

Families enrol their children in Sunday School classes. Each class has a fixed number of seats
and runs in one of four periods. When a class fills up, families join its waitlist; when a seat
opens, the system moves the next child in automatically. Every enrolment waits for the
Principal's approval, and families are emailed at each step.

The system replaced a spreadsheet-and-passcode arrangement. The three things it exists to
guarantee:

1. **Seats can't be oversold.** Two parents clicking at the same instant for the last seat is a
   race the server resolves; exactly one wins.
2. **Nobody is double-booked.** A child holds at most one class per period; a teacher teaches at
   most one class per period.
3. **Nothing is decided by accident.** Enrolments are Pending until the Principal approves or
   rejects them, and every decision is emailed and written to an audit log.

## 2. Roles

Every account has exactly one role. Roles are cumulative in power, but each adds a distinct
screen rather than just more buttons.

| Role | Can do |
|---|---|
| **Family** | Add and edit their own children. Sign children up, drop them, join waitlists, rank waitlist choices. See the public schedule. |
| **Teacher** | Claim one unclaimed published class per period, and drop that claim unless staff assigned it. See their own rosters. |
| **Management** | Create, edit, publish, reorder and delete classes. Assign teachers. Add and remove children from classes. Read everything, including the approval queue. **Cannot approve.** |
| **Principal** | Everything Management can, plus: approve and reject enrolments, create staff accounts, change roles, deactivate accounts, delete children, read the audit log. |

**Anyone can register children.** Teachers and staff are often parents too, so every account —
whatever its role — has the family screens. Role only adds powers.

There is exactly one Principal-shaped hole to fill on a new install: the first Principal is
created from the command line (§14), and every other account after that is created either by a
family signing themselves up or by the Principal inside the app.

## 3. Using the app

### Creating an account

Three steps, by design — the email code proves the address works before a password exists.

1. **Enter your email.** The response is always the same ("if that address can receive email, a
   code is on its way"), whether or not an account already exists. That is deliberate: the page
   must not become a way to test which families are registered.
2. **Enter the 6-digit code** from the email. It lasts 15 minutes and allows 5 attempts.
3. **Enter your name and choose a password.** You are logged in immediately.

If the address already has an account, step 1 quietly sends a "you already have an account" email
with a reset link instead of a code. If staff created the account in advance, signing up
activates it and **keeps the role** staff assigned.

Forgotten passwords follow the same three steps and sign out every other device.

### Families

- **My children** — add each child once (first and last name). Children belong to your account.
- **Sign-up sheet** — pick a child, then a class per period. Each sign-up starts **Pending**.
- **Full class?** Join its waitlist and optionally rank your choices 1st, 2nd, 3rd. Rank beats
  join order, so a 1st choice joined late still outranks someone's unranked entry.
- **Status badges** — Pending (waiting on the Principal), Approved, Rejected. A rejection frees
  the seat; you can apply again later.
- Dropping an enrolment frees the seat immediately, which may pull a waitlisted child in.

Pages poll the server every few seconds while the tab is visible, so seat counts stay honest
without a refresh.

### Teachers

- **My classes** shows the classes you teach, including unpublished drafts, with each roster and
  its waitlist.
- **Claiming**: any published class with no teacher can be claimed, one per period. You can
  release a claim you made yourself. If staff assigned you, the claim is locked and only staff
  can change it.
- Teachers see children's names and statuses, never family contact details.

### Management

- **Classes** — create, edit, publish/unpublish, reorder, delete. Assign or remove a teacher.
- Add a child to a class directly (it lands as **Pending**), or remove one.
- Read-only view of the approval queue and of every roster, with family contact details so
  payments can be cross-checked.

### Principal

Everything above, plus:

- **Approvals** — the queue of Pending enrolments, filterable by class and period. Approve or
  reject individually, or approve in bulk. A rejection can carry a reason, which is included in
  the email to the family.
- Adding a child to a class as Principal enrols them **Approved** straight away.
- **People** — create staff accounts (they receive an invite email), change roles, deactivate
  accounts, force-sign-out a user, delete a child.
- **Audit log** — who did what, when.

## 4. The rules the system enforces

These are enforced on the server. The UI reflects them; it does not implement them.

### Periods

Four: `1`, `2`, `3` and `year` ("All Periods"). A child may hold **one class in each numbered
period, plus one `year` class** — the year bucket doesn't compete with the numbered ones.

### Seats

- A class has a capacity of 1–500.
- **Pending and Approved both hold a seat.** A pending enrolment is not a reservation queue; it
  occupies the seat until the Principal decides. There is no expiry timer — this was a deliberate
  choice, so a family is never bumped for being slow.
- A rejection frees the seat at once.

### Sign-up eligibility

A family can only sign up for a class that is **published and has a teacher**. Staff can enrol a
child into a draft or teacherless class, because staff are doing the setting up.

### Waitlists

- You may join only when the class is **full**. A class with a free seat never has a waitlist —
  if it did, someone would be waiting for a seat that was already available.
- A child may wait for a class in a period where they already hold one; being promoted then
  *switches* them (below).
- Ranks are 1st / 2nd / 3rd, or unranked. Queue order is **rank first, then join order**. A rank
  is unique per child: setting a rank clears it from their other entries.

### Promotion — what happens when a seat opens

Triggered by a drop, a rejection, a removal, a capacity increase, or a deleted child.

1. The class pulls in the top of its waitlist, and keeps pulling **until it is full or the
   waitlist is empty**.
2. If the promoted child already holds another class in that same period, they are **switched**:
   the old enrolment is removed and the new one takes its place. That frees a seat in the old
   class, which can promote someone there, and so on — a cascade.
3. A switched **Approved** enrolment stays Approved. The family isn't sent back to Pending for
   something the system did to them.
4. The child's waitlist entries in that period ranked **below** the one that got them in are
   removed. Without this, a child could later be pulled out of their 1st choice into their 2nd.

### Editing classes

- Capacity cannot drop below the seats already held — the API returns 409 rather than silently
  orphaning children.
- Changing a class's period is refused if it would double-book the teacher or any enrolled child;
  the error lists who.
- Raising capacity promotes as many waitlisted children as now fit.
- Deleting a class removes its enrolments and waitlist and **emails the affected families**.

### Teachers

- A teacher holds at most one class per period.
- Only role `teacher` may self-claim. Anyone who can teach (teacher, management, principal) can
  be *assigned* by staff.
- A staff assignment locks the class: the teacher cannot drop it.
- Demoting or deactivating a user unassigns them from every class they were teaching.

### Privacy

| Audience | Sees |
|---|---|
| Public (not logged in) | Published classes, seat counts, teacher label ("Amina R."). **No children's names.** |
| Family | Their own children only. Another family's child returns 404, not 403 — the API doesn't confirm that the id exists. |
| Teacher | Their own rosters: names and statuses. No family contact details. |
| Management / Principal | Everything, including family contact details. |

## 5. Architecture

**Development**

```
browser ──> vite :5173 ──/api──> api :8000 ──> postgres :55432
                                    │
                                    └──smtp──> mailpit :8025   (captures mail, sends nothing)
```

**Production**

```
internet ──443──> caddy ──> web (nginx) ──> api (FastAPI) ──> db (Postgres)
                   TLS       React build       /api/v1          pgdata volume
                             + /api proxy
```

Only Caddy is published. nginx, the API and the database are reachable only on the internal
Docker network. Everything is same-origin, which is what lets the session live in an
`HttpOnly` cookie with no CORS and no token in JavaScript.

**The stack**

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, plain CSS, `lucide-react` icons. No state library — server state plus polling. |
| API | Python 3.13, FastAPI, Pydantic v2, uvicorn |
| Data | PostgreSQL 17, SQLAlchemy 2 (async, asyncpg), Alembic |
| Email | aiosmtplib over a transactional outbox table |
| Auth | Argon2 (`pwdlib`), opaque session tokens, HMAC'd email codes |
| Serving | nginx (static + proxy + rate limit), Caddy (TLS) |
| Tooling | uv, ruff, pytest, oxlint |

**Why a proxy in front of the API at all?** Same-origin. The browser talks only to one host, so
the session cookie is sent on every `/api` request without CORS, and the cookie can stay
`HttpOnly` — unreadable by any script, which removes the whole class of token-theft XSS bugs.

## 6. Repository layout

```
.
├── src/                        React app (see §7)
├── backend/
│   ├── app/
│   │   ├── main.py             app factory, routers, error handlers, middleware, lifespan
│   │   ├── cli.py              bootstrap-principal | seed | check-invariants | send-test-email
│   │   ├── core/               settings, clock, security, errors, Origin-check middleware
│   │   ├── db/                 engine, session factory, naming conventions
│   │   ├── models/             SQLAlchemy tables and enums
│   │   ├── schemas/            Pydantic models, one module per audience
│   │   ├── api/routes/         HTTP layer — thin, delegates to services
│   │   └── services/
│   │       ├── auth/           codes, sessions, login/reset flows
│   │       ├── engine/         every seat/waitlist/class/teacher mutation
│   │       ├── queries/        read models per audience
│   │       └── notify/         outbox, templates, SMTP backends, worker
│   ├── migrations/             Alembic
│   └── tests/                  pytest against a real Postgres
├── nginx/                      static serving, /api proxy, rate limit, security headers
├── caddy/Caddyfile             TLS terminator
├── scripts/backup-db.sh        nightly pg_dump with retention
├── docker-compose.yml          production stack
├── docker-compose.override.yml development overrides (auto-loaded)
├── docker-compose.tls.yml      HTTPS overlay for production
├── DEPLOY.md                   AWS walkthrough
└── DOCUMENTATION.md            this file
```

## 7. The frontend

| Path | Purpose |
|---|---|
| `src/ClassSignupApp.jsx` | App shell: session, hash routing, role-aware navigation, toasts |
| `src/api/client.js` | `fetch` wrapper. Same-origin `/api/v1`, throws `ApiError` carrying the server's `code` and message |
| `src/api/endpoints.js` | One function per endpoint, grouped by audience |
| `src/auth/` | Session state from `GET /auth/me`, login/logout, role helpers |
| `src/lib/hooks.js` | `useResource` (poll while visible), `useHashRoute` |
| `src/views/` | One file per screen: `AuthView`, `SignupSheetView`, `ChildrenView`, `ScheduleView`, `TeacherView`, `ManageView`, `ApprovalsView`, `PeopleView` |
| `src/components/` | Shared UI: `ui.jsx`, `AddChildForm`, `PeriodArt` |

**Routes** are hash-based: `#/` is the sign-up sheet, plus `#/children`, `#/schedule`,
`#/teacher`, `#/manage`, `#/approvals`, `#/people` and `#/login`. `homeRouteFor()` decides where
each role lands after logging in — staff on Classes, teachers on My classes, everyone else on the
sign-up sheet.

**No client-side business logic.** Views render what the server returned and surface the server's
error message. A rule lives in exactly one place — the backend — so the UI can never disagree
with what actually happened.

**Freshness** comes from `useResource`, which re-fetches every ~7 s while the tab is visible,
keeps the last good data if a poll fails, and only shows an error when it has nothing to show.
There are no WebSockets: at this scale, polling is simpler and has no reconnect edge cases.

**Client state** is limited to one thing: which child is selected on the sign-up sheet, kept in
`localStorage` as a convenience. Everything else is server state.

## 8. Data model

Nine tables. Bigint identity primary keys, `timestamptz` everywhere, and enums stored as varchar
with a named CHECK constraint (easier to migrate than native Postgres enums).

| Table | Columns |
|---|---|
| `users` | `id, email, first_name, last_name, display_name, phone, password_hash, role, is_active, email_verified_at, failed_login_count, last_failed_login_at, created_at, updated_at` |
| `students` | `id, family_id, first_name, last_name, created_by, created_at` |
| `classes` | `id, name, description, period, capacity, teacher_id, teacher_locked, published, sort_order, created_at, updated_at` |
| `enrollments` | `id, student_id, class_id, period, status, source, created_by, decided_by, decided_at, rejection_reason, created_at, updated_at` |
| `waitlist_entries` | `id, student_id, class_id, priority, created_by, created_at` |
| `sessions` | `id, user_id, token_hash, created_at, expires_at, last_used_at, user_agent` |
| `email_codes` | `id, email, purpose, code_mac, expires_at, attempts, verified_at, completion_token_hash, completion_expires_at, consumed_at, created_at` |
| `outbox_emails` | `id, to_email, template, params, attempts, next_attempt_at, sent_at, last_error, created_at` |
| `audit_events` | `id, actor_id, action, entity_type, entity_id, details, created_at` |

Notes worth knowing:

- `users.password_hash` is nullable: a staff-created account has no password until the person
  signs up.
- `students.family_id` is nullable, for a walk-in child staff added with no parent account.
- `enrollments.period` is **denormalised on purpose** and tied to `classes(id, period)` by a
  composite foreign key with `ON UPDATE CASCADE`. Moving a class to another period rewrites its
  enrolments' period in the same statement, so the two can never disagree.

### Invariants

Eight properties that must hold at all times. `backend/app/services/engine/invariants.py`
expresses each as a SQL query that must return zero rows; the test suite checks all eight after
**every single test**, and `python -m app.cli check-invariants` checks them against production.

| # | Rule | Enforced by |
|---|---|---|
| I1 | Pending + Approved enrolments in a class ≤ its capacity | engine lock |
| I2 | ≤ 1 active enrolment per child per period (`year` is its own bucket) | partial unique index |
| I3 | ≤ 1 enrolment row per (child, class) — re-applying revives the rejected row | unique constraint |
| I4 | A child is never enrolled in and waitlisted on the same class | engine |
| I5 | A class with a free seat has an empty waitlist | engine |
| I6 | A child's waitlist ranks are unique | partial unique index |
| I7 | A teacher has ≤ 1 class per period; a locked class has a teacher | unique index + CHECK |
| I8 | `enrollments.period` equals its class's period | composite FK |

Four of the eight are enforced by the database itself, so even a bug in new code cannot violate
them — the write fails instead.

## 9. The enrollment engine

Everything that touches seats, waitlists, classes or teachers goes through
`backend/app/services/engine/`. Nothing else may write those tables.

### One global lock

Every mutation runs inside `engine_tx()`: a fresh transaction whose **first statement** is
`SELECT pg_advisory_xact_lock(4172026001)`. One global lock, held for the duration.

Why a single lock rather than per-class row locks:

- Writes are rare and finish in milliseconds at this scale, so serialising them costs nothing a
  user could perceive.
- Every check-then-act becomes race-free: "is there a free seat, then take it" cannot interleave.
- A promotion cascade touches an unpredictable set of classes. Fine-grained locks taken in a
  data-dependent order are how deadlocks happen; one lock cannot deadlock.

If the lock can't be acquired within `DB_LOCK_TIMEOUT_MS` (5 s), the API returns 503
`BUSY_RETRY` rather than hanging.

**Verified, not assumed:** a test fires 20 concurrent sign-ups at the last seat and asserts
exactly one 201 and nineteen 409s. A companion test with the lock removed must overbook — which
proves the first test is capable of failing.

### Explicit write order

The engine writes with SQLAlchemy Core statements in a deliberate order — delete the old
enrolment *before* inserting the new one, clear a rank before setting it. The ORM's unit of work
reorders flushes, which trips the partial unique indexes. Reads inside the lock are fresh Core
selects, so the identity map can't serve a stale row.

Creating an enrolment is an upsert:

```sql
INSERT INTO enrollments (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uq_enrollments_student_id_class_id
DO UPDATE SET status = 'pending', ... WHERE enrollments.status = 'rejected'
```

A family re-applying reuses their rejected row. If no row comes back, the child is already
enrolled, and the API answers `ALREADY_ENROLLED`.

### Promotion

```
queue = [classes that just gained a seat]
while queue:
    c = queue.pop()
    while seats_taken(c) < c.capacity and waitlist(c) is not empty:
        w = head of waitlist        # ORDER BY priority NULLS LAST, id
        delete w
        old = the child's active enrolment in c.period, if any
        if old:
            delete old              # before the insert — order matters
            queue.push(old.class_id)
        upsert enrollment(c, status = approved if old was approved else pending, source = waitlist)
        delete the child's c.period waitlist entries ranked below w
        emit promoted email + audit event
```

It always terminates: every iteration removes at least one waitlist entry.

### Emails and audit entries are transactional

Both are written **inside** the same transaction as the change. An email therefore exists only if
the change committed, and a committed change always has its email. No "approved but nobody was
told", no "told but not approved".

## 10. Accounts and security

### Sign-up and reset codes

- 6 digits, stored **only as an HMAC** keyed by `SECRET_KEY` — a database leak yields no usable
  codes.
- 15-minute lifetime, 5 attempts. The attempt counter is a single atomic `UPDATE`, so parallel
  guesses can't each get a fresh budget.
- One request per 60 s per address, 5 per hour.
- Verifying returns a **single-use completion token** (30 min), stored hashed. Two concurrent
  completions: one wins.
- Once the email is sent, the code is scrubbed from the outbox row.

### Sessions

- A random 32-byte opaque token, stored as SHA-256. The database never holds anything that can be
  replayed as a session.
- Delivered in an `HttpOnly; SameSite=Lax` cookie named `alh_session`, or
  `__Host-alh_session` when `COOKIE_SECURE=true` — the `__Host-` prefix makes the browser refuse
  the cookie unless it is Secure, host-only and `Path=/`.
- 30-day lifetime. `last_used_at` is written at most once every 5 minutes, to avoid a write on
  every request.
- Revoked by logout, by a password reset (which kills every session), and by deactivation.

### Passwords

- Argon2id, 64 MB / 3 passes / 4 lanes, run in a worker thread so hashing never blocks the event
  loop.
- An unknown email still gets a dummy hash verification, so response timing doesn't reveal which
  addresses exist.
- Unknown email and wrong password return the identical error.
- After 5 failures an account backs off exponentially, 30 s doubling to 15 minutes.

### Request protection

- **Origin check**: any unsafe method (POST/PUT/PATCH/DELETE) carrying an `Origin` header must be
  same-origin or listed in `ALLOWED_ORIGINS`, else 403 `BAD_ORIGIN`. With `SameSite=Lax` that is
  a second layer, not the only one.
- **Rate limiting**: nginx throttles `/api/v1/auth/*` to 30 requests/minute per IP with a burst
  of 20, answering with the same JSON error shape the API uses. It keys on the real client IP,
  taken from `X-Forwarded-For` but trusted **only** from the Docker networks — a public client
  cannot spoof it, and a single attacker cannot exhaust everyone's budget.
- **Security headers** on every response: `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`.
- **Per-audience response schemas.** There is no shared schema with optional sensitive fields —
  the family, teacher and admin views are separate Pydantic models, so a field cannot leak by
  being forgotten. A test asserts the exact key set each audience receives.
- **No stack traces or echoed input** in error responses. Validation errors never reflect the
  submitted value, so a password can't end up in a log through an error message.
- **Access rules are tested as a matrix.** `tests/test_rbac.py` enumerates every route against
  every role; a new route with no entry fails the build. It is impossible to ship an unguarded
  endpoint by forgetting one.

## 11. Email

Mail is not sent inline. Instead a row is written to `outbox_emails` in the same transaction as
the change, and a worker inside the API process delivers it.

- The worker claims due rows with `FOR UPDATE SKIP LOCKED`, so several API processes never send
  the same message twice.
- Sending happens **outside** the transaction — SMTP is slow and can hang; no database lock waits
  on the network.
- A failure is recorded with `attempts + 1` and retried with backoff: 30 s doubling to a 1-hour
  ceiling, giving up after 8 attempts. `last_error` keeps the reason.
- Sent rows are kept 30 days for troubleshooting, with the code scrubbed.

**Templates** (plain text): `signup_code`, `reset_code`, `account_exists`, `account_invite`,
`enrollment_approved`, `enrollment_rejected`, `waitlist_promoted`, `enrollment_removed`,
`class_cancelled`.

**Backends**: `smtp` (real), `console` (logs it), `memory` (tests). In development, Mailpit
captures everything at http://localhost:8025 and delivers nothing, so you can test any address
without sending real mail.

Check a live relay with:

```bash
docker compose exec api python -m app.cli send-test-email --to you@example.org
```

## 12. API reference

Base path `/api/v1`. Interactive docs at `/api/docs` (disabled when `ENV=production`).

Every error, without exception:

```json
{"error": {"code": "CLASS_FULL", "message": "This class is full.", "details": null}}
```

Branch on `code`; `message` is already written for people and can be shown as-is.

### Endpoints

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Sign-up | `POST /auth/signup/request-code` · `/verify-code` · `/complete` |
| Session | `POST /auth/login` · `POST /auth/logout` |
| Reset | `POST /auth/password-reset/request-code` · `/verify-code` · `/complete` |
| Me | `GET /auth/me` · `PATCH /auth/me` · `POST /auth/me/password` |
| Public | `GET /classes` · `GET /classes/{id}` |
| My children | `GET/POST /me/students` · `PATCH/DELETE /me/students/{id}` |
| Family | `GET /me/overview` · `POST /enrollments` · `DELETE /enrollments/{id}` · `POST /waitlist` · `PATCH/DELETE /waitlist/{id}` |
| Teacher | `GET /teacher/classes` · `POST/DELETE /teacher/classes/{id}/claim` |
| Admin classes | `GET/POST /admin/classes` · `GET/PATCH/DELETE /admin/classes/{id}` · `POST /admin/classes/{id}/move` · `PUT/DELETE /admin/classes/{id}/teacher` · `POST /admin/classes/{id}/enrollments` · `DELETE /admin/enrollments/{id}` · `DELETE /admin/waitlist/{id}` |
| Admin people | `GET/POST /admin/students` · `PATCH/DELETE /admin/students/{id}` · `GET/POST /admin/users` · `PATCH /admin/users/{id}` · `POST /admin/users/{id}/revoke-sessions` · `GET /admin/audit` |
| Approvals | `GET /admin/enrollments?status=&class_id=&period=` · `POST /admin/enrollments/{id}/approve` · `/reject` · `POST /admin/enrollments/approve-bulk` |

39 paths in total. `GET /me/overview` is the family dashboard in one request: children, their
enrolments with status, and waitlist positions computed with a window function.

### Who may call what

✓ allowed · own = only the caller's own children/classes (other ids return 404) · – denied

| Endpoint group | Anon | Family | Teacher | Mgmt | Principal |
|---|---|---|---|---|---|
| `/health`, `/auth/signup/*`, `/auth/login`, `/auth/password-reset/*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `/auth/logout`, `/auth/me*` | – | ✓ | ✓ | ✓ | ✓ |
| `GET /classes*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `/me/students*`, `/me/overview`, `/enrollments*`, `/waitlist*` | – | own | own | own | own |
| `GET /teacher/classes` | – | – | own | own | own |
| `/teacher/classes/{id}/claim` | – | – | ✓ | – | – |
| `/admin/classes*`, `/admin/students` (read/create/update), `/admin/users` (read) | – | – | – | ✓ | ✓ |
| `GET /admin/enrollments` (queue, read-only) | – | – | – | ✓ | ✓ |
| `/admin/enrollments/*/approve`, `/reject`, `approve-bulk` | – | – | – | – | ✓ |
| `POST/PATCH /admin/users`, `revoke-sessions`, `DELETE /admin/students/{id}`, `GET /admin/audit` | – | – | – | – | ✓ |

### Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `CLASS_FULL` | 409 | No seats left |
| `PERIOD_CONFLICT` | 409 | The child already holds a class in that period |
| `CLASS_NOT_OPEN` | 409 | Unpublished, or has no teacher |
| `HAS_OPEN_SEATS` | 409 | Can't join a waitlist for a class that isn't full |
| `ALREADY_ENROLLED` / `ALREADY_WAITLISTED` | 409 | Duplicate |
| `ALREADY_CLAIMED` | 409 | Another teacher has it |
| `CLAIM_LOCKED` | 403 | Staff assigned this class; the teacher can't drop it |
| `CAPACITY_BELOW_ENROLLED` | 409 | New capacity is below seats held |
| `STUDENT_PERIOD_CONFLICT` / `TEACHER_PERIOD_CONFLICT` | 409 | A period change would double-book; `details` names who |
| `LAST_PRINCIPAL` | 409 | Refusing to remove the last Principal |
| `EMAIL_TAKEN` | 409 | Address already has an account |
| `INVALID_TEACHER` / `INVALID_FAMILY` | 422 | Not a user who can hold that role |
| `INVALID_CODE` / `TOO_MANY_ATTEMPTS` / `INVALID_TOKEN` | 400/429 | Code flow |
| `INVALID_CREDENTIALS` / `ACCOUNT_DISABLED` | 401/403 | Login |
| `ACCOUNT_EXISTS` | 409 | Sign-up completion for an active account |
| `RATE_LIMITED` | 429 | Too many requests |
| `UNAUTHENTICATED` / `FORBIDDEN` / `NOT_FOUND` | 401/403/404 | Access |
| `VALIDATION_ERROR` | 422 | Malformed request; input is never echoed back |
| `BUSY_RETRY` | 503 | Lock or statement timeout — safe to retry |
| `CONFLICT` / `INTERNAL_ERROR` | 409/500 | Unexpected |

## 13. Configuration

All settings come from the environment (`.env` locally). Templates:
[.env.example](.env.example) for development, [.env.production.example](.env.production.example)
for production.

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `development` | `production` refuses a weak `SECRET_KEY` or a non-Secure cookie, and hides `/api/docs` |
| `LOG_LEVEL` | `INFO` | |
| `EXPOSE_DOCS` | unset | Overrides the docs default |
| `DATABASE_URL` | local dev DSN | Compose builds it from the `POSTGRES_*` vars |
| `POSTGRES_DB` / `_USER` / `_PASSWORD` | `alhidaya` / `alhidaya` / — | URL-encode specials in the password |
| `SECRET_KEY` | dev value | HMAC pepper for codes. **32+ random chars in production.** Changing it invalidates pending codes |
| `APP_BASE_URL` | `http://localhost:5173` | Used in email links |
| `ALLOWED_ORIGINS` | localhost trio | Comma-separated. Must match the address bar exactly |
| `COOKIE_SECURE` | `false` | `true` in production; switches the cookie to `__Host-` |
| `SESSION_TTL_DAYS` | `30` | |
| `SESSION_TOUCH_INTERVAL_SECONDS` | `300` | |
| `CODE_TTL_MINUTES` | `15` | |
| `CODE_MAX_ATTEMPTS` | `5` | |
| `CODE_RESEND_COOLDOWN_SECONDS` | `60` | |
| `CODE_MAX_PER_HOUR` | `5` | |
| `COMPLETION_TOKEN_TTL_MINUTES` | `30` | |
| `LOGIN_FAILURES_BEFORE_BACKOFF` | `5` | |
| `LOGIN_BACKOFF_BASE_SECONDS` / `_MAX_SECONDS` | `30` / `900` | |
| `ARGON2_TIME_COST` / `_MEMORY_COST` / `_PARALLELISM` | `3` / `65536` / `4` | Tests lower these for speed |
| `DB_LOCK_TIMEOUT_MS` | `5000` | Exceeded → 503 `BUSY_RETRY` |
| `DB_STATEMENT_TIMEOUT_MS` | `15000` | |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT_MS` | `30000` | |
| `EMAIL_BACKEND` | `console` | `smtp` \| `console` \| `memory` |
| `EMAIL_FROM` | placeholder | With Gmail/Workspace it must be the authenticated address |
| `SMTP_HOST` / `_PORT` / `_USERNAME` / `_PASSWORD` | `localhost:1025` | |
| `SMTP_STARTTLS` / `SMTP_USE_TLS` | `false` / `false` | STARTTLS for 587, TLS for 465 |
| `SMTP_TIMEOUT_SECONDS` | `15` | |
| `OUTBOX_WORKER_ENABLED` | `true` | |
| `OUTBOX_POLL_SECONDS` | `5.0` | |
| `OUTBOX_MAX_ATTEMPTS` | `8` | |
| `PUBLIC_DOMAIN` | unset | TLS overlay: the hostname Caddy gets a certificate for. Empty → plain HTTP on :80 |
| `WEB_PORT` / `API_HOST_PORT` / `DB_HOST_PORT` / `MAILPIT_*_PORT` | `8080` / `8000` / `55432` / `8025`,`1025` | Host ports |

## 14. Running and operating it

### Development

```bash
cp .env.example .env
docker compose up -d --build        # api :8000, postgres :55432, mailpit :8025
docker compose exec api python -m app.cli seed    # demo data, password Password123!
npm install && npm run dev          # frontend :5173, proxies /api to the API
```

Demo accounts after seeding: `principal@example.com`, `manager@example.com`,
`teacher1@example.com`…`teacher3@example.com`, `family1@example.com`…`family3@example.com`, all
with `Password123!`. Codes and notifications land in Mailpit.

The API runs with `--reload` and the source bind-mounted, so Python edits apply immediately.

### Tests

```bash
docker compose exec api pytest                       # 105 tests
RUN_SLOW=1 docker compose exec api pytest -k long    # + 40 long randomized runs
docker compose exec api ruff check . && npm run lint
```

Tests run against a real Postgres — a `<db>_test` database, created and migrated automatically,
truncated before each test. No mocked database: the invariants are enforced by real indexes, and
mocking them away would test nothing.

What the suite covers: the auth flows and their limits; every enrolment and waitlist rule;
promotion cascades and switching; class and teacher edits; approvals; **concurrency** (20 racing
sign-ups, plus a control that must overbook without the lock); **fuzzing** (seeded random
operation sequences with all eight invariants checked after every step); the **RBAC matrix**;
per-audience **privacy**; and migrations (`alembic check` finds no drift, and
upgrade→downgrade→upgrade round-trips).

### Production

Full walkthrough: [DEPLOY.md](DEPLOY.md). In short:

```bash
cp .env.production.example .env    # secrets, PUBLIC_DOMAIN, SMTP
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

`migrate` applies migrations and exits; the API starts only if it succeeded. The API image runs
as a non-root user (uid 10001). Caddy obtains and renews the certificate itself.

### Admin CLI

```bash
docker compose exec api python -m app.cli bootstrap-principal --email … --first-name … --last-name …
docker compose exec api python -m app.cli check-invariants
docker compose exec api python -m app.cli send-test-email --to …
docker compose exec api python -m app.cli seed          # refuses when ENV=production
```

`bootstrap-principal` reserves the first Principal account and refuses if an active one exists.
That person then signs up normally with the same address to set a password, keeping the role.

### Backups

```bash
./scripts/backup-db.sh                  # gzipped pg_dump into backups/, 14-day retention
# 15 3 * * * cd /srv/alhidaya && ./scripts/backup-db.sh >> backups/backup.log 2>&1
```

Copy the dumps off the machine. A backup that only exists on the server it protects is not a
backup. Restore instructions are in the script's header.

### Updating

```bash
git pull && docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

Migrations run before the new API starts; expect a few seconds of downtime.

**New migrations** after changing models:

```bash
docker compose exec api alembic revision --autogenerate -m "what changed"
```

Review the generated file — autogenerate does not reliably produce partial indexes or composite
foreign keys, and several invariants depend on them.

### Troubleshooting

| Symptom | Where to look |
|---|---|
| Site won't load | `docker compose ps` — every service should be `healthy` |
| Certificate never issued | `logs caddy`. DNS must resolve here and port 80 must be open |
| API won't start | `logs api`. Production refuses a weak `SECRET_KEY` or `COOKIE_SECURE=false` |
| "Cross-site request blocked" | `ALLOWED_ORIGINS` doesn't match the URL in the address bar |
| No emails | `logs api`, then `send-test-email`. Failures are kept in `outbox_emails.last_error` |
| 503 `BUSY_RETRY` | Lock or statement timeout. Safe to retry; if constant, look for a long-running transaction |
| Seat counts look wrong | `check-invariants`. If it reports nothing, the counts are right |

## 15. Limits and deferred work

Known and deliberate:

- **No automated frontend tests.** The backend is covered thoroughly; the React layer has lint
  only. Do a manual pass over the four roles before a release.
- **Polling, not push.** Roughly one request per 7 s per open tab. Fine for hundreds of families;
  add ETags or a data-version counter before thousands.
- **One term.** There is no school-year model, so the data is for the current term. Archiving
  means taking a dump and clearing the tables.
- **No CSV export** of the approval queue yet.
- **Fonts load from Google's CDN** (`index.html`). If it's blocked, the site falls back to system
  fonts — it works, it just looks different. Self-hosting is a small job.
- **Single API instance** is assumed. The design allows more (the lock is in Postgres and the
  outbox uses `SKIP LOCKED`), but nothing has been tested horizontally.
- **A few seconds of downtime** on deploy.
- **`SECRET_KEY` rotation** invalidates every pending sign-up code and password reset.

## 16. Glossary

| Term | Meaning |
|---|---|
| **Period** | One of four slots: `1`, `2`, `3`, or `year` ("All Periods"). A child may hold one numbered period each, plus one `year` class |
| **Active enrolment** | Status Pending or Approved — it holds a seat |
| **Locked class** | A class whose teacher was assigned by staff; the teacher cannot drop it |
| **Claim** | A teacher assigning themselves to an unclaimed published class |
| **Promotion** | Moving the top of a waitlist into a seat that opened |
| **Switch** | A promotion where the child already held another class that period; the old enrolment is removed and its seat freed, which can cascade |
| **Pruning** | Removing a promoted child's lower-ranked waitlist entries in that period, so they can't later be pulled out of a better choice |
| **Outbox** | `outbox_emails` — mail queued inside the transaction that caused it, delivered by a background worker |
| **Invariant** | One of eight properties that must always hold; checked after every test and available via `check-invariants` |
| **Engine** | `services/engine/` — the only code allowed to write seats, waitlists, classes or teacher assignments |
