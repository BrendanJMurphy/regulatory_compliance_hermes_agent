"""Runtime configuration.

Everything comes from environment variables so that no secret and no environment-specific
path lives in code or in the image. Values are read once at import into an immutable
``Settings`` instance; tests construct their own ``Settings`` directly.

Naming convention: every variable is prefixed ``COMPLIANCE_``. Booleans accept
``1/true/yes`` (case-insensitive). Paths are expanded and made absolute.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class IdentityMode(StrEnum):
    """Where the MCP server learns who the human requester is.

    ``HEADER``    Production. An authenticating gateway in front of this server sets a trusted
                  header on every request. The ``requester`` tool argument must match it or is
                  ignored (see ``COMPLIANCE_IDENTITY_HEADER_STRICT``). The model cannot spoof it.
    ``PARAMETER`` Development only. The model supplies ``requester`` itself. Acceptable with
                  synthetic data and a single trusted operator; never with real users.
    """

    HEADER = "header"
    PARAMETER = "parameter"


class ReviewIdentityMode(StrEnum):
    """How ``compliance-review`` authenticates the human making an approval decision.

    ``OIDC`` Production. The reviewer passes an OIDC ID token from the firm's identity provider;
             the CLI verifies its signature, issuer, audience and expiry, then uses the
             ``preferred_username`` claim as the approver identity.
    ``DEV``  Development only. ``--as <upn>`` is trusted as given.
    """

    OIDC = "oidc"
    DEV = "dev"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


def _env_csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in os.environ.get(name, default).split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    # ---- Data and state -------------------------------------------------------------------
    data_dir: Path = field(default_factory=lambda: _env_path("COMPLIANCE_DATA_DIR", "./data"))
    state_dir: Path = field(default_factory=lambda: _env_path("COMPLIANCE_STATE_DIR", "./state"))

    # ---- Audit ---------------------------------------------------------------------------
    audit_log: Path = field(default_factory=lambda: _env_path("COMPLIANCE_AUDIT_LOG", "./state/audit/audit.jsonl"))
    # Secret used to MAC every record. Held by the server process only (from a secrets manager),
    # never written next to the log. With it, an attacker who can rewrite the log file cannot
    # forge a valid chain. Empty disables MACs (dev only; verify still checks the hash chain).
    audit_hmac_key: str = field(default_factory=lambda: _env("COMPLIANCE_AUDIT_HMAC_KEY"))
    # Rotate the active log once it exceeds this many bytes. The chain continues across files.
    audit_rotate_bytes: int = field(default_factory=lambda: _env_int("COMPLIANCE_AUDIT_ROTATE_BYTES", 50_000_000))
    # Optional HTTPS sink (SIEM / WORM archive). Records are spooled to disk first and sent by a
    # background thread with retry, so a slow or dead sink never blocks or loses a tool call.
    audit_forward_url: str = field(default_factory=lambda: _env("COMPLIANCE_AUDIT_FORWARD_URL"))
    audit_forward_token: str = field(default_factory=lambda: _env("COMPLIANCE_AUDIT_FORWARD_TOKEN"))
    # Send the chain head to the sink every N records so the archive can prove no tail was cut.
    audit_anchor_every: int = field(default_factory=lambda: _env_int("COMPLIANCE_AUDIT_ANCHOR_EVERY", 100))

    # ---- Transport -------------------------------------------------------------------------
    host: str = field(default_factory=lambda: _env("COMPLIANCE_MCP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("COMPLIANCE_MCP_PORT", 8765))
    # Host header values the MCP transport accepts (DNS-rebinding protection).
    allowed_hosts: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("COMPLIANCE_MCP_ALLOWED_HOSTS", "127.0.0.1:8765,localhost:8765,compliance-mcp:8765")
    )
    # Shared secret the gateway must present as a bearer token. Empty disables the check (dev only).
    bearer_token: str = field(default_factory=lambda: _env("COMPLIANCE_MCP_TOKEN"))

    # ---- Identity ----------------------------------------------------------------------------
    identity_mode: IdentityMode = field(default_factory=lambda: IdentityMode(_env("COMPLIANCE_IDENTITY_MODE", "parameter")))
    identity_header: str = field(default_factory=lambda: _env("COMPLIANCE_IDENTITY_HEADER", "x-requester").lower())
    # In HEADER mode: if the model also passes ``requester`` and it differs from the header, deny
    # (strict) or silently use the header (lenient). Strict surfaces prompt-injection attempts.
    identity_header_strict: bool = field(default_factory=lambda: _env_bool("COMPLIANCE_IDENTITY_HEADER_STRICT", True))
    session_header: str = field(default_factory=lambda: _env("COMPLIANCE_SESSION_HEADER", "x-session-id").lower())
    # Re-read users.json at most this often. Deactivations take effect within this window.
    directory_ttl_seconds: int = field(default_factory=lambda: _env_int("COMPLIANCE_DIRECTORY_TTL_SECONDS", 60))

    # ---- Review CLI ---------------------------------------------------------------------------
    review_identity_mode: ReviewIdentityMode = field(default_factory=lambda: ReviewIdentityMode(_env("COMPLIANCE_REVIEW_IDENTITY_MODE", "dev")))
    oidc_issuer: str = field(default_factory=lambda: _env("COMPLIANCE_OIDC_ISSUER"))
    oidc_audience: str = field(default_factory=lambda: _env("COMPLIANCE_OIDC_AUDIENCE"))
    oidc_jwks_url: str = field(default_factory=lambda: _env("COMPLIANCE_OIDC_JWKS_URL"))
    oidc_username_claim: str = field(default_factory=lambda: _env("COMPLIANCE_OIDC_USERNAME_CLAIM", "preferred_username"))

    # ---- Behaviour ---------------------------------------------------------------------------
    # Let callers override "today" in date-relative tools. Needed for deterministic tests and
    # scenario runs; must be off in production so a prompt cannot move deadlines.
    allow_clock_override: bool = field(default_factory=lambda: _env_bool("COMPLIANCE_ALLOW_CLOCK_OVERRIDE", False))
    # Identity stamped on every audit record for this server instance.
    agent_id: str = field(default_factory=lambda: _env("COMPLIANCE_AGENT_ID", "hermes-regcomply"))
    log_json: bool = field(default_factory=lambda: _env_bool("COMPLIANCE_LOG_JSON", True))

    @property
    def drafts_db(self) -> Path:
        return self.state_dir / "drafts.sqlite3"

    @property
    def audit_spool_dir(self) -> Path:
        return self.audit_log.parent / "spool"


SETTINGS = Settings()
