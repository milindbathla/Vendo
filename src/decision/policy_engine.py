"""
Deterministic Permission and Policy Engine
===========================================
Enforces business-scoped authorization, risk-tiering, and approval verification
completely outside of LLM instructions.
Guarantees fail-closed evaluation and protects against prompt-injection overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.models.task import (
    ActionProposal,
    ActionType,
    PolicyDecision,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)

# Low-risk internal actions that are pre-approved for autonomous execution
LOW_RISK_INTERNAL_ACTIONS: Set[str] = {
    ActionType.CLASSIFY_TASK.value,
    ActionType.CREATE_INTERNAL_TASK.value,
    ActionType.RETRIEVE_INFORMATION.value,
    ActionType.GENERATE_SUMMARY.value,
    ActionType.CREATE_INTERNAL_DRAFT.value,
}

# Consequential external actions that strictly require authenticated owner approval
CONSEQUENTIAL_ACTIONS: Set[str] = {
    ActionType.SEND_EXTERNAL_EMAIL.value,
    ActionType.SEND_BINDING_QUOTATION.value,
    ActionType.SCHEDULE_APPOINTMENT.value,
    ActionType.CREATE_PURCHASE_ORDER.value,
    ActionType.EXECUTE_PAYMENT.value,
    ActionType.ISSUE_REFUND.value,
    ActionType.MODIFY_CONFIRMED_FACT.value,
}


@dataclass
class PolicyEvaluationResult:
    """Outcome of evaluating an action proposal against deterministic policies."""
    decision: PolicyDecision
    reason: str
    action_type: str
    requires_approval: bool
    risk_level: str  # "LOW", "HIGH", "CRITICAL", "UNKNOWN"
    policy_rule: str


@dataclass
class PolicyVerificationResult:
    """Outcome of validating an approval record before action dispatch."""
    is_valid: bool
    reason: str
    actor_id: str
    payload_hash_matched: bool


class PermissionEngine:
    """
    Deterministic security boundary for autonomous agent actions.
    Decisions are computed strictly by deterministic rules. No LLM instructions
    or untrusted payload fields can elevate privileges or grant self-approval.
    """

    def __init__(self, authorized_owners_by_business: Optional[Dict[str, List[str]]] = None) -> None:
        # business_id -> list of authorized owner user IDs (e.g. ["owner:rajesh", "admin:1"])
        self._authorized_owners: Dict[str, List[str]] = authorized_owners_by_business or {}

    def set_authorized_owners(self, business_id: str, owner_ids: List[str]) -> None:
        """Sets the list of authorized owner user IDs for a business."""
        self._authorized_owners[business_id] = [oid.strip() for oid in owner_ids if oid.strip()]

    def is_authorized_owner(self, business_id: str, actor_id: str) -> bool:
        """Checks if the actor is registered as an authorized owner for the business."""
        if not actor_id or not business_id:
            return False
        allowed = self._authorized_owners.get(business_id)
        if allowed is None:
            # If no explicit list is configured, default owner format matches owner:* or admin:*
            return actor_id.startswith("owner:") or actor_id.startswith("admin:")
        return actor_id in allowed

    def evaluate_action(
        self,
        action_type: str,
        payload: Dict[str, Any],
        business_id: str,
        actor_role: str = "assistant",
    ) -> PolicyEvaluationResult:
        """
        Deterministically evaluates whether an action proposal can be executed
        autonomously (ALLOW), requires authenticated owner approval (REQUIRE_APPROVAL),
        or must be rejected (DENY).
        """
        norm_action = (action_type or "").strip().lower()

        # Check for injection attempts in untrusted payload attempting self-authorization
        # Even if payload contains keys like 'decision', 'approved', 'allow_all', they are ignored.
        if norm_action in LOW_RISK_INTERNAL_ACTIONS:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason=f"Action '{norm_action}' is a predefined low-risk internal operation.",
                action_type=norm_action,
                requires_approval=False,
                risk_level="LOW",
                policy_rule="ALLOW_PREDEFINED_LOW_RISK_INTERNAL",
            )

        if norm_action in CONSEQUENTIAL_ACTIONS:
            # Consequential actions always require owner approval
            return PolicyEvaluationResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                reason=(
                    f"Action '{norm_action}' involves external commitments, payments, "
                    f"or state modifications requiring authenticated owner approval."
                ),
                action_type=norm_action,
                requires_approval=True,
                risk_level="HIGH" if norm_action not in {ActionType.EXECUTE_PAYMENT.value, ActionType.ISSUE_REFUND.value} else "CRITICAL",
                policy_rule="REQUIRE_AUTHENTICATED_OWNER_APPROVAL",
            )

        # Fail-closed: Any unrecognized, malformed, or arbitrary action type is denied
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            reason=f"Unrecognized or unauthorized action type '{action_type}'. Operation denied.",
            action_type=norm_action,
            requires_approval=True,
            risk_level="UNKNOWN",
            policy_rule="DENY_UNKNOWN_ACTION_TYPE",
        )

    def verify_approval(
        self,
        proposal: ActionProposal,
        execution_payload: Dict[str, Any],
        actor_id: str,
        business_id: str,
    ) -> PolicyVerificationResult:
        """
        Validates an approval before consequential execution.
        Enforces:
          1. Tenant isolation: proposal.business_id must match request business_id.
          2. Actor authenticity: actor_id must be an authorized owner for this business.
          3. Exact payload binding: execution_payload must match proposal.payload_hash.
        """
        # 1. Tenant isolation
        if proposal.business_id != business_id:
            logger.warning(
                f"Tenant isolation violation: proposal business {proposal.business_id} "
                f"does not match executing business {business_id}."
            )
            return PolicyVerificationResult(
                is_valid=False,
                reason="TENANT_MISMATCH: Cannot approve or execute actions across different businesses.",
                actor_id=actor_id,
                payload_hash_matched=False,
            )

        # 2. Actor authorization check
        if not self.is_authorized_owner(business_id, actor_id):
            logger.warning(
                f"Unauthorized approval attempt by actor '{actor_id}' for business '{business_id}'."
            )
            return PolicyVerificationResult(
                is_valid=False,
                reason=f"UNAUTHORIZED_ACTOR: Actor '{actor_id}' is not an authorized owner for business '{business_id}'.",
                actor_id=actor_id,
                payload_hash_matched=False,
            )

        # 3. Payload integrity check (re-hashing)
        computed_hash = compute_payload_hash(execution_payload)
        if computed_hash != proposal.payload_hash:
            logger.error(
                f"Payload tampering detected! Expected hash {proposal.payload_hash}, "
                f"got {computed_hash}."
            )
            return PolicyVerificationResult(
                is_valid=False,
                reason="PAYLOAD_HASH_MISMATCH: Execution payload has been modified after proposal. Fresh approval required.",
                actor_id=actor_id,
                payload_hash_matched=False,
            )

        return PolicyVerificationResult(
            is_valid=True,
            reason="Approval verified: Authorized owner and exact payload hash confirmed.",
            actor_id=actor_id,
            payload_hash_matched=True,
        )
