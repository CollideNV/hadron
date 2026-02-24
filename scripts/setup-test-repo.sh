#!/bin/bash
set -euo pipefail

# Creates a local git repo from test-repo/ for testing the pipeline
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_REPO_SRC="$PROJECT_DIR/test-repo"
TEST_REPO_DEST="${1:-/tmp/hadron-test-repo}"

echo "Setting up test repo at $TEST_REPO_DEST..."

rm -rf "$TEST_REPO_DEST"
mkdir -p "$TEST_REPO_DEST"

# Initialize as a bare repo with a working copy
git init "$TEST_REPO_DEST"
cp -r "$TEST_REPO_SRC"/* "$TEST_REPO_DEST/"

cd "$TEST_REPO_DEST"
git add -A
git commit -m "Initial commit: test app with basic endpoints"

echo ""
echo "Test repo ready at: $TEST_REPO_DEST"
echo "Branch: $(git branch --show-current)"
echo ""
echo "To trigger a CR:"
echo "  ./scripts/trigger-cr.sh $TEST_REPO_DEST"
