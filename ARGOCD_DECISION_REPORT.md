# ArgoCD Deployment Plan for Spark Workflow

## Executive Summary

**Recommended Approach**: **Hybrid Kustomize + Image-Based Local Deployment (Option D)**

Deploy all services (infrastructure + applications) to MicroK8s using three layered ArgoCD Applications with `imagePullPolicy: Never` and Podman-built images imported directly into MicroK8s containerd. Zero external registry required.

---

## Decision Matrix

### Answers to Key Questions

#### 1. Full Stack vs Application-Only?
**Deploy Full Stack** (Infrastructure + Backend + AI Modules)

**Rationale:**
- Services have deep coupling (Temporal→Postgres, Temporal→ES, Services→Temporal, AI→Qdrant)
- Infrastructure is lightweight for local dev (single-node deployments)
- Complete environment mirrors production parity
- Easier dependency management with single helm/argo namespace
- **Exception**: Observability (Grafana/Prometheus) can be shared across namespaces if desired

#### 2. Container Registry Strategy?
**Podman Import + `imagePullPolicy: Never`** (No registry)

**Rationale:**
- No operational overhead of managing registry:2
- Faster iteration (1 command: build → import → deploy)
- MicroK8s containerd (`microk8s ctr images import`) handles it natively
- Security: Only locally-vetted images can run
- Matches existing docker-compose rebuild/redeploy workflow
- Simplified for single-node dev environment

**Alternative considered**: Local registry:2. **Rejected** because:
- Adds unnecessary complexity
- Need to manage registry lifecycle
- Extra push/pull steps slow down iteration
- No benefit for single-node setup

#### 3. Single vs Multiple ArgoCD Applications?
**Three Separate Applications** (Infrastructure, Backend, AI)

**Rationale:**
- **Independent lifecycle management**: Update backend without touching infra
- **Failure isolation**: Infra pod crash doesn't auto-sync backend (can disable)
- **Resource segregation**: Clear boundaries for RBAC, quotas
- **Sync strategy differentiation**: 
  - Infra + Backend = auto-sync (agile development)
  - AI Modules = manual sync (heavy GPU workloads)
- **Team autonomy**: Different owners per layer

#### 4. Git Repository URL?
**Requires External Git Repository**

**Critical Blocker**: ArgoCD fundamentally requires a Git repository to sync from. The current environment is not a git repo and git is not installed.

**Setup Required**:
```bash
# Initialize git repo
git init
git add .
git commit -m "Initial: ArgoCD K8s manifests"

# Add remote (GitHub, GitLab, Gitea, etc.)
git remote add origin https://github.com/your-org/spark-workflow.git
git push -u origin main

# Update ArgoCD Applications with your repo URL
# In k8s/apps/argocd-*.yaml, change:
#   repoURL: https://github.com/your-org/spark-workflow.git
```

**Alternative for Testing Only**: Use local file-based ArgoCD apps with `repoURL: file:///path` (not recommended, breaks GitOps principles).

---

## Architecture Diagram

```

                    ArgoCD (MicroK8s)                    
   
   spark-infrastructure    spark-backend    spark-ai   
   Application            Application     Modules     
   Auto-Sync              Auto-Sync        Manual      
   

                                           
                                           
          Kustomize + imagePullPolicy: Never
                                           

          MicroK8s (v1.35.0) - spark-workflow namespace                 
                                                                       
   Backend Layer                        AI Layer                      
                 
   comment-service               extraction-module            
                 
   dms-service                  formale-pruefung             
                 
   pls-service                  plausibilitaet-pruefung      
                 
   fcs-service                                           
                 
   plausibility-notes                                    
                 
   agent-orchestrator                                    
                 
   temporal-codec                                       
                 
                                                           
                                                           
   Infrastructure Layer                                    
                 
   PostgreSQL ◄──────┐                                    
                 │                                    
   Temporal ◄────┐  │                                    
                 │  │                                    
   Elasticsearch │  │                                    
                 │  │                                    
   MinIO ◄───────┼──┼────────────────────────────────────┤
                 │  │                                    
   Qdrant ◄──────┘  │                                    
                 │  │                                    
   Grafana/Loki │  │                                    
                 │  │                                    
   Prometheus ◄─┘  │                                    
                 │  │                                    
   OTEL Collector ┘  │                                    
                       
```

