"""OIDC ID-token verification for the review CLI.

An approver proves who they are by presenting an ID token issued by the firm's identity
provider (Entra ID, Okta, ...). We verify the token the standard way: fetch the issuer's
signing keys from its JWKS endpoint, check the signature, issuer, audience, and expiry, then
read the username claim. Nothing here trusts anything the caller typed.

Kept deliberately small and dependency-light (``PyJWT`` with its ``cryptography`` extra).
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient


class TokenInvalid(PermissionError):
    """The token could not be verified. The message is safe to show."""


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    audience: str
    jwks_url: str
    username_claim: str = "preferred_username"

    def validate(self) -> None:
        missing = [k for k in ("issuer", "audience", "jwks_url") if not getattr(self, k)]
        if missing:
            raise ValueError(f"OIDC review identity needs COMPLIANCE_OIDC_{'/'.join(m.upper() for m in missing)}")


class OidcVerifier:
    def __init__(self, config: OidcConfig, *, jwk_client: PyJWKClient | None = None) -> None:
        config.validate()
        self._config = config
        # Injectable for tests; PyJWKClient caches keys and refreshes on unknown ``kid``.
        self._jwks = jwk_client or PyJWKClient(config.jwks_url, cache_keys=True)

    def username(self, token: str) -> str:
        """Return the verified username claim, or raise ``TokenInvalid``."""
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self._config.audience,
                issuer=self._config.issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalid(f"id token rejected: {exc}") from exc
        username = claims.get(self._config.username_claim)
        if not isinstance(username, str) or not username:
            raise TokenInvalid(f"id token has no '{self._config.username_claim}' claim")
        return username
