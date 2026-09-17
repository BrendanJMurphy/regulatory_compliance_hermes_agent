import json

from compliance_mcp.audit import verify
from compliance_mcp.models import DraftKind, PolicyLookupResult, ToolError
from tests.conftest import ANALYST, FRONT_OFFICE, INACTIVE, SERVICE, caller


def test_policy_lookup_returns_current_version_with_citation(svc):
    r = svc.policy_lookup(caller(ANALYST), query="gift limit per recipient")
    assert isinstance(r, PolicyLookupResult)
    hit = r.sections[0]
    assert (hit.policy_id, hit.version) == ("POL-GE", "2.1")
    assert "v2.1" in hit.citation and "2025-01-15" in hit.citation
    assert all(s.version != "2.0" for s in r.sections), "superseded versions must not surface"
    drafts = svc.policy_lookup(caller(ANALYST), query="draft text under review").sections
    assert not any(s.policy_id == "POL-MK" and s.version == "1.5" for s in drafts), "unapproved drafts must not surface"


def test_policy_get_as_of_returns_the_version_in_force(svc):
    assert svc.policy_get(caller(ANALYST), policy_id="POL-GE", as_of="2024-06-01").policy.version == "2.0"
    assert svc.policy_get(caller(ANALYST), policy_id="POL-GE", as_of="2025-06-01").policy.version == "2.1"
    assert svc.policy_get(caller(ANALYST), policy_id="POL-GE", as_of="2020-01-01").policy is None


def test_reads_are_open_to_active_users_only(svc):
    assert svc.policy_list(caller(FRONT_OFFICE)).ok
    for who in ("nobody@example-am.com", INACTIVE, ""):
        r = svc.policy_list(caller(who))
        assert isinstance(r, ToolError) and r.error == "access_denied"


def test_draft_create_requires_analyst_group(svc):
    denied = svc.draft_create(caller(FRONT_OFFICE), kind=DraftKind.POLICY_MAPPING, title="t", body="b")
    assert isinstance(denied, ToolError) and denied.error == "access_denied"
    ok = svc.draft_create(caller(ANALYST), kind=DraftKind.POLICY_MAPPING, title="Map FINRA 26-19", body="body", related_ids=("FINRA-RN-26-19",))
    assert ok.ok and ok.status == "pending"
    assert svc.draft_list(caller(FRONT_OFFICE)).drafts[0].draft_id == ok.draft_id
    assert svc.draft_create(caller(SERVICE), kind=DraftKind.POLICY_MAPPING, title="cron", body="b").ok, "service account may file drafts"


def test_invalid_dates_are_rejected_before_any_work(svc):
    r = svc.control_test_results(caller(ANALYST), control_id="CTL-GE-01", start="2026-02-30")
    assert isinstance(r, ToolError) and r.error == "invalid_input" and "real date" in r.detail
    r = svc.control_test_results(caller(ANALYST), control_id="CTL-GE-01", start="2026-06-01", end="2026-01-01")
    assert isinstance(r, ToolError) and "after end" in r.detail


def test_clock_override_is_gated(svc, settings, audit, directory):
    from dataclasses import replace

    from compliance_mcp.drafts import DraftStore
    from compliance_mcp.service import ComplianceService

    locked = ComplianceService(replace(settings, allow_clock_override=False), audit=audit, directory=directory, drafts=DraftStore(settings.drafts_db))
    r = locked.attestations_due(caller(ANALYST), within_days=30, today="2026-09-15")
    assert isinstance(r, ToolError) and r.error == "invalid_input"
    r = svc.attestations_due(caller(ANALYST), within_days=30, today="2026-09-15")
    assert [a.attestation_id for a in r.attestations] == ["TRN-2026-AML-014", "ATT-2026-Q3-001"]


def test_evidence_bundle_reports_gaps_and_is_hashed(svc):
    m = svc.evidence_bundle(caller(ANALYST), control_id="CTL-GE-01", start="2026-01-01", end="2026-06-30").manifest
    assert len(m.test_results) == 6
    assert {v.version for v in m.policy_versions} == {"2.0", "2.1"}
    assert any("T-2026-027" in g for g in m.gaps)
    assert m.change_tickets[0].ticket_id == "CHG-2026-0412"
    assert len(m.manifest_sha256) == 64
    short = svc.evidence_bundle(caller(ANALYST), control_id="CTL-GE-01", start="2026-07-01", end="2026-08-31").manifest
    assert any("expected at least 2 monthly" in g for g in short.gaps)
    quarterly = svc.evidence_bundle(caller(ANALYST), control_id="CTL-BX-01", start="2026-01-01", end="2026-06-30").manifest
    assert not any("expected at least" in g for g in quarterly.gaps), "two quarterly tests in six months is enough"
    missing = svc.evidence_bundle(caller(ANALYST), control_id="CTL-NOPE", start="2026-01-01", end="2026-02-01")
    assert isinstance(missing, ToolError) and missing.error == "not_found"


def test_regulatory_feed(svc):
    rel = svc.regulatory_releases(caller(ANALYST), since="2026-08-01")
    assert [r.release_id for r in rel.releases] == ["SEC-2026-0812-MKTG", "FINRA-RN-26-19", "FCA-PS26-9"]
    assert svc.regulatory_releases(caller(ANALYST), since="2026-08-01", source="FCA").releases[0].release_id == "FCA-PS26-9"


def test_every_call_is_audited_with_session_and_directory_version(svc, settings, directory):
    svc.policy_lookup(caller(ANALYST, "sess-A"), query="best execution")
    svc.draft_create(caller(FRONT_OFFICE, "sess-B"), kind=DraftKind.POLICY_MAPPING, title="t", body="b")
    svc.evidence_bundle(caller(ANALYST, "sess-C"), control_id="CTL-NOPE", start="2026-01-01", end="2026-02-01")
    recs = [json.loads(line) for line in settings.audit_log.read_text().splitlines()]
    assert [r["outcome"] for r in recs] == ["ok", "denied", "error"]
    assert [r["session_id"] for r in recs] == ["sess-A", "sess-B", "sess-C"]
    assert all(r["directory_version"] == directory.version for r in recs)
    assert recs[1]["prev_hash"] == recs[0]["hash"] and all(r["mac"] for r in recs)
    assert verify(settings.audit_log, hmac_key=settings.audit_hmac_key).ok


def test_draft_body_is_hashed_not_stored_in_audit(svc, settings):
    svc.draft_create(caller(ANALYST), kind=DraftKind.CONTROL_FINDING_NOTE, title="note", body="confidential body text")
    rec = json.loads(settings.audit_log.read_text().splitlines()[-1])
    assert "confidential" not in json.dumps(rec) and "body_sha256" in rec["args"]


def test_internal_errors_are_not_leaked_to_the_model(svc, monkeypatch):
    monkeypatch.setattr(svc._policies, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("/secret/path exploded")))
    r = svc.policy_lookup(caller(ANALYST), query="anything")
    assert isinstance(r, ToolError) and r.error == "internal_error" and "/secret" not in r.detail
