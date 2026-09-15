import json

from compliance_mcp.audit import verify
from tests.conftest import ANALYST, APPROVER, BOTH, FRONT_OFFICE, INACTIVE


def test_policy_lookup_cites_current_version_only(svc):
    r = svc.policy_lookup(ANALYST, "gift limit per recipient")
    assert r["ok"]
    hit = r["sections"][0]
    assert hit["policy_id"] == "POL-GE" and hit["version"] == "2.1"
    assert "v2.1" in hit["citation"] and "2025-01-15" in hit["citation"]
    # v2.0 is superseded and the v1.5 marketing draft is not approved: neither may surface.
    assert all(s["version"] != "2.0" for s in r["sections"])
    assert all(not (s["policy_id"] == "POL-MK" and s["version"] == "1.5") for s in svc.policy_lookup(ANALYST, "draft text under review")["sections"])


def test_policy_get_as_of_returns_version_in_force(svc):
    assert svc.policy_get(ANALYST, "POL-GE", as_of="2024-06-01")["policy"]["version"] == "2.0"
    assert svc.policy_get(ANALYST, "POL-GE", as_of="2025-06-01")["policy"]["version"] == "2.1"
    assert svc.policy_get(ANALYST, "POL-GE", as_of="2020-01-01")["policy"] is None


def test_any_allowlisted_user_can_read_but_unknown_and_inactive_cannot(svc):
    assert svc.policy_list(FRONT_OFFICE)["ok"]
    assert svc.policy_list("nobody@example-am.com")["error"] == "access_denied"
    assert svc.policy_list(INACTIVE)["error"] == "access_denied"
    assert svc.policy_list("")["error"] == "access_denied"


def test_draft_create_requires_analyst_group(svc):
    denied = svc.draft_create(FRONT_OFFICE, "policy_mapping", "t", "b")
    assert denied["error"] == "access_denied"
    ok = svc.draft_create(ANALYST, "policy_mapping", "Map FINRA 26-19 to POL-GE", "body", ["FINRA-RN-26-19", "POL-GE"])
    assert ok["ok"] and ok["status"] == "pending"
    assert svc.draft_list(FRONT_OFFICE)["drafts"][0]["draft_id"] == ok["draft_id"]
    assert svc.draft_create(ANALYST, "publish_policy", "t", "b")["error"] == "ValueError"


def test_evidence_bundle_detects_gaps(svc):
    r = svc.evidence_bundle(ANALYST, "CTL-GE-01", "2026-01-01", "2026-06-30")
    m = r["manifest"]
    assert len(m["test_results"]) == 6
    assert {v["version"] for v in m["policy_versions"]} == {"2.0", "2.1"}
    assert any("T-2026-027" in g for g in m["gaps"])
    assert m["change_tickets"][0]["ticket_id"] == "CHG-2026-0412"
    short = svc.evidence_bundle(ANALYST, "CTL-GE-01", "2026-07-01", "2026-08-31")["manifest"]
    assert any("expected at least 2 monthly" in g for g in short["gaps"])


def test_regulatory_feed_and_attestations(svc):
    rel = svc.regulatory_releases(ANALYST, "2026-08-01")
    assert [r["release_id"] for r in rel["releases"]] == ["SEC-2026-0812-MKTG", "FINRA-RN-26-19", "FCA-PS26-9"]
    assert svc.regulatory_releases(ANALYST, "2026-08-01", source="FCA")["releases"][0]["release_id"] == "FCA-PS26-9"
    due = svc.attestations_due(ANALYST, within_days=30, today="2026-09-15")
    assert [a["attestation_id"] for a in due["attestations"]] == ["TRN-2026-AML-014", "ATT-2026-Q3-001"]


def test_every_call_is_audited_and_chain_verifies(svc, settings):
    svc.policy_lookup(ANALYST, "best execution")
    svc.draft_create(FRONT_OFFICE, "policy_mapping", "t", "b")
    svc.evidence_bundle(ANALYST, "CTL-NOPE", "2026-01-01", "2026-02-01")
    lines = [json.loads(l) for l in settings.audit_log.read_text().splitlines()]
    assert [l["outcome"] for l in lines] == ["ok", "denied", "error"]
    assert lines[0]["prev_hash"] == "0" * 64 and lines[1]["prev_hash"] == lines[0]["hash"]
    ok, count, _ = verify(settings.audit_log)
    assert ok and count == 3
    # Tamper with the middle record: the chain must break.
    lines[1]["requester"] = "someone.else"
    settings.audit_log.write_text("\n".join(json.dumps(l, sort_keys=True) for l in lines) + "\n")
    ok, _, msg = verify(settings.audit_log)
    assert not ok and "altered" in msg


def test_draft_body_is_hashed_not_stored_in_audit(svc, settings):
    svc.draft_create(ANALYST, "control_finding_note", "note", "confidential body text")
    rec = json.loads(settings.audit_log.read_text().splitlines()[-1])
    assert "confidential" not in json.dumps(rec) and "body_sha256" in rec["args"]


def test_concurrent_writers_share_one_chain(settings):
    """Two AuditLog instances (as in server + review CLI) interleaving writes must produce one valid chain."""
    from compliance_mcp.audit import AuditLog

    a = AuditLog(settings.audit_log, "a")
    b = AuditLog(settings.audit_log, "b")
    for i in range(10):
        (a if i % 2 else b).write(requester="x", tool="t", args={}, outcome="ok", result_summary=str(i))
    ok, count, _ = verify(settings.audit_log)
    assert ok and count == 10
