#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Deploying Hadron to local Kubernetes (Docker Desktop)..."

# Apply K8s manifests
echo "==> Applying K8s manifests..."
kubectl apply -k "$PROJECT_DIR/k8s/overlays/local/"

# Wait for pods
echo "==> Waiting for Postgres..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-postgres --timeout=120s

echo "==> Waiting for Redis..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-redis --timeout=60s

# Run migrations
echo "==> Running database migrations..."
kubectl -n hadron exec deploy/hadron-controller -- alembic -c /app/alembic.ini upgrade head 2>/dev/null || \
  echo "  (migrations may need to be run manually if controller isn't ready yet)"

echo "==> Waiting for Controller..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-controller --timeout=120s

echo ""
echo "Hadron deployed! Access the controller:"
echo ""
echo "  kubectl -n hadron port-forward svc/hadron-controller 8000:8000"
echo ""
echo "Then:"
echo "  curl http://localhost:8000/healthz"
echo "  curl http://localhost:8000/docs"
