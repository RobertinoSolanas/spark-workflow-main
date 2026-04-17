# Temporal Codec Service

A small FastAPI server that exposes the Temporal payload codec `/encode` and `/decode` routes, backed by S3-based payload storage.

## Overview

This service enables viewing workflow inputs and results in the Temporal UI when payloads exceed 100 KB. Large payloads are transparently uploaded to S3 and retrieved whenever a workflow or activity boundary is crossed.

## Getting Started

```bash
uv run main.py
```

### Configuration

Non-secret configuration lives in `.env.local` (tracked in git). To generate secrets, run once from the repository root:

```bash
scripts/create_secrets.sh
```

This script creates the shared root-level `.env` file used by the local Docker Compose setup.

| Variable                   | Description                     |
| -------------------------- | ------------------------------- |
| `TEMPORAL_S3_BUCKET_NAME`  | S3 bucket for Temporal payloads |
| `TEMPORAL_S3_ENDPOINT_URL` | S3 endpoint URL                 |
| `TEMPORAL_S3_REGION`       | S3 region                       |