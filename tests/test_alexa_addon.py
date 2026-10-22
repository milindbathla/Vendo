"""
Tests for Alexa+ MCP Add-on Compatibility & Multi-Turn Workflows
================================================================
Validates:
- RFC 8414 Authorization Server Metadata (/.well-known/oauth-authorization-server)
- RFC 9728 Protected Resource Metadata (/.well-known/oauth-protected-resource)
- RFC 9207 Issuer Identification (iss parameter in /oauth/authorize callback)
- OAuth 2.1 PKCE Account Linking Flow (/oauth/authorize -> /oauth/token exchange)
- Scenario A: Business Briefing ("What's happening in my business today?")
- Scenario B: Pending Approvals & Ordinal Follow-up ("Which approvals need attention?", "Explain the second one")
- Scenario C: Authenticated Proposal Approval ("Approve that proposal")
- Scenario D: Cross-Tenant Isolation Defense (impostor denied without data leakage)
"""
import os
import tempfile
import urllib.parse
from typing import Generator
import pytest
from starlette.testclient import TestClient

from src.models.principal import TrustedPrincipal
from src.security.auth_service import (
    create_access_token,
    compute_code_challenge_s256,
)
from src.db.connection import initialize_database, seed_business_state
from src.decision.approval_service import PurchaseApprovalService
from src.db.state_repository import BusinessStateRepository
from src.db.task_repository import TaskRepository, OperationalTask, ActionProposal, TaskState
from src.db.session_repository import SessionRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.email_repository import EmailRepository
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher
from src.agent.supervisor import EmailOperationalSupervisor
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.server.mcp_auth import _current_mcp_principal
import src.server.web_app as web_app
from src.server.web_app import app


@pytest.fixture
def alexa_env(tmp_path, monkeypatch):
    """Provides a fully wired, isolated environment for Alexa+ testing."""
    temp_db = str(tmp_path / "test_alexa_addon.sqlite3")
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

    return {
        "db_path": temp_db,
        "task_repo": task_repo,
        "session_repo": session_repo,
        "profile_repo": profile_repo,
        "policy_engine": policy_engine,
        "orchestrator": orch,
        "client": TestClient(app),
    }


# ── 1. OAuth Metadata & Discovery Endpoints ────────────────────────────────────

def test_oauth_authorization_server_metadata(alexa_env):
    """RFC 8414 metadata endpoint must advertise endpoints, code response_type, S256, and refresh_token."""
    client = alexa_env["client"]
    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 200
    meta = res.json()
    assert meta["issuer"] in ("vendo-auth", "http://localhost:8000") or meta["issuer"].startswith("http")
    assert "/oauth/authorize" in meta["authorization_endpoint"]
    assert "/oauth/token" in meta["token_endpoint"]
    assert "/oauth/revoke" in meta["revocation_endpoint"]
    assert "code" in meta["response_types_supported"]
    assert "authorization_code" in meta["grant_types_supported"]
    assert "refresh_token" in meta["grant_types_supported"]
    assert "S256" in meta["code_challenge_methods_supported"]
    assert "approvals:execute" in meta["scopes_supported"]
    assert meta.get("authorization_response_iss_parameter_supported") is True


def test_oauth_protected_resource_metadata(alexa_env):
    """RFC 9728 metadata endpoint must advertise canonical resource indicator and authorization servers."""
    client = alexa_env["client"]
    res = client.get("/.well-known/oauth-protected-resource")
    assert res.status_code == 200
    meta = res.json()
    assert "/mcp" in meta["resource"]
    assert isinstance(meta["authorization_servers"], list) and len(meta["authorization_servers"]) > 0
    assert "business:read" in meta["scopes_supported"]
    assert "header" in meta["bearer_methods_supported"]


# ── 2. OAuth 2.1 PKCE Account Linking Flow ────────────────────────────────────

