#!/bin/bash
# Spark Workflow - ArgoCD Deployment Setup Script
#
# This script sets up the entire spark-workflow stack on MicroK8s with ArgoCD.
# It handles image building, loading into MicroK8s, and ArgoCD application creation.
#
# Prerequisites:
#   - MicroK8s v1.35.0+ running with ArgoCD add-on enabled
#   - Podman 5.7.0+ installed
#   - Git repository initialized and accessible

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo "Spark Workflow - ArgoCD Deployment Setup"
echo "============================================"
echo ""

# ---- Configuration ----
NAMESPACE="spark-workflow"
GIT_REPO="${GIT_REPO:-https://github.com/your-org/spark-workflow.git}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_IMAGES="${SKIP_IMAGES:-false}"

echo "Configuration:"
echo "  Project Root: $PROJECT_ROOT"
echo "  Namespace: $NAMESPACE"
echo "  Git Repo: $GIT_REPO"
echo "  Skip Build: $SKIP_BUILD"
echo "  Skip Image Import: $SKIP_IMAGES"
echo ""

# ---- Step 1: Verify Prerequisites ----
echo "[Step 1] Verifying prerequisites..."

if ! command -v microk8s &> /dev/null; then
    echo "ERROR: microk8s is not installed or not in PATH"
    exit 1
fi

if ! microk8s status --wait-ready &> /dev/null; then
    echo "ERROR: microk8s is not running"
    exit 1
fi

if ! microk8s kubectl get ns argocd &> /dev/null; then
    echo "ERROR: ArgoCD namespace not found. Enable with: microk8s addons enable argocd"
    exit 1
fi

if ! command -v podman &> /dev/null; then
    echo "ERROR: podman is not installed or not in PATH"
    exit 1
fi

echo "✓ Prerequisites verified"
echo ""

# ---- Step 2: Ensure namespace exists ----
echo "[Step 2] Ensuring namespace '$NAMESPACE' exists..."
microk8s kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | microk8s kubectl apply -f -
echo "✓ Namespace ready"
echo ""

# ---- Step 3: Build container images ----
if [ "$SKIP_BUILD" != "true" ]; then
    echo "[Step 3] Building container images with Podman..."
    echo "  Note: This may take several minutes."
    echo ""
    
    BACKEND_SERVICES=(
        "agent_orchestration_service"
        "document_management_service"
        "formal_completeness_check"
        "plausibility_notes"
        "project_logic_service"
        "temporal_codec_service"
    )
    
    for svc in "${BACKEND_SERVICES[@]}"; do
        echo "  Building: $svc"
        podman build \
            -f "02-backend/$svc/Dockerfile" \
            -t "spark-backend-${svc//_/-}:latest" \
            --build-arg INCLUDE_DEPENDENCIES=prod \
            . 2>&1 | tail -3
    done
    
    AI_SERVICES=(
        "modul-inhaltsextraktion"
        "modul-formale-pruefung"
        "modul-plausibilitaet-pruefung"
    )
    
    for svc in "${AI_SERVICES[@]}"; do
        echo "  Building: $svc"
        podman build \
            -f "05-modulcluster/$svc/Dockerfile" \
            -t "spark-ai-${svc//_/-}:latest" \
            --build-arg INCLUDE_DEPENDENCIES=prod \
            . 2>&1 | tail -3
    done
    
    echo "  Building: litellm-proxy"
    podman build -f 04-shared-services/basiskomponenten/litellm-proxy/Dockerfile \
        -t spark-litellm-proxy:latest . 2>&1 | tail -3
    
    echo "  Building: unoserver"
    podman build -f 04-shared-services/basiskomponenten/unoserver/Dockerfile \
        -t spark-unoserver:latest . 2>&1 | tail -3
    
    echo "✓ All images built"
    echo ""
else
    echo "[Step 3] Skipping image build (SKIP_BUILD=true)"
    echo ""
fi

# ---- Step 4: Import images into MicroK8s ----
if [ "$SKIP_IMAGES" != "true" ]; then
    echo "[Step 4] Importing images into MicroK8s containerd..."
    
    IMAGE_NAMES=(
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
    
    for img in "${IMAGE_NAMES[@]}"; do
        echo "  Importing: $img:latest"
        podman save "localhost/$img:latest" | microk8s ctr images import - 2>&1 | grep -v "ctr: content/io" || true
    done
    
    echo "✓ Images imported into MicroK8s"
    echo ""
    
    # Verify images
    echo "  Verifying imported images..."
    microk8s ctr images ls | grep spark || echo "  WARNING: No spark images found in MicroK8s"
    echo ""
else
    echo "[Step 4] Skipping image import (SKIP_IMAGES=true)"
    echo ""
fi

# ---- Step 5: Deploy infrastructure ----
echo "[Step 5] Deploying infrastructure layer..."
microk8s kubectl kustomize k8s/infrastructure/base | microk8s kubectl apply -f -
echo "✓ Infrastructure applied"
echo ""

# ---- Step 6: Deploy backend services ----
echo "[Step 6] Deploying backend services layer..."
microk8s kubectl kustomize k8s/backend/base | microk8s kubectl apply -f -
echo "✓ Backend services applied"
echo ""

# ---- Step 7: Deploy AI modules ----
echo "[Step 7] Deploying AI modules layer..."
microk8s kubectl kustomize k8s/ai-modules/base | microk8s kubectl apply -f -
echo "✓ AI modules applied"
echo ""

# ---- Step 8: Create ArgoCD Applications ----
echo "[Step 8] Creating ArgoCD Applications..."

# Update Git repo URL in ArgoCD apps
sed -i "s|https://github.com/your-org/spark-workflow.git|$GIT_REPO|" \
    k8s/apps/argocd-spark-infrastructure.yaml \
    k8s/apps/argocd-spark-backend.yaml \
    k8s/apps/argocd-spark-ai-modules.yaml

microk8s kubectl apply -f k8s/apps/ -n argocd
echo "✓ ArgoCD Applications created"
echo ""

# ---- Step 9: Wait for readiness ----
echo "[Step 9] Waiting for pods to be ready..."
echo "  (This may take 2-5 minutes for the first time)"
echo ""

microk8s kubectl wait --for=condition=ready pod \
    -l component=infrastructure \
    -n "$NAMESPACE" \
    --timeout=300s 2>&1 || echo "  Some infra pods may still be starting..."

microk8s kubectl wait --for=condition=ready pod \
    -l component=backend \
    -n "$NAMESPACE" \
    --timeout=300s 2>&1 || echo "  Some backend pods may still be starting..."

microk8s kubectl wait --for=condition=ready pod \
    -l component=ai \
    -n "$NAMESPACE" \
    --timeout=300s 2>&1 || echo "  Some AI pods may still be starting..."

echo ""
echo "============================================"
echo "Deployment Complete!"
echo "============================================"
echo ""
echo "Access URLs:"
echo "  Temporal UI:      http://localhost:8080"
echo "  MinIO Console:    http://localhost:9001"
echo "  Grafana:          http://localhost:3000"
echo "  Prometheus:       http://localhost:9090"
echo ""
echo "Check pod status:"
echo "  microk8s kubectl get pods -n spark-workflow"
echo ""
echo "ArgoCD URLs:"
echo "  Get ArgoCD admin password:"
echo "    microk8s kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
echo "  Port-forward ArgoCD UI:"
echo "    microk8s kubectl port-forward svc/argocd-argocd-server -n argocd 8080:443"
echo ""
echo "View ArgoCD Applications:"
echo "  microk8s kubectl get applications -n argocd"
echo "============================================"
