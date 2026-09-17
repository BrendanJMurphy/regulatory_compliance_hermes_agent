"""Tamper-evident audit log.

Every tool call, every approval decision, and every identity failure becomes one record.
The log is designed so that a reviewer can answer "who did what, when, and was the log
itself changed afterwards" without trusting the host it ran on.

How integrity works
-------------------
* **Hash chain.** Each record stores ``prev_hash`` (the SHA-256 of the previous record) and
  its own ``hash``. Editing, inserting or deleting a record breaks every link after it.
* **MAC.** With ``hmac_key`` set, each record also carries an HMAC-SHA256 over its hash.
  The key lives only in the server process (from a secrets manager). Someone who can rewrite
  the file cannot recompute MACs, so a rewritten chain fails verification.
* **Anchoring.** Every ``anchor_every`` records the current head hash is forwarded to the
  external sink. The archive can then prove no tail was cut off the local file.
* **Rotation.** When the active file exceeds ``rotate_bytes`` it is renamed to
  ``<stem>.<utc timestamp>.jsonl`` and a fresh file starts with ``prev_hash`` equal to the
  old head, so the chain runs unbroken across files. ``verify`` walks all files in order.

Concurrency: the server and the review CLI share one chain. Appends take an exclusive
``flock`` on the active file and read the previous hash from disk while holding it.

Forwarding: records are spooled to disk as individual files and sent by a background
thread with exponential backoff. A slow or unavailable sink never blocks or loses a record.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logging_setup import get_logger

log = get_logger(__name__)

GENESIS = "0" * 64
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _utc_now() -> str:
    return time.strftime(_TS_FORMAT, time.gmtime())


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(record_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(record_without_hash)).hexdigest()


def _mac(key: str, record_hash: str) -> str:
    return hmac.new(key.encode("utf-8"), record_hash.encode("ascii"), hashlib.sha256).hexdigest()


def redact(args: dict[str, Any]) -> dict[str, Any]:
    """Replace values of secret-looking keys. Applied before an argument dict is persisted."""
    return {k: ("[redacted]" if any(s in k.lower() for s in ("token", "secret", "password", "api_key")) else v) for k, v in args.items()}


@dataclass(frozen=True)
class AuditRecord:
    id: str
    ts: str
    agent_id: str
    requester: str
    session_id: str
    directory_version: str
    tool: str
    args: dict[str, Any]
    outcome: str  # ok | denied | error
    result_summary: str
    prev_hash: str
    hash: str
    mac: str = ""


# --------------------------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------------------------


class AuditLog:
    def __init__(
        self,
        path: Path,
        agent_id: str,
        *,
        hmac_key: str = "",
        rotate_bytes: int = 50_000_000,
        forwarder: Forwarder | None = None,
        anchor_every: int = 100,
    ) -> None:
        self.path = path
        self.agent_id = agent_id
        self._hmac_key = hmac_key
        self._rotate_bytes = rotate_bytes
        self._forwarder = forwarder
        self._anchor_every = max(1, anchor_every)
        self._thread_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    # ---- chain head ---------------------------------------------------------------------

    @staticmethod
    def _tail_record(fh) -> dict[str, Any] | None:
        """Last complete record of an open binary file, read backwards in chunks."""
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        if size == 0:
            return None
        buf = b""
        pos = size
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            if buf.count(b"\n") >= 2:
                break
        lines = [line for line in buf.split(b"\n") if line.strip()]
        return json.loads(lines[-1]) if lines else None

    def head(self) -> str:
        with self.path.open("rb") as fh:
            rec = self._tail_record(fh)
        return rec["hash"] if rec else GENESIS

    # ---- append -------------------------------------------------------------------------

    def write(
        self,
        *,
        requester: str,
        tool: str,
        args: dict[str, Any],
        outcome: str,
        result_summary: str,
        session_id: str = "",
        directory_version: str = "",
    ) -> AuditRecord:
        """Append one record. Returns it, including the hash that now heads the chain."""
        with self._thread_lock:
            with self.path.open("a+b") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    tail = self._tail_record(fh)
                    prev_hash = tail["hash"] if tail else GENESIS
                    seq = (tail.get("seq", 0) if tail else 0) + 1
                    body: dict[str, Any] = {
                        "id": str(uuid.uuid4()),
                        "seq": seq,
                        "ts": _utc_now(),
                        "agent_id": self.agent_id,
                        "requester": requester,
                        "session_id": session_id,
                        "directory_version": directory_version,
                        "tool": tool,
                        "args": redact(args),
                        "outcome": outcome,
                        "result_summary": result_summary[:2000],
                        "prev_hash": prev_hash,
                    }
                    body["hash"] = _digest(body)
                    if self._hmac_key:
                        body["mac"] = _mac(self._hmac_key, body["hash"])
                    fh.seek(0, os.SEEK_END)
                    fh.write((json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
                    fh.flush()
                    os.fsync(fh.fileno())
                    size = fh.tell()
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            if size >= self._rotate_bytes:
                self._rotate()
        if self._forwarder:
            self._forwarder.enqueue(body)
            if seq % self._anchor_every == 0:
                self._forwarder.enqueue({"type": "anchor", "ts": body["ts"], "agent_id": self.agent_id, "seq": seq, "head": body["hash"]})
        return AuditRecord(**{k: body.get(k, "") for k in AuditRecord.__dataclass_fields__})

    def _rotate(self) -> None:
        """Rename the active file; the next append starts a new file chained to the old head.

        The new file's first record carries ``prev_hash`` = old head because ``write`` reads
        the tail of whatever file is active, and a fresh file has no tail. To keep that link
        explicit we write a marker record first.
        """
        head = self.head()
        # Nanosecond timestamp: unique even if two rotations land in the same second, and it
        # still sorts chronologically, which ``chain_files`` relies on.
        stamp = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.{time.time_ns() % 1_000_000_000:09d}Z"
        rotated = self.path.with_name(f"{self.path.stem}.{stamp}{self.path.suffix}")
        os.replace(self.path, rotated)
        self.path.touch()
        marker: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "seq": 0,
            "ts": _utc_now(),
            "agent_id": self.agent_id,
            "requester": "",
            "session_id": "",
            "directory_version": "",
            "tool": "audit_rotate",
            "args": {"continues": rotated.name},
            "outcome": "ok",
            "result_summary": f"chain continues from {rotated.name}",
            "prev_hash": head,
        }
        marker["hash"] = _digest(marker)
        if self._hmac_key:
            marker["mac"] = _mac(self._hmac_key, marker["hash"])
        self.path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
        log.info("audit log rotated", extra={"rotated_to": rotated.name, "head": head})


# --------------------------------------------------------------------------------------------
# Forwarder (spool + background sender)
# --------------------------------------------------------------------------------------------


class Forwarder:
    """Durable, non-blocking delivery of audit records to an HTTPS sink.

    ``enqueue`` writes the record to ``spool_dir`` and returns immediately. A daemon thread
    sends spooled files oldest-first and deletes each on a 2xx. Failures back off
    exponentially (1s .. 60s) and never drop a record; the spool is the retry queue.
    """

    def __init__(self, spool_dir: Path, url: str, token: str = "", *, timeout: float = 5.0) -> None:
        self.spool_dir = spool_dir
        self.url = url
        self.token = token
        self.timeout = timeout
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="audit-forwarder", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout)

    def enqueue(self, record: dict[str, Any]) -> None:
        # Name sorts chronologically: nanosecond clock plus a uuid to break ties.
        name = f"{time.time_ns():020d}-{uuid.uuid4().hex}.json"
        tmp = self.spool_dir / f".{name}.tmp"
        tmp.write_bytes(_canonical(record))
        os.replace(tmp, self.spool_dir / name)  # atomic publish
        self._wake.set()

    def pending(self) -> int:
        return sum(1 for p in self.spool_dir.glob("*.json"))

    def flush_once(self) -> int:
        """Send everything spooled, synchronously. Returns records delivered. Used by tests and shutdown."""
        sent = 0
        for path in sorted(self.spool_dir.glob("*.json")):
            if not self._send(path):
                break
            sent += 1
        return sent

    def _send(self, path: Path) -> bool:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            resp = httpx.post(self.url, content=path.read_bytes(), headers=headers, timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                path.unlink(missing_ok=True)
                return True
            log.warning("audit sink rejected record", extra={"status": resp.status_code, "file": path.name})
        except httpx.HTTPError as exc:
            log.warning("audit sink unreachable", extra={"error": str(exc), "file": path.name})
        return False

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._wake.wait(timeout=backoff)
            self._wake.clear()
            if self._stop.is_set():
                break
            files = sorted(self.spool_dir.glob("*.json"))
            if not files:
                backoff = 1.0
                continue
            if self._send(files[0]):
                backoff = 1.0
                self._wake.set()  # keep draining
            else:
                backoff = min(backoff * 2, 60.0)


# --------------------------------------------------------------------------------------------
# Verifier
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    records: int
    files: int
    head: str
    message: str


def chain_files(active: Path) -> list[Path]:
    """All files of one chain, oldest first: rotated files by timestamp, then the active file."""
    rotated = sorted(active.parent.glob(f"{active.stem}.*{active.suffix}"))
    return [p for p in rotated if p != active] + ([active] if active.exists() else [])


def verify(active: Path, *, hmac_key: str = "") -> VerifyResult:
    """Walk every file of the chain and check each link, hash, and (if keyed) MAC."""
    files = chain_files(active)
    prev = GENESIS
    count = 0
    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                rec = json.loads(line)
                where = f"{path.name}:{lineno}"
                if rec.get("prev_hash") != prev:
                    return VerifyResult(False, count, len(files), prev, f"{where}: chain broken (prev_hash mismatch)")
                body = {k: v for k, v in rec.items() if k not in ("hash", "mac")}
                if _digest(body) != rec.get("hash"):
                    return VerifyResult(False, count, len(files), prev, f"{where}: record hash mismatch (record altered)")
                if hmac_key:
                    if not rec.get("mac"):
                        return VerifyResult(False, count, len(files), prev, f"{where}: record has no MAC but a key is configured")
                    if not hmac.compare_digest(rec["mac"], _mac(hmac_key, rec["hash"])):
                        return VerifyResult(False, count, len(files), prev, f"{where}: MAC mismatch (record forged)")
                prev = rec["hash"]
                count += 1
    return VerifyResult(True, count, len(files), prev, f"{count} records across {len(files)} file(s) verified, head {prev[:12]}")


# --------------------------------------------------------------------------------------------
# CLI: compliance-audit verify | tail [n] | spool
# --------------------------------------------------------------------------------------------


def main() -> None:
    import argparse

    from .settings import SETTINGS

    parser = argparse.ArgumentParser(prog="compliance-audit", description="Inspect and verify the audit chain.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="check every link, hash and MAC across all chain files")
    tail = sub.add_parser("tail", help="print the most recent records")
    tail.add_argument("n", nargs="?", type=int, default=20)
    sub.add_parser("spool", help="show how many records are waiting for the external sink")
    args = parser.parse_args()

    if args.cmd == "verify":
        result = verify(SETTINGS.audit_log, hmac_key=SETTINGS.audit_hmac_key)
        print(("OK " if result.ok else "FAIL ") + result.message)
        raise SystemExit(0 if result.ok else 1)
    if args.cmd == "spool":
        print(f"{sum(1 for _ in SETTINGS.audit_spool_dir.glob('*.json')) if SETTINGS.audit_spool_dir.exists() else 0} record(s) pending")
        return
    lines = SETTINGS.audit_log.read_text(encoding="utf-8").splitlines() if SETTINGS.audit_log.exists() else []
    for line in lines[-args.n :]:
        rec = json.loads(line)
        print(f"{rec['ts']} {rec['outcome']:6} {rec['requester']:<28} {rec['tool']:<24} {rec['result_summary'][:80]}")


if __name__ == "__main__":
    main()
