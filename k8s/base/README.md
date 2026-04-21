# Spark Workflow - Kubernetes Deployment

This directory contains Kubernetes deployment descriptors for the Spark Workflow application.

## Directory Structure

```
k8s/base/
├── 01-infrastructure/          # Core infrastructure services
│   ├── postgresql-deployment.yaml
│   ├── elasticsearch-deployment.yaml
│   ├── minio-deployment.yaml
│   ├── qdrant-deployment.yaml
│   └── temporal-deployment.yaml
├── 02-applications/            # Backend application services
│   └── backend-deployments.yaml
├── 03-modules/                 # Workflow modules
│   └── modul-deployments.yaml
├── 04-shared-services/         # Shared base components
│   └── shared-services-deployments.yaml
├── 05-observability/           # Monitoring & observability
│   └── observability-deployments.yaml
├── 06-secrets/                 # Secrets
│   └── secrets.yaml
├── 07-external-access/         # External access (NodePort)
│   └── external-services.yaml
├── kustomization.yaml          # Kustomize base configuration
└── README.md
```

## Services Overview

### Infrastructure Services

| Service | Port | Description |
|---------|------|-------------|
| postgresql | 5432 | PostgreSQL database |
| elasticsearch | 9200, 9300 | Elasticsearch for Temporal |
| minio | 9000, 9001 | S3-compatible object storage |
| qdrant | 6333, 6334 | Vector database |
| temporal | 7233 | Temporal workflow engine |
| temporal-ui | 8080 | Temporal UI dashboard |

### Application Services

| Service | Port | Description |
|---------|------|-------------|
| temporal-codec-service | 8000 | Temporal payload codec |
| document-management-service | 8000 | Document management API |
| document-management-upload | 8000 | Document upload worker |
| agent-orchestration-service | 8000 | Agent orchestration API |
| formal-completeness-check | 8000 | Formal completeness check API |
| plausibility-notes | 8000 | Plausibility notes API |
| project-logic-service | 8000 | Project logic API |

### Modules

| Service | Port | Description |
|---------|------|-------------|
| modul-inhaltsextraktion | - | Content extraction module |
| modul-formale-pruefung | - | Formal check module |
| modul-plausibilitaet-pruefung | - | Plausibility check module |

### Shared Services

| Service | Port | Description |
|---------|------|-------------|
| litellm-proxy | 4000 | LiteLLM API proxy |
| unoserver | 9000 | Document conversion server |
| docling-serve | 5001 | Docling document processing |

### Observability

| Service | Port | Description |
|---------|------|-------------|
| tempo | 3200 | Distributed tracing |
| loki | 3100 | Log aggregation |
| otel-collector | 4317, 4318 | OpenTelemetry collector |
| prometheus | 9090 | Metrics collection |
| grafana | 3000 | Visualization dashboard |

## External Access (NodePort)

| Service | NodePort | URL |
|---------|----------|-----|
| postgresql | 30432 | `localhost:30432` |
| minio | 30900/30901 | `localhost:30900` / `localhost:30901` |
| temporal-ui | 38080 | `localhost:38080` |
| grafana | 33000 | `localhost:33000` |
| prometheus | 39090 | `localhost:39090` |
| litellm-proxy | 34000 | `localhost:34000` |
| agent-orchestration | 38001 | `localhost:38001` |
| document-management | 38002 | `localhost:38002` |
| formal-completeness-check | 38003 | `localhost:38003` |
| plausibility-notes | 38004 | `localhost:38004` |
| project-logic | 38005 | `localhost:38005` |

## Deployment

### Prerequisites

1. MicroK8s installed and running
2. Required addons enabled:
```bash
microk8s enable storage
microk8s enable helm
```

### Deploy All Services

```bash
# Apply all manifests
microk8s kubectl apply -k k8s/base/

# Or apply individual components
microk8s kubectl apply -k k8s/base/01-infrastructure/
microk8s kubectl apply -k k8s/base/02-applications/
microk8s kubectl apply -k k8s/base/03-modules/
microk8s kubectl apply -k k8s/base/04-shared-services/
microk8s kubectl apply -k k8s/base/05-observability/
microk8s kubectl apply -k k8s/base/07-external-access/
```

### Check Deployment Status

```bash
# Check all pods
microk8s kubectl get pods -n spark-workflow

# Check all services
microk8s kubectl get services -n spark-workflow

# Check persistent volumes
microk8s kubectl get pvc -n spark-workflow
```

### View Logs

```bash
# View logs for a specific pod
microk8s kubectl logs -n spark-workflow <pod-name>

# Follow logs
microk8s kubectl logs -f -n spark-workflow <pod-name>
```

### Delete All Resources

```bash
microk8s kubectl delete -k k8s/base/
```

## Image Building

Build Docker images for each service:

```bash
# Build all images
./scripts/docker_build_all.sh

# Or build individual services
docker build -t spark-workflow/temporal-codec-service:latest -f 02-backend/temporal_codec_service/Dockerfile .
docker build -t spark-workflow/document-management-service:latest -f 02-backend/document_management_service/Dockerfile .
docker build -t spark-workflow/modul-inhaltsextraktion:latest -f 05-modulcluster/modul-inhaltsextraktion/Dockerfile .
```

## Resource Requirements

| Component | CPU Request | Memory Request | CPU Limit | Memory Limit |
|-----------|-------------|----------------|-----------|--------------|
| PostgreSQL | 100m | 256Mi | 500m | 512Mi |
| Elasticsearch | 100m | 512Mi | 500m | 1Gi |
| MinIO | - | - | - | - |
| Qdrant | 100m | 512Mi | 1000m | 2Gi |
| Temporal | 200m | 512Mi | 1000m | 1Gi |
| Backend Services | 50-100m | 128-256Mi | 200-500m | 256-512Mi |
| Modules | 250-500m | 512Mi-1Gi | 1000-2000m | 2-4Gi |
| Docling | 500m | 8Gi | 4000m | 48Gi |
| Observability | 50-100m | 128-256Mi | 200-500m | 256-1Gi |

**Total Minimum Resources**: ~4 CPU, ~16Gi RAM
**Total Recommended Resources**: ~8 CPU, ~32Gi RAM

## Notes

1. All services run in the `spark-workflow` namespace
2. Secrets are managed via `secretGenerator` in kustomization
3. Persistent volumes are used for data durability
4. Health checks (readiness/liveness probes) are configured for all services
5. Docling requires GPU support - add NVIDIA device plugin for GPU workloads