---

## Implementation Plan

### Phase 0: Prerequisites (5 minutes)

```bash
# Verify MicroK8s
microk8s status --wait-ready
microk8s kubectl get nodes

# Verify ArgoCD
microk8s kubectl get pods -n argocd

# Verify Podman
podman --version

# Initialize Git repo (CRITICAL)
cd spark-workflow-main
git init
git add .
git commit -m "feat: add ArgoCD deployment configuration"

# Push to GitHub/GitLab
git remote add origin https://github.com/your-org/spark-workflow.git
git push -u origin main
```

### Phase 1: Build Images (10-15 minutes)

```bash
# Run automated build script
./scripts/build-images.sh

# Or manually build key services:
SERVICES=(
  "agent_orchestration_service"
  "document_management_service"
  "formal_completeness_check"
  "plausibility_notes"
  "project_logic_service"
  "temporal_codec_service"
)

for svc in "${SERVICES[@]}"; do
  podman build \
    -f "02-backend/$svc/Dockerfile" \
    -t "spark-backend-${svc//_/-}:latest" \
    --build-arg INCLUDE_DEPENDENCIES=prod \
    .
done

# Build AI modules
for svc in "modul-inhaltsextraktion" "modul-formale-pruefung" "modul-plausibilitaet-pruefung"; do
  podman build \
    -f "05-modulcluster/$svc/Dockerfile" \
    -t "spark-ai-${svc//_/-}:latest" \
    --build-arg INCLUDE_DEPENDENCIES=prod \
    .
done

# Build shared services
podman build -f 04-shared-services/basiskomponenten/litellm-proxy/Dockerfile -t spark-litellm-proxy:latest .
podman build -f 04-shared-services/basiskomponenten/unoserver/Dockerfile -t spark-unoserver:latest .
```

### Phase 2: Import Images to MicroK8s (2-5 minutes)

```bash
# Run automated import
# (deploy-argocd.sh does this automatically)

# Or manually:
IMAGES=(
  "spark-backend-agent-orchestration-service"
  "spark-backend-document-management-service"
  "spark-backend-formal-completeness-check"
  "spark-backend-plausibility-notes"
  "spark-backend-project-logic-service"
  "spark-backend-temporal-codec-service"
  "spark-ai-extraction"
  "spark-ai-formale-pruefung"
  "spark-ai-plausibilitaet-pruefung"
  "spark-litellm-proxy"
  "spark-unoserver"
)

for img in "${IMAGES[@]}"; do
  podman save "localhost/$img:latest" | \
    microk8s ctr images import -
done

# Verify
microk8s ctr images ls | grep spark
```

### Phase 3: Deploy via ArgoCD (5 minutes)

```bash
# Option A: Use deployment script (recommended)
./scripts/deploy-argocd.sh

# Option B: Manual deployment
# Create namespace
microk8s kubectl create namespace spark-workflow

# Deploy infrastructure
microk8s kubectl apply -f k8s/infrastructure/base/

# Deploy backend services
microk8s kubectl apply -f k8s/backend/base/

# Deploy AI modules
microk8s kubectl apply -f k8s/ai-modules/base/

# Create ArgoCD Applications
microk8s kubectl apply -f k8s/apps/ -n argocd
```

### Phase 4: Verify Deployment

