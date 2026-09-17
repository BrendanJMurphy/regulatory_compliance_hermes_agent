#!/usr/bin/env bash
# Wipe run state so a scenario run starts clean: drafts, audit log, Hermes sessions and memory.
# Config and skills are untouched. Safe to run repeatedly.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down --remove-orphans >/dev/null 2>&1 || true
rm -rf state/audit state/drafts.sqlite3 state/drafts.sqlite3-wal state/drafts.sqlite3-shm
mkdir -p state/audit
rm -rf hermes/sessions hermes/memories hermes/cron hermes/logs hermes/cache hermes/backups hermes/*.db hermes/skills/autonomous-ai-agents
echo "state reset"
