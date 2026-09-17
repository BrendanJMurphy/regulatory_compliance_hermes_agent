# Security

## Reporting

Open a private security advisory on GitHub for this repository, or email the maintainer.
Do not open a public issue for anything that could be exploited. Expect an acknowledgement
within three business days.

## Scope and model

This is an example deployment pattern with synthetic data. The security-relevant pieces are:

- **compliance-mcp**: bearer-token transport auth, identity resolution (header or parameter
  mode), role gating, the single draft-only write path, and the MAC'd hash-chained audit log.
- **compliance-review**: OIDC-verified approver identity, four-eyes, single decision per draft.
- **Hermes profile**: toolset denylist, bundled-skill opt-out, memory disabled, MCP-only data access.

Known limits and their mitigations are tracked in `docs/controls-matrix.md`. The most
important: `COMPLIANCE_IDENTITY_MODE=parameter` trusts the model to report who is asking and
is for synthetic data only. Production requires `header` mode behind an authenticating gateway.

## Dependencies

`mcp/requirements.txt` pins every dependency with hashes; CI fails if it drifts from
`pyproject.toml` and scans the built image with Trivy for high and critical CVEs.
