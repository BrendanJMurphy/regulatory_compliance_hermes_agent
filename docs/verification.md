# Verification log

What was checked, how, and on which version. Re-run on every Hermes upgrade.

## 2026-09-15, hermes-agent 0.21.3 (image nousresearch/hermes-agent, upstream c294e945)

All checks ran inside Docker with a throwaway copy of `hermes/` mounted as `/opt/data`.
Nothing was installed on the host and `~/.hermes` was never created.

| Check | Method | Result |
|-------|--------|--------|
| Config keys resolve | `hermes config get` for model, providers, agent.disabled_toolsets, skills.*, memory.write_approval, mcp_servers | All values echoed back as written; MCP header shown redacted |
| Named provider shape | `hermes_cli/providers.py::resolve_user_provider` reads `base_url` and `key_env` | Config uses those keys; `api_key` is not read for named providers |
| Provider key reaches the wire | throwaway containers against OpenRouter with a fake but well-formed key (`sk-or-v1-...`): `key_env` only from process env, `key_env` + `api_key: "${VAR}"`, key in HERMES_HOME/.env, built-in `openrouter` provider | All four sent the header (401 "User not found" = header present, key invalid). A malformed fake key (`sk-or-dummy-plumbing-test`) was silently dropped by Hermes's placeholder check and produced 401 "Missing Authentication header". Config sets both `key_env` and `api_key`. |
| Gateway reaches MCP over the compose network | curl from the gateway container | 401 without token, 200 with token |
| Toolset names | `toolsets.py` registry | All denylisted names exist; allowlist is skills, cronjob, memory, clarify, context_engine |
| Effective tool surface | `model_tools.get_tool_definitions(None, disabled_toolsets)` in-container | 5 tools: clarify, memory, skill_manage, skill_view, skills_list |
| Bundled skill seeding | boot with and without `.no-bundled-skills` | Without: 58 skills seeded. With: 1 essential (`hermes-agent`) plus the 5 compliance skills |
| Skills load | `hermes skills list` | 5 local compliance skills enabled, 0 hub-installed |
| Cron flags | `hermes_cli/subcommands/cron.py` | `--name`, `--deliver`, `--skill` (repeatable) exist |
| Teams cron delivery | `plugins/platforms/teams/adapter.py` | `deliver=teams` routes to `TEAMS_HOME_CHANNEL` |
| MCP config keys | `tools/mcp_tool_*.py` | `url`, `headers`, `timeout`, `connect_timeout`, `enabled`, `tools.include/exclude` read |
| MCP server | pytest (11), live HTTP client with and without bearer token, `compliance-audit verify` | Pass; 401 without token; 13 tools; chain verifies |
| MCP image | `docker build`, in-container service call | Builds; fixture data loads |
| Compose file | `docker compose config --quiet` | Valid |

## Not verified
- A live model round-trip. No governed endpoint exists yet; `eval/validate_extraction.py` is ready for it.
- Teams end to end. Needs the Azure Bot registration and a tunnel or public ingress.
- The `hermes doctor` warnings about npm vulnerabilities in the image's browser and web workspaces.
  Both toolsets are disabled here, but the packages are still in the image; raise with the platform team.
