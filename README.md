# Regulatory Change and Evidence agent

A self-hosted [Hermes](https://hermes-agent.nousresearch.com) agent for the compliance team of a
regulated asset manager. It answers policy questions with citations, drafts obligation mappings
for new regulatory releases, assembles evidence-pack indexes, and chases attestations, all
through Microsoft Teams. It cannot publish, approve, or send anything: every write is a draft
that a named human approves.

```
Teams  ──▶  Hermes gateway (nousresearch/hermes-agent)  ──▶  compliance-mcp (this repo)  ──▶  policy repo / GRC / tickets / regulator feed
                 │  model: firm-hosted OpenAI-compatible endpoint             │
                 │  skills: 5 reviewed skills, hub disabled                    └─▶  audit.jsonl (hash chain) ─▶ SIEM / WORM
                 └  toolsets: web, browser, terminal, file all off
                                                    humans ──▶ compliance-review approve/reject
```

## Layout

| Path | What |
|------|------|
| `hermes/config.yaml` | Hermes profile: governed model endpoint, disabled toolsets, skill lockdown, MCP wiring. Mounted at `/opt/data`. |
| `hermes/skills/compliance/` | The five skills: charter (always loaded), policy-lookup, regulatory-intake, evidence-pack, attestation-reminders. |
| `mcp/` | The compliance MCP server: 12 read tools plus `draft_create`, typed contracts, identity resolution, role gating, MAC'd hash-chained audit log with spooled forwarding, SQLite review queue, OIDC-verified review CLI. Fixture data under `mcp/data/`. |
| `eval/` | Gold set and scorer for the extraction step (model risk validation). |
| `scripts/` | `bootstrap.sh` (compose bring-up), `setup-cron.sh` (the two scheduled jobs). |
| `docs/` | Controls matrix, rollout plan, verification log, and a captured sample run. |

## Run it locally, without turning your machine into a Hermes box

Everything runs in containers. Hermes's home directory is this repo's `hermes/` folder mounted
into the gateway container, so nothing is written to `~/.hermes`, no installer touches your shell
profile, and `docker compose down -v` removes all state. Requires Docker Desktop.
The fixture data lets the whole loop run with no connection to real systems.

```bash
cp .env.example .env            # fill in model endpoint, MCP token, Teams credentials
./scripts/bootstrap.sh
docker compose exec gateway hermes doctor
docker compose exec gateway hermes config get agent.disabled_toolsets
./scripts/setup-cron.sh         # needs TEAMS_HOME_CHANNEL in .env
```

To exercise the agent without Teams, use the CLI inside the container:

```bash
docker compose exec gateway hermes chat -q "What is our gift limit? requester=tom.reyes@example-am.com"
```

Human review of drafts and audit checks run against the MCP container:

```bash
docker compose exec compliance-mcp compliance-review list
docker compose exec compliance-mcp compliance-review approve D-20260915-abcd1234 --as dana.whitfield@example-am.com --note "reviewed"
docker compose exec compliance-mcp compliance-audit verify
docker compose exec compliance-mcp compliance-audit tail 50
```

## Repeatable test runs

```bash
./scripts/reset-state.sh      # wipe drafts, audit log, sessions, memory
./scripts/run-scenarios.sh    # 8 scenarios + human review + audit verify, saved to runs/<timestamp>/
```

`scripts/check-run.py` asserts the run's invariants (guardrails held, tools used where required,
three intake drafts, audit chain verified) and the runner calls it at the end. `docs/sample-run.md`
is one captured run. A full run costs well under a dollar on Sonnet.

## Develop the MCP server

```bash
cd mcp && uv venv && . .venv/bin/activate && uv pip install -e ".[dev]"
pytest && ruff check src tests && mypy              # 28 tests: identity, roles, drafts under race, audit chain/MAC/rotation/forwarding, OIDC, tool schemas
COMPLIANCE_MCP_TOKEN=dev compliance-mcp            # http://127.0.0.1:8765/mcp
```

For a local Hermes profile without Docker, point `mcp_servers.compliance` at a stdio command
instead of a URL: `command: compliance-mcp`, `args: ["--stdio"]`.

## Model validation

```bash
COMPLIANCE_MODEL_BASE_URL=... COMPLIANCE_MODEL_API_KEY=... COMPLIANCE_MODEL=... python eval/validate_extraction.py
```

Thresholds and the reason for each are in `docs/controls-matrix.md` (MRM-1). Run before go-live
and after any model or prompt change.

## What is real and what is a stub

Real: the MCP server, its identity and access rules, the MAC'd audit chain with rotation and
spooled forwarding, the SQLite review queue, the OIDC-verified review CLI, the tests, the skills,
the Hermes config, the CI pipeline, and the compose topology.

Stubs: the five adapters in `mcp/src/compliance_mcp/store.py` read JSON and Markdown fixtures.
Each is the integration contract for the real policy repository, GRC platform, ticketing system,
and regulator feed cache. Replace the bodies, keep the read-only interfaces.

Everything in the config was verified inside the official 0.21.3 image; see `docs/verification.md`
for the method and results, and `docs/controls-matrix.md` for known limits.
