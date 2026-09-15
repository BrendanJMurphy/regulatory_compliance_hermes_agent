#!/usr/bin/env bash
# One-time local bring-up. Assumes Docker and a filled-in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "copy .env.example to .env and fill it in first"; exit 1; }
chmod 600 .env
docker compose build compliance-mcp
docker compose up -d compliance-mcp
docker compose up -d gateway
echo "gateway up. next: docker compose exec gateway hermes doctor ; ./scripts/setup-cron.sh"
