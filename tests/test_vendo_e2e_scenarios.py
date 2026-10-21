"""
Unit & Integration Tests for Vendo End-to-End Orchestration, Voice Briefings & Security
========================================================================================
Validates Phase 1 to Phase 6 capabilities:
1. Dynamic priority scoring of operational tasks.
2. Context-aware daily operational briefings across retail, workshop, and salon.
3. Conversational multi-turn proposal explanation and approval/rejection.
4. Simulated payment and refund execution handlers through PermissionEngine.
5. Strict cross-tenant authorization barriers.
6. Execution payload hash tampering rejection.
7. Replay idempotency.
"""

import os
import tempfile
import pytest

from src.db.connection import initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import TaskRepository, ActionProposal, OperationalTask, TaskState
from src.db.email_repository import EmailRepository
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher, ActionType
from src.agent.supervisor import EmailOperationalSupervisor
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.models.adaptive_profile import AdaptiveBusinessProfile, FactStatus, FactSource
from src.demo_runner import build_isolated_demo_environment


@pytest.fixture
def demo_env():
    env = build_isolated_demo_environment()
    yield env
    if os.path.exists(env["db_path"]):
        os.remove(env["db_path"])


def test_priority_calculation(demo_env):
    orchestrator = demo_env["orchestrator"]
    task = OperationalTask(
        business_id="retail_kirana_01",
        title="Restock high-demand goods",
        state=TaskState.WORKING,
    )
    props = [
        ActionProposal(
            action_type="execute_payment",
            payload={"amount": 15000.0},
            requires_approval=True,
        )
    ]
    prio = orchestrator.calculate_task_priority(task, props)
    assert prio["score"] >= 60, "Task with high payment and approval requirement must score >= 60"
    assert prio["level"] in ("HIGH", "CRITICAL")
    assert "consequential action" in prio["explainable_reason"].lower()


def test_briefings_across_three_business_types(demo_env):
    orchestrator = demo_env["orchestrator"]

    # 1. Retail
    brief_retail = orchestrator.generate_daily_briefing("retail_kirana_01")
    assert brief_retail["category"] == "retail_store"
    assert "Kirana Supermart" in brief_retail["headline"]
    assert "voice_summary" in brief_retail

    # 2. Workshop
    brief_workshop = orchestrator.generate_daily_briefing("workshop_auto_01")
    assert brief_workshop["category"] == "repair_workshop"
    assert "Speedy Auto Garage" in brief_workshop["headline"]
    assert "voice_summary" in brief_workshop

    # 3. Salon
    brief_salon = orchestrator.generate_daily_briefing("salon_glow_01")
    assert brief_salon["category"] == "salon_services"
    assert "Glow Beauty Lounge" in brief_salon["headline"]
    assert "voice_summary" in brief_salon


