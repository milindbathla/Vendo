"""
Tests for Secure Remote MCP Server (Streamable HTTP Transport)
==============================================================
Validates:
- Streamable HTTP transport compliance (/mcp)
- RFC 6750 Bearer token authentication at the MCP transport boundary
- Fail-closed behavior in production mode (AUTOPILOT_ENV=production)
- Actor spoofing defense (client-supplied actor_id ignored/overridden by verified token subject)
- Strict cross-tenant access control across all operational tools
- OAuth scope enforcement on sensitive tools
- Latency measurement validating the <500ms target
"""
import os
import tempfile
import time
import json
from typing import Generator
import pytest
from starlette.testclient import TestClient

from src.models.principal import TrustedPrincipal
from src.security.auth_service import create_access_token
from src.db.connection import initialize_database, seed_business_state
from src.decision.approval_service import PurchaseApprovalService
from src.db.state_repository import BusinessStateRepository
from src.db.task_repository import TaskRepository, OperationalTask, ActionProposal, TaskState
from src.server.mcp_auth import _current_mcp_principal, get_current_mcp_principal
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.email_repository import EmailRepository
from src.db.session_repository import SessionRepository
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher
from src.agent.supervisor import EmailOperationalSupervisor
from src.server.mcp_server import create_mcp_server
import src.server.web_app as web_app
from src.server.web_app import app


def _unwrap_result(res):
    """Unwraps FastMCP call_tool results across dict and list return types."""
    if isinstance(res, tuple) and len(res) == 2:
        return res[1].get("result", res[1])
    elif isinstance(res, list) and len(res) > 0 and hasattr(res[0], "text"):
        try:
            return json.loads(res[0].text)
        except Exception:
            return res[0].text
    return res


@pytest.fixture
def isolated_mcp_db(tmp_path, monkeypatch):
    """Provides a fresh isolated database and configures web_app / mcp_server."""
    temp_db = str(tmp_path / "test_remote_mcp.sqlite3")
    initialize_database(temp_db)
    seed_business_state(temp_db)
    task_repo = TaskRepository(temp_db)
    approvals_svc = PurchaseApprovalService(db_path=temp_db)
    session_repo = SessionRepository(temp_db)
    profile_repo = AdaptiveProfileRepository(temp_db)
    email_repo = EmailRepository(temp_db)
    policy_engine = PermissionEngine()
    policy_engine.set_authorized_owners("home_tiffin", ["real_owner_tiffin", "owner:real_owner_tiffin"])
    policy_engine.set_authorized_owners("biz_kirana_01", ["owner_kirana", "owner:owner_kirana"])
    action_dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)
    supervisor = EmailOperationalSupervisor(
        email_repo=email_repo,
        task_repo=task_repo,
        profile_repo=profile_repo,
        policy_engine=policy_engine,
    )
    custom_mcp_server = create_mcp_server(
        approval_service=approvals_svc,
        profile_repo=profile_repo,
        task_repo=task_repo,
        email_repo=email_repo,
        policy_engine=policy_engine,
        action_dispatcher=action_dispatcher,
        supervisor=supervisor,
        session_repo=session_repo,
    )

    monkeypatch.setattr(web_app, "_DB_PATH", temp_db)
    monkeypatch.setattr(web_app, "task_repo", task_repo)
    monkeypatch.setattr(web_app, "approvals_service", approvals_svc)
    monkeypatch.setattr(web_app, "session_repo", session_repo)
    monkeypatch.setenv("DATABASE_PATH", temp_db)
    monkeypatch.setenv("VENDO_JWT_SECRET", "production-secret-key-32-chars-long-test-entropy!!")
    return temp_db, task_repo, custom_mcp_server


# ── Transport & Authentication Boundary Tests ─────────────────────────────────

