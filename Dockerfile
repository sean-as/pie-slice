# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend (same-origin API at /api) ----
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_URL=/api
RUN npm run build

# ---- Stage 2: backend runtime, serving the built frontend ----
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////data/pieslice.db

WORKDIR /app

# Dependencies first so this layer caches until the lockfile changes.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend /build/dist ./static

RUN useradd --system --uid 1000 --no-create-home app \
    && mkdir /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8000

# Single worker, no --reload: SQLite allows one writer process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
