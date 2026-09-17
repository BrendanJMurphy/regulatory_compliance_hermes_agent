#!/usr/bin/env bash
# Regenerate mcp/requirements.txt with pinned versions and hashes from pyproject.toml.
# Run after changing dependencies; commit the result. The Dockerfile installs from it.
set -euo pipefail
cd "$(dirname "$0")/../mcp"
uv pip compile pyproject.toml --generate-hashes --python-version 3.12 -o requirements.txt
echo "wrote mcp/requirements.txt"
