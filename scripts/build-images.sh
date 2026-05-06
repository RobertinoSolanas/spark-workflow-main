#!/bin/bash
# Build all container images using Podman
# Images will be saved and imported into MicroK8s

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGES=(
  "spark-infrastructure:latest"
  "spark-backend-pls:latest"
  "spark-backend-dms:latest"
  "spark-backend-dms-upload:latest"
  "spark-backend-agent-orchestrator:latest"
  "spark-backend-fcs:latest"
  "spark-backend-plausibility-notes:latest"
  "spark-backend-temporal-codec:latest"
  "spark-ai-extraction:latest"
  "spark-ai-formale-pruefung:latest"
  "spark-ai-plausibilitaet-pruefung:latest"
  "spark-litellm-proxy:latest"
  "spark-unoserver:latest"
)

echo "=== Building container images with Podman ==="

# Build infrastructure image (for temporal-codec and shared services)
echo "Building infrastructure image..."

# Build each backend service
SERVICES=(
  "agent_orchestration_service"
  "document_management_service"
  "formal_completeness_check"
  "plausibility_notes"
  "project_logic_service"
  "temporal_codec_service"
)

for svc in "${SERVICES[@]}"; do
  echo "Building backend service: $svc"
  podman build \
    -f "02-backend/$svc/Dockerfile" \
    -t "spark-backend-$(echo $svc | tr '_' '-'):latest" \
    --build-arg INCLUDE_DEPENDENCIES=prod \
    .
done

# Build AI module services
AI_SERVICES=(
  "modul-inhaltsextraktion"
  "modul-formale-pruefung"
  "modul-plausibilitaet-pruefung"
)

for svc in "${AI_SERVICES[@]}"; do
  echo "Building AI module: $svc"
  podman build \
    -f "05-modulcluster/$svc/Dockerfile" \
    -t "spark-ai-$(echo $svc | tr '_' '-'):latest" \
    --build-arg INCLUDE_DEPENDENCIES=prod \
    .
done

# Build shared services
echo "Building litellm-proxy..."
podman build -f 04-shared-services/basiskomponenten/litellm-proxy/Dockerfile \
  -t spark-litellm-proxy:latest .

echo "Building unoserver..."
podman build -f 04-shared-services/basiskomponenten/unoserver/Dockerfile \
  -t spark-unoserver:latest .

echo "=== All images built ==="
podman images | grep spark