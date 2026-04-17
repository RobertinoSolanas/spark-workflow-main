#!/usr/bin/env bash
set -euo pipefail

for d in $(uv workspace list --paths); do
  uv run --directory "$d" pyrefly check || true
done | grep 'INFO.*errors'
