"""
Tests for Production-Grade Authentication, Authorization & Security
=====================================================================
Validates RFC 7519 JWT verification, OAuth 2.1 PKCE authorization code grants,
token revocation, centralized tenant authorization, actor spoofing defenses,
and REST security under both development and production (fail-closed) policies.
"""
import os
import tempfile
import time
from typing import Generator
import pytest
from starlette.testclient import TestClient

from src.models.principal import TrustedPrincipal
from src.security.auth_service import (
    create_access_token,
    verify_access_token,
    revoke_token,
    compute_code_challenge_s256,
    verify_pkce,
    issue_authorization_code,
    exchange_authorization_code,
    check_business_authorization,
    AuthenticationError,
    TokenExpiredError,
    InvalidCredentialsError,
    ScopeInsufficientError,
    TenantAccessDeniedError,
    JWT_SECRET,
    JWT_AUDIENCE,
    JWT_ISSUER,
)
from src.decision.policy_engine import PermissionEngine
from src.db.connection import initialize_database, seed_business_state
from src.decision.approval_service import PurchaseApprovalService
from src.db.state_repository import BusinessStateRepository
import src.server.web_app as web_app
from src.server.web_app import app


# ── Unit Tests: Token Minting, Verification, Revocation ────────────────────────

def test_jwt_minting_and_successful_verification():
    """Validates that a minted JWT contains required claims and successfully verifies into TrustedPrincipal."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01", "biz_retail_02"],
        scopes=["business:read", "approvals:execute"],
        roles=["owner"],
        expires_in_seconds=3600,
        session_id="sess_12345",
    )
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    principal = verify_access_token(token, required_scopes=["business:read"])
    assert principal.is_authenticated is True
    assert principal.subject == "owner_rajesh"
    assert principal.session_id == "sess_12345"
    assert "biz_kirana_01" in principal.business_membership
    assert "biz_retail_02" in principal.business_membership
    assert principal.has_business_access("biz_kirana_01") is True
    assert principal.has_business_access("biz_other") is False
    assert principal.has_scope("approvals:execute") is True
    assert principal.has_scope("admin:all") is False


def test_jwt_expired_token_rejected():
    """Expired tokens must raise TokenExpiredError and fail verification."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01"],
        expires_in_seconds=-10,  # Expired 10 seconds ago
    )
    with pytest.raises(TokenExpiredError):
        verify_access_token(token)


def test_jwt_tampered_signature_rejected():
    """Tokens with altered payloads or tampered signatures must raise InvalidCredentialsError."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01"],
    )
    # Tamper with the signature portion
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature_bytes_here"
    with pytest.raises(InvalidCredentialsError):
        verify_access_token(tampered_token)


def test_jwt_mismatched_audience_or_issuer():
    """Tokens with an unexpected audience or issuer must be rejected."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01"],
        audience="wrong-aud",
        issuer="wrong-iss",
    )
    with pytest.raises(InvalidCredentialsError):
        verify_access_token(token, expected_audience="expected-aud")


def test_jwt_insufficient_scope():
    """Tokens lacking the requested scope must raise ScopeInsufficientError."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01"],
        scopes=["business:read"],
    )
    with pytest.raises(ScopeInsufficientError):
        verify_access_token(token, required_scopes=["approvals:execute"])


def test_jwt_revocation():
    """Revoking a token causes immediate rejection on subsequent verification attempts."""
    token = create_access_token(
        subject="owner_rajesh",
        business_ids=["biz_kirana_01"],
    )
    # First verification succeeds
    p1 = verify_access_token(token)
    assert p1.is_authenticated is True

    # Revoke token
    revoke_token(token)

    # Subsequent verification must raise InvalidCredentialsError
    with pytest.raises(InvalidCredentialsError) as exc_info:
        verify_access_token(token)
    assert "revoked" in str(exc_info.value).lower()


# ── Unit Tests: PKCE S256 & Authorization Code Flow ───────────────────────────

def test_pkce_s256_computation_and_verification():
    """Validates RFC 7636 PKCE S256 challenge generation and verifier verification."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = compute_code_challenge_s256(verifier)
    assert challenge != verifier
    assert len(challenge) > 20

    # Matches S256
    assert verify_pkce(verifier, challenge, method="S256") is True

    # Rejects incorrect verifier
    assert verify_pkce("wrong_verifier_12345678901234567890", challenge, method="S256") is False

    # Rejects 'plain' method
    assert verify_pkce(verifier, verifier, method="plain") is False


