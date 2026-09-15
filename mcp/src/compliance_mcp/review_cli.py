"""Human review of agent drafts. This is deliberately not an MCP tool.

    compliance-review list [pending|approved|rejected]
    compliance-review show <draft_id>
    compliance-review approve <draft_id> --as <upn> [--note "..."]
    compliance-review reject  <draft_id> --as <upn> [--note "..."]

Approvals require the approver to be in the `compliance-approvers` group and to differ
from the draft's requester (four-eyes). Every decision is written to the same audit chain
as the agent's tool calls.
"""

from __future__ import annotations

import argparse
import json
import sys

from .access import AccessDenied, Directory
from .audit import AuditLog
from .drafts import DraftQueue
from .settings import SETTINGS

APPROVER_GROUP = "compliance-approvers"


def main() -> None:
    p = argparse.ArgumentParser(prog="compliance-review")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("status", nargs="?", default="pending")
    s = sub.add_parser("show"); s.add_argument("draft_id")
    for name in ("approve", "reject"):
        s = sub.add_parser(name); s.add_argument("draft_id"); s.add_argument("--as", dest="who", required=True); s.add_argument("--note", default="")
    a = p.parse_args()

    q = DraftQueue(SETTINGS.state_dir / "drafts")
    if a.cmd == "list":
        for d in q.list(a.status):
            print(f"{d['draft_id']}  {d['kind']:<22} {d['created']}  by {d['requester']:<28} {d['title']}")
        return
    if a.cmd == "show":
        d = q.get(a.draft_id)
        if not d:
            sys.exit(f"no draft {a.draft_id}")
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return

    directory = Directory(SETTINGS.data_dir / "users.json")
    audit = AuditLog(SETTINGS.audit_log, "human-review-cli", SETTINGS.audit_forward_url, SETTINGS.audit_forward_token)
    decision = "approved" if a.cmd == "approve" else "rejected"
    try:
        user = directory.require_group(a.who, APPROVER_GROUP)
        d = q.get(a.draft_id)
        if not d:
            raise FileNotFoundError(f"no draft {a.draft_id}")
        if d["requester"].lower() == user["upn"].lower():
            raise AccessDenied("four-eyes: a draft cannot be approved by its requester")
        d = q.decide(a.draft_id, decision=decision, by=user["upn"], note=a.note)
        audit.write(requester=user["upn"], tool=f"draft_{decision}", args={"draft_id": a.draft_id, "content_sha256": d["content_sha256"], "note": a.note}, outcome="ok", result_summary=f"{a.draft_id} {decision}")
        print(f"{a.draft_id} {decision} by {user['upn']}")
    except (AccessDenied, FileNotFoundError) as exc:
        audit.write(requester=a.who, tool=f"draft_{decision}", args={"draft_id": a.draft_id}, outcome="denied", result_summary=str(exc))
        sys.exit(f"refused: {exc}")


if __name__ == "__main__":
    main()
