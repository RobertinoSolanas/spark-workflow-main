# Temporal Server Configuration

Dynamic configuration for the local Temporal server. The Temporal server itself runs as a Docker container (`temporalio/auto-setup:1.29.0`) started via `docker compose up -d` from the repository root.

## Files

| File | Purpose |
|------|---------|
| `development-sql.yaml` | Dynamic config overrides mounted into the Temporal server container |

## Configuration

`development-sql.yaml` contains development-only overrides:

| Setting | Value | Description |
|---------|-------|-------------|
| `limit.maxIDLength` | 255 | Maximum workflow/activity ID length |
| `system.forceSearchAttributesCacheRefreshOnRead` | true | Forces cache refresh for search attributes (dev only — do not enable in production) |

## Docker Compose Services

The following Temporal-related services are defined in the root `docker-compose.yaml`:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `temporal` | `temporalio/auto-setup:1.29.0` | `7233` | Temporal server (auto-provisions DB schema) |
| `temporal-ui` | `temporalio/ui:2.44.1` | `8080` | Temporal Web UI for workflow monitoring |
| `temporal-admin-tools` | `temporalio/admin-tools:1.29` | — | CLI tools for cluster management |
| `temporal-init` | `temporalio/admin-tools:1.29` | — | One-shot init job: registers `ProjectId` search attribute, sets 60-day retention |

### Dependencies

- **PostgreSQL** (`postgresql:5432`): Temporal persistence store
- **Elasticsearch** (`elasticsearch:9200`): Temporal visibility store for workflow search

## Accessing the UIs

| UI | URL |
|----|-----|
| Temporal Web UI | http://localhost:8080 |
| Temporal gRPC | `localhost:7233` |
