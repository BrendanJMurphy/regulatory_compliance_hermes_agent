# Controls matrix

Maps each control the risk review asked for to where it is enforced. "Enforced by" names the
mechanism, not a promise. Anything marked *config* is only as good as the deployed
`hermes/config.yaml`, so that file is under change control and `hermes doctor` runs in CI.

| Id | Control | Enforced by | Evidence |
|----|---------|-------------|----------|
| SC-1 | No customer, client, or trade data in scope | MCP server only reads policies, controls, tickets, feed, attestations. No credentials for OMS or CRM exist in the deployment. | `mcp/src/compliance_mcp/store.py`, `.env.example` |
| SC-2 | Read by default, write by exception | Only `draft_create` writes, and only to the review queue (SQLite). No approve/publish/send tool exists; `tests/test_server.py` asserts the exact tool set. Every tool publishes an output schema. | test suite |
| SC-3 | Write requires role | `draft_create` requires `compliance-analysts`; unknown, inactive, or empty requester is denied. Directory reloads on change (TTL) and its snapshot version is stamped on every audit record. | `directory.py`, `test_service.py` |
| SC-4 | Four-eyes approval by an authenticated human | `compliance-review` in `oidc` mode verifies an ID token (signature, issuer, audience, expiry) and uses its username claim; `dev` mode is for synthetic data. Approver must be a person in `compliance-approvers` and not the requester. A draft is decided at most once (conditional UPDATE). | `review_cli.py`, `oidc.py`, `drafts.py`, tests |
| AU-1 | Every call and decision logged with correlation | One record per call (ok/denied/error) carrying requester, gateway session id, directory snapshot version, tool, redacted args. Review CLI writes to the same chain and records the OS user. | `audit.py`, `service.py` |
| AU-2 | Tamper evidence and authenticity | SHA-256 chain plus HMAC-SHA256 per record with a key held only by the server process (`COMPLIANCE_AUDIT_HMAC_KEY`). Rewriting the file without the key fails `verify`. File lock keeps multi-process writes on one chain; rotation continues the chain across files. | `test_audit.py` |
| AU-3 | Retention in WORM archive | Records and periodic head anchors are spooled to disk and forwarded by a background sender with retry; nothing is dropped when the sink is down. State lives on a host path for the platform's backup agents. | `Forwarder`, `docker-compose.yml` |
| AU-4 | No secrets or draft bodies in the audit log | Args redaction; draft body is logged as a hash. | `test_draft_body_is_hashed_not_stored_in_audit` |
| DR-1 | Model and data residency | *config*: `providers.firm-llm.base_url` points at the firm-hosted endpoint; auxiliary tasks inherit it. OpenRouter is permitted only with synthetic data (dev). | `hermes/config.yaml`, `.env.example` |
| DR-2 | No outbound internet or shell for the agent | *config*: every toolset in `toolsets.py` is denylisted except skills, cronjob, memory, clarify, context_engine. Verified inside the 0.21.3 image: the agent sees 5 built-in tools (clarify, memory, skills_list, skill_view, skill_manage) plus the MCP tools. Egress proxy allowlist at the network layer (platform). | `hermes/config.yaml`, `docs/verification.md` |
| SK-1 | Skill allowlisting | `hermes/.no-bundled-skills` marker stops the image seeding its 58 bundled skills at boot (verified: only `hermes-agent` essential plus the 5 compliance skills load). *config*: `external_dirs: []`, `project_discovery: false`, `guard_agent_created: true`, `write_approval: true`. Hub installs are CLI-only (`hermes skills install`) and so gated by host access. Skills are checked into this repo and reviewed by security. | `hermes/config.yaml`, `hermes/skills/` |
| SK-2 | Charter always in context | *config*: `skills.auto_load: [regcomply-charter]`. | `regcomply-charter/SKILL.md` |
| ID-1 | Requester identity on every call | `COMPLIANCE_IDENTITY_MODE=header` (production): identity comes from a header set by the authenticating gateway; a conflicting model-supplied value is refused and logged as a spoof attempt. `parameter` mode (dev) trusts the model. `TEAMS_ALLOWED_USERS` gates who can reach the bot at all. | `server.py::_caller_identity`, `test_server.py` |
| ID-2 | Service identity for unattended runs | Cron jobs run as `svc-regcomply@`, a `kind: service` account that can file drafts and can never approve. | `scripts/setup-cron.sh`, `directory.py` |
| MRM-1 | Model registered and validated | `eval/validate_extraction.py` with thresholds recall >= 0.85, hallucination <= 0.05, date accuracy >= 0.90. Re-run on any model change; result file attached to the inventory entry. | `eval/results/` |
| MRM-2 | Answers grounded in source | Charter and skills forbid answering policy questions from memory; tool output carries citations; drafts require verbatim quotes. Sampled weekly by an analyst. | skills, sampling log (external) |
| MEM-1 | No cross-user memory | *config*: `memory.memory_enabled: false` on the shared gateway. Continuity comes from governed records (drafts, tickets). | `hermes/config.yaml`, CI check |
| IN-1 | Input validation | Date arguments are pattern-checked in the MCP schema and validated as real, ordered dates; the clock override is disabled unless `COMPLIANCE_ALLOW_CLOCK_OVERRIDE`. Errors return a stable code; internals go to the log only. | `models.py`, `service.py` |
| OPS-1 | Supply chain and build | Dependencies pinned with hashes; multi-stage non-root image; CI builds and scans the image (Trivy) and fails on lock-file drift. | `mcp/requirements.txt`, `.github/workflows/ci.yml` |
| OPS-2 | Observability | JSON logs to stderr; Prometheus counters and latency histogram per tool at `/metrics`. | `logging_setup.py`, `server.py` |
| DC-1 | Draft content is machine-checked | `policy_mapping`: every quote in the obligations table must appear verbatim in a related release; `evidence_pack_index`: the cited manifest hash must equal the bundle recomputed now for that control and period. Refused drafts return `draft_rejected` with reasons; the prompt rule is backed by a server rule. | `draft_checks.py`, `test_features.py` |
| RL-1 | Runaway protection | Per-requester token bucket (`COMPLIANCE_RATE_LIMIT_PER_MINUTE`); denials audited. | `ratelimit.py` |
| FE-1 | Only the fetcher touches the internet | `compliance-feed` pulls RSS/Atom from an explicit regulator host allowlist, strips to plain text, and never overwrites a cached release (edited text arrives as a new id, so quoted text stays stable). Runs as a separate job; the agent has no egress. | `feed_fetcher.py` |
| EX-1 | Evidence packs are complete and verifiable | `compliance-review export` builds a zip only for an approved index: index, manifest, referenced policy documents (hash-checked), audit excerpt, cover sheet, `SHA256SUMS`. | `evidence_export.py` |
| RET-1 | Retention | `compliance-admin purge` removes decided drafts and rotated audit files past the configured period; dry run by default; the purge itself is audited. The active audit file is never touched. | `admin_cli.py` |
| TR-1 | Transport security to MCP | Bearer token (constant-time compare), DNS-rebinding protection, internal network only, GET refused. `/healthz` and `/metrics` are the only unauthenticated paths. | `server.py`, `docker-compose.yml` |

