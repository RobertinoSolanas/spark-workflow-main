# SPARK Workflow — Architecture & Repository Documentation

## Overview

**SPARK Workflow** is an AI-powered document processing system designed to support complex planning and approval procedures in German public administration. It is developed by the [Bundesministerium für Digitales und Staatsmodernisierung](https://www.bmds.bund.de/) (Federal Ministry for Digitalisation and State Modernisation) and released as open source under the [EUPL-1.2](LICENSE) license.

- **Version:** 0.1.0-beta
- **Release Date:** 2026-03-31 (First Release)
- **Status:** Beta
- **Python Requirement:** >=3.13, <3.14
- **Package Manager:** [uv](https://docs.astral.sh/uv/) (workspace-based monorepo)
- **Workflow Engine:** [Temporal](https://temporal.io)
- **License:** [EUPL-1.2](LICENSE)

---

## Repository Structure

```
spark-workflow-main/
├── 02-backend/                    # Supporting backend services
│   ├── agent_orchestration_service/   # Triggers & manages AI workflows via Temporal
│   ├── comment_service/               # (planned, not yet in workspace)
│   ├── document_management_service/   # Document storage & access (DMS)
│   ├── formal_completeness_check/     # REST API for formal completeness results
│   ├── logging/                       # Shared event logging library
│   ├── plausibility_notes/            # REST API for plausibility check notes
│   ├── project_logic_service/         # Project CRUD, deadlines, process steps
│   └── temporal_codec_service/        # S3 payload codec for Temporal UI
│
├── 04-shared-services/          # Shared infrastructure & libraries
│   ├── basiskomponenten/
│   │   ├── litellm-proxy/         # OpenAI-compatible API gateway (routes to vLLM)
│   │   └── unoserver/             # LibreOffice document conversion service
│   ├── prompt-injection/          # Prompt defense/injection detection library
│   └── temporal/                  # Shared Temporal Python SDK abstraction library
│
├── 05-modulcluster/             # AI processing modules (Temporal workers)
│   ├── modul-formale-pruefung/      # Formal completeness check module
│   ├── modul-inhaltsextraktion/     # Content extraction (PDF/DOCX/PPTX → Markdown)
│   └── modul-plausibilitaet-pruefung/ # Plausibility/contradiction detection module
│
├── docker/                      # Docker configuration files
│   ├── observability/             # Grafana, Prometheus, Tempo, Loki, OTel
│   └── temporal/                  # Temporal dynamic config
│
├── docs/                        # Documentation
│   └── roadmap.md                 # 3-phase open-source release roadmap
│
├── scripts/                     # Utility scripts
│   ├── create_secrets.sh          # Generates root .env with shared secrets
│   ├── docker_build_all.sh        # Builds all Docker images
│   ├── pyrefly_all.sh             # Runs pyrefly type checking across workspace
│   └── quick_start/               # Development UI & helper script
│
├── docker-compose.yaml          # Shared infrastructure services
├── docker-compose.services.yaml # Application services
└── pyproject.toml               # Workspace root (uv monorepo config)
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SPARK Workflow                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐                                                    │
│  │   Quick Start UI  │  ← Development interface for testing workflows   │
│  └────────┬─────────┘                                                    │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────────────┐     ┌──────────────────────┐                  │
│  │ Agent Orchestration  │────▶│    Temporal Engine    │                  │
│  │   Service (FASAPI)   │     │  (Workflow Orchest.)  │                  │
│  └──────────────────────┘     └──────────┬───────────┘                  │
│                                          │                               │
│                    ┌─────────────────────┼─────────────────────┐        │
│                    │                     │                     │        │
│                    ▼                     ▼                     ▼        │
│         ┌─────────────────┐   ┌─────────────────┐   ┌────────────────┐ │
│         │ Modul Inhalt    │   │ Modul Formale   │   │ Modul Plaus-   │ │
│         │ extraktion      │   │ Vollständig-    │   │ ibilitäts-     │ │
│         │ (Content        │   │ prüfung         │   │ prüfung        │ │
│         │  Extraction)    │   │ (Formal Check)  │   │ (Plausibility) │ │
│         └────────┬────────┘   └────────┬────────┘   └────────┬───────┘ │
│                  │                     │                      │         │
│                  ▼                     ▼                      ▼         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Document Management Service (DMS)              │  │
│  │              (PostgreSQL + MinIO S3-compatible Storage)           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                  │                                                      │
│  ┌───────────────┴────────────────────────────────────────────────┐    │
│  │                          Shared Services                       │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │    │
│  │  │ LiteLLM      │  │ Qdrant       │  │ Prompt Injection     │  │    │
│  │  │ Proxy (LLM)  │  │ (Vector DB)  │  │ Detection            │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │    │
│  │  ┌──────────────┐  ┌──────────────┐                            │    │
│  │  │ UnoServer    │  │ Temporal     │                            │    │
│  │  │ (DOCX Conv.) │  │ Shared Lib   │                            │    │
│  │  └──────────────┘  └──────────────┘                            │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Observability Stack                         │  │
│  │  Grafana ← Prometheus ← OTel Collector ← Tempo (traces)         │  │
│  │                        ↓                                         │  │
│  │                      Loki (logs)                                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Service Catalog

### 02-Backend Services (Supporting Services)

| Service | Port | Purpose |
|---------|------|---------|
| [`agent_orchestration_service`](02-backend/agent_orchestration_service/) | 8001 | FastAPI service that triggers and manages AI workflows via Temporal. Entry point for workflow execution. |
| [`document_management_service`](02-backend/document_management_service/) | — | Manages document storage, retrieval, and access via signed URLs. Uses PostgreSQL + MinIO S3. |
| [`project_logic_service`](02-backend/project_logic_service/) | 8004 | Project CRUD operations, deadline management, process steps, and generic types. |
| [`formal_completeness_check`](02-backend/formal_completeness_check/) | 8003 | REST API storing and serving formal completeness check results. |
| [`plausibility_notes`](02-backend/plausibility_notes/) | — | REST API for plausibility check notes and results. |
| [`temporal_codec_service`](02-backend/temporal_codec_service/) | 8005 | S3 payload codec service enabling Temporal UI to decode large payloads. |
| [`logging`](02-backend/logging/) | — | Shared event logging library (ECS-compatible structured logging). |

### 04-Shared Services

| Service | Port | Purpose |
|---------|------|---------|
| [`litellm-proxy`](04-shared-services/basiskomponenten/litellm-proxy/) | 4000 | OpenAI-compatible API gateway routing requests to vLLM backend. Provides model aliases for GPT-OSS, Mistral, and BGE-M3 embeddings. |
| [`unoserver`](04-shared-services/basiskomponenten/unoserver/) | — | LibreOffice-based document conversion service (DOCX/PPTX → PDF/Markdown). |
| [`temporal`](04-shared-services/temporal/) | — | Shared Python library providing Temporal SDK abstraction (worker management, Pydantic serialization, S3 payload offloading, OTel instrumentation). |
| [`prompt-injection`](04-shared-services/prompt-injection/) | — | Prompt injection detection and defense library. |

### 05-Modulcluster (AI Processing Modules)

| Module | Purpose | Dependencies |
|--------|---------|--------------|
| [`modul-inhaltsextraktion`](05-modulcluster/modul-inhaltsextraktion/) | Content extraction from PDF/DOCX/PPTX → structured Markdown. Includes AI metadata extraction, image/table analysis via VLM, Qdrant vector indexing, and PageIndex structure extraction. | Docling-serve, UnoServer, LiteLLM, Qdrant, DMS, Temporal |
| [`modul-formale-pruefung`](05-modulcluster/modul-formale-pruefung/) | Formal completeness check. Two-track approach: (1) LLM document matching against required document types, (2) Table of Contents (Inhaltsverzeichnis) detection and matching. | LiteLLM, DMS, Temporal |
| [`modul-plausibilitaet-pruefung`](05-modulcluster/modul-plausibilitaet-pruefung/) | Plausibility/contradiction detection. Three-phase pipeline: claim extraction → semantic candidate retrieval (Qdrant vector search) → multi-stage contradiction detection (risk screening → context verification → clustering). | LiteLLM, Qdrant, DMS, Temporal |

---

## Infrastructure Services (docker-compose.yaml)

| Service | Port(s) | Purpose |
|---------|---------|---------|
| `postgresql` | 5432 | PostgreSQL 16 — Primary database for all services |
| `elasticsearch` | — | Elasticsearch 7.17 — Backend for Temporal search |
| `temporal` | 7233 | Temporal workflow engine 1.29 |
| `temporal-ui` | 8080 | Temporal web UI |
| `minio` | 9000, 9001 | MinIO S3-compatible object storage |
| `qdrant` | 6333, 6334 | Qdrant vector database for semantic search |
| `tempo` | 3200 | Grafana Tempo distributed tracing |
| `loki` | 3100 | Grafana Loki log aggregation |
| `otel-collector` | 4317, 4318 | OpenTelemetry Collector |
| `prometheus` | 9090 | Prometheus metrics |
| `grafana` | 3000 | Grafana dashboards |

---

## Data Flow — Workflow Execution

```
1. User uploads documents via Quick Start UI or DMS API
                │
                ▼
2. Agent Orchestration Service queues workflow in Temporal
                │
                ▼
3. Temporal orchestrates Modul Inhaltsextraktion
   ├── Downloads documents via signed URLs
   ├── Converts PDF/DOCX/PPTX → Markdown (Docling + UnoServer)
   ├── Extracts metadata, summaries, images, tables (LiteLLM/VLM)
   ├── Chunks and indexes into Qdrant
   └── Stores processed documents in DMS
                │
                ▼
4. Temporal orchestrates Modul Formale Prüfung
   ├── LLM Document Matching (classifies docs into categories)
   ├── TOC (Inhaltsverzeichnis) Detection & Parsing
   └── TOC Matching against expected submission structure
                │
                ▼
5. Temporal orchestrates Modul Plausibilitätsprüfung
   ├── Extracts structured claims from document chunks
   ├── Embeds claims in Qdrant for vector search
   ├── Retrieves similar claims across documents
   ├── Screens for contradictions (risk scoring)
   ├── Verifies contradictions with context
   └── Clusters and summarizes findings
                │
                ▼
6. Results stored in DMS → displayed in frontend (future release)
```

---

## Technology Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.13 |
| **Package Manager** | uv (monorepo workspace) |
| **Web Framework** | FastAPI |
| **Workflow Engine** | Temporal 1.29 |
| **Database** | PostgreSQL 16 |
| **Object Storage** | MinIO (S3-compatible) |
| **Vector Database** | Qdrant 1.17 |
| **LLM Gateway** | LiteLLM Proxy |
| **LLM Backend** | vLLM (GPT-OSS 120B, Mistral Small 24B) |
| **Embedding Model** | BAAI/bge-m3 |
| **Document Processing** | Docling, LibreOffice UnoServer |
| **Observability** | OpenTelemetry, Prometheus, Grafana, Tempo, Loki |
| **Container Orchestration** | Docker Compose |
| **Linting/Formatting** | Ruff |
| **Type Checking** | Pyrefly |

---

## Configuration

### Secrets Management

Run from repository root to generate shared secrets:

```bash
./scripts/create_secrets.sh
```

This creates a root `.env` file containing:
- Database credentials (`DB_PASSWORD`)
- S3 access keys (`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`)
- Temporal codec keys
- API keys for LLM services

### Per-Service Configuration

Each service has its own `.env.local` (tracked in git) for non-secret defaults and a `.env` (gitignored) for secrets.

### LLM Configuration

For local deployment, set in `.env`:
```
VLLM_URL=http://vllm:8000
VLLM_API_KEY=your-key
```

Or use any OpenAI-compatible endpoint:
```
LITELLM_BASE_URL=https://your-api-endpoint
```

---

## Quick Start

```bash
# 1. Generate secrets (required before first start)
./scripts/create_secrets.sh

# 2. Start shared infrastructure
docker compose up -d

# 3. Start application services
docker compose -f docker-compose.services.yaml up --build

# 4. Start development UI
uv run scripts/quick_start/testrun_ui.py
```

Place PDF/DOCX files in `scripts/quick_start/uploads/` to process.

---

## Open-Source Roadmap

| Release | Status | Focus |
|---------|--------|-------|
| **First Release** (2026-03-31) | ✅ Released | Content extraction, formal completeness checks, plausibility checks, supporting backend services |
| **Second Release** (planned) | 🔜 Future | Substantive completeness checks, legal review & assessment, drafting of decisions, frontend |
| **Third Release** (planned) | 🔜 Future | Participation of public authorities, roles & rights management, Helm charts, user management, feedback mechanisms |

See [`docs/roadmap.md`](docs/roadmap.md) for details.

---

## Security Notice

> This project provides AI-based modules for document processing and is intended as a reference and integration foundation. It does **not** include a complete production-ready security configuration. Secure configuration, hardening, deployment, access control, secret handling, and operation must be implemented by the respective operator. A dedicated security review is required before use in integration, test, or production environments.

See [`README.md`](README.md) for the full security notice.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines.

See [`MAINTAINERS.md`](MAINTAINERS.md) for project maintainers.

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for community standards.
