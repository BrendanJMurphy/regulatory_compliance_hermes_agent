"""Approval CLI: four-eyes, approver group, dev vs OIDC identity."""

import time
from dataclasses import replace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK

from compliance_mcp import review_cli
from compliance_mcp.audit import verify
from compliance_mcp.models import DraftKind
from compliance_mcp.oidc import OidcConfig, OidcVerifier, TokenInvalid
from compliance_mcp.settings import ReviewIdentityMode
from tests.conftest import ANALYST, APPROVER, BOTH, FRONT_OFFICE, HMAC_KEY, caller


def _file_draft(svc, by=BOTH) -> str:
    return svc.draft_create(caller(by), kind=DraftKind.CONTROL_FINDING_NOTE, title="t", body="b").draft_id


def test_dev_mode_enforces_four_eyes_and_approver_group(svc, settings, capsys):
    draft_id = _file_draft(svc, by=BOTH)
    assert review_cli.main(["approve", draft_id, "--as", BOTH], settings) == 2  # requester cannot self-approve
    assert "four-eyes" in capsys.readouterr().err
    assert review_cli.main(["approve", draft_id, "--as", ANALYST], settings) == 2  # analysts are not approvers
    assert review_cli.main(["approve", draft_id, "--as", FRONT_OFFICE], settings) == 2
    assert review_cli.main(["approve", draft_id, "--as", APPROVER, "--note", "reviewed"], settings) == 0
    assert svc.draft_get(caller(ANALYST), draft_id=draft_id).draft.decision.by == APPROVER
    assert review_cli.main(["reject", draft_id, "--as", APPROVER], settings) == 2  # already decided
    result = verify(settings.audit_log, hmac_key=HMAC_KEY)
    assert result.ok and result.records >= 6


# ---- OIDC -------------------------------------------------------------------------------------

ISSUER, AUDIENCE = "https://login.example-am.com/tenant", "compliance-review-cli"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJwks:
    """Stands in for PyJWKClient: returns the public half of our test key for any token."""

    def __init__(self, private_key) -> None:
        pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self._jwk = PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(serialization.load_pem_public_key(pem)), algorithm="RS256")

    def get_signing_key_from_jwt(self, token: str):
        return self._jwk


def _token(key, **overrides) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300, "preferred_username": APPROVER, **overrides}
    return jwt.encode(claims, key, algorithm="RS256")


def test_oidc_verifier_accepts_valid_and_rejects_bad_tokens(signing_key):
    verifier = OidcVerifier(OidcConfig(ISSUER, AUDIENCE, "https://unused/jwks"), jwk_client=_FakeJwks(signing_key))
    assert verifier.username(_token(signing_key)) == APPROVER
    for bad in (
        _token(signing_key, aud="other-app"),
        _token(signing_key, iss="https://evil.example"),
        _token(signing_key, exp=int(time.time()) - 600),
        _token(rsa.generate_private_key(public_exponent=65537, key_size=2048)),  # wrong key
    ):
        with pytest.raises(TokenInvalid):
            verifier.username(bad)
    with pytest.raises(TokenInvalid, match="no 'preferred_username'"):
        verifier.username(_token(signing_key, preferred_username=None))


def test_oidc_mode_refuses_as_and_uses_the_token_identity(svc, settings, signing_key, monkeypatch, capsys):
    oidc_settings = replace(
        settings, review_identity_mode=ReviewIdentityMode.OIDC, oidc_issuer=ISSUER, oidc_audience=AUDIENCE, oidc_jwks_url="https://unused/jwks"
    )
    monkeypatch.setattr(review_cli, "OidcVerifier", lambda cfg: OidcVerifier(cfg, jwk_client=_FakeJwks(signing_key)))
    draft_id = _file_draft(svc)
    assert review_cli.main(["approve", draft_id, "--as", APPROVER], oidc_settings) == 2
    assert "requires --id-token" in capsys.readouterr().err
    assert review_cli.main(["approve", draft_id, "--id-token", _token(signing_key, preferred_username=FRONT_OFFICE)], oidc_settings) == 2
    assert review_cli.main(["approve", draft_id, "--id-token", _token(signing_key)], oidc_settings) == 0
    assert svc.draft_get(caller(ANALYST), draft_id=draft_id).draft.decision.by == APPROVER