def test_remote_mcp_unauthenticated_fails_closed_in_production(isolated_mcp_db, monkeypatch):
    """In production mode, unauthenticated HTTP requests to /mcp must return 401 Unauthorized."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    res = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert res.status_code == 401
    # Alexa+ MCP Toolkit requirement: unauthenticated discovery must NOT return WWW-Authenticate header
    assert "WWW-Authenticate" not in res.headers
    data = res.json()
    assert data.get("error") == "unauthorized"


def test_remote_mcp_expired_token_rejected(isolated_mcp_db, monkeypatch):
    """Expired Bearer token on /mcp returns 401 with error=invalid_token."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    expired_token = create_access_token(
        subject="owner_sharma",
        business_ids=["biz_kirana_01"],
        expires_in_seconds=-10,
    )

    res = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert res.status_code == 401
    assert "invalid_token" in res.headers.get("WWW-Authenticate", "")


def test_remote_mcp_malformed_token_rejected(isolated_mcp_db, monkeypatch):
    """Malformed Bearer token on /mcp returns 401."""
    monkeypatch.setenv("AUTOPILOT_ENV", "production")
    client = TestClient(app)

    res = client.post(
        "/mcp",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert res.status_code == 401


# ── Tool-Level Authorization & Actor Spoofing Defenses ───────────────────────

@pytest.mark.anyio
async def test_tool_actor_spoofing_prevented_by_context_principal(isolated_mcp_db):
    """
    Client-supplied actor_id must NEVER override the server-verified principal.
    The verified principal's subject is used for all business checks.
    """
    _temp_db, task_repo, custom_mcp_server = isolated_mcp_db

    # Create a task and proposal for home_tiffin
    task = OperationalTask(
        task_id="task_remote_01",
        business_id="home_tiffin",
        title="Restock packaging",
        task_type="supplier_order",
    )
    task_repo.create_task(task, actor="email_ingestion")
    task_repo.transition_state("task_remote_01", "home_tiffin", TaskState.CLASSIFIED, actor="test")
    task_repo.transition_state("task_remote_01", "home_tiffin", TaskState.PLANNING, actor="test")
    task_repo.transition_state("task_remote_01", "home_tiffin", TaskState.WORKING, actor="test")
    task_repo.transition_state("task_remote_01", "home_tiffin", TaskState.AWAITING_APPROVAL, actor="test")

    prop = ActionProposal(
        action_id="act_remote_01",
        action_type="purchase_order",
        description="Order 50 meal boxes",
        payload={"supplier_id": "sup_boxes", "amount": 1200.0},
        requires_approval=True,
    )
    action = task_repo.propose_action(task.task_id, "home_tiffin", prop)

    # Set verified principal in context (owner of home_tiffin)
    verified_principal = TrustedPrincipal(
        subject="real_owner_tiffin",
        issuer="vendo-auth",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["home_tiffin"],
        roles=["owner"],
        scopes=["approvals:execute", "approvals:read"],
    )
    token = _current_mcp_principal.set(verified_principal)

    try:
        # Client tries to pass a spoofed actor_id="impostor_admin"
        res = await custom_mcp_server.call_tool(
            "approve_action_proposal",
            {
                "action_id": action.action_id,
                "business_id": "home_tiffin",
                "actor_id": "impostor_admin",
            },
        )
        result = _unwrap_result(res)
        assert result["status"] == "APPROVED"
        # The approved record must record the REAL authenticated owner, not the spoofed string
        assert result["action"]["approved_by"] == "real_owner_tiffin"
    finally:
        _current_mcp_principal.reset(token)


@pytest.mark.anyio
async def test_tool_cross_tenant_access_denied(isolated_mcp_db):
    """
    An authenticated owner for Business A cannot invoke tools for Business B.
    Must return UNAUTHORIZED without leaking private business data.
    """
    _temp_db, task_repo, custom_mcp_server = isolated_mcp_db

    # Principal only has membership for biz_kirana
    kirana_principal = TrustedPrincipal(
        subject="owner_kirana",
        issuer="vendo-auth",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["biz_kirana_01"],
        roles=["owner"],
        scopes=["approvals:read", "approvals:execute", "tasks:read"],
    )
    token = _current_mcp_principal.set(kirana_principal)

    try:
        # Kirana owner attempts to access home_tiffin's operational tasks
        res = await custom_mcp_server.call_tool(
            "list_operational_tasks",
            {"business_id": "home_tiffin"},
        )
        result = _unwrap_result(res)
        assert isinstance(result, dict)
        assert result.get("status") == "UNAUTHORIZED"
        assert "not authorized for business" in result.get("error", "")

        # Kirana owner attempts to get home_tiffin's daily briefing
        briefing_res = await custom_mcp_server.call_tool(
            "get_daily_operational_briefing",
            {"business_id": "home_tiffin"},
        )
        b_result = _unwrap_result(briefing_res)
        assert isinstance(b_result, dict)
        assert b_result.get("status") == "UNAUTHORIZED"
    finally:
        _current_mcp_principal.reset(token)


@pytest.mark.anyio
async def test_tool_scope_enforcement(isolated_mcp_db):
    """
    Tools must reject callers whose tokens lack the required OAuth scope.
    """
    _temp_db, task_repo, custom_mcp_server = isolated_mcp_db

    # Principal has read-only scope, lacks approvals:execute
    readonly_principal = TrustedPrincipal(
        subject="analyst_bob",
        issuer="vendo-auth",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["home_tiffin"],
        roles=["analyst"],
        scopes=["business:read", "tasks:read"],  # No approvals:execute
    )
    token = _current_mcp_principal.set(readonly_principal)

    try:
        res = await custom_mcp_server.call_tool(
            "approve_action_proposal",
            {
                "action_id": "act_dummy",
                "business_id": "home_tiffin",
            },
        )
        result = _unwrap_result(res)
        assert isinstance(result, dict)
        assert result.get("status") == "UNAUTHORIZED"
        assert "required scope" in result.get("error", "")
    finally:
        _current_mcp_principal.reset(token)


# ── Latency & Performance Verification (<500ms target) ─────────────────────────

@pytest.mark.anyio
async def test_mcp_tool_execution_latency_target(isolated_mcp_db):
    """
    Measures execution time of key Alexa+ tools to verify compliance with
    Amazon's recommended <500ms latency target.
    """
    _temp_db, task_repo, custom_mcp_server = isolated_mcp_db

    principal = TrustedPrincipal(
        subject="perf_owner",
        issuer="vendo-auth",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["home_tiffin"],
        roles=["owner"],
        scopes=["business:read", "tasks:read"],
    )
    token = _current_mcp_principal.set(principal)

    try:
        # Measure get_daily_operational_briefing
        t0 = time.perf_counter()
        res = await custom_mcp_server.call_tool(
            "get_daily_operational_briefing",
            {"business_id": "home_tiffin"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        result0 = _unwrap_result(res)
        assert result0["status"] in ("SUCCESS", "READY", "OK") or "business_id" in result0
        assert elapsed_ms < 500.0, f"Daily briefing tool took {elapsed_ms:.1f}ms (>500ms target)"

        # Measure query_business_orchestrator
        t1 = time.perf_counter()
        q_res = await custom_mcp_server.call_tool(
            "query_business_orchestrator",
            {"business_id": "home_tiffin", "message": "Pending approvals summary"},
        )
        q_elapsed_ms = (time.perf_counter() - t1) * 1000.0
        assert q_elapsed_ms < 500.0, f"Query orchestrator tool took {q_elapsed_ms:.1f}ms (>500ms target)"

        # Measure list_pending_approvals
        t2 = time.perf_counter()
        p_res = await custom_mcp_server.call_tool(
            "list_pending_approvals",
            {"business_id": "home_tiffin"},
        )
        p_elapsed_ms = (time.perf_counter() - t2) * 1000.0
        assert p_elapsed_ms < 500.0, f"List approvals tool took {p_elapsed_ms:.1f}ms (>500ms target)"

    finally:
        _current_mcp_principal.reset(token)
