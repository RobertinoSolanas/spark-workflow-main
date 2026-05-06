# Temporal Shared Library

A shared Python library providing an abstraction layer over the Temporal SDK for durable, fault-tolerant workflow orchestration. It handles client creation, worker management, payload serialization (including S3 offloading for large payloads), OpenTelemetry instrumentation, and structured logging.

> **Note:** This package is a **client library**, not the Temporal server itself. The Temporal server runs as a Docker container (`temporalio/auto-setup`) and is started via `docker compose up -d` from the repository root.

## Overview

The Temporal shared library provides:

- **Worker management**: `start_temporal_worker()` for starting Temporal workers with sensible defaults
- **Client management**: `create_temporal_client()` / `get_temporal_client()` singleton for connecting to Temporal
- **Pydantic serialization**: Automatic Pydantic model serialization via `PydanticPayloadConverter`
- **Large payload offloading**: Transparent S3 storage for payloads exceeding 100 KB (`LargePayloadCodec`)
- **OpenTelemetry integration**: Tracing via `CustomOtelPlugin` and auto-instrumentation
- **Structured logging**: ECS-compatible logging with a `LoggingInterceptor` for workflow / activity events
- **Workflow definitions**: Shared workflow and type definitions used across modules

## Installation

This is a workspace package. Services in the repository depend on it via `pyproject.toml`:

```toml
[tool.uv.sources]
temporal = { workspace = true }
```

### Dependencies

- `temporalio[opentelemetry]` — Temporal SDK with OTel support
- `event-logging` — Shared ECS-compatible logging library (workspace dependency)
- `aioboto3` — Async S3 client for large payload storage
- `opentelemetry-sdk`, `opentelemetry-api`, `opentelemetry-exporter-otlp-proto-grpc` — Tracing

## Usage

### Starting a Worker

Module services create an `S3PayloadStorage` from their settings and pass it to `start_temporal_worker`. This is how the modules (`05-modulcluster/`) use it:

```python
from temporal.s3_payload_storage import S3PayloadStorage
from temporal.worker import start_temporal_worker

storage = S3PayloadStorage(
    bucket_name=ENV.TEMPORAL.S3_BUCKET_NAME,
    endpoint_url=ENV.TEMPORAL.S3_ENDPOINT_URL,
    access_key=ENV.TEMPORAL.S3_ACCESS_KEY_ID,
    secret_key=ENV.TEMPORAL.S3_SECRET_ACCESS_KEY,
    region=ENV.TEMPORAL.S3_REGION,
)

await start_temporal_worker(
    host=ENV.TEMPORAL.HOST,
    workflows=workflows,
    activities=activities,
    task_queue=ENV.TEMPORAL.TASK_QUEUE,
    storage=storage,
)
```

### Executing a Workflow

Backend services (orchestrator) use `create_temporal_client` and the execution helpers:

```python
from temporal import execute_workflow, start_workflow, create_temporal_client

client = await create_temporal_client(host=settings.temporal.host, storage=storage)

# Execute and wait for result
result = await execute_workflow(client, "my_workflow", input_data, task_queue="my-queue")

# Start without waiting
handle = await start_workflow(client, "my_workflow", input_data, task_queue="my-queue")
```

### S3 Large Payload Storage

Payloads exceeding 100 KB are transparently offloaded to S3 via `LargePayloadCodec`. Pass an `S3PayloadStorage` instance to `start_temporal_worker` and `create_temporal_client` to enable this. The codec service uses the same storage to decode payloads for the Temporal UI.

## Configuration

The S3 payload storage is configured via environment variables. These must be consistent across all services that use Temporal (orchestrator, DMS, codec service, modules):

| Variable                        | Description                          |
| ------------------------------- | ------------------------------------ |
| `TEMPORAL_S3_BUCKET_NAME`       | S3 bucket for payload offloading — must be the same across all services |
| `TEMPORAL_S3_ENDPOINT_URL`      | S3 endpoint URL                      |
| `TEMPORAL_S3_REGION`            | S3 region (optional)                 |

See the codec service and DMS `.env.local` files for non-secret defaults. Secrets (`TEMPORAL_S3_ACCESS_KEY_ID`, `TEMPORAL_S3_SECRET_ACCESS_KEY`) are generated via `scripts/create_secrets.sh`.

## Project Structure

```
src/temporal/
├── __init__.py              # Public API exports
├── worker.py                # Client creation & worker startup
├── utils.py                 # Workflow execution helpers
├── types.py                 # Shared types (Base64Bytes, etc.)
├── payload_codec.py         # Large payload S3 offloading codec
├── s3_payload_storage.py    # S3 storage backend
├── observability.py         # OpenTelemetry setup
├── custom_otel_plugin.py    # Custom OTel Temporal plugin
├── auto_trace.py            # Auto-instrumentation utilities
├── logging_setup.py         # ECS-compatible logging configuration
├── interceptors/            # Temporal interceptors
│   └── logging_interceptor.py
├── activities/              # Shared reusable activities
└── workflows/               # Shared workflow definitions
    ├── bewertung/
    ├── formale_pruefung/
    ├── inhaltsextraktion/
    ├── modul_suche_und_zuordnung/
    ├── plausibilitaet_pruefung/
    └── rechtsmethodik/
```

## Public API

| Export                   | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `start_temporal_worker`  | Start a Temporal worker with workflows / activities |
| `create_temporal_client` | Create a new Temporal client                      |
| `get_temporal_client`    | Get or create the singleton Temporal client       |
| `execute_workflow`       | Execute a workflow and wait for the result        |
| `start_workflow`         | Start a workflow without waiting                  |
| `stop_workflow`          | Cancel a running workflow                         |
| `is_in_workflow`         | Check if current context is inside a workflow     |
| `WorkflowName`           | Enum of registered workflow names                 |
| `Base64Bytes`            | Custom type for base64-encoded byte payloads      |
