"""Typed contracts for everything that crosses a boundary.

Three families live here:

* **Records** (``Policy``, ``Control``, ...): the shape of data from the systems of record.
  Adapters in ``store.py`` must produce these; fixture drift fails fast at load time.
* **Tool results** (``PolicyLookupResult``, ...): what each MCP tool returns. Because the
  tools are annotated with these types, the MCP server publishes a JSON schema for every
  result, so the model knows the field names without guessing.
* **Envelopes** (``ToolError``, ``CallerIdentity``): cross-cutting shapes.

All models are immutable (``frozen=True``) and reject unknown fields, so a typo in a fixture
or an adapter is an error rather than silently ignored data.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------------------------
# Shared scalar types
# --------------------------------------------------------------------------------------------

#: Calendar date as ``YYYY-MM-DD``. The pattern makes the MCP schema reject malformed input
#: before it reaches Python; the validator below then guarantees it is a real date.
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Calendar date, YYYY-MM-DD", examples=["2026-06-30"])]


def parse_iso_date(value: str) -> date:
    """Parse a validated ``IsoDate`` string. Raises ``ValueError`` for impossible dates."""
    return date.fromisoformat(value)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------------------------


class IdentitySource(StrEnum):
    HEADER = "header"  # Set by an authenticating gateway; trusted.
    PARAMETER = "parameter"  # Supplied by the model; dev only.


class CallerIdentity(_Frozen):
    """Who asked, and how we know.

    ``requester`` is the directory identity (UPN or object id) as presented. It is resolved
    against the directory by the service; this object does not imply the user is allowed.
    ``session_id`` correlates the call with the conversation in the gateway's own logs.
    """

    requester: str
    source: IdentitySource
    session_id: str = ""


class User(_Frozen):
    id: str
    upn: str
    name: str
    groups: tuple[str, ...] = ()
    active: bool = True
    # ``person`` accounts belong to a human. ``service`` accounts run unattended jobs and are
    # never eligible to approve anything.
    kind: Literal["person", "service"] = "person"


# --------------------------------------------------------------------------------------------
# Systems of record
# --------------------------------------------------------------------------------------------


class PolicyStatus(StrEnum):
    APPROVED = "approved"
    DRAFT = "draft"
    RETIRED = "retired"


class PolicySection(_Frozen):
    heading: str
    text: str


class Policy(_Frozen):
    """One approved (or draft) version of one policy document."""

    policy_id: str
    version: str
    effective_date: IsoDate
    status: PolicyStatus
    title: str
    owner: str = ""
    regulations: tuple[str, ...] = ()
    controls: tuple[str, ...] = ()
    source: str
    sha256: str
    sections: tuple[PolicySection, ...] = ()

    @field_validator("effective_date")
    @classmethod
    def _real_date(cls, v: str) -> str:
        parse_iso_date(v)
        return v


class PolicyHit(_Frozen):
    """A section returned by search, with a ready-to-quote citation."""

    policy_id: str
    version: str
    effective_date: IsoDate
    title: str
    heading: str
    text: str
    citation: str


class PolicySummary(_Frozen):
    policy_id: str
    version: str
    effective_date: IsoDate
    title: str
    owner: str
    regulations: tuple[str, ...]
    controls: tuple[str, ...]


class Control(_Frozen):
    control_id: str
    name: str
    description: str
    owner: str
    test_frequency: Literal["monthly", "quarterly", "annual", ""] = ""
    policies: tuple[str, ...] = ()
    regulations: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


class TestResult(_Frozen):
    test_id: str
    control_id: str
    tested_on: IsoDate
    tester: str
    result: Literal["pass", "fail", "partial", "not-tested"]
    notes: str = ""


class Ticket(_Frozen):
    ticket_id: str
    created: IsoDate
    status: str
    type: Literal["change", "incident", "task"]
    title: str
    summary: str = ""
    controls: tuple[str, ...] = ()
    policies: tuple[str, ...] = ()


class Release(_Frozen):
    release_id: str
    source: str
    published: IsoDate
    title: str
    url: str
    text: str


class ReleaseSummary(_Frozen):
    release_id: str
    source: str
    published: IsoDate
    title: str
    url: str


class Attestation(_Frozen):
    attestation_id: str
    type: str
    owner: str
    manager: str
    due: IsoDate
    status: Literal["open", "complete", "overdue"]


class AttestationDue(Attestation):
    days_remaining: int


# --------------------------------------------------------------------------------------------
# Drafts (the only write path)
# --------------------------------------------------------------------------------------------


class DraftKind(StrEnum):
    POLICY_MAPPING = "policy_mapping"
    EVIDENCE_PACK_INDEX = "evidence_pack_index"
    CONTROL_FINDING_NOTE = "control_finding_note"
    ATTESTATION_ESCALATION = "attestation_escalation"


class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Decision(_Frozen):
    by: str
    note: str
    at: str  # ISO-8601 UTC timestamp


class Draft(_Frozen):
    draft_id: str
    kind: DraftKind
    title: str
    body: str
    requester: str
    session_id: str = ""
    related_ids: tuple[str, ...] = ()
    created: str  # ISO-8601 UTC timestamp
    status: DraftStatus
    content_sha256: str
    decision: Decision | None = None


class DraftSummary(_Frozen):
    draft_id: str
    kind: DraftKind
    title: str
    requester: str
    created: str
    status: DraftStatus
    decision: Decision | None = None


# --------------------------------------------------------------------------------------------
# Tool results
# --------------------------------------------------------------------------------------------


class ToolError(_Frozen):
    """Returned instead of a result when a call is refused or fails.

    ``error`` is a short stable code the model can branch on:
      access_denied   caller unknown, inactive, or lacking the group
      rate_limited    caller exceeded the per-minute budget; wait and retry
      invalid_input   an argument failed validation; fix it and retry
      draft_rejected  draft content broke a rule (e.g. non-verbatim quote); fix content and retry
      not_found       a referenced record does not exist
      internal_error  the server failed; the error is logged
    ``detail`` is safe to show and never contains paths, stack traces, or other internals.
    """

    ok: Literal[False] = False
    error: Literal["access_denied", "rate_limited", "invalid_input", "draft_rejected", "not_found", "internal_error"]
    detail: str


class ToolResult(_Frozen):
    """Base of every successful tool result. ``summary`` is one line and is written to the audit record."""

    ok: Literal[True] = True
    #: One line describing the outcome; also written to the audit record.
    summary: str


class PolicyLookupResult(ToolResult):
    sections: tuple[PolicyHit, ...]
    instruction: str = "Answer only from these sections and cite each one. If nothing here answers the question, say so and name the policy owner."


class PolicyGetResult(ToolResult):
    policy: Policy | None


class PolicyListResult(ToolResult):
    policies: tuple[PolicySummary, ...]


class ControlLookupResult(ToolResult):
    controls: tuple[Control, ...]


class ControlTestResultsResult(ToolResult):
    results: tuple[TestResult, ...]


class RegulatoryReleasesResult(ToolResult):
    releases: tuple[ReleaseSummary, ...]


class RegulatoryReleaseGetResult(ToolResult):
    release: Release | None


class TicketSearchResult(ToolResult):
    tickets: tuple[Ticket, ...]


class AttestationsDueResult(ToolResult):
    attestations: tuple[AttestationDue, ...]


class PolicyVersionRef(_Frozen):
    policy_id: str
    version: str
    effective_date: IsoDate
    title: str
    source: str
    sha256: str


class EvidenceManifest(_Frozen):
    control: Control
    period_start: IsoDate
    period_end: IsoDate
    policy_versions: tuple[PolicyVersionRef, ...]
    test_results: tuple[TestResult, ...]
    change_tickets: tuple[Ticket, ...]
    #: Human-readable findings the approver must see. Never filtered or softened.
    gaps: tuple[str, ...]
    #: SHA-256 over the canonical JSON of every field above; quoted in the evidence index.
    manifest_sha256: str


class EvidenceBundleResult(ToolResult):
    manifest: EvidenceManifest


class DraftCreateResult(ToolResult):
    draft_id: str
    status: DraftStatus


class DraftListResult(ToolResult):
    drafts: tuple[DraftSummary, ...]


class DraftGetResult(ToolResult):
    draft: Draft | None
