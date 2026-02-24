#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building Hadron Docker images..."

echo "==> Building hadron-controller..."
docker build -t hadron-controller:latest -f "$PROJECT_DIR/Dockerfile.controller" "$PROJECT_DIR"

echo "==> Building hadron-worker..."
docker build -t hadron-worker:latest -f "$PROJECT_DIR/Dockerfile.worker" "$PROJECT_DIR"

echo "Done! Images built:"
docker images | grep hadron