## Known limits
- Config keys were verified against the hermes-agent 0.21.3 source (`providers.<name>.key_env`,
  `agent.disabled_toolsets` names, `skills.*`, `memory.*`, `mcp_servers.*`, cron flags, Teams
  delivery). Re-verify on every Hermes upgrade: a renamed key would silently re-enable a toolset.
  The compose file pins the image by digest.
- At first boot the image migrates `config.yaml` to its current schema in place and writes a backup
  under `hermes/backups/`. The mounted `hermes/` directory is therefore runtime state as well as
  config; treat the git copy as the source of truth and diff after upgrades.
- Hermes does not pass the Teams sender identity to MCP servers per call (verified against
  0.21.3: MCP requests carry no user metadata). `header` mode therefore needs either a Hermes
  change or one gateway profile per user, each with its own static `X-Requester` header in
  `mcp_servers.compliance.headers`. Per-user profiles are workable for a small team and make
  identity transport-trusted; a Hermes change is the scalable path. Until that exists, the shipped
  configuration runs in `parameter` mode and is suitable for synthetic data only.
- The review CLI runs on the container host. OIDC mode makes the approver identity trustworthy,
  but the intended end state is an approval surface inside Teams (adaptive card) or an SSO web
  page so approvers never need shell access.
- Fixture data replaces real system adapters. Each class in `store.py` is the integration
  contract; production adapters must keep the same read-only shape.
