# Dienst Plausibilitätsprüfungsmodul (Service Plausibility Check)

A FastAPI microservice that manages AI-generated plausibility check results from *Modul Plausibilitätsprüfung*.

## Overview

- **Check results:** Receives and persists structured AI output from completed workflow jobs
- **Note management:** Allows reviewers to update the status of individual notes or remove them

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services from the [root README](../../README.md#dependencies) when running locally

### Dependencies

| Service                     | Purpose                                 |
| --------------------------- | --------------------------------------- |
| PostgreSQL                  | Primary data store                      |
| Document Management Service | Fetches AI job result JSON by `file_id` |

### Installation

```bash
uv sync
```

Non-secret configuration lives in `.env.local` (tracked in git). To generate secrets, run once from the repository root:

```bash
scripts/create_secrets.sh
```

This creates the shared root-level `.env` used by the local Docker Compose setup.

### Configuration

| Variable                                      | Description                                     |
| --------------------------------------------- | ----------------------------------------------- |
| `DB_USER` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection                         |
| `DOCUMENT_MANAGEMENT_SERVICE_URL`             | URL to the Document Management Service        |
| `CORS_ORIGINS`                                | Comma-separated list of allowed CORS origins  |
| `SERVICE_NAME`                                | Service identifier, e.g. `plausibility-notes` |

See `.env.local` for non-secret defaults.

### Running the Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

- **API docs:** http://localhost:8000/docs
- **Health:** http://localhost:8000/healthz
- **Metrics:** http://localhost:8000/metrics

## Docker & Docker Compose

```bash
# Start shared services from repo root
docker compose -f ../../docker-compose.yaml up -d

docker compose up --build

# Subsequent runs
docker compose up -d
```

## Database Migrations

```bash
# Apply migrations
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "description"
```

## API Endpoints

All routes are prefixed with `/plausibility-notes`.

| Method   | Path                     | Description                               |
| -------- | ------------------------ | ----------------------------------------- |
| `GET`    | `/{project_id}`          | List all plausibility notes for a project |
| `POST`   | `/{project_id}/job-done` | Receive completed AI job results          |
| `PATCH`  | `/notes/{note_id}`       | Update note status                        |
| `DELETE` | `/notes/{note_id}`       | Delete a note                             |

Full interactive API documentation: http://localhost:8000/docs
