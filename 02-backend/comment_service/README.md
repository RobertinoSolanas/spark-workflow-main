# Comment Service

A FastAPI microservice for managing comments on projects. Provides CRUD operations backed by PostgreSQL.

## Overview

- **Comment management:** Creating, reading, updating and deleting user comments scoped to a project, with optional filtering by process step and source type

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services from the [root README](../../README.md#dependencies) when running locally

### Dependencies

| Service    | Purpose            |
| ---------- | ------------------ |
| PostgreSQL | Primary data store |

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
| --------------------------------------------- | --------------------------------------------    |
| `DB_USER` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection                        |
| `BACKEND_CORS_ORIGINS`                        | Comma-separated list of allowed CORS origins |
| `SERVICE_NAME`                                | Service identifier, e.g. `comment-service`   |

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

| Method   | Path                                           | Description                                                               |
| -------- | ---------------------------------------------- | ------------------------------------------------------------------------- |
| `GET`    | `/projects/{project_id}/comments`              | List comments for a project (filterable by `process_step`, `source_type`) |
| `POST`   | `/projects/{project_id}/comments`              | Create a comment                                                          |
| `PATCH`  | `/projects/{project_id}/comments/{comment_id}` | Update a comment                                                          |
| `DELETE` | `/projects/{project_id}/comments/{comment_id}` | Delete a comment                                                          |

Full interactive API documentation: http://localhost:8000/docs
