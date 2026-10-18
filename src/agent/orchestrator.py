"""
Adaptive Business AI Orchestrator
===================================
Coordinates between dynamic business profiles, prerequisite validation,
specialist agents, external integrations, and the two-phase approval workflow.
Ensures tiffin-specific assumptions are never applied to other verticals.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

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

logger = logging.getLogger(__name__)


class AdaptiveBusinessOrchestrator:
    """
    Business-agnostic AI orchestrator that dynamically inspects profile prerequisites,
    dispatches to specialist analytical tools, and guards purchase execution.
    """

    def __init__(
        self,
        repo: AdaptiveProfileRepository,
        approval_service: Optional[PurchaseApprovalService] = None,
        places_adapter: Optional[GooglePlacesAdapter] = None,
        zoho_adapter: Optional[ZohoBooksAdapter] = None,
    ):
        self.repo = repo
        self.approvals = approval_service or PurchaseApprovalService()
        self.places = places_adapter or GooglePlacesAdapter()
        self.zoho = zoho_adapter or ZohoBooksAdapter()

    def handle_user_message(
        self,
        message: str,
        business_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Primary entry point for user interaction. Dispatches to onboarding,
        financial analysis, opportunity evaluation, or external scouts.
        """
        msg_lower = message.lower()

        # 1. Resolve or create active profile
        profile = None
        if business_id:
            profile = self.repo.get_profile(business_id)

        # 2. If profile exists, check for explicit operational/analytical requests first
        if profile is not None:
            # A. Profitability / Margin Inquiry
            if any(w in msg_lower for w in ["profit", "margin", "break-even", "breakeven", "how am i doing", "economics"]):
                return self.analyze_profitability(profile)

            # B. Opportunity / New Orders / Job Evaluation
            if any(w in msg_lower for w in ["can i take", "more orders", "more jobs", "new client", "opportunity", "take on"]):
                # Extract additional quantity requested
                import re
                m = re.search(r"(\d+)\s*(?:more|additional)?\s*(?:orders|jobs|repairs|clients|customers|units|dresses|items|meals|tiffins|bikes)?", msg_lower)
                additional_qty = float(m.group(1)) if m else 5.0
                return self.evaluate_opportunity(profile, additional_qty, user_question=message)

            # C. Competitor Scout Inquiry
            if any(w in msg_lower for w in ["competitor", "nearby", "competition", "other shops", "places nearby"]):
                return self.scout_competitors(profile)

            # D. Accounting & Invoice Inquiry
            if any(w in msg_lower for w in ["zoho", "invoice", "bills", "receivable", "accounting"]):
                return self.get_accounting_status(profile)

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
            probe_onboarder._extract_numeric_facts(message)
            or probe_onboarder._extract_products(message)
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
            result = onboarder.process_utterance(message)
            # Persist updated profile
            self.repo.save_profile(onboarder.profile)
            return {
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
            }

        # E. General Business State Summary
        return self.get_business_summary(profile)

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
