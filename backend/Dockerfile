# syntax=docker/dockerfile:1.7

# ---- base: Python + uv, virtualenv outside /app so a dev bind mount doesn't hide it ----
FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# ---- deps: runtime dependencies only (cached until pyproject/uv.lock change) ----
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ---- dev: + test/lint tooling; run with the source bind-mounted and --reload ----
FROM deps AS dev
# The source is bind-mounted in dev: don't let root-owned caches land in the host checkout.
ENV PYTEST_ADDOPTS="-p no:cacheprovider" \
    RUFF_NO_CACHE=true
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- prod: slim runtime, non-root ----
FROM base AS prod
COPY --from=deps /opt/venv /opt/venv
COPY . .
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
