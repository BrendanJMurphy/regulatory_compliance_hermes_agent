"""Review queue. The agent can only create drafts; humans approve or reject them via the CLI.

Drafts are JSON files under `COMPLIANCE_STATE_DIR/drafts/<status>/`. Moving a file
between status directories is the state transition, which keeps the audit story simple:
the approval record names the human, the draft id, and the draft's content hash.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

KINDS = {"policy_mapping", "evidence_pack_index", "control_finding_note", "attestation_escalation"}
STATUSES = ("pending", "approved", "rejected")


class DraftQueue:
    def __init__(self, root: Path) -> None:
        self.root = root
        for s in STATUSES:
            (root / s).mkdir(parents=True, exist_ok=True)

    def create(self, *, kind: str, title: str, body: str, requester: str, related_ids: list[str]) -> dict:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {sorted(KINDS)}")
        if not title.strip() or not body.strip():
            raise ValueError("title and body are required")
        draft = {
            "draft_id": f"D-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
            "kind": kind,
            "title": title.strip(),
            "body": body,
            "requester": requester,
            "related_ids": related_ids,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "pending",
            "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "decision": None,
        }
        self._write("pending", draft)
        return draft

    def list(self, status: str = "pending") -> list[dict]:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return sorted((json.loads(p.read_text(encoding="utf-8")) for p in (self.root / status).glob("*.json")), key=lambda d: d["created"])

    def get(self, draft_id: str) -> dict | None:
        for s in STATUSES:
            p = self.root / s / f"{draft_id}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        return None

    def decide(self, draft_id: str, *, decision: str, by: str, note: str = "") -> dict:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        src = self.root / "pending" / f"{draft_id}.json"
        if not src.exists():
            raise FileNotFoundError(f"no pending draft {draft_id}")
        draft = json.loads(src.read_text(encoding="utf-8"))
        draft["status"] = decision
        draft["decision"] = {"by": by, "note": note, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self._write(decision, draft)
        src.unlink()
        return draft

    def _write(self, status: str, draft: dict) -> None:
        (self.root / status / f"{draft['draft_id']}.json").write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
