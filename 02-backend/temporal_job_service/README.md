# Temporal Job Service

A FastAPI microservice for querying and monitoring Temporal workflows, with Prometheus metrics integration.

## Overview

- **Workflow listing**: Retrieves and filters workflows by execution status and project ID
- **Workflow details**: Provides detailed status, results, and nested child workflow information (up to 2 levels deep)
- **Status tracking**: Returns the latest workflow ID for each execution status type

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Shared platform services from the [root README](../../README.md#dependencies) when running locally

When using the repository's Docker setup, the `ProjectId` search attribute is created automatically.

### Dependencies

| Service  | Purpose                  |
| -------- | ------------------------ |
| Temporal | Workflow engine to query |

### Installation

```bash
uv sync
```

Non-secret configuration lives in `.env.local` (tracked in git). No additional secrets are required for this service.

### Configuration

| Variable             | Default                | Description                 |
| -------------------- | ---------------------- | --------------------------- |
| `TEMPORAL_ADDRESS`   | `localhost:7233`       | Temporal server address     |
| `TEMPORAL_NAMESPACE` | `default`              | Temporal namespace to query |
| `SERVICE_NAME`       | `temporal-job-service` | Service identifier          |

See `.env.local` for defaults.

### Running the Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

## Docker & Docker Compose

```bash
# Start shared services from repo root
docker compose -f ../../docker-compose.yaml up -d

docker compose up --build
```

## API Endpoints

| Method | Path                                               | Description                                                        |
| ------ | -------------------------------------------------- | ------------------------------------------------------------------ |
| `GET`  | `/temporal/workflows`                              | List workflows, filterable by `project_id` and `execution_status`  |
| `GET`  | `/temporal/workflows/{workflow_id}`                | Get workflow details including status, result, and child workflows |
| `GET`  | `/temporal/workflows/{workflow_id}/execution-tree` | Get full execution lineage tree                                    |

#### `GET /temporal/workflows` — query parameters

| Parameter          | Required | Description                                                                                                              |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------ |
| `project_id`       | Yes      | Filter workflows by project UUID                                                                                         |
| `execution_status` | No       | One of: `Running`, `Completed`, `Failed`, `Canceled`, `Terminated`, `TimedOut`, `ContinuedAsNew`, `all` (default: `all`) |

#### Response fields

- `latest_running_workflow_id` / `latest_completed_workflow_id` / `latest_failed_workflow_id` — latest workflow ID per status (null if none)
- `retrieved_workflows` — count of returned workflows
- `workflows` — array with `workflow_id`, `project_id`, `workflow_type`, `workflow_start_time`, `workflow_close_time`, `children`

Full interactive API documentation: http://localhost:8000/docs
