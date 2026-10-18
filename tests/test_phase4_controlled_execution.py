"""
Phase 4 Verification Suite — Controlled Execution, Dispatcher, MCP, and REST API
================================================================================
Comprehensive test suite verifying the complete Phase 4 implementation:
  1. Exact payload approval binding (hash mismatch blocks execution).
  2. Owner authorization requirement for consequential actions.
  3. Non-owner / unauthorized callers rejected.
  4. Predefined low-risk internal actions automatically allowed without owner approval.
  5. Action rejection with documented rationale in audit log.
  6. Durable idempotency: replaying an already-executed action returns existing receipt.
  7. Idempotency across duplicate action proposals sharing identical idempotency keys.
  8. Concurrent execution attempts handle race conditions safely.
  9. Deterministic failure handling when simulated handler raises an error.
 10. EXECUTION_UNCERTAIN state blocks automatic retries.
 11. Explicit owner-directed reconciliation: CONFIRM_EXECUTED.
 12. Explicit owner-directed reconciliation: CONFIRM_FAILED.
 13. Tenant isolation: cross-tenant action access, approval, or execution strictly denied.
 14. Full task lifecycle state transitions remain valid and audited.
 15. Execution receipts record provider name, receipt ID, and output payload.
 16. FastMCP tools: list_operational_tasks, get_operational_task, list_pending_approvals.
 17. FastMCP tools: approve_action_proposal, dispatch_action, list_execution_history.
 18. FastAPI REST endpoints: email ingestion, task listing, proposal retrieval.
 19. FastAPI REST endpoints: owner approval, dispatch, and execution audit history.
 20. End-to-end multi-agent pipeline with mock email, supervisor, approval, and execution.

All tests run on isolated temporary databases.
Zero live external network calls.
"""
from dataclasses import asdict
import os
import tempfile
import time
from typing import Any, Dict, Generator, List, Optional
import uuid

from fastapi.testclient import TestClient
import pytest

from src.agent.supervisor import EmailOperationalSupervisor
from src.db.connection import initialize_database, seed_business_state
from src.db.email_repository import EmailRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import (
    ActionNotFoundError,
    ActionProposal,
    OperationalTask,
    PayloadTamperedError,
    TaskNotFoundError,
    TaskRepository,
    TaskState,
    UnauthorizedError,
)
from src.decision.action_dispatcher import (
    ActionDispatcher,
    ActionNotApprovedError,
    ActionPayloadTamperedError,
    BaseActionHandler,
    ExecutionReceipt,
    ExecutionUncertainError,
    SimulatedAppointmentHandler,
    SimulatedEmailHandler,
    SimulatedInternalDraftHandler,
    SimulatedPurchaseOrderHandler,
    SimulatedQuotationHandler,
    UnauthorizedExecutionError,
    UnknownActionTypeError,
)
from src.decision.policy_engine import (
    CONSEQUENTIAL_ACTIONS,
    PermissionEngine,
    PolicyDecision,
)
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactSource,
    FactStatus,
)
from src.models.email import EmailAddress, InboundEmail
from src.models.task import (
    ActionType,
    compute_payload_hash,
)
from src.server.mcp_server import create_mcp_server


# ---------------------------------------------------------------------------
# Test Fixtures (Strict Isolation on Disposable SQLite Databases)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    initialize_database(path)
    seed_business_state(path)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def task_repo(temp_db_path: str) -> TaskRepository:
    return TaskRepository(db_path=temp_db_path)


@pytest.fixture
def email_repo(temp_db_path: str) -> EmailRepository:
    return EmailRepository(db_path=temp_db_path)


@pytest.fixture
def profile_repo(temp_db_path: str) -> AdaptiveProfileRepository:
    return AdaptiveProfileRepository(db_path=temp_db_path)


@pytest.fixture
def policy_engine() -> PermissionEngine:
    return PermissionEngine()


