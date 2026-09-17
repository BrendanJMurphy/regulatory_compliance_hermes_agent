#!/usr/bin/env bash
# One-time local bring-up. Assumes Docker Desktop and a copied .env.
# Generates the two local secrets if they are still at their placeholder values.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "copy .env.example to .env and fill it in first"; exit 1; }
chmod 600 .env

gen_secret() {  # gen_secret VAR : replace VAR=generate-me with 32 random bytes, hex encoded
  if grep -q "^$1=generate-me" .env; then
    local value; value=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i.bak "s|^$1=generate-me|$1=$value|" .env && rm -f .env.bak
    echo "generated $1"
  fi
}
gen_secret COMPLIANCE_MCP_TOKEN
gen_secret COMPLIANCE_AUDIT_HMAC_KEY

mkdir -p state/audit
docker compose build compliance-mcp
docker compose up -d compliance-mcp
docker compose up -d gateway
echo "gateway up. next: docker compose exec gateway hermes doctor ; ./scripts/setup-cron.sh"
