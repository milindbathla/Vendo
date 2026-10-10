"""
Alexa Business Autopilot — Baseline Decision Engine
===================================================
A deterministic, explainable decision pipeline for Indian small businesses.
Evaluates upcoming demand against business state (inventory, capacity, cash)
and recommends actionable procurement decisions with clear rationale.

Decision Pipeline:
Business State -> Demand Forecast -> Inventory Requirement -> Shortage
               -> Cash Constraints -> Procurement Options (Normal, Bulk, Partial)
               -> Decision Score -> Explainable Recommendation
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import math

from src.models.business import BusinessProfile


@dataclass
class AutopilotState:
    """Snapshot of business state for decision evaluation."""
    inventory_on_hand: float
    total_cash: float
    forecast_demand: float
    inventory_on_order: float = 0.0
    daily_capacity: Optional[float] = None
    cash_reserve_target: float = 2000.0
    lead_time_days: Optional[int] = None


@dataclass
class AutopilotOption:
    """A viable procurement option with financial impact and risk assessment."""
    name: str
    display_name: str
    quantity: float
    unit_cost: float
    total_cost: float
    cash_after: float
    stockout_units: float
    stockout_risk_pct: float
    cash_stress_pct: float
    wastage_risk_pct: float
    net_score: float
    is_feasible: bool
    description: str
    infeasible_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "quantity": round(self.quantity, 1),
            "unit_cost": round(self.unit_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "cash_after": round(self.cash_after, 2),
            "stockout_units": round(self.stockout_units, 1),
            "stockout_risk_pct": round(self.stockout_risk_pct, 1),
            "cash_stress_pct": round(self.cash_stress_pct, 1),
            "wastage_risk_pct": round(self.wastage_risk_pct, 1),
            "net_score": round(self.net_score, 2),
            "is_feasible": self.is_feasible,
            "infeasible_reason": self.infeasible_reason,
            "description": self.description,
        }


@dataclass
class AutopilotRecommendation:
    """Comprehensive decision package returned by Business Autopilot."""
    business_type: str
    display_name: str
    forecast_demand: float
    available_inventory: float
    daily_capacity: float
    capacity_constrained: bool
    unfulfillable_demand_due_to_capacity: float
    shortage: float
    usable_cash: float
    total_cash: float
    cash_reserve_target: float
    options: List[AutopilotOption]
    recommended_option: AutopilotOption
    reason: str
    explanation_bullets: List[str]
    conversational_response: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "display_name": self.display_name,
            "forecast_demand": round(self.forecast_demand, 1),
            "available_inventory": round(self.available_inventory, 1),
            "daily_capacity": round(self.daily_capacity, 1),
            "capacity_constrained": self.capacity_constrained,
            "unfulfillable_demand_due_to_capacity": round(self.unfulfillable_demand_due_to_capacity, 1),
            "shortage": round(self.shortage, 1),
            "usable_cash": round(self.usable_cash, 2),
            "total_cash": round(self.total_cash, 2),
            "cash_reserve_target": round(self.cash_reserve_target, 2),
            "options": [opt.to_dict() for opt in self.options],
            "recommendation": self.recommended_option.name,
            "recommended_quantity": round(self.recommended_option.quantity, 1),
            "recommended_cost": round(self.recommended_option.total_cost, 2),
            "reason": self.reason,
            "explanation_bullets": self.explanation_bullets,
            "conversational_response": self.conversational_response,
        }


class BusinessAutopilot:
    """
    Baseline Decision Engine for Alexa Business Autopilot.
    Consumes business state and profile parameters to recommend optimal, safe actions.
    """

    def __init__(self, profile: BusinessProfile, enforce_moq: bool = False):
        self.profile = profile
        self.enforce_moq = enforce_moq

    def analyze(
        self,
        state: Optional[AutopilotState] = None,
        forecast_demand: Optional[float] = None,
        inventory_on_hand: Optional[float] = None,
        total_cash: Optional[float] = None,
        daily_capacity: Optional[float] = None,
    ) -> AutopilotRecommendation:
        """
        Executes the baseline decision pipeline and returns a structured recommendation.
        """
        on_hand = inventory_on_hand if inventory_on_hand is not None else (
            state.inventory_on_hand if state else self.profile.starting_inventory
        )
        on_order = state.inventory_on_order if state else 0.0
        cash = total_cash if total_cash is not None else (
            state.total_cash if state else self.profile.starting_capital
        )
        demand = forecast_demand if forecast_demand is not None else (
            state.forecast_demand if state else self.profile.base_daily_demand
        )
        capacity = daily_capacity if daily_capacity is not None else (
            state.daily_capacity if (state and state.daily_capacity is not None) else self.profile.daily_capacity
        )
        reserve_target = state.cash_reserve_target if state else 2000.0

        available_inv = on_hand + on_order
        usable_cash = max(0.0, cash - reserve_target)

        # 1. Capacity bottleneck evaluation
        effective_capacity = max(1.0, capacity)
        capacity_constrained = demand > effective_capacity
        unfulfillable_cap = max(0.0, demand - effective_capacity) if capacity_constrained else 0.0

        # Maximum demand that could physically be fulfilled given operational capacity
        effective_achievable_demand = min(demand, effective_capacity)

        # 2. Inventory shortage evaluation
        shortage = max(0.0, effective_achievable_demand - available_inv)

        # 3. Generate and Evaluate Options
        options: List[AutopilotOption] = []

        # Case A: Inventory already covers achievable demand
        if shortage <= 0.0:
            no_purchase_opt = AutopilotOption(
                name="no_purchase",
                display_name="No Purchase Required",
                quantity=0.0,
                unit_cost=self.profile.supplier_unit_cost,
                total_cost=0.0,
                cash_after=cash,
                stockout_units=0.0,
                stockout_risk_pct=0.0,
                cash_stress_pct=0.0,
                wastage_risk_pct=round(self.profile.daily_wastage_rate * 100, 1),
                net_score=100.0,
                is_feasible=True,
                description=f"Current inventory ({available_inv:.0f} units) fully covers expected demand ({demand:.0f} orders).",
            )
            options.append(no_purchase_opt)
            rec_option = no_purchase_opt

            bullets = [
                f"Current inventory ({available_inv:.0f} units) is sufficient for tomorrow's demand ({demand:.0f} orders).",
                f"No additional procurement expenditure needed; full liquid cash of Rs.{cash:,.2f} preserved.",
            ]
            if capacity_constrained:
                bullets.append(
                    f"Warning: Expected demand ({demand:.0f}) exceeds daily production capacity ceiling ({effective_capacity:.0f}). "
                    f"About {unfulfillable_cap:.0f} orders cannot be fulfilled due to capacity ceiling, not inventory."
                )

            conv_response = (
                f"You have {available_inv:.0f} units in stock and expect {demand:.0f} orders tomorrow. "
                f"No purchase is needed right now. All orders can be prepared with existing supplies."
            )
            if capacity_constrained:
                conv_response += (
                    f" Note that your daily capacity is {effective_capacity:.0f} orders, so about "
                    f"{unfulfillable_cap:.0f} orders will exceed your daily throughput."
                )

            return AutopilotRecommendation(
                business_type=self.profile.business_type,
                display_name=self.profile.display_name,
                forecast_demand=demand,
                available_inventory=available_inv,
                daily_capacity=effective_capacity,
                capacity_constrained=capacity_constrained,
                unfulfillable_demand_due_to_capacity=unfulfillable_cap,
                shortage=0.0,
                usable_cash=usable_cash,
                total_cash=cash,
                cash_reserve_target=reserve_target,
                options=options,
                recommended_option=rec_option,
                reason="Existing on-hand inventory is sufficient to fulfill all achievable customer demand.",
                explanation_bullets=bullets,
                conversational_response=conv_response,
            )

        # Case B: Shortage exists -> evaluate Normal, Bulk, and Partial/Wait options
        # -------------------------------------------------------------------------
        # Option 1: Normal Procurement (Buys required shortage)
        norm_qty = max(shortage, self.profile.min_order_quantity if self.enforce_moq else shortage)
        norm_unit_cost = self.profile.supplier_unit_cost
        norm_total_cost = norm_qty * norm_unit_cost
        norm_feasible = norm_total_cost <= usable_cash
        norm_cash_after = cash - norm_total_cost if norm_feasible else cash
        norm_cash_stress = (norm_total_cost / usable_cash * 100) if usable_cash > 0 else 100.0

        norm_score = self._compute_option_score(
            fulfilled_demand=effective_achievable_demand,
            shortage_remaining=0.0 if norm_feasible else shortage,
            total_cost=norm_total_cost,
            cash_after=norm_cash_after,
            usable_cash=usable_cash,
            excess_inventory=max(0.0, available_inv + norm_qty - effective_achievable_demand),
            unit_cost=norm_unit_cost,
            is_feasible=norm_feasible,
        )

        norm_opt = AutopilotOption(
            name="normal_purchase",
            display_name="Normal Procurement",
            quantity=norm_qty,
            unit_cost=norm_unit_cost,
            total_cost=norm_total_cost,
            cash_after=norm_cash_after,
            stockout_units=0.0 if norm_feasible else shortage,
            stockout_risk_pct=0.0 if norm_feasible else 100.0,
            cash_stress_pct=min(100.0, norm_cash_stress),
            wastage_risk_pct=round(self.profile.daily_wastage_rate * 100, 1),
            net_score=norm_score,
            is_feasible=norm_feasible,
            description=f"Order {norm_qty:.0f} units at regular wholesale cost (Rs.{norm_unit_cost:.2f}/unit).",
            infeasible_reason=None if norm_feasible else f"Cost (Rs.{norm_total_cost:,.0f}) exceeds usable cash buffer (Rs.{usable_cash:,.0f}).",
        )
        options.append(norm_opt)

        # Option 2: Bulk Procurement (Unlock wholesale discount at bulk threshold)
        bulk_qty = max(norm_qty, self.profile.bulk_order_threshold)
        bulk_unit_cost = self.profile.supplier_unit_cost * (1.0 - self.profile.bulk_discount)
        bulk_total_cost = bulk_qty * bulk_unit_cost
        bulk_feasible = bulk_total_cost <= usable_cash
        bulk_cash_after = cash - bulk_total_cost if bulk_feasible else cash
        bulk_cash_stress = (bulk_total_cost / usable_cash * 100) if usable_cash > 0 else 100.0
        bulk_excess_inv = max(0.0, available_inv + bulk_qty - effective_achievable_demand)

        bulk_score = self._compute_option_score(
            fulfilled_demand=effective_achievable_demand,
            shortage_remaining=0.0 if bulk_feasible else shortage,
            total_cost=bulk_total_cost,
            cash_after=bulk_cash_after,
            usable_cash=usable_cash,
            excess_inventory=bulk_excess_inv,
            unit_cost=bulk_unit_cost,
            is_feasible=bulk_feasible,
        )

        bulk_opt = AutopilotOption(
            name="bulk_purchase",
            display_name="Bulk Procurement",
            quantity=bulk_qty,
            unit_cost=bulk_unit_cost,
            total_cost=bulk_total_cost,
            cash_after=bulk_cash_after,
            stockout_units=0.0 if bulk_feasible else shortage,
            stockout_risk_pct=0.0 if bulk_feasible else 100.0,
            cash_stress_pct=min(100.0, bulk_cash_stress),
            wastage_risk_pct=min(100.0, round(self.profile.daily_wastage_rate * 180, 1)),
            net_score=bulk_score,
            is_feasible=bulk_feasible,
            description=f"Order {bulk_qty:.0f} units to unlock {self.profile.bulk_discount*100:.0f}% wholesale discount (Rs.{bulk_unit_cost:.2f}/unit).",
            infeasible_reason=None if bulk_feasible else f"Requires Rs.{bulk_total_cost:,.0f} which exceeds usable cash of Rs.{usable_cash:,.0f}.",
        )
        options.append(bulk_opt)

        # Option 3: Wait / Partial Purchase (Buy less than required to preserve cash, accept some stockout risk)
        if not norm_feasible:
            # When normal procurement is unaffordable, buy what liquid cash allows
            partial_qty = max(0.0, math.floor(usable_cash / norm_unit_cost))
            partial_qty = min(partial_qty, max(0.0, shortage - 1.0))
        else:
            # Voluntary cash preservation: buy 40-50% of shortage or 0 units
            partial_qty = max(0.0, math.floor(shortage * 0.4))

        partial_cost = partial_qty * norm_unit_cost
        partial_uncovered = shortage - partial_qty
        partial_feasible = partial_cost <= usable_cash
        partial_cash_after = cash - partial_cost
        partial_cash_stress = (partial_cost / usable_cash * 100) if usable_cash > 0 else 0.0

        partial_score = self._compute_option_score(
            fulfilled_demand=effective_achievable_demand - partial_uncovered,
            shortage_remaining=partial_uncovered,
            total_cost=partial_cost,
            cash_after=partial_cash_after,
            usable_cash=usable_cash,
            excess_inventory=0.0,
            unit_cost=norm_unit_cost,
            is_feasible=partial_feasible,
        )

        partial_desc = (
            f"Buy {partial_qty:.0f} units to preserve cash (accept {partial_uncovered:.0f} unfulfilled orders)."
            if partial_qty > 0
            else f"Hold off purchasing to conserve liquid cash (accept {shortage:.0f} unfulfilled orders)."
        )

        partial_opt = AutopilotOption(
            name="partial_or_conserve",
            display_name="Cash Preservation / Partial",
            quantity=partial_qty,
            unit_cost=norm_unit_cost,
            total_cost=partial_cost,
            cash_after=partial_cash_after,
            stockout_units=partial_uncovered,
            stockout_risk_pct=round((partial_uncovered / max(1.0, demand)) * 100, 1),
            cash_stress_pct=min(100.0, partial_cash_stress),
            wastage_risk_pct=0.0,
            net_score=partial_score,
            is_feasible=partial_feasible,
            description=partial_desc,
            infeasible_reason=None,
        )
        options.append(partial_opt)

        # 4. Select Optimal Feasible Option
        feasible_options = [opt for opt in options if opt.is_feasible]
        if feasible_options:
            rec_option = max(feasible_options, key=lambda opt: opt.net_score)
        else:
            rec_option = partial_opt

        # 5. Build Human-Explainable Rationale & Bullets
        bullets = []
        bullets.append(f"Tomorrow's expected demand: {demand:.0f} orders.")
        bullets.append(f"Current available inventory: {available_inv:.0f} units (Shortage: {shortage:.0f} units).")

        if capacity_constrained:
            bullets.append(
                f"Daily capacity ceiling: {effective_capacity:.0f} orders/day. "
                f"Even with infinite stock, {unfulfillable_cap:.0f} orders cannot be fulfilled today without expanding kitchen capacity."
            )

        if rec_option.name == "normal_purchase":
            bullets.append(f"Normal procurement covers the {shortage:.0f}-unit shortage cleanly.")
            bullets.append(f"Requires Rs.{rec_option.total_cost:,.2f}, leaving Rs.{rec_option.cash_after:,.2f} in cash (comfortably above Rs.{reserve_target:,.0f} safety reserve).")
            if bulk_feasible:
                bullets.append(
                    f"Bulk procurement ({bulk_qty:.0f} units) saves Rs.{(norm_unit_cost - bulk_unit_cost):.2f}/unit but commits "
                    f"Rs.{(bulk_total_cost - norm_total_cost):,.0f} more cash and increases spoilage risk on excess stock."
                )
                bullets.append("Preserving working capital and avoiding perishable holding risk is preferable.")
            else:
                bullets.append(f"Bulk purchase was rejected because Rs.{bulk_total_cost:,.0f} exceeds your usable cash buffer of Rs.{usable_cash:,.0f}.")
            reason = f"Normal procurement covers tomorrow's {shortage:.0f}-unit shortage safely while protecting working capital."

        elif rec_option.name == "bulk_purchase":
            savings = (self.profile.supplier_unit_cost - bulk_unit_cost) * bulk_qty
            bullets.append(f"Bulk procurement of {rec_option.quantity:.0f} units unlocks a {self.profile.bulk_discount*100:.0f}% wholesale discount, saving Rs.{savings:,.2f}.")
            bullets.append(f"Your usable cash buffer of Rs.{usable_cash:,.2f} is sufficient to absorb the Rs.{rec_option.total_cost:,.2f} investment.")
            bullets.append(f"Leaves Rs.{rec_option.cash_after:,.2f} liquid cash after purchase, maintaining the safety buffer.")
            reason = f"Bulk procurement unlocks wholesale discounts of Rs.{savings:,.0f} and your cash buffer comfortably accommodates the lot."

        else: # partial_or_conserve
            bullets.append(f"Usable cash is heavily constrained (only Rs.{usable_cash:,.2f} above safety reserve).")
            bullets.append(f"Normal procurement would compromise liquid working capital. Recommending {rec_option.quantity:.0f} units.")
            bullets.append(f"Warning: {rec_option.stockout_units:.0f} orders will be unfulfilled to protect enterprise solvency.")
            reason = "Working capital is constrained; conserving liquid cash is prioritized over full order coverage."

        # 6. Conversational Alexa-Style Voice Response
        conv_response = self._format_conversational_response(
            rec_option=rec_option,
            demand=demand,
            available_inv=available_inv,
            shortage=shortage,
            capacity=effective_capacity,
            capacity_constrained=capacity_constrained,
        )

        return AutopilotRecommendation(
            business_type=self.profile.business_type,
            display_name=self.profile.display_name,
            forecast_demand=demand,
            available_inventory=available_inv,
            daily_capacity=effective_capacity,
            capacity_constrained=capacity_constrained,
            unfulfillable_demand_due_to_capacity=unfulfillable_cap,
            shortage=shortage,
            usable_cash=usable_cash,
            total_cash=cash,
            cash_reserve_target=reserve_target,
            options=options,
            recommended_option=rec_option,
            reason=reason,
            explanation_bullets=bullets,
            conversational_response=conv_response,
        )

    def answer_owner_question(
        self,
        question: str,
        forecast_demand: Optional[float] = None,
        state: Optional[AutopilotState] = None,
    ) -> Dict[str, Any]:
        """
        Simulates an Alexa voice dialog:
        Owner asks e.g. "I have 20 tiffin orders tomorrow. Can I fulfill them?"
        Returns structured analysis and natural response text.
        """
        rec = self.analyze(state=state, forecast_demand=forecast_demand)
        return {
            "question": question,
            "conversational_response": rec.conversational_response,
            "structured_recommendation": rec.to_dict(),
        }

    def run_what_if_scenarios(
        self,
        base_state: Optional[AutopilotState] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs key what-if baseline scenarios demonstrating how recommendations adapt.
        """
        state = base_state or AutopilotState(
            inventory_on_hand=14.0,
            total_cash=8000.0,
            forecast_demand=20.0,
            daily_capacity=25.0,
            cash_reserve_target=2000.0,
        )

        scenarios = [
            {
                "id": "scenario_1_baseline",
                "name": "Scenario 1: Expected Demand",
                "description": f"Standard forecast of {state.forecast_demand:.0f} orders with Rs.{state.total_cash:,.0f} cash.",
                "state": state,
            },
            {
                "id": "scenario_2_demand_surge",
                "name": "Scenario 2: +40% Demand Surge",
                "description": f"Demand spike ({state.forecast_demand * 1.4:.0f} orders) stressing inventory.",
                "state": AutopilotState(
                    inventory_on_hand=state.inventory_on_hand,
                    total_cash=state.total_cash,
                    forecast_demand=round(state.forecast_demand * 1.4),
                    daily_capacity=state.daily_capacity,
                    cash_reserve_target=state.cash_reserve_target,
                ),
            },
            {
                "id": "scenario_3_cash_crunch",
                "name": "Scenario 3: Severe Cash Crunch",
                "description": "Cash reduced to Rs.2,200 (usable cash = Rs.200 above reserve).",
                "state": AutopilotState(
                    inventory_on_hand=state.inventory_on_hand,
                    total_cash=2200.0,
                    forecast_demand=state.forecast_demand,
                    daily_capacity=state.daily_capacity,
                    cash_reserve_target=state.cash_reserve_target,
                ),
            },
            {
                "id": "scenario_4_capacity_choke",
                "name": "Scenario 4: Restricted Capacity",
                "description": "Daily capacity restricted to 15 orders/day (burner down / staff absent).",
                "state": AutopilotState(
                    inventory_on_hand=state.inventory_on_hand,
                    total_cash=state.total_cash,
                    forecast_demand=state.forecast_demand,
                    daily_capacity=15.0,
                    cash_reserve_target=state.cash_reserve_target,
                ),
            },
        ]

        results = []
        for sc in scenarios:
            rec = self.analyze(state=sc["state"])
            results.append({
                "scenario_id": sc["id"],
                "scenario_name": sc["name"],
                "description": sc["description"],
                "forecast_demand": rec.forecast_demand,
                "available_inventory": rec.available_inventory,
                "shortage": rec.shortage,
                "capacity": rec.daily_capacity,
                "capacity_constrained": rec.capacity_constrained,
                "recommended_action": rec.recommended_option.display_name,
                "recommended_qty": rec.recommended_option.quantity,
                "estimated_cost": rec.recommended_option.total_cost,
                "cash_after": rec.recommended_option.cash_after,
                "stockout_units": rec.recommended_option.stockout_units,
                "reason": rec.reason,
            })
        return results

    def _compute_option_score(
        self,
        fulfilled_demand: float,
        shortage_remaining: float,
        total_cost: float,
        cash_after: float,
        usable_cash: float,
        excess_inventory: float,
        unit_cost: float,
        is_feasible: bool,
    ) -> float:
        """
        Deterministic, explainable utility score:
        Revenue Gained - Procurement Cost - Stockout Penalty - Spoilage Penalty - Cash Stress Penalty
        """
        if not is_feasible:
            return -9999.0

        revenue = fulfilled_demand * self.profile.selling_price
        gross_procurement_cost = total_cost

        # Stockout penalty accounts for lost margin + customer churn risk multiplier (1.5x)
        contribution_margin = max(1.0, self.profile.selling_price - self.profile.variable_cost_per_unit)
        stockout_penalty = shortage_remaining * contribution_margin * 1.5

        # Spoilage / holding risk penalty on excess stock
        spoilage_penalty = excess_inventory * unit_cost * self.profile.daily_wastage_rate

        # Cash stress penalty accelerates quadratically as spend approaches usable cash limit
        spend_fraction = min(1.0, total_cost / max(1.0, usable_cash))
        cash_stress_penalty = (spend_fraction ** 2) * (unit_cost * 1.5)

        net_utility = revenue - gross_procurement_cost - stockout_penalty - spoilage_penalty - cash_stress_penalty
        return net_utility

    def _format_conversational_response(
        self,
        rec_option: AutopilotOption,
        demand: float,
        available_inv: float,
        shortage: float,
        capacity: float,
        capacity_constrained: bool,
    ) -> str:
        """Formats an intuitive voice-ready response."""
        if rec_option.name == "normal_purchase":
            msg = (
                f"You have {available_inv:.0f} units and need {demand:.0f} for tomorrow. "
                f"I recommend ordering {rec_option.quantity:.0f} units using normal procurement. "
                f"This will cost Rs.{rec_option.total_cost:,.0f} and leave you with Rs.{rec_option.cash_after:,.0f} in cash."
            )
        elif rec_option.name == "bulk_purchase":
            msg = (
                f"You have {available_inv:.0f} units and expect {demand:.0f} orders. "
                f"You have a strong cash buffer of Rs.{rec_option.cash_after:,.0f}, so I recommend buying {rec_option.quantity:.0f} units in bulk. "
                f"This unlocks a {self.profile.bulk_discount*100:.0f}% discount, costing Rs.{rec_option.total_cost:,.0f}."
            )
        elif rec_option.name == "partial_or_conserve":
            msg = (
                f"You have {available_inv:.0f} units and expect {demand:.0f} orders, but cash is tight. "
                f"To protect your Rs.2,000 safety reserve, I recommend buying only {rec_option.quantity:.0f} units for Rs.{rec_option.total_cost:,.0f}. "
                f"You will be short by {rec_option.stockout_units:.0f} orders, but your cash will be protected."
            )
        else:
            msg = f"You are fully stocked for tomorrow's {demand:.0f} orders with {available_inv:.0f} units on hand. No purchase needed."

        if capacity_constrained:
            msg += f" Note: your daily capacity is {capacity:.0f} orders, so peak orders above that cannot be fulfilled."

        return msg
