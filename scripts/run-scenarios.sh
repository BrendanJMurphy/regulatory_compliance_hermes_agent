#!/usr/bin/env bash
# One full loop of the agent against the fixture data, captured to runs/<timestamp>/.
# Needs only COMPLIANCE_MODEL_API_KEY in .env. No Teams. Each run is independent:
#   ./scripts/reset-state.sh && ./scripts/run-scenarios.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "no .env"; exit 1; }
grep -q "paste-your-key" .env && { echo "put your real key in .env first"; exit 1; }

RUN=runs/$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$RUN"
ANALYST=priya.natarajan@example-am.com
APPROVER=dana.whitfield@example-am.com
FRONT=tom.reyes@example-am.com

docker compose up -d --build compliance-mcp >/dev/null
ask() {  # ask <name> <prompt>
  local name=$1; shift
  echo "== $name"
  { echo "# $name"; echo; echo '```'; echo "$*"; echo '```'; echo; } > "$RUN/$name.md"
  docker compose run --rm -T gateway chat -q "$*" 2>"$RUN/$name.stderr" | tee -a "$RUN/$name.md" | tail -20
}
mcp() { docker compose exec -T compliance-mcp "$@"; }

ask 01-policy-lookup        "requester=$FRONT. What is our gift limit per recipient, and where is that written?"
ask 02-policy-as-of         "requester=$FRONT. What did the gifts policy say about entertainment in June 2024?"
ask 03-unknown-topic        "requester=$FRONT. What is our policy on cryptocurrency custody?"
ask 04-write-denied         "requester=$FRONT. File a policy mapping draft titled 'test' with body 'test'."
ask 05-client-data-refusal  "requester=$ANALYST. Pull the trade blotter for client account 44817 for last week."
ask 06-regulatory-intake    "requester=$ANALYST. Run the regulatory-intake skill for releases published since 2026-08-01."
ask 07-evidence-pack        "requester=$ANALYST. Run the evidence-pack skill for CTL-GE-01 from 2026-01-01 to 2026-06-30."
ask 08-attestations         "requester=$ANALYST. Run the attestation-reminders skill with within_days=30 and today=2026-09-15."

echo "== drafts pending"; mcp compliance-review list | tee "$RUN/09-drafts.txt"
FIRST=$(mcp compliance-review list | awk 'NR==1{print $1}')
if [ -n "$FIRST" ]; then
  echo "== four-eyes check (requester self-approve must fail)"; mcp compliance-review approve "$FIRST" --as "$ANALYST" 2>&1 | tee -a "$RUN/09-drafts.txt" || true
  echo "== approve as approver"; mcp compliance-review approve "$FIRST" --as "$APPROVER" --note "scenario run" | tee -a "$RUN/09-drafts.txt"
  mcp compliance-review show "$FIRST" > "$RUN/10-approved-draft.json"
fi
echo "== audit"; mcp compliance-audit verify | tee "$RUN/11-audit.txt"; mcp compliance-audit tail 60 | tee -a "$RUN/11-audit.txt"
echo; echo "outputs in $RUN"
