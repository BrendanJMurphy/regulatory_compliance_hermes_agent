import pytest

from compliance_mcp.server import build_server

EXPECTED = {
    "policy_lookup", "policy_get", "policy_list", "control_lookup", "control_test_results",
    "regulatory_releases", "regulatory_release_get", "ticket_search", "attestations_due",
    "evidence_bundle", "draft_create", "draft_list", "draft_get",
}


@pytest.mark.asyncio
async def test_tool_surface_is_exactly_the_governed_set(settings):
    server = build_server(settings)
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED
    for t in tools:
        assert "requester" in t.input_schema["required"], f"{t.name} must require requester"
    # No approve/publish/send tool is exposed to the agent.
    assert not {n for n in names if any(w in n for w in ("approve", "publish", "send", "delete"))}


@pytest.mark.asyncio
async def test_edge_middleware_rejects_get_and_missing_token(settings):
    from httpx import ASGITransport, AsyncClient
    from mcp.server.transport_security import TransportSecuritySettings
    from compliance_mcp.server import _edge_middleware

    server = build_server(settings)
    app = server.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host="127.0.0.1", stateless_http=True, json_response=True)
    app = _edge_middleware(app, "secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/mcp", json={})).status_code == 401
        r = await c.get("/mcp", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 405 and r.headers["allow"] == "POST, DELETE"
    # The POST handshake itself is covered by the live smoke test in docs/verification.md;
    # the ASGI test transport does not run the streamable-HTTP app's lifespan.