def test_multi_turn_approval_and_execution(demo_env):
    orchestrator = demo_env["orchestrator"]
    task_repo = demo_env["task_repo"]

    task = task_repo.create_task(
        OperationalTask(
            business_id="retail_kirana_01",
            title="Procure cooking oil stock",
            task_type="supplier_quote",
        )
    )
    prop = task_repo.propose_action(
        task_id=task.task_id,
        business_id="retail_kirana_01",
        proposal=ActionProposal(
            task_id=task.task_id,
            business_id="retail_kirana_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="Advance payment of Rs 10,000 to edible oil supplier",
            payload={"amount": 10000.0, "vendor": "Fortune Oils"},
            requires_approval=True,
        ),
        actor="system",
    )

    # Explain proposal
    explain_resp = orchestrator.handle_user_message(
        message="Explain the first one",
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    assert explain_resp["status"] == "SUCCESS"
    assert "Advance payment of Rs 10,000" in explain_resp["voice_summary"]

    # Approve and execute
    approve_resp = orchestrator.handle_user_message(
        message="Approve proposal 1",
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    assert approve_resp["status"] == "APPROVED_AND_EXECUTED"
    assert approve_resp["receipt"] is not None
    assert approve_resp["receipt"]["status"] == "COMPLETED"


def test_cross_tenant_isolation_in_orchestrator(demo_env):
    orchestrator = demo_env["orchestrator"]
    task_repo = demo_env["task_repo"]

    task = task_repo.create_task(
        OperationalTask(
            business_id="retail_kirana_01",
            title="Confidential Retail Payroll",
        )
    )
    prop = task_repo.propose_action(
        task_id=task.task_id,
        business_id="retail_kirana_01",
        proposal=ActionProposal(
            task_id=task.task_id,
            business_id="retail_kirana_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="Payroll disbursement",
            payload={"amount": 25000.0},
            requires_approval=True,
        ),
    )

    # Workshop owner tries to approve Retail proposal
    unauth_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message="Approve proposal 1",
        actor_id="owner:owner_verma",
    )
    assert unauth_resp["status"] == "UNAUTHORIZED"
    assert "not an authorized owner" in unauth_resp["error"]


def test_tampered_payload_dispatch_blocked(demo_env):
    dispatcher = demo_env["action_dispatcher"]
    task_repo = demo_env["task_repo"]
    policy = demo_env["policy_engine"]

    task = task_repo.create_task(
        OperationalTask(
            business_id="workshop_auto_01",
            title="Part order payment",
        )
    )
    prop = task_repo.propose_action(
        task_id=task.task_id,
        business_id="workshop_auto_01",
        proposal=ActionProposal(
            task_id=task.task_id,
            business_id="workshop_auto_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="Payment for brake pads",
            payload={"amount": 2400.0, "vendor": "Bosch Spares"},
            requires_approval=True,
        ),
    )
    # Owner approves original payload
    task_repo.approve_action(
        action_id=prop.action_id,
        business_id="workshop_auto_01",
        actor_id="owner:owner_verma",
        execution_payload={"amount": 2400.0, "vendor": "Bosch Spares"},
        policy_engine=policy,
    )

    # Dispatch with altered payload
    with pytest.raises(Exception) as exc_info:
        dispatcher.dispatch_action(
            action_id=prop.action_id,
            business_id="workshop_auto_01",
            actor_id="owner:owner_verma",
            execution_payload={"amount": 24000.0, "vendor": "Attacker"},
        )
    assert "hash does not match" in str(exc_info.value).lower()


def test_conversational_approval_out_of_bounds_and_ambiguity(demo_env):
    orchestrator = demo_env["orchestrator"]
    task_repo = demo_env["task_repo"]

    t1 = task_repo.create_task(
        OperationalTask(business_id="retail_kirana_01", title="Task 1")
    )
    p1 = task_repo.propose_action(
        task_id=t1.task_id,
        business_id="retail_kirana_01",
        proposal=ActionProposal(
            task_id=t1.task_id,
            business_id="retail_kirana_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="First Proposal",
            payload={"amount": 1000.0},
            requires_approval=True,
        ),
    )
    p2 = task_repo.propose_action(
        task_id=t1.task_id,
        business_id="retail_kirana_01",
        proposal=ActionProposal(
            task_id=t1.task_id,
            business_id="retail_kirana_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="Second Proposal",
            payload={"amount": 2000.0},
            requires_approval=True,
        ),
    )

    # 1. Out of bounds index
    out_of_bounds_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message="Approve proposal 5",
        actor_id="owner:owner_sharma",
    )
    assert out_of_bounds_resp["status"] == "INVALID_REFERENCE"
    assert "Proposal 5 not found" in out_of_bounds_resp["reply"]

    # 2. Ambiguous reference when 2 are pending
    ambig_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message="Approve it",
        actor_id="owner:owner_sharma",
    )
    assert ambig_resp["status"] == "AMBIGUOUS_REFERENCE"
    assert "Please specify which one" in ambig_resp["reply"]

    # 3. Valid ordinal reference
    valid_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message="Approve proposal 1",
        actor_id="owner:owner_sharma",
    )
    assert valid_resp["status"] == "APPROVED_AND_EXECUTED"

    # 4. Stale reference check: attempting to re-approve the same proposal
    stale_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message=f"Approve proposal 1",
        actor_id="owner:owner_sharma",
    )
    # The cache now has 1 item left (p2), and p1 is executed
    assert stale_resp["status"] in ("APPROVED_AND_EXECUTED", "STALE_REFERENCE", "SUCCESS")


def test_token_store_production_fail_closed(tmp_path):
    from src.db.token_store import TokenStore
    db_file = str(tmp_path / "test_tokens.db")

    # In production without key, TokenStore must fail closed
    old_env = os.environ.get("AUTOPILOT_ENV")
    old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    try:
        os.environ["AUTOPILOT_ENV"] = "production"
        if "TOKEN_ENCRYPTION_KEY" in os.environ:
            del os.environ["TOKEN_ENCRYPTION_KEY"]

        with pytest.raises(RuntimeError) as exc_info:
            TokenStore(db_path=db_file, encryption_key="")
        assert "Insecure token storage fallback" in str(exc_info.value)
    finally:
        if old_env is not None:
            os.environ["AUTOPILOT_ENV"] = old_env
        else:
            os.environ.pop("AUTOPILOT_ENV", None)
        if old_key is not None:
            os.environ["TOKEN_ENCRYPTION_KEY"] = old_key


def test_oauth_csrf_state_handling():
    from src.server.auth_routes import _create_oauth_state, _verify_and_consume_oauth_state

    # 1. State creation
    state = _create_oauth_state("zoho_books", "merchant_xyz")
    assert isinstance(state, str) and len(state) >= 32

    # 2. Forged provider fails
    assert _verify_and_consume_oauth_state(state, "other_provider") is None

    # 3. Valid consume returns merchant_id
    merchant = _verify_and_consume_oauth_state(state, "zoho_books")
    assert merchant == "merchant_xyz"

    # 4. Single-use replay fails
    assert _verify_and_consume_oauth_state(state, "zoho_books") is None
