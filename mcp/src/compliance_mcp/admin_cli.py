"""Operational maintenance: retention purge.

    compliance-admin purge --older-than-days 2555 [--apply]

Deletes decided drafts and rotated audit files older than the retention period. The default
(2555 days, seven years) matches a typical books-and-records schedule; pass the firm's own
value. Without ``--apply`` the command only reports what it would delete.

The active audit file is never touched: rotation produces the archival files, and only whole
rotated files past retention are removed so the chain stays verifiable up to the purge point.
Every purge is itself written to the audit chain.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta

from .audit import AuditLog, chain_files
from .logging_setup import configure_logging
from .settings import SETTINGS, Settings


def main(argv: list[str] | None = None, settings: Settings = SETTINGS) -> int:
    configure_logging(json_output=settings.log_json)
    parser = argparse.ArgumentParser(prog="compliance-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    purge = sub.add_parser("purge", help="delete decided drafts and rotated audit files past retention")
    purge.add_argument("--older-than-days", type=int, default=2555)
    purge.add_argument("--apply", action="store_true", help="actually delete; default is a dry run")
    args = parser.parse_args(argv)

    cutoff = datetime.now(UTC) - timedelta(days=args.older_than_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(settings.drafts_db) as conn:
        drafts = conn.execute("SELECT COUNT(*) FROM drafts WHERE status != 'pending' AND decision_at < ?", (cutoff_iso,)).fetchone()[0]
        if args.apply:
            conn.execute("DELETE FROM drafts WHERE status != 'pending' AND decision_at < ?", (cutoff_iso,))

    rotated = [p for p in chain_files(settings.audit_log)[:-1] if datetime.fromtimestamp(p.stat().st_mtime, UTC) < cutoff]
    if args.apply:
        for path in rotated:
            path.unlink()
        AuditLog(settings.audit_log, "compliance-admin", hmac_key=settings.audit_hmac_key).write(
            requester="operator",
            tool="retention_purge",
            outcome="ok",
            result_summary=f"purged {drafts} draft(s) and {len(rotated)} rotated audit file(s) older than {args.older_than_days} days",
            args={"older_than_days": args.older_than_days, "cutoff": cutoff_iso, "files": [p.name for p in rotated]},
        )
    mode = "purged" if args.apply else "would purge"
    print(f"{mode} {drafts} decided draft(s) and {len(rotated)} rotated audit file(s) older than {args.older_than_days} days (cutoff {cutoff_iso})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
