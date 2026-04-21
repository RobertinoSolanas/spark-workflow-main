# Spark Workflow - Kubernetes & ArgoCD Deployment

This directory contains Kubernetes manifests and ArgoCD configuration for deploying the Spark Workflow application.

## Directory Structure

```
k8s/
├── kustomization.yaml              # Root kustomization (for ArgoCD)
├── argocd-application.yaml         # ArgoCD Application manifest
├── README.md                       # This file
├── patches/                        # Kustomize patches
│   └── image-pull-policy.yaml
└── base/                           # Base manifests
    ├── kustomization.yaml          # Base kustomization
    ├── README.md
    ├── 01-infrastructure/          # Core infrastructure
    │   ├── postgresql-deployment.yaml
    │   ├── elasticsearch-deployment.yaml
    │   ├── minio-deployment.yaml
    │   ├── qdrant-deployment.yaml
    │   └── temporal-deployment.yaml
    ├── 02-applications/            # Backend services
    │   └── backend-deployments.yaml
    ├── 03-modules/                 # Workflow modules
    │   └── modul-deployments.yaml
    ├── 04-shared-services/         # Shared components
    │   └── shared-services-deployments.yaml
    ├── 05-observability/           # Monitoring stack
    │   └── observability-deployments.yaml
    ├── 06-secrets/                 # Secrets
    │   └── secrets.yaml
    └── 07-external-access/         # NodePort services
        └── external-services.yaml
```

## Deployment Options

### Option 1: Direct kubectl Deployment (Quick Testing)

```bash
# Apply all manifests directly
microk8s kubectl apply -k k8s/

# Check status
microk8s kubectl get pods -n spark-workflow
```

### Option 2: ArgoCD Deployment (Recommended for GitOps)

