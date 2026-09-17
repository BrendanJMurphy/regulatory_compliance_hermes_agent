"""Draft content checks, rate limiting, feed fetcher, evidence export, retention purge."""

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from compliance_mcp import admin_cli, review_cli
from compliance_mcp.feed_fetcher import FeedRefused, fetch_xml, merge_into_cache, parse_feed
from compliance_mcp.models import DraftKind, ToolError
from compliance_mcp.ratelimit import RateLimited, TokenBucketLimiter
from tests.conftest import ANALYST, APPROVER, caller

FIXTURES = Path(__file__).parent / "fixtures"

VERBATIM = "raise the annual gift limit from $100 to $250 per recipient per year"
MAPPING_BODY = f'''# Regulatory mapping draft: FINRA-RN-26-19

## Obligations extracted

| # | Type | Quote (verbatim) | Applies to | Effective / compliance date |
|---|------|------------------|------------|-----------------------------|
| 1 | requirement | "{VERBATIM}" | member firms | 2027-01-01 |
| 2 | record-keeping | "Member firms must maintain a separate record of all gifts subject to the rule" | member firms | not stated |
'''


# ---- draft checks -----------------------------------------------------------------------------


def test_policy_mapping_with_verbatim_quotes_is_accepted(svc):
    r = svc.draft_create(caller(ANALYST), kind=DraftKind.POLICY_MAPPING, title="FINRA 26-19", body=MAPPING_BODY, related_ids=("FINRA-RN-26-19", "POL-GE"))
    assert r.ok, r


def test_policy_mapping_with_paraphrased_quote_is_rejected(svc, settings):
    body = MAPPING_BODY.replace(VERBATIM, "raises the gift limit to two hundred and fifty dollars")
    r = svc.draft_create(caller(ANALYST), kind=DraftKind.POLICY_MAPPING, title="FINRA 26-19", body=body, related_ids=("FINRA-RN-26-19",))
    assert isinstance(r, ToolError) and r.error == "draft_rejected"
    assert "1 quote(s) are not verbatim" in r.detail and "two hundred" in r.detail
    last = json.loads(settings.audit_log.read_text().splitlines()[-1])
    assert last["outcome"] == "error" and last["result_summary"].startswith("draft_rejected")


def test_policy_mapping_needs_a_known_release_and_a_quotes_table(svc):
    r = svc.draft_create(caller(ANALYST), kind=DraftKind.POLICY_MAPPING, title="t", body=MAPPING_BODY, related_ids=("POL-GE",))
    assert isinstance(r, ToolError) and "known release id" in r.detail
    r = svc.draft_create(caller(ANALYST), kind=DraftKind.POLICY_MAPPING, title="t", body="no table here", related_ids=("FINRA-RN-26-19",))
    assert isinstance(r, ToolError) and "no obligations table" in r.detail


def test_evidence_index_must_cite_the_current_manifest_hash(svc):
    manifest = svc.evidence_bundle(caller(ANALYST), control_id="CTL-GE-01", start="2026-01-01", end="2026-06-30").manifest
    title = "Evidence index CTL-GE-01 2026-01-01..2026-06-30"
    good = svc.draft_create(
        caller(ANALYST),
        kind=DraftKind.EVIDENCE_PACK_INDEX,
        title=title,
        body=f"Manifest SHA-256: {manifest.manifest_sha256}\n\n## Gaps\n- ...",
        related_ids=("CTL-GE-01",),
    )
    assert good.ok, good
    stale = svc.draft_create(caller(ANALYST), kind=DraftKind.EVIDENCE_PACK_INDEX, title=title, body="Manifest SHA-256: " + "0" * 64, related_ids=())
    assert isinstance(stale, ToolError) and "does not match" in stale.detail
    wrong_period = svc.draft_create(
        caller(ANALYST),
        kind=DraftKind.EVIDENCE_PACK_INDEX,
        title="Evidence index CTL-GE-01 2026-01-01..2026-03-31",
        body=manifest.manifest_sha256,
        related_ids=(),
    )
    assert isinstance(wrong_period, ToolError) and "does not match" in wrong_period.detail
    bad_title = svc.draft_create(caller(ANALYST), kind=DraftKind.EVIDENCE_PACK_INDEX, title="my index", body=manifest.manifest_sha256, related_ids=())
    assert isinstance(bad_title, ToolError) and "title must be" in bad_title.detail


# ---- rate limiting ---------------------------------------------------------------------------------


def test_token_bucket_cuts_off_a_burst_then_recovers():
    now = [0.0]
    limiter = TokenBucketLimiter(per_minute=60, burst=5, clock=lambda: now[0])
    for _ in range(5):
        limiter.check("u")
    with pytest.raises(RateLimited):
        limiter.check("u")
    limiter.check("someone-else")  # buckets are per requester
    now[0] += 2.0  # two seconds refill two tokens at 60/min
    limiter.check("u")
    limiter.check("u")
    with pytest.raises(RateLimited):
        limiter.check("u")


