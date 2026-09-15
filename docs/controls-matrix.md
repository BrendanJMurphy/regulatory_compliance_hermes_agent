# Controls matrix

Maps each control the risk review asked for to where it is enforced. "Enforced by" names the
mechanism, not a promise. Anything marked *config* is only as good as the deployed
`hermes/config.yaml`, so that file is under change control and `hermes doctor` runs in CI.

| Id | Control | Enforced by | Evidence |
|----|---------|-------------|----------|
| SC-1 | No customer, client, or trade data in scope | MCP server only reads policies, controls, tickets, feed, attestations. No credentials for OMS or CRM exist in the deployment. | `mcp/src/compliance_mcp/store.py`, `.env.example` |
| SC-2 | Read by default, write by exception | Only `draft_create` writes, and only to the review queue. No approve/publish/send tool exists (`tests/test_server.py`). | test suite |
| SC-3 | Write requires role | `draft_create` requires `compliance-analysts`; unknown, inactive, or empty requester is denied. | `access.py`, `test_service.py` |
| SC-4 | Four-eyes approval by a human | `compliance-review approve` requires `compliance-approvers` and a different person from the requester. Not reachable from the agent. | `review_cli.py`, `test_review_cli.py` |
| AU-1 | Every prompt, tool call, and decision logged | MCP server writes one hash-chained record per call (ok/denied/error). Review CLI writes to the same chain. Hermes session logs cover prompts and model output. | `audit.py`, `compliance-audit verify` |
| AU-2 | Tamper evidence | SHA-256 chain; `verify` fails on any edited or removed record. File lock keeps multi-process writes on one chain. | `test_service.py::test_every_call_is_audited_and_chain_verifies` |
| AU-3 | Retention in WORM archive | `COMPLIANCE_AUDIT_FORWARD_URL` streams each record; local file is shipped nightly by the platform team. Books-and-records retention period applies. | platform runbook (external) |
| AU-4 | No secrets or draft bodies in the audit log | Args redaction; draft body is logged as a hash. | `test_draft_body_is_hashed_not_stored_in_audit` |
| DR-1 | Model and data residency | *config*: `providers.custom.base_url` points at the firm-hosted endpoint; compression uses the same. No consumer API keys in `.env`. | `hermes/config.yaml` |
| DR-2 | No outbound internet or shell for the agent | *config*: every toolset in `toolsets.py` is denylisted except skills, cronjob, memory, clarify, context_engine. Verified inside the 0.21.3 image: the agent sees 5 built-in tools (clarify, memory, skills_list, skill_view, skill_manage) plus the MCP tools. Egress proxy allowlist at the network layer (platform). | `hermes/config.yaml`, `docs/verification.md` |
| SK-1 | Skill allowlisting | `hermes/.no-bundled-skills` marker stops the image seeding its 58 bundled skills at boot (verified: only `hermes-agent` essential plus the 5 compliance skills load). *config*: `external_dirs: []`, `project_discovery: false`, `guard_agent_created: true`, `write_approval: true`. Hub installs are CLI-only (`hermes skills install`) and so gated by host access. Skills are checked into this repo and reviewed by security. | `hermes/config.yaml`, `hermes/skills/` |
| SK-2 | Charter always in context | *config*: `skills.auto_load: [regcomply-charter]`. | `regcomply-charter/SKILL.md` |
| ID-1 | Requester identity on every call | Every MCP tool has a required `requester` parameter; the charter instructs the agent to pass the Teams sender. `TEAMS_ALLOWED_USERS` gates who can reach the bot at all. | `test_server.py`, `.env.example` |
| ID-2 | Service identity for unattended runs | Cron jobs run as a named service UPN that is in the allowlist. | `scripts/setup-cron.sh` |
| MRM-1 | Model registered and validated | `eval/validate_extraction.py` with thresholds recall >= 0.85, hallucination <= 0.05, date accuracy >= 0.90. Re-run on any model change; result file attached to the inventory entry. | `eval/results/` |
| MRM-2 | Answers grounded in source | Charter and skills forbid answering policy questions from memory; tool output carries citations; drafts require verbatim quotes. Sampled weekly by an analyst. | skills, sampling log (external) |
| MEM-1 | Memory limited and approved | *config*: `memory.write_approval: true`, `user_profile_enabled: false`. | `hermes/config.yaml` |
| TR-1 | Transport security to MCP | Bearer token required (401 otherwise), DNS-rebinding protection with allowed hosts, internal Docker network only. | `server.py`, `docker-compose.yml` |

## Known limits
- Config keys were verified against the hermes-agent 0.21.3 source (`providers.<name>.key_env`,
  `agent.disabled_toolsets` names, `skills.*`, `memory.*`, `mcp_servers.*`, cron flags, Teams
  delivery). Re-verify on every Hermes upgrade: a renamed key would silently re-enable a toolset.
  The compose file pins the image by digest.
- At first boot the image migrates `config.yaml` to its current schema in place and writes a backup
  under `hermes/backups/`. The mounted `hermes/` directory is therefore runtime state as well as
  config; treat the git copy as the source of truth and diff after upgrades.
- Requester identity is passed by the model, not injected by the transport. The Teams allowlist
  prevents outsiders, but a permitted user could ask the agent to use another allowlisted UPN.
  Mitigation until Hermes exposes per-call sender metadata to MCP: audit sampling, and the
  approver sees the requester on every draft. Track as an open risk.
- Fixture data replaces real system adapters. Each class in `store.py` is the integration
  contract; production adapters must keep the same read-only shape.
