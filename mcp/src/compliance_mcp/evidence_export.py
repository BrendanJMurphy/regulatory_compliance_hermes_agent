"""Build a self-contained evidence pack from an approved evidence index draft.

An examiner receives a zip, not a chat transcript. The pack contains the approved index,
the evidence manifest as JSON, every policy document version it references, the audit
records that produced and approved it, and a checksum file over everything. Each file's
SHA-256 is listed in ``SHA256SUMS`` so the recipient can verify nothing was altered in transit.

Only drafts of kind ``evidence_pack_index`` in status ``approved`` can be exported; the
export is refused otherwise, so an unapproved index can never leave the system.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .draft_checks import _INDEX_TITLE
from .models import Draft, DraftKind, DraftStatus, EvidenceManifest


class ExportRefused(ValueError):
    """The draft is not an approved evidence index."""


def build_pack(
    draft: Draft,
    manifest: EvidenceManifest,
    *,
    data_dir: Path,
    audit_lines: list[str],
    exporter: str,
) -> bytes:
    """Return the zip bytes for an approved evidence index draft."""
    if draft.kind is not DraftKind.EVIDENCE_PACK_INDEX:
        raise ExportRefused(f"draft {draft.draft_id} is a {draft.kind}, not an evidence index")
    if draft.status is not DraftStatus.APPROVED or draft.decision is None:
        raise ExportRefused(f"draft {draft.draft_id} is {draft.status}; only approved indexes can be exported")

    files: dict[str, bytes] = {
        "index.md": draft.body.encode("utf-8"),
        "manifest.json": manifest.model_dump_json(indent=2).encode("utf-8"),
        "audit-excerpt.jsonl": ("\n".join(audit_lines) + "\n").encode("utf-8"),
    }
    for ref in manifest.policy_versions:
        source = data_dir / ref.source
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != ref.sha256:
            raise ExportRefused(f"policy document {ref.source} no longer matches the hash recorded in the manifest")
        files[f"policies/{Path(ref.source).name}"] = content

    cover = {
        "draft_id": draft.draft_id,
        "title": draft.title,
        "control_id": manifest.control.control_id,
        "period": {"start": manifest.period_start, "end": manifest.period_end},
        "manifest_sha256": manifest.manifest_sha256,
        "requested_by": draft.requester,
        "approved_by": draft.decision.by,
        "approved_at": draft.decision.at,
        "approval_note": draft.decision.note,
        "exported_by": exporter,
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    files["COVER.json"] = (json.dumps(cover, indent=2) + "\n").encode("utf-8")
    files["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {name}\n" for name, b in sorted(files.items())).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in sorted(files.items()):
            zf.writestr(name, content)
    return buffer.getvalue()


def period_from_title(title: str) -> tuple[str, str, str] | None:
    """(control_id, start, end) parsed from an evidence index title, or None."""
    m = _INDEX_TITLE.search(title)
    return (m["control"], m["start"], m["end"]) if m else None


def audit_lines_for(draft_id: str, audit_file: Path) -> list[str]:
    """Every audit record that mentions the draft id, verbatim, oldest first."""
    if not audit_file.exists():
        return []
    pattern = re.compile(re.escape(draft_id))
    return [line for line in audit_file.read_text(encoding="utf-8").splitlines() if pattern.search(line)]
