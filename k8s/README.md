# Kubernetes Manifests - Spark Workflow

This directory contains Kubernetes manifests for deploying the Spark Workflow stack on MicroK8s with ArgoCD.

## Directory Structure

```
k8s/
 apps/                                    # ArgoCD Application definitions
    argocd-spark-infrastructure.yaml    # Infrastructure app
    argocd-spark-backend.yaml           # Backend services app
    argocd-spark-ai-modules.yaml        # AI modules app
 infrastructure/
    base/                               # Infrastructure layer (Postgres, Temporal, etc.)
       kustomization.yaml
       namespace.yaml
       postgresql.yaml
       elasticsearch.yaml
       temporal.yaml
       storage.yaml
       observability-config.yaml
    overlays/dev/                       # Dev environment patches
        kustomization.yaml
 backend/
    base/                               # Backend FastAPI services
       kustomization.yaml
       services.yaml
    overlays/dev/
        kustomization.yaml
 ai-modules/
     base/                               # AI/ML workflow modules
        kustomization.yaml
        services.yaml
     overlays/dev/
         kustomization.yaml
```

## Quick Start

### Prerequisites

1. MicroK8s v1.35.0+ running
2. ArgoCD add-on enabled: `microk8s addons enable argocd`
3. Podman 5.7.0+ installed
4. Git repository initialized and accessible

### Deploy Everything

```bash
# From the project root
./scripts/deploy-argocd.sh
```

This script will:
1. Build all container images with Podman
2. Import images into MicroK8s containerd
3. Deploy infrastructure layer
4. Deploy backend services layer
5. Deploy AI modules layer
6. Create ArgoCD Applications for GitOps management

### Manual Deployment

```bash
# 1. Ensure namespace exists
microk8s kubectl create namespace spark-workflow

# 2. Deploy infrastructure
microk8s kubectl kustomize k8s/infrastructure/base | microk8s kubectl apply -f -

# 3. Deploy backend services
microk8s kubectl kustomize k8s/backend/base | microk8s kubectl apply -f -

# 4. Deploy AI modules
microk8s kubectl kustomize k8s/ai-modules/base | microk8s kubectl apply -f -

# 5. Create ArgoCD Applications
microk8s kubectl apply -f k8s/apps/ -n argocd
```

## Architecture

### Layer 1: Infrastructure

Shared foundation services:
- **PostgreSQL** (StatefulSet) - Primary database
- **Temporal** (StatefulSet) - Workflow engine with ES
- **Elasticsearch** (StatefulSet) - Temporal search index
- **MinIO** (StatefulSet) - Object storage for Temporal payloads
- **Qdrant** (StatefulSet) - Vector database
- **Observability** - Grafana, Prometheus, Tempo, Loki, OTEL

### Layer 2: Backend Services

FastAPI microservices:
- `comment-service` - Comment management
- `document-management-service` - Document storage/management
- `project-logic-service` - Project logic
- `formal-completeness-check` - Formal completeness checks
- `plausibility-notes` - Plausibility notes
- `agent-orchestration-service` - AI agent orchestration
- `temporal-codec-service` - Temporal payload codec

### Layer 3: AI Modules

Temporal workflow workers:
- `extraction-module` - Document content extraction
- `formale-pruefung-module` - Formal verification workflows
- `plausibilitaet-pruefung-module` - Plausibility verification workflows

## Service Dependencies

```
PostgreSQL
    ↓
Temporal (+ Elasticsearch)
    ↑
MinIO (Temporal payloads)
    ↑
Qdrant (Vector storage)
    ↑
Backend Services (all depend on PostgreSQL)
    ↓
AI Modules (depend on Backend + Infrastructure)
```

## Configuration

### Image Settings

All services use `imagePullPolicy: Never`, meaning they will only use images
loaded locally into MicroK8s containerd. To update a service:

1. Rebuild with Podman
2. Import into MicroK8s
3. Restart the deployment

```bash
# Example: Update agent-orchestration-service
podman build -f 02-backend/agent_orchestration_service/Dockerfile \
  -t spark-backend-agent-orchestration-service:latest .

podman save spark-backend-agent-orchestration-service:latest | \
  microk8s ctr images import -

microk8s kubectl rollout restart deployment/agent-orchestration-service \
  -n spark-workflow
```

### Environment Variables

Common configuration is stored in ConfigMaps:
- `backend-config` - Shared backend config
- `ai-modules-config` - AI module config
- `postgresql-secrets` - Database and storage credentials

### Secrets

Sensitive data is stored in K8s Secrets (not in Git):

