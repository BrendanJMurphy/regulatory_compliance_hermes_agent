"""Runtime settings, all from environment variables so nothing secret lives in code."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: _env_path("COMPLIANCE_DATA_DIR", "./data"))
    state_dir: Path = field(default_factory=lambda: _env_path("COMPLIANCE_STATE_DIR", "./state"))
    audit_log: Path = field(default_factory=lambda: _env_path("COMPLIANCE_AUDIT_LOG", "./state/audit.jsonl"))
    # Optional HTTPS sink (SIEM / WORM archive). Best effort, never blocks a tool call.
    audit_forward_url: str = field(default_factory=lambda: os.environ.get("COMPLIANCE_AUDIT_FORWARD_URL", ""))
    audit_forward_token: str = field(default_factory=lambda: os.environ.get("COMPLIANCE_AUDIT_FORWARD_TOKEN", ""))
    host: str = field(default_factory=lambda: os.environ.get("COMPLIANCE_MCP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("COMPLIANCE_MCP_PORT", "8765")))
    # Host header values the MCP transport accepts (DNS-rebinding protection).
    allowed_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            h.strip() for h in os.environ.get("COMPLIANCE_MCP_ALLOWED_HOSTS", "127.0.0.1:8765,localhost:8765,compliance-mcp:8765").split(",") if h.strip()
        )
    )
    # Shared secret the gateway must present as a bearer token. Empty disables the check (dev only).
    bearer_token: str = field(default_factory=lambda: os.environ.get("COMPLIANCE_MCP_TOKEN", ""))
    # Identity stamped on every audit record for the calling agent instance.
    agent_id: str = field(default_factory=lambda: os.environ.get("COMPLIANCE_AGENT_ID", "hermes-regcomply"))


SETTINGS = Settings()