def test_service_returns_rate_limited_error(settings, audit, directory):
    from dataclasses import replace

    from compliance_mcp.drafts import DraftStore
    from compliance_mcp.service import ComplianceService

    tight = ComplianceService(replace(settings, rate_limit_per_minute=3), audit=audit, directory=directory, drafts=DraftStore(settings.drafts_db))
    results = [tight.policy_list(caller(ANALYST)) for _ in range(4)]
    assert [r.ok for r in results[:3]] == [True, True, True]
    assert isinstance(results[3], ToolError) and results[3].error == "rate_limited"


# ---- feed fetcher ------------------------------------------------------------------------------------


def test_rss_and_atom_parse_to_plain_text_releases():
    finra = parse_feed((FIXTURES / "finra.xml").read_text(), "FINRA")
    assert len(finra) == 1, "empty items are skipped"
    r = finra[0]
    assert r.release_id.startswith("FINRA-20260915-") and r.published == "2026-09-15"
    assert "<" not in r.text and "business communications conducted on unapproved channels" in r.text
    assert r.title.startswith("Regulatory Notice 26-21: Supervision of & Recordkeeping")
    fca = parse_feed((FIXTURES / "fca.atom").read_text(), "FCA")
    assert fca[0].url.endswith("ps26-11") and fca[0].published == "2026-09-10" and "1 April 2027" in fca[0].text


def test_merge_never_overwrites_a_known_release(tmp_path):
    cache = tmp_path / "finra.json"
    releases = parse_feed((FIXTURES / "finra.xml").read_text(), "FINRA")
    assert merge_into_cache(cache, "FINRA", releases) == (1, 0)
    assert merge_into_cache(cache, "FINRA", releases) == (0, 1)
    edited = releases[0].model_copy(update={"text": "silently edited"})
    merge_into_cache(cache, "FINRA", [edited])
    stored = json.loads(cache.read_text())["releases"]
    assert len(stored) == 1 and stored[0]["text"] != "silently edited"


def test_fetch_refuses_hosts_off_the_allowlist():
    with pytest.raises(FeedRefused):
        fetch_xml("https://evil.example.com/feed.xml")


# ---- evidence export -----------------------------------------------------------------------------------


def test_export_builds_a_verifiable_pack_only_for_approved_indexes(svc, settings, tmp_path, capsys):
    manifest = svc.evidence_bundle(caller(ANALYST), control_id="CTL-GE-01", start="2026-01-01", end="2026-06-30").manifest
    title = "Evidence index CTL-GE-01 2026-01-01..2026-06-30"
    draft_id = svc.draft_create(
        caller(ANALYST), kind=DraftKind.EVIDENCE_PACK_INDEX, title=title, body=f"hash {manifest.manifest_sha256}", related_ids=()
    ).draft_id

    assert review_cli.main(["export", draft_id, "--out", str(tmp_path)], settings) == 2, "pending index must not export"
    assert "only approved" in capsys.readouterr().err
    assert review_cli.main(["approve", draft_id, "--as", APPROVER], settings) == 0
    assert review_cli.main(["export", draft_id, "--out", str(tmp_path)], settings) == 0

    with zipfile.ZipFile(tmp_path / f"{draft_id}.zip") as zf:
        names = set(zf.namelist())
        assert {"COVER.json", "index.md", "manifest.json", "audit-excerpt.jsonl", "SHA256SUMS", "policies/POL-GE-v2.1.md", "policies/POL-GE-v2.0.md"} <= names
        sums = dict(line.split("  ", 1)[::-1] for line in zf.read("SHA256SUMS").decode().splitlines())
        import hashlib

        for name, digest in sums.items():
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest, name
        cover = json.loads(zf.read("COVER.json"))
        assert cover["approved_by"] == APPROVER and cover["manifest_sha256"] == manifest.manifest_sha256
        assert any(draft_id in line for line in zf.read("audit-excerpt.jsonl").decode().splitlines())


# ---- retention purge -------------------------------------------------------------------------------------


def test_purge_is_a_dry_run_by_default_and_never_touches_pending_or_active(svc, settings, capsys):
    old = svc.draft_create(caller(ANALYST), kind=DraftKind.CONTROL_FINDING_NOTE, title="old", body="b").draft_id
    keep = svc.draft_create(caller(ANALYST), kind=DraftKind.CONTROL_FINDING_NOTE, title="pending", body="b").draft_id
    review_cli.main(["reject", old, "--as", APPROVER], settings)
    with sqlite3.connect(settings.drafts_db) as conn:  # age the decision far past retention
        conn.execute("UPDATE drafts SET decision_at = '2010-01-01T00:00:00Z' WHERE draft_id = ?", (old,))

    assert admin_cli.main(["purge", "--older-than-days", "30"], settings) == 0
    assert "would purge 1 decided draft(s)" in capsys.readouterr().out
    assert svc.draft_get(caller(ANALYST), draft_id=old).draft is not None

    assert admin_cli.main(["purge", "--older-than-days", "30", "--apply"], settings) == 0
    assert svc.draft_get(caller(ANALYST), draft_id=old).draft is None
    assert svc.draft_get(caller(ANALYST), draft_id=keep).draft.status == "pending"
    records = [json.loads(line) for line in settings.audit_log.read_text().splitlines()]
    purge = [r for r in records if r["tool"] == "retention_purge"]
    assert len(purge) == 1 and purge[0]["outcome"] == "ok" and purge[0]["args"]["older_than_days"] == 30