See the [ArgoCD Setup Guide](#argocd-setup-guide) below for detailed instructions.

### Option 3: Automated Local Deployment

```bash
# Run the complete deployment script
./scripts/deploy_local.sh full
```

## ArgoCD Setup Guide

### Prerequisites

1. **MicroK8s installed and running**
   ```bash
   microk8s status
   ```

2. **Required MicroK8s addons enabled**
   ```bash
   microk8s enable registry storage dns
   ```

3. **Docker configured with insecure registry**
   ```bash
   # Add to /etc/docker/daemon.json
   {
     "insecure-registries": ["localhost:32000", "127.0.0.1:32000"]
   }
   sudo systemctl restart docker
   ```

### Step-by-Step Deployment

#### 1. Build and Push Images to Local Registry

```bash
# Build all images and push to localhost:32000
./scripts/build_and_push_local.sh
```

Or build individual services:
```bash
docker build -t localhost:32000/spark-workflow/temporal-codec-service:latest \
    -f 02-backend/temporal_codec_service/Dockerfile .
docker push localhost:32000/spark-workflow/temporal-codec-service:latest
```

#### 2. Install ArgoCD

```bash
# Run the installer script
./scripts/install_argocd.sh
```

Or manually:
```bash
# Create namespace
microk8s kubectl create namespace argocd

# Install ArgoCD
microk8s kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml -n argocd

# Expose via NodePort
microk8s kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "NodePort"}}'

# Get password
microk8s kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.admin}" | base64 -d
```

#### 3. Create ArgoCD Application

```bash
# Apply the Application manifest
# First, update the repoURL in k8s/argocd-application.yaml with your git repo
microk8s kubectl apply -f k8s/argocd-application.yaml
```

Or via ArgoCD UI:
1. Open ArgoCD UI: `https://localhost:<nodeport>`
2. Login (username: `admin`)
3. Click "New Application"
4. Configure:
   - **Application Name**: spark-workflow
   - **Project**: default
   - **Source Repository**: your git repo URL
   - **Source Path**: k8s
   - **Target Revision**: HEAD
   - **Destination**: https://kubernetes.default.svc / spark-workflow
5. Click "Create"
6. Click "Sync"

#### 4. Verify Deployment

```bash
# Check all pods
microk8s kubectl get pods -n spark-workflow

# Check services
microk8s kubectl get services -n spark-workflow

# Check ArgoCD sync status
microk8s kubectl get applications -n argocd
```

## Services Overview

### Internal Services (ClusterIP)

| Service | Port | Description |
|---------|------|-------------|
| postgresql | 5432 | PostgreSQL database |
| elasticsearch | 9200 | Elasticsearch for Temporal |
| minio | 9000 | S3-compatible storage |
| qdrant | 6333 | Vector database |
| temporal | 7233 | Temporal workflow engine |
| temporal-ui | 8080 | Temporal UI |
| document-management-service | 8000 | Document management API |
| agent-orchestration-service | 8000 | Agent orchestration API |
| formal-completeness-check | 8000 | Formal completeness check |
| plausibility-notes | 8000 | Plausibility notes |
| project-logic-service | 8000 | Project logic API |
| litellm-proxy | 4000 | LiteLLM proxy |
| docling-serve | 5001 | Docling document processing |
| tempo | 3200 | Distributed tracing |
| loki | 3100 | Log aggregation |
| otel-collector | 4317/4318 | OpenTelemetry collector |
| prometheus | 9090 | Metrics collection |
| grafana | 3000 | Visualization |

### External Services (NodePort)

| Service | NodePort | URL |
|---------|----------|-----|
| minio | 30900/30901 | http://localhost:30900 / :30901 |
| temporal-ui | 38080 | https://localhost:38080 |
| grafana | 33000 | https://localhost:33000 |
| prometheus | 39090 | https://localhost:39090 |
| litellm-proxy | 34000 | http://localhost:34000 |
| agent-orchestration | 38001 | http://localhost:38001 |
| document-management | 38002 | http://localhost:38002 |

## Resource Requirements

| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| PostgreSQL | 100m-500m | 256Mi-512Mi | 10Gi |
| Elasticsearch | 100m-500m | 512Mi-1Gi | - |
| MinIO | - | - | 20Gi |
| Qdrant | 100m-1000m | 512Mi-2Gi | 10Gi |
| Temporal | 200m-1000m | 512Mi-1Gi | - |
| Backend Services | 50m-500m | 128Mi-512Mi | - |
| Modules | 250m-2000m | 512Mi-4Gi | - |
| Docling | 500m-4000m | 8Gi-48Gi | - |
| Observability | 50m-500m | 128Mi-1Gi | 20Gi |

**Minimum Cluster Resources**: 4 CPU, 16Gi RAM, 60Gi Storage
**Recommended Cluster Resources**: 8 CPU, 32Gi RAM, 100Gi Storage

## Troubleshooting

### Images Not Pulling

```bash
# Check if images are in the local registry
curl http://localhost:32000/v2/_catalog

# Check Docker has the images
docker images | grep spark-workflow

# Manually import to MicroK8s
microk8s ctr images import spark-workflow-service:latest
```

### Pods in Pending State

```bash
# Check persistent volumes
microk8s kubectl get pv,pvc -n spark-workflow

# Check storage class
microk8s kubectl get storageclass
```

### ArgoCD Sync Issues

```bash
# Force sync
microk8s kubectl argocd app sync spark-workflow -n argocd

# View sync details
microk8s kubectl argocd app diff spark-workflow -n argocd

# View ArgoCD logs
microk8s kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server -f
```

### Registry Issues

```bash
# Check registry status
microk8s status | grep registry

# Restart registry
microk8s disable registry
microk8s enable registry
```

## Cleanup

```bash
# Delete all spark-workflow resources
microk8s kubectl delete -k k8s/

# Delete ArgoCD application
microk8s kubectl delete application spark-workflow -n argocd

# Delete ArgoCD entirely
microk8s kubectl delete -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml -n argocd
```