def test_oauth_account_linking_pkce_flow(alexa_env):
    """
    Simulates complete Alexa+ Account Linking handshake:
    1. Alexa redirects user to /oauth/authorize with S256 challenge.
    2. Vendo redirects back to Alexa redirect_uri with single-use code.
    3. Alexa backend exchanges code + verifier at /oauth/token.
    4. Vendo issues JWT Bearer access token.
    5. Replaying code fails.
    """
    client = alexa_env["client"]
    verifier = "alexa_secure_pkce_verifier_string_min_43_chars_long!!"
    challenge = compute_code_challenge_s256(verifier)

    auth_params = {
        "client_id": "alexa_skill_vendo_01",
        "redirect_uri": "https://alexa.amazon.com/api/skills/redirect",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "alexa_session_state_xyz",
        "scope": "business:read business:write approvals:read approvals:execute",
        "owner_id": "owner_sharma",
        "business_id": "biz_kirana_01",
    }

    # Step 1 & 2: Authorize request -> 302 Redirect
    auth_res = client.get("/oauth/authorize", params=auth_params, follow_redirects=False)
    assert auth_res.status_code == 302
    redirect_location = auth_res.headers["location"]
    assert redirect_location.startswith("https://alexa.amazon.com/api/skills/redirect")

    # Extract code and RFC 9207 iss from query params
    parsed = urllib.parse.urlparse(redirect_location)
    query = urllib.parse.parse_qs(parsed.query)
    code = query["code"][0]
    assert query["state"][0] == "alexa_session_state_xyz"
    assert "iss" in query  # RFC 9207 Authorization Server Issuer Identification
    assert code.startswith("authcode_")

    # Step 3 & 4: Token exchange with code_verifier
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://alexa.amazon.com/api/skills/redirect",
        "client_id": "alexa_skill_vendo_01",
        "code_verifier": verifier,
    }
    token_res = client.post("/oauth/token", json=token_payload)
    assert token_res.status_code == 200
    token_data = token_res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "Bearer"
    assert token_data["subject"] == "owner_sharma"
    assert "biz_kirana_01" in token_data["business_ids"]

    # Step 5: Code replay attack fails
    replay_res = client.post("/oauth/token", json=token_payload)
    assert replay_res.status_code == 400

    # Step 6: Successful Refresh Token grant with rotation
    refresh_payload = {
        "grant_type": "refresh_token",
        "refresh_token": token_data["refresh_token"],
        "client_id": "alexa_skill_vendo_01",
    }
    refresh_res = client.post("/oauth/token", json=refresh_payload)
    assert refresh_res.status_code == 200
    refreshed_data = refresh_res.json()
    assert "access_token" in refreshed_data
    assert "refresh_token" in refreshed_data
    assert refreshed_data["refresh_token"] != token_data["refresh_token"]  # Rotated!

    # Step 7: Replay attack on consumed refresh token
    replay_refresh_res = client.post("/oauth/token", json=refresh_payload)
    assert replay_refresh_res.status_code == 400

    # Step 8: Even the newly rotated token is now revoked due to replay detection
    compromised_payload = {
        "grant_type": "refresh_token",
        "refresh_token": refreshed_data["refresh_token"],
        "client_id": "alexa_skill_vendo_01",
    }
    revoked_family_res = client.post("/oauth/token", json=compromised_payload)
    assert revoked_family_res.status_code == 400


# ── 3. Multi-Turn Alexa+ Workflows (Scenarios A, B, C, D) ──────────────────────

