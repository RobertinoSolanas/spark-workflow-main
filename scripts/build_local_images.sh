#!/bin/bash
# =============================================================================
# Build and Import All Images to Local MicroK8s Cluster
# =============================================================================
# Usage: ./scripts/build_local_images.sh
# Prerequisites:
#   1. podman installed
#   2. microk8s running
# =============================================================================

set -euo pipefail

# Configuration
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAMESPACE="spark-workflow"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v podman &> /dev/null; then
        log_error "podman is not installed. Install it with: sudo apt install podman"
        exit 1
    fi

    if ! command -v microk8s &> /dev/null; then
        log_error "MicroK8s is not installed."
        exit 1
    fi

    if ! microk8s status | grep -q "microk8s is running"; then
        log_error "MicroK8s is not running. Start it with: microk8s start"
        exit 1
    fi

    log_success "All prerequisites met!"
}

# Build and import a single service
build_and_import() {
    local service_name=$1
    local dockerfile_path=$2
    local context=$3

    local image_tag="${NAMESPACE}/${service_name}:latest"
    local tar_file="/tmp/${service_name}.tar"

    log_info "Building ${YELLOW}${service_name}${NC}..."
    log_info "  Dockerfile: ${dockerfile_path}"
    log_info "  Context: ${context}"
    log_info "  Image: ${image_tag}"

    # Build image
    if ! podman build -t "${image_tag}" -f "${PROJECT_ROOT}/${dockerfile_path}" "${PROJECT_ROOT}/${context}" 2>&1; then
        log_error "Build failed for ${service_name}"
        return 1
    fi

    log_success "Build completed for ${service_name}"

    # Save to tar
    log_info "Saving image to ${tar_file}..."
    if ! podman save "${image_tag}" -o "${tar_file}" 2>&1; then
        log_error "Save failed for ${service_name}"
        return 1
    fi

    # Import to MicroK8s
    log_info "Importing to MicroK8s..."
    if ! sudo microk8s ctr images import "${tar_file}" 2>&1; then
        log_warn "Import may have failed for ${service_name}. Try running: sudo microk8s ctr images import ${tar_file}"
        return 1
    fi

    # Cleanup
    rm -f "${tar_file}"

    log_success "Imported ${service_name} to MicroK8s"
    return 0
}

# Main
main() {
    echo "=============================================="
    echo " Spark Workflow - Local Image Builder"
    echo " Namespace: ${NAMESPACE}"
    echo "=============================================="
    echo ""

    check_prerequisites
    echo ""

    # Define all services to build
    declare -a SERVICES=(
        "temporal-codec-service:02-backend/temporal_codec_service/Dockerfile:."
        "document-management-service:02-backend/document_management_service/Dockerfile:."
        "agent-orchestration-service:02-backend/agent_orchestration_service/Dockerfile:."
        "formal-completeness-check:02-backend/formal_completeness_check/Dockerfile:."
        "plausibility-notes:02-backend/plausibility_notes/Dockerfile:."
        "project-logic-service:02-backend/project_logic_service/Dockerfile:."
        "modul-inhaltsextraktion:05-modulcluster/modul-inhaltsextraktion/Dockerfile:."
        "modul-formale-pruefung:05-modulcluster/modul-formale-pruefung/Dockerfile:."
        "modul-plausibilitaet-pruefung:05-modulcluster/modul-plausibilitaet-pruefung/Dockerfile:."
        "litellm-proxy:04-shared-services/basiskomponenten/litellm-proxy/Dockerfile:04-shared-services/basiskomponenten/litellm-proxy"
        "unoserver:04-shared-services/basiskomponenten/unoserver/Dockerfile:04-shared-services/basiskomponenten/unoserver"
    )

    local failed=()
    local success=()

    for service_def in "${SERVICES[@]}"; do
        IFS=':' read -r name dockerfile context <<< "$service_def"

        if build_and_import "$name" "$dockerfile" "$context"; then
            success+=("$name")
        else
            failed+=("$name")
        fi
        echo ""
    done

    # Summary
    echo "=============================================="
    echo " Build Summary"
    echo "=============================================="
    echo -e "${GREEN}Successful (${#success[@]}):${NC}"
    for img in "${success[@]}"; do
        echo "  ✓ ${NAMESPACE}/${img}:latest"
    done

    if [ ${#failed[@]} -gt 0 ]; then
        echo -e "${RED}Failed (${#failed[@]}):${NC}"
        for img in "${failed[@]}"; do
            echo "  ✗ ${img}"
        done
        echo ""
        log_warn "Manual import required for failed images:"
        for img in "${failed[@]}"; do
            echo "  sudo microk8s ctr images import /tmp/${img}.tar"
        done
    else
        log_success "All images built and imported successfully!"
        echo ""
        log_info "Next steps:"
        echo "  1. Verify images: microk8s ctr images ls | grep spark-workflow"
        echo "  2. Check ArgoCD sync: microk8s kubectl get application spark-workflow -n argocd"
        echo "  3. Check pods: microk8s kubectl get pods -n spark-workflow"
    fi
}

# Run main function
main "$@"
