"""Shared fixtures.

Every test gets its own state directory and audit log. The fixture data under ``data/`` is
read-only and shared. ``svc`` builds a fully wired service exactly as the server would,
but with no HTTP in the way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compliance_mcp.audit import AuditLog
from compliance_mcp.directory import Directory
from compliance_mcp.drafts import DraftStore
from compliance_mcp.models import CallerIdentity, IdentitySource
from compliance_mcp.service import ComplianceService
from compliance_mcp.settings import IdentityMode, ReviewIdentityMode, Settings

DATA = Path(__file__).resolve().parent.parent / "data"

ANALYST = "priya.natarajan@example-am.com"
APPROVER = "dana.whitfield@example-am.com"
BOTH = "marcus.oyelaran@example-am.com"  # analyst and approver
FRONT_OFFICE = "tom.reyes@example-am.com"
INACTIVE = "former.employee@example-am.com"
SERVICE = "svc-regcomply@example-am.com"
HMAC_KEY = "test-hmac-key"


def caller(upn: str, session_id: str = "sess-1") -> CallerIdentity:
    return CallerIdentity(requester=upn, source=IdentitySource.PARAMETER, session_id=session_id)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    state = tmp_path / "state"
    return Settings(
        data_dir=DATA,
        state_dir=state,
        audit_log=state / "audit" / "audit.jsonl",
        audit_hmac_key=HMAC_KEY,
        bearer_token="test-token",
        identity_mode=IdentityMode.PARAMETER,
        review_identity_mode=ReviewIdentityMode.DEV,
        allow_clock_override=True,
        log_json=False,
    )


@pytest.fixture
def audit(settings: Settings) -> AuditLog:
    return AuditLog(settings.audit_log, "test-agent", hmac_key=settings.audit_hmac_key)


@pytest.fixture
def directory(settings: Settings) -> Directory:
    return Directory(settings.data_dir / "users.json", ttl_seconds=0)


@pytest.fixture
def svc(settings: Settings, audit: AuditLog, directory: Directory) -> ComplianceService:
    return ComplianceService(settings, audit=audit, directory=directory, drafts=DraftStore(settings.drafts_db))
