#!/usr/bin/env bash
set -euo pipefail

DOCKERFILES=(
  # 02-backend
  02-backend/agent_orchestration_service/Dockerfile
  02-backend/comment_service/Dockerfile
  02-backend/document_management_service/Dockerfile
  02-backend/formal_completeness_check/Dockerfile
  02-backend/plausibility_notes/Dockerfile
  02-backend/project_logic_service/Dockerfile
  02-backend/temporal_job_service/Dockerfile

  # 05-modulcluster
  05-modulcluster/modul-formale-pruefung/Dockerfile
  05-modulcluster/modul-plausibilitaet-pruefung/Dockerfile
  05-modulcluster/modul-inhaltsextraktion/Dockerfile
)

failed=()

for df in "${DOCKERFILES[@]}"; do
  name=$(echo "$df" | sed 's|/Dockerfile$||; s|/|-|g')
  tag="test-${name}:local"
  echo "=========================================="
  echo "Building: $df"
  echo "Tag:      $tag"
  echo "=========================================="
  if docker buildx build \
    -t "$tag" \
    -f "$df" \
    .; then
    echo "OK: $df"
  else
    echo "FAILED: $df"
    failed+=("$df")
  fi
  echo ""
done

echo "=========================================="
if [ ${#failed[@]} -eq 0 ]; then
  echo "All ${#DOCKERFILES[@]} builds succeeded."
else
  echo "${#failed[@]} of ${#DOCKERFILES[@]} builds FAILED:"
  for f in "${failed[@]}"; do
    echo "  - $f"
  done
  exit 1
fi
