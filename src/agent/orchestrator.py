"""
Adaptive Business AI Orchestrator
===================================
Coordinates between dynamic business profiles, prerequisite validation,
specialist agents, external integrations, and the two-phase approval workflow.
Ensures tiffin-specific assumptions are never applied to other verticals.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional
import uuid

from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)
from src.agent.onboarding import AdaptiveBusinessOnboarder
from src.db.profile_repository import AdaptiveProfileRepository
from src.decision.approval_service import PurchaseApprovalService, PlanStatus
from src.integrations.google_places import GooglePlacesAdapter
from src.integrations.zoho_books import ZohoBooksAdapter
from src.db.task_repository import (
    TaskRepository,
    ActionProposal,
    OperationalTask,
    TaskState,
)
from src.db.email_repository import EmailRepository
from src.db.session_repository import (
    SessionRepository,
    SessionNotFoundError,
    SessionExpiredError,
    SessionRevokedError,
    SessionAccessDeniedError,
)
from src.models.session import ConversationSession
from src.decision.policy_engine import PermissionEngine, PolicyDecision
from src.decision.action_dispatcher import ActionDispatcher, ExecutionReceipt
from src.models.email import InboundEmail, EmailAddress
from src.models.task import ActionType

logger = logging.getLogger(__name__)


class AdaptiveBusinessOrchestrator:
    """
    Business-agnostic AI orchestrator that dynamically coordinates business profiles,
    prerequisite validation, operational task lifecycles, permission verification,
    specialist analytical tools, and simulated action execution.
    """

    def __init__(
        self,
        repo: AdaptiveProfileRepository,
        approval_service: Optional[PurchaseApprovalService] = None,
        places_adapter: Optional[GooglePlacesAdapter] = None,
        zoho_adapter: Optional[ZohoBooksAdapter] = None,
        task_repo: Optional[TaskRepository] = None,
        email_repo: Optional[EmailRepository] = None,
        supervisor: Optional[Any] = None,
        action_dispatcher: Optional[ActionDispatcher] = None,
        policy_engine: Optional[PermissionEngine] = None,
        session_repo: Optional[SessionRepository] = None,
        tiffin_service: Optional[Any] = None,
    ):
        self.repo = repo
        self.approvals = approval_service or PurchaseApprovalService()
        self.places = places_adapter or GooglePlacesAdapter()
        self.zoho = zoho_adapter or ZohoBooksAdapter()
        self.task_repo = task_repo
        self.email_repo = email_repo
        self.supervisor = supervisor
        self.action_dispatcher = action_dispatcher
        self.policy_engine = policy_engine or PermissionEngine()
        self.session_repo = session_repo
        self.tiffin_service = tiffin_service
        self._last_referenced_actions: Dict[str, List[ActionProposal]] = {}

    def _get_active_proposals_for_context(
        self,
        business_id: str,
        session_id: Optional[str] = None,
    ) -> List[ActionProposal]:
        """
        Safely retrieves the current ordered list of action proposals for the context.
        If session_id is provided and session_repo is connected, retrieves fresh proposals
        from task_repo matching session.referenced_action_ids in exact ordered sequence.
        Otherwise falls back to in-memory _last_referenced_actions or task_repo.list_pending_actions.
        """
        if session_id and self.session_repo and self.task_repo:
            try:
                sess = self.session_repo.get_session(session_id, business_id=business_id)
                if sess and sess.referenced_action_ids:
                    proposals = []
                    for aid in sess.referenced_action_ids:
                        act = self.task_repo.get_action(aid, business_id=business_id)
                        if act and act.execution_status == "PROPOSED":
                            proposals.append(act)
                    if proposals:
                        return proposals
            except Exception as e:
                logger.warning("Error fetching proposals from session %s: %s", session_id, e)

        # Fallback to in-memory cache or task_repo
        if self._last_referenced_actions.get(business_id):
            return self._last_referenced_actions[business_id]
        if self.task_repo:
            return self.task_repo.list_pending_actions(business_id=business_id)
        return []

    def handle_user_message(
        self,
        message: Optional[str] = None,
        business_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        user_message: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Primary entry point for user interaction. Dispatches to operational briefings,
        approval workflows, task management, onboarding, financial analysis,
        opportunity evaluation, or external scouts.
        Maintains persistent multi-turn session state across process restarts when session_id is provided.
        """
        effective_message = message if message is not None else (user_message or "")
        msg_lower = effective_message.lower()

        # Session validation & identity binding
        session: Optional[ConversationSession] = None
        if session_id and self.session_repo:
            try:
                session = self.session_repo.get_session(session_id)
            except Exception as e:
                return {"status": "ERROR", "error": f"Failed to retrieve session: {str(e)}"}

            if not session:
                return {
                    "status": "SESSION_NOT_FOUND",
                    "reply": f"Conversation session '{session_id}' was not found.",
                    "voice_summary": "Your conversation session could not be found.",
                }
            if not session.is_active:
                st = session.status if not session.is_expired else "EXPIRED"
                return {
                    "status": f"SESSION_{st}",
                    "reply": f"Conversation session '{session_id}' has {st.lower()}.",
                    "voice_summary": f"Your conversation session has {st.lower()}.",
                }

            # Enforce tenant binding
            if business_id and session.business_id != business_id:
                return {
                    "status": "CROSS_TENANT_ACCESS_DENIED",
                    "reply": f"Access denied: Session '{session_id}' belongs to business '{session.business_id}', not '{business_id}'.",
                    "voice_summary": "Access denied: session belongs to another business.",
                }
            if not business_id:
                business_id = session.business_id

            # Enforce owner identity if actor_id provided
            if actor_id and actor_id != session.owner_id and actor_id != session.subject:
                if not self.policy_engine.is_authorized_owner(business_id, actor_id):
                    return {
                        "status": "UNAUTHORIZED_SESSION_ACCESS",
                        "reply": f"Access denied: Actor '{actor_id}' is not authorized to access session '{session_id}'.",
                        "voice_summary": "You are not authorized to access this session.",
                    }

            # Record user turn
            session.add_turn(role="user", content=effective_message)
        elif not session_id and self.session_repo and business_id:
            try:
                owner = actor_id or f"owner:{business_id}"
                subj = actor_id or f"sub_{business_id}"
                session = self.session_repo.create_session(
                    business_id=business_id,
                    owner_id=owner,
                    subject=subj,
                    metadata={"source": "conversational_query"},
                )
                session.add_turn(role="user", content=effective_message)
            except Exception as e:
                logger.warning("Could not auto-create conversation session: %s", e)

        # Helper to attach session details and persist turns before return
        def _finalize_response(result: Dict[str, Any]) -> Dict[str, Any]:
            if session and self.session_repo:
                try:
                    # Update referenced action IDs if present in result
                    if result.get("pending_approvals"):
                        result_proposals = result["pending_approvals"]
                        act_ids = [p["action_id"] if isinstance(p, dict) else p.action_id for p in result_proposals]
                        session.set_referenced_actions(act_ids)
                    elif result.get("approvals"):
                        result_proposals = result["approvals"]
                        act_ids = [p["action_id"] if isinstance(p, dict) else p.action_id for p in result_proposals]
                        session.set_referenced_actions(act_ids)
                    elif result.get("status") in ("APPROVED_AND_EXECUTED", "REJECTED", "APPROVED") and "action_id" in result:
                        approved_id = result["action_id"]
                        rem_ids = [aid for aid in session.referenced_action_ids if aid != approved_id]
                        session.set_referenced_actions(rem_ids)
                        session.metadata.pop("focused_action_id", None)
                    elif result.get("proposal") and "action_id" in result:
                        session.metadata["focused_action_id"] = result["action_id"]
                        if not session.referenced_action_ids:
                            session.set_referenced_actions([result["action_id"]])

                    # Record assistant response turn
                    resp_content = result.get("voice_summary") or result.get("reply") or ""
                    session.add_turn(role="assistant", content=resp_content)
                    self.session_repo.save_session(session)
                    result["session_id"] = session.session_id
                    result["session_context_version"] = session.context_version
                except Exception as e:
                    logger.warning("Error finalizing session in orchestrator: %s", e)
            return result

        # 1. Resolve or create active profile
        profile = None
        if business_id:
            profile = self.repo.get_profile(business_id)

        target_biz = profile.business_id if profile else business_id

        # 2. Check for explicit operational/analytical requests first
        if target_biz is not None:
            # A. Operational Briefing / Attention / Focus
            if any(w in msg_lower for w in [
                "what should i focus", "what needs my attention", "what needs attention",
                "daily briefing", "briefing", "agenda", "today's priorities",
                "operational briefing", "summary of today", "what's pending", "what is pending",
                "focus on today", "focus on", "what should i do", "what appointments and preparations"
            ]):
                return _finalize_response(self.generate_daily_briefing(target_biz, actor_id=actor_id, session_id=session_id))

            # B. Pending Approvals List
            if any(w in msg_lower for w in [
                "pending approval", "pending proposals", "needs approval", "show approvals",
                "list approvals", "actions to approve", "proposals awaiting", "which approvals"
            ]):
                return _finalize_response(self.list_pending_approvals_summary(target_biz, session_id=session_id))

            # C. Conversational multi-turn proposal explanation
            if any(w in msg_lower for w in [
                "explain the first", "explain the second", "explain the third", "explain the",
                "explain proposal", "details of proposal", "tell me about proposal",
                "tell me more about", "explain that quote", "explain quote", "explain one",
                "explain that", "explain this", "tell me about the first", "tell me about the second",
                "tell me about the third"
            ]) or (msg_lower.startswith("explain") and any(w in msg_lower for w in ["first", "second", "third", "one", "proposal", "quote", "1", "2", "3", "action"])):
                return _finalize_response(self.handle_explain_proposal(target_biz, effective_message, session_id=session_id))

            # D. Conversational multi-turn approval
            if any(w in msg_lower for w in [
                "approve it", "approve proposal", "approve the quotation", "confirm proposal",
                "approve the quote", "execute proposal", "approve the first", "approve the second",
                "approve the third", "approve that", "approve this"
            ]) or (msg_lower.startswith("approve") and any(w in msg_lower for w in ["first", "second", "third", "one", "proposal", "quote", "1", "2", "3", "action", "it", "that"])):
                return _finalize_response(self.handle_approve_followup(target_biz, effective_message, actor_id=actor_id, session_id=session_id))

            # E. Conversational multi-turn rejection
            if any(w in msg_lower for w in [
                "reject it", "reject proposal", "decline proposal", "reject the quotation",
                "reject the first", "reject the second", "reject the third", "reject that",
                "decline the quote", "decline it"
            ]) or (msg_lower.startswith("reject") and any(w in msg_lower for w in ["first", "second", "third", "one", "proposal", "quote", "1", "2", "3", "action", "it", "that"])):
                return _finalize_response(self.handle_reject_followup(target_biz, effective_message, actor_id=actor_id, session_id=session_id))

            # F. Inbound supplier quote / message processing
            if any(w in msg_lower for w in [
                "supplier sent a quotation", "supplier quote", "quotation from",
                "inbound email", "supplier quotation", "received an email from"
            ]):
                return _finalize_response(self.process_operational_request(target_biz, effective_message, actor_id=actor_id, session_id=session_id))

            # G. Urgent operational tasks by domain
            if any(w in msg_lower for w in [
                "supplier follow-up", "customer repair", "client appointment",
                "upcoming work", "urgent task", "what is urgent", "what repairs need"
            ]):
                return _finalize_response(self.get_urgent_tasks_summary(target_biz))

        if profile is not None:

            # H. Profitability / Margin Inquiry
            if any(w in msg_lower for w in ["profit", "margin", "break-even", "breakeven", "how am i doing", "economics"]):
                return _finalize_response(self.analyze_profitability(profile))

            # I. Opportunity / New Orders / Job Evaluation
            if any(w in msg_lower for w in ["can i take", "more orders", "more jobs", "new client", "opportunity", "take on"]):
                # Extract additional quantity requested
                m = re.search(r"(\d+)\s*(?:more|additional)?\s*(?:orders|jobs|repairs|clients|customers|units|dresses|items|meals|tiffins|bikes)?", msg_lower)
                additional_qty = float(m.group(1)) if m else 5.0
                return _finalize_response(self.evaluate_opportunity(profile, additional_qty, user_question=effective_message))

            # J. Competitor Scout Inquiry
            if any(w in msg_lower for w in ["competitor", "nearby", "competition", "other shops", "places nearby"]):
                return _finalize_response(self.scout_competitors(profile))

            # K. Accounting & Invoice Inquiry
            if any(w in msg_lower for w in ["zoho", "invoice", "bills", "receivable", "accounting"]):
                return _finalize_response(self.get_accounting_status(profile))

        # 3. Check if intent is onboarding / fact update / profile answer
        onboarding_signals = [
            "i run", "i own", "my business is", "my shop is", "we offer",
            "we repair", "we sell", "actually", "update", "correction", "instead of",
            "charge is", "costs around", "can handle up to", "have rs", "cash",
            "safety buffer", "fixed expenses", "rent is", "spare parts", "consumables",
            "ticket is", "fee is", "monthly rent", "monthly expenses", "fixed overhead",
            "electricity", "overhead",
        ]
        probe_onboarder = AdaptiveBusinessOnboarder(profile=profile)
        has_extracted_facts = bool(
            probe_onboarder._extract_numeric_facts(effective_message)
            or probe_onboarder._extract_products(effective_message)
        )
        is_correction = any(w in msg_lower for w in [
            "actually", "correction", "change that to", "not", "update my", "instead of",
            "change to", "correct that to", "change price to", "corrected"
        ])
        has_onboarding_signal = any(sig in msg_lower for sig in onboarding_signals)

        is_onboarding_intent = (
            profile is None
            or not profile.onboarding_completed
            or is_correction
            or has_extracted_facts
            or has_onboarding_signal
        )

        if is_onboarding_intent:
            # If caller supplied a business_id but the profile doesn't exist yet,
            # pass that ID as a hint so we reuse it rather than generating a new one.
            onboarder = AdaptiveBusinessOnboarder(
                profile=profile,
                business_id_hint=business_id if (profile is None and business_id) else None,
            )
            result = onboarder.process_utterance(effective_message)
            # Persist updated profile
            self.repo.save_profile(onboarder.profile)
            return _finalize_response({
                "intent": "onboarding",
                "business_id": onboarder.profile.business_id,
                "display_name": onboarder.profile.display_name,
                "category": onboarder.profile.category,
                "reply": result["reply"],
                "next_question": result["next_question"],
                "missing_critical_facts": result["missing_critical_facts"],
                "extracted_facts": result["extracted_facts"],
                "corrections": result["corrections"],
                "onboarding_completed": onboarder.profile.onboarding_completed,
            })

        # E. General Business State Summary
        return _finalize_response(self.get_business_summary(profile))

    def _get_unit_label(self, category: str) -> str:
        """Returns domain-appropriate unit label."""
        if category in ("mechanical_repair", "electronics_repair"):
            return "jobs"
        elif category in ("clothing_retail", "tailoring_boutique"):
            return "garments"
        elif category == "salon_service":
            return "clients"
        elif category == "small_fabrication":
            return "fabrication jobs"
        elif category == "home_bakery":
            return "cakes/orders"
        elif category == "home_tiffin":
            return "tiffins"
        return "units"

    def analyze_profitability(self, profile: AdaptiveBusinessProfile) -> Dict[str, Any]:
        """
        Computes domain-agnostic contribution margin and break-even metrics.
        Fails safely with a targeted question if critical facts are missing.
        Never silently assumes unconfirmed inputs without explicit assumption labeling.
        """
        selling_price = profile.get_value("selling_price")
        unit_cost = profile.get_value("unit_material_cost", profile.get_value("supplier_unit_cost"))
        unit_name = self._get_unit_label(profile.category)

        # Prerequisite verification: price and direct cost are mandatory
        if selling_price is None:
            return {
                "status": "PREREQUISITES_MISSING",
                "missing_field": "selling_price",
                "reply": "To calculate profitability, I need your typical selling price or service fee. What do you charge per customer/unit?",
            }
        if unit_cost is None:
            return {
                "status": "PREREQUISITES_MISSING",
                "missing_field": "unit_material_cost",
                "reply": "To calculate your profit margin, what is your direct material or parts cost per unit/job?",
            }

        assumptions: List[str] = []
        if profile.is_confirmed("daily_fixed_cost"):
            fixed_cost = float(profile.get_value("daily_fixed_cost"))
        else:
            fixed_cost = float(profile.get_value("daily_fixed_cost", 250.0))
            assumptions.append(f"Daily fixed overhead assumed as Rs.{fixed_cost:.2f} (unconfirmed by owner)")

        if profile.is_confirmed("daily_capacity"):
            capacity = float(profile.get_value("daily_capacity"))
        else:
            capacity = float(profile.get_value("daily_capacity", 20.0))
            assumptions.append(f"Daily capacity assumed as {capacity:.0f} {unit_name}/day (unconfirmed by owner)")

        unit_margin = selling_price - unit_cost
        margin_pct = (unit_margin / selling_price) * 100.0 if selling_price > 0 else 0.0
        breakeven_units = math.ceil(fixed_cost / unit_margin) if unit_margin > 0 else float("inf")
        profit_at_capacity = (unit_margin * capacity) - fixed_cost

        reply_lines = [
            f"For {profile.display_name} ({profile.category.replace('_', ' ').title()}):",
            f"• Revenue per {unit_name[:-1] if unit_name.endswith('s') else unit_name}: Rs.{selling_price:.2f}",
            f"• Direct material/parts cost: Rs.{unit_cost:.2f}",
            f"• Contribution margin: Rs.{unit_margin:.2f} ({margin_pct:.1f}%)",
            f"• Break-even volume: {breakeven_units} {unit_name} per day (covering Rs.{fixed_cost:.2f} daily fixed overhead)",
            f"• Daily profit at full capacity ({capacity:.0f} {unit_name}/day): Rs.{profit_at_capacity:.2f}.",
        ]
        if assumptions:
            reply_lines.append(f"\n*Assumptions (unconfirmed)*: {'; '.join(assumptions)}.")

        return {
            "status": "SUCCESS",
            "intent": "profitability",
            "business_id": profile.business_id,
            "display_name": profile.display_name,
            "category": profile.category,
            "selling_price": selling_price,
            "revenue_per_unit": selling_price,
            "unit_cost": unit_cost,
            "contribution_margin": unit_margin,
            "margin_pct": round(margin_pct, 2),
            "breakeven_units_per_day": breakeven_units,
            "profit_at_capacity": round(profit_at_capacity, 2),
            "assumptions": assumptions,
            "reply": "\n".join(reply_lines),
        }

    def evaluate_opportunity(
        self,
        profile: AdaptiveBusinessProfile,
        additional_units: float,
        user_question: str = "",
        current_demand: Optional[float] = None,
        current_inventory: Optional[float] = None,
        total_cash: Optional[float] = None,
        daily_capacity: Optional[float] = None,
        safety_reserve: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates whether a business can take on additional demand.
        Uses universal constraints: capacity limit, inventory shortages, and usable cash.
        Never calls tiffin recipes for non-tiffin businesses.
        """
        capacity = daily_capacity if daily_capacity is not None else profile.get_value("daily_capacity")
        unit_cost = profile.get_value("unit_material_cost", profile.get_value("supplier_unit_cost"))
        unit_name = self._get_unit_label(profile.category)

        # Check required prerequisites: capacity and unit cost are strictly required
        if capacity is None:
            return {
                "status": "PREREQUISITES_MISSING",
                "missing_field": "daily_capacity",
                "reply": f"To evaluate if you can take this extra work, what is your maximum daily capacity in {unit_name}?",
            }
        if unit_cost is None:
            return {
                "status": "PREREQUISITES_MISSING",
                "missing_field": "unit_material_cost",
                "reply": f"What is your direct material or parts cost per {unit_name[:-1] if unit_name.endswith('s') else unit_name} so I can verify affordability?",
            }

        assumptions: List[str] = []
        if current_inventory is not None:
            current_inv = float(current_inventory)
        else:
            current_inv = float(profile.get_value("current_inventory", 0.0))
            if not profile.is_confirmed("current_inventory"):
                assumptions.append("Current on-hand inventory assumed as 0 units (pending stock count)")

        if total_cash is not None:
            cash_balance = float(total_cash)
        elif profile.is_confirmed("cash_balance"):
            cash_balance = float(profile.get_value("cash_balance"))
        else:
            cash_balance = float(profile.get_value("cash_balance", 5000.0))
            assumptions.append(f"Liquid cash balance assumed as Rs.{cash_balance:.2f} (unconfirmed by owner)")

        if safety_reserve is not None:
            res_val = float(safety_reserve)
        elif profile.is_confirmed("safety_reserve"):
            res_val = float(profile.get_value("safety_reserve"))
        else:
            res_val = float(profile.get_value("safety_reserve", 1500.0))
            assumptions.append(f"Safety reserve buffer assumed as Rs.{res_val:.2f} (unconfirmed by owner)")
        resolved_reserve = res_val

        base_demand = current_demand if current_demand is not None else float(profile.get_value("base_daily_demand", 0.0))

        projected_demand = base_demand + additional_units
        capacity_headroom = max(0.0, capacity - base_demand)
        fulfillable_by_capacity = min(additional_units, capacity_headroom)

        # Inventory / Parts Shortage Check
        inventory_needed = max(0.0, fulfillable_by_capacity - current_inv)
        procurement_cost = inventory_needed * unit_cost
        usable_cash = max(0.0, cash_balance - resolved_reserve)
        affordable = procurement_cost <= usable_cash

        # Determine Decision
        if fulfillable_by_capacity == 0:
            decision = "REJECT"
            reason = f"You are already at your daily capacity ceiling of {capacity:.0f} {unit_name}."
            voice_response = f"You cannot take these {additional_units:.0f} additional {unit_name} tomorrow because your daily capacity of {capacity:.0f} is fully booked."
        elif not affordable:
            affordable_units = math.floor(usable_cash / unit_cost) if unit_cost > 0 else 0
            decision = "ACCEPT_PARTIALLY" if affordable_units > 0 else "REJECT"
            reason = f"Procuring supplies for {inventory_needed:.0f} {unit_name} costs Rs.{procurement_cost:.2f}, exceeding usable cash of Rs.{usable_cash:.2f} (protecting Rs.{resolved_reserve:.2f} reserve)."
            voice_response = f"You can only afford to take {affordable_units:.0f} additional {unit_name} to protect your cash safety reserve."
        elif inventory_needed > 0:
            decision = "ACCEPT_WITH_PROCUREMENT"
            reason = f"Capacity is sufficient, but {inventory_needed:.0f} {unit_name} of supplies must be procured for Rs.{procurement_cost:.2f}."
            voice_response = f"You can take all {fulfillable_by_capacity:.0f} more {unit_name} tomorrow if you procure {inventory_needed:.0f} units of supplies today for Rs.{procurement_cost:.2f}."
        else:
            decision = "ACCEPT"
            reason = f"Capacity is adequate ({capacity:.0f}/day) and current stock covers all requirements."
            voice_response = f"You can safely accept all {fulfillable_by_capacity:.0f} more {unit_name} tomorrow. Your current stock and capacity are sufficient."

        # Create purchase plan if procurement needed and affordable
        plan_dict = None
        if decision == "ACCEPT_WITH_PROCUREMENT" and affordable:
            plan = self.approvals.create_plan(
                supplier_id="local_wholesale",
                supplier_name=f"Supplies for {profile.category.replace('_', ' ').title()}",
                items=[{
                    "ingredient_name": "materials_package",
                    "display_name": f"Material kits for {inventory_needed:.0f} {unit_name}",
                    "quantity": inventory_needed,
                    "unit": "kits",
                    "unit_price": unit_cost,
                    "total_price": procurement_cost,
                }],
                total_cost=procurement_cost,
                explanation=f"Procurement for {fulfillable_by_capacity:.0f} extra {unit_name} in {profile.display_name}.",
            )
            plan_dict = plan.to_dict()

        reply_str = f"**Decision: {decision}**\n\n{reason}\n\n*Voice response*: \"{voice_response}\""
        if assumptions:
            reply_str += f"\n\n*Assumptions (unconfirmed)*: {'; '.join(assumptions)}."

        return {
            "status": "SUCCESS",
            "decision": decision,
            "business_id": profile.business_id,
            "business_name": profile.display_name,
            "category": profile.category,
            "additional_requested": additional_units,
            "fulfillable_orders": fulfillable_by_capacity,
            "unfulfillable_orders": additional_units - fulfillable_by_capacity,
            "capacity_ceiling": capacity,
            "inventory_needed": inventory_needed,
            "procurement_cost": procurement_cost,
            "usable_cash": usable_cash,
            "safety_reserve": resolved_reserve,
            "purchase_plan": plan_dict,
            "reason": reason,
            "voice_response": voice_response,
            "assumptions": assumptions,
            "reply": reply_str,
        }

    def scout_competitors(self, profile: AdaptiveBusinessProfile) -> Dict[str, Any]:
        """Scouts nearby competitors tailored to the specific business category."""
        # Map category to appropriate Google Places types
        cat_map = {
            "mechanical_repair": ["car_repair"],
            "electronics_repair": ["electronics_store"],
            "clothing_retail": ["clothing_store"],
            "tailoring_boutique": ["clothing_store"],
            "small_fabrication": ["hardware_store"],
            "salon_service": ["beauty_salon", "hair_care"],
            "retail_kirana": ["grocery_store", "supermarket"],
            "home_bakery": ["bakery", "cafe"],
            "home_tiffin": ["restaurant", "meal_delivery"],
        }
        types = cat_map.get(profile.category, ["store", "point_of_interest"])

        resp = self.places.search_nearby_places(
            latitude=26.4727,
            longitude=80.3015,
            radius_meters=2000.0,
            place_types=types,
        )

        avg_rating = f"{resp.summary.average_competitor_rating:.1f}/5.0" if (resp.summary and resp.summary.average_competitor_rating) else "N/A"
        disclaimer = resp.summary.disclaimer if resp.summary else "Competitor overview."
        reply = (
            f"Scouted nearby listings for **{profile.display_name}** in {profile.city}:\n"
            f"• Found {resp.total_count} matching commercial locations within 2.0 km.\n"
            f"• Average competitor rating: {avg_rating}.\n"
            f"• Note: {disclaimer}"
        )

        return {
            "status": "SUCCESS",
            "business_id": profile.business_id,
            "total_count": resp.total_count,
            "competitor_summary": resp.summary.to_dict() if resp.summary else None,
            "is_mock": self.places.is_mock,
            "reply": reply,
        }

    def get_accounting_status(self, profile: AdaptiveBusinessProfile) -> Dict[str, Any]:
        """Fetches accounting overview from Zoho Books (live or mock)."""
        summary = self.zoho.get_accounting_summary()
        reply = (
            f"Accounting overview for **{profile.display_name}** (via Zoho Books):\n"
            f"• Invoiced Revenue: Rs.{summary.total_invoiced_revenue:,.2f}\n"
            f"• Cash Collected: Rs.{summary.cash_collected:,.2f}\n"
            f"• Accounts Receivable: Rs.{summary.outstanding_receivables:,.2f} ({summary.invoices_count} invoices)\n"
            f"• Accounts Payable (Bills): Rs.{summary.total_bills_payable:,.2f} ({summary.bills_count} bills)\n"
            f"• Mode: {'Mock simulation' if self.zoho.is_mock else 'Live Zoho Books connection'}"
        )
        return {
            "status": "SUCCESS",
            "business_id": profile.business_id,
            "accounting_summary": summary.to_dict(),
            "is_mock": self.zoho.is_mock,
            "reply": reply,
        }

    def get_business_summary(self, profile: AdaptiveBusinessProfile) -> Dict[str, Any]:
        """Provides a complete breakdown of confirmed, assumed, and unknown business facts."""
        confirmed = {k: f.value for k, f in profile.facts.items() if f.status == FactStatus.CONFIRMED}
        assumed = {k: f.value for k, f in profile.facts.items() if f.status == FactStatus.ASSUMED}
        outdated = {k: f.value for k, f in profile.facts.items() if f.status == FactStatus.OUTDATED}

        lines = [
            f"**Business Profile**: {profile.display_name} (`{profile.business_id}`)",
            f"**Category**: {profile.category.replace('_', ' ').title()}",
            f"**Onboarding Status**: {'Completed' if profile.onboarding_completed else 'In Progress'}",
            "",
            "**Confirmed Facts**:",
        ]
        if confirmed:
            for k, v in confirmed.items():
                lines.append(f"  • {k.replace('_', ' ').title()}: {v}")
        else:
            lines.append("  (No confirmed facts yet)")

        if assumed:
            lines.append("\n**Assumed Defaults**:")
            for k, v in assumed.items():
                lines.append(f"  • {k.replace('_', ' ').title()}: {v}")

        if outdated:
            lines.append("\n**Outdated / Corrected History**:")
            for k, v in outdated.items():
                lines.append(f"  • {k.replace('_', ' ').title()}: {v}")

        return {
            "status": "SUCCESS",
            "business_id": profile.business_id,
            "display_name": profile.display_name,
            "category": profile.category,
            "onboarding_completed": profile.onboarding_completed,
            "confirmed_facts": confirmed,
            "assumed_facts": assumed,
            "outdated_facts": outdated,
            "reply": "\n".join(lines),
        }

    # -------------------------------------------------------------------------
    # Operational Intelligence, Briefings & Multi-turn Execution
    # -------------------------------------------------------------------------

    def _get_domain_terminology(self, category: str) -> Dict[str, str]:
        """Returns domain-adapted terminology for different business types."""
        cat = (category or "").lower()
        if any(w in cat for w in ["repair", "workshop", "garage", "mechanic"]):
            return {
                "unit": "jobs",
                "unit_singular": "job",
                "customer_work": "customer repair jobs",
                "supplies": "spare parts & components",
                "focus_area": "customer delivery deadlines and parts availability",
                "sample_task": "Check status of vehicle repair job",
            }
        elif any(w in cat for w in ["salon", "spa", "parlour", "beauty"]):
            return {
                "unit": "clients",
                "unit_singular": "client",
                "customer_work": "client appointments & styling sessions",
                "supplies": "cosmetics & salon supplies",
                "focus_area": "appointment schedule and stylist availability",
                "sample_task": "Confirm upcoming client appointment",
            }
        elif any(w in cat for w in ["retail", "kirana", "store", "shop", "grocer"]):
            return {
                "unit": "orders",
                "unit_singular": "order",
                "customer_work": "customer counter sales & order fulfillments",
                "supplies": "wholesale inventory & supplier deliveries",
                "focus_area": "supplier delivery schedules and inventory reorders",
                "sample_task": "Follow up on bulk wholesale shipment",
            }
        elif any(w in cat for w in ["tiffin", "food", "cater", "bakery"]):
            return {
                "unit": "meals",
                "unit_singular": "meal",
                "customer_work": "daily meal preparation & catering orders",
                "supplies": "fresh produce & wholesale ingredients",
                "focus_area": "morning ingredient delivery and batch prep timing",
                "sample_task": "Confirm grocery delivery for daily meal preparation",
            }
        return {
            "unit": "units",
            "unit_singular": "unit",
            "customer_work": "customer jobs & orders",
            "supplies": "materials & inventory",
            "focus_area": "operational deadlines and supply chain status",
            "sample_task": "Review supplier quote and scheduled tasks",
        }

    def calculate_task_priority(
        self,
        task: OperationalTask,
        proposals: Optional[List[ActionProposal]] = None,
    ) -> Dict[str, Any]:
        """
        Computes an explainable, deterministic priority score (0-100) and priority level
        based on task lifecycle state, consequential proposal presence, financial magnitude,
        and task urgency.
        """
        score = 0
        reasons: List[str] = []

        # 1. Base score from task state
        state_scores = {
            TaskState.AWAITING_APPROVAL: 65,
            TaskState.EXECUTION_UNCERTAIN: 75,
            TaskState.WORKING: 45,
            TaskState.PLANNING: 40,
            TaskState.AWAITING_INFORMATION: 35,
            TaskState.RECEIVED: 30,
            TaskState.CLASSIFIED: 35,
            TaskState.EXECUTING: 50,
            TaskState.COMPLETED: 0,
            TaskState.FAILED: 10,
            TaskState.REJECTED: 0,
            TaskState.CANCELLED: 0,
        }
        base = state_scores.get(task.state, 20)
        score += base
        reasons.append(f"Lifecycle state is {task.state.value} (base {base} pts)")

        # 2. Consequential action proposals requiring approval
        props = proposals or []
        consequential_proposals = [p for p in props if p.requires_approval and p.execution_status == "PROPOSED"]
        if consequential_proposals:
            score += 20
            reasons.append(f"{len(consequential_proposals)} consequential action(s) require owner approval (+20 pts)")

        # 3. Financial magnitude
        total_amount = 0.0
        for p in props:
            amt = p.payload.get("amount") or p.payload.get("quote_amount") or 0.0
            try:
                total_amount += float(amt)
            except (ValueError, TypeError):
                pass
        if total_amount >= 5000:
            score += 10
            reasons.append(f"Financial commitment of Rs.{total_amount:,.2f} (+10 pts)")
        elif total_amount > 0:
            score += 5
            reasons.append(f"Financial commitment of Rs.{total_amount:,.2f} (+5 pts)")

        # 4. Urgency keywords in task title or description
        text = f"{task.title} {task.description}".lower()
        if any(w in text for w in ["urgent", "asap", "immediate", "overdue", "critical", "priority"]):
            score += 15
            reasons.append("Urgent deadline flagged in task details (+15 pts)")

        score = min(100, max(0, score))
        if score >= 80:
            level = "CRITICAL"
        elif score >= 60:
            level = "HIGH"
        elif score >= 35:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "score": score,
            "level": level,
            "reasons": reasons,
            "explainable_reason": f"{level} ({score}/100): " + "; ".join(reasons) + ".",
            "financial_amount": total_amount,
        }

    def generate_daily_briefing(
        self,
        business_id: str,
        actor_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates an adaptive, domain-aware operational briefing for the business owner.
        Combines pending approvals, prioritized tasks, financial snapshot, and voice summary.
        """
        profile = self.repo.get_profile(business_id)
        display_name = profile.display_name if profile else business_id
        category = profile.category if profile else "general"
        terms = self._get_domain_terminology(category)

        # Retrieve tasks and pending approvals if task_repo is available
        tasks = []
        pending_actions = []
        if self.task_repo:
            tasks = self.task_repo.list_tasks(business_id=business_id, limit=20)
            pending_actions = self.task_repo.list_pending_actions(business_id=business_id)
            self._last_referenced_actions[business_id] = list(pending_actions)
            if session_id and self.session_repo and pending_actions:
                try:
                    self.session_repo.update_referenced_actions(
                        session_id, [p.action_id for p in pending_actions], business_id=business_id
                    )
                except Exception as e:
                    logger.warning("Could not update session referenced actions: %s", e)

        # Prioritize tasks
        prioritized_tasks = []
        for t in tasks:
            props = self.task_repo.list_actions_for_task(t.task_id, business_id=business_id) if self.task_repo else []
            prio = self.calculate_task_priority(t, props)
            prioritized_tasks.append({
                "task_id": t.task_id,
                "title": t.title,
                "state": t.state.value,
                "priority_score": prio["score"],
                "priority_level": prio["level"],
                "priority_reason": prio["explainable_reason"],
                "actions_count": len(props),
            })
        prioritized_tasks.sort(key=lambda x: x["priority_score"], reverse=True)

        # Financial snapshot from profile facts
        cash = profile.get_value("cash_balance", profile.get_value("starting_capital", 0.0)) if profile else 0.0
        reserve = profile.get_value("safety_reserve", 2000.0) if profile else 2000.0
        capacity = profile.get_value("daily_capacity", 0.0) if profile else 0.0
        usable_capital = max(0.0, float(cash) - float(reserve))

        # Suggested Next Actions
        suggested_actions: List[str] = []
        if pending_actions:
            first_action = pending_actions[0]
            suggested_actions.append(
                f"Review and approve {first_action.action_type.replace('_', ' ')}: '{first_action.description}'."
            )
        active_high_tasks = [t for t in prioritized_tasks if t["priority_level"] in ("CRITICAL", "HIGH")]
        if active_high_tasks:
            suggested_actions.append(f"Follow up on priority item: '{active_high_tasks[0]['title']}'.")
        else:
            suggested_actions.append(f"Check capacity readiness for tomorrow ({capacity:.0f} {terms['unit']}/day capacity).")

        # Voice-first summary for Alexa+
        voice_lines = []
        if pending_actions:
            voice_lines.append(
                f"You have {len(pending_actions)} pending approval{'s' if len(pending_actions) > 1 else ''}. "
                f"The most important is {pending_actions[0].description}."
            )
        else:
            voice_lines.append("You have no pending approvals.")

        open_tasks = [t for t in prioritized_tasks if t["state"] not in ("COMPLETED", "REJECTED", "CANCELLED")]
        if open_tasks:
            voice_lines.append(
                f"There are {len(open_tasks)} active operational {terms['unit_singular'] if len(open_tasks) == 1 else terms['unit']} requiring attention."
            )
        else:
            voice_lines.append("All daily operations are currently up to date.")

        if pending_actions:
            voice_lines.append("Would you like to review the first approval?")

        voice_summary = " ".join(voice_lines)

        reply_lines = [
            f"**Operational Briefing — {display_name}** ({category.replace('_', ' ').title()})",
            f"• Available Liquid Cash: Rs.{float(cash):,.2f} (Usable capital: Rs.{usable_capital:,.2f}, Safety reserve: Rs.{float(reserve):,.2f})",
            f"• Daily Capacity: {capacity:.0f} {terms['unit']}/day",
            f"• Focus for today: {terms['focus_area']}",
            "",
            f"**Pending Approvals ({len(pending_actions)})**:",
        ]
        if pending_actions:
            for i, p in enumerate(pending_actions[:3], 1):
                reply_lines.append(f"  {i}. `[{p.action_id[:8]}]` {p.description} (Type: {p.action_type})")
        else:
            reply_lines.append("  (None — no actions waiting for approval)")

        reply_lines.append(f"\n**Top Prioritized Tasks ({len(open_tasks)} active)**:")
        if open_tasks:
            for t in open_tasks[:3]:
                reply_lines.append(f"  • `[{t['priority_level']}]` {t['title']} — {t['priority_reason']}")
        else:
            reply_lines.append("  (No active tasks)")

        reply_lines.append("\n**Suggested Next Actions**:")
        for i, a in enumerate(suggested_actions, 1):
            reply_lines.append(f"  {i}. {a}")

        return {
            "status": "SUCCESS",
            "business_id": business_id,
            "display_name": display_name,
            "category": category,
            "headline": f"{display_name} Briefing: {len(pending_actions)} pending approvals, {len(open_tasks)} open tasks",
            "pending_approvals_count": len(pending_actions),
            "pending_approvals": [p.to_dict() for p in pending_actions],
            "active_tasks_count": len(open_tasks),
            "prioritized_tasks": prioritized_tasks,
            "financial_snapshot": {
                "cash_balance": float(cash),
                "safety_reserve": float(reserve),
                "usable_capital": usable_capital,
                "daily_capacity": float(capacity),
                "unit": terms["unit"],
            },
            "suggested_next_actions": suggested_actions,
            "voice_summary": voice_summary,
            "reply": "\n".join(reply_lines),
        }

    def list_pending_approvals_summary(
        self,
        business_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists pending action proposals for a business with clear voice formatting."""
        if not self.task_repo:
            return {"status": "ERROR", "error": "Task repository not connected."}
        pending = self.task_repo.list_pending_actions(business_id=business_id)
        self._last_referenced_actions[business_id] = list(pending)
        if session_id and self.session_repo and pending:
            try:
                self.session_repo.update_referenced_actions(
                    session_id, [p.action_id for p in pending], business_id=business_id
                )
            except Exception as e:
                logger.warning("Could not update session referenced actions: %s", e)

        if not pending:
            return {
                "status": "SUCCESS",
                "business_id": business_id,
                "pending_count": 0,
                "approvals": [],
                "voice_summary": "You have no pending approvals at this time.",
                "reply": "You have no actions currently awaiting owner approval.",
            }

        lines = [f"**Pending Approvals for `{business_id}` ({len(pending)})**:"]
        for i, p in enumerate(pending, 1):
            lines.append(f"{i}. `[{p.action_id[:8]}]` {p.description} (Type: `{p.action_type}`)")

        voice = f"You have {len(pending)} pending approval{'s' if len(pending) > 1 else ''}. The first is {pending[0].description}."
        return {
            "status": "SUCCESS",
            "business_id": business_id,
            "pending_count": len(pending),
            "approvals": [p.to_dict() for p in pending],
            "voice_summary": voice,
            "reply": "\n".join(lines),
        }

    def _resolve_proposal_index(
        self,
        business_id: str,
        message: str,
        pending: List[ActionProposal],
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        Safely resolves a conversational ordinal reference ('proposal 1', 'first one', 'second', 'number 2')
        against the active pending proposals for the tenant.
        Rejects out-of-range, ambiguous, or invalid references.
        """
        msg_lower = message.lower()

        # 1. Check for explicit numeric reference: "proposal 1", "#2", "number 3", "proposal 2"
        m = re.search(r"(?:proposal|number|#)\s*(\d+)", msg_lower)
        if not m:
            m = re.search(r"\b(\d+)\b", msg_lower)

        if m:
            val = int(m.group(1)) - 1
            if 0 <= val < len(pending):
                return val, None
            else:
                return None, {
                    "status": "INVALID_REFERENCE",
                    "reply": f"Proposal {val + 1} not found. There {'is only 1 pending proposal' if len(pending) == 1 else f'are only {len(pending)} pending proposals'} for `{business_id}`.",
                    "voice_summary": f"I could not find proposal {val + 1}. There are only {len(pending)} pending proposals.",
                }

        # 2. Check for explicit ordinal words
        ordinal_words = {
            "first": 0, "1st": 0, "the first": 0, "first one": 0,
            "second": 1, "2nd": 1, "the second": 1, "second one": 1,
            "third": 2, "3rd": 2, "the third": 2, "third one": 2,
            "fourth": 3, "4th": 3, "the fourth": 3,
            "fifth": 4, "5th": 4,
            "last": len(pending) - 1, "last one": len(pending) - 1,
        }
        for word, idx in ordinal_words.items():
            if re.search(r"\b" + re.escape(word) + r"\b", msg_lower):
                if 0 <= idx < len(pending):
                    return idx, None
                else:
                    return None, {
                        "status": "INVALID_REFERENCE",
                        "reply": f"The requested {word} proposal does not exist. There are currently {len(pending)} pending proposal(s).",
                        "voice_summary": f"That proposal reference is out of range. There are only {len(pending)} pending proposals.",
                    }

        # 3. If a specific proposal was focused in the session, and message is generic confirmation/approval ("approve it", "approve that", "approve this", "yes", "confirm")
        if session_id and self.session_repo:
            try:
                active_session = self.session_repo.get_session(session_id)
                focused_id = active_session.metadata.get("focused_action_id") if active_session else None
                if focused_id:
                    for idx, p in enumerate(pending):
                        if p.action_id == focused_id:
                            return idx, None
            except Exception:
                pass

        # 4. If exactly 1 proposal exists, generic confirmation/inquiry unambiguously refers to it
        if len(pending) == 1:
            return 0, None

        # 5. If multiple proposals exist and no specific ordinal was supplied, reject as ambiguous
        descriptions = [f"{i+1}) {p.description}" for i, p in enumerate(pending[:3])]
        return None, {
            "status": "AMBIGUOUS_REFERENCE",
            "reply": (
                f"You have {len(pending)} pending proposals:\n"
                + "\n".join(f"  • {d}" for d in descriptions)
                + "\nPlease specify which one you wish to select (for example, 'Approve proposal 1')."
            ),
            "voice_summary": f"You have {len(pending)} pending approvals. Please specify which proposal number to approve.",
        }

    def handle_explain_proposal(
        self,
        business_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explains an action proposal referenced conversationally (e.g. 'explain the first one')."""
        if not self.task_repo:
            return {"status": "ERROR", "error": "Task repository not connected."}

        pending = self._get_active_proposals_for_context(business_id, session_id=session_id)
        if not pending:
            return {
                "status": "NO_PENDING_APPROVALS",
                "reply": "You currently have no pending proposals to explain.",
                "voice_summary": "You have no pending proposals to review.",
            }

        target_idx, err_resp = self._resolve_proposal_index(business_id, message, pending, session_id=session_id)
        if err_resp:
            return err_resp

        proposal = pending[target_idx]
        task = self.task_repo.get_task(proposal.task_id, business_id=business_id) if proposal.task_id else None

        explanation_lines = [
            f"**Proposal Details**: {proposal.description}",
            f"• Action ID: `{proposal.action_id}`",
            f"• Action Type: `{proposal.action_type}` (Requires Owner Approval)",
            f"• Linked Task: {task.title if task else 'General'}",
            f"• Payload Integrity Hash: `{proposal.payload_hash[:16]}...`",
            f"• Exact Payload:",
            f"```json\n{json.dumps(proposal.payload, indent=2)}\n```",
            f"• Rationale: This is a consequential action modifying external commitments. An authenticated owner approval binds to this exact SHA-256 hash before execution.",
        ]

        voice = (
            f"Proposal {target_idx + 1} is for {proposal.description}. "
            f"It requires your approval before sending. "
            f"Would you like me to approve it?"
        )

        # Retain full pending proposal list for ordinal numbering, but set focused proposal in session metadata
        self._last_referenced_actions[business_id] = pending
        if session_id and self.session_repo:
            try:
                sess = self.session_repo.get_session(session_id)
                if sess:
                    sess.metadata["focused_action_id"] = proposal.action_id
                    self.session_repo.save_session(sess)
            except Exception as e:
                logger.warning("Could not set session focused action: %s", e)

        return {
            "status": "SUCCESS",
            "action_id": proposal.action_id,
            "proposal": proposal.to_dict(),
            "voice_summary": voice,
            "reply": "\n".join(explanation_lines),
        }

    def handle_approve_followup(
        self,
        business_id: str,
        message: str,
        actor_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approves and optionally dispatches an action proposal referenced conversationally."""
        if not self.task_repo:
            return {"status": "ERROR", "error": "Task repository not connected."}

        pending = self._get_active_proposals_for_context(business_id, session_id=session_id)
        if not pending:
            return {
                "status": "NO_PENDING_APPROVALS",
                "reply": "There are no pending action proposals awaiting approval.",
                "voice_summary": "There are no pending actions to approve.",
            }

        effective_actor = actor_id or f"owner:{business_id}"
        if not self.policy_engine.is_authorized_owner(business_id, effective_actor):
            return {
                "status": "UNAUTHORIZED",
                "error": f"Actor '{effective_actor}' is not an authorized owner for business '{business_id}'. Approval rejected.",
                "voice_summary": "I cannot execute this approval because the actor is not an authorized owner.",
                "reply": f"Approval denied: Actor `{effective_actor}` lacks owner authorization for `{business_id}`.",
            }

        target_idx, err_resp = self._resolve_proposal_index(business_id, message, pending, session_id=session_id)
        if err_resp:
            return err_resp

        proposal = pending[target_idx]

        # Verify proposal fresh state from DB (reject stale references)
        fresh_proposal = self.task_repo.get_action(proposal.action_id, business_id=business_id)
        if not fresh_proposal or fresh_proposal.execution_status != "PROPOSED":
            current_st = fresh_proposal.execution_status if fresh_proposal else "NOT_FOUND"
            return {
                "status": "STALE_REFERENCE",
                "reply": f"Proposal '{proposal.action_id[:8]}' ({proposal.description}) is no longer pending (current state: {current_st}).",
                "voice_summary": "That proposal is no longer pending approval.",
            }

        # 1. Approve via TaskRepository
        approved = self.task_repo.approve_action(
            action_id=proposal.action_id,
            business_id=business_id,
            actor_id=effective_actor,
            execution_payload=proposal.payload,
            policy_engine=self.policy_engine,
        )

        # 2. Dispatch via ActionDispatcher if available
        receipt = None
        if self.action_dispatcher:
            receipt = self.action_dispatcher.dispatch_action(
                action_id=proposal.action_id,
                business_id=business_id,
                actor_id=effective_actor,
                execution_payload=proposal.payload,
            )

        # Update cache & session
        rem_props = [p for p in pending if p.action_id != proposal.action_id]
        self._last_referenced_actions[business_id] = rem_props
        if session_id and self.session_repo:
            try:
                self.session_repo.update_referenced_actions(
                    session_id, [p.action_id for p in rem_props], business_id=business_id
                )
            except Exception as e:
                logger.warning("Could not update session referenced actions: %s", e)

        reply_lines = [
            f"**Action Approved and Dispatched** (Simulation Mode):",
            f"• Action: {proposal.description}",
            f"• Approved by: `{effective_actor}`",
            f"• Dispatch Status: `{receipt.status if receipt else 'APPROVED'}`",
            f"• Receipt ID: `{receipt.receipt_id if receipt else 'N/A'}`",
            f"• Simulation Notice: Safe offline simulation. No real money or external email was sent.",
        ]
        voice = f"I have approved and executed the {proposal.description} in simulation mode. Receipt generated."

        return {
            "status": "APPROVED_AND_EXECUTED",
            "action_id": proposal.action_id,
            "receipt": receipt.to_dict() if receipt else None,
            "voice_summary": voice,
            "reply": "\n".join(reply_lines),
        }

    def handle_reject_followup(
        self,
        business_id: str,
        message: str,
        actor_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rejects an action proposal referenced conversationally."""
        if not self.task_repo:
            return {"status": "ERROR", "error": "Task repository not connected."}

        pending = self._get_active_proposals_for_context(business_id, session_id=session_id)
        if not pending:
            return {
                "status": "NO_PENDING_APPROVALS",
                "reply": "There are no pending action proposals to reject.",
                "voice_summary": "There are no pending actions to reject.",
            }

        effective_actor = actor_id or f"owner:{business_id}"
        if not self.policy_engine.is_authorized_owner(business_id, effective_actor):
            return {
                "status": "UNAUTHORIZED",
                "error": f"Actor '{effective_actor}' is not authorized to reject actions for business '{business_id}'.",
                "voice_summary": "You are not authorized to reject this action.",
                "reply": f"Rejection denied: Unauthorized actor `{effective_actor}`.",
            }

        target_idx, err_resp = self._resolve_proposal_index(business_id, message, pending, session_id=session_id)
        if err_resp:
            return err_resp

        proposal = pending[target_idx]

        # Verify proposal fresh state from DB (reject stale references)
        fresh_proposal = self.task_repo.get_action(proposal.action_id, business_id=business_id)
        if not fresh_proposal or fresh_proposal.execution_status != "PROPOSED":
            current_st = fresh_proposal.execution_status if fresh_proposal else "NOT_FOUND"
            return {
                "status": "STALE_REFERENCE",
                "reply": f"Proposal '{proposal.action_id[:8]}' ({proposal.description}) is no longer pending (current state: {current_st}).",
                "voice_summary": "That proposal is no longer pending rejection.",
            }

        rejected = self.task_repo.reject_action(
            action_id=proposal.action_id,
            business_id=business_id,
            actor_id=effective_actor,
            rejection_reason="Rejected by business owner during operational review.",
        )
        rem_props = [p for p in pending if p.action_id != proposal.action_id]
        self._last_referenced_actions[business_id] = rem_props
        if session_id and self.session_repo:
            try:
                self.session_repo.update_referenced_actions(
                    session_id, [p.action_id for p in rem_props], business_id=business_id
                )
            except Exception as e:
                logger.warning("Could not update session referenced actions: %s", e)

        voice = f"The proposed action '{proposal.description}' has been rejected."
        return {
            "status": "REJECTED",
            "action_id": proposal.action_id,
            "action": rejected.to_dict(),
            "voice_summary": voice,
            "reply": f"Proposal `{proposal.action_id[:8]}` ({proposal.description}) has been rejected.",
        }

    def process_operational_request(
        self,
        business_id: str,
        request_text: str,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        actor_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes an inbound operational text or quotation email through the supervisor pipeline.
        Associates context, creates task, extracts details, proposes action, evaluates policy.
        """
        if not self.supervisor:
            return {"status": "ERROR", "error": "Operational supervisor not connected."}

        email_sender = sender or "supplier.quote@mandi.market"
        email_subj = subject or "Quotation / Order Request"

        inbound = InboundEmail(
            message_id=f"msg_orch_{uuid.uuid4().hex[:10]}",
            business_id=business_id,
            sender=EmailAddress(email=email_sender, name="Supplier Partner"),
            to_recipients=[EmailAddress(email=f"{business_id}@autopilot.local")],
            subject=email_subj,
            body_text=request_text,
        )

        if self.email_repo:
            self.email_repo.save_email(inbound)

        outcome = self.supervisor.process_email(inbound)
        if self.task_repo:
            pending = self.task_repo.list_pending_actions(business_id=business_id)
            self._last_referenced_actions[business_id] = list(pending)
            if session_id and self.session_repo and pending:
                try:
                    self.session_repo.update_referenced_actions(
                        session_id, [p.action_id for p in pending], business_id=business_id
                    )
                except Exception as e:
                    logger.warning("Could not update session referenced actions: %s", e)

        reply_lines = [
            f"**Operational Request Processed** for `{business_id}`:",
            f"• Task ID: `{outcome.task.task_id}` ({outcome.task.title})",
            f"• Lifecycle State: `{outcome.state.value}`",
            f"• Classification: Intent `{outcome.intent}`",
            f"• Analysis Summary: {outcome.analysis_summary}",
        ]
        if outcome.actions_awaiting_approval:
            reply_lines.append(f"\n**Action Proposed (Awaiting Approval)**:")
            for a in outcome.actions_awaiting_approval:
                reply_lines.append(f"  • `[{a.get('action_id', '')[:8]}]` {a.get('description', '')}")
            voice = (
                f"I processed the supplier message and created task '{outcome.task.title}'. "
                f"A consequential action is waiting for your approval. Would you like to review it?"
            )
        else:
            voice = f"I processed the request and updated task '{outcome.task.title}'."

        return {
            "status": "SUCCESS",
            "task_id": outcome.task.task_id,
            "state": outcome.state.value,
            "intent": outcome.intent,
            "actions_awaiting_approval": outcome.actions_awaiting_approval,
            "actions_allowed": outcome.actions_allowed,
            "voice_summary": voice,
            "reply": "\n".join(reply_lines),
        }

    def get_urgent_tasks_summary(self, business_id: str) -> Dict[str, Any]:
        """Retrieves and summarizes urgent tasks adapted to business category."""
        if not self.task_repo:
            return {"status": "ERROR", "error": "Task repository not connected."}
        profile = self.repo.get_profile(business_id)
        terms = self._get_domain_terminology(profile.category if profile else "general")
        tasks = self.task_repo.list_tasks(business_id=business_id, limit=20)
        scored = []
        for t in tasks:
            if t.state not in (TaskState.COMPLETED, TaskState.REJECTED, TaskState.CANCELLED):
                props = self.task_repo.list_actions_for_task(t.task_id, business_id=business_id)
                prio = self.calculate_task_priority(t, props)
                scored.append((t, prio))
        scored.sort(key=lambda x: x[1]["score"], reverse=True)

        reply_lines = [
            f"**Active Operations Summary — {profile.display_name if profile else business_id}**:",
            f"Domain: {terms['customer_work']}",
        ]
        if scored:
            for t, prio in scored[:5]:
                reply_lines.append(f"  • `[{prio['level']}]` **{t.title}** ({t.state.value}) — {prio['explainable_reason']}")
            voice = f"You have {len(scored)} active {terms['unit']}. The highest priority is {scored[0][0].title}."
        else:
            reply_lines.append(f"  (No urgent or active {terms['unit']} found)")
            voice = f"You have no urgent {terms['unit']} pending."

        return {
            "status": "SUCCESS",
            "business_id": business_id,
            "urgent_tasks": [{"task_id": t.task_id, "title": t.title, "priority": prio} for t, prio in scored],
            "voice_summary": voice,
            "reply": "\n".join(reply_lines),
        }
