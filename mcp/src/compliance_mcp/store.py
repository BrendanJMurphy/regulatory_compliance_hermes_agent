"""Read-only adapters over the governed systems of record.

Each class is the integration contract for one upstream system: the policy repository, the
GRC platform (controls and test results), ticketing, the regulator feed cache, and the
attestation tracker. The bodies here read JSON and Markdown fixtures so the agent can be
exercised end to end with no connection to real systems. Production replaces the bodies
with API clients and keeps the method signatures.

Every adapter returns the typed models from ``models.py``, so a fixture or an upstream
payload that drifts from the contract fails at load time, not in the middle of a call.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from .models import (
    Attestation,
    AttestationDue,
    Control,
    Policy,
    PolicyHit,
    PolicySection,
    PolicyStatus,
    Release,
    TestResult,
    Ticket,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _in_range(day: str, start: str | None, end: str | None) -> bool:
    """Inclusive range test on ISO dates. Works on strings because the format sorts lexically."""
    return (not start or day >= start) and (not end or day <= end)


# --------------------------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------------------------

_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


class PolicyRepository:
    """Policies are Markdown files with a front-matter block; one file per version.

    Front matter keys: policy_id, version, effective_date, status, title, owner,
    regulations (comma-separated), controls (comma-separated). Body sections start at ``## ``.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._docs: list[Policy] = [self._parse(p) for p in sorted(root.glob("*.md"))]

    def _parse(self, path: Path) -> Policy:
        text = path.read_text(encoding="utf-8")
        match = _FRONT_MATTER.match(text)
        if not match:
            raise ValueError(f"{path}: missing front matter")
        meta = {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in match.group(1).splitlines())}
        return Policy(
            policy_id=meta["policy_id"],
            version=meta["version"],
            effective_date=meta["effective_date"],
            status=PolicyStatus(meta.get("status", "approved")),
            title=meta["title"],
            owner=meta.get("owner", ""),
            regulations=tuple(s.strip() for s in meta.get("regulations", "").split(",") if s.strip()),
            controls=tuple(s.strip() for s in meta.get("controls", "").split(",") if s.strip()),
            source=str(path.relative_to(self._root.parent)),
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            sections=self._split_sections(match.group(2)),
        )

    @staticmethod
    def _split_sections(body: str) -> tuple[PolicySection, ...]:
        sections: list[PolicySection] = []
        heading = "Preamble"
        lines: list[str] = []

        def flush() -> None:
            if any(line.strip() for line in lines):
                sections.append(PolicySection(heading=heading, text="\n".join(lines).strip()))

        for line in body.splitlines():
            if line.startswith("## "):
                flush()
                heading, lines = line[3:].strip(), []
            else:
                lines.append(line)
        flush()
        return tuple(sections)

    def current(self) -> list[Policy]:
        """The latest approved version of each policy, sorted by id. Drafts never appear."""
        latest: dict[str, Policy] = {}
        for doc in self._docs:
            if doc.status is not PolicyStatus.APPROVED:
                continue
            if doc.policy_id not in latest or doc.effective_date > latest[doc.policy_id].effective_date:
                latest[doc.policy_id] = doc
        return sorted(latest.values(), key=lambda d: d.policy_id)

    def versions(self, policy_id: str) -> list[Policy]:
        return sorted((d for d in self._docs if d.policy_id == policy_id), key=lambda d: d.effective_date)

    def version_as_of(self, policy_id: str, as_of: str) -> Policy | None:
        """The approved version in force on ``as_of``: latest with effective_date <= as_of."""
        candidates = [d for d in self.versions(policy_id) if d.status is PolicyStatus.APPROVED and d.effective_date <= as_of]
        return candidates[-1] if candidates else None

    def search(self, query: str, limit: int = 5) -> list[PolicyHit]:
        """Rank current sections by term frequency.

        Deliberately simple: the production adapter delegates to the policy system's own
        search. This one exists so the fixture loop behaves like the real thing.
        """
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
        scored: list[tuple[int, PolicyHit]] = []
        for doc in self.current():
            for section in doc.sections:
                haystack = f"{section.heading} {section.text}".lower()
                score = sum(haystack.count(t) for t in terms)
                if score:
                    citation = f"{doc.policy_id} v{doc.version} (effective {doc.effective_date}), section '{section.heading}', source {doc.source}"
                    scored.append(
                        (
                            score,
                            PolicyHit(
                                policy_id=doc.policy_id,
                                version=doc.version,
                                effective_date=doc.effective_date,
                                title=doc.title,
                                heading=section.heading,
                                text=section.text,
                                citation=citation,
                            ),
                        )
                    )
        scored.sort(key=lambda pair: -pair[0])
        return [hit for _, hit in scored[:limit]]


# --------------------------------------------------------------------------------------------
# Controls and test results (GRC)
# --------------------------------------------------------------------------------------------


class ControlLibrary:
    def __init__(self, path: Path) -> None:
        data = _load_json(path)
        self._controls = {c.control_id: c for c in (Control.model_validate(raw) for raw in data["controls"])}
        self._tests = [TestResult.model_validate(raw) for raw in data["test_results"]]

    def get(self, control_id: str) -> Control | None:
        return self._controls.get(control_id)

    def search(self, query: str) -> list[Control]:
        needle = query.lower()
        return [c for c in self._controls.values() if needle in c.model_dump_json().lower()]

    def results(self, control_id: str, start: str | None, end: str | None) -> list[TestResult]:
        return [t for t in self._tests if t.control_id == control_id and _in_range(t.tested_on, start, end)]


# --------------------------------------------------------------------------------------------
# Tickets
# --------------------------------------------------------------------------------------------


class TicketSystem:
    def __init__(self, path: Path) -> None:
        self._tickets = [Ticket.model_validate(raw) for raw in _load_json(path)["tickets"]]

    def search(self, query: str = "", control_id: str = "", start: str | None = None, end: str | None = None) -> list[Ticket]:
        needle = query.lower()
        return [
            t
            for t in self._tickets
            if (not control_id or control_id in t.controls) and (not needle or needle in t.model_dump_json().lower()) and _in_range(t.created, start, end)
        ]


# --------------------------------------------------------------------------------------------
# Regulator feed cache
# --------------------------------------------------------------------------------------------


class RegulatoryFeed:
    """Releases pulled from official regulator feeds by a separate fetcher; one JSON file per source."""

    def __init__(self, root: Path) -> None:
        releases: list[Release] = []
        for path in sorted(root.glob("*.json")):
            releases.extend(Release.model_validate(raw) for raw in _load_json(path)["releases"])
        self._by_id = {r.release_id: r for r in releases}

    def since(self, since: str, source: str = "") -> list[Release]:
        return sorted((r for r in self._by_id.values() if r.published >= since and (not source or r.source == source)), key=lambda r: r.published)

    def get(self, release_id: str) -> Release | None:
        return self._by_id.get(release_id)


# --------------------------------------------------------------------------------------------
# Attestations
# --------------------------------------------------------------------------------------------


class AttestationTracker:
    def __init__(self, path: Path) -> None:
        self._items = [Attestation.model_validate(raw) for raw in _load_json(path)["attestations"]]

    def due(self, within_days: int, today: date) -> list[AttestationDue]:
        out = []
        for item in self._items:
            if item.status == "complete":
                continue
            days = (date.fromisoformat(item.due) - today).days
            if days <= within_days:
                out.append(AttestationDue(**item.model_dump(), days_remaining=days))
        return sorted(out, key=lambda a: a.due)
