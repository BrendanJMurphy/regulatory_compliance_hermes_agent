"""Review queue: the only thing the agent can write.

Drafts live in a single SQLite table. SQLite gives us what a directory of JSON files could
not: atomic state transitions, a guarantee that a draft is approved at most once even when
two approvers race, and a queryable history. The database is small (drafts are text) and
lives on the state volume next to the audit log.

State machine: ``pending`` -> ``approved`` | ``rejected``. There is no path back to pending
and no delete; a rejected draft stays as the record of a decision.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import Decision, Draft, DraftKind, DraftStatus, DraftSummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id       TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    requester      TEXT NOT NULL,
    session_id     TEXT NOT NULL DEFAULT '',
    related_ids    TEXT NOT NULL,           -- JSON array
    created        TEXT NOT NULL,           -- ISO-8601 UTC
    status         TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    decision_by    TEXT,
    decision_note  TEXT,
    decision_at    TEXT
);
CREATE INDEX IF NOT EXISTS drafts_status_created ON drafts (status, created);
"""


class DraftConflict(RuntimeError):
    """The draft is not pending: it does not exist or was already decided."""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class DraftStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per operation keeps this safe across threads and
        # processes (the MCP server and the review CLI share the file). WAL mode lets
        # readers proceed while a writer holds the lock.
        conn = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            yield conn
        finally:
            conn.close()

    # ---- writes -------------------------------------------------------------------------

    def create(self, *, kind: DraftKind, title: str, body: str, requester: str, related_ids: tuple[str, ...], session_id: str = "") -> Draft:
        if not title.strip() or not body.strip():
            raise ValueError("title and body are required")
        draft = Draft(
            draft_id=f"D-{time.strftime('%Y%m%d', time.gmtime())}-{uuid.uuid4().hex[:8]}",
            kind=kind,
            title=title.strip(),
            body=body,
            requester=requester,
            session_id=session_id,
            related_ids=related_ids,
            created=_utc_now(),
            status=DraftStatus.PENDING,
            content_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO drafts (draft_id, kind, title, body, requester, session_id, related_ids, created, status, content_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft.draft_id,
                    draft.kind,
                    draft.title,
                    draft.body,
                    draft.requester,
                    draft.session_id,
                    json.dumps(list(draft.related_ids)),
                    draft.created,
                    draft.status,
                    draft.content_sha256,
                ),
            )
        return draft

    def decide(self, draft_id: str, *, decision: DraftStatus, by: str, note: str = "") -> Draft:
        """Move a pending draft to approved/rejected, exactly once.

        The UPDATE is conditioned on ``status = 'pending'``; if two reviewers race, the second
        sees ``rowcount == 0`` and gets ``DraftConflict`` instead of overwriting the first.
        """
        if decision not in (DraftStatus.APPROVED, DraftStatus.REJECTED):
            raise ValueError("decision must be approved or rejected")
        at = _utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE drafts SET status = ?, decision_by = ?, decision_note = ?, decision_at = ? WHERE draft_id = ? AND status = 'pending'",
                (decision, by, note, at, draft_id),
            )
            if cur.rowcount != 1:
                conn.execute("ROLLBACK")
                raise DraftConflict(f"draft {draft_id} is not pending (missing or already decided)")
            conn.execute("COMMIT")
        draft = self.get(draft_id)
        assert draft is not None  # just updated it
        return draft

    # ---- reads --------------------------------------------------------------------------

    def get(self, draft_id: str) -> Draft | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return self._to_draft(row) if row else None

    def list(self, status: DraftStatus = DraftStatus.PENDING) -> list[DraftSummary]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM drafts WHERE status = ? ORDER BY created", (status,)).fetchall()
        return [DraftSummary(**{k: getattr(d, k) for k in DraftSummary.model_fields}) for d in map(self._to_draft, rows)]

    @staticmethod
    def _to_draft(row: sqlite3.Row) -> Draft:
        decision = Decision(by=row["decision_by"], note=row["decision_note"] or "", at=row["decision_at"]) if row["decision_by"] else None
        return Draft(
            draft_id=row["draft_id"],
            kind=DraftKind(row["kind"]),
            title=row["title"],
            body=row["body"],
            requester=row["requester"],
            session_id=row["session_id"],
            related_ids=tuple(json.loads(row["related_ids"])),
            created=row["created"],
            status=DraftStatus(row["status"]),
            content_sha256=row["content_sha256"],
            decision=decision,
        )
