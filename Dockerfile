# One image for local and Cloud Run (ADR-0011).
#   docker build .              -> runtime image: FastAPI serving the built frontend on $PORT
#   docker build --target dev . -> API with dev deps, used by docker-compose with --reload
#   docker build --target demo . -> the hosted demo: runtime plus demo-data/ (`just demo-image`)

FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS python-base
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM python-base AS dev
RUN uv sync --frozen --no-install-project
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM python-base AS runtime
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY config/ config/
COPY --from=frontend /app/frontend/dist frontend/dist
RUN useradd --create-home app
USER app
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]

# Hosted demo (ADR-0011): demo-data/ (scripts.build_demo_data) becomes DATA_DIR, owned by root so
# the app user cannot write it. Pushed only to a private registry; never in git. No key here:
# Cloud Run injects LLM_API_KEY from Secret Manager.
FROM runtime AS demo
USER root
COPY demo-data/ data/
# A Windows build context arrives world-writable.
RUN chown -R root:root data && chmod -R u=rw,go=r,a+X data
USER app
ENV DEMO_MODE=1

# The default target stays the runtime image, without data (CI builds this).
FROM runtime
