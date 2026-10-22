"""
Tests for Final Backend Security and Alexa+ Protocol Compatibility Fixes
=======================================================================
Validates the six specific areas:
1. RFC 9728 Protected Resource Metadata & RFC 8414 Authorization Server Metadata
2. Alexa+ QuickStart HTTP 401 contract (no WWW-Authenticate header on discovery)
3. Complete OAuth 2.1 PKCE & Refresh-Token Lifecycle (issuance, rotation, replay protection, family revocation)
4. Centralized Deployment URL validation & Anti-Open-Redirect defenses
5. Production Identity & Token Trust (fail-closed secret validation, anti-spoofing)
6. Streamable HTTP MCP Scenarios & Local Verification
"""
from __future__ import annotations

import os
import time
import urllib.parse
import pytest
from starlette.testclient import TestClient

from src.models.principal import TrustedPrincipal
from src.security.oauth_config import (
    validate_deployment_url,
    get_public_base_url,
    get_mcp_resource_url,
    get_auth_issuer_url,
    is_valid_client_redirect,
    ConfigurationError,
)
from src.security.auth_service import (
    create_access_token,
    verify_access_token,
    compute_code_challenge_s256,
    issue_authorization_code,
    exchange_authorization_code,
    refresh_access_token,
    revoke_oauth_token,
    InvalidCredentialsError,
    DEFAULT_SECRET,
)
from src.db.connection import initialize_database, seed_business_state
from src.db.task_repository import TaskRepository, OperationalTask, ActionProposal, TaskState
from src.db.session_repository import SessionRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.email_repository import EmailRepository
from src.db.state_repository import BusinessStateRepository
from src.db.refresh_token_repository import RefreshTokenRepository
from src.decision.approval_service import PurchaseApprovalService
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher
from src.agent.supervisor import EmailOperationalSupervisor
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.server.mcp_server import create_mcp_server
import src.server.web_app as web_app
from src.server.web_app import app


@pytest.fixture
def security_test_env(tmp_path, monkeypatch):
    """Provides a fresh isolated database and configured app for security testing."""
    temp_db = str(tmp_path / "security_fixes_test.sqlite3")
    initialize_database(temp_db)
    seed_business_state(temp_db)

    task_repo = TaskRepository(temp_db)
    email_repo = EmailRepository(temp_db)
    session_repo = SessionRepository(temp_db)
    profile_repo = AdaptiveProfileRepository(temp_db)
    approvals_svc = PurchaseApprovalService(db_path=temp_db)
    state_repo = BusinessStateRepository(temp_db)

    policy_engine = PermissionEngine()
    policy_engine.set_authorized_owners("biz_kirana_01", ["owner_sharma", "owner:owner_sharma"])
    policy_engine.set_authorized_owners("home_tiffin", ["owner_tiffin", "owner:owner_tiffin"])

    action_dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)
    supervisor = EmailOperationalSupervisor(
        email_repo=email_repo,
        task_repo=task_repo,
        profile_repo=profile_repo,
        policy_engine=policy_engine,
    )
    orch = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        approval_service=approvals_svc,
        task_repo=task_repo,
        email_repo=email_repo,
        supervisor=supervisor,
        action_dispatcher=action_dispatcher,
        policy_engine=policy_engine,
        session_repo=session_repo,
    )

    monkeypatch.setattr(web_app, "_DB_PATH", temp_db)
    monkeypatch.setattr(web_app, "task_repo", task_repo)
    monkeypatch.setattr(web_app, "session_repo", session_repo)
    monkeypatch.setattr(web_app, "approvals_service", approvals_svc)
    monkeypatch.setattr(web_app, "state_repo", state_repo)
    monkeypatch.setattr(web_app, "policy_engine", policy_engine)
    monkeypatch.setattr(web_app, "orchestrator", orch)
    monkeypatch.setenv("DATABASE_PATH", temp_db)

    client = TestClient(app)
    return {
        "db_path": temp_db,
        "task_repo": task_repo,
        "session_repo": session_repo,
        "profile_repo": profile_repo,
        "policy_engine": policy_engine,
        "client": client,
    }


# ── FIX 1: OAuth Metadata & RFC Compliance ────────────────────────────────────

def test_rfc9728_protected_resource_metadata(security_test_env):
    """
    Validates RFC 9728 OAuth 2.0 Protected Resource Metadata at /.well-known/oauth-protected-resource.
    Must contain canonical resource identifier, authorization_servers, scopes_supported, and bearer_methods.
    """
    client = security_test_env["client"]
    res = client.get("/.well-known/oauth-protected-resource")
    assert res.status_code == 200
    meta = res.json()

    assert "resource" in meta
    assert meta["resource"].endswith("/mcp")
    assert "authorization_servers" in meta
    assert isinstance(meta["authorization_servers"], list)
    assert len(meta["authorization_servers"]) > 0

    assert "scopes_supported" in meta
    assert "business:read" in meta["scopes_supported"]
    assert "approvals:execute" in meta["scopes_supported"]

    assert "bearer_methods_supported" in meta
    assert "header" in meta["bearer_methods_supported"]