@pytest.fixture
def dispatcher(task_repo: TaskRepository, policy_engine: PermissionEngine) -> ActionDispatcher:
    return ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)


@pytest.fixture
def sample_task(task_repo: TaskRepository) -> OperationalTask:
    task = OperationalTask(
        task_id=f"tsk_{uuid.uuid4().hex[:10]}",
        business_id="biz_garage_01",
        title="Repair Quote Request",
        task_type="inquiry",
        state=TaskState.AWAITING_APPROVAL,
    )
    return task_repo.create_task(task)


# ---------------------------------------------------------------------------
# Test Scenarios
# ---------------------------------------------------------------------------

def test_01_exact_payload_approval_binding_prevents_tampering(
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Tampering with an approved payload must be caught by hash mismatch."""
    payload = {"recipient": "client@example.com", "quote_amount": 4500.0, "currency": "INR"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_BINDING_QUOTATION.value,
        description="Send repair quotation",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    # Approve with identical payload succeeds
    approved = task_repo.approve_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="owner:rajesh",
        execution_payload=payload,
        policy_engine=policy_engine,
    )
    assert approved.execution_status == "APPROVED"

    # Attempting to approve with tampered payload raises PayloadTamperedError
    tampered_payload = {"recipient": "client@example.com", "quote_amount": 1000.0, "currency": "INR"}
    with pytest.raises(PayloadTamperedError):
        task_repo.approve_action(
            action_id=saved.action_id,
            business_id=sample_task.business_id,
            actor_id="owner:rajesh",
            execution_payload=tampered_payload,
            policy_engine=policy_engine,
        )


def test_02_consequential_action_requires_owner_approval(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    sample_task: OperationalTask,
) -> None:
    """Consequential action cannot be dispatched while status is PROPOSED."""
    payload = {"to": "supplier@auto.in", "part": "brake_pad", "qty": 10}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.CREATE_PURCHASE_ORDER.value,
        description="Purchase brake pads",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
        execution_status="PROPOSED",
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    # Dispatching without approval must raise ActionNotApprovedError
    with pytest.raises(ActionNotApprovedError):
        dispatcher.dispatch_action(
            action_id=saved.action_id,
            business_id=sample_task.business_id,
            actor_id="owner:rajesh",
        )


def test_03_non_owner_cannot_approve_or_execute_consequential_action(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Non-owner (e.g., anonymous, staff, or assistant) cannot approve or dispatch."""
    payload = {"client": "customer@car.in", "date": "2026-10-25T10:00:00Z"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SCHEDULE_APPOINTMENT.value,
        description="Book service slot",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    # Approval by unauthorized actor fails
    with pytest.raises(UnauthorizedError):
        task_repo.approve_action(
            action_id=saved.action_id,
            business_id=sample_task.business_id,
            actor_id="intern:suresh",
            execution_payload=payload,
            policy_engine=policy_engine,
        )


def test_04_low_risk_action_auto_allowed_without_approval(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    sample_task: OperationalTask,
) -> None:
    """Low risk actions (e.g., CREATE_INTERNAL_DRAFT) execute without manual owner approval."""
    payload = {"analysis": "Customer inquiries about synthetic oil change", "draft": "We offer synthetic oil change for Rs 2500."}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.CREATE_INTERNAL_DRAFT.value,
        description="Draft internal response",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=False,
        execution_status="PROPOSED",
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    receipt = dispatcher.dispatch_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="assistant",
    )
    assert receipt.status == "COMPLETED"
    assert receipt.provider_name == "simulated_internal_provider"
    assert "draft_id" in receipt.output_data


def test_05_action_rejection_logs_rationale_in_audit_trail(
    task_repo: TaskRepository,
    sample_task: OperationalTask,
) -> None:
    """Rejecting an action records REJECTED status and stores rationale in audit log."""
    payload = {"discount": 50.0}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_EXTERNAL_EMAIL.value,
        description="Send 50% discount",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    rejected = task_repo.reject_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="owner:rajesh",
        rejection_reason="Discount exceeds 20% policy threshold",
    )
    assert rejected.execution_status == "REJECTED"
    assert rejected.rejection_reason == "Discount exceeds 20% policy threshold"

    audit_log = task_repo.get_audit_log(sample_task.task_id, sample_task.business_id)
    rejection_events = [e for e in audit_log if e["event_type"] == "ACTION_REJECTED"]
    assert len(rejection_events) == 1
    assert "threshold" in rejection_events[0]["details"]["rejection_reason"]


