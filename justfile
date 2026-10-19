set shell := ["bash", "-cu"]
set dotenv-load := false

# List recipes
default:
    @just --list

# Install Python and frontend dependencies, and git hooks
install:
    uv sync
    cd frontend && npm ci
    uv run pre-commit install

# Run the dev stack (API :8000, UI :5173) with hot reload
dev:
    docker compose up --build

# Stop the dev stack
down:
    docker compose down

# Lint backend and frontend
lint:
    uv run ruff format --check .
    uv run ruff check .
    cd frontend && npm run -s lint && npm run -s format:check

# Auto-format backend and frontend
fmt:
    uv run ruff format .
    uv run ruff check --fix .
    cd frontend && npm run -s format

# Type-check backend and frontend
typecheck:
    uv run basedpyright
    cd frontend && npm run -s typecheck

# Run backend and frontend tests
test:
    uv run pytest
    cd frontend && npm run -s test

# Everything CI runs
check: lint typecheck test
    cd frontend && npm run -s build

# Run the four agent gates, printing JSON envelopes (e.g. `just gates --issue 5`)
gates *args:
    rc=0; for g in run_lint run_typecheck run_tests coverage_delta; do uv run python scripts/gates/$g.py {{args}} || rc=$?; done; exit $rc

# Build the runtime image (what Cloud Run runs)
image:
    docker build -t twin-lab:local .

# Run the runtime image locally on :8080
serve: image
    docker run --rm -p 8080:8080 --env-file .env twin-lab:local
