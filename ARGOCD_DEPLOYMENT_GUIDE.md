# Development Workflow: ArgoCD on MicroK8s

This document describes the recommended approach for deploying the spark-workflow stack on MicroK8s with ArgoCD and Podman.

## Architecture Overview

### Layered Deployment Strategy

The stack is divided into three deployment layers managed by separate ArgoCD Applications:

| Layer | Components | Purpose |
|-------|-----------|---------|
| **Infrastructure** | PostgreSQL, Temporal (+ES), MinIO, Qdrant | Shared foundation services |
| **Backend Services** | 8 FastAPI microservices | Business logic and API layer |
| **AI Modules** | Extraction, Formal Pruefung, Plausibilitaet modules | Temporal workflow workers |

### Why This Approach?

**Chosen Strategy: Hybrid Kustomize + Image-Based Local Deployment (Option D)**

1. **Kustomize for Environment Management**
   - Declarative configuration via Git
   - Environment overlays capability
   - Native integration with ArgoCD
   - No Helm chart templating complexity

2. **Image-Based with `imagePullPolicy: Never`**
   - No container registry required
   - Direct Podman → MicroK8s containerd workflow
   - Fast iteration for local development
   - Matches existing compose-based rebuild/redeploy pattern

3. **Layered ArgoCD Applications**
   - Independent lifecycle management
   - Clear separation of concerns
   - Infrastructure changes don't cascade unexpectedly
   - Faster failure isolation

## Alternatives Considered

| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| **Helm Chart** | Single chart for entire stack | Over-engineering for single-node dev; harder to modify individual services |
| **Kustomize Overlays Only** | No image management | Still needs registry or image loading mechanism |
| **Raw Manifests** | Plain YAML in Git | Lacks environment flexibility; manual updates needed |
| **Registry-Based** | Run local registry:2 | Adds operational overhead; unnecessary for local dev |

## Prerequisites

- **MicroK8s v1.35.0+** running with ArgoCD add-on enabled
- **Podman 5.7.0+** for building container images
- **Git repository** accessible by ArgoCD (for sync)

## Quick Start

### 1. Verify Prerequisites

```bash
# Check MicroK8s status
microk8s status --wait-ready

# Verify ArgoCD is enabled
microk8s kubectl get pods -n argocd

# Check Podman
podman --version
```

### 2. Initialize Git Repository (Required for ArgoCD)

⚠️ **Critical**: ArgoCD requires a Git repository to sync from. If you don't have one:

```bash
cd spark-workflow-main
git init
git add .
git commit -m "Initial: ArgoCD K8s manifests"

# Add remote and push (replace with your actual repo)
git remote add origin https://github.com/your-org/spark-workflow.git
git push -u origin main
```

### 3. Run Deployment Script

```bash
# Full deployment (builds images, deploys to K8s, creates ArgoCD apps)
./scripts/deploy-argocd.sh
```

**Or manual step-by-step:**

```bash
# Set your git repo URL
export GIT_REPO="https://github.com/your-org/spark-workflow.git"

# Build images (first time only)
./scripts/build-images.sh

# Import images into MicroK8s
# (script does this automatically)

# Deploy infrastructure
microk8s kubectl kustomize k8s/infrastructure/base | microk8s kubectl apply -f -

# Deploy backend services
microk8s kubectl kustomize k8s/backend/base | microk8s kubectl apply -f -

# Deploy AI modules
microk8s kubectl kustomize k8s/ai-modules/base | microk8s kubectl apply -f -

# Create ArgoCD Applications
microk8s kubectl apply -f k8s/apps/ -n argocd
```

## Development Workflow

### Making Changes to Services

1. **Modify source code** in the respective service directory
2. **Rebuild the image**:
   ```bash
   podman build -f 02-backend/agent_orchestration_service/Dockerfile \
       -t spark-backend-agent-orchestration-service:latest \
       --build-arg INCLUDE_DEPENDENCIES=prod \
       .
   ```
3. **Import to MicroK8s**:
   ```bash
   podman save spark-backend-agent-orchestration-service:latest | \
       microk8s ctr images import -
   ```
4. **Trigger ArgoCD sync** (automatic with self-heal enabled):
   ```bash
   # Or manually restart the deployment
   microk8s kubectl rollout restart deployment/agent-orchestration-service -n spark-workflow
   ```

### Rebuilding All Images

```bash
# Clean build (removes cache)
podman system prune -a
./scripts/build-images.sh
./scripts/deploy-argocd.sh --skip-build  # Skip rebuild, just deploy
```

### Accessing Services

| Service | Port | URL |
|---------|------|-----|
| Temporal UI | 8080 | http://localhost:8080 |
| MinIO Console | 9001 | http://localhost:9001 |
| Grafana | 3000 | http://localhost:3000 |
| Prometheus | 9090 | http://localhost:9090 |
| ArgoCD UI | 8443 | https://localhost:8443 |

