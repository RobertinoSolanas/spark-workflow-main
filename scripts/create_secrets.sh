#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    echo ".env already exists — delete it first if you want to regenerate secrets."
    exit 1
fi

secret() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '='; }

S3_KEY=$(secret)
S3_SECRET=$(secret)

cat > "$ENV_FILE" <<EOF
S3_ACCESS_KEY_ID=not_ceph
S3_SECRET_ACCESS_KEY=$S3_SECRET
DB_PASSWORD=$(secret)
TEMPORAL_S3_ACCESS_KEY_ID=not_ceph
TEMPORAL_S3_SECRET_ACCESS_KEY=$S3_SECRET


## For LLM usage you have two options, default is LiteLLM via

VLLM_URL=# Your existing endpoint
VLLM_API_KEY=# Your api key
LITELLM_BASE_URL=http://litellm-proxy:4000/v1
LITELLM_MASTER_KEY=$(secret)

# If you already have an external OpenAI-compatible endpoint,
# comment out the litellm-proxy service in docker-compose.services.yaml
# LITELLM_BASE_URL=# Your existing endpoint
# LITELLM_MASTER_KEY=# Your api key
EOF

echo "Created $ENV_FILE"
