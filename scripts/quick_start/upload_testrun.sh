#!/usr/bin/env bash
# Upload files from the local uploads/ folder to the target DMS under a fresh project ID.
# Outputs a JSON payload with the project_id, file_ids, and document_types.
#
# Usage:
#   ./upload_testrun.sh [--yes] [--limit N] [output.json]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DMS_URL="${TARGET_DMS_URL:-http://localhost:8002}"
UPLOADS_DIR="${SCRIPT_DIR}/uploads"
DOCUMENT_TYPES_JSON="${SCRIPT_DIR}/document_types.json"
AUTO_CONFIRM=false
LIMIT=""
OUTPUT=""

# --- Arg parsing ---

usage() {
  cat <<EOF
Usage: ./upload_testrun.sh [--yes] [--limit N] [output.json]

Options:
  --yes       Skip confirmation prompt
  --limit N   Only upload the first N files

Environment:
  TARGET_DMS_URL  Target DMS base URL (default: http://localhost:8002)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)       AUTO_CONFIRM=true; shift ;;
    --limit)     LIMIT="${2:?--limit requires a value}"; shift 2 ;;
    --limit=*)   LIMIT="${1#*=}"; shift ;;
    --help|-h)   usage; exit 0 ;;
    --*)         echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    *)           OUTPUT="$1"; shift ;;
  esac
done

[[ -z "${LIMIT}" ]] || [[ "${LIMIT}" =~ ^[0-9]+$ ]] || { echo "--limit must be a positive integer" >&2; exit 1; }
[[ -d "${UPLOADS_DIR}" ]] || { echo "Uploads directory not found: ${UPLOADS_DIR}" >&2; exit 1; }
[[ -f "${DOCUMENT_TYPES_JSON}" ]] || { echo "document_types.json not found" >&2; exit 1; }

# --- Helpers ---

confirm_or_exit() {
  if [[ "${AUTO_CONFIRM}" == true ]]; then
    echo "$1 yes (--yes)"
    return
  fi
  [[ -t 0 ]] || { echo "Confirmation required but stdin is not interactive. Use --yes." >&2; exit 1; }
  read -r -p "$1 [y/N] " reply
  [[ "${reply}" =~ ^[Yy] ]] || { echo "Aborted."; exit 0; }
}

check_health() {
  echo "Checking DMS health..."
  if ! curl -fsS --max-time 5 "${TARGET_DMS_URL}/health" > /dev/null; then
    echo "DMS healthcheck failed at ${TARGET_DMS_URL}/health" >&2
    exit 1
  fi
  echo "DMS is healthy."
}

# --- Discover files ---

LOCAL_FILES=()
while IFS= read -r -d '' f; do
  LOCAL_FILES+=("$f")
done < <(find "${UPLOADS_DIR}" -type f ! -name '.gitkeep' -print0 | sort -z)

TOTAL=${#LOCAL_FILES[@]}
[[ "${TOTAL}" -gt 0 ]] || { echo "No files in uploads directory."; exit 0; }

if [[ -n "${LIMIT}" ]] && [[ "${LIMIT}" -lt "${TOTAL}" ]]; then
  LOCAL_FILES=("${LOCAL_FILES[@]:0:${LIMIT}}")
fi

NEW_PROJECT="$(python3 -c 'import uuid; print(uuid.uuid4())')"

echo "=== Upload Testrun ==="
echo "Project:  ${NEW_PROJECT}"
echo "Target:   ${TARGET_DMS_URL}"
echo "Files:    ${#LOCAL_FILES[@]}/${TOTAL}${LIMIT:+ (limit ${LIMIT})}"
echo ""

for f in "${LOCAL_FILES[@]}"; do
  echo "  ${f#${UPLOADS_DIR}/}"
done
echo ""

confirm_or_exit "Upload ${#LOCAL_FILES[@]} files?"
check_health

# --- Upload ---

FILE_IDS=()

for filepath in "${LOCAL_FILES[@]}"; do
  rel="${filepath#${UPLOADS_DIR}/}"
  payload=$(jq -n --arg fn "$rel" --arg pid "$NEW_PROJECT" \
    '{type: "document", filename: $fn, projectId: $pid}')

  upload_json=$(curl -fsS -X POST "${TARGET_DMS_URL}/v2/files/generate-upload-url" \
    -H "Content-Type: application/json" -d "$payload")
  upload_url=$(echo "$upload_json" | jq -r '.uploadUrl')
  mime=$(echo "$upload_json" | jq -r '.mimeType // "application/pdf"')

  curl -fsS -X PUT -H "Content-Type: ${mime}" --data-binary "@${filepath}" "$upload_url"

  confirm_json=$(curl -fsS -X POST "${TARGET_DMS_URL}/v2/files/confirm-upload" \
    -H "Content-Type: application/json" -d "$payload")
  file_id=$(echo "$confirm_json" | jq -r '.id')

  FILE_IDS+=("$file_id")
  echo "UP: ${rel} -> ${file_id}"
done

# --- Build payload JSON ---

doc_types=$(cat "${DOCUMENT_TYPES_JSON}")
payload_json=$(jq -n \
  --arg pid "$NEW_PROJECT" \
  --argjson fids "$(printf '%s\n' "${FILE_IDS[@]}" | jq -R . | jq -s .)" \
  --argjson dtypes "$doc_types" \
  '{project_id: $pid, file_ids: $fids, document_types: $dtypes}')

if [[ -n "${OUTPUT}" ]]; then
  echo "$payload_json" > "$OUTPUT"
  echo ""
  echo "=== Done ==="
  echo "Payload written to ${OUTPUT}"
else
  echo ""
  echo "=== Done ==="
  echo "$payload_json"
fi