```bash
# Get ArgoCD admin password
microk8s kubectl -n argocd get secret argocd-initial-admin-secret \
    -o jsonpath='{.data.password}' | base64 -d
```

## ArgoCD Applications

### View Application Status

```bash
microk8s kubectl get applications -n argocd

# Sync all applications
microk8s kubectl patch appproject default -n argocd --type merge \
    -p '{"spec":{"sourceRepos":["*"]}}'
```

### Application Details

| Application | Path | Sync Policy | Purpose |
|-------------|------|-------------|---------|
| `spark-infrastructure` | `k8s/infrastructure/base` | Auto-sync, self-heal | DB, Temporal, Storage |
| `spark-backend` | `k8s/backend/base` | Auto-sync, self-heal | FastAPI services |
| `spark-ai-modules` | `k8s/ai-modules/base` | Manual sync | AI/ML workers |

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
microk8s kubectl get pods -n spark-workflow

# View logs
microk8s kubectl logs <pod-name> -n spark-workflow

# Describe pod for events
microk8s kubectl describe pod <pod-name> -n spark-workflow
```

### Image Pull Errors

```bash
# Verify images are in MicroK8s
microk8s ctr images ls | grep spark

# Re-import if needed
podman save spark-backend-agent-orchestration-service:latest | \
    microk8s ctr images import -
```

### ArgoCD Not Syncing

```bash
# Check ArgoCD app status
microk8s kubectl get applications -n argocd

# Check ArgoCD controller logs
microk8s kubectl logs -n argocd \
    deployment/argocd-application-controller

# Manually sync
microk8s kubectl patch application spark-backend -n argocd \
    --type merge -p '{"operation":{"initiatedBy":{"username":"manual"}}}'
```

### Database Connection Issues

```bash
# Check Postgres connectivity
microk8s kubectl exec -it -n spark-workflow \
    deployment/agent-orchestration-service \
    -- psql -h postgresql -U postgres -c "SELECT 1;"
```

## File Structure

```
 spark-workflow-main/
 k8s/
    apps/                          # ArgoCD Application manifests
       argocd-spark-infrastructure.yaml
       argocd-spark-backend.yaml
       argocd-spark-ai-modules.yaml
    infrastructure/
       base/                      # Infra K8s manifests (Postgres, Temporal, etc.)
           kustomization.yaml
           namespace.yaml
           postgresql.yaml
           elasticsearch.yaml
           temporal.yaml
           storage.yaml
    backend/
       base/                      # Backend services K8s manifests
           kustomization.yaml
           services.yaml
    ai-modules/
        base/                      # AI modules K8s manifests
            kustomization.yaml
            services.yaml
 scripts/
    deploy-argocd.sh              # Automated deployment script
    build-images.sh               # Image build script
 ...
```

## Best Practices

1. **Use ArgoCD for GitOps Workflow**: All changes flow through Git → ArgoCD → K8s
2. **Leverage Self-Heal**: ArgoCD automatically corrects drift from desired state
3. **Tag Images Explicitly**: For production, use semantic versioning instead of `latest`
4. **Monitor Resource Usage**: Adjust resource requests/limits based on actual usage
5. **Use Persistent Volumes**: Data persistence across pod restarts (already configured)
6. **Regular Backups**: Export Temporal data and Postgres regularly

## Scaling Considerations

### Horizontal Pod Autoscaler

```bash
# Example: Scale backend services based on CPU
microk8s kubectl autoscale deployment agent-orchestration-service \
    --cpu-percent=70 --min=1 --max=10 -n spark-workflow
```

### Vertical Scaling

Modify resource requests/limits in the respective deployment YAMLs under `k8s/backend/base/services.yaml`.

## Migration from Docker Compose

| Docker Compose | Kubernetes Equivalent |
|----------------|----------------------|
| `docker-compose up` | `microk8s kubectl apply -f k8s/` + ArgoCD sync |
| `docker-compose logs` | `microk8s kubectl logs -f <pod>` |
| `docker-compose ps` | `microk8s kubectl get pods` |
| `docker-compose down` | `microk8s kubectl delete -f k8s/` |
| `depends_on` | Pod affinity / init containers |

## Security Notes

- All services run as non-root (UID 65532)
- Secrets stored in K8s Secrets (not in Git)
- Network policies can be added for pod-to-pod communication restrictions
- Resource limits prevent DoS within the cluster
- `imagePullPolicy: Never` ensures only locally-vetted images run

## Next Steps

- [ ] Configure HTTPS/TLS for Ingress
- [ ] Set up monitoring alerts (Prometheus + Alertmanager)
- [ ] Implement distributed tracing (Jaeger/Tempo)
- [ ] Add network policies for pod isolation
- [ ] Configure backup jobs for Postgres and Temporal data
- [ ] Set up CI/CD pipeline for automated image builds
