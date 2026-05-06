# Agent Orchestration Service

A FastAPI microservice that triggers and manages AI-powered document processing workflows via [Temporal](https://temporal.io).

## Overview

- **Workflow triggering**: Starts and cancels AI processing workflows for document analysis
- **Activity routing**: Delegates processing steps to downstream services via Temporal activities

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services from the [root README](../../README.md#dependencies) when running locally

### Dependencies

| Service                           | Purpose                                 |
| --------------------------------- | --------------------------------------- |
| Temporal                          | Durable workflow engine                 |
| S3-compatible object storage      | Temporal large-payload codec storage    |
| Document Management Service       | Document access for workflow activities |
| Dienst formale Vollständigkeitsprüfungsmodul | Job result callback target              |
| Dienst Plausibilitätsprüfungsmodul           | Job result callback target              |

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

| Variable                          | Description                                      |
| --------------------------------- | ------------------------------------------------ |
| `TEMPORAL_HOST`                   | Temporal server address, e.g. `localhost:7233`   |
| `TEMPORAL_TASK_QUEUE`             | Temporal task queue name                         |
| `TEMPORAL_NAMESPACE`              | Temporal namespace (default: `default`)          |
| `API_DMS_BASE_URL`                | URL to the Document Management Service           |
| `API_FVP_BASE_URL`                | URL to the Formal Completeness Check Service     |
| `API_PLAUSIBILITY_NOTES_BASE_URL` | URL to the Plausibility Notes Service            |
| `USE_TRANSFER_ENCODING_CHUNKED`   | Enable chunked uploads for Ceph-backed flows     |
| `CORS_ORIGINS`                    | Comma-separated list of allowed CORS origins     |
| `OTEL_SERVICE_NAME`               | OpenTelemetry service name                       |
| `OTEL_ENDPOINT`                   | OpenTelemetry collector gRPC endpoint (optional) |

See `.env.local` for non-secret defaults.

### Running the Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/healthz
- **Metrics**: http://localhost:8000/metrics

## Docker & Docker Compose

```bash
docker compose up --build
```

## API Endpoints

| Method | Path                              | Description                                |
| ------ | --------------------------------- | ------------------------------------------ |
| `POST` | `/workflows/formale-pruefung`     | Start a formal completeness check workflow |
| `POST` | `/workflows/cancel/{workflow_id}` | Cancel a running workflow                  |

Full interactive API documentation: http://localhost:8000/docs
