"""Tool implementations, independent of the MCP transport so they can be unit tested directly.

Every public method takes `requester` first, resolves it against the directory, performs
the operation, and writes exactly one audit record (ok / denied / error). Nothing here
mutates a system of record; the only write path is the draft queue.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .access import AccessDenied, Directory
from .audit import AuditLog
from .drafts import DraftQueue
from .settings import Settings
from .store import Attestations, ControlLibrary, PolicyRepository, RegulatoryFeed, TicketSystem

WRITE_GROUP = "compliance-analysts"


class ComplianceService:
    def __init__(self, settings: Settings) -> None:
        d = settings.data_dir
        self.settings = settings
        self.directory = Directory(d / "users.json")
        self.policies = PolicyRepository(d / "policies")
        self.controls = ControlLibrary(d / "controls.json")
        self.tickets = TicketSystem(d / "tickets.json")
        self.feed = RegulatoryFeed(d / "regulatory_feed")
        self.attestations = Attestations(d / "attestations.json")
        self.drafts = DraftQueue(settings.state_dir / "drafts")
        self.audit = AuditLog(settings.audit_log, settings.agent_id, settings.audit_forward_url, settings.audit_forward_token)

    # ---- plumbing -------------------------------------------------------

    def _guarded(self, requester: str, tool: str, args: dict[str, Any], fn: Callable[[dict], Any], *, group: str | None = None) -> dict:
        try:
            user = self.directory.require_group(requester, group) if group else self.directory.resolve(requester)
            result = fn(user)
            summary = result.get("summary") if isinstance(result, dict) else str(result)
            self.audit.write(requester=user["upn"], tool=tool, args=args, outcome="ok", result_summary=summary or "")
            return {"ok": True, **result}
        except AccessDenied as exc:
            self.audit.write(requester=requester, tool=tool, args=args, outcome="denied", result_summary=str(exc))
            return {"ok": False, "error": "access_denied", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface to the agent, keep the audit trail complete
            self.audit.write(requester=requester, tool=tool, args=args, outcome="error", result_summary=f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}

    # ---- policies -------------------------------------------------------

    def policy_lookup(self, requester: str, query: str, limit: int = 5) -> dict:
        def run(_user: dict) -> dict:
            hits = self.policies.search(query, limit=limit)
            return {
                "summary": f"{len(hits)} section(s) for '{query}'",
                "sections": [
                    {"policy_id": h.policy_id, "version": h.version, "effective_date": h.effective_date, "title": h.title, "heading": h.heading, "text": h.text, "citation": h.cite()}
                    for h in hits
                ],
                "instruction": "Answer only from these sections and cite each one. If nothing here answers the question, say so and name the policy owner.",
            }

        return self._guarded(requester, "policy_lookup", {"query": query, "limit": limit}, run)

    def policy_get(self, requester: str, policy_id: str, as_of: str | None = None) -> dict:
        def run(_user: dict) -> dict:
            doc = self.policies.version_as_of(policy_id, as_of) if as_of else next((d for d in self.policies.current() if d["policy_id"] == policy_id), None)
            if doc is None:
                return {"summary": f"no approved version of {policy_id}" + (f" as of {as_of}" if as_of else ""), "policy": None}
            return {"summary": f"{policy_id} v{doc['version']}", "policy": {k: v for k, v in doc.items() if k != "sections"}}

        return self._guarded(requester, "policy_get", {"policy_id": policy_id, "as_of": as_of}, run)

    def policy_list(self, requester: str) -> dict:
        def run(_user: dict) -> dict:
            items = [{k: d[k] for k in ("policy_id", "version", "effective_date", "title", "owner", "regulations", "controls")} for d in self.policies.current()]
            return {"summary": f"{len(items)} current policies", "policies": items}

        return self._guarded(requester, "policy_list", {}, run)

    # ---- controls ---------------------------------------------------------

    def control_lookup(self, requester: str, control_id: str = "", query: str = "") -> dict:
        def run(_user: dict) -> dict:
            if control_id:
                c = self.controls.get(control_id)
                return {"summary": f"control {control_id} {'found' if c else 'not found'}", "controls": [c] if c else []}
            hits = self.controls.search(query)
            return {"summary": f"{len(hits)} control(s) for '{query}'", "controls": hits}

        return self._guarded(requester, "control_lookup", {"control_id": control_id, "query": query}, run)

    def control_test_results(self, requester: str, control_id: str, start: str | None = None, end: str | None = None) -> dict:
        def run(_user: dict) -> dict:
            rows = self.controls.results(control_id, start, end)
            return {"summary": f"{len(rows)} test result(s) for {control_id} {start or ''}..{end or ''}", "results": rows}

        return self._guarded(requester, "control_test_results", {"control_id": control_id, "start": start, "end": end}, run)

    # ---- regulatory feed -------------------------------------------------

    def regulatory_releases(self, requester: str, since: str, source: str = "") -> dict:
        def run(_user: dict) -> dict:
            rows = self.feed.since(since, source)
            return {"summary": f"{len(rows)} release(s) since {since}", "releases": [{k: r[k] for k in ("release_id", "source", "published", "title", "url")} for r in rows]}

        return self._guarded(requester, "regulatory_releases", {"since": since, "source": source}, run)

    def regulatory_release_get(self, requester: str, release_id: str) -> dict:
        def run(_user: dict) -> dict:
            r = self.feed.get(release_id)
            return {"summary": f"release {release_id} {'found' if r else 'not found'}", "release": r}

        return self._guarded(requester, "regulatory_release_get", {"release_id": release_id}, run)

    # ---- tickets ------------------------------------------------------------

    def ticket_search(self, requester: str, query: str = "", control_id: str = "", start: str | None = None, end: str | None = None) -> dict:
        def run(_user: dict) -> dict:
            rows = self.tickets.search(query, control_id, start, end)
            return {"summary": f"{len(rows)} ticket(s)", "tickets": rows}

        return self._guarded(requester, "ticket_search", {"query": query, "control_id": control_id, "start": start, "end": end}, run)

    # ---- attestations ---------------------------------------------------------

    def attestations_due(self, requester: str, within_days: int = 14, today: str | None = None) -> dict:
        def run(_user: dict) -> dict:
            t = date.fromisoformat(today) if today else date.today()
            rows = self.attestations.due(within_days, t)
            return {"summary": f"{len(rows)} attestation(s) due within {within_days} days", "attestations": rows}

        return self._guarded(requester, "attestations_due", {"within_days": within_days, "today": today}, run)

    # ---- evidence -------------------------------------------------------------

    def evidence_bundle(self, requester: str, control_id: str, start: str, end: str) -> dict:
        """Assemble the evidence manifest for one control over a period. Read only; the index is drafted separately."""

        def run(_user: dict) -> dict:
            control = self.controls.get(control_id)
            if control is None:
                raise ValueError(f"unknown control {control_id}")
            policy_versions = []
            for pid in control.get("policies", []):
                for v in self.policies.versions(pid):
                    if v["status"] == "approved" and v["effective_date"] <= end:
                        policy_versions.append({k: v[k] for k in ("policy_id", "version", "effective_date", "title", "source", "sha256")})
            results = self.controls.results(control_id, start, end)
            tickets = self.tickets.search("", control_id, start, end)
            manifest = {
                "control": control,
                "period": {"start": start, "end": end},
                "policy_versions": policy_versions,
                "test_results": results,
                "change_tickets": tickets,
                "gaps": _gaps(control, results, start, end),
            }
            manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            return {"summary": f"evidence for {control_id} {start}..{end}: {len(policy_versions)} policy versions, {len(results)} tests, {len(tickets)} tickets, {len(manifest['gaps'])} gap(s)", "manifest": manifest}

        return self._guarded(requester, "evidence_bundle", {"control_id": control_id, "start": start, "end": end}, run)

    # ---- drafts (the only write path) ------------------------------------------

    def draft_create(self, requester: str, kind: str, title: str, body: str, related_ids: list[str] | None = None) -> dict:
        def run(user: dict) -> dict:
            d = self.drafts.create(kind=kind, title=title, body=body, requester=user["upn"], related_ids=related_ids or [])
            return {"summary": f"draft {d['draft_id']} ({kind}) queued for human review", "draft_id": d["draft_id"], "status": "pending"}

        return self._guarded(requester, "draft_create", {"kind": kind, "title": title, "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "related_ids": related_ids or []}, run, group=WRITE_GROUP)

    def draft_list(self, requester: str, status: str = "pending") -> dict:
        def run(_user: dict) -> dict:
            rows = [{k: d[k] for k in ("draft_id", "kind", "title", "requester", "created", "status", "decision")} for d in self.drafts.list(status)]
            return {"summary": f"{len(rows)} {status} draft(s)", "drafts": rows}

        return self._guarded(requester, "draft_list", {"status": status}, run)

    def draft_get(self, requester: str, draft_id: str) -> dict:
        def run(_user: dict) -> dict:
            d = self.drafts.get(draft_id)
            return {"summary": f"draft {draft_id} {'found' if d else 'not found'}", "draft": d}

        return self._guarded(requester, "draft_get", {"draft_id": draft_id}, run)


def _gaps(control: dict, results: list[dict], start: str, end: str) -> list[str]:
    gaps: list[str] = []
    freq = control.get("test_frequency", "")
    expected = {"monthly": 1, "quarterly": 1 / 3, "annual": 1 / 12}.get(freq)
    if expected:
        months = max(1, (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7]) + 1)
        need = int(months * expected + 0.999)
        if len(results) < need:
            gaps.append(f"expected at least {need} {freq} test(s) in period, found {len(results)}")
    for r in results:
        if r.get("result") != "pass":
            gaps.append(f"test {r['test_id']} on {r['tested_on']} result={r.get('result')}: {r.get('notes', '')}")
    return gaps