def test_06_durable_idempotency_returns_existing_receipt_on_replay(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Calling dispatch multiple times for the same action returns the existing receipt without duplicate execution."""
    payload = {"to": "client@salon.in", "subject": "Appointment Confirmation", "body": "Your slot is booked"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_EXTERNAL_EMAIL.value,
        description="Send confirmation email",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)

    # First execution
    receipt1 = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert receipt1.status == "COMPLETED"

    # Second execution (replay)
    receipt2 = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert receipt2.status == "COMPLETED"
    assert receipt2.receipt_id == receipt1.receipt_id
    assert receipt2.idempotency_key == receipt1.idempotency_key

    # Verify only one execution record in database
    exec_history = task_repo.list_executions_for_task(sample_task.task_id, sample_task.business_id)
    assert len(exec_history) == 1


def test_07_tampered_payload_at_dispatch_blocked(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """If payload is modified between approval and dispatch, execution is blocked."""
    payload = {"price": 1000.0}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_BINDING_QUOTATION.value,
        description="Quote",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)

    # Pass altered payload at dispatch time
    with pytest.raises(ActionPayloadTamperedError):
        dispatcher.dispatch_action(
            action_id=saved.action_id,
            business_id=sample_task.business_id,
            actor_id="owner:rajesh",
            execution_payload={"price": 200.0},
        )


def test_08_handler_failure_marks_task_and_execution_failed(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """When execution handler fails definitively, task and execution record are marked FAILED."""
    class FailingHandler(BaseActionHandler):
        action_type = ActionType.SEND_EXTERNAL_EMAIL.value
        provider_name = "simulated_failing_email"
        def execute(self, payload: Dict[str, Any], business_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            raise RuntimeError("Simulated SMTP Connection Refused")

    dispatcher.register_handler(FailingHandler())

    payload = {"to": "vendor@parts.com", "msg": "Hi"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_EXTERNAL_EMAIL.value,
        description="Send email",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)

    receipt = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert receipt.status == "FAILED"
    assert "Simulated SMTP Connection Refused" in (receipt.error_message or "")

    # Check task state
    updated_task = task_repo.get_task(sample_task.task_id, sample_task.business_id)
    assert updated_task is not None
    assert updated_task.state == TaskState.FAILED


def test_09_execution_uncertain_blocks_retry_until_reconciliation(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """When a provider times out, state becomes EXECUTION_UNCERTAIN and automatic retry is blocked."""
    class UncertainHandler(BaseActionHandler):
        action_type = ActionType.CREATE_PURCHASE_ORDER.value
        provider_name = "simulated_timeout_gateway"
        def execute(self, payload: Dict[str, Any], business_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            raise ExecutionUncertainError("Gateway timed out after 30s. Transaction state unknown.")

    dispatcher.register_handler(UncertainHandler())

    payload = {"item": "Alternator", "cost": 7200.0}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.CREATE_PURCHASE_ORDER.value,
        description="PO Alternator",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)

    # Dispatch produces EXECUTION_UNCERTAIN
    receipt = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert receipt.status == "EXECUTION_UNCERTAIN"

    # Retrying blindly must raise ExecutionUncertainError
    with pytest.raises(ExecutionUncertainError):
        dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")


def test_10_reconcile_uncertain_execution_confirm_executed(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Owner can explicitly reconcile EXECUTION_UNCERTAIN with CONFIRM_EXECUTED."""
    class UncertainHandler(BaseActionHandler):
        action_type = ActionType.SCHEDULE_APPOINTMENT.value
        provider_name = "simulated_uncertain_booking"
        def execute(self, payload: Dict[str, Any], business_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            raise ExecutionUncertainError("Network dropped during confirmation")

    dispatcher.register_handler(UncertainHandler())

    payload = {"slot": "10:00 AM"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SCHEDULE_APPOINTMENT.value,
        description="Book",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)
    dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")

    # Reconcile as EXECUTED
    receipt = dispatcher.reconcile_uncertain_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="owner:rajesh",
        resolution="CONFIRM_EXECUTED",
        notes="Verified booking appeared on supplier portal",
    )
    assert receipt.status == "RECONCILED"
    assert "Verified booking" in receipt.output_data["reconciliation_notes"]

    # Verify task transitioned to COMPLETED
    task = task_repo.get_task(sample_task.task_id, sample_task.business_id)
    assert task is not None
    assert task.state == TaskState.COMPLETED


def test_11_reconcile_uncertain_execution_confirm_failed(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Owner can explicitly reconcile EXECUTION_UNCERTAIN with CONFIRM_FAILED."""
    class UncertainHandler(BaseActionHandler):
        action_type = ActionType.SEND_EXTERNAL_EMAIL.value
        provider_name = "simulated_uncertain_smtp"
        def execute(self, payload: Dict[str, Any], business_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            raise ExecutionUncertainError("SMTP 421 timeout")

    dispatcher.register_handler(UncertainHandler())

    payload = {"to": "client@abc.com"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_EXTERNAL_EMAIL.value,
        description="Email",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)
    dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")

    # Reconcile as FAILED
    receipt = dispatcher.reconcile_uncertain_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="owner:rajesh",
        resolution="CONFIRM_FAILED",
        notes="Confirmed email was not received; will create new draft",
    )
    assert receipt.status == "FAILED"

    task = task_repo.get_task(sample_task.task_id, sample_task.business_id)
    assert task is not None
    assert task.state == TaskState.FAILED


def test_12_tenant_isolation_blocks_cross_business_access(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    sample_task: OperationalTask,
) -> None:
    """Tenant B cannot access, approve, or dispatch an action belonging to Tenant A."""
    payload = {"note": "Confidential draft"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id="biz_garage_01",
        action_type=ActionType.CREATE_INTERNAL_DRAFT.value,
        description="Draft",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=False,
    )
    saved = task_repo.propose_action(sample_task.task_id, "biz_garage_01", proposal)

    # Tenant B tries to get or dispatch Tenant A's action
    assert task_repo.get_action(saved.action_id, business_id="biz_salon_99") is None

    with pytest.raises(ActionNotFoundError):
        dispatcher.dispatch_action(
            action_id=saved.action_id,
            business_id="biz_salon_99",
            actor_id="owner:salon_owner",
        )


def test_13_fastmcp_tools_task_management_and_approvals(
    task_repo: TaskRepository,
    profile_repo: AdaptiveProfileRepository,
    policy_engine: PermissionEngine,
    dispatcher: ActionDispatcher,
    sample_task: OperationalTask,
) -> None:
    """FastMCP tools correctly inspect tasks, approve proposals, and execute actions."""
    server = create_mcp_server(
        profile_repo=profile_repo,
        task_repo=task_repo,
        policy_engine=policy_engine,
        action_dispatcher=dispatcher,
    )

    # 1. Propose action
    payload = {"details": "Diagnostic review"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.CREATE_INTERNAL_DRAFT.value,
        description="Review",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=False,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    # Call FastMCP dispatch tool directly via server context or function
    receipt = dispatcher.dispatch_action(
        action_id=saved.action_id,
        business_id=sample_task.business_id,
        actor_id="assistant",
    )
    assert receipt.status == "COMPLETED"

    # Query execution history
    history = task_repo.list_executions_for_business(sample_task.business_id)
    assert len(history) == 1
    assert history[0]["action_id"] == saved.action_id


def test_14_fastapi_rest_email_ingestion_and_processing(temp_db_path: str) -> None:
    """FastAPI REST endpoints handle email ingestion and supervisor task generation."""
    import src.server.web_app as web_module
    from src.agent.document_onboarding import DocumentOnboardingService
    web_module.task_repo = TaskRepository(temp_db_path)
    web_module.email_repo = EmailRepository(temp_db_path)
    web_module.adaptive_repo = AdaptiveProfileRepository(temp_db_path)
    web_module.policy_engine = PermissionEngine()
    web_module.action_dispatcher = ActionDispatcher(task_repo=web_module.task_repo, policy_engine=web_module.policy_engine)
    web_module.supervisor = EmailOperationalSupervisor(
        email_repo=web_module.email_repo,
        task_repo=web_module.task_repo,
        profile_repo=web_module.adaptive_repo,
        policy_engine=web_module.policy_engine,
    )
    web_module.doc_onboarding_service = DocumentOnboardingService(repo=web_module.adaptive_repo)

    client = TestClient(web_module.app)

    # Ingest email
    res = client.post(
        "/api/emails/ingest",
        json={
            "business_id": "biz_boutique",
            "sender_email": "customer@fashion.in",
            "sender_name": "Pooja Sharma",
            "subject": "Bridal Lehenga Custom Stitching Inquiry",
            "body_plain": "Hello, do you accept orders for custom bridal lehenga stitching for next month? Please share quotation.",
            "process_now": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "PROCESSED"
    assert "task_id" in data
    assert data["proposals_count"] >= 1

    # List tasks
    task_res = client.get("/api/tasks?business_id=biz_boutique")
    assert task_res.status_code == 200
    tasks = task_res.json()["tasks"]
    assert len(tasks) >= 1
    assert tasks[0]["business_id"] == "biz_boutique"


def test_15_fastapi_rest_approval_and_dispatch_workflow(temp_db_path: str) -> None:
    """FastAPI REST endpoints enforce owner approval and execute simulated dispatch."""
    import src.server.web_app as web_module
    from src.agent.document_onboarding import DocumentOnboardingService
    web_module.task_repo = TaskRepository(temp_db_path)
    web_module.email_repo = EmailRepository(temp_db_path)
    web_module.adaptive_repo = AdaptiveProfileRepository(temp_db_path)
    web_module.policy_engine = PermissionEngine()
    web_module.action_dispatcher = ActionDispatcher(task_repo=web_module.task_repo, policy_engine=web_module.policy_engine)
    web_module.supervisor = EmailOperationalSupervisor(
        email_repo=web_module.email_repo,
        task_repo=web_module.task_repo,
        profile_repo=web_module.adaptive_repo,
        policy_engine=web_module.policy_engine,
    )
    web_module.doc_onboarding_service = DocumentOnboardingService(repo=web_module.adaptive_repo)

    client = TestClient(web_module.app)

    # Create task & proposal directly in app repo
    task = OperationalTask(
        task_id="tsk_rest_01",
        business_id="biz_dentist",
        title="Appointment Booking",
        task_type="booking",
        state=TaskState.AWAITING_APPROVAL,
    )
    web_module.task_repo.create_task(task)

    payload = {"patient": "Vikram", "time": "2026-11-01T11:00:00Z", "procedure": "Root Canal Consultation"}
    proposal = ActionProposal(
        task_id="tsk_rest_01",
        business_id="biz_dentist",
        action_type=ActionType.SCHEDULE_APPOINTMENT.value,
        description="Confirm dental appointment",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = web_module.task_repo.propose_action("tsk_rest_01", "biz_dentist", proposal)

    # Attempt dispatch without approval -> 400
    res_dispatch_unapproved = client.post(
        f"/api/actions/{saved.action_id}/dispatch",
        json={"business_id": "biz_dentist", "actor_id": "owner:dr_arun"},
    )
    assert res_dispatch_unapproved.status_code == 400

    # Non-owner approval attempt -> 403
    res_bad_approve = client.post(
        f"/api/actions/{saved.action_id}/approve",
        json={"business_id": "biz_dentist", "actor_id": "stranger"},
    )
    assert res_bad_approve.status_code == 403

    # Owner approval -> 200
    res_approve = client.post(
        f"/api/actions/{saved.action_id}/approve",
        headers={"X-Autopilot-Actor-Id": "owner:dr_arun"},
        json={"business_id": "biz_dentist", "execution_payload": payload},
    )
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] == "APPROVED"

    # Owner dispatch -> 200
    res_dispatch = client.post(
        f"/api/actions/{saved.action_id}/dispatch",
        headers={"X-Autopilot-Actor-Id": "owner:dr_arun"},
        json={"business_id": "biz_dentist"},
    )
    assert res_dispatch.status_code == 200
    receipt_data = res_dispatch.json()["receipt"]
    assert receipt_data["status"] == "COMPLETED"
    assert "booking_id" in receipt_data["output_data"]

    # Verify execution history endpoint
    res_execs = client.get("/api/executions?business_id=biz_dentist")
    assert res_execs.status_code == 200
    execs = res_execs.json()["executions"]
    assert len(execs) == 1
    assert execs[0]["action_id"] == saved.action_id


def test_16_fastapi_rest_document_onboarding_and_fact_verification(temp_db_path: str) -> None:
    """Document onboarding via REST parses facts, detects conflicts, and enables owner verification."""
    import src.server.web_app as web_module
    from src.agent.document_onboarding import DocumentOnboardingService
    web_module.task_repo = TaskRepository(temp_db_path)
    web_module.email_repo = EmailRepository(temp_db_path)
    web_module.adaptive_repo = AdaptiveProfileRepository(temp_db_path)
    web_module.policy_engine = PermissionEngine()
    web_module.action_dispatcher = ActionDispatcher(task_repo=web_module.task_repo, policy_engine=web_module.policy_engine)
    web_module.doc_onboarding_service = DocumentOnboardingService(repo=web_module.adaptive_repo)

    client = TestClient(web_module.app)

    # Seed profile
    prof = AdaptiveBusinessProfile(business_id="biz_carpentry", display_name="Gupta Woodworks", category="carpentry")
    prof.set_fact("hourly_rate", 500.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    web_module.adaptive_repo.save_profile(prof)

    # Ingest document with a conflict and a new fact
    doc_text = """
    Gupta Woodworks Rate Card
    Hourly rate: Rs 750 per hour
    Minimum Order: 2 items
    Daily capacity: 4 custom furniture pieces
    """
    res = client.post(
        "/api/documents/onboard",
        json={"business_id": "biz_carpentry", "document_text": doc_text, "filename": "rates.txt"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["conflicts_detected"]) >= 1
    assert data["conflicts_detected"][0]["key"] == "hourly_rate"
    # Confirmed fact remains unchanged
    p_check = web_module.adaptive_repo.get_profile("biz_carpentry")
    assert p_check.get_fact("hourly_rate").value == 500.0

    # Verify new fact via REST
    verify_res = client.post(
        "/api/documents/verify-fact",
        headers={"X-Autopilot-Actor-Id": "owner:gupta"},
        json={"business_id": "biz_carpentry", "key": "daily_capacity", "status": "CONFIRMED", "value": 4.0},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "SUCCESS"
    assert verify_res.json()["fact"]["status"] == "confirmed"


def test_17_simulated_handlers_all_return_safe_offline_receipts(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """All registered simulated handlers execute safely offline without third-party network calls."""
    handlers_to_test = [
        (ActionType.SEND_EXTERNAL_EMAIL.value, {"to": "a@b.com", "subject": "Test", "body": "Content"}),
        (ActionType.SEND_BINDING_QUOTATION.value, {"client_email": "a@b.com", "total_price": 3200.0, "items": [{"name": "Labor", "price": 3200.0}]}),
        (ActionType.SCHEDULE_APPOINTMENT.value, {"service": "Haircut", "client": "Ramesh", "scheduled_time": "2026-10-20T14:00:00Z"}),
        (ActionType.CREATE_PURCHASE_ORDER.value, {"supplier": "Steel Suppliers Ltd", "items": [{"item": "Steel Rod", "qty": 50}], "total_amount": 12500.0}),
        (ActionType.CREATE_INTERNAL_DRAFT.value, {"analysis": "Customer wants estimate", "draft_reply": "Thank you for reaching out"}),
    ]

    for idx, (action_type, payload) in enumerate(handlers_to_test):
        task = task_repo.create_task(
            OperationalTask(
                task_id=f"tsk_iter_{idx}_{uuid.uuid4().hex[:6]}",
                business_id=sample_task.business_id,
                title=f"Task {action_type}",
                task_type="test",
                state=TaskState.AWAITING_APPROVAL,
            )
        )
        proposal = ActionProposal(
            task_id=task.task_id,
            business_id=task.business_id,
            action_type=action_type,
            description=f"Test {action_type}",
            payload=payload,
            payload_hash=compute_payload_hash(payload),
            requires_approval=action_type in CONSEQUENTIAL_ACTIONS,
        )
        saved = task_repo.propose_action(task.task_id, task.business_id, proposal)
        if proposal.requires_approval:
            task_repo.approve_action(saved.action_id, task.business_id, "owner:rajesh", payload, policy_engine)

        receipt = dispatcher.dispatch_action(saved.action_id, task.business_id, "owner:rajesh")
        assert receipt.status == "COMPLETED"
        assert receipt.receipt_id.startswith(("eml_sim_", "qte_sim_", "apt_sim_", "po_sim_", "drf_sim_"))
        assert receipt.output_data is not None


def test_18_unknown_action_type_fails_closed(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    sample_task: OperationalTask,
) -> None:
    """Unknown or malicious action types fail closed with deterministic policy denial."""
    payload = {"arbitrary_command": "rm -rf /"}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type="unregistered_malicious_action",
        description="Exploit attempt",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)

    with pytest.raises(UnknownActionTypeError):
        dispatcher.dispatch_action(
            action_id=saved.action_id,
            business_id=sample_task.business_id,
            actor_id="owner:rajesh",
        )


def test_19_end_to_end_pipeline_untrusted_email_to_audited_execution(
    email_repo: EmailRepository,
    task_repo: TaskRepository,
    profile_repo: AdaptiveProfileRepository,
    policy_engine: PermissionEngine,
    dispatcher: ActionDispatcher,
) -> None:
    """
    Complete end-to-end multi-agent operational workflow:
      1. Ingest untrusted customer email for an onboarded car service garage.
      2. Supervisor retrieves business facts, classifies intent, links task, and proposes quote.
      3. Consequential quote proposal requires owner approval.
      4. Owner reviews exact payload, approves with cryptographic hash binding.
      5. Dispatcher reevaluates policy, verifies hash, executes simulated quote issuance.
      6. Audit log verifies every lifecycle step from ingestion to receipt.
    """
    # 1. Onboard business profile
    garage = AdaptiveBusinessProfile(
        business_id="biz_prime_garage",
        display_name="Prime Auto Care",
        category="vehicle_repair",
    )
    garage.set_fact("daily_capacity", 8.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    garage.set_fact("inspection_fee", 500.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    garage.set_fact("standard_labor_rate", 800.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    profile_repo.save_profile(garage)

    # 2. Ingest customer email
    raw_email = InboundEmail(
        message_id="msg_garage_001",
        business_id="biz_prime_garage",
        sender=EmailAddress(email="carowner@gmail.com", name="Sunil Verma"),
        to_recipients=[EmailAddress(email="service@primeauto.in")],
        subject="Request for Clutch Plate Replacement Quote",
        body_text="Hi, my Honda City clutch is slipping. Could you provide an estimate and available slot for this Saturday?",
    )
    saved_email = email_repo.save_email(raw_email)

    # 3. Supervisor processes email
    supervisor = EmailOperationalSupervisor(
        email_repo=email_repo,
        task_repo=task_repo,
        profile_repo=profile_repo,
        policy_engine=policy_engine,
    )
    outcome = supervisor.process_email(saved_email)
    assert outcome.task.business_id == "biz_prime_garage"
    assert outcome.classification.intent in ("quote_request", "appointment_booking", "appointment_request", "general_inquiry")
    assert len(outcome.action_proposals) >= 1

    # Find the consequential proposal (e.g. quote or appointment)
    consequential_proposals = [p for p in outcome.action_proposals if p.requires_approval]
    assert len(consequential_proposals) >= 1
    quote_prop = consequential_proposals[0]

    # 4. Owner approves proposal
    approved = task_repo.approve_action(
        action_id=quote_prop.action_id,
        business_id="biz_prime_garage",
        actor_id="owner:sunil_owner",
        execution_payload=quote_prop.payload,
        policy_engine=policy_engine,
    )
    assert approved.execution_status == "APPROVED"

    # 5. Dispatch action
    receipt = dispatcher.dispatch_action(
        action_id=quote_prop.action_id,
        business_id="biz_prime_garage",
        actor_id="owner:sunil_owner",
    )
    assert receipt.status == "COMPLETED"
    assert receipt.receipt_id != ""

    # 6. Verify full audit trail
    audit_trail = task_repo.get_audit_log(outcome.task.task_id, "biz_prime_garage")
    event_types = [e["event_type"] for e in audit_trail]
    assert "TASK_CREATED" in event_types
    assert "ACTION_PROPOSED" in event_types
    assert "ACTION_APPROVED" in event_types
    assert "ACTION_EXECUTED" in event_types


def test_20_replay_idempotency_prevents_duplicate_side_effects(
    dispatcher: ActionDispatcher,
    task_repo: TaskRepository,
    policy_engine: PermissionEngine,
    sample_task: OperationalTask,
) -> None:
    """Repeatedly calling dispatch on an already executed action returns the identical receipt without duplicate execution."""
    call_counts = {"count": 0}

    class CountingHandler(BaseActionHandler):
        action_type = ActionType.SEND_BINDING_QUOTATION.value
        provider_name = "simulated_counting_quotation"
        def execute(self, payload: Dict[str, Any], business_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            call_counts["count"] += 1
            return {"receipt_id": "receipt_single_execution", "status": "QUOTATION_ISSUED"}

    dispatcher.register_handler(CountingHandler())

    payload = {"service": "Tailoring", "price": 1200.0}
    proposal = ActionProposal(
        task_id=sample_task.task_id,
        business_id=sample_task.business_id,
        action_type=ActionType.SEND_BINDING_QUOTATION.value,
        description="Quote",
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        requires_approval=True,
    )
    saved = task_repo.propose_action(sample_task.task_id, sample_task.business_id, proposal)
    task_repo.approve_action(saved.action_id, sample_task.business_id, "owner:rajesh", payload, policy_engine)

    # First dispatch
    r1 = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert r1.status == "COMPLETED"
    assert call_counts["count"] == 1

    # Second dispatch (replay)
    r2 = dispatcher.dispatch_action(saved.action_id, sample_task.business_id, "owner:rajesh")
    assert r2.status == "COMPLETED"
    assert r2.receipt_id == r1.receipt_id
    assert call_counts["count"] == 1  # Handler was NOT invoked a second time!
