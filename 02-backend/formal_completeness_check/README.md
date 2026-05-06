# Dienst formale Vollständigkeitsprüfungsmodul (Service Formal Completeness Check)

A FastAPI microservice that manages the formal completeness check results from *Modul Formale Vollständigkeitsprüfung* in addition to checklists, templates, and table‑of‑contents‑level annotations.

## Overview

The *Dienst formale Vollständigkeitsprüfungsmodul* provides:

- **Completeness checks**: Manages AI-generated completeness check results and per‑project status entries
- **Template management**: Provides and manages document checklists and templates based on project type
- **TOC notes**: Manages table-of-contents-level annotations associated with completeness checks

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services as described in the [root README](../../README.md#dependencies) when running locally

### Dependencies

| Service                     | Purpose                                       |
| --------------------------- | --------------------------------------------- |
| PostgreSQL                  | Primary data store                            |
| Document Management Service | Fetches AI job result JSON by `file_id`       |
| Project Logic Service       | Queries project types for template management |

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

| Variable                                      | Description                                          |
| --------------------------------------------- | ---------------------------------------------------- |
| `DB_USER` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection                                |
| `DOCUMENT_MANAGEMENT_SERVICE_URL`             | URL to the Document Management Service               |
| `PROJECT_LOGIC_SERVICE_URL`                   | URL to the Project Logic Service                     |
| `CORS_ORIGINS`                                | Comma-separated list of allowed CORS origins         |
| `SERVICE_NAME`                                | Service identifier, e.g. `formal-completeness-check` |

See `.env.local` for non-secret defaults.

### Running the Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

The application exposes:

- **API documentation**: http://localhost:8000/docs
- **Health endpoint**: http://localhost:8000/healthz
- **Metrics**: http://localhost:8000/metrics

## Architecture

The service exposes FastAPI endpoints and interacts with platform components via HTTP. Data is stored in PostgreSQL, and completeness results are managed by referencing upstream AI tasks from the *Document Management Service*.

### Docker & Docker Compose

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

### Formal Completeness (by project)

| Method   | Path                                         | Description                         |
| -------- | -------------------------------------------- | ----------------------------------- |
| `GET`    | `/{project_id}`                              | Get completeness results            |
| `GET`    | `/{project_id}/required-document-types`      | List required document types        |
| `POST`   | `/{project_id}/required-document-types`      | Add a custom document type          |
| `PATCH`  | `/{project_id}/required-document-types/{id}` | Update a document type              |
| `DELETE` | `/{project_id}/required-document-types/{id}` | Remove a document type              |
| `GET`    | `/{project_id}/document-assignments`         | Get AI/human document assignments   |
| `PATCH`  | `/{project_id}/documents/{file_id}`          | Set human assignment for a document |
| `POST`   | `/{project_id}/results`                      | Receive completed AI job results    |

### TOC Notes (by project)

| Method  | Path                                | Description                       |
| ------- | ----------------------------------- | --------------------------------- |
| `GET`   | `/{project_id}/toc-notes`           | List TOC notes                    |
| `POST`  | `/{project_id}/toc-notes`           | Create TOC notes                  |
| `POST`  | `/{project_id}/toc-notes/results`   | Receive completed TOC job results |
| `PATCH` | `/{project_id}/toc-notes/{note_id}` | Update note status                |

### Template Management (by project type)

| Method   | Path                                     | Description                |
| -------- | ---------------------------------------- | -------------------------- |
| `GET`    | `/{project_type_id}/template-categories` | List template categories   |
| `POST`   | `/{project_type_id}/template-categories` | Create template categories |
| `DELETE` | `/{project_type_id}/template-categories` | Delete template data       |

Full interactive API documentation: http://localhost:8000/docs
