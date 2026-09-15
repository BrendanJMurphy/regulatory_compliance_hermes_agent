"""MCP transport layer. Registers each service method as a tool and enforces the bearer token.

Run with `compliance-mcp` (streamable HTTP on COMPLIANCE_MCP_HOST:COMPLIANCE_MCP_PORT/mcp)
or `compliance-mcp --stdio` for a local Hermes profile using a stdio MCP server.
"""

from __future__ import annotations

import sys
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from .service import ComplianceService
from .settings import SETTINGS, Settings

INSTRUCTIONS = """Governed compliance data for a regulated asset manager.
Every tool requires `requester`: the Azure AD object id or UPN of the human who asked.
Read tools return source-cited data. The only write is draft_create, which queues a draft
for human approval; nothing you do here publishes a policy, closes a finding, or contacts
anyone outside the firm. Answer policy questions only from policy_lookup results."""

Requester = Annotated[str, Field(description="Azure AD object id or UPN of the human requester (from the Teams message). Required.")]


def build_server(settings: Settings = SETTINGS) -> MCPServer:
    svc = ComplianceService(settings)
    server = MCPServer(name="compliance-mcp", instructions=INSTRUCTIONS, version="0.1.0")

    @server.tool(description="Search current approved policies for sections matching a question. Returns text plus a citation for each hit.")
    def policy_lookup(requester: Requester, query: str, limit: int = 5) -> dict:
        return svc.policy_lookup(requester, query, limit)

    @server.tool(description="Fetch one policy's metadata and version (current, or the version in force on a given date).")
    def policy_get(requester: Requester, policy_id: str, as_of: str | None = None) -> dict:
        return svc.policy_get(requester, policy_id, as_of)

    @server.tool(description="List current approved policies with owners, mapped regulations, and controls.")
    def policy_list(requester: Requester) -> dict:
        return svc.policy_list(requester)

    @server.tool(description="Find a control by id, or search controls by free text.")
    def control_lookup(requester: Requester, control_id: str = "", query: str = "") -> dict:
        return svc.control_lookup(requester, control_id, query)

    @server.tool(description="Control test results from the GRC system for a control over a date range (YYYY-MM-DD).")
    def control_test_results(requester: Requester, control_id: str, start: str | None = None, end: str | None = None) -> dict:
        return svc.control_test_results(requester, control_id, start, end)

    @server.tool(description="Regulatory releases published since a date (YYYY-MM-DD), optionally filtered by source: SEC, FINRA, FCA.")
    def regulatory_releases(requester: Requester, since: str, source: str = "") -> dict:
        return svc.regulatory_releases(requester, since, source)

    @server.tool(description="Full text and metadata of one regulatory release.")
    def regulatory_release_get(requester: Requester, release_id: str) -> dict:
        return svc.regulatory_release_get(requester, release_id)

    @server.tool(description="Search change/incident tickets by text, control id, and created-date range.")
    def ticket_search(requester: Requester, query: str = "", control_id: str = "", start: str | None = None, end: str | None = None) -> dict:
        return svc.ticket_search(requester, query, control_id, start, end)

    @server.tool(description="Open attestations and training items due within N days, with owner and manager.")
    def attestations_due(requester: Requester, within_days: int = 14, today: str | None = None) -> dict:
        return svc.attestations_due(requester, within_days, today)

    @server.tool(description="Assemble the evidence manifest for a control over a period: policy versions in force, test results, change tickets, and detected gaps. Read only.")
    def evidence_bundle(requester: Requester, control_id: str, start: str, end: str) -> dict:
        return svc.evidence_bundle(requester, control_id, start, end)

    @server.tool(description="Queue a draft for human review. kind: policy_mapping | evidence_pack_index | control_finding_note | attestation_escalation. Requires the compliance-analysts group. Nothing is published by this call.")
    def draft_create(requester: Requester, kind: str, title: str, body: str, related_ids: list[str] | None = None) -> dict:
        return svc.draft_create(requester, kind, title, body, related_ids)

    @server.tool(description="List drafts by status: pending | approved | rejected.")
    def draft_list(requester: Requester, status: str = "pending") -> dict:
        return svc.draft_list(requester, status)

    @server.tool(description="Fetch one draft including its body and any human decision.")
    def draft_get(requester: Requester, draft_id: str) -> dict:
        return svc.draft_get(requester, draft_id)

    return server


def _edge_middleware(app, token: str):
    """ASGI wrapper applied in front of the MCP app.

    1. Bearer auth: any request without the shared token gets 401 (when a token is configured).
    2. GET is refused with 405. The server runs stateless, so the streamable-HTTP GET channel
       (server-initiated messages) has nothing to send and would otherwise hold an event stream
       open forever. Hermes probes new endpoints with HEAD then GET and reads the full body, so
       an open stream makes its probe hang until timeout and the server never connects.
       Refusing GET makes the probe fall through to the JSON-RPC POST handshake immediately.
    """
    from starlette.responses import JSONResponse

    async def asgi(scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if token and headers.get("authorization") != f"Bearer {token}":
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
            if scope.get("method") == "GET":
                await JSONResponse({"error": "method not allowed; this server is stateless, use POST"}, status_code=405, headers={"Allow": "POST, DELETE"})(scope, receive, send)
                return
        await app(scope, receive, send)

    return asgi


def main() -> None:
    settings = SETTINGS
    server = build_server(settings)
    if "--stdio" in sys.argv:
        server.run(transport="stdio")
        return
    if not settings.bearer_token:
        print("[compliance-mcp] WARNING: COMPLIANCE_MCP_TOKEN is empty; the HTTP endpoint is unauthenticated. Dev only.", file=sys.stderr)
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(settings.allowed_hosts), allowed_origins=[])
    app = server.streamable_http_app(transport_security=security, host=settings.host, stateless_http=True, json_response=True)
    app = _edge_middleware(app, settings.bearer_token)
    import uvicorn

    print(f"[compliance-mcp] listening on http://{settings.host}:{settings.port}/mcp  data={settings.data_dir}  audit={settings.audit_log}", file=sys.stderr)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
