# Deploying to production (AWS EC2)

Everything runs in Docker: Postgres, the FastAPI API, the React build behind nginx, and Caddy
for HTTPS. One command brings the whole thing up.

```
internet ──443──> caddy ──> web (nginx) ──> api (FastAPI) ──> db (Postgres)
                   TLS       React build        /api/v1          pgdata volume
                             + /api proxy
```

Only Caddy is exposed. nginx, the API and the database are reachable only on the internal
Docker network.

## 1. The server

A **t3.small** (2 GB RAM) or larger running Ubuntu 24.04. A t3.micro can run the stack but tends
to run out of memory while building the React bundle; if you must use one, add swap first.

- Attach an **Elastic IP** so the address survives a reboot.
- Security group inbound: **22** (your IP only), **80** and **443** (anywhere). Nothing else —
  in particular do not open 5432.

Install Docker:

```bash
sudo apt update && sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
```

## 2. The domain

Point an **A record** at the Elastic IP — for example `signup.your-domain.org`. Caddy needs the
DNS to resolve before it can get a certificate, and Let's Encrypt validates over port 80.

Route 53, Cloudflare or any registrar works. Propagation is usually a minute or two. Check with
`dig +short signup.your-domain.org`.

## 3. Configuration

```bash
git clone <your repo> /srv/alhidaya && cd /srv/alhidaya
cp .env.production.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # -> SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # -> POSTGRES_PASSWORD
nano .env
```

Fill in, at minimum:

| Variable | Value |
|---|---|
| `SECRET_KEY` | the 48-char random string (the API refuses to start in production without one) |
| `POSTGRES_PASSWORD` | the 24-char random string |
| `PUBLIC_DOMAIN` | `signup.your-domain.org` |
| `APP_BASE_URL` | `https://signup.your-domain.org` |
| `ALLOWED_ORIGINS` | `https://signup.your-domain.org` |
| `SMTP_*` | your email relay — see §6 |

`.env` holds every secret for the system. It is gitignored; keep it that way, and keep a copy
somewhere safe (a password manager), because losing `SECRET_KEY` invalidates every pending
sign-up code and every session.

## 4. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.tls.yml ps
```

`migrate` runs the database migrations and exits; the API starts only after it succeeds. Caddy
requests a certificate on first start — watch it happen:

```bash
docker compose -f docker-compose.yml -f docker-compose.tls.yml logs -f caddy
```

Then open `https://signup.your-domain.org`. `http://` redirects to `https://` on its own.

## 5. The first Principal

The database starts empty — no accounts, no demo data.

```bash
docker compose -f docker-compose.yml exec api \
  python -m app.cli bootstrap-principal --email you@school.org --first-name Amina --last-name Rahman
```

That reserves the account. Then go to the site, choose **Create account** with that same email,
enter the code you receive, and set a password. The Principal role sticks. From then on the
Principal creates the other staff accounts in the app.

Never run `python -m app.cli seed` on the production database — it refuses when `ENV=production`,
but it is worth knowing why: it creates demo families with a published password.

## 6. Email

Approvals, rejections, waitlist promotions and every sign-up code go out by email, so the system
is not usable without a working relay.

Use a transactional provider rather than a personal mailbox: a Gmail account is capped near 500
recipients a day and its mail is far more likely to be filed as spam.

- **SendGrid:** `smtp.sendgrid.net:587`, `SMTP_USERNAME=apikey`, `SMTP_PASSWORD=<API key>`,
  `SMTP_STARTTLS=true`.
- **Postmark / SES:** same shape, different host.

Add the provider's **SPF and DKIM** records to your domain's DNS. Without them, approval notices
land in junk folders and families will say they never got them.

Check it before announcing the site:

```bash
docker compose -f docker-compose.yml exec api python -m app.cli send-test-email --to you@school.org
```

## 7. Backups

The whole database lives in the `pgdata` Docker volume. Back it up from day one:

```bash
crontab -e
# 15 3 * * * cd /srv/alhidaya && ./scripts/backup-db.sh >> backups/backup.log 2>&1
```

That writes a nightly gzipped dump to `backups/` and keeps 14 days. Copy them off the machine —
`aws s3 sync backups/ s3://your-bucket/alhidaya/` — because a backup that only exists on the
server it protects is not a backup.

Restoring is in the header of `scripts/backup-db.sh`.

## 8. Updating

```bash
cd /srv/alhidaya && git pull
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

Migrations run automatically before the new API starts. There are a few seconds of downtime while
containers restart.

## 9. If something is wrong

| Symptom | Where to look |
|---|---|
| Site won't load | `docker compose ... ps` — every service should be `healthy` |
| Certificate never issued | `logs caddy`. DNS must resolve to this server and port 80 must be open |
| API won't start | `logs api`. In production it refuses a weak `SECRET_KEY` or `COOKIE_SECURE=false` |
| Login says "Cross-site request blocked" | `ALLOWED_ORIGINS` doesn't match the URL in the address bar |
| No emails arrive | `logs api`, then `send-test-email`. Failed sends retry with backoff and are kept in `outbox_emails` |
| Everything is slow | `docker stats`. 2 GB is the practical floor |

## Running without a domain

If DNS isn't ready, leave `PUBLIC_DOMAIN` empty: Caddy then serves plain HTTP on port 80 and you
can reach the site by IP.

Understand what that costs. Browsers refuse to store `Secure` cookies over `http://`, so with
`COOKIE_SECURE=true` nobody can log in — and `ENV=production` requires `COOKIE_SECURE=true`. To
run over plain HTTP you must set `ENV=development` and `COOKIE_SECURE=false`, which means
passwords and session cookies cross the network in the clear.

That is fine for a smoke test from your own laptop. It is not acceptable for real families
entering real passwords. Get the domain before you hand out the link.
