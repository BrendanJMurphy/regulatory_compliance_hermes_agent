"""MCP transport: registers the service as tools and enforces the edge controls.

Layers, outermost first:

1. ``_edge_middleware`` (ASGI): bearer token, GET refusal, ``/healthz`` and ``/metrics``.
2. The SDK's streamable-HTTP app with DNS-rebinding protection.
3. Tool functions, which resolve the caller's identity from the request (see
   ``_caller_identity``) and delegate to ``ComplianceService``.

Run ``compliance-mcp`` for HTTP, or ``compliance-mcp --stdio`` for a local stdio profile.
"""

from __future__ import annotations

import hmac
import sys
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import Field

from . import __version__
from .audit import AuditLog, Forwarder
from .directory import Directory
from .drafts import DraftStore
from .logging_setup import configure_logging, get_logger
from .models import (
    AttestationsDueResult,
    CallerIdentity,
    ControlLookupResult,
    ControlTestResultsResult,
    DraftCreateResult,
    DraftGetResult,
    DraftKind,
    DraftListResult,
    DraftStatus,
    EvidenceBundleResult,
    IdentitySource,
    IsoDate,
    PolicyGetResult,
    PolicyListResult,
    PolicyLookupResult,
    RegulatoryReleaseGetResult,
    RegulatoryReleasesResult,
    TicketSearchResult,
    ToolError,
)
from .service import ComplianceService
from .settings import SETTINGS, IdentityMode, Settings

log = get_logger(__name__)

INSTRUCTIONS = """Governed compliance data for a regulated asset manager.
Every tool takes `requester`: the UPN or Azure AD object id of the human who asked.
Read tools return source-cited data. The only write is draft_create, which queues a draft
for human approval; nothing here publishes a policy, closes a finding, or contacts anyone.
Answer policy questions only from policy_lookup / policy_get results."""

Requester = Annotated[
    str, Field(description="UPN or Azure AD object id of the human requester. In production the gateway supplies it; pass what the platform gave you.")
]

TOOL_CALLS = Counter("compliance_tool_calls_total", "Tool calls by tool and outcome", ["tool", "outcome"])
TOOL_LATENCY = Histogram("compliance_tool_seconds", "Tool call latency", ["tool"])


def build_service(settings: Settings) -> ComplianceService:
    """Wire the service from settings. Kept separate so tests can build one without HTTP."""
    forwarder = None
    if settings.audit_forward_url:
        forwarder = Forwarder(settings.audit_spool_dir, settings.audit_forward_url, settings.audit_forward_token)
        forwarder.start()
    audit = AuditLog(
        settings.audit_log,
        settings.agent_id,
        hmac_key=settings.audit_hmac_key,
        rotate_bytes=settings.audit_rotate_bytes,
        forwarder=forwarder,
        anchor_every=settings.audit_anchor_every,
    )
    directory = Directory(settings.data_dir / "users.json", ttl_seconds=settings.directory_ttl_seconds)
    return ComplianceService(settings, audit=audit, directory=directory, drafts=DraftStore(settings.drafts_db))


def _caller_identity(ctx: Context, requester_param: str, settings: Settings) -> CallerIdentity:
    """Decide who the caller is, according to ``settings.identity_mode``.

    HEADER mode trusts a header set by the authenticating gateway and treats a conflicting
    model-supplied value as a spoof attempt (strict) or noise (lenient). PARAMETER mode
    trusts the model, which is only acceptable with synthetic data.
    """
    headers = {k.lower(): v for k, v in (ctx.headers or {}).items()} if ctx else {}
    session_id = headers.get(settings.session_header, "")
    if settings.identity_mode is IdentityMode.HEADER:
        from_header = headers.get(settings.identity_header, "").strip()
        if not from_header:
            return CallerIdentity(requester="", source=IdentitySource.HEADER, session_id=session_id)
        if settings.identity_header_strict and requester_param.strip() and requester_param.strip().lower() != from_header.lower():
            log.warning("requester parameter disagrees with identity header", extra={"header": from_header, "parameter": requester_param})
            return CallerIdentity(requester="", source=IdentitySource.HEADER, session_id=session_id)
        return CallerIdentity(requester=from_header, source=IdentitySource.HEADER, session_id=session_id)
    return CallerIdentity(requester=requester_param, source=IdentitySource.PARAMETER, session_id=session_id)


