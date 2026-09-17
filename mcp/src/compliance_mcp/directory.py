"""User directory and role checks.

The directory is a snapshot of the firm's identity provider: which people and service
accounts may talk to the agent, and which groups they belong to. In production the file is
written by a sync job from the directory groups; it is never hand-edited.

Two properties matter for audit:

* **Freshness.** The file is re-read when it changes, checked at most every ``ttl_seconds``,
  so a deactivation takes effect without a restart.
* **Provenance.** Every audit record carries the ``version`` (content hash) of the snapshot
  that authorised the call, so a reviewer can reconstruct exactly who was allowed what, when.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from .models import User

# Group that may file drafts. Approval is a separate group; see review_cli.
ANALYST_GROUP = "compliance-analysts"
APPROVER_GROUP = "compliance-approvers"


class AccessDenied(PermissionError):
    """Raised for any identity or role failure. The message is safe to show to the caller."""


class Directory:
    def __init__(self, users_file: Path, *, ttl_seconds: int = 60) -> None:
        self._path = users_file
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}
        self._version = ""
        self._mtime = 0.0
        self._checked_at = 0.0
        self._load(force=True)

    # ---- loading ------------------------------------------------------------------------

    def _load(self, *, force: bool = False) -> None:
        """Reload if the file changed. Cheap: a stat per ``ttl`` window, a full parse only on change."""
        now = time.monotonic()
        if not force and now - self._checked_at < self._ttl:
            return
        with self._lock:
            self._checked_at = now
            mtime = self._path.stat().st_mtime
            if not force and mtime == self._mtime:
                return
            raw = self._path.read_bytes()
            users = [User.model_validate(u) for u in json.loads(raw)["users"]]
            index: dict[str, User] = {}
            for user in users:
                index[user.id.lower()] = user
                index[user.upn.lower()] = user
            self._users = index
            self._version = hashlib.sha256(raw).hexdigest()[:16]
            self._mtime = mtime

    @property
    def version(self) -> str:
        """Short content hash of the snapshot currently in force."""
        self._load()
        return self._version

    # ---- checks -------------------------------------------------------------------------

    def resolve(self, requester: str) -> User:
        """Return the active user for a UPN or object id, or raise ``AccessDenied``."""
        self._load()
        key = (requester or "").strip().lower()
        if not key:
            raise AccessDenied("requester identity is required on every call")
        user = self._users.get(key)
        if user is None:
            raise AccessDenied(f"requester '{requester}' is not in the allowlist")
        if not user.active:
            raise AccessDenied(f"requester '{requester}' is inactive")
        return user

    def require_group(self, requester: str, group: str) -> User:
        user = self.resolve(requester)
        if group not in user.groups:
            raise AccessDenied(f"requester '{user.upn}' is not a member of '{group}'")
        return user

    def require_approver(self, requester: str) -> User:
        """Approvers must be people in the approver group. Service accounts never approve."""
        user = self.require_group(requester, APPROVER_GROUP)
        if user.kind != "person":
            raise AccessDenied(f"'{user.upn}' is a service account and cannot approve")
        return user
