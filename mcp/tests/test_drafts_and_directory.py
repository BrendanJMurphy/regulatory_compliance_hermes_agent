"""Draft store atomicity and directory freshness."""

import json
import threading
import time

import pytest

from compliance_mcp.directory import AccessDenied, Directory
from compliance_mcp.drafts import DraftConflict, DraftStore
from compliance_mcp.models import DraftKind, DraftStatus
from tests.conftest import ANALYST, APPROVER, BOTH, DATA, SERVICE


def test_draft_is_decided_exactly_once_under_a_race(settings):
    store = DraftStore(settings.drafts_db)
    draft = store.create(kind=DraftKind.CONTROL_FINDING_NOTE, title="t", body="b", requester=ANALYST, related_ids=())
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def approve(by: str) -> None:
        barrier.wait()
        try:
            store.decide(draft.draft_id, decision=DraftStatus.APPROVED, by=by)
            outcomes.append(f"ok:{by}")
        except DraftConflict:
            outcomes.append(f"conflict:{by}")

    threads = [threading.Thread(target=approve, args=(who,)) for who in (APPROVER, BOTH)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(o.split(":")[0] for o in outcomes) == ["conflict", "ok"]
    assert store.get(draft.draft_id).status == DraftStatus.APPROVED


def test_rejected_drafts_stay_as_a_record_and_cannot_be_reopened(settings):
    store = DraftStore(settings.drafts_db)
    d = store.create(kind=DraftKind.CONTROL_FINDING_NOTE, title="t", body="b", requester=ANALYST, related_ids=("CTL-GE-01",))
    store.decide(d.draft_id, decision=DraftStatus.REJECTED, by=APPROVER, note="not needed")
    assert store.list(DraftStatus.REJECTED)[0].decision.note == "not needed"
    with pytest.raises(DraftConflict):
        store.decide(d.draft_id, decision=DraftStatus.APPROVED, by=APPROVER)
    assert store.create(kind=DraftKind.CONTROL_FINDING_NOTE, title="x", body="y", requester=ANALYST, related_ids=()).related_ids == ()


def test_directory_reloads_when_the_file_changes(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text((DATA / "users.json").read_text())
    directory = Directory(users_file, ttl_seconds=0)
    v1 = directory.version
    assert directory.resolve(ANALYST).upn == ANALYST

    data = json.loads(users_file.read_text())
    next(u for u in data["users"] if u["upn"] == ANALYST)["active"] = False
    time.sleep(0.01)  # ensure a distinct mtime on coarse filesystems
    users_file.write_text(json.dumps(data))
    with pytest.raises(AccessDenied, match="inactive"):
        directory.resolve(ANALYST)
    assert directory.version != v1


def test_service_accounts_can_never_approve(directory):
    with pytest.raises(AccessDenied, match="not a member"):
        directory.require_approver(SERVICE)
    assert directory.require_approver(APPROVER).kind == "person"
