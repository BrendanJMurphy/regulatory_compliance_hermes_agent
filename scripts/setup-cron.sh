#!/usr/bin/env bash
# Register the two scheduled jobs. Hermes stores jobs in $HERMES_HOME/cron/jobs.json and
# recommends creating them through the CLI rather than editing the file. Run once after
# the gateway is up:  ./scripts/setup-cron.sh  (or inside the container: docker compose exec gateway ...)
set -euo pipefail

HERMES=${HERMES:-hermes}
# `deliver=teams` routes to the conversation in TEAMS_HOME_CHANNEL (set in .env, or via /sethome
# from inside the target channel). Flags below verified against hermes_cli/subcommands/cron.py (0.21.3).
CHANNEL=${COMPLIANCE_TEAMS_CHANNEL:-"teams"}
# The service identity used as `requester` for unattended runs. Must be in the allowlist
# (users.json) and in the compliance-analysts group so it can file drafts.
SERVICE_UPN=${COMPLIANCE_SERVICE_UPN:-"priya.natarajan@example-am.com"}

$HERMES cron create "weekdays at 7am" \
  "Run the regulatory-intake skill for releases published since yesterday. Use requester=${SERVICE_UPN}. File one policy_mapping draft per release and post a summary with draft ids." \
  --deliver "$CHANNEL" --skill regulatory-intake --name regulatory-intake-daily

$HERMES cron create "every monday 8am" \
  "Run the attestation-reminders skill with within_days=14. Use requester=${SERVICE_UPN}. Post the grouped summary." \
  --deliver "$CHANNEL" --skill attestation-reminders --name attestation-reminders-weekly

$HERMES cron list
