#!/bin/bash
set -euo pipefail

CONTROLLER_URL="${HADRON_CONTROLLER_URL:-http://localhost:8000}"
REPO_URL="${1:-/tmp/hadron-test-repo}"

echo "Triggering CR against Hadron controller at $CONTROLLER_URL..."
echo "Target repo: $REPO_URL"
echo ""

CR_RESPONSE=$(curl -s -X POST "$CONTROLLER_URL/api/pipeline/trigger" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "title": "Add a GET /health endpoint",
  "description": "Add a GET /health endpoint that returns {\"status\": \"ok\", \"version\": \"0.1.0\"}. The endpoint should be accessible without authentication. Include appropriate tests.",
  "source": "api",
  "repo_url": "$REPO_URL",
  "repo_default_branch": "main",
  "test_command": "pytest tests/ -v",
  "language": "python"
}
EOF
)

echo "Response: $CR_RESPONSE"

CR_ID=$(echo "$CR_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['cr_id'])" 2>/dev/null || echo "")

if [ -n "$CR_ID" ]; then
  echo ""
  echo "CR triggered: $CR_ID"
  echo ""
  echo "Monitor events:"
  echo "  curl -N '$CONTROLLER_URL/api/events/stream?cr_id=$CR_ID'"
  echo ""
  echo "Check status:"
  echo "  curl '$CONTROLLER_URL/api/pipeline/$CR_ID'"
fi
