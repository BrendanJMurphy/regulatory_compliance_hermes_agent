"""Append-only, hash-chained audit log.

Every tool invocation is written as one JSON line. Each record carries the SHA-256 of
the previous record, so any edit or deletion in the middle of the file breaks the chain
and is detected by `compliance-audit verify`. The file is opened in append mode only;
nothing in this package ever rewrites it.

The intended deployment copies this file (or streams each line) into the firm's
WORM archive under the books-and-records retention schedule. Forwarding is best
effort and never blocks or fails a tool call; the local file is the source of truth.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(record_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(record_without_hash)).hexdigest()


@dataclass
class AuditRecord:
    id: str
    ts: str
    agent_id: str
    requester: str
    tool: str
    args: dict[str, Any]
    outcome: str  # ok | denied | error
    result_summary: str
    prev_hash: str
    hash: str


class AuditLog:
    def __init__(self, path: Path, agent_id: str, forward_url: str = "", forward_token: str = "") -> None:
        self.path = path
        self.agent_id = agent_id
        self.forward_url = forward_url
        self.forward_token = forward_token
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    @staticmethod
    def _tail_hash(fh) -> str:
        """Hash of the last complete record in an open file, read from the end. GENESIS if empty."""
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        if size == 0:
            return GENESIS
        chunk = 4096
        buf = b""
        pos = size
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            if buf.count(b"\n") >= 2 or pos == 0:
                break
        lines = [l for l in buf.split(b"\n") if l.strip()]
        return json.loads(lines[-1])["hash"] if lines else GENESIS

    def head(self) -> str:
        with self.path.open("rb") as fh:
            return self._tail_hash(fh)

    def write(self, *, requester: str, tool: str, args: dict[str, Any], outcome: str, result_summary: str) -> AuditRecord:
        with self._lock:
            # Append mode plus an exclusive advisory lock: several processes (the MCP server,
            # the review CLI) share one chain, so the previous hash is always read from disk
            # while the lock is held, never from memory.
            with self.path.open("a+b") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    prev = self._tail_hash(fh)
                    body = {
                        "id": str(uuid.uuid4()),
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "agent_id": self.agent_id,
                        "requester": requester,
                        "tool": tool,
                        "args": _redact(args),
                        "outcome": outcome,
                        "result_summary": result_summary[:2000],
                        "prev_hash": prev,
                    }
                    body["hash"] = _digest(body)
                    fh.seek(0, os.SEEK_END)
                    fh.write((json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
                    fh.flush()
                    os.fsync(fh.fileno())
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        self._forward(body)
        return AuditRecord(**body)

    def _forward(self, body: dict[str, Any]) -> None:
        if not self.forward_url:
            return
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if self.forward_token:
                headers["Authorization"] = f"Bearer {self.forward_token}"
            httpx.post(self.forward_url, content=_canonical(body), headers=headers, timeout=3.0)
        except Exception as exc:  # noqa: BLE001 - forwarding must never break the tool call
            print(f"[audit] forward failed: {exc}", file=sys.stderr)


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Drop obviously secret-looking keys before persisting arguments."""
    out: dict[str, Any] = {}
    for k, v in args.items():
        if any(s in k.lower() for s in ("token", "secret", "password", "api_key")):
            out[k] = "[redacted]"
        else:
            out[k] = v
    return out


def verify(path: Path) -> tuple[bool, int, str]:
    """Walk the file and confirm every record's hash and chain link. Returns (ok, count, message)."""
    if not path.exists():
        return True, 0, "no audit log yet"
    prev = GENESIS
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            expected_prev = prev
            if rec.get("prev_hash") != expected_prev:
                return False, count, f"line {lineno}: chain broken (prev_hash mismatch)"
            body = {k: v for k, v in rec.items() if k != "hash"}
            if _digest(body) != rec.get("hash"):
                return False, count, f"line {lineno}: record hash mismatch (record altered)"
            prev = rec["hash"]
            count += 1
    return True, count, f"{count} records verified, head {prev[:12]}"


def main() -> None:
    from .settings import SETTINGS

    argv = sys.argv[1:]
    if not argv or argv[0] not in {"verify", "tail"}:
        print("usage: compliance-audit verify | tail [n]", file=sys.stderr)
        sys.exit(2)
    if argv[0] == "verify":
        ok, count, msg = verify(SETTINGS.audit_log)
        print(("OK " if ok else "FAIL ") + msg)
        sys.exit(0 if ok else 1)
    n = int(argv[1]) if len(argv) > 1 else 20
    lines = SETTINGS.audit_log.read_text(encoding="utf-8").splitlines() if SETTINGS.audit_log.exists() else []
    for line in lines[-n:]:
        rec = json.loads(line)
        print(f"{rec['ts']} {rec['outcome']:6} {rec['requester']:<28} {rec['tool']:<24} {rec['result_summary'][:80]}")


if __name__ == "__main__":
    main()
