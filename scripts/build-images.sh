#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building Hadron Docker images..."

echo "==> Building hadron-controller..."
docker build -t hadron-controller:latest -f "$PROJECT_DIR/Dockerfile.controller" "$PROJECT_DIR"

echo "==> Building hadron-worker..."
docker build -t hadron-worker:latest -f "$PROJECT_DIR/Dockerfile.worker" "$PROJECT_DIR"

echo "==> Building hadron-frontend..."
docker build -t hadron-frontend:latest -f "$PROJECT_DIR/Dockerfile.frontend" "$PROJECT_DIR"

echo "==> Building hadron-e2e-runner..."
docker build -t hadron-e2e-runner:latest -f "$PROJECT_DIR/Dockerfile.e2e-runner" "$PROJECT_DIR"

echo "Done! Images built:"
docker images | grep hadron

# Load images into K8s containerd if running Docker Desktop with containerd
if docker exec desktop-control-plane true 2>/dev/null; then
    echo ""
    echo "==> Loading images into K8s containerd..."
    docker save hadron-controller:latest | docker exec -i desktop-control-plane ctr -n k8s.io images import -
    docker save hadron-worker:latest | docker exec -i desktop-control-plane ctr -n k8s.io images import -
    docker save hadron-frontend:latest | docker exec -i desktop-control-plane ctr -n k8s.io images import -
    docker save hadron-e2e-runner:latest | docker exec -i desktop-control-plane ctr -n k8s.io images import -
    echo "Images loaded into K8s containerd."
fi