```bash
microk8s kubectl create secret generic postgresql-secrets \
  --from-literal=POSTGRES_PASSWORD=your-password \
  --from-literal=S3_ACCESS_KEY_ID=your-key \
  --from-literal=S3_SECRET_ACCESS_KEY=your-secret \
  -n spark-workflow
```

## Observability

### Access Grafana
```bash
microk8s kubectl port-forward -n spark-workflow svc/grafana 3000:3000
# http://localhost:3000 (admin/admin)
```

### Access Prometheus
```bash
microk8s kubectl port-forward -n spark-workflow svc/prometheus 9090:9090
# http://localhost:9090
```

### Access Temporal UI
```bash
microk8s kubectl port-forward -n spark-workflow svc/temporal-ui 8080:8080
# http://localhost:8080
```

### Access MinIO Console
```bash
microk8s kubectl port-forward -n spark-workflow svc/minio 9001:9001
# http://localhost:9001 (minio:minio123)
```

## ArgoCD Management

### View Application Status

```bash
microk8s kubectl get applications -n argocd
```

### Sync Applications

```bash
# Manual sync
microk8s kubectl patch application spark-backend -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"manual"}}}'
```

### View Application Details

```bash
microk8s kubectl describe application spark-backend -n argocd
```

### Access ArgoCD UI

```bash
# Get admin password
microk8s kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d

# Port-forward
microk8s kubectl port-forward svc/argocd-argocd-server -n argocd 8080:443
# https://localhost:8080
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
microk8s kubectl get pods -n spark-workflow

# View logs
microk8s kubectl logs <pod-name> -n spark-workflow

# Describe for events
microk8s kubectl describe pod <pod-name> -n spark-workflow
```

### Image Not Found

```bash
# Verify images in MicroK8s
microk8s ctr images ls | grep spark

# Re-import
podman save <image-name> | microk8s ctr images import -
```

### Database Connection Issues

```bash
# Test PostgreSQL connectivity
microk8s kubectl exec -it -n spark-workflow \
  deployment/postgresql -- psql -U postgres -c "SELECT 1;"
```

### ArgoCD Not Syncing

```bash
# Check controller logs
microk8s kubectl logs -n argocd \
  deployment/argocd-application-controller
```

## Scaling

### Horizontal Pod Autoscaler

```bash
# Enable autoscaling for a service
microk8s kubectl autoscale deployment agent-orchestration-service \
  --cpu-percent=70 --min=1 --max=5 -n spark-workflow
```

### Manual Scaling

```bash
microk8s kubectl scale deployment agent-orchestration-service \
  --replicas=3 -n spark-workflow
```

## Maintenance

### Backup

```bash
# Backup PostgreSQL
microk8s kubectl exec -it -n spark-workflow \
  deployment/postgresql -- \
  pg_dumpall -U postgres > backup-$(date +%Y%m%d).sql
```

### Update Configuration

```bash
# Edit kustomization or YAML files
vim k8s/backend/base/services.yaml

# Apply changes
microk8s kubectl kustomize k8s/backend/base | microk8s kubectl apply -f -

# ArgoCD will auto-sync (if enabled)
```

### Rollback

```bash
# Rollback deployment
microk8s kubectl rollout undo deployment/agent-orchestration-service \
  -n spark-workflow

# Or use Git to revert changes and let ArgoCD sync
```

## Resource Requirements

### Minimum
- CPU: 2 cores
- RAM: 4 GiB
- Disk: 20 GiB

### Recommended
- CPU: 4 cores
- RAM: 8 GiB
- Disk: 50 GiB

## Cleanup

### Remove All Resources (Keep Data)
```bash
microk8s kubectl delete -f k8s/backend/ -f k8s/ai-modules/ -n spark-workflow
```

### Remove Everything (Including Data)
```bash
microk8s kubectl delete -f k8s/ -n spark-workflow
microk8s kubectl delete namespace spark-workflow
```

## Development vs Production

### Development (Current)
- Single-node deployments
- `imagePullPolicy: Never`
- Local Podman builds
- Auto-sync enabled
- No resource limits

### Production Considerations
- Multi-node cluster
- Container registry (Harbor, ECR, GCR, etc.)
- Image tags with versions
- Resource limits and requests
- Network policies
- RBAC restrictions
- Backup automation
- Monitoring and alerting

## See Also

- [Deployment Guide](../../ARGOCD_DEPLOYMENT_GUIDE.md)
- [Docker Compose Setup](../docker-compose.yaml)
- [Project README](../../README.md)
