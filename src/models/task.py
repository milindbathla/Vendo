"""
Operational Task and Action Proposal Models
============================================
Defines the stateful task lifecycle, structured action proposals, immutable
payload hashes, and deterministic policy decision types for Amazon Business Autopilot.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
import uuid


class TaskState(str, Enum):
    """Lifecycle states of an autonomous small-business operational task."""
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    PLANNING = "PLANNING"
    WORKING = "WORKING"
    AWAITING_INFORMATION = "AWAITING_INFORMATION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN"


# Valid state transitions lookup table
VALID_TRANSITIONS: Dict[TaskState, set[TaskState]] = {
    TaskState.RECEIVED: {
        TaskState.CLASSIFIED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.CLASSIFIED: {
        TaskState.PLANNING,
        TaskState.WORKING,
        TaskState.AWAITING_INFORMATION,
        TaskState.AWAITING_APPROVAL,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.PLANNING: {
        TaskState.WORKING,
        TaskState.AWAITING_INFORMATION,
        TaskState.AWAITING_APPROVAL,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WORKING: {
        TaskState.PLANNING,
        TaskState.AWAITING_INFORMATION,
        TaskState.AWAITING_APPROVAL,
        TaskState.EXECUTING,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.AWAITING_INFORMATION: {
        TaskState.PLANNING,
        TaskState.WORKING,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.AWAITING_APPROVAL: {
        TaskState.EXECUTING,
        TaskState.REJECTED,
        TaskState.CANCELLED,
        TaskState.PLANNING,
    },
    TaskState.EXECUTING: {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.EXECUTION_UNCERTAIN,
    },
    TaskState.EXECUTION_UNCERTAIN: {
        TaskState.COMPLETED,
        TaskState.FAILED,
    },
    # Terminal states (no transitions allowed)
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.REJECTED: set(),
    TaskState.CANCELLED: set(),
}


class ActionType(str, Enum):
    """Categorization of actions into safe low-risk and consequential categories."""
    # Predefined low-risk internal actions (ALLOW)
    CLASSIFY_TASK = "classify_task"
    CREATE_INTERNAL_TASK = "create_internal_task"
    RETRIEVE_INFORMATION = "retrieve_information"
    GENERATE_SUMMARY = "generate_summary"
    CREATE_INTERNAL_DRAFT = "create_internal_draft"

    # Consequential actions requiring authenticated owner approval (REQUIRE_APPROVAL)
    SEND_EXTERNAL_EMAIL = "send_external_email"
    SEND_BINDING_QUOTATION = "send_binding_quotation"
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    CREATE_PURCHASE_ORDER = "create_purchase_order"
    EXECUTE_PAYMENT = "execute_payment"
    ISSUE_REFUND = "issue_refund"
    MODIFY_CONFIRMED_FACT = "modify_confirmed_fact"


class PolicyDecision(str, Enum):
    """Deterministic policy engine decision."""
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """
    Computes a canonical SHA-256 hash of a payload dictionary.
    Keys are sorted and data is formatted strictly to prevent hash alteration.
    """
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class ActionProposal:
    """
    Structured action proposal with immutable payload hash.
    Execution is strictly bound to this exact payload hash.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    business_id: str = ""
    action_type: str = ""
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_hash: str = ""
    requires_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    execution_status: str = "PROPOSED"  # PROPOSED, APPROVED, REJECTED, EXECUTED, FAILED, UNCERTAIN
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def __post_init__(self) -> None:
        if not self.payload_hash:
            self.payload_hash = compute_payload_hash(self.payload)

    def verify_integrity(self, candidate_payload: Dict[str, Any]) -> bool:
        """Verifies that the candidate payload matches the proposal's immutable hash."""
        return compute_payload_hash(candidate_payload) == self.payload_hash

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionProposal":
        return cls(**data)


@dataclass
class OperationalTask:
    """
    Persistent operational task linked to business and incoming email.
    Supports lifecycle tracking and optimistic concurrency via versioning.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    business_id: str = ""
    inbound_email_id: Optional[str] = None
    thread_id: Optional[str] = None
    title: str = ""
    description: str = ""
    task_type: str = "general_operations"
    state: TaskState = TaskState.RECEIVED
    context_data: Dict[str, Any] = field(default_factory=dict)
    proposed_actions: List[str] = field(default_factory=list)  # list of action_id
    version: int = 1
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def can_transition_to(self, target_state: TaskState) -> bool:
        """Validates if transition from current state to target state is permissible."""
        return target_state in VALID_TRANSITIONS.get(self.state, set())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, TaskState) else str(self.state)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationalTask":
        d = dict(data)
        d["state"] = TaskState(d["state"])
        return cls(**d)