def build_server(settings: Settings = SETTINGS, service: ComplianceService | None = None) -> MCPServer:
    svc = service or build_service(settings)
    server = MCPServer(name="compliance-mcp", instructions=INSTRUCTIONS, version=__version__)

    def call(ctx: Context, requester: str, tool: str, **kwargs):
        caller = _caller_identity(ctx, requester, settings)
        with TOOL_LATENCY.labels(tool).time():
            result = getattr(svc, tool)(caller, **kwargs)
        TOOL_CALLS.labels(tool, result.error if isinstance(result, ToolError) else "ok").inc()
        return result

    # Each tool is a thin, typed shim. Return annotations give the MCP client an output schema.

    @server.tool(description="Search current approved policies for sections matching a question. Each hit carries a citation.")
    def policy_lookup(ctx: Context, requester: Requester, query: str, limit: int = 5) -> PolicyLookupResult | ToolError:
        return call(ctx, requester, "policy_lookup", query=query, limit=limit)

    @server.tool(description="One policy: current version, or the version in force on as_of (YYYY-MM-DD).")
    def policy_get(ctx: Context, requester: Requester, policy_id: str, as_of: IsoDate | None = None) -> PolicyGetResult | ToolError:
        return call(ctx, requester, "policy_get", policy_id=policy_id, as_of=as_of)

    @server.tool(description="List current approved policies with owners, mapped regulations, and controls.")
    def policy_list(ctx: Context, requester: Requester) -> PolicyListResult | ToolError:
        return call(ctx, requester, "policy_list")

    @server.tool(description="Find a control by id, or search controls by free text.")
    def control_lookup(ctx: Context, requester: Requester, control_id: str = "", query: str = "") -> ControlLookupResult | ToolError:
        return call(ctx, requester, "control_lookup", control_id=control_id, query=query)

    @server.tool(description="Control test results from the GRC system over a date range.")
    def control_test_results(
        ctx: Context, requester: Requester, control_id: str, start: IsoDate | None = None, end: IsoDate | None = None
    ) -> ControlTestResultsResult | ToolError:
        return call(ctx, requester, "control_test_results", control_id=control_id, start=start, end=end)

    @server.tool(description="Regulatory releases published since a date, optionally filtered by source: SEC, FINRA, FCA.")
    def regulatory_releases(ctx: Context, requester: Requester, since: IsoDate, source: str = "") -> RegulatoryReleasesResult | ToolError:
        return call(ctx, requester, "regulatory_releases", since=since, source=source)

    @server.tool(description="Full text and metadata of one regulatory release.")
    def regulatory_release_get(ctx: Context, requester: Requester, release_id: str) -> RegulatoryReleaseGetResult | ToolError:
        return call(ctx, requester, "regulatory_release_get", release_id=release_id)

    @server.tool(description="Search change and incident tickets by text, control id, and created-date range.")
    def ticket_search(
        ctx: Context, requester: Requester, query: str = "", control_id: str = "", start: IsoDate | None = None, end: IsoDate | None = None
    ) -> TicketSearchResult | ToolError:
        return call(ctx, requester, "ticket_search", query=query, control_id=control_id, start=start, end=end)

    @server.tool(description="Open attestations and training due within N days, with owner and manager.")
    def attestations_due(ctx: Context, requester: Requester, within_days: int = 14, today: IsoDate | None = None) -> AttestationsDueResult | ToolError:
        return call(ctx, requester, "attestations_due", within_days=within_days, today=today)

    @server.tool(description="Evidence manifest for a control over a period: policy versions in force, test results, tickets, gaps. Read only.")
    def evidence_bundle(ctx: Context, requester: Requester, control_id: str, start: IsoDate, end: IsoDate) -> EvidenceBundleResult | ToolError:
        return call(ctx, requester, "evidence_bundle", control_id=control_id, start=start, end=end)

    @server.tool(description="Queue a draft for human review. Requires the compliance-analysts group. Publishes nothing.")
    def draft_create(
        ctx: Context, requester: Requester, kind: DraftKind, title: str, body: str, related_ids: list[str] | None = None
    ) -> DraftCreateResult | ToolError:
        return call(ctx, requester, "draft_create", kind=kind, title=title, body=body, related_ids=tuple(related_ids or ()))

    @server.tool(description="List drafts by status.")
    def draft_list(ctx: Context, requester: Requester, status: DraftStatus = DraftStatus.PENDING) -> DraftListResult | ToolError:
        return call(ctx, requester, "draft_list", status=status)

    @server.tool(description="One draft including its body and any human decision.")
    def draft_get(ctx: Context, requester: Requester, draft_id: str) -> DraftGetResult | ToolError:
        return call(ctx, requester, "draft_get", draft_id=draft_id)

    return server


def _edge_middleware(app, token: str):
    """ASGI wrapper in front of the MCP app.

    * ``/healthz`` and ``/metrics`` are served here, unauthenticated, for the orchestrator.
    * Every other request needs the bearer token (constant-time compare) when one is set.
    * GET on the MCP path is refused. The server is stateless, so the streamable-HTTP GET
      channel has nothing to send; left open it hangs clients that probe with GET.
    """
    from starlette.responses import JSONResponse, Response

    async def asgi(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/healthz":
            await JSONResponse({"status": "ok", "version": __version__})(scope, receive, send)
            return
        if path == "/metrics":
            await Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if token and not hmac.compare_digest(headers.get("authorization", ""), f"Bearer {token}"):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        if scope.get("method") == "GET":
            await JSONResponse({"error": "method not allowed; this server is stateless, use POST"}, status_code=405, headers={"Allow": "POST, DELETE"})(
                scope, receive, send
            )
            return
        await app(scope, receive, send)

    return asgi


def main() -> None:
    settings = SETTINGS
    configure_logging(json_output=settings.log_json)
    server = build_server(settings)
    if "--stdio" in sys.argv:
        server.run(transport="stdio")
        return
    if not settings.bearer_token:
        log.warning("COMPLIANCE_MCP_TOKEN is empty; the HTTP endpoint is unauthenticated (dev only)")
    if settings.identity_mode is IdentityMode.PARAMETER:
        log.warning("identity mode is 'parameter': the model supplies requester identity (dev only)")
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(settings.allowed_hosts), allowed_origins=[])
    app = _edge_middleware(
        server.streamable_http_app(transport_security=security, host=settings.host, stateless_http=True, json_response=True), settings.bearer_token
    )
    import uvicorn

    log.info(
        "compliance-mcp listening",
        extra={"host": settings.host, "port": settings.port, "identity_mode": settings.identity_mode, "data_dir": str(settings.data_dir)},
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
