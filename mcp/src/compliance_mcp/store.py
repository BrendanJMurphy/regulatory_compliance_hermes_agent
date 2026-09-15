"""Read-only adapters over the governed systems of record.

In production each class wraps an internal API (policy repository, GRC platform,
ticketing, regulator feed cache). Here they read JSON/Markdown fixtures from
`COMPLIANCE_DATA_DIR` so the agent can be exercised end to end without any
connection to real systems. The interfaces are the contract; swap the bodies.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _in_range(d: str, start: str | None, end: str | None) -> bool:
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


@dataclass
class PolicySection:
    policy_id: str
    version: str
    effective_date: str
    title: str
    heading: str
    text: str
    source: str

    def cite(self) -> str:
        return f"{self.policy_id} v{self.version} (effective {self.effective_date}), section '{self.heading}', source {self.source}"


class PolicyRepository:
    """Policies are Markdown files with a small front matter block. One file per approved version."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._docs = [self._parse(p) for p in sorted(root.glob("*.md"))]

    def _parse(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            raise ValueError(f"{path} missing front matter")
        meta = {}
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        body = m.group(2)
        sections: list[tuple[str, str]] = []
        current = ("Preamble", [])
        for line in body.splitlines():
            if line.startswith("## "):
                if current[1]:
                    sections.append((current[0], "\n".join(current[1]).strip()))
                current = (line[3:].strip(), [])
            else:
                current[1].append(line)
        if current[1]:
            sections.append((current[0], "\n".join(current[1]).strip()))
        return {
            "policy_id": meta["policy_id"],
            "version": meta["version"],
            "effective_date": meta["effective_date"],
            "status": meta.get("status", "approved"),
            "title": meta["title"],
            "owner": meta.get("owner", ""),
            "regulations": [r.strip() for r in meta.get("regulations", "").split(",") if r.strip()],
            "controls": [c.strip() for c in meta.get("controls", "").split(",") if c.strip()],
            "source": str(path.relative_to(self.root.parent)),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "sections": sections,
            "raw": text,
        }

    def current(self) -> list[dict]:
        """Latest approved version of each policy."""
        latest: dict[str, dict] = {}
        for d in self._docs:
            if d["status"] != "approved":
                continue
            cur = latest.get(d["policy_id"])
            if cur is None or d["effective_date"] > cur["effective_date"]:
                latest[d["policy_id"]] = d
        return sorted(latest.values(), key=lambda d: d["policy_id"])

    def versions(self, policy_id: str) -> list[dict]:
        return sorted((d for d in self._docs if d["policy_id"] == policy_id), key=lambda d: d["effective_date"])

    def version_as_of(self, policy_id: str, as_of: str) -> dict | None:
        cands = [d for d in self.versions(policy_id) if d["status"] == "approved" and d["effective_date"] <= as_of]
        return cands[-1] if cands else None

    def search(self, query: str, limit: int = 5) -> list[PolicySection]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
        scored: list[tuple[int, PolicySection]] = []
        for d in self.current():
            for heading, text in d["sections"]:
                hay = (heading + " " + text).lower()
                score = sum(hay.count(t) for t in terms)
                if score:
                    scored.append((score, PolicySection(d["policy_id"], d["version"], d["effective_date"], d["title"], heading, text, d["source"])))
        scored.sort(key=lambda s: -s[0])
        return [s for _, s in scored[:limit]]


class ControlLibrary:
    def __init__(self, path: Path) -> None:
        data = _load(path)
        self.controls: dict[str, dict] = {c["control_id"]: c for c in data["controls"]}
        self.tests: list[dict] = data["test_results"]

    def get(self, control_id: str) -> dict | None:
        return self.controls.get(control_id)

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [c for c in self.controls.values() if q in json.dumps(c).lower()]

    def results(self, control_id: str, start: str | None, end: str | None) -> list[dict]:
        return [t for t in self.tests if t["control_id"] == control_id and _in_range(t["tested_on"], start, end)]


class TicketSystem:
    def __init__(self, path: Path) -> None:
        self.tickets: list[dict] = _load(path)["tickets"]

    def search(self, query: str = "", control_id: str = "", start: str | None = None, end: str | None = None) -> list[dict]:
        q = query.lower()
        out = []
        for t in self.tickets:
            if control_id and control_id not in t.get("controls", []):
                continue
            if q and q not in json.dumps(t).lower():
                continue
            if not _in_range(t["created"], start, end):
                continue
            out.append(t)
        return out


class RegulatoryFeed:
    """Cached releases from official regulator feeds (SEC, FINRA, FCA). One JSON file per source."""

    def __init__(self, root: Path) -> None:
        self.releases: list[dict] = []
        for p in sorted(root.glob("*.json")):
            self.releases.extend(_load(p)["releases"])
        self.by_id = {r["release_id"]: r for r in self.releases}

    def since(self, since: str, source: str = "") -> list[dict]:
        return sorted(
            (r for r in self.releases if r["published"] >= since and (not source or r["source"] == source)),
            key=lambda r: r["published"],
        )

    def get(self, release_id: str) -> dict | None:
        return self.by_id.get(release_id)


class Attestations:
    def __init__(self, path: Path) -> None:
        self.items: list[dict] = _load(path)["attestations"]

    def due(self, within_days: int, today: date) -> list[dict]:
        out = []
        for a in self.items:
            if a["status"] == "complete":
                continue
            due = date.fromisoformat(a["due"])
            days = (due - today).days
            if days <= within_days:
                out.append({**a, "days_remaining": days})
        return sorted(out, key=lambda a: a["due"])
