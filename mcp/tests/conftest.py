import os
from pathlib import Path

import pytest

from compliance_mcp.service import ComplianceService
from compliance_mcp.settings import Settings

DATA = Path(__file__).resolve().parent.parent / "data"

ANALYST = "priya.natarajan@example-am.com"
APPROVER = "dana.whitfield@example-am.com"
BOTH = "marcus.oyelaran@example-am.com"
FRONT_OFFICE = "tom.reyes@example-am.com"
INACTIVE = "former.employee@example-am.com"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=DATA, state_dir=tmp_path / "state", audit_log=tmp_path / "state" / "audit.jsonl", bearer_token="t")


@pytest.fixture
def svc(settings: Settings) -> ComplianceService:
    return ComplianceService(settings)


@pytest.fixture
def env(settings: Settings, monkeypatch):
    monkeypatch.setenv("COMPLIANCE_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("COMPLIANCE_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("COMPLIANCE_AUDIT_LOG", str(settings.audit_log))
    return settings
