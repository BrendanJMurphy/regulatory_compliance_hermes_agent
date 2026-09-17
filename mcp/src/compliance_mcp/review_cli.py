"""Human review of agent drafts. Deliberately not an MCP tool.

    compliance-review list [pending|approved|rejected]
    compliance-review show <draft_id>
    compliance-review approve <draft_id> --id-token <jwt> [--note "..."]
    compliance-review reject  <draft_id> --id-token <jwt> [--note "..."]
    compliance-review export  <draft_id> --out <dir>      # approved evidence indexes only

Who is approving is established by ``COMPLIANCE_REVIEW_IDENTITY_MODE``:

* ``oidc`` (production): ``--id-token`` is verified against the firm's identity provider
  and the username claim becomes the approver. ``--as`` is refused.
* ``dev``: ``--as <upn>`` is trusted as typed. For synthetic data only.

Rules enforced regardless of mode: the approver must be a person in the approver group,
must not be the draft's requester (four-eyes), and the draft must still be pending.
Every decision, and every refused attempt, is written to the same audit chain as the
agent's tool calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .audit import AuditLog
from .directory import AccessDenied, Directory
from .drafts import DraftConflict, DraftStore
from .evidence_export import ExportRefused, audit_lines_for, build_pack, period_from_title
from .logging_setup import configure_logging
from .models import DraftStatus
from .oidc import OidcConfig, OidcVerifier, TokenInvalid
from .settings import SETTINGS, ReviewIdentityMode, Settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compliance-review", description="Approve or reject drafts queued by the compliance agent.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_cmd = sub.add_parser("list", help="list drafts by status")
    list_cmd.add_argument("status", nargs="?", default="pending", choices=[s.value for s in DraftStatus])

    show_cmd = sub.add_parser("show", help="print one draft as JSON")
    show_cmd.add_argument("draft_id")

    export_cmd = sub.add_parser("export", help="write an approved evidence index as a zip evidence pack")
    export_cmd.add_argument("draft_id")
    export_cmd.add_argument("--out", required=True, help="directory to write <draft_id>.zip into")

    for name, help_text in (("approve", "approve a pending draft"), ("reject", "reject a pending draft")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("draft_id")
        identity = cmd.add_mutually_exclusive_group(required=True)
        identity.add_argument("--id-token", help="OIDC ID token proving who you are (production)")
        identity.add_argument("--as", dest="as_upn", help="approver UPN, trusted as typed (dev mode only)")
        cmd.add_argument("--note", default="", help="free-text reason recorded with the decision")
    return parser


def _approver_identity(args: argparse.Namespace, settings: Settings) -> str:
    """Return the approver's UPN according to the configured identity mode, or raise ``AccessDenied``."""
    if settings.review_identity_mode is ReviewIdentityMode.OIDC:
        if not args.id_token:
            raise AccessDenied("this environment requires --id-token; --as is not accepted")
        verifier = OidcVerifier(OidcConfig(settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url, settings.oidc_username_claim))
        try:
            return verifier.username(args.id_token)
        except TokenInvalid as exc:
            raise AccessDenied(str(exc)) from exc
    if not args.as_upn:
        raise AccessDenied("dev mode expects --as <upn>")
    return args.as_upn


def main(argv: list[str] | None = None, settings: Settings = SETTINGS) -> int:
    configure_logging(json_output=settings.log_json)
    args = _build_parser().parse_args(argv)
    store = DraftStore(settings.drafts_db)

    if args.cmd == "list":
        for d in store.list(DraftStatus(args.status)):
            print(f"{d.draft_id}  {d.kind:<22} {d.created}  by {d.requester:<30} {d.title}")
        return 0
    if args.cmd == "show":
        draft = store.get(args.draft_id)
        if draft is None:
            print(f"no draft {args.draft_id}", file=sys.stderr)
            return 1
        print(draft.model_dump_json(indent=2))
        return 0

    directory = Directory(settings.data_dir / "users.json", ttl_seconds=settings.directory_ttl_seconds)
    audit = AuditLog(settings.audit_log, "human-review-cli", hmac_key=settings.audit_hmac_key, rotate_bytes=settings.audit_rotate_bytes)
    if args.cmd == "export":
        return _export(args, settings, store, audit, directory)

    decision = DraftStatus.APPROVED if args.cmd == "approve" else DraftStatus.REJECTED
    presented = args.as_upn or "<id-token>"
    try:
        upn = _approver_identity(args, settings)
        approver = directory.require_approver(upn)
        draft = store.get(args.draft_id)
        if draft is None:
            raise DraftConflict(f"no draft {args.draft_id}")
        if draft.requester.lower() == approver.upn.lower():
            raise AccessDenied("four-eyes: a draft cannot be approved by its requester")
        draft = store.decide(args.draft_id, decision=decision, by=approver.upn, note=args.note)
        audit.write(
            requester=approver.upn,
            tool=f"draft_{decision}",
            outcome="ok",
            result_summary=f"{args.draft_id} {decision}",
            args={"draft_id": args.draft_id, "content_sha256": draft.content_sha256, "note": args.note, "os_user": os.environ.get("USER", "")},
            directory_version=directory.version,
        )
        print(f"{args.draft_id} {decision} by {approver.upn}")
        return 0
    except (AccessDenied, DraftConflict) as exc:
        audit.write(
            requester=presented,
            tool=f"draft_{decision}",
            outcome="denied",
            result_summary=str(exc),
            args={"draft_id": args.draft_id, "os_user": os.environ.get("USER", "")},
            directory_version=directory.version,
        )
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _export(args: argparse.Namespace, settings: Settings, store: DraftStore, audit: AuditLog, directory: Directory) -> int:
    """Build the evidence pack zip for an approved index. Refusals are audited like decisions."""
    from .server import build_service  # local import: the service wires the systems of record

    exporter = os.environ.get("USER", "operator")
    try:
        draft = store.get(args.draft_id)
        if draft is None:
            raise ExportRefused(f"no draft {args.draft_id}")
        period = period_from_title(draft.title)
        if period is None:
            raise ExportRefused("draft title does not identify a control and period")
        manifest = build_service(settings).compute_manifest(*period)
        if manifest is None:
            raise ExportRefused(f"unknown control {period[0]}")
        pack = build_pack(draft, manifest, data_dir=settings.data_dir, audit_lines=audit_lines_for(args.draft_id, settings.audit_log), exporter=exporter)
        out = Path(args.out) / f"{args.draft_id}.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pack)
        audit.write(
            requester=exporter,
            tool="evidence_export",
            outcome="ok",
            result_summary=f"{args.draft_id} exported ({len(pack)} bytes)",
            args={"draft_id": args.draft_id, "path": str(out), "manifest_sha256": manifest.manifest_sha256},
            directory_version=directory.version,
        )
        print(f"wrote {out}")
        return 0
    except ExportRefused as exc:
        audit.write(
            requester=exporter,
            tool="evidence_export",
            outcome="denied",
            result_summary=str(exc),
            args={"draft_id": args.draft_id},
            directory_version=directory.version,
        )
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
