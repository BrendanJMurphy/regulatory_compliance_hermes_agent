# Changelog

## 0.2.0 (2026-09-17)

Hardening pass toward an enterprise-grade control environment.

- Identity: `COMPLIANCE_IDENTITY_MODE=header` trusts an authenticating gateway's header and
  treats a conflicting model-supplied requester as a spoof; `parameter` mode is dev only.
- Approvals: `compliance-review` verifies an OIDC ID token in production; service accounts can
  never approve; a draft is decided at most once even under a race (SQLite, conditional update).
- Audit: HMAC per record with a key held only by the server; rotation with unbroken chain
  across files; periodic head anchoring; spooled background forwarding with retry.
- Correlation: every audit record carries the gateway session id and the directory snapshot
  version that authorised the call.
- Input validation: dates are pattern-checked in the MCP schema and validated as real dates;
  ranges must be ordered; clock override is gated behind `COMPLIANCE_ALLOW_CLOCK_OVERRIDE`.
- Typed contracts: pydantic models for every record and tool result; tools publish output schemas.
- Errors: the model receives a stable code and a safe message; tracebacks go to structured logs.
- Directory: reloads on change with a TTL; unattended jobs run as a service account.
- Hermes profile: memory disabled on the shared gateway; terminal backend set to local.
- Operations: `/healthz` and `/metrics`; hashed, pinned dependencies; multi-stage non-root
  image; compose hardening (loopback bind, capability drop, resource limits, host-backed state).
- CI: lint, types, tests, lock-file drift, image build, Trivy scan, Hermes config sanity.
- Repo: LICENSE (MIT), SECURITY.md, CODEOWNERS, this changelog.

## 0.1.0 (2026-09-15)

Initial example: MCP server, five skills, Docker deployment, fixture data, live sample run.