def test_scenario_a_daily_business_briefing(alexa_env):
    """
    Scenario A:
    Owner: "Vendo, what's happening in my business today?"
    Vendo provides a personalized business briefing with a concise voice summary.
    """
    client = alexa_env["client"]
    token = create_access_token(
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        scopes=["business:read", "tasks:read"],
    )

    res = client.get(
        "/api/orchestrator/briefing",
        headers={"Authorization": f"Bearer {token}"},
        params={"business_id": "biz_kirana_01"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "voice_summary" in data or "reply" in data
    assert "pending_approvals_count" in data


def test_scenario_b_and_c_pending_approvals_and_ordinal_approval(alexa_env):
    """
    Scenario B & C:
    Owner: "Which approvals need my attention?" -> lists pending approvals.
    Owner: "Explain the second one." -> resolves proposal #2 and explains it.
    Owner: "Approve it." -> verifies session, resolves proposal #2, executes approval via policy engine.
    """
    client = alexa_env["client"]
    task_repo: TaskRepository = alexa_env["task_repo"]
    business_id = "biz_kirana_01"

    # Seed two pending tasks with action proposals
    t1 = OperationalTask(
        task_id="task_seed_01",
        business_id=business_id,
        title="Restock Atta & Rice",
        task_type="supplier_order",
    )
    task_repo.create_task(t1, actor="inventory_agent")
    task_repo.transition_state(t1.task_id, business_id, TaskState.CLASSIFIED, actor="test")
    task_repo.transition_state(t1.task_id, business_id, TaskState.PLANNING, actor="test")
    task_repo.transition_state(t1.task_id, business_id, TaskState.WORKING, actor="test")
    task_repo.transition_state(t1.task_id, business_id, TaskState.AWAITING_APPROVAL, actor="test")

    p1 = ActionProposal(
        action_id="act_seed_01",
        action_type="create_purchase_order",
        description="Purchase 100kg Aashirvaad Atta from Kanpur Mills",
        payload={"supplier_id": "sup_kanpur", "item": "Atta", "amount": 4200.0},
        requires_approval=True,
    )
    task_repo.propose_action(t1.task_id, business_id, p1)

    t2 = OperationalTask(
        task_id="task_seed_02",
        business_id=business_id,
        title="Restock Mustard Oil",
        task_type="supplier_order",
    )
    task_repo.create_task(t2, actor="inventory_agent")
    task_repo.transition_state(t2.task_id, business_id, TaskState.CLASSIFIED, actor="test")
    task_repo.transition_state(t2.task_id, business_id, TaskState.PLANNING, actor="test")
    task_repo.transition_state(t2.task_id, business_id, TaskState.WORKING, actor="test")
    task_repo.transition_state(t2.task_id, business_id, TaskState.AWAITING_APPROVAL, actor="test")

    p2 = ActionProposal(
        action_id="act_seed_02",
        action_type="create_purchase_order",
        description="Purchase 50L Fortune Mustard Oil from Lucknow Wholesale",
        payload={"supplier_id": "sup_lucknow", "item": "Mustard Oil", "amount": 6500.0},
        requires_approval=True,
    )
    task_repo.propose_action(t2.task_id, business_id, p2)

    # Owner token
    token = create_access_token(
        subject="owner_sharma",
        business_ids=[business_id],
        scopes=["business:read", "approvals:read", "approvals:execute"],
    )

    # Turn 1: "Which approvals need my attention?"
    turn1_res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_id": business_id,
            "message": "Which approvals need my attention?",
        },
    )
    assert turn1_res.status_code == 200
    t1_data = turn1_res.json()
    session_id = t1_data.get("session_id")
    assert session_id is not None

    # Turn 2: "Explain the second one."
    turn2_res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_id": business_id,
            "message": "Explain the second one.",
            "session_id": session_id,
        },
    )
    assert turn2_res.status_code == 200
    t2_data = turn2_res.json()
    reply = t2_data.get("reply", "")
    # Should reference proposal #2 (Mustard Oil / Lucknow Wholesale)
    assert "oil" in reply.lower() or "lucknow" in reply.lower() or "act_seed_02" in reply.lower() or "second" in reply.lower()

    # Turn 3 (Scenario C): "Approve it."
    turn3_res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_id": business_id,
            "message": "Approve it.",
            "session_id": session_id,
        },
    )
    assert turn3_res.status_code == 200
    t3_data = turn3_res.json()
    assert t3_data.get("approval_status") == "APPROVED" or "approved" in t3_data.get("reply", "").lower()

    # Verify persistent state: proposal #2 is approved
    approved_action = task_repo.get_action("act_seed_02", business_id=business_id)
    assert approved_action is not None
    assert approved_action.approved_by == "owner_sharma"

    # Proposal #1 remains PENDING
    unapproved_action = task_repo.get_action("act_seed_01", business_id=business_id)
    assert unapproved_action is not None
    assert unapproved_action.approved_by is None


def test_scenario_d_cross_tenant_impostor_denied(alexa_env):
    """
    Scenario D:
    A different business owner attempts to query or approve another business's proposal.
    Must deny access with 403 Forbidden without leaking any private business info.
    """
    client = alexa_env["client"]

    # Impostor token: only authorized for biz_other
    impostor_token = create_access_token(
        subject="impostor_vikram",
        business_ids=["biz_garage_01"],
        scopes=["business:read", "approvals:execute"],
    )

    # Impostor attempts to query biz_kirana_01
    res = client.post(
        "/api/orchestrator/query",
        headers={"Authorization": f"Bearer {impostor_token}"},
        json={
            "business_id": "biz_kirana_01",
            "message": "Show me pending approvals",
        },
    )
    assert res.status_code == 403
    detail = res.json().get("detail", "").lower()
    assert "not an authorized owner" in detail or "forbidden" in detail
    assert "atta" not in str(res.json()).lower()