def test_oauth_authorization_code_lifecycle_and_single_use():
    """Issues an auth code, verifies single-use exchange, and rejects replay attacks."""
    verifier = "v_abcdefghijklmnopqrstuvwxyz0123456789_verifier"
    challenge = compute_code_challenge_s256(verifier)

    code = issue_authorization_code(
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        scopes=["business:read", "approvals:execute"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    assert code.startswith("authcode_")

    # Successful exchange
    token_resp = exchange_authorization_code(
        code=code,
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        code_verifier=verifier,
    )
    assert "access_token" in token_resp
    assert token_resp["token_type"] == "Bearer"
    assert token_resp["subject"] == "owner_sharma"

    # Replay attack: reusing the same code must fail immediately
    with pytest.raises(InvalidCredentialsError) as exc_info:
        exchange_authorization_code(
            code=code,
            client_id="alexa_mcp_client",
            redirect_uri="https://alexa.amazon.com/api/skills/redirect",
            code_verifier=verifier,
        )
    assert "already-consumed" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_oauth_exchange_mismatched_client_or_redirect():
    """Client ID or redirect URI mismatch during exchange must be rejected."""
    verifier = "v_mismatch_check_verifier_1234567890"
    challenge = compute_code_challenge_s256(verifier)

    code = issue_authorization_code(
        client_id="valid_client",
        redirect_uri="https://valid.redirect/callback",
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        scopes=["business:read"],
        code_challenge=challenge,
    )

    with pytest.raises(InvalidCredentialsError):
        exchange_authorization_code(
            code=code,
            client_id="impostor_client",
            redirect_uri="https://valid.redirect/callback",
            code_verifier=verifier,
        )


# ── Unit Tests: Centralized Tenant Authorization ──────────────────────────────

def test_central_business_authorization():
    """Validates tenant authorization boundary across valid owners, admins, and cross-tenant impostors."""
    principal = TrustedPrincipal(
        subject="owner_kirana",
        issuer="vendo-auth",
        audience="vendo-api",
        issued_at=time.time(),
        expires_at=time.time() + 3600,
        is_authenticated=True,
        business_membership=["biz_kirana_01"],
        roles=["owner"],
    )

    # Authorized for own business
    assert check_business_authorization(principal, "biz_kirana_01") is True

    # Denied for other businesses
    assert check_business_authorization(principal, "biz_retail_02") is False
    assert check_business_authorization(principal, "biz_tiffin_03") is False

    # Expired principal is denied even for own business
    expired_principal = TrustedPrincipal(
        subject="owner_kirana",
        issuer="vendo-auth",
        audience="vendo-api",
        issued_at=time.time() - 7200,
        expires_at=time.time() - 3600,
        is_authenticated=True,
        business_membership=["biz_kirana_01"],
    )
    assert check_business_authorization(expired_principal, "biz_kirana_01") is False


# ── Integration Tests: REST Security & Fail-Closed Production Policy ───────────

@pytest.fixture
def isolated_web_env(tmp_path, monkeypatch):
    """Provides a fresh isolated database and test client."""
    temp_db = str(tmp_path / "test_auth_web.sqlite3")
    initialize_database(temp_db)
    seed_business_state(temp_db)
    svc = PurchaseApprovalService(db_path=temp_db)
    repo = BusinessStateRepository(temp_db)
    monkeypatch.setattr(web_app, "_DB_PATH", temp_db)
    monkeypatch.setattr(web_app, "approvals_service", svc)
    monkeypatch.setattr(web_app, "state_repo", repo)
    monkeypatch.setenv("DATABASE_PATH", temp_db)
    monkeypatch.setenv("VENDO_JWT_SECRET", "production-secret-key-32-chars-long-test-entropy!!")
    return temp_db


def test_production_rest_fails_closed_without_token(isolated_web_env, monkeypatch):
    """In AUTOPILOT_ENV=production, requests without a valid Bearer token must return 401."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    # Attempt query without credentials
    res = client.post(
        "/api/orchestrator/query",
        json={"business_id": "home_tiffin", "query": "Pending approvals"},
    )
    assert res.status_code == 401
    assert "Bearer" in res.headers.get("www-authenticate", "")

    # Attempt query with spoofed X-Actor-ID header (must be ignored and fail-closed)
    res_spoof = client.post(
        "/api/orchestrator/query",
        headers={"X-Actor-ID": "owner:home_tiffin"},
        json={"business_id": "home_tiffin", "query": "Pending approvals"},
    )
    assert res_spoof.status_code == 401


def test_production_rest_succeeds_with_valid_bearer_token(isolated_web_env, monkeypatch):
    """In AUTOPILOT_ENV=production, requests with a valid Bearer token succeed."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    token = create_access_token(
        subject="owner_tiffin",
        business_ids=["home_tiffin"],
        scopes=["business:read", "tasks:read"],
    )

    res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"business_id": "home_tiffin", "query": "What is my status?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "business_id" in data or "response" in data or "intent" in data


def test_production_rest_cross_tenant_token_rejected(isolated_web_env, monkeypatch):
    """A valid token for Business A attempting to access Business B must return 403 Forbidden."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    # Token only for biz_kirana
    token = create_access_token(
        subject="owner_kirana",
        business_ids=["biz_kirana_01"],
        scopes=["business:read", "tasks:read"],
    )

    # Attempt to access home_tiffin
    res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"business_id": "home_tiffin", "query": "What is my status?"},
    )
    assert res.status_code == 403
    detail = res.json().get("detail", "").lower()
    assert "not an authorized owner" in detail or "forbidden" in detail or "cross-tenant" in detail


def test_production_rest_invalid_or_expired_token(isolated_web_env, monkeypatch):
    """Malformed or expired Bearer tokens in production must return 401."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    # Malformed token
    res_malformed = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": "Bearer not-a-real-jwt-token"},
        json={"business_id": "home_tiffin", "query": "Hello"},
    )
    assert res_malformed.status_code == 401

    # Expired token
    expired_token = create_access_token(
        subject="owner_tiffin",
        business_ids=["home_tiffin"],
        expires_in_seconds=-60,
    )
    res_expired = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"business_id": "home_tiffin", "query": "Hello"},
    )
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json().get("detail", "").lower()
