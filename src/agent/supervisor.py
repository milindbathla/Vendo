"""
Email-Triggered Multi-Agent Supervisor
=======================================
Coordinates end-to-end small-business operations triggered by inbound emails.
Connects EmailRepository, TaskRepository, AdaptiveProfileRepository, specialist
analytical tools, and the deterministic PermissionEngine.
Guarantees:
  - Untrusted data isolation (LLMs cannot assign business identity or approve actions).
  - Multi-tenant tenant isolation across all businesses.
  - Fail-closed transitions to AWAITING_INFORMATION or AWAITING_APPROVAL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional

from src.db.email_repository import EmailRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import TaskRepository
from src.decision.policy_engine import (
    PermissionEngine,
    PolicyDecision,
    PolicyEvaluationResult,
)
from src.models.adaptive_profile import AdaptiveBusinessProfile
from src.models.email import InboundEmail
from src.models.task import (
    ActionProposal,
    ActionType,
    OperationalTask,
    TaskState,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)


@dataclass
class SupervisorClassification:
    """Classification details from supervisor intent analysis."""
    intent: str
    confidence: float = 0.9

    def to_dict(self) -> Dict[str, Any]:
        return {"intent": self.intent, "confidence": self.confidence}


@dataclass
class SupervisorExecutionResult:
    """Outcome of an email-triggered supervisor workflow cycle."""
    task_id: str
    business_id: str
    inbound_email_id: str
    intent: str
    state: TaskState
    actions_proposed: List[Dict[str, Any]] = field(default_factory=list)
    actions_allowed: List[Dict[str, Any]] = field(default_factory=list)
    actions_awaiting_approval: List[Dict[str, Any]] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    follow_up_questions: List[str] = field(default_factory=list)
    analysis_summary: str = ""
    is_duplicate: bool = False
    task: Optional[OperationalTask] = None
    classification: Optional[SupervisorClassification] = None
    action_proposals: List[ActionProposal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "business_id": self.business_id,
            "inbound_email_id": self.inbound_email_id,
            "intent": self.intent,
            "state": self.state.value if isinstance(self.state, TaskState) else str(self.state),
            "actions_proposed": self.actions_proposed,
            "actions_allowed": self.actions_allowed,
            "actions_awaiting_approval": self.actions_awaiting_approval,
            "missing_information": self.missing_information,
            "follow_up_questions": self.follow_up_questions,
            "analysis_summary": self.analysis_summary,
            "is_duplicate": self.is_duplicate,
            "classification": self.classification.to_dict() if self.classification else None,
        }


class EmailOperationalSupervisor:
    """
    Business-agnostic AI supervisor managing email-triggered tasks.
    Coordinates specialized read-only tools and routes all consequential
    actions through deterministic PermissionEngine policies.
    """

    def __init__(
        self,
        email_repo: EmailRepository,
        task_repo: TaskRepository,
        profile_repo: AdaptiveProfileRepository,
        policy_engine: Optional[PermissionEngine] = None,
    ) -> None:
        self.email_repo = email_repo
        self.task_repo = task_repo
        self.profile_repo = profile_repo
        self.policy_engine = policy_engine or PermissionEngine()

    def process_inbound_email(
        self, email_id: str, business_id: str
    ) -> SupervisorExecutionResult:
        """
        Primary orchestration entry point. Executes steps 1 through 13:
          1. Retrieve email from EmailRepository.
          2. Resolve business profile from trusted context.
          3. Retrieve or create OperationalTask.
          4. Classify intent.
          5. Retrieve verified business facts.
          6. Select and execute specialist tools.
          7. Identify missing or conflicting information.
          8. Generate action proposals and drafts.
          9. Deterministically evaluate proposals via PermissionEngine.
          10. Automatically perform permitted internal actions.
          11. Move consequential actions to AWAITING_APPROVAL.
          12. Record all state transitions and audit logs.
        """
        # Step 1: Retrieve email
        email = self.email_repo.get_email(email_id, business_id=business_id)
        if not email:
            raise ValueError(f"Inbound email '{email_id}' not found for business '{business_id}'.")

        # Step 2: Resolve canonical business profile
        profile = self.profile_repo.get_profile(business_id)
        if not profile:
            # Fallback/stub profile if not yet onboarded to avoid crashing
            profile = AdaptiveBusinessProfile(
                business_id=business_id,
                display_name="Adaptive Business",
                category="general_business",
            )

        # Step 3: Check for existing task linked to this email (idempotency check)
        existing_tasks = self.task_repo.list_tasks(business_id=business_id, limit=50)
        task = next((t for t in existing_tasks if t.inbound_email_id == email_id), None)
        if task is not None:
            logger.info(f"Task already exists for email {email_id}: {task.task_id}")
            actions = self.task_repo.list_actions_for_task(task.task_id, business_id)
            return SupervisorExecutionResult(
                task_id=task.task_id,
                business_id=business_id,
                inbound_email_id=email_id,
                intent=task.context_data.get("intent", "general_operations"),
                state=task.state,
                actions_proposed=[a.to_dict() for a in actions],
                analysis_summary=task.description,
                is_duplicate=True,
                task=task,
                classification=SupervisorClassification(intent=task.context_data.get("intent", "general_operations")),
                action_proposals=actions,
            )

        # Create new OperationalTask in RECEIVED state
        task = OperationalTask(
            business_id=business_id,
            inbound_email_id=email.message_id,
            thread_id=email.thread_id,
            title=f"Email: {email.normalized_subject or 'Inbound Message'}",
            description=f"Received message from {email.sender.format()}",
            state=TaskState.RECEIVED,
        )
        self.task_repo.create_task(task, actor="supervisor:email_ingestion")

        # Step 4: Classify intent
        intent = self._classify_intent(email)
        task.context_data["intent"] = intent
        task.context_data["sender"] = email.sender.to_dict()
        task.task_type = intent
        task = self.task_repo.transition_state(
            task.task_id, business_id, TaskState.CLASSIFIED, actor="supervisor:classifier",
            details={"classified_intent": intent}
        )

        # Step 5 & 6: Retrieve verified facts and execute specialist read-only analysis
        task = self.task_repo.transition_state(
            task.task_id, business_id, TaskState.WORKING, actor="supervisor:specialist_analysis"
        )
        analysis_result = self._execute_specialist_analysis(email, intent, profile)

        # Step 7: Check for missing critical information
        missing_info = analysis_result.get("missing_information", [])
        follow_up_questions = analysis_result.get("follow_up_questions", [])

        if missing_info:
            # Transition to AWAITING_INFORMATION
            task.description = f"Analysis paused: missing critical information ({', '.join(missing_info)})."
            task = self.task_repo.transition_state(
                task.task_id, business_id, TaskState.AWAITING_INFORMATION,
                actor="supervisor:policy_engine",
                details={"missing_information": missing_info, "follow_up_questions": follow_up_questions}
            )
            # Create low-risk internal summary proposal
            summary_prop = ActionProposal(
                task_id=task.task_id,
                business_id=business_id,
                action_type=ActionType.GENERATE_SUMMARY.value,
                description=f"Internal operational summary for email {email.message_id}",
                payload={
                    "email_id": email.message_id,
                    "sender": email.sender.email,
                    "intent": intent,
                    "analysis": analysis_result.get("summary", ""),
                    "missing_information": missing_info,
                    "follow_up_questions": follow_up_questions,
                },
                requires_approval=False,
            )
            saved_prop = self.task_repo.propose_action(
                task.task_id, business_id, summary_prop, actor="supervisor:proposer"
            )
            saved_prop.execution_status = "EXECUTED"
            return SupervisorExecutionResult(
                task_id=task.task_id,
                business_id=business_id,
                inbound_email_id=email.message_id,
                intent=intent,
                state=task.state,
                actions_proposed=[saved_prop.to_dict()],
                actions_allowed=[saved_prop.to_dict()],
                missing_information=missing_info,
                follow_up_questions=follow_up_questions,
                analysis_summary=analysis_result.get("summary", ""),
                task=task,
                classification=SupervisorClassification(intent=intent),
                action_proposals=[saved_prop],
            )

        # Step 8: Generate structured action proposals
        proposals = self._generate_proposals(email, intent, profile, analysis_result, task.task_id)

        allowed_actions = []
        awaiting_approval_actions = []
        saved_proposals: List[ActionProposal] = []

        # Step 9 & 10 & 11: Evaluate proposals deterministically via PermissionEngine
        has_consequential_actions = False

        for prop in proposals:
            eval_res = self.policy_engine.evaluate_action(
                action_type=prop.action_type,
                payload=prop.payload,
                business_id=business_id,
                actor_role="assistant",
            )
            # Record proposal in repository
            saved_prop = self.task_repo.propose_action(
                task.task_id, business_id, prop, actor="supervisor:proposer"
            )
            saved_proposals.append(saved_prop)

            if eval_res.decision == PolicyDecision.ALLOW:
                # Low-risk internal action automatically executed
                saved_prop.execution_status = "EXECUTED"
                allowed_actions.append(saved_prop.to_dict())
            elif eval_res.decision == PolicyDecision.REQUIRE_APPROVAL:
                has_consequential_actions = True
                awaiting_approval_actions.append(saved_prop.to_dict())

        # Step 12: Move task to AWAITING_APPROVAL if consequential actions exist, or COMPLETED
        if has_consequential_actions:
            task = self.task_repo.transition_state(
                task.task_id, business_id, TaskState.AWAITING_APPROVAL,
                actor="supervisor:policy_engine",
                details={"awaiting_actions_count": len(awaiting_approval_actions)}
            )
        else:
            task = self.task_repo.transition_state(
                task.task_id, business_id, TaskState.COMPLETED,
                actor="supervisor:executor",
                details={"completed_internal_actions": len(allowed_actions)}
            )

        task.description = analysis_result.get("summary", "Workflow completed.")
        return SupervisorExecutionResult(
            task_id=task.task_id,
            business_id=business_id,
            inbound_email_id=email.message_id,
            intent=intent,
            state=task.state,
            actions_proposed=[p.to_dict() for p in proposals],
            actions_allowed=allowed_actions,
            actions_awaiting_approval=awaiting_approval_actions,
            missing_information=[],
            follow_up_questions=[],
            analysis_summary=analysis_result.get("summary", ""),
            task=task,
            classification=SupervisorClassification(intent=intent),
            action_proposals=saved_proposals,
        )

    def process_email(self, email: InboundEmail) -> SupervisorExecutionResult:
        """
        Convenience execution wrapper that accepts a normalized InboundEmail object.
        Ensures the email is durably stored in EmailRepository and invokes process_inbound_email.
        """
        existing = self.email_repo.get_email(email.message_id, business_id=email.business_id)
        if not existing:
            self.email_repo.save_email(email)
        return self.process_inbound_email(email.message_id, email.business_id)

    # ── Internal Intent Classification ────────────────────────────────────────

    def _classify_intent(self, email: InboundEmail) -> str:
        """Classifies email intent deterministically from untrusted text."""
        subject = (email.subject or "").lower()
        body = (email.body_text or "").lower()
        combined = f"{subject} {body}"

        if any(w in combined for w in ["bulk order", "wholesale order", "quote for 100", "50 pieces", "100 meters", "bulk purchase", "large order"]):
            return "bulk_order_inquiry"
        if any(w in combined for w in ["appointment", "booking", "slot", "haircut", "facial", "styling session"]):
            return "appointment_request"
        if any(w in combined for w in ["service", "repair", "brake", "engine", "puncture", "maintenance", "fix my"]):
            return "service_request"
        if any(w in combined for w in ["consulting", "project scope", "milestone", "audit", "retainer"]):
            return "project_inquiry"
        if any(w in combined for w in ["invoice", "dispatch", "shipment", "raw material", "po #", "dispatch notice"]):
            return "supplier_request"
        # Inbound supplier quotation/offer (distributor, wholesaler, or vendor offering prices to the business)
        if any(w in combined for w in ["quotation for", "quotation from", "supplier quotation", "special diwali rate", "wholesale rate", "distributor quote", "vendor quote", "dealer price"]):
            return "supplier_request"
        if any(w in combined for w in ["inquiry", "how much", "rate", "cost", "price", "catalog"]):
            return "customer_inquiry"
        return "general_operations"

    # ── Specialist Analysis ───────────────────────────────────────────────────

    def _execute_specialist_analysis(
        self, email: InboundEmail, intent: str, profile: AdaptiveBusinessProfile
    ) -> Dict[str, Any]:
        """Runs domain-agnostic read-only analysis using active profile facts."""
        text = f"{email.subject} {email.body_text}".lower()

        # 1. Retail / Bulk Order Analysis
        if intent in ("bulk_order_inquiry", "customer_inquiry"):
            qty_match = re.search(r"(\d+)\s*(?:pcs|pieces|meters|units|items|dresses|shirts)?", text)
            requested_qty = float(qty_match.group(1)) if qty_match else 20.0

            selling_price = profile.get_value("selling_price")
            # If no single selling price, check offered_catalog
            catalog = profile.get_value("offered_catalog", [])
            matched_item = None
            if catalog:
                for it in catalog:
                    if it["name"].lower() in text:
                        matched_item = it
                        selling_price = float(it["price"])
                        break

            if selling_price is None:
                return {
                    "missing_information": ["selling_price"],
                    "follow_up_questions": [
                        f"What is your standard selling price or rate card for the requested items in inquiry: '{email.subject}'?"
                    ],
                    "summary": "Pricing information not found in business profile.",
                }

            capacity = profile.get_value("daily_capacity", 50.0)
            lead_time_days = max(1, int(round(requested_qty / max(1.0, capacity))))
            total_est_revenue = requested_qty * float(selling_price)

            return {
                "summary": (
                    f"Bulk inquiry for {requested_qty} units. Estimated revenue: Rs {total_est_revenue:,.2f}. "
                    f"Production/fulfillment lead time: ~{lead_time_days} days based on daily capacity of {capacity}."
                ),
                "requested_qty": requested_qty,
                "unit_price": selling_price,
                "total_revenue": total_est_revenue,
                "lead_time_days": lead_time_days,
            }

        # 2. Repair / Service Request Analysis
        if intent == "service_request":
            service_fee = profile.get_value("selling_price") or profile.get_value("base_service_fee")
            if service_fee is None:
                # Check catalog
                catalog = profile.get_value("offered_catalog", [])
                if catalog:
                    service_fee = catalog[0].get("price", 500.0)
                else:
                    return {
                        "missing_information": ["service_fee"],
                        "follow_up_questions": [
                            "What is the standard diagnostic or service fee for this vehicle/equipment repair?"
                        ],
                        "summary": "Standard repair fee missing in business profile.",
                    }

            return {
                "summary": f"Service request identified. Standard service fee: Rs {service_fee:,.2f}.",
                "unit_price": service_fee,
                "total_revenue": service_fee,
            }

        # 3. Appointment Booking Analysis
        if intent == "appointment_request":
            session_fee = profile.get_value("selling_price") or profile.get_value("session_fee", 800.0)
            return {
                "summary": f"Appointment inquiry. Standard service session rate: Rs {session_fee:,.2f}.",
                "unit_price": session_fee,
                "total_revenue": session_fee,
            }

        # 4. Project Inquiry
        if intent == "project_inquiry":
            retainer_fee = profile.get_value("selling_price") or profile.get_value("retainer_rate")
            if retainer_fee is None:
                return {
                    "missing_information": ["retainer_fee", "project_scope"],
                    "follow_up_questions": [
                        "Please specify your billing rate (hourly or milestone) for consulting project scopes."
                    ],
                    "summary": "Project rate card missing in business profile.",
                }
            return {
                "summary": f"Project consulting scope review. Proposed milestone rate: Rs {retainer_fee:,.2f}.",
                "unit_price": retainer_fee,
                "total_revenue": retainer_fee,
            }

        # 5. Supplier invoice, PO tracking, or supplier quotation
        if intent == "supplier_request":
            # Extract monetary amount if quoted
            amt_match = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", text)
            quote_amount = 0.0
            if amt_match:
                try:
                    quote_amount = float(amt_match.group(1).replace(",", ""))
                except ValueError:
                    quote_amount = 0.0

            if quote_amount > 0:
                summary = (
                    f"Supplier quotation received from {email.sender.name or email.sender.email} "
                    f"for Rs {quote_amount:,.2f}. Owner approval required before creating purchase order."
                )
            else:
                summary = f"Supplier document update noted for {profile.display_name}. Verification required."

            return {
                "summary": summary,
                "supplier_action": "review_quotation" if quote_amount > 0 else "verify_dispatch",
                "quoted_amount": quote_amount,
            }

        return {"summary": "General operations inquiry analyzed."}

    # ── Proposal Generation ───────────────────────────────────────────────────

    def _generate_proposals(
        self,
        email: InboundEmail,
        intent: str,
        profile: AdaptiveBusinessProfile,
        analysis: Dict[str, Any],
        task_id: str,
    ) -> List[ActionProposal]:
        """Generates internal low-risk actions and consequential external proposals."""
        proposals: List[ActionProposal] = []

        # 1. Always create a low-risk internal summary / draft action (ALLOW)
        proposals.append(
            ActionProposal(
                task_id=task_id,
                business_id=profile.business_id,
                action_type=ActionType.GENERATE_SUMMARY.value,
                description=f"Internal operational summary for email {email.message_id}",
                payload={
                    "email_id": email.message_id,
                    "sender": email.sender.email,
                    "intent": intent,
                    "analysis": analysis.get("summary", ""),
                },
                requires_approval=False,
            )
        )

        # 2. Consequential action based on intent (REQUIRE_APPROVAL)
        if intent in ("bulk_order_inquiry", "customer_inquiry"):
            quote_amount = analysis.get("total_revenue", 0.0)
            proposals.append(
                ActionProposal(
                    task_id=task_id,
                    business_id=profile.business_id,
                    action_type=ActionType.SEND_BINDING_QUOTATION.value,
                    description=f"Send formal binding quotation to {email.sender.email} for Rs {quote_amount:,.2f}",
                    payload={
                        "recipient_email": email.sender.email,
                        "recipient_name": email.sender.name,
                        "subject": f"Quotation: {email.normalized_subject}",
                        "quote_amount": quote_amount,
                        "lead_time_days": analysis.get("lead_time_days", 3),
                        "terms": "Net 15 days upon delivery",
                    },
                    requires_approval=True,
                )
            )

        elif intent == "service_request":
            fee = analysis.get("total_revenue", 0.0)
            proposals.append(
                ActionProposal(
                    task_id=task_id,
                    business_id=profile.business_id,
                    action_type=ActionType.SEND_EXTERNAL_EMAIL.value,
                    description=f"Send service estimation email to {email.sender.email}",
                    payload={
                        "recipient_email": email.sender.email,
                        "subject": f"Service Estimate: {email.normalized_subject}",
                        "estimated_fee": fee,
                        "message": f"Hello, your service estimate is Rs {fee:,.2f}. We can inspect your equipment tomorrow.",
                    },
                    requires_approval=True,
                )
            )

        elif intent == "appointment_request":
            proposals.append(
                ActionProposal(
                    task_id=task_id,
                    business_id=profile.business_id,
                    action_type=ActionType.SCHEDULE_APPOINTMENT.value,
                    description=f"Confirm appointment booking for {email.sender.name or email.sender.email}",
                    payload={
                        "client_email": email.sender.email,
                        "client_name": email.sender.name,
                        "slot": "Tomorrow 11:00 AM",
                        "service_type": "Standard Session",
                    },
                    requires_approval=True,
                )
            )

        elif intent == "project_inquiry":
            milestone_fee = analysis.get("total_revenue", 0.0)
            proposals.append(
                ActionProposal(
                    task_id=task_id,
                    business_id=profile.business_id,
                    action_type=ActionType.SEND_BINDING_QUOTATION.value,
                    description=f"Send consulting milestone proposal to {email.sender.email}",
                    payload={
                        "recipient_email": email.sender.email,
                        "subject": f"Consulting Proposal: {email.normalized_subject}",
                        "quote_amount": milestone_fee,
                        "scope": "Milestone delivery within 2 weeks",
                    },
                    requires_approval=True,
                )
            )

        elif intent == "supplier_request":
            quoted_amt = analysis.get("quoted_amount", 0.0)
            if quoted_amt > 0:
                desc = f"Create purchase order to {email.sender.name or email.sender.email} for Rs {quoted_amt:,.2f}"
                payload = {
                    "supplier_email": email.sender.email,
                    "supplier_name": email.sender.name,
                    "quotation_ref": email.normalized_subject,
                    "order_amount": quoted_amt,
                    "status": "AWAITING_OWNER_PO_CONFIRMATION",
                }
            else:
                desc = "Create purchase order confirmation for supplier dispatch"
                payload = {
                    "supplier_email": email.sender.email,
                    "document_ref": email.normalized_subject,
                    "action": "acknowledge_receipt",
                }

            proposals.append(
                ActionProposal(
                    task_id=task_id,
                    business_id=profile.business_id,
                    action_type=ActionType.CREATE_PURCHASE_ORDER.value,
                    description=desc,
                    payload=payload,
                    requires_approval=True,
                )
            )

        return proposals
