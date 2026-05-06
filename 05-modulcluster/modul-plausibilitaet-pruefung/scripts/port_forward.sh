#!/bin/bash
# Port-forward script for modul-plausibilitaet-pruefung third-party services
#
# This script port-forwards all Kubernetes services required to run
# the plausibility checking module locally.
#
# Usage: ./port-forward.sh
# Stop: Press Ctrl+C (kills all port-forwards)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting services for modul-plausibilitaet-pruefung...${NC}"
echo ""

# Get module root directory (one level up from scripts/)
MODULE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Array to store background PIDs
PIDS=()

# Cleanup function to kill all port-forwards and stop docker on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping all port-forwards...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo -e "${YELLOW}Stopping Temporal (docker-compose)...${NC}"
    docker compose -f "$MODULE_DIR/docker-compose.yaml" down 2>/dev/null || true
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

# Set trap to cleanup on exit
trap cleanup SIGINT SIGTERM EXIT

# Function to start a port-forward
start_port_forward() {
    local namespace=$1
    local service=$2
    local local_port=$3
    local remote_port=$4
    local description=$5

    echo -e "  ${GREEN}[+]${NC} ${description}"
    echo -e "      ${YELLOW}${service}${NC} → localhost:${local_port}"

    kubectl port-forward -n "$namespace" --address 0.0.0.0 "svc/$service" "${local_port}:${remote_port}" &>/dev/null &
    PIDS+=($!)
    sleep 0.5
}

# Start Temporal via docker-compose
echo -e "${YELLOW}Starting Temporal (docker-compose)...${NC}"
docker compose -f "$MODULE_DIR/docker-compose.yaml" up -d temporal temporal-ui postgresql elasticsearch
echo -e "  ${GREEN}[+]${NC} Temporal (workflow orchestration)"
echo -e "      ${YELLOW}docker-compose${NC} → localhost:7233"
echo -e "  ${GREEN}[+]${NC} Temporal UI (workflow dashboard)"
echo -e "      ${YELLOW}docker-compose${NC} → localhost:8080"
sleep 3

echo ""
echo -e "${YELLOW}Port-forwards:${NC}"
echo ""

# Qdrant - Vector database for fact storage/retrieval
start_port_forward "testing-database" "qdrant" 6333 6333 "Qdrant (vector database)"

# DMS - Document Management Service
start_port_forward "backend-module" "dms-module-test" 8000 80 "DMS (Document Management Service)"

echo ""
echo -e "${GREEN}All services started successfully!${NC}"
echo ""
echo -e "${YELLOW}Local endpoints:${NC}"
echo "  - Temporal:        localhost:7233"
echo "  - Temporal UI:     http://localhost:8080"
echo "  - Qdrant:          http://localhost:6333"
echo "  - DMS:             http://localhost:8000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all background processes
wait
