# SPARK Workflow

Welcome to the repository of SPARK Workflow!

SPARK Workflow is developed as part of the SPARK project at BMDS and is being released as open source in three consecutive releases. This repository contains the first release. For more information, see [roadmap.md](./docs/roadmap.md).

> [!WARNING]
> **Security Notice:** This project provides AI-based modules for document processing and is intended as a reference and integration foundation for use in different environments. It does not include a complete production-ready security configuration.
>
> Configurations, defaults, example values, and supporting scripts contained in this repository may be suitable for development, testing, or integration purposes, but must not be assumed to be secure or appropriate for direct use in production environments without review and adaptation.
>
> Secure configuration, hardening, deployment, access control, secret handling, and operation must be implemented by the respective operator in accordance with the requirements, policies, and risk profile of the target environment.
>
> A dedicated security review is required before use in integration, test, or production environments.

## Getting Started

### Prerequisites

Run `./scripts/create_secrets.sh` to generate a root `.env` file containing shared secrets (for example database credentials, S3 access keys, Temporal codec keys). **This step is required before starting any containers.** The `.env` file is consumed by both `docker-compose.yaml` (infrastructure services) and `docker-compose.services.yaml` (application services).

Make sure that you review the created `.env` file as you need to configure it with an OpenAI compatible API endpoint and key. For local deployment using LiteLLM, set: `VLLM_URL` and `VLLM_API_KEY` as these values work out of the box. Alternatively, you can set `LITELLM_BASE_URL` to any endpoint. More information is provided as comments inside the generated `.env` file.

When running services individually (without Docker Compose), each service loads its own `.env.local` (tracked) and `.env` (gitignored). Create a per-service `.env` with the secrets listed in the service's README.

### Dependencies

It is recommended to run this repository with Docker or any other compatible tool. This setup only requires a few minutes.

```bash
# 1. Generate secrets (required before first start)
./scripts/create_secrets.sh

# 2. Start shared infrastructure (Postgres, Temporal, MinIO, Qdrant, Observability)
docker compose up -d

# 3. Start application services (requires shared infrastructure to run first)
docker compose -f docker-compose.services.yaml up --build
```

### Docker Base Images

By default, Dockerfiles use `python:3.13-slim` from Docker Hub (no login required).
To use Docker Hardened Images instead, pass the base image build arguments:

```bash
docker compose -f docker-compose.services.yaml build \
  --build-arg BASE_IMAGE_DEV=dhi.io/python:3.13.12-debian13-dev \
  --build-arg BASE_IMAGE=dhi.io/python:3.13.12-debian13
```

This requires a prior `docker login dhi.io` with valid credentials.

Alternatively you can infer how each service is connected to each other based on the `docker-compose.yaml` and run them individually. Each service includes its own `README.md` with instructions on how to run it.

### How to Run a Workflow

A workflow involves multiple steps, so a small UI and helper script are provided for development purposes. The utilities are located in `./scripts/quick_start`. This requires `uv` to be installed.

Start the UI with:

```bash
uv run scripts/quick_start/testrun_ui.py
```

Place the documents you want to process inside the `scripts/quick_start/uploads` folder. PDF and DOCX files are supported.

For additional details, refer to `scripts/quick_start/README.md`.

## Troubleshooting

<details>
<summary>PostgreSQL won't start / application services are crashing</summary>

This is most likely because the `.env` file with secrets hasn't been created yet. Create it by running:

```bash
./scripts/create_secrets.sh
```

Then restart all containers. If the `.env` already exists and you want to regenerate it, delete it first and re-run the script. You then need to clear all volumes and then rebuild the entire stack.

</details>

<details>
<summary>Temporal UI: "missing csrf token in request header"</summary>

The Temporal UI sets its CSRF cookie with the `Secure` flag. Some browsers drop `Secure` cookies over plain HTTP, which prevents the CSRF token from being sent with API requests.

To fix this, add `TEMPORAL_CSRF_COOKIE_INSECURE=true` to the `temporal-ui` service in `docker-compose.yaml`:

```yaml
temporal-ui:
  environment:
    - TEMPORAL_ADDRESS=temporal:7233
    - TEMPORAL_CSRF_COOKIE_INSECURE=true
```

Then recreate the container:

```bash
docker compose up -d temporal-ui
```

</details>

## License

This project is licensed under the EUPL-1.2.

It also includes third-party components under other open source licenses.
See [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for details.
# spark-workflow-main
