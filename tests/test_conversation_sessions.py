"""
Tests for Persistent Conversation Sessions & Ordinal Reference Safety
=====================================================================
Validates durability across server restarts, multi-turn context retention,
strict tenant and identity isolation, expiry/revocation enforcement,
and deterministic approval reference resolution.
"""
import os
import sqlite3
import tempfile
import time
from typing import Generator
import pytest

from src.db.connection import initialize_database, get_connection
from src.db.session_repository import (
    SessionRepository,
    SessionNotFoundError,
    SessionExpiredError,
    SessionRevokedError,
    SessionAccessDeniedError,
)
from src.models.session import ConversationSession, ConversationTurn
from src.models.adaptive_profile import AdaptiveBusinessProfile
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import (
    TaskRepository,
    ActionProposal,
    OperationalTask,
    TaskState,
    compute_payload_hash,
)
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher
from src.agent.orchestrator import AdaptiveBusinessOrchestrator


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Provides a fresh isolated disposable SQLite database file."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    initialize_database(path)
    yield path
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def test_session_creation_and_retrieval(temp_db_path: str):
    """Verifies creating, retrieving, and persisting sessions."""
    repo = SessionRepository(db_path=temp_db_path)
    session = repo.create_session(
        business_id="biz_kirana_01",
        owner_id="owner_sharma",
        subject="sub_sharma_123",
        ttl_seconds=3600,
        metadata={"channel": "alexa_plus"},
    )
    assert session.session_id.startswith("sess_")
    assert session.business_id == "biz_kirana_01"
    assert session.owner_id == "owner_sharma"
    assert session.subject == "sub_sharma_123"
    assert session.is_active is True
    assert session.is_expired is False

    # Retrieve session
    loaded = repo.get_session(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.business_id == "biz_kirana_01"
    assert loaded.metadata.get("channel") == "alexa_plus"


def test_session_survives_process_restart(temp_db_path: str):
    """
    Simulates a complete process/server restart by destroying repository instances
    and verifying state is fully recovered from disk.
    """
    # 1. First process life: Create session, add turns and proposal references
    repo1 = SessionRepository(db_path=temp_db_path)
    session = repo1.create_session(
        business_id="biz_garage_01",
        owner_id="owner_verma",
    )
    repo1.append_turn(session.session_id, role="user", content="Show me pending approvals")
    repo1.append_turn(session.session_id, role="assistant", content="You have 2 pending approvals.")
    repo1.update_referenced_actions(session.session_id, ["act_procure_parts", "act_notify_client"])

    # Simulate restart: delete repo1 reference
    del repo1

    # 2. Second process life: New repository instance reads same database
    repo2 = SessionRepository(db_path=temp_db_path)
    recovered = repo2.get_session(session.session_id)
    assert recovered is not None
    assert recovered.business_id == "biz_garage_01"
    assert len(recovered.turns) == 2
    assert recovered.turns[0].content == "Show me pending approvals"
    assert recovered.turns[1].content == "You have 2 pending approvals."
    assert recovered.referenced_action_ids == ["act_procure_parts", "act_notify_client"]
    assert recovered.context_version >= 3


def test_session_expiration_enforcement(temp_db_path: str):
    """Verifies that expired sessions are rejected and flagged as EXPIRED."""
    repo = SessionRepository(db_path=temp_db_path)
    # Create session with tiny TTL (0.1 second)
    session = repo.create_session(
        business_id="biz_salon_01",
        owner_id="owner_priya",
        ttl_seconds=0.1,
    )
    time.sleep(0.15)

    loaded = repo.get_session(session.session_id)
    assert loaded is not None
    assert loaded.status == "EXPIRED"
    assert loaded.is_active is False

    with pytest.raises(SessionExpiredError):
        repo.append_turn(session.session_id, role="user", content="Hello?")

    with pytest.raises(SessionExpiredError):
        repo.update_referenced_actions(session.session_id, ["act_1"])


def test_session_revocation_enforcement(temp_db_path: str):
    """Verifies that explicitly revoked sessions immediately block all further interactions."""
    repo = SessionRepository(db_path=temp_db_path)
    session = repo.create_session(
        business_id="biz_retail_01",
        owner_id="owner_gupta",
    )
    assert repo.revoke_session(session.session_id) is True

    revoked = repo.get_session(session.session_id)
    assert revoked is not None
    assert revoked.status == "REVOKED"
    assert revoked.is_active is False

    with pytest.raises(SessionRevokedError):
        repo.append_turn(session.session_id, role="user", content="Approve order")


def test_cross_tenant_session_isolation(temp_db_path: str):
    """Verifies that a session belonging to Business A cannot be accessed or manipulated by Business B."""
    repo = SessionRepository(db_path=temp_db_path)
    session_a = repo.create_session(
        business_id="biz_alpha",
        owner_id="owner_alpha",
    )

    # Attempting to load session_a with business_id="biz_beta" must fail
    with pytest.raises(SessionAccessDeniedError) as exc_info:
        repo.get_session(session_a.session_id, business_id="biz_beta")
    assert "belongs to business 'biz_alpha', not 'biz_beta'" in str(exc_info.value)


def test_cross_owner_session_isolation(temp_db_path: str):
    """Verifies that a different owner cannot hijack a session belonging to another owner."""
    repo = SessionRepository(db_path=temp_db_path)
    session = repo.create_session(
        business_id="biz_shared",
        owner_id="owner_legitimate",
        subject="sub_legit_456",
    )

    with pytest.raises(SessionAccessDeniedError) as exc_info:
        repo.get_session(session.session_id, owner_id="owner_attacker")
    assert "belongs to owner 'owner_legitimate'" in str(exc_info.value)


def test_parallel_sessions_remain_isolated(temp_db_path: str):
    """Two simultaneous sessions for the same business must maintain separate proposal references and history."""
    repo = SessionRepository(db_path=temp_db_path)
    s1 = repo.create_session(business_id="biz_store", owner_id="owner_1")
    s2 = repo.create_session(business_id="biz_store", owner_id="owner_1")

    repo.update_referenced_actions(s1.session_id, ["act_proposal_A", "act_proposal_B"])
    repo.update_referenced_actions(s2.session_id, ["act_proposal_X", "act_proposal_Y"])

    loaded1 = repo.get_session(s1.session_id)
    loaded2 = repo.get_session(s2.session_id)

    assert loaded1.referenced_action_ids == ["act_proposal_A", "act_proposal_B"]
    assert loaded2.referenced_action_ids == ["act_proposal_X", "act_proposal_Y"]


def test_orchestrator_multi_turn_approval_with_session(temp_db_path: str):
    """
    End-to-end multi-turn conversational interaction using persistent session:
    1. Briefing / List pending proposals
    2. 'Explain the first one' -> identifies proposal 1
    3. Simulate server restart
    4. 'Approve it' -> approves the exact proposal from recovered session context.
    """
    profile_repo = AdaptiveProfileRepository(temp_db_path)
    task_repo = TaskRepository(temp_db_path)
    session_repo = SessionRepository(temp_db_path)
    policy_engine = PermissionEngine({"biz_kirana": ["owner:owner_sharma", "owner_sharma"]})
    dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)

    # Seed business profile
    prof = AdaptiveBusinessProfile(
        business_id="biz_kirana",
        display_name="Kirana Supermart",
        category="retail_store",
        onboarding_completed=True,
    )
    profile_repo.save_profile(prof)

    # Seed an operational task and consequential action proposal
    task = OperationalTask(
        task_id="tsk_kirana_order_1",
        business_id="biz_kirana",
        title="Supplier bulk order",
        task_type="supplier_quote",
        state=TaskState.AWAITING_APPROVAL,
    )
    task_repo.create_task(task)
    payload = {"supplier": "Fortune Edible Oils", "amount": 14500.0}
    prop = ActionProposal(
        action_id="act_po_fortune_123",
        task_id=task.task_id,
        business_id="biz_kirana",
        action_type="create_purchase_order",
        description="Create purchase order to Fortune Edible Oils for Rs 14,500.00",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    action1 = task_repo.propose_action(task.task_id, task.business_id, prop)

    # Create persistent session
    session = session_repo.create_session(
        business_id="biz_kirana",
        owner_id="owner_sharma",
    )

    # Orchestrator instance 1
    orch1 = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        task_repo=task_repo,
        policy_engine=policy_engine,
        action_dispatcher=dispatcher,
        session_repo=session_repo,
    )

    # Turn 1: List pending approvals
    t1_resp = orch1.handle_user_message(
        message="Show me pending approvals",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert t1_resp["status"] == "SUCCESS"
    assert t1_resp["pending_count"] == 1
    assert t1_resp["session_id"] == session.session_id

    # Turn 2: Explain the first one
    t2_resp = orch1.handle_user_message(
        message="Explain the first one",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert t2_resp["status"] == "SUCCESS"
    assert t2_resp["action_id"] == action1.action_id
    assert "Fortune Edible Oils" in t2_resp["reply"]

    # --- SIMULATE PROCESS / SERVER RESTART ---
    del orch1
    del session_repo

    # Orchestrator instance 2 (reloading from same DB)
    session_repo_reloaded = SessionRepository(temp_db_path)
    orch2 = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        task_repo=task_repo,
        policy_engine=policy_engine,
        action_dispatcher=dispatcher,
        session_repo=session_repo_reloaded,
    )

    # Turn 3: Approve it across server restart!
    t3_resp = orch2.handle_user_message(
        message="Approve it",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert t3_resp["status"] == "APPROVED_AND_EXECUTED"
    assert t3_resp["action_id"] == action1.action_id
    assert t3_resp["receipt"] is not None

    # Verify session turns and proposal cleanup in DB
    final_session = session_repo_reloaded.get_session(session.session_id)
    assert len(final_session.turns) >= 6  # 3 user turns + 3 assistant responses
    assert action1.action_id not in final_session.referenced_action_ids


def test_stale_proposal_reference_rejected(temp_db_path: str):
    """If a proposal is already approved/rejected, subsequent approval attempts fail closed with STALE_REFERENCE."""
    profile_repo = AdaptiveProfileRepository(temp_db_path)
    task_repo = TaskRepository(temp_db_path)
    session_repo = SessionRepository(temp_db_path)
    policy_engine = PermissionEngine({"biz_kirana": ["owner:owner_sharma", "owner_sharma"]})
    dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)

    prof = AdaptiveBusinessProfile(
        business_id="biz_kirana",
        display_name="Kirana Supermart",
        category="retail_store",
        onboarding_completed=True,
    )
    profile_repo.save_profile(prof)

    task = OperationalTask(
        task_id="tsk_stock_order_2",
        business_id="biz_kirana",
        title="Stock order",
        task_type="supplier_quote",
        state=TaskState.AWAITING_APPROVAL,
    )
    task_repo.create_task(task)
    payload = {"item": "rice", "amount": 5000.0}
    prop = ActionProposal(
        action_id="act_po_rice_2",
        task_id=task.task_id,
        business_id="biz_kirana",
        action_type="create_purchase_order",
        description="PO for Rice",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    action = task_repo.propose_action(task.task_id, task.business_id, prop)

    session = session_repo.create_session(business_id="biz_kirana", owner_id="owner_sharma")
    orch = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        task_repo=task_repo,
        policy_engine=policy_engine,
        action_dispatcher=dispatcher,
        session_repo=session_repo,
    )

    # Seed reference into session
    session_repo.update_referenced_actions(session.session_id, [action.action_id], business_id="biz_kirana")

    # Outside actor rejects the action proposal directly in the database
    task_repo.reject_action(
        action_id=action.action_id,
        business_id="biz_kirana",
        actor_id="owner_sharma",
        rejection_reason="Out of budget",
    )

    # Now user attempts conversational approval
    resp = orch.handle_user_message(
        message="Approve proposal 1",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert resp["status"] in ("STALE_REFERENCE", "NO_PENDING_APPROVALS")


def test_cleanup_expired_sessions(temp_db_path: str):
    """Verifies that expired and revoked sessions are cleaned up properly."""
    repo = SessionRepository(db_path=temp_db_path)
    s1 = repo.create_session("biz_1", "owner_1", ttl_seconds=0.05)
    s2 = repo.create_session("biz_2", "owner_2", ttl_seconds=3600)
    s3 = repo.create_session("biz_3", "owner_3", ttl_seconds=3600)
    repo.revoke_session(s3.session_id)

    time.sleep(0.1)
    cleaned = repo.cleanup_expired_sessions()
    assert cleaned >= 2  # s1 expired, s3 revoked

    assert repo.get_session(s1.session_id) is None
    assert repo.get_session(s3.session_id) is None
    assert repo.get_session(s2.session_id) is not None


def test_ordinal_references_preserve_identity_across_turns(temp_db_path: str):
    """
    Verifies that when 3 proposals exist, ordinal references ("the second one", "proposal 2")
    unambiguously resolve to the exact second proposal, even after server restart.
    """
    profile_repo = AdaptiveProfileRepository(temp_db_path)
    task_repo = TaskRepository(temp_db_path)
    session_repo = SessionRepository(temp_db_path)
    policy_engine = PermissionEngine({"biz_kirana": ["owner:owner_sharma", "owner_sharma"]})
    dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)

    prof = AdaptiveBusinessProfile(
        business_id="biz_kirana",
        display_name="Kirana Supermart",
        category="retail_store",
        onboarding_completed=True,
    )
    profile_repo.save_profile(prof)

    task = OperationalTask(
        task_id="tsk_multi_props",
        business_id="biz_kirana",
        title="Multiple vendor quotes",
        task_type="supplier_quote",
        state=TaskState.AWAITING_APPROVAL,
    )
    task_repo.create_task(task)

    # Create 3 proposals in specific order
    props = []
    for i, name in enumerate(["Flour Atta 50kg", "Mustard Oil 15L", "Sugar 100kg"], 1):
        p = ActionProposal(
            action_id=f"act_item_{i}",
            task_id=task.task_id,
            business_id="biz_kirana",
            action_type="create_purchase_order",
            description=f"PO for {name}",
            payload={"item": name, "amount": 1000.0 * i},
            payload_hash=compute_payload_hash({"item": name, "amount": 1000.0 * i}),
            requires_approval=True,
        )
        task_repo.propose_action(task.task_id, task.business_id, p)
        props.append(p)

    session = session_repo.create_session("biz_kirana", "owner_sharma")
    orch = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        task_repo=task_repo,
        policy_engine=policy_engine,
        action_dispatcher=dispatcher,
        session_repo=session_repo,
    )

    # Turn 1: List proposals -> binds act_item_1, act_item_2, act_item_3 into session
    res_list = orch.handle_user_message(
        message="Show me pending approvals",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert res_list["pending_count"] == 3

    # Turn 2: Explain the second one
    res_exp2 = orch.handle_user_message(
        message="Explain the second one",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert res_exp2["action_id"] == "act_item_2"
    assert "Mustard Oil 15L" in res_exp2["reply"]

    # Turn 3: Approve proposal 2
    res_app2 = orch.handle_user_message(
        message="Approve proposal 2",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert res_app2["status"] == "APPROVED_AND_EXECUTED"
    assert res_app2["action_id"] == "act_item_2"

    # Turn 4: Out-of-range ordinal (e.g. "proposal 10") is rejected
    res_oob = orch.handle_user_message(
        message="Approve proposal 10",
        business_id="biz_kirana",
        actor_id="owner_sharma",
        session_id=session.session_id,
    )
    assert res_oob["status"] == "INVALID_REFERENCE"


def test_concurrent_session_consistency(temp_db_path: str):
    """Verifies that appending turns sequentially or in rapid succession does not corrupt state."""
    repo = SessionRepository(db_path=temp_db_path)
    session = repo.create_session("biz_concur", "owner_concur")

    for i in range(10):
        repo.append_turn(session.session_id, role="user" if i % 2 == 0 else "assistant", content=f"Message {i}")

    reloaded = repo.get_session(session.session_id)
    assert len(reloaded.turns) == 10
    assert reloaded.turns[-1].content == "Message 9"
    assert reloaded.context_version >= 11
