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

echo "==> Waiting for Dashboard API (controller)..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-controller --timeout=120s

echo "==> Waiting for Orchestrator..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-orchestrator --timeout=120s

echo "==> Waiting for SSE Gateway..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-gateway --timeout=60s

echo "==> Waiting for Frontend (nginx)..."
kubectl -n hadron wait --for=condition=ready pod -l app=hadron-frontend --timeout=60s

echo ""
echo "Hadron deployed! Open the dashboard via:"
echo ""
echo "  kubectl -n hadron port-forward svc/hadron-frontend 8080:8080"
echo "  open http://localhost:8080/"
echo ""
echo "For direct backend access (debugging):"
echo "  kubectl -n hadron port-forward svc/hadron-controller 8000:8000 &"
echo "  kubectl -n hadron port-forward svc/hadron-orchestrator 8002:8002 &"
echo "  kubectl -n hadron port-forward svc/hadron-gateway 8001:8001 &"
echo ""
echo "Health checks:"
echo "  curl http://localhost:8000/healthz   # Dashboard API"
echo "  curl http://localhost:8002/healthz   # Orchestrator"
echo "  curl http://localhost:8001/healthz   # SSE Gateway"
