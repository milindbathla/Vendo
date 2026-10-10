"""
Alexa Business Autopilot V2 -- Deterministic Business Decision Orchestrator
============================================================================
A lightweight testing and demonstration layer simulating the agentic MCP tool
orchestration pipeline for Indian small businesses.

Orchestration Flow:
    User Opportunity Question
            ↓
    [1] get_business_overview()
            ↓
    [2] forecast_demand()
            ↓
    [3] analyze_inventory()
            ↓
    [4] get_capacity_status()
            ↓
    [5] get_financial_position()
            ↓
    [6] analyze_purchase_affordability()
            ↓
    [7] optimize_procurement_plan()
            ↓
    [8] Final Business Decision (ACCEPT, ACCEPT_WITH_PROCUREMENT, ACCEPT_PARTIALLY, REJECT)
            ↓
    Explainable Voice Response
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import math

from src.models.business import BusinessProfile
from src.simulator import load_business_profiles


class DecisionType(str, Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_PROCUREMENT = "ACCEPT_WITH_PROCUREMENT"
    ACCEPT_PARTIALLY = "ACCEPT_PARTIALLY"
    REJECT = "REJECT"


@dataclass
class BusinessOverview:
    business_type: str
    display_name: str
    selling_price: float
    supplier_unit_cost: float
    current_demand: float
    additional_demand: float
    projected_demand: float


@dataclass
class DemandForecast:
    current_demand: float
    additional_demand: float
    projected_demand: float
    confidence: str = "HIGH"


@dataclass
class InventoryStatus:
    available_units: float
    required_units: float
    shortage_units: float
    coverage_ratio_pct: float


@dataclass
class CapacityStatus:
    daily_capacity: float
    projected_demand: float
    capacity_shortage: float
    additional_orders_allowed: float
    is_bottleneck: bool


@dataclass
class FinancialPosition:
    total_cash: float
    safety_reserve: float
    usable_cash: float
    is_cash_constrained: bool


@dataclass
class PurchaseAffordability:
    required_units: float
    estimated_cost: float
    usable_cash: float
    is_affordable: bool
    max_affordable_units: float
    remaining_cash_after: float


@dataclass
class ProcurementPlan:
    recommended_procurement_units: float
    procurement_mode: str  # "none", "normal", "bulk", "partial"
    estimated_cost: float
    cash_after: float
    stockout_units: float


@dataclass
class OpportunityDecision:
    decision: DecisionType
    user_question: str
    business_overview: BusinessOverview
    demand_forecast: DemandForecast
    inventory_status: InventoryStatus
    capacity_status: CapacityStatus
    financial_position: FinancialPosition
    affordability: PurchaseAffordability
    procurement_plan: ProcurementPlan
    fulfillable_additional_orders: float
    unfulfillable_additional_orders: float
    reason: str
    recommendations: List[str]
    explanation_bullets: List[str]
    voice_response: str
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "user_question": self.user_question,
            "business": self.business_overview.display_name,
            "current_demand": round(self.demand_forecast.current_demand, 1),
            "additional_demand": round(self.demand_forecast.additional_demand, 1),
            "projected_demand": round(self.demand_forecast.projected_demand, 1),
            "available_inventory": round(self.inventory_status.available_units, 1),
            "inventory_shortage": round(self.inventory_status.shortage_units, 1),
            "daily_capacity": round(self.capacity_status.daily_capacity, 1),
            "capacity_shortage": round(self.capacity_status.capacity_shortage, 1),
            "total_cash": round(self.financial_position.total_cash, 2),
            "usable_cash": round(self.financial_position.usable_cash, 2),
            "procurement_units": round(self.procurement_plan.recommended_procurement_units, 1),
            "procurement_cost": round(self.procurement_plan.estimated_cost, 2),
            "fulfillable_additional_orders": round(self.fulfillable_additional_orders, 1),
            "unfulfillable_additional_orders": round(self.unfulfillable_additional_orders, 1),
            "reason": self.reason,
            "recommendations": self.recommendations,
            "explanation_bullets": self.explanation_bullets,
            "voice_response": self.voice_response,
            "tool_trace": self.tool_trace,
        }


class BusinessAutopilotV2:
    """
    Deterministic Business Autopilot V2 Orchestrator.
    Executes mock/local MCP business intelligence tools to evaluate whether
    a business can safely take an opportunity.
    """

    def __init__(self, profile: Optional[BusinessProfile] = None):
        if profile is None:
            profiles = load_business_profiles()
            self.profile = profiles["home_tiffin"]
        else:
            self.profile = profile

    # -------------------------------------------------------------------------
    # Conceptual Local MCP Tools
    # -------------------------------------------------------------------------

    def get_business_overview(self, current_demand: float, additional_demand: float) -> BusinessOverview:
        """[Tool 1] Retrieves business category, economics, and order projections."""
        projected = current_demand + additional_demand
        return BusinessOverview(
            business_type=self.profile.business_type,
            display_name=self.profile.display_name,
            selling_price=self.profile.selling_price,
            supplier_unit_cost=self.profile.supplier_unit_cost,
            current_demand=current_demand,
            additional_demand=additional_demand,
            projected_demand=projected,
        )

    def forecast_demand(self, current_demand: float, additional_demand: float) -> DemandForecast:
        """[Tool 2] Aggregates expected baseline demand with incoming requested opportunity."""
        projected = current_demand + additional_demand
        return DemandForecast(
            current_demand=current_demand,
            additional_demand=additional_demand,
            projected_demand=projected,
            confidence="HIGH",
        )

    def analyze_inventory(self, current_inventory: float, required_demand: float) -> InventoryStatus:
        """[Tool 3] Evaluates ingredient availability against required production units."""
        shortage = max(0.0, required_demand - current_inventory)
        coverage = (current_inventory / required_demand * 100) if required_demand > 0 else 100.0
        return InventoryStatus(
            available_units=current_inventory,
            required_units=required_demand,
            shortage_units=shortage,
            coverage_ratio_pct=min(100.0, coverage),
        )

    def get_capacity_status(self, daily_capacity: float, projected_demand: float, current_demand: float) -> CapacityStatus:
        """[Tool 4] Assesses physical production/kitchen constraints."""
        cap_shortage = max(0.0, projected_demand - daily_capacity)
        additional_allowed = max(0.0, daily_capacity - current_demand)
        return CapacityStatus(
            daily_capacity=daily_capacity,
            projected_demand=projected_demand,
            capacity_shortage=cap_shortage,
            additional_orders_allowed=additional_allowed,
            is_bottleneck=cap_shortage > 0.0,
        )

    def get_financial_position(self, total_cash: float, safety_reserve: float = 2000.0) -> FinancialPosition:
        """[Tool 5] Inspects liquid cash balance and safety reserve threshold."""
        usable = max(0.0, total_cash - safety_reserve)
        return FinancialPosition(
            total_cash=total_cash,
            safety_reserve=safety_reserve,
            usable_cash=usable,
            is_cash_constrained=usable <= (self.profile.supplier_unit_cost * 5),
        )

    def analyze_purchase_affordability(
        self,
        required_shortage: float,
        unit_cost: float,
        usable_cash: float,
    ) -> PurchaseAffordability:
        """[Tool 6] Evaluates whether procurement is affordable without violating liquidity reserve."""
        cost = required_shortage * unit_cost
        is_affordable = cost <= usable_cash
        max_affordable = math.floor(usable_cash / unit_cost) if unit_cost > 0 else required_shortage
        remaining_cash = usable_cash - cost if is_affordable else (usable_cash - (max_affordable * unit_cost))
        return PurchaseAffordability(
            required_units=required_shortage,
            estimated_cost=cost,
            usable_cash=usable_cash,
            is_affordable=is_affordable,
            max_affordable_units=float(max_affordable),
            remaining_cash_after=max(0.0, remaining_cash),
        )

    def optimize_procurement_plan(
        self,
        shortage: float,
        unit_cost: float,
        usable_cash: float,
        daily_wastage_rate: float,
    ) -> ProcurementPlan:
        """[Tool 7] Selects optimal procurement package (None, Normal, Bulk, or Partial)."""
        if shortage <= 0.0:
            return ProcurementPlan(
                recommended_procurement_units=0.0,
                procurement_mode="none",
                estimated_cost=0.0,
                cash_after=usable_cash,
                stockout_units=0.0,
            )

        normal_cost = shortage * unit_cost
        # Check bulk qualification
        bulk_threshold = self.profile.bulk_order_threshold
        bulk_discount = self.profile.bulk_discount
        bulk_cost = bulk_threshold * unit_cost * (1.0 - bulk_discount)

        if normal_cost <= usable_cash:
            # Check if bulk is viable and economical
            if (
                bulk_cost <= usable_cash
                and daily_wastage_rate <= 0.01
                and shortage >= (bulk_threshold * 0.7)
            ):
                return ProcurementPlan(
                    recommended_procurement_units=bulk_threshold,
                    procurement_mode="bulk",
                    estimated_cost=bulk_cost,
                    cash_after=usable_cash - bulk_cost,
                    stockout_units=0.0,
                )
            return ProcurementPlan(
                recommended_procurement_units=shortage,
                procurement_mode="normal",
                estimated_cost=normal_cost,
                cash_after=usable_cash - normal_cost,
                stockout_units=0.0,
            )
        else:
            # Cash constrained: partial purchase
            max_units = math.floor(usable_cash / unit_cost)
            partial_cost = max_units * unit_cost
            return ProcurementPlan(
                recommended_procurement_units=float(max_units),
                procurement_mode="partial",
                estimated_cost=partial_cost,
                cash_after=usable_cash - partial_cost,
                stockout_units=shortage - max_units,
            )

    # -------------------------------------------------------------------------
    # Core Decision Orchestrator
    # -------------------------------------------------------------------------

    def evaluate_opportunity(
        self,
        additional_orders: float,
        current_demand: Optional[float] = None,
        current_inventory: Optional[float] = None,
        total_cash: Optional[float] = None,
        daily_capacity: Optional[float] = None,
        cash_reserve_target: float = 2000.0,
        user_question: Optional[str] = None,
    ) -> OpportunityDecision:
        """
        Orchestrates tool calls to evaluate:
        "Can I safely take X more orders tomorrow?"
        """
        curr_demand = current_demand if current_demand is not None else self.profile.base_daily_demand
        curr_inv = current_inventory if current_inventory is not None else self.profile.starting_inventory
        cash = total_cash if total_cash is not None else self.profile.starting_capital
        cap = daily_capacity if daily_capacity is not None else self.profile.daily_capacity
        q_text = user_question or f"Can I take {additional_orders:.0f} more orders tomorrow?"

        tool_trace: List[Dict[str, Any]] = []

        # Tool 1: Business Overview
        overview = self.get_business_overview(curr_demand, additional_orders)
        tool_trace.append({
            "step": 1,
            "tool": "get_business_overview",
            "summary": f"Business: {overview.display_name}, Current: {overview.current_demand:.0f}, Add: {overview.additional_demand:.0f}",
        })

        # Tool 2: Demand Forecast
        demand_fc = self.forecast_demand(curr_demand, additional_orders)
        tool_trace.append({
            "step": 2,
            "tool": "forecast_demand",
            "summary": f"Expected demand: {demand_fc.projected_demand:.0f} orders (confidence: {demand_fc.confidence})",
        })

        # Tool 3: Inventory Analysis
        inv_status = self.analyze_inventory(curr_inv, demand_fc.projected_demand)
        tool_trace.append({
            "step": 3,
            "tool": "analyze_inventory",
            "summary": f"Available: {inv_status.available_units:.0f} units, Required: {inv_status.required_units:.0f}, Shortage: {inv_status.shortage_units:.0f}",
        })

        # Tool 4: Capacity Analysis
        cap_status = self.get_capacity_status(cap, demand_fc.projected_demand, curr_demand)
        tool_trace.append({
            "step": 4,
            "tool": "get_capacity_status",
            "summary": f"Daily Capacity: {cap_status.daily_capacity:.0f}, Projected: {cap_status.projected_demand:.0f}, Shortage: {cap_status.capacity_shortage:.0f}",
        })

        # Tool 5: Financial Position
        fin_pos = self.get_financial_position(cash, cash_reserve_target)
        tool_trace.append({
            "step": 5,
            "tool": "get_financial_position",
            "summary": f"Cash: Rs.{fin_pos.total_cash:,.2f}, Safety reserve: Rs.{fin_pos.safety_reserve:,.2f}, Usable: Rs.{fin_pos.usable_cash:,.2f}",
        })

        # Tool 6: Purchase Affordability
        affordability = self.analyze_purchase_affordability(
            inv_status.shortage_units,
            self.profile.supplier_unit_cost,
            fin_pos.usable_cash,
        )
        tool_trace.append({
            "step": 6,
            "tool": "analyze_purchase_affordability",
            "summary": f"Cost: Rs.{affordability.estimated_cost:,.2f}, Usable cash: Rs.{affordability.usable_cash:,.2f}, Affordable: {affordability.is_affordable}",
        })

        # Tool 7: Procurement Plan
        proc_plan = self.optimize_procurement_plan(
            inv_status.shortage_units,
            self.profile.supplier_unit_cost,
            fin_pos.usable_cash,
            self.profile.daily_wastage_rate,
        )
        tool_trace.append({
            "step": 7,
            "tool": "optimize_procurement_plan",
            "summary": f"Order: {proc_plan.recommended_procurement_units:.0f} units ({proc_plan.procurement_mode}), Cost: Rs.{proc_plan.estimated_cost:,.2f}",
        })

        # ---------------------------------------------------------------------
        # Holistic Decision Synthesis
        # ---------------------------------------------------------------------
        # 1. Physical capacity limits how many total orders the kitchen can fulfill
        effective_capacity = max(0.0, cap)
        max_orders_by_capacity = min(demand_fc.projected_demand, effective_capacity)
        additional_allowed_by_capacity = max(0.0, min(additional_orders, effective_capacity - curr_demand))

        # 2. Material availability limits how many total orders can be made
        # (on-hand stock + affordable procurement)
        max_orders_by_materials = curr_inv + (
            inv_status.shortage_units if affordability.is_affordable else affordability.max_affordable_units
        )
        # But we do not procure more than achievable demand
        achievable_total = min(demand_fc.projected_demand, max_orders_by_capacity, max_orders_by_materials)
        fulfillable_additional = max(0.0, min(additional_orders, achievable_total - curr_demand))
        unfulfillable_additional = max(0.0, additional_orders - fulfillable_additional)

        # Classify the decision
        explanation_bullets: List[str] = []
        recommendations: List[str] = []

        if fulfillable_additional >= additional_orders:
            # We can fulfill ALL additional orders
            if inv_status.shortage_units == 0:
                decision = DecisionType.ACCEPT
                reason = "Both inventory and daily capacity comfortably accommodate all additional orders without requiring new procurement."
                explanation_bullets.append(f"Available inventory ({curr_inv:.0f} units) covers all {demand_fc.projected_demand:.0f} projected orders.")
                explanation_bullets.append(f"Daily capacity of {cap:.0f} orders/day is sufficient.")
                explanation_bullets.append("No additional working capital expenditure is required.")
                recommendations.append(f"Accept all {additional_orders:.0f} additional orders.")
                voice_response = (
                    f"Yes, you can safely take all {additional_orders:.0f} more orders tomorrow. "
                    f"Your current inventory of {curr_inv:.0f} units and capacity of {cap:.0f} orders can fulfill them without any extra purchases."
                )
            else:
                decision = DecisionType.ACCEPT_WITH_PROCUREMENT
                reason = (
                    f"Capacity is sufficient ({cap:.0f} orders/day), but an inventory shortage of "
                    f"{inv_status.shortage_units:.0f} units must be procured for Rs.{proc_plan.estimated_cost:,.2f}."
                )
                explanation_bullets.append(f"Daily capacity ({cap:.0f} orders) easily fits {demand_fc.projected_demand:.0f} total orders.")
                explanation_bullets.append(f"Current inventory ({curr_inv:.0f} units) is short by {inv_status.shortage_units:.0f} units.")
                explanation_bullets.append(
                    f"Procurement cost of Rs.{proc_plan.estimated_cost:,.2f} is fully affordable "
                    f"(leaves Rs.{fin_pos.usable_cash - proc_plan.estimated_cost:,.2f} usable cash above safety reserve)."
                )
                recommendations.append(f"Accept all {additional_orders:.0f} additional orders.")
                recommendations.append(f"Order {proc_plan.recommended_procurement_units:.0f} units of ingredients immediately.")
                voice_response = (
                    f"You can take all {additional_orders:.0f} more orders tomorrow if you procure ingredients today. "
                    f"You need {proc_plan.recommended_procurement_units:.0f} units costing Rs.{proc_plan.estimated_cost:,.0f}, "
                    f"which is well within your usable cash."
                )

        elif fulfillable_additional > 0:
            # We can fulfill SOME additional orders, but not all
            decision = DecisionType.ACCEPT_PARTIALLY
            recommendations.append(f"Accept {fulfillable_additional:.0f} additional orders.")
            recommendations.append(f"Decline the remaining {unfulfillable_additional:.0f} orders.")

            # Identify binding constraint
            if cap_status.is_bottleneck and not affordability.is_affordable:
                # Both constraints bind
                reason = (
                    f"Constrained by both production capacity ({cap:.0f} orders/day) and usable cash "
                    f"(Rs.{fin_pos.usable_cash:,.2f}). Only {fulfillable_additional:.0f} additional orders can be safely accepted."
                )
                explanation_bullets.append(f"Production capacity limits throughput to {cap:.0f} total orders.")
                explanation_bullets.append(f"Cash buffer allows procuring ingredients for only {affordability.max_affordable_units:.0f} units.")
                voice_response = (
                    f"You can safely take {fulfillable_additional:.0f} more orders tomorrow, but not all {additional_orders:.0f}. "
                    f"Your kitchen capacity is capped at {cap:.0f} orders, and your available cash limits further procurement."
                )
            elif cap_status.is_bottleneck:
                # Capacity is the sole or primary bottleneck
                reason = (
                    f"Inventory can be replenished, but production capacity is limited to "
                    f"{cap:.0f} orders/day. Therefore only {fulfillable_additional:.0f} of the additional {additional_orders:.0f} orders can be safely accepted."
                )
                explanation_bullets.append(f"Daily capacity ceiling is {cap:.0f} orders (current demand: {curr_demand:.0f}).")
                explanation_bullets.append(f"Maximum additional orders kitchen can prepare: {additional_allowed_by_capacity:.0f}.")
                explanation_bullets.append(f"Procuring ingredients for all {additional_orders:.0f} would produce excess stock that cannot be cooked.")
                voice_response = (
                    f"You can safely take {fulfillable_additional:.0f} more orders tomorrow. Your current capacity "
                    f"limits you to {cap:.0f} total orders. You have enough cash to procure the additional ingredients required."
                )
            else:
                # Cash is the binding constraint
                reason = (
                    f"Production capacity is sufficient, but usable cash (Rs.{fin_pos.usable_cash:,.2f}) "
                    f"is insufficient to procure all needed ingredients without violating your Rs.{fin_pos.safety_reserve:,.2f} safety reserve."
                )
                explanation_bullets.append(f"Covering all {additional_orders:.0f} orders requires Rs.{affordability.estimated_cost:,.2f} in ingredients.")
                explanation_bullets.append(f"Usable cash is only Rs.{fin_pos.usable_cash:,.2f} above reserve.")
                explanation_bullets.append(f"Buying {affordability.max_affordable_units:.0f} units allows fulfilling {fulfillable_additional:.0f} extra orders.")
                voice_response = (
                    f"You can only take {fulfillable_additional:.0f} more orders tomorrow because of cash limits. "
                    f"To protect your Rs.{fin_pos.safety_reserve:,.0f} safety reserve, you can only spend Rs.{proc_plan.estimated_cost:,.0f} on ingredients."
                )

        else:
            # CANNOT fulfill ANY additional orders
            decision = DecisionType.REJECT
            recommendations.append(f"Decline all {additional_orders:.0f} additional orders.")

            if curr_demand >= cap:
                reason = f"Current production capacity ({cap:.0f} orders/day) is already fully utilized by existing demand ({curr_demand:.0f} orders)."
                explanation_bullets.append(f"Kitchen is operating at 100% capacity ({curr_demand:.0f}/{cap:.0f} orders).")
                explanation_bullets.append("Accepting any more orders will cause delayed delivery, burnt food, or quality degradation.")
                voice_response = (
                    f"I recommend declining the {additional_orders:.0f} additional orders. Your kitchen is already at maximum capacity "
                    f"with {curr_demand:.0f} orders scheduled for tomorrow."
                )
            else:
                reason = "Working capital is completely exhausted; cannot procure required ingredients while preserving safety reserve."
                explanation_bullets.append(f"Current inventory ({curr_inv:.0f} units) is already committed to existing {curr_demand:.0f} orders.")
                explanation_bullets.append(f"Usable cash (Rs.{fin_pos.usable_cash:,.2f}) cannot afford any ingredient purchases.")
                voice_response = (
                    f"You should decline the {additional_orders:.0f} additional orders. Your available ingredients are already committed, "
                    f"and cash reserves cannot support new procurement today."
                )

        return OpportunityDecision(
            decision=decision,
            user_question=q_text,
            business_overview=overview,
            demand_forecast=demand_fc,
            inventory_status=inv_status,
            capacity_status=cap_status,
            financial_position=fin_pos,
            affordability=affordability,
            procurement_plan=proc_plan,
            fulfillable_additional_orders=fulfillable_additional,
            unfulfillable_additional_orders=unfulfillable_additional,
            reason=reason,
            recommendations=recommendations,
            explanation_bullets=explanation_bullets,
            voice_response=voice_response,
            tool_trace=tool_trace,
        )