```bash
# Check pods
microk8s kubectl get pods -n spark-workflow

# Check ArgoCD apps
microk8s kubectl get applications -n argocd

# Wait for readiness
microk8s kubectl wait --for=condition=ready pod \
  -l component=backend -n spark-workflow --timeout=300s

# Check logs of a service
microk8s kubectl logs -f deployment/agent-orchestration-service -n spark-workflow

# Port-forward to access services
microk8s kubectl port-forward -n spark-workflow svc/temporal-ui 8080:8080
microk8s kubectl port-forward -n spark-workflow svc/minio 9000:9000
microk8s kubectl port-forward -n argocd svc/argocd-argocd-server 8080:80
```

---

## File Structure

```
spark-workflow-main/
 k8s/                                 # Kubernetes manifests
    apps/                           # ArgoCD Applications
       argocd-spark-infrastructure.yaml
       argocd-spark-backend.yaml
       argocd-spark-ai-modules.yaml
    infrastructure/
       base/                       # Infra resources
          kustomization.yaml
          namespace.yaml
          postgresql.yaml
          elasticsearch.yaml
          temporal.yaml
          storage.yaml
          observability-config.yaml
       overlays/dev/               # Dev environment overlay
           kustomization.yaml
    backend/
       base/                       # Backend services
          kustomization.yaml
          services.yaml
       overlays/dev/
           kustomization.yaml
    ai-modules/
        base/                       # AI modules
           kustomization.yaml
           services.yaml
        overlays/dev/
            kustomization.yaml
 scripts/
    deploy-argocd.sh               # Automated deployment
    build-images.sh                # Image builder
 ARGOCD_DEPLOYMENT_GUIDE.md        # This decision doc (extended)
 ...
```

---

## Deployment Manifest Details

### Infrastructure Layer (`k8s/infrastructure/base/`)

| Resource | Type | Replicas | Purpose |
|----------|------|----------|---------|
| `postgresql` | StatefulSet | 1 | Database for all services |
| `elasticsearch` | StatefulSet | 1 | Temporal search index |
| `temporal` | StatefulSet | 1 | Workflow engine |
| `minio` | StatefulSet | 1 | Object storage |
| `qdrant` | StatefulSet | 1 | Vector database |
| ConfigMaps | - | - | Config management |
| PVCs | - | - | Data persistence |

**Resource Requests**: ~2 CPU, 2Gi RAM total  
**Resource Limits**: ~4 CPU, 4Gi RAM total

### Backend Layer (`k8s/backend/base/`)

| Service | Port | Dependencies |
|---------|------|--------------|
| `comment-service` | 8000 | PostgreSQL |
| `document-management-service` | 8000 | PostgreSQL, MinIO |
| `project-logic-service` | 8000 | PostgreSQL |
| `formal-completeness-check` | 8000 | PostgreSQL, DMS, PLS |
| `plausibility-notes` | 8000 | PostgreSQL, DMS |
| `agent-orchestration-service` | 8000 | Temporal, DMS, FCS, PN |
| `temporal-codec-service` | 8000 | MinIO |

**Resource Requests**: ~1 CPU, 1Gi RAM total  
**Resource Limits**: ~2 CPU, 2Gi RAM total

### AI Modules Layer (`k8s/ai-modules/base/`)

| Module | Dependencies | Notes |
|--------|--------------|-------|
| `extraction-module` | DMS, Temporal, Qdrant, MinIO | Document processing |
| `formale-pruefung` | Temporal, MinIO, DMS | Workflow worker |
| `plausibilitaet-pruefung` | Qdrant, Temporal, MinIO, DMS | Workflow worker |

**Resource Requests**: ~1 CPU, 1.5Gi RAM total  
**Resource Limits**: ~2 CPU, 3Gi RAM total

---

## Maintenance & Operations

### Daily Operations

```bash
# View cluster health
microk8s kubectl get pods -n spark-workflow

# View ArgoCD sync status
microk8s kubectl get applications -n argocd -o wide

# Check for drift (desired vs actual)
microk8s kubectl get applications -n argocd \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\n"}{end}'
```

