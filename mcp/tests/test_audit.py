"""Audit chain: tamper detection, MACs, multi-process safety, rotation, spooled forwarding."""

import json
import threading

import httpx

from compliance_mcp.audit import AuditLog, Forwarder, chain_files, verify
from tests.conftest import HMAC_KEY


def _write_n(log: AuditLog, n: int) -> None:
    for i in range(n):
        log.write(requester="x", tool="t", args={"i": i}, outcome="ok", result_summary=str(i))


def test_edit_in_the_middle_breaks_the_chain(settings, audit):
    _write_n(audit, 3)
    lines = [json.loads(line) for line in settings.audit_log.read_text().splitlines()]
    lines[1]["requester"] = "someone.else"
    settings.audit_log.write_text("\n".join(json.dumps(line, sort_keys=True) for line in lines) + "\n")
    result = verify(settings.audit_log, hmac_key=HMAC_KEY)
    assert not result.ok and "altered" in result.message


def test_rewritten_chain_without_the_key_fails_mac_check(settings, audit):
    """An attacker with file access recomputes every hash; without the key the MACs no longer match."""
    _write_n(audit, 3)
    unkeyed = AuditLog(settings.audit_log.with_name("forged.jsonl"), "attacker")  # no hmac key
    for rec in (json.loads(line) for line in settings.audit_log.read_text().splitlines()):
        unkeyed.write(requester="forged", tool=rec["tool"], args=rec["args"], outcome=rec["outcome"], result_summary=rec["result_summary"])
    forged = verify(unkeyed.path, hmac_key=HMAC_KEY)
    assert not forged.ok and "no MAC" in forged.message
    assert verify(settings.audit_log, hmac_key=HMAC_KEY).ok


def test_concurrent_writers_from_threads_and_instances_share_one_chain(settings):
    a = AuditLog(settings.audit_log, "a", hmac_key=HMAC_KEY)
    b = AuditLog(settings.audit_log, "b", hmac_key=HMAC_KEY)
    threads = [threading.Thread(target=_write_n, args=(log, 25)) for log in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result = verify(settings.audit_log, hmac_key=HMAC_KEY)
    assert result.ok and result.records == 100


def test_rotation_keeps_the_chain_unbroken_across_files(settings):
    log = AuditLog(settings.audit_log, "a", hmac_key=HMAC_KEY, rotate_bytes=2000)
    _write_n(log, 30)
    files = chain_files(settings.audit_log)
    assert len(files) >= 3, "expected several rotated files"
    result = verify(settings.audit_log, hmac_key=HMAC_KEY)
    assert result.ok and result.files == len(files)
    # 30 real records plus one rotation marker per rotated file.
    assert result.records == 30 + (len(files) - 1)


def test_secrets_in_args_are_redacted(settings, audit):
    audit.write(requester="x", tool="t", args={"query": "q", "api_key": "sk-123", "token": "abc"}, outcome="ok", result_summary="")
    rec = json.loads(settings.audit_log.read_text().splitlines()[-1])
    assert rec["args"] == {"query": "q", "api_key": "[redacted]", "token": "[redacted]"}


class _Sink:
    """In-memory HTTPS sink that can be told to fail, to exercise spool-and-retry."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            return httpx.Response(503)
        self.received.append(json.loads(request.content))
        return httpx.Response(200)


def test_forwarder_spools_when_sink_is_down_and_anchors_periodically(settings, monkeypatch):
    sink = _Sink()
    transport = httpx.MockTransport(sink.handler)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw))
    fwd = Forwarder(settings.audit_spool_dir, "https://siem.example/ingest", "tok")
    log = AuditLog(settings.audit_log, "a", hmac_key=HMAC_KEY, forwarder=fwd, anchor_every=5)

    sink.fail = True
    _write_n(log, 5)
    assert fwd.pending() == 6, "5 records + 1 anchor are spooled, none lost"
    assert fwd.flush_once() == 0 and fwd.pending() == 6

    sink.fail = False
    assert fwd.flush_once() == 6 and fwd.pending() == 0
    anchors = [r for r in sink.received if r.get("type") == "anchor"]
    assert len(anchors) == 1 and anchors[0]["head"] == log.head()
    assert [r["seq"] for r in sink.received if "seq" in r and r.get("type") != "anchor"] == [1, 2, 3, 4, 5]
