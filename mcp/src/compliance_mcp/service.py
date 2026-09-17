"""Tool implementations, independent of the MCP transport so they are unit-testable.

Every public method is decorated with ``@audited``, which does the same four things for
each call: resolve and authorise the caller, run the body, write exactly one audit record
(``ok`` / ``denied`` / ``error``), and translate failures into a ``ToolError`` the model can
act on. The bodies therefore contain only domain logic.

Nothing here mutates a system of record. The single write path is ``draft_create``.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
from collections.abc import Callable
from datetime import date
from typing import TypeVar

from pydantic import ValidationError

from .audit import AuditLog
from .directory import ANALYST_GROUP, AccessDenied, Directory
from .draft_checks import DraftRejected, check_draft
from .drafts import DraftStore
from .logging_setup import get_logger
from .models import (
    AttestationsDueResult,
    CallerIdentity,
    ControlLookupResult,
    ControlTestResultsResult,
    DraftCreateResult,
    DraftGetResult,
    DraftKind,
    DraftListResult,
    DraftStatus,
    EvidenceBundleResult,
    EvidenceManifest,
    IsoDate,
    PolicyGetResult,
    PolicyListResult,
    PolicyLookupResult,
    PolicySummary,
    PolicyVersionRef,
    RegulatoryReleaseGetResult,
    RegulatoryReleasesResult,
    ReleaseSummary,
    TicketSearchResult,
    ToolError,
    ToolResult,
    User,
    parse_iso_date,
)
from .ratelimit import RateLimited, TokenBucketLimiter
from .settings import Settings
from .store import AttestationTracker, ControlLibrary, PolicyRepository, RegulatoryFeed, TicketSystem

log = get_logger(__name__)

R = TypeVar("R", bound=ToolResult)


class InvalidInput(ValueError):
    """A caller-supplied argument is unusable. The message is safe to return to the model."""


class NotFound(LookupError):
    """A referenced record does not exist. The message is safe to return to the model."""


def audited(tool: str, *, group: str | None = None, audit_args: Callable[..., dict] | None = None):
    """Wrap a service method with authorisation, audit, and error translation.

    ``group``      required group membership for the call (``None`` = any active user).
    ``audit_args`` optional function mapping the call's keyword arguments to what should be
                   persisted in the audit record; used to log a hash instead of a draft body.

    The wrapped method receives the resolved ``User`` as its second argument, so bodies can
    use the canonical UPN rather than whatever string the caller presented.
    """

    def decorator(fn: Callable[..., R]) -> Callable[..., R | ToolError]:
        @functools.wraps(fn)
        def wrapper(self: ComplianceService, caller: CallerIdentity, /, **kwargs) -> R | ToolError:
            persisted = audit_args(**kwargs) if audit_args else dict(kwargs)
            record = functools.partial(self._audit.write, tool=tool, args=persisted, session_id=caller.session_id, directory_version=self._directory.version)
            try:
                user = self._directory.require_group(caller.requester, group) if group else self._directory.resolve(caller.requester)
                self._limiter.check(user.upn)
                result = fn(self, user, **kwargs)
                record(requester=user.upn, outcome="ok", result_summary=result.summary)
                return result
            except AccessDenied as exc:
                record(requester=caller.requester, outcome="denied", result_summary=str(exc))
                return ToolError(error="access_denied", detail=str(exc))
            except RateLimited as exc:
                record(requester=caller.requester, outcome="denied", result_summary=str(exc))
                return ToolError(error="rate_limited", detail=str(exc))
            except DraftRejected as exc:
                record(requester=caller.requester, outcome="error", result_summary=f"draft_rejected: {exc}")
                return ToolError(error="draft_rejected", detail=str(exc))
            except (InvalidInput, ValidationError) as exc:
                detail = str(exc) if isinstance(exc, InvalidInput) else "argument failed validation"
                record(requester=caller.requester, outcome="error", result_summary=f"invalid_input: {detail}")
                return ToolError(error="invalid_input", detail=detail)
            except NotFound as exc:
                record(requester=caller.requester, outcome="error", result_summary=f"not_found: {exc}")
                return ToolError(error="not_found", detail=str(exc))
            except Exception:  # the model gets a code, the log gets the traceback
                log.exception("tool failed", extra={"tool": tool, "requester": caller.requester, "session_id": caller.session_id})
                record(requester=caller.requester, outcome="error", result_summary="internal_error")
                return ToolError(error="internal_error", detail="the tool failed; the error has been logged")

        return wrapper

    return decorator


def _validate_range(start: str | None, end: str | None) -> None:
    """Dates are pattern-checked by the MCP schema; here we reject impossible dates and inverted ranges."""
    for label, value in (("start", start), ("end", end)):
        if value:
            try:
                parse_iso_date(value)
            except ValueError as exc:
                raise InvalidInput(f"{label} is not a real date: {value}") from exc
    if start and end and start > end:
        raise InvalidInput(f"start {start} is after end {end}")


class ComplianceService:
    def __init__(self, settings: Settings, *, audit: AuditLog, directory: Directory, drafts: DraftStore) -> None:
        data = settings.data_dir
        self._settings = settings
        self._audit = audit
        self._directory = directory
        self._drafts = drafts
        self._policies = PolicyRepository(data / "policies")
        self._controls = ControlLibrary(data / "controls.json")
        self._tickets = TicketSystem(data / "tickets.json")
        self._feed = RegulatoryFeed(data / "regulatory_feed")
        self._attestations = AttestationTracker(data / "attestations.json")
        self._limiter = TokenBucketLimiter(per_minute=settings.rate_limit_per_minute)

    # ---- policies ---------------------------------------------------------------------------

    @audited("policy_lookup")
    def policy_lookup(self, user: User, *, query: str, limit: int = 5) -> PolicyLookupResult:
        """Search current approved policy sections. Every hit carries a citation string."""
        if not query.strip():
            raise InvalidInput("query is required")
        hits = self._policies.search(query, limit=max(1, min(limit, 20)))
        return PolicyLookupResult(summary=f"{len(hits)} section(s) for '{query}'", sections=tuple(hits))

    @audited("policy_get")
    def policy_get(self, user: User, *, policy_id: str, as_of: IsoDate | None = None) -> PolicyGetResult:
        """One policy: the current version, or the version in force on ``as_of``."""
        _validate_range(as_of, None)
        doc = self._policies.version_as_of(policy_id, as_of) if as_of else next((d for d in self._policies.current() if d.policy_id == policy_id), None)
        when = f" as of {as_of}" if as_of else ""
        return PolicyGetResult(summary=f"{policy_id} v{doc.version}" if doc else f"no approved version of {policy_id}{when}", policy=doc)

    @audited("policy_list")
    def policy_list(self, user: User) -> PolicyListResult:
        items = tuple(PolicySummary(**{k: getattr(d, k) for k in PolicySummary.model_fields}) for d in self._policies.current())
        return PolicyListResult(summary=f"{len(items)} current policies", policies=items)

    # ---- controls -------------------------------------------------------------------------------

    @audited("control_lookup")
    def control_lookup(self, user: User, *, control_id: str = "", query: str = "") -> ControlLookupResult:
        if control_id:
            control = self._controls.get(control_id)
            return ControlLookupResult(summary=f"control {control_id} {'found' if control else 'not found'}", controls=(control,) if control else ())
        if not query.strip():
            raise InvalidInput("control_id or query is required")
        hits = tuple(self._controls.search(query))
        return ControlLookupResult(summary=f"{len(hits)} control(s) for '{query}'", controls=hits)

    @audited("control_test_results")
    def control_test_results(self, user: User, *, control_id: str, start: IsoDate | None = None, end: IsoDate | None = None) -> ControlTestResultsResult:
        _validate_range(start, end)
        rows = tuple(self._controls.results(control_id, start, end))
        return ControlTestResultsResult(summary=f"{len(rows)} test result(s) for {control_id} {start or ''}..{end or ''}", results=rows)

    # ---- regulatory feed -------------------------------------------------------------------------

    @audited("regulatory_releases")
    def regulatory_releases(self, user: User, *, since: IsoDate, source: str = "") -> RegulatoryReleasesResult:
        _validate_range(since, None)
        rows = tuple(ReleaseSummary(**{k: getattr(r, k) for k in ReleaseSummary.model_fields}) for r in self._feed.since(since, source))
        return RegulatoryReleasesResult(summary=f"{len(rows)} release(s) since {since}", releases=rows)

    @audited("regulatory_release_get")
    def regulatory_release_get(self, user: User, *, release_id: str) -> RegulatoryReleaseGetResult:
        release = self._feed.get(release_id)
        return RegulatoryReleaseGetResult(summary=f"release {release_id} {'found' if release else 'not found'}", release=release)

    # ---- tickets ---------------------------------------------------------------------------------

    @audited("ticket_search")
    def ticket_search(
        self, user: User, *, query: str = "", control_id: str = "", start: IsoDate | None = None, end: IsoDate | None = None
    ) -> TicketSearchResult:
        _validate_range(start, end)
        rows = tuple(self._tickets.search(query, control_id, start, end))
        return TicketSearchResult(summary=f"{len(rows)} ticket(s)", tickets=rows)

    # ---- attestations --------------------------------------------------------------------------------

    @audited("attestations_due")
    def attestations_due(self, user: User, *, within_days: int = 14, today: IsoDate | None = None) -> AttestationsDueResult:
        """Open attestations due within a window. ``today`` is honoured only when clock override is enabled."""
        if within_days < 0 or within_days > 366:
            raise InvalidInput("within_days must be between 0 and 366")
        if today and not self._settings.allow_clock_override:
            raise InvalidInput("overriding today's date is disabled in this environment")
        _validate_range(today, None)
        as_of = parse_iso_date(today) if today else date.today()
        rows = tuple(self._attestations.due(within_days, as_of))
        return AttestationsDueResult(summary=f"{len(rows)} attestation(s) due within {within_days} days of {as_of.isoformat()}", attestations=rows)

    # ---- evidence ----------------------------------------------------------------------------------------

    @audited("evidence_bundle")
    def evidence_bundle(self, user: User, *, control_id: str, start: IsoDate, end: IsoDate) -> EvidenceBundleResult:
        """Everything an examiner would ask for on one control over one period, plus detected gaps."""
        _validate_range(start, end)
        manifest = self.compute_manifest(control_id, start, end)
        if manifest is None:
            raise NotFound(f"unknown control {control_id}")
        summary = (
            f"evidence for {control_id} {start}..{end}: {len(manifest.policy_versions)} policy versions, "
            f"{len(manifest.test_results)} tests, {len(manifest.change_tickets)} tickets, {len(manifest.gaps)} gap(s)"
        )
        return EvidenceBundleResult(summary=summary, manifest=manifest)

    def compute_manifest(self, control_id: str, start: str, end: str) -> EvidenceManifest | None:
        """The evidence bundle for a control and period, or None for an unknown control.

        Not audited on its own: it is called by ``evidence_bundle`` (audited), by draft checks,
        and by the export command, all of which leave their own record.
        """
        control = self._controls.get(control_id)
        if control is None:
            return None
        policy_versions = tuple(
            PolicyVersionRef(**{k: getattr(v, k) for k in PolicyVersionRef.model_fields})
            for pid in control.policies
            for v in self._policies.versions(pid)
            if v.status == "approved" and v.effective_date <= end
        )
        results = tuple(self._controls.results(control_id, start, end))
        tickets = tuple(self._tickets.search("", control_id, start, end))
        gaps = tuple(_detect_gaps(control.test_frequency, results, start, end))
        # The hash covers everything except itself, computed over canonical JSON of the typed fields.
        unsigned = EvidenceManifest(
            control=control,
            period_start=start,
            period_end=end,
            policy_versions=policy_versions,
            test_results=results,
            change_tickets=tickets,
            gaps=gaps,
            manifest_sha256="",
        )
        digest = hashlib.sha256(json.dumps(unsigned.model_dump(exclude={"manifest_sha256"}), sort_keys=True).encode()).hexdigest()
        return unsigned.model_copy(update={"manifest_sha256": digest})

    # ---- drafts: the only write path ------------------------------------------------------------------------

    @audited(
        "draft_create",
        group=ANALYST_GROUP,
        audit_args=lambda *, kind, title, body, related_ids=(): {
            "kind": kind,
            "title": title,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "related_ids": list(related_ids),
        },
    )
    def draft_create(self, user: User, *, kind: DraftKind, title: str, body: str, related_ids: tuple[str, ...] = ()) -> DraftCreateResult:
        """Queue a draft for human review. Requires the analyst group. Publishes nothing."""
        if not title.strip() or not body.strip():
            raise InvalidInput("title and body are required")
        check_draft(
            kind=kind,
            title=title,
            body=body,
            related_ids=tuple(related_ids),
            lookup_release=self._feed.get,
            recompute_hash=lambda c, s, e: m.manifest_sha256 if (m := self.compute_manifest(c, s, e)) else None,
        )
        draft = self._drafts.create(kind=kind, title=title, body=body, requester=user.upn, related_ids=tuple(related_ids), session_id="")
        return DraftCreateResult(summary=f"draft {draft.draft_id} ({kind}) queued for human review", draft_id=draft.draft_id, status=draft.status)

    @audited("draft_list")
    def draft_list(self, user: User, *, status: DraftStatus = DraftStatus.PENDING) -> DraftListResult:
        rows = tuple(self._drafts.list(status))
        return DraftListResult(summary=f"{len(rows)} {status} draft(s)", drafts=rows)

    @audited("draft_get")
    def draft_get(self, user: User, *, draft_id: str) -> DraftGetResult:
        draft = self._drafts.get(draft_id)
        return DraftGetResult(summary=f"draft {draft_id} {'found' if draft else 'not found'}", draft=draft)


def _draft_audit_args(*, kind: DraftKind, title: str, body: str, related_ids: tuple[str, ...] = ()) -> dict:
    """What the audit record keeps for a draft: everything except the body, which is hashed."""
    return {"kind": kind, "title": title, "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "related_ids": list(related_ids)}


# --------------------------------------------------------------------------------------------
# Gap detection
# --------------------------------------------------------------------------------------------

_TESTS_PER_MONTH = {"monthly": 1.0, "quarterly": 1 / 3, "annual": 1 / 12}


def _months_inclusive(start: str, end: str) -> int:
    s, e = parse_iso_date(start), parse_iso_date(end)
    return max(1, (e.year - s.year) * 12 + e.month - s.month + 1)


def _detect_gaps(frequency: str, results, start: str, end: str) -> list[str]:
    """Findings an approver must see: too few tests for the control's cadence, and any non-pass result.

    The count check is a floor, not a schedule check: a quarterly control over six months
    needs at least two results. Which quarters they fell in is for the human reviewer.
    """
    gaps: list[str] = []
    per_month = _TESTS_PER_MONTH.get(frequency)
    if per_month:
        needed = math.ceil(_months_inclusive(start, end) * per_month)
        if len(results) < needed:
            gaps.append(f"expected at least {needed} {frequency} test(s) in period, found {len(results)}")
    gaps.extend(f"test {r.test_id} on {r.tested_on} result={r.result}: {r.notes}".rstrip(": ") for r in results if r.result != "pass")
    return gaps