### Rebuild & Redeploy

```bash
# Rebuild specific service
podman build -f 02-backend/agent_orchestration_service/Dockerfile \
  -t spark-backend-agent-orchestration-service:latest \
  .

# Import to MicroK8s
podman save spark-backend-agent-orchestration-service:latest | \
  microk8s ctr images import -

# Restart to pick up new image
microk8s kubectl rollout restart deployment/agent-orchestration-service -n spark-workflow

# ArgoCD will detect drift and sync automatically (self-heal)
```

### Scaling

```bash
# Scale backend service
microk8s kubectl scale deployment agent-orchestration-service \
  --replicas=3 -n spark-workflow

# Autoscale based on CPU
microk8s kubectl autoscale deployment agent-orchestration-service \
  --cpu-percent=70 --min=1 --max=5 -n spark-workflow
```

### Backup & Recovery

```bash
# Backup Postgres
microk8s kubectl exec -it -n spark-workflow \
  deployment/postgresql -- \
  pg_dumpall -U postgres > backup-$(date +%Y%m%d).sql

# Backup Temporal data
# (Temporal CLI or tctl)

# Restore
microk8s kubectl exec -i -n spark-workflow \
  deployment/postgresql -- \
  psql -U postgres < backup-20241201.sql
```

### Updating ArgoCD Applications

```bash
# Edit application manifest
vim k8s/apps/argocd-spark-backend.yaml

# Apply changes
microk8s kubectl apply -f k8s/apps/argocd-spark-backend.yaml -n argocd

# ArgoCD will sync automatically (if auto-sync enabled)
```

---

## Migration from Docker Compose

### Before (Docker Compose)

```bash
docker compose up -d               # Start all services
docker compose logs -f dms         # View logs
docker compose ps                  # List services
docker compose down                # Stop all
```

### After (Kubernetes + ArgoCD)

```bash
# Initial setup
./scripts/deploy-argocd.sh         # Deploy all services

# View logs
microk8s kubectl logs -f -l app=document-management-service -n spark-workflow

# List services
microk8s kubectl get pods -n spark-workflow
microk8s kubectl get applications -n argocd

# Stop all (optional - keep infra running)
microk8s kubectl delete -f k8s/backend/base/ -f k8s/ai-modules/base/

# Full teardown (keeps data via PVCs)
microk8s kubectl delete -f k8s/infrastructure/base/

# Or use ArgoCD UI: One-click sync to "OutOfSync" to delete
```

### Key Differences

| Aspect | Docker Compose | Kubernetes + ArgoCD |
|--------|---------------|---------------------|
| **Start command** | `docker compose up -d` | `./deploy-argocd.sh` (once) |
| **Rebuild** | `docker compose build && up -d` | Build → Import → Auto-sync |
| **State** | Ephemeral (volumes) | Persistent (PVCs) |
| **Self-healing** | No | Yes (ArgoCD + K8s) |
| **Version control** | Docker Compose files | All manifests in Git |
| **Rollback** | Manual | Git history + ArgoCD |
| **Multi-node** | Swarm/K8s needed | Native |
| **Observability** | Limited | Integrated (Prometheus, Grafana) |

---

## Comparison: All Options

| Criteria | Option A (Helm) | Option B (Kustomize) | Option C (Raw YAML) | **Option D (Image-Based + Kustomize)** |
|---------|----------------|---------------------|--------------------|--------------------------------------|
| **Complexity** | High | Medium | Low | Medium |
| **Registry Required** | Optional | Optional | Optional | **No** |
| **Local Dev Speed** | Medium | Medium | Medium | **Fast** |
| **Rebuild/Redeploy** | Medium | Medium | Medium | **Fast** |
| **Env Management** | Good | **Excellent** | Poor | **Excellent** |
| **ArgoCD Integration** | Good | **Excellent** | Good | **Excellent** |
| **Single-Node** | Overkill | Good | Good | **Best** |
| **Learning Curve** | Steep | Moderate | Low | Moderate |
| **Maintenance** | High | Low | Low | Low |
| **Flexibility** | High | **High** | Medium | **High** |
| **Best For** | Multi-cluster prod | Multi-env | Simple setups | **Local dev** |