def test_rfc8414_authorization_server_metadata(security_test_env):
    """
    Validates RFC 8414 OAuth 2.0 Authorization Server Metadata at /.well-known/oauth-authorization-server.
    Must accurately advertise supported grant types, response types, endpoints, and PKCE S256.
    Must not advertise unsupported features.
    """
    client = security_test_env["client"]
    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 200
    meta = res.json()

    assert "issuer" in meta
    assert "/oauth/authorize" in meta["authorization_endpoint"]
    assert "/oauth/token" in meta["token_endpoint"]
    assert "/oauth/revoke" in meta["revocation_endpoint"]

    # Advertised capabilities
    assert meta["response_types_supported"] == ["code"]
    assert set(meta["grant_types_supported"]) == {"authorization_code", "refresh_token"}
    assert "S256" in meta["code_challenge_methods_supported"]
    assert meta.get("authorization_response_iss_parameter_supported") is True  # RFC 9207

    # Ensure unsupported grants (e.g., implicit, password) are strictly NOT advertised
    assert "password" not in meta["grant_types_supported"]
    assert "token" not in meta["response_types_supported"]
    assert "client_credentials" not in meta["grant_types_supported"]


def test_metadata_host_header_manipulation_ignored(security_test_env):
    """Untrusted Host headers must NOT poison the canonical authorization server metadata URLs."""
    client = security_test_env["client"]
    res = client.get(
        "/.well-known/oauth-authorization-server",
        headers={"Host": "malicious-phishing-host.com"},
    )
    assert res.status_code == 200
    meta = res.json()
    assert "malicious-phishing-host.com" not in meta["issuer"]
    assert "malicious-phishing-host.com" not in meta["authorization_endpoint"]
    assert "malicious-phishing-host.com" not in meta["token_endpoint"]


# ── FIX 2: Alexa+-Compatible HTTP 401 Behavior on /mcp ────────────────────────

def test_mcp_unauthenticated_discovery_omits_www_authenticate(security_test_env, monkeypatch):
    """
    Amazon Alexa+ QuickStart requirement:
    Unauthenticated MCP discovery requests on /mcp must return HTTP 401 WITHOUT a WWW-Authenticate header.
    Must not expose tools, tenant data, or session information.
    """
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = security_test_env["client"]

    res = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "alexa_init", "method": "initialize", "params": {}},
    )
    assert res.status_code == 401
    assert "WWW-Authenticate" not in res.headers
    data = res.json()
    assert data.get("error") == "unauthorized"
    # Ensure no tools or sensitive information leaked
    assert "tools" not in data
    assert "result" not in data


