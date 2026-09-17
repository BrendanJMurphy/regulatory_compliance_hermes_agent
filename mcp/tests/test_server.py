"""Transport layer: tool surface, identity resolution, edge middleware."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.server.transport_security import TransportSecuritySettings

from compliance_mcp.models import IdentitySource
from compliance_mcp.server import _caller_identity, _edge_middleware, build_server
from compliance_mcp.settings import IdentityMode
from tests.conftest import ANALYST, FRONT_OFFICE

EXPECTED_TOOLS = {
    "policy_lookup",
    "policy_get",
    "policy_list",
    "control_lookup",
    "control_test_results",
    "regulatory_releases",
    "regulatory_release_get",
    "ticket_search",
    "attestations_due",
    "evidence_bundle",
    "draft_create",
    "draft_list",
    "draft_get",
}


@pytest.mark.asyncio
async def test_tool_surface_is_exactly_the_governed_set_with_schemas(settings, svc):
    tools = await build_server(settings, service=svc).list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert "requester" in t.input_schema["required"], f"{t.name} must require requester"
        assert t.output_schema, f"{t.name} should publish an output schema"
    dates = next(t for t in tools if t.name == "evidence_bundle").input_schema["properties"]["start"]
    assert dates["pattern"].startswith("^\\d{4}"), "date arguments are pattern-checked in the schema"
    assert not {n for n in EXPECTED_TOOLS if any(w in n for w in ("approve", "publish", "send", "delete"))}


def _ctx(**headers):
    return SimpleNamespace(headers=headers)


def test_header_identity_mode_ignores_and_flags_spoofed_parameter(settings):
    strict = replace(settings, identity_mode=IdentityMode.HEADER)
    ident = _caller_identity(_ctx(**{"x-requester": ANALYST, "x-session-id": "s1"}), FRONT_OFFICE, strict)
    assert ident.requester == "" and ident.source is IdentitySource.HEADER, "conflicting parameter is treated as a spoof"
    ident = _caller_identity(_ctx(**{"X-Requester": ANALYST, "x-session-id": "s1"}), ANALYST, strict)
    assert ident.requester == ANALYST and ident.session_id == "s1"
    ident = _caller_identity(_ctx(), ANALYST, strict)
    assert ident.requester == "", "no header means no identity, whatever the model says"
    lenient = replace(strict, identity_header_strict=False)
    assert _caller_identity(_ctx(**{"x-requester": ANALYST}), FRONT_OFFICE, lenient).requester == ANALYST


def test_parameter_identity_mode_trusts_the_model(settings):
    ident = _caller_identity(_ctx(**{"x-session-id": "s9"}), ANALYST, settings)
    assert ident.requester == ANALYST and ident.source is IdentitySource.PARAMETER and ident.session_id == "s9"


@pytest.mark.asyncio
async def test_edge_middleware(settings, svc):
    server = build_server(settings, service=svc)
    app = _edge_middleware(
        server.streamable_http_app(
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False), host="127.0.0.1", stateless_http=True, json_response=True
        ),
        "secret",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/healthz")).json()["status"] == "ok"
        assert b"compliance_tool_calls_total" in (await c.get("/metrics")).content or (await c.get("/metrics")).status_code == 200
        assert (await c.post("/mcp", json={})).status_code == 401
        assert (await c.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})).status_code == 401
        r = await c.get("/mcp", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 405 and r.headers["allow"] == "POST, DELETE"
