"""
Controlled Action Dispatcher and Simulated Handlers
===================================================
Centralized execution dispatcher enforcing deterministic policy re-evaluation,
exact SHA-256 payload binding, authenticated owner authorization, durable
idempotency, concurrency safety, and failure recovery (including EXECUTION_UNCERTAIN).

Includes safe offline simulated handlers for:
  - External email sending
  - Binding quotation issuance
  - Appointment confirmation
  - Purchase order creation / acknowledgement

No live external APIs are ever called.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from src.db.task_repository import (
    ActionNotFoundError,
    ActionProposal,
    OperationalTask,
    PayloadTamperedError,
    TaskNotFoundError,
    TaskRepository,
    UnauthorizedError,
)
from src.decision.policy_engine import (
    CONSEQUENTIAL_ACTIONS,
    PermissionEngine,
    PolicyDecision,
)
from src.models.task import (
    ActionType,
    TaskState,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)

SIMULATION_NOTICE = "SIMULATED EXECUTION: Safe offline simulation. No live external email, calendar, payment, or supplier API was invoked."


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ActionDispatcherError(Exception):
    """Base exception for action dispatcher operations."""


class ActionNotApprovedError(ActionDispatcherError):
    """Raised when attempting to execute a consequential action without owner approval."""


class ActionPayloadTamperedError(ActionDispatcherError):
    """Raised when the execution payload hash differs from the approved proposal hash."""


class UnauthorizedExecutionError(ActionDispatcherError):
    """Raised when an unauthenticated or non-owner actor attempts to execute an action."""


class UnknownActionTypeError(ActionDispatcherError):
    """Raised when an action type is unrecognized or unsupported."""


class ExecutionUncertainError(ActionDispatcherError):
    """Raised when external execution outcome is indeterminate (e.g. simulated network timeout)."""


class ExecutionFailedError(ActionDispatcherError):
    """Raised when an action execution definitively fails."""


# ---------------------------------------------------------------------------
# Execution Receipt
# ---------------------------------------------------------------------------

@dataclass
class ExecutionReceipt:
    """Structured receipt generated upon action execution."""
    receipt_id: str
    action_id: str
    task_id: str
    business_id: str
    provider_name: str
    status: str  # "COMPLETED", "FAILED", "EXECUTION_UNCERTAIN", "RECONCILED"
    idempotency_key: str
    output_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    simulation_notice: str = SIMULATION_NOTICE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "action_id": self.action_id,
            "task_id": self.task_id,
            "business_id": self.business_id,
            "provider_name": self.provider_name,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "simulation_notice": self.simulation_notice,
        }


# ---------------------------------------------------------------------------
# Base Handler Interface
# ---------------------------------------------------------------------------

class BaseActionHandler(ABC):
    """
    Abstract adapter interface for action execution.
    Real providers (e.g. Gmail, Outlook, Zoho, Calendar) can implement this
    interface without changing the supervisor or permission architecture.
    """

    @property
    @abstractmethod
    def action_type(self) -> str:
        """Supported action type string."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name identifying the execution engine."""

    @abstractmethod
    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the action and returns structured output data.
        Raises ExecutionFailedError on definitive failure.
        Raises ExecutionUncertainError on indeterminate outcome.
        """


# ---------------------------------------------------------------------------
# Simulated Action Handlers (Safe Offline Implementations)
# ---------------------------------------------------------------------------

class SimulatedEmailHandler(BaseActionHandler):
    """Simulated external email sending adapter."""

    @property
    def action_type(self) -> str:
        return ActionType.SEND_EXTERNAL_EMAIL.value

    @property
    def provider_name(self) -> str:
        return "simulated_email_provider"

    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        recipient = payload.get("recipient_email") or payload.get("recipient") or ""
        subject = payload.get("subject", "Business Communication")
        message = payload.get("message", "")

        # Test simulation hooks for failure & uncertainty
        if payload.get("simulate_uncertainty") or "timeout@" in recipient or "uncertain@" in recipient:
            raise ExecutionUncertainError(
                f"Simulated timeout communicating with mail transfer agent for '{recipient}'. Delivery confirmation lost."
            )
        if payload.get("simulate_failure") or "fail@" in recipient:
            raise ExecutionFailedError(
                f"Simulated delivery failure: Mailbox '{recipient}' unavailable or rejected."
            )

        sim_receipt_id = f"eml_sim_{uuid.uuid4().hex[:12]}"
        return {
            "receipt_id": sim_receipt_id,
            "recipient": recipient,
            "subject": subject,
            "message_bytes": len(message.encode("utf-8")),
            "delivery_status": "DELIVERED_SIMULATED",
            "server_handshake": "250 OK (Simulated)",
        }


class SimulatedQuotationHandler(BaseActionHandler):
    """Simulated binding quotation issuance adapter."""

    @property
    def action_type(self) -> str:
        return ActionType.SEND_BINDING_QUOTATION.value

    @property
    def provider_name(self) -> str:
        return "simulated_quotation_provider"

    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        recipient = payload.get("recipient_email") or ""
        quote_amount = payload.get("quote_amount", 0.0)
        lead_time = payload.get("lead_time_days", 3)
        terms = payload.get("terms", "Net 15 days")

        # Test hooks
        if payload.get("simulate_uncertainty") or "uncertain@" in recipient:
            raise ExecutionUncertainError(
                f"Simulated timeout sending binding quotation to '{recipient}'."
            )
        if payload.get("simulate_failure") or "fail@" in recipient:
            raise ExecutionFailedError(
                f"Simulated quotation issuance failure: recipient '{recipient}' unreachable."
            )

        quote_id = f"QUO-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
        sim_receipt_id = f"qte_sim_{uuid.uuid4().hex[:12]}"
        return {
            "receipt_id": sim_receipt_id,
            "quote_id": quote_id,
            "recipient_email": recipient,
            "quote_amount": float(quote_amount),
            "lead_time_days": lead_time,
            "terms": terms,
            "status": "ISSUED_SIMULATED",
        }


class SimulatedAppointmentHandler(BaseActionHandler):
    """Simulated appointment confirmation adapter."""

    @property
    def action_type(self) -> str:
        return ActionType.SCHEDULE_APPOINTMENT.value

    @property
    def provider_name(self) -> str:
        return "simulated_calendar_provider"

    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        client_email = payload.get("client_email") or payload.get("recipient_email") or ""
        slot = payload.get("slot", "Scheduled Slot")
        service_type = payload.get("service_type", "Standard Service")

        # Test hooks
        if payload.get("simulate_uncertainty") or "uncertain@" in client_email:
            raise ExecutionUncertainError(
                f"Simulated calendar sync timeout booking slot '{slot}' for '{client_email}'."
            )
        if payload.get("simulate_failure") or "fail@" in client_email:
            raise ExecutionFailedError(
                f"Simulated booking conflict: Slot '{slot}' already occupied."
            )

        booking_id = f"APT-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
        sim_receipt_id = f"apt_sim_{uuid.uuid4().hex[:12]}"
        return {
            "receipt_id": sim_receipt_id,
            "booking_id": booking_id,
            "client_email": client_email,
            "slot": slot,
            "service_type": service_type,
            "status": "CONFIRMED_SIMULATED",
        }


class SimulatedPurchaseOrderHandler(BaseActionHandler):
    """Simulated purchase order creation and acknowledgement adapter."""

    @property
    def action_type(self) -> str:
        return ActionType.CREATE_PURCHASE_ORDER.value

    @property
    def provider_name(self) -> str:
        return "simulated_procurement_provider"

    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        supplier_email = payload.get("supplier_email") or payload.get("supplier") or ""
        action_name = payload.get("action", "create_order")
        doc_ref = payload.get("document_ref", "")

        # Test hooks
        if payload.get("simulate_uncertainty") or "uncertain@" in supplier_email:
            raise ExecutionUncertainError(
                f"Simulated timeout dispatching purchase order to supplier '{supplier_email}'."
            )
        if payload.get("simulate_failure") or "fail@" in supplier_email:
            raise ExecutionFailedError(
                f"Simulated procurement rejected: Supplier '{supplier_email}' closed orders."
            )

        po_number = f"PO-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
        sim_receipt_id = f"po_sim_{uuid.uuid4().hex[:12]}"
        return {
            "receipt_id": sim_receipt_id,
            "po_number": po_number,
            "supplier_email": supplier_email,
            "document_ref": doc_ref,
            "action": action_name,
            "status": "ACKNOWLEDGED_SIMULATED",
        }


class SimulatedInternalDraftHandler(BaseActionHandler):
    """Simulated low-risk internal draft handler."""

    @property
    def action_type(self) -> str:
        return ActionType.CREATE_INTERNAL_DRAFT.value

    @property
    def provider_name(self) -> str:
        return "simulated_internal_provider"

    def execute(
        self,
        payload: Dict[str, Any],
        business_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        draft_id = f"drf_sim_{uuid.uuid4().hex[:12]}"
        return {
            "receipt_id": draft_id,
            "draft_id": draft_id,
            "summary": payload.get("analysis", ""),
            "status": "DRAFT_STORED",
        }


# ---------------------------------------------------------------------------
# Centralized Action Dispatcher
# ---------------------------------------------------------------------------

class ActionDispatcher:
    """
    Centralized execution dispatcher.
    Enforces the full 10-step execution verification contract before invoking any handler:
      1. Accept an existing persisted action proposal.
      2. Resolve the correct business and task from trusted context.
      3. Reevaluate deterministic policy immediately before execution.
      4. Verify the exact proposed payload hash.
      5. Verify the action's current approval status.
      6. Verify authenticated owner authorization for consequential actions.
      7. Reject unknown or unsupported action types.
      8. Route permitted actions to registered execution handlers.
      9. Persist execution attempts, results, and receipts.
      10. Update task and action states consistently.
    """

    def __init__(
        self,
        task_repo: TaskRepository,
        policy_engine: Optional[PermissionEngine] = None,
        handlers: Optional[Dict[str, BaseActionHandler]] = None,
    ) -> None:
        self.task_repo = task_repo
        self.policy_engine = policy_engine or PermissionEngine()
        self._handlers: Dict[str, BaseActionHandler] = {}

        # Register default simulated handlers
        self.register_handler(SimulatedEmailHandler())
        self.register_handler(SimulatedQuotationHandler())
        self.register_handler(SimulatedAppointmentHandler())
        self.register_handler(SimulatedPurchaseOrderHandler())
        self.register_handler(SimulatedInternalDraftHandler())

        if handlers:
            for h in handlers.values():
                self.register_handler(h)

    def register_handler(self, handler: BaseActionHandler) -> None:
        """Registers an action execution handler for an action type."""
        self._handlers[handler.action_type.lower()] = handler

    def dispatch_action(
        self,
        action_id: str,
        business_id: str,
        actor_id: str,
        execution_payload: Optional[Dict[str, Any]] = None,
    ) -> ExecutionReceipt:
        """
        Executes an action proposal with strict pre-execution verification.
        Guarantees durable idempotency: replaying an already-executed action
        returns the existing receipt without duplicate side-effects.
        """
        # 1. Accept existing persisted action proposal
        proposal = self.task_repo.get_action(action_id, business_id=business_id)
        if not proposal:
            raise ActionNotFoundError(
                f"Action proposal '{action_id}' not found for business '{business_id}'."
            )

        # 2. Resolve trusted task context
        task = self.task_repo.get_task(proposal.task_id, business_id=business_id)
        if not task:
            raise TaskNotFoundError(
                f"Parent task '{proposal.task_id}' not found for business '{business_id}'."
            )

        # 3. Check durable idempotency first
        # Look for existing execution record for this action or idempotency_key
        existing_exec = self.task_repo.get_execution_by_action(action_id, business_id=business_id)
        if not existing_exec:
            existing_exec = self.task_repo.get_execution_by_idempotency_key(
                business_id=business_id, idempotency_key=proposal.idempotency_key
            )

        if existing_exec:
            status = existing_exec["status"]
            if status in ("COMPLETED", "RECONCILED"):
                logger.info(
                    f"Action '{action_id}' already executed with receipt '{existing_exec['receipt_id']}'. "
                    f"Returning existing execution receipt (idempotent)."
                )
                return ExecutionReceipt(
                    receipt_id=existing_exec["receipt_id"] or existing_exec["execution_id"],
                    action_id=action_id,
                    task_id=task.task_id,
                    business_id=business_id,
                    provider_name=existing_exec["provider_name"],
                    status=status,
                    idempotency_key=existing_exec["idempotency_key"],
                    output_data=existing_exec["output_data"],
                    timestamp=existing_exec["completed_at"] or existing_exec["created_at"],
                )
            elif status == "EXECUTION_UNCERTAIN":
                raise ExecutionUncertainError(
                    f"Action '{action_id}' is in EXECUTION_UNCERTAIN state. "
                    f"Automatic retry blocked. Explicit owner reconciliation required."
                )

        # 4. Resolve payload to verify
        payload = execution_payload if execution_payload is not None else proposal.payload

        # 5. Reevaluate deterministic policy immediately before execution
        eval_result = self.policy_engine.evaluate_action(
            action_type=proposal.action_type,
            payload=payload,
            business_id=business_id,
            actor_role="assistant",
        )

        if eval_result.decision == PolicyDecision.DENY:
            raise UnknownActionTypeError(
                f"Deterministic policy denied execution of action '{proposal.action_type}': {eval_result.reason}"
            )

        # 6. Verify payload hash integrity (tampering check)
        computed_hash = compute_payload_hash(payload)
        if computed_hash != proposal.payload_hash:
            logger.error(
                f"Tampering detected! Provided payload hash '{computed_hash}' does not match "
                f"proposal hash '{proposal.payload_hash}'."
            )
            raise ActionPayloadTamperedError(
                "Execution payload hash does not match approved proposal payload hash. Execution blocked."
            )

        # 7. For consequential actions, verify approval status and owner authorization
        is_consequential = proposal.requires_approval or (proposal.action_type in CONSEQUENTIAL_ACTIONS)
        if is_consequential:
            # Check proposal approval status
            if proposal.execution_status != "APPROVED":
                raise ActionNotApprovedError(
                    f"Action '{action_id}' requires owner approval but current status is '{proposal.execution_status}'."
                )

            # Check that caller actor is an authorized owner
            if not self.policy_engine.is_authorized_owner(business_id, actor_id):
                raise UnauthorizedExecutionError(
                    f"Actor '{actor_id}' is not an authorized owner for business '{business_id}'."
                )

            # Verify that the approver recorded on the proposal was also authorized
            if not proposal.approved_by or not self.policy_engine.is_authorized_owner(business_id, proposal.approved_by):
                raise UnauthorizedExecutionError(
                    f"Action proposal was not approved by a valid authorized owner: '{proposal.approved_by}'."
                )

        # 8. Check for registered execution handler (reject unknown)
        handler = self._handlers.get(proposal.action_type.lower())
        if not handler:
            raise UnknownActionTypeError(
                f"No registered execution handler for action type '{proposal.action_type}'. Execution failed closed."
            )

        # 9. Persist execution attempt
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        self.task_repo.record_execution_attempt(
            execution_id=execution_id,
            action_id=action_id,
            task_id=task.task_id,
            business_id=business_id,
            idempotency_key=proposal.idempotency_key,
            provider_name=handler.provider_name,
            status="EXECUTING",
            output_data={},
        )

        # Move task to EXECUTING via legal transition path
        if task.state != TaskState.EXECUTING:
            if task.state == TaskState.RECEIVED:
                task = self.task_repo.transition_state(
                    task_id=task.task_id,
                    business_id=business_id,
                    target_state=TaskState.CLASSIFIED,
                    actor=actor_id,
                    details={"reason": "Advancing state to execute action"},
                )
            if task.state == TaskState.CLASSIFIED:
                task = self.task_repo.transition_state(
                    task_id=task.task_id,
                    business_id=business_id,
                    target_state=TaskState.PLANNING,
                    actor=actor_id,
                    details={"reason": "Advancing state to execute action"},
                )
            if task.state == TaskState.PLANNING:
                task = self.task_repo.transition_state(
                    task_id=task.task_id,
                    business_id=business_id,
                    target_state=TaskState.WORKING,
                    actor=actor_id,
                    details={"reason": "Advancing state to execute action"},
                )
            self.task_repo.transition_state(
                task_id=task.task_id,
                business_id=business_id,
                target_state=TaskState.EXECUTING,
                actor=actor_id,
                details={"reason": "Action execution initiated by dispatcher"},
            )


        # 10. Execute through handler with failure and uncertainty handling
        try:
            output_data = handler.execute(
                payload=payload,
                business_id=business_id,
                context={"task_id": task.task_id, "action_id": action_id, "actor_id": actor_id},
            )
            receipt_id = output_data.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:12]}"

            # Complete execution record
            self.task_repo.complete_execution(
                execution_id=execution_id,
                receipt_id=receipt_id,
                output_data=output_data,
                business_id=business_id,
            )

            # Mark action as EXECUTED in proposals
            conn = self.task_repo._conn()
            try:
                conn.execute(
                    "UPDATE autopilot_action_proposals SET execution_status = 'EXECUTED' WHERE action_id = ?",
                    (action_id,),
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            # Complete task
            self.task_repo.transition_state(
                task_id=task.task_id,
                business_id=business_id,
                target_state=TaskState.COMPLETED,
                actor=actor_id,
                details={"reason": f"Action '{action_id}' executed successfully with receipt '{receipt_id}'"},
            )

            # Log audit entry
            conn = self.task_repo._conn()
            try:
                self.task_repo._insert_audit(
                    conn=conn,
                    task_id=task.task_id,
                    business_id=business_id,
                    action_id=action_id,
                    actor=actor_id,
                    event_type="ACTION_EXECUTED",
                    details={
                        "receipt_id": receipt_id,
                        "provider": handler.provider_name,
                        "action_type": proposal.action_type,
                    },
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            return ExecutionReceipt(
                receipt_id=receipt_id,
                action_id=action_id,
                task_id=task.task_id,
                business_id=business_id,
                provider_name=handler.provider_name,
                status="COMPLETED",
                idempotency_key=proposal.idempotency_key,
                output_data=output_data,
            )

        except ExecutionUncertainError as e:
            err_msg = str(e)
            logger.warning(f"Execution outcome uncertain for action '{action_id}': {err_msg}")

            # Mark execution record as EXECUTION_UNCERTAIN
            self.task_repo.mark_execution_uncertain_record(
                execution_id=execution_id,
                reason=err_msg,
                business_id=business_id,
            )

            # Mark action & task as EXECUTION_UNCERTAIN
            self.task_repo.mark_execution_uncertain(
                action_id=action_id,
                business_id=business_id,
                task_id=task.task_id,
                actor=actor_id,
                reason=err_msg,
            )

            return ExecutionReceipt(
                receipt_id=execution_id,
                action_id=action_id,
                task_id=task.task_id,
                business_id=business_id,
                provider_name=handler.provider_name,
                status="EXECUTION_UNCERTAIN",
                idempotency_key=proposal.idempotency_key,
                error_message=err_msg,
            )

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Execution failed definitively for action '{action_id}': {err_msg}")

            # Mark execution record as FAILED
            self.task_repo.fail_execution(
                execution_id=execution_id,
                error_message=err_msg,
                business_id=business_id,
            )

            # Mark action proposal as FAILED
            conn = self.task_repo._conn()
            try:
                conn.execute(
                    "UPDATE autopilot_action_proposals SET execution_status = 'FAILED' WHERE action_id = ?",
                    (action_id,),
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            # Mark task as FAILED
            self.task_repo.transition_state(
                task_id=task.task_id,
                business_id=business_id,
                target_state=TaskState.FAILED,
                actor=actor_id,
                details={"reason": f"Action execution failed: {err_msg}"},
            )

            return ExecutionReceipt(
                receipt_id=execution_id,
                action_id=action_id,
                task_id=task.task_id,
                business_id=business_id,
                provider_name=handler.provider_name,
                status="FAILED",
                idempotency_key=proposal.idempotency_key,
                error_message=err_msg,
            )

    def reconcile_uncertain_action(
        self,
        action_id: str,
        business_id: str,
        actor_id: str,
        resolution: str,  # "CONFIRM_EXECUTED" or "CONFIRM_FAILED"
        notes: str,
    ) -> ExecutionReceipt:
        """
        Explicit owner-directed reconciliation for an action in EXECUTION_UNCERTAIN.
        Never retries automatically. Requires authenticated owner decision.
        """
        # Validate owner authorization
        if not self.policy_engine.is_authorized_owner(business_id, actor_id):
            raise UnauthorizedExecutionError(
                f"Actor '{actor_id}' is not an authorized owner for business '{business_id}'."
            )

        proposal = self.task_repo.get_action(action_id, business_id=business_id)
        if not proposal:
            raise ActionNotFoundError(f"Action '{action_id}' not found for business '{business_id}'.")

        task = self.task_repo.get_task(proposal.task_id, business_id=business_id)
        if not task:
            raise TaskNotFoundError(f"Parent task '{proposal.task_id}' not found.")

        exec_record = self.task_repo.get_execution_by_action(action_id, business_id=business_id)
        if not exec_record or exec_record["status"] != "EXECUTION_UNCERTAIN":
            raise ActionDispatcherError(
                f"Action '{action_id}' is not currently in EXECUTION_UNCERTAIN status."
            )

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        norm_res = (resolution or "").strip().upper()

        if norm_res == "CONFIRM_EXECUTED":
            sim_receipt_id = f"reconciled_{uuid.uuid4().hex[:12]}"
            self.task_repo.reconcile_execution_record(
                execution_id=exec_record["execution_id"],
                resolution="RECONCILED",
                notes=notes,
                actor_id=actor_id,
                business_id=business_id,
                receipt_id=sim_receipt_id,
            )

            # Update proposal
            conn = self.task_repo._conn()
            try:
                conn.execute(
                    "UPDATE autopilot_action_proposals SET execution_status = 'EXECUTED' WHERE action_id = ?",
                    (action_id,),
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            # Transition task to COMPLETED
            self.task_repo.transition_state(
                task_id=task.task_id,
                business_id=business_id,
                target_state=TaskState.COMPLETED,
                actor=actor_id,
                details={"reason": f"Action reconciled as EXECUTED by owner: {notes}"},
            )

            # Audit record
            conn = self.task_repo._conn()
            try:
                self.task_repo._insert_audit(
                    conn=conn,
                    task_id=task.task_id,
                    business_id=business_id,
                    action_id=action_id,
                    actor=actor_id,
                    event_type="EXECUTION_RECONCILED",
                    details={
                        "resolution": "CONFIRM_EXECUTED",
                        "notes": notes,
                        "receipt_id": sim_receipt_id,
                    },
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            return ExecutionReceipt(
                receipt_id=sim_receipt_id,
                action_id=action_id,
                task_id=task.task_id,
                business_id=business_id,
                provider_name=exec_record["provider_name"],
                status="RECONCILED",
                idempotency_key=proposal.idempotency_key,
                output_data={"reconciliation_notes": notes, "reconciled_by": actor_id},
            )

        elif norm_res == "CONFIRM_FAILED":
            self.task_repo.reconcile_execution_record(
                execution_id=exec_record["execution_id"],
                resolution="FAILED",
                notes=notes,
                actor_id=actor_id,
                business_id=business_id,
            )

            # Update proposal
            conn = self.task_repo._conn()
            try:
                conn.execute(
                    "UPDATE autopilot_action_proposals SET execution_status = 'FAILED' WHERE action_id = ?",
                    (action_id,),
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            # Transition task to FAILED
            self.task_repo.transition_state(
                task_id=task.task_id,
                business_id=business_id,
                target_state=TaskState.FAILED,
                actor=actor_id,
                details={"reason": f"Action reconciled as FAILED by owner: {notes}"},
            )

            # Audit record
            conn = self.task_repo._conn()
            try:
                self.task_repo._insert_audit(
                    conn=conn,
                    task_id=task.task_id,
                    business_id=business_id,
                    action_id=action_id,
                    actor=actor_id,
                    event_type="EXECUTION_RECONCILED",
                    details={
                        "resolution": "CONFIRM_FAILED",
                        "notes": notes,
                    },
                )
                conn.commit()
            finally:
                self.task_repo._close(conn)

            return ExecutionReceipt(
                receipt_id=exec_record["execution_id"],
                action_id=action_id,
                task_id=task.task_id,
                business_id=business_id,
                provider_name=exec_record["provider_name"],
                status="FAILED",
                idempotency_key=proposal.idempotency_key,
                output_data={"reconciliation_notes": notes, "reconciled_by": actor_id},
                error_message=notes,
            )

        else:
            raise ActionDispatcherError(
                f"Invalid reconciliation resolution '{resolution}'. Must be 'CONFIRM_EXECUTED' or 'CONFIRM_FAILED'."
            )