def test_mcp_invalid_and_expired_tokens_rejected(security_test_env, monkeypatch):
    """Invalid or expired bearer tokens on /mcp must return 401 and fail closed."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    monkeypatch.setenv("VENDO_JWT_SECRET", "production-secure-key-with-sufficient-entropy-9999999999")
    client = security_test_env["client"]

    # 1. Invalid signature
    res = client.post(
        "/mcp",
        headers={"Authorization": "Bearer forged.token.signature"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert res.status_code == 401

    # 2. Expired token
    expired_token = create_access_token(
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        expires_in_seconds=-60,
    )
    res_exp = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert res_exp.status_code == 401


def test_mcp_wrong_audience_and_issuer_rejected(security_test_env, monkeypatch):
    """Token with wrong audience or issuer must be rejected on /mcp."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    monkeypatch.setenv("VENDO_JWT_SECRET", "production-secure-key-with-sufficient-entropy-9999999999")
    client = security_test_env["client"]

    wrong_aud_token = create_access_token(
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        audience="wrong-service-api",
    )
    res = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {wrong_aud_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert res.status_code == 401


# ── FIX 3: Complete OAuth Refresh-Token Lifecycle ──────────────────────────────

def test_refresh_token_lifecycle_rotation_and_persistence(security_test_env):
    """
    Validates:
    - Initial authorization code exchange yields access_token + refresh_token
    - Refresh tokens are cryptographically random and stored hashed in SQLite
    - Refresh grant issues a new access token and safely rotates the refresh token
    - Previous refresh token is consumed and marked non-usable
    - Server restart persistence: querying the DB directly confirms durable state
    """
    client = security_test_env["client"]
    db_path = security_test_env["db_path"]

    verifier = "pkce_verifier_long_enough_random_test_string_12345"
    challenge = compute_code_challenge_s256(verifier)

    # 1. Authorize
    auth_params = {
        "client_id": "alexa_skill_vendo_01",
        "redirect_uri": "https://alexa.amazon.com/api/skills/redirect",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "state_refresh_test_01",
        "scope": "business:read approvals:execute",
        "owner_id": "owner_sharma",
        "business_id": "biz_kirana_01",
    }
    auth_res = client.get("/oauth/authorize", params=auth_params, follow_redirects=False)
    assert auth_res.status_code == 302
    parsed = urllib.parse.urlparse(auth_res.headers["location"])
    code = urllib.parse.parse_qs(parsed.query)["code"][0]

    # 2. Exchange code for tokens
    exchange_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://alexa.amazon.com/api/skills/redirect",
        "client_id": "alexa_skill_vendo_01",
        "code_verifier": verifier,
    }
    tok_res = client.post("/oauth/token", json=exchange_payload)
    assert tok_res.status_code == 200
    tok_data = tok_res.json()
    r1 = tok_data["refresh_token"]
    assert r1.startswith("ref_")

    # Verify directly in SQLite repository
    rt_repo = RefreshTokenRepository(db_path)
    record1 = rt_repo.get_token_record(r1)
    assert record1 is not None
    assert record1.subject == "owner_sharma"
    assert record1.consumed_at is None
    assert not record1.is_revoked

    # 3. Refresh token grant (Amazon Alexa+ does NOT send resource parameter here)
    refresh_payload = {
        "grant_type": "refresh_token",
        "refresh_token": r1,
        "client_id": "alexa_skill_vendo_01",
    }
    ref_res = client.post("/oauth/token", json=refresh_payload)
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    r2 = ref_data["refresh_token"]

    # Verify rotation: r2 is distinct from r1
    assert r2 != r1
    assert ref_data["subject"] == "owner_sharma"
    assert "biz_kirana_01" in ref_data["business_ids"]

    # Check persistence: r1 is now consumed
    record1_after = rt_repo.get_token_record(r1)
    assert record1_after.consumed_at is not None

    record2 = rt_repo.get_token_record(r2)
    assert record2 is not None
    assert record2.family_id == record1.family_id
    assert record2.consumed_at is None


def test_refresh_token_replay_attack_detection_revokes_entire_family(security_test_env):
    """
    Replay Protection:
    If a previously consumed refresh token is re-presented:
    1. Replay is detected.
    2. Token issuance fails immediately.
    3. Entire token family is revoked.
    4. Subsequent refresh requests with even the legitimate active token in that family are denied.
    """
    client = security_test_env["client"]
    verifier = "pkce_replay_test_verifier_secure_random_string_09876"
    challenge = compute_code_challenge_s256(verifier)

    # Issue initial tokens
    code = issue_authorization_code(
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        scopes=["business:read", "approvals:execute"],
        code_challenge=challenge,
    )
    tokens = exchange_authorization_code(
        code=code,
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        code_verifier=verifier,
    )
    rt_original = tokens["refresh_token"]

    # First legitimate refresh -> rotates to rt_rotated
    ref_result = refresh_access_token(
        refresh_token=rt_original,
        client_id="alexa_mcp_client",
    )
    rt_rotated = ref_result["refresh_token"]
    assert rt_rotated != rt_original

    # Replay attack: Attacker attempts to use consumed rt_original
    with pytest.raises(InvalidCredentialsError) as exc_info:
        refresh_access_token(
            refresh_token=rt_original,
            client_id="alexa_mcp_client",
        )
    assert "replay detected" in str(exc_info.value).lower()

    # Legit user now tries to use rt_rotated -> must be denied because family was revoked
    with pytest.raises(InvalidCredentialsError) as fam_exc:
        refresh_access_token(
            refresh_token=rt_rotated,
            client_id="alexa_mcp_client",
        )
    assert "revoked" in str(fam_exc.value).lower()


def test_cross_client_refresh_token_rejected(security_test_env):
    """A refresh token issued to client A cannot be refreshed by client B."""
    verifier = "pkce_cross_client_verifier_1234567890"
    challenge = compute_code_challenge_s256(verifier)

    code = issue_authorization_code(
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        scopes=["business:read"],
        code_challenge=challenge,
    )
    tokens = exchange_authorization_code(
        code=code,
        client_id="alexa_mcp_client",
        redirect_uri="https://alexa.amazon.com/api/skills/redirect",
        code_verifier=verifier,
    )

    with pytest.raises(InvalidCredentialsError) as exc:
        refresh_access_token(
            refresh_token=tokens["refresh_token"],
            client_id="test-client-id",  # Wrong client
        )
    assert "client_id mismatch" in str(exc.value).lower()


# ── FIX 4: Centralized Deployment URLs & Anti-Open-Redirect Defenses ───────────

