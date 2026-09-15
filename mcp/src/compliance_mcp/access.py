"""Requester identity and role gating.

The agent passes the requester's directory identity (Azure AD object id or UPN) on every
call. Read tools are open to any allowlisted user; write tools (which only ever create
drafts) require membership in an approved group. Approval of a draft is never exposed
as an MCP tool: it happens through `compliance-review`, run by a named human.
"""

from __future__ import annotations

import json
from pathlib import Path


class AccessDenied(PermissionError):
    pass


class Directory:
    def __init__(self, users_file: Path) -> None:
        raw = json.loads(users_file.read_text(encoding="utf-8"))
        self.users: dict[str, dict] = {}
        for u in raw["users"]:
            self.users[u["id"].lower()] = u
            self.users[u["upn"].lower()] = u

    def resolve(self, requester: str) -> dict:
        if not requester or not requester.strip():
            raise AccessDenied("requester identity is required on every call")
        u = self.users.get(requester.strip().lower())
        if u is None:
            raise AccessDenied(f"requester '{requester}' is not in the allowlist")
        if not u.get("active", True):
            raise AccessDenied(f"requester '{requester}' is inactive")
        return u

    def require_group(self, requester: str, group: str) -> dict:
        u = self.resolve(requester)
        if group not in u.get("groups", []):
            raise AccessDenied(f"requester '{u['upn']}' is not a member of '{group}'")
        return u
