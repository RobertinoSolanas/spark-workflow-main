# Project Logic Service

A microservice handling core project-related domains including deadlines, process steps, and project management.

## Overview

- **Projects**: Project CRUD operations
- **Deadlines**: Managing project deadlines
- **Process Steps**: Managing process steps for projects
- **Generic Types**: Project types and project statuses

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

| Variable                                      | Description                                      |
| --------------------------------------------- | ------------------------------------------------ |
| `DB_USER` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection                            |
| `SERVICE_NAME`                                | Service identifier, e.g. `project-logic-service` |
| `PROJECT_LOGIC_SERVICE_CORS_ORIGINS`          | Comma-separated list of allowed CORS origins     |

See `.env.local` for non-secret defaults.

### Running the Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/healthz
- **Metrics**: http://localhost:8000/metrics

### Troubleshooting

- **Port already in use:** Change the port mapping in `docker-compose.yml` or stop the conflicting service

- **Database connection issues:** Verify `DB_*` variables in `.env.local` and `.env`, and confirm PostgreSQL is running

- **Migrations not applied:** Check `docker compose logs app` and verify migration files exist in `src/models/db/migrations/versions/`

## Docker & Docker Compose

```bash
# Start shared services from repo root
docker compose -f ../../docker-compose.yaml up -d

docker compose up --build

# Subsequent runs
docker compose up -d

# View logs
docker compose logs -f app
```

## Database Migrations

```bash
# Apply migrations
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "description"
```

## Architecture

Standard microservice pattern: independent PostgreSQL database, async SQLAlchemy, ECS-compatible structured logging, and Prometheus metrics

### Data Models

- **Project:** Core entity with status and type references. References an optional `Applicant` via a nullable `applicant_id` foreign key

- **Applicant:** Stores applicant contact details (13 fields: name, address, contact info). All fields are nullable, allowing projects to exist without an applicant

- **Deadline / Process Step:** Scoped to a project; process steps are also filtered by project type

## API Endpoints

### Projects

| Method  | Path                            | Description           |
| ------- | ------------------------------- | --------------------- |
| `GET`   | `/projects`                     | List projects         |
| `POST`  | `/projects`                     | Create a project      |
| `GET`   | `/projects/{project_id}`        | Get project details   |
| `PATCH` | `/projects/{project_id}`        | Update a project      |
| `PATCH` | `/projects/{project_id}/status` | Update project status |

### Deadlines

| Method   | Path                       | Description                                 |
| -------- | -------------------------- | ------------------------------------------- |
| `GET`    | `/deadlines`               | List deadlines (filterable by `project_id`) |
| `POST`   | `/deadlines`               | Create a deadline                           |
| `GET`    | `/deadlines/{deadline_id}` | Get a deadline                              |
| `PATCH`  | `/deadlines/{deadline_id}` | Update a deadline                           |
| `DELETE` | `/deadlines/{deadline_id}` | Delete a deadline                           |

### Reference Data

| Method | Path                | Description           |
| ------ | ------------------- | --------------------- |
| `GET`  | `/process-steps`    | List process steps    |
| `GET`  | `/project-types`    | List project types    |
| `GET`  | `/project-statuses` | List project statuses |

Full interactive API documentation: http://localhost:8000/docs
