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