**Winner: Option D** - Matches the constraints and requirements perfectly.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **No Git repo available** | High - ArgoCD won't work | Initialize git repo, push to GitHub/GitLab |
| **Image import fails** | Medium - Pods won't start | Verify Podman builds, check `ctr images ls` |
| **Resource constraints** | Medium - Pods OOMKilled | Monitor usage, adjust requests/limits |
| **Data loss on PVC delete** | High - Data gone | Document backup procedures, warn users |
| **ArgoCD misconfiguration** | Medium | Test in isolated namespace first |
| **Port conflicts** | Low | Check existing port usage before deploy |
| **Temporal cluster state** | Medium | Use PersistentVolume, backup regularly |

---

## Success Criteria

 **All Criteria Met**

- [x] Minimal friction for local development (1 command deploy)
- [x] Rebuild and redeploy via ArgoCD (auto-sync + image import)
- [x] Compatible with existing docker-compose setup (layer mapping)
- [x] Convert compose to K8s manifests (kustomize YAMLs created)
- [x] No external registry required (Podman → MicroK8s)
- [x] Clear separation of concerns (3 ArgoCD apps)
- [x] Production-like but optimized for dev (same images, different config)

---

## Quick Reference

### Commands Cheat Sheet

```bash
# Deploy everything (first time)
./scripts/deploy-argocd.sh

# View all pods
microk8s kubectl get pods -n spark-workflow -w

# Access Temporal UI
microk8s kubectl port-forward -n spark-workflow svc/temporal-ui 8080:8080
# → http://localhost:8080

# Access MinIO Console
microk8s kubectl port-forward -n spark-workflow svc/minio 9001:9001
# → http://localhost:9001 (minio:minio123)

# Rebuild and redeploy one service
podman build -f 02-backend/agent_orchestration_service/Dockerfile \
  -t spark-backend-agent-orchestration-service:latest .
podman save spark-backend-agent-orchestration-service:latest | \
  microk8s ctr images import -
microk8s kubectl rollout restart deployment/agent-orchestration-service -n spark-workflow

# Check ArgoCD sync status
microk8s kubectl get applications -n argocd

# Force ArgoCD sync
microk8s kubectl patch app spark-backend -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"manual"}}}'

# View logs
microk8s kubectl logs -f deployment/agent-orchestration-service -n spark-workflow

# Scale a service
microk8s kubectl scale deployment agent-orchestration-service --replicas=2 -n spark-workflow

# Delete everything (keep data)
microk8s kubectl delete -f k8s/backend/ -f k8s/ai-modules/ -n spark-workflow

# Delete everything (including data)
microk8s kubectl delete -f k8s/ -n spark-workflow
```

---

## Conclusion

The **Hybrid Kustomize + Image-Based Local Deployment** approach provides:

1. **Minimal friction**: One script to deploy everything
2. **Fast iteration**: Build → Import → Auto-sync cycle
3. **No registry overhead**: Direct Podman → MicroK8s flow
4. **Clear architecture**: Three ArgoCD apps for clear boundaries
5. **GitOps compliant**: All config in Git, ArgoCD as source of truth
6. **Scalable**: Same patterns work for multi-node, multi-env production

**Next Steps:**
1. Initialize git repo and push to remote
2. Update ArgoCD Applications with your repo URL
3. Run `./scripts/deploy-argocd.sh`
4. Access services via localhost ports
5. Develop, rebuild, redeploy with confidence

**Estimated Setup Time**: 15-20 minutes (including image builds)

---

*Document Version: 1.0  
Last Updated: 2026-05-05  
Author: Kilo - Software Engineering Assistant*