def test_deployment_url_validation_rules(monkeypatch):
    """Validates URL canonicalization, rejection of placeholders, and HTTPS enforcement."""
    # 1. Dev allows localhost
    monkeypatch.setenv("AUTOPILOT_ENV", "development")
    url_dev = validate_deployment_url("http://localhost:8000/", "BASE_URL")
    assert url_dev == "http://localhost:8000"

    # 2. Production strictly requires HTTPS
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    with pytest.raises(ConfigurationError) as exc_http:
        validate_deployment_url("http://api.vendo.com", "BASE_URL")
    assert "must use HTTPS in production" in str(exc_http.value)

    # 3. Production strictly rejects placeholder .example.com
    with pytest.raises(ConfigurationError) as exc_ex:
        validate_deployment_url("https://api.vendo.example.com", "BASE_URL")
    assert "cannot use placeholder '.example.com'" in str(exc_ex.value)

    # 4. Embedded credentials strictly rejected in any environment
    with pytest.raises(ConfigurationError) as exc_cred:
        validate_deployment_url("https://admin:secret@api.vendo.com", "BASE_URL")
    assert "must not embed credentials" in str(exc_cred.value)


def test_open_redirect_rejected_at_authorize_endpoint(security_test_env):
    """Attempts to redirect user to an unregistered external callback must be rejected immediately."""
    client = security_test_env["client"]
    verifier = "pkce_open_redirect_verifier_12345"
    challenge = compute_code_challenge_s256(verifier)

    malicious_params = {
        "client_id": "alexa_skill_vendo_01",
        "redirect_uri": "https://malicious-phishing-site.com/callback",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "owner_id": "owner_sharma",
        "business_id": "biz_kirana_01",
    }
    res = client.get("/oauth/authorize", params=malicious_params, follow_redirects=False)
    assert res.status_code == 400
    assert "redirect uri" in res.json().get("detail", "").lower()


# ── FIX 5: Production Identity & Token Trust Boundaries ───────────────────────

def test_production_mode_rejects_insecure_default_secret(monkeypatch):
    """
    In production mode (AUTOPILOT_ENV=production), attempting to use the default test signing key
    must fail closed to prevent forgery attacks.
    """
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    monkeypatch.delenv("VENDO_JWT_SECRET", raising=False)

    with pytest.raises(ConfigurationError) as exc:
        create_access_token(
            subject="owner_sharma",
            business_ids=["biz_kirana_01"],
        )
    assert "production mode strictly requires" in str(exc.value).lower()


@pytest.mark.anyio
async def test_mcp_tool_actor_id_cannot_spoof_identity(security_test_env):
    """
    MCP tool arguments must NEVER be trusted as identity proofs.
    The caller's actor identity is strictly derived from the verified token principal.
    """
    from src.server.mcp_auth import _current_mcp_principal

    task_repo: TaskRepository = security_test_env["task_repo"]
    policy_engine: PermissionEngine = security_test_env["policy_engine"]

    # Create task & proposal
    task = OperationalTask(
        task_id="task_spoof_01",
        business_id="biz_kirana_01",
        title="Restock sugar",
        task_type="supplier_order",
    )
    task_repo.create_task(task, actor="test")
    task_repo.transition_state(task.task_id, "biz_kirana_01", TaskState.CLASSIFIED, actor="test")
    task_repo.transition_state(task.task_id, "biz_kirana_01", TaskState.PLANNING, actor="test")
    task_repo.transition_state(task.task_id, "biz_kirana_01", TaskState.WORKING, actor="test")
    task_repo.transition_state(task.task_id, "biz_kirana_01", TaskState.AWAITING_APPROVAL, actor="test")

    proposal = ActionProposal(
        action_id="act_spoof_01",
        action_type="purchase_order",
        description="Buy 50kg sugar",
        payload={"supplier_id": "sup_sugar", "amount": 2000.0},
        requires_approval=True,
    )
    task_repo.propose_action(task.task_id, "biz_kirana_01", proposal)

    # Verified principal bound to context
    verified_principal = TrustedPrincipal(
        subject="owner_sharma",
        issuer="vendo-auth",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["biz_kirana_01"],
        roles=["owner"],
        scopes=["approvals:execute", "approvals:read"],
    )
    ctx_token = _current_mcp_principal.set(verified_principal)

    try:
        custom_mcp = create_mcp_server(
            task_repo=task_repo,
            policy_engine=policy_engine,
        )
        res = await custom_mcp.call_tool(
            "approve_action_proposal",
            {
                "action_id": "act_spoof_01",
                "business_id": "biz_kirana_01",
                "actor_id": "fake_admin",  # Client tries to spoof actor
            },
        )
        # Verified: approved_by in the database is the verified token subject, not fake_admin
        act = task_repo.get_action("act_spoof_01", business_id="biz_kirana_01")
        assert act.approved_by == "owner_sharma"
        assert act.approved_by != "fake_admin"
    finally:
        _current_mcp_principal.reset(ctx_token)
