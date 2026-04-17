# Document Management Service

A FastAPI microservice for storing, retrieving, and managing documents in S3-compatible object storage, with Temporal-based workflow support for file processing and approvals.

## Overview

- **File management**: Upload, download, list, and delete documents via presigned URLs; supports versioning and soft deletion
- **Storage backend**: Uses S3-compatible object storage for document persistence
- **Approval workflows**: Manages document approval states via Temporal
- **ZIP processing**: Accepts ZIP archives and extracts them via a Temporal workflow

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services from the [root README](../../README.md#dependencies) when running locally

### Dependencies

| Service                      | Purpose                               |
| ---------------------------- | ------------------------------------- |
| PostgreSQL                   | File metadata store                   |
| S3-compatible object storage | Document storage backend              |
| Temporal                     | ZIP processing and approval workflows |

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

| Variable                                      | Description                                    |
| --------------------------------------------- | ---------------------------------------------- |
| `SERVICE_NAME`                                | Service identifier                             |
| `DB_USER` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection                          |
| `BUCKET_NAME`                                 | S3 bucket name                                 |
| `DOC_STORE_PATH`                              | Base path prefix inside the bucket             |
| `S3_ENDPOINT_URL`                             | S3 API endpoint                                |
| `S3_EXTERNAL_URL`                             | External URL used for presigned URLs           |
| `S3_REGION`                                   | S3 region (optional)                           |
| `TEMPORAL_HOST`                               | Temporal server address, e.g. `localhost:7233` |
| `TEMPORAL_TASK_QUEUE`                         | Temporal task queue name                       |
| `TEMPORAL_NAMESPACE`                          | Temporal namespace (default: `default`)        |
| `TEMPORAL_ENABLE_APPROVAL`                    | Enable approval workflows (`true` / `false`)   |
| `TEMPORAL_APPROVAL_TIMEOUT_DAYS`              | Approval timeout in days                       |
| `TEMPORAL_S3_BUCKET_NAME`                     | S3 bucket for Temporal payloads                |
| `TEMPORAL_S3_ENDPOINT_URL`                    | S3 endpoint for Temporal payloads              |
| `CHECKPOINT_RETENTION_PERIOD_DAYS`            | Days to retain Temporal checkpoint data        |
| `CORS_ORIGINS`                                | Comma-separated list of allowed CORS origins   |

See `.env.local` for non-secret defaults.

### Running the Service

```bash
# Start shared services from repo root
docker compose -f ../../docker-compose.yaml up -d

# Start the service
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/healthz
- **Metrics**: http://localhost:8000/metrics

## Docker & Docker Compose

```bash
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

## Architecture

### Storage

All documents are stored in S3-compatible object storage via `AsyncS3StorageClient` (backed by `aioboto3`). The client uses two connections — a **private** one (internal endpoint for server-side operations) and a **public** one (`S3_EXTERNAL_URL` for generating presigned upload/download URLs that are reachable by the browser). Objects are stored under `<BUCKET_NAME>/<DOC_STORE_PATH>/`.

### Retention Cleanup

Temporal checkpoint files are automatically cleaned up after `CHECKPOINT_RETENTION_PERIOD_DAYS` days.

### Adding a New File Type

1. Add the value to `FileTypeEnum` in `src/models/db/file_enum.py`
2. Add any required columns to the `File` model and run migrations
3. Add a Pydantic upload schema and include it in the discriminated union
4. Implement a `PathBuilder` subclass and register it in `PathBuilderFactory`
5. Add the new fields to `FileResponse`

## API Endpoints

### Files

| Method   | Path                                        | Description                                    |
| -------- | ------------------------------------------- | ---------------------------------------------- |
| `POST`   | `/v2/files/generate-upload-url`             | Generate a presigned upload URL                |
| `POST`   | `/v2/files/confirm-upload`                  | Confirm upload and persist metadata            |
| `POST`   | `/v2/files/start-file-processing`           | Start Temporal processing for an uploaded ZIP  |
| `GET`    | `/v2/files`                                 | List files (filterable by type, project, name) |
| `GET`    | `/v2/files/{file_id}`                       | Get file metadata                              |
| `GET`    | `/v2/files/{file_id}/versions`              | List versions of a file                        |
| `PATCH`  | `/v2/files/{file_id}`                       | Update file metadata                           |
| `DELETE` | `/v2/files/{file_id}`                       | Soft delete a file                             |
| `GET`    | `/v2/files/{file_id}/generate-download-url` | Generate a presigned download URL              |

### Approvals

| Method | Path                                  | Description                                      |
| ------ | ------------------------------------- | ------------------------------------------------ |
| `GET`  | `/v2/files/{file_id}/approval-status` | Get current approval status                      |
| `POST` | `/v2/files/{file_id}/decision`        | Submit approval decision (`approve` or `reject`) |
| `GET`  | `/v2/files/{file_id}/diff`            | Get file diff from running workflow              |
| `POST` | `/v2/files/{file_id}/diff`            | Set file diff in running workflow                |
| `GET`  | `/v2/files/{file_id}/cancel`          | Cancel a running upload workflow                 |

### ZIP Files

| Method | Path                          | Description           |
| ------ | ----------------------------- | --------------------- |
| `GET`  | `/v2/zip-files`               | List ZIP files        |
| `GET`  | `/v2/zip-files/{zip_file_id}` | Get ZIP file metadata |

Full interactive API documentation: http://localhost:8000/docs
