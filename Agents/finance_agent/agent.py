"""
Finance Agent
==============
Analyzes cash, profitability, and financial feasibility for Indian
micro-enterprises. Wraps and extends the low-level FinanceEngine with
higher-level intelligence tools suitable for agent/LLM consumption.

Tools provided:
  - get_financial_position()          → Current cash, P&L snapshot
  - forecast_cash_flow()              → N-day rolling cash projection
  - analyze_profitability()           → Margin, contribution, break-even
  - analyze_purchase_affordability()  → Can the business afford a purchase?
  - simulate_financial_impact()       → What-if scenario on a proposed action

Design follows the same dataclass + class pattern as FinanceEngine.
All data is deterministic / in-memory for hackathon demonstration purposes.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


SIMULATION_NOTICE = (
    "Finance Agent — deterministic in-memory projections. "
    "For hackathon demonstration only. Not connected to live banking or accounting APIs."
)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class FinancialPosition:
    """Point-in-time financial snapshot for a business."""
    business_type: str
    display_name: str
    cash_balance: float             # Rs — current liquid cash
    total_revenue_today: float
    total_cogs_today: float
    gross_profit_today: float
    gross_margin_pct: float
    operating_expenses_today: float
    net_profit_today: float
    net_margin_pct: float
    receivables_outstanding: float  # Unpaid but earned
    cash_runway_days: float         # Days of fixed costs covered
    health_label: str               # "healthy", "caution", "critical"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "display_name": self.display_name,
            "cash_balance_rs": round(self.cash_balance, 2),
            "today": {
                "revenue_rs": round(self.total_revenue_today, 2),
                "cogs_rs": round(self.total_cogs_today, 2),
                "gross_profit_rs": round(self.gross_profit_today, 2),
                "gross_margin_pct": round(self.gross_margin_pct, 2),
                "operating_expenses_rs": round(self.operating_expenses_today, 2),
                "net_profit_rs": round(self.net_profit_today, 2),
                "net_margin_pct": round(self.net_margin_pct, 2),
            },
            "receivables_outstanding_rs": round(self.receivables_outstanding, 2),
            "cash_runway_days": round(self.cash_runway_days, 1),
            "health_label": self.health_label,
            "simulation_notice": SIMULATION_NOTICE,
        }


@dataclass
class CashFlowForecast:
    """N-day rolling cash flow projection."""
    business_type: str
    forecast_days: int
    starting_cash: float
    projected_daily_inflow: float
    projected_daily_outflow: float
    projected_daily_net: float
    end_cash_balance: float
    lowest_cash_day: int
    lowest_cash_amount: float
    days_below_reserve: int
    cash_reserve_target: float
    daily_breakdown: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "forecast_days": self.forecast_days,
            "starting_cash_rs": round(self.starting_cash, 2),
            "projected_daily_inflow_rs": round(self.projected_daily_inflow, 2),
            "projected_daily_outflow_rs": round(self.projected_daily_outflow, 2),
            "projected_daily_net_rs": round(self.projected_daily_net, 2),
            "end_cash_balance_rs": round(self.end_cash_balance, 2),
            "lowest_cash_day": self.lowest_cash_day,
            "lowest_cash_amount_rs": round(self.lowest_cash_amount, 2),
            "days_below_reserve": self.days_below_reserve,
            "cash_reserve_target_rs": round(self.cash_reserve_target, 2),
            "daily_breakdown": self.daily_breakdown,
            "simulation_notice": SIMULATION_NOTICE,
        }


@dataclass
class ProfitabilityAnalysis:
    """Margin, contribution, and break-even analysis."""
    business_type: str
    selling_price: float
    unit_material_cost: float
    variable_cost_per_unit: float
    delivery_cost_per_unit: float
    platform_commission_rate: float
    daily_fixed_cost: float
    contribution_margin_per_unit: float
    contribution_margin_pct: float
    break_even_units_per_day: float
    daily_capacity: float
    capacity_utilisation_at_breakeven: float
    current_units_per_day: float
    profit_at_capacity: float
    profit_at_current: float
    margin_label: str               # "high", "medium", "low", "loss"
    insights: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "pricing": {
                "selling_price_rs": round(self.selling_price, 2),
                "unit_material_cost_rs": round(self.unit_material_cost, 2),
                "variable_cost_per_unit_rs": round(self.variable_cost_per_unit, 2),
                "delivery_cost_per_unit_rs": round(self.delivery_cost_per_unit, 2),
                "platform_commission_rate": round(self.platform_commission_rate, 4),
            },
            "contribution_margin_per_unit_rs": round(self.contribution_margin_per_unit, 2),
            "contribution_margin_pct": round(self.contribution_margin_pct, 2),
            "break_even_units_per_day": round(self.break_even_units_per_day, 1),
            "capacity_utilisation_at_breakeven_pct": round(self.capacity_utilisation_at_breakeven, 2),
            "current_units_per_day": round(self.current_units_per_day, 1),
            "profit_at_full_capacity_rs": round(self.profit_at_capacity, 2),
            "profit_at_current_demand_rs": round(self.profit_at_current, 2),
            "margin_label": self.margin_label,
            "insights": self.insights,
            "simulation_notice": SIMULATION_NOTICE,
        }


@dataclass
class AffordabilityAssessment:
    """Can the business afford a proposed purchase?"""
    business_type: str
    purchase_amount: float
    current_cash: float
    cash_reserve_target: float
    usable_cash: float
    cash_after_purchase: float
    is_affordable: bool
    affordability_ratio: float      # purchase / usable_cash (lower = safer)
    risk_label: str                 # "safe", "moderate", "high", "infeasible"
    recommendation: str
    alternatives: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "purchase_amount_rs": round(self.purchase_amount, 2),
            "current_cash_rs": round(self.current_cash, 2),
            "cash_reserve_target_rs": round(self.cash_reserve_target, 2),
            "usable_cash_rs": round(self.usable_cash, 2),
            "cash_after_purchase_rs": round(self.cash_after_purchase, 2),
            "is_affordable": self.is_affordable,
            "affordability_ratio": round(self.affordability_ratio, 3),
            "risk_label": self.risk_label,
            "recommendation": self.recommendation,
            "alternatives": self.alternatives,
            "simulation_notice": SIMULATION_NOTICE,
        }


@dataclass
class FinancialImpactSimulation:
    """What-if financial scenario result."""
    scenario_name: str
    business_type: str
    baseline_cash: float
    baseline_daily_profit: float
    simulated_cash: float
    simulated_daily_profit: float
    cash_delta: float
    profit_delta: float
    payback_days: Optional[float]   # Days to recover cash outflow from extra profit
    risk_label: str
    summary: str
    key_metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "business_type": self.business_type,
            "baseline": {
                "cash_rs": round(self.baseline_cash, 2),
                "daily_profit_rs": round(self.baseline_daily_profit, 2),
            },
            "simulated": {
                "cash_rs": round(self.simulated_cash, 2),
                "daily_profit_rs": round(self.simulated_daily_profit, 2),
            },
            "delta": {
                "cash_rs": round(self.cash_delta, 2),
                "daily_profit_rs": round(self.profit_delta, 2),
            },
            "payback_days": round(self.payback_days, 1) if self.payback_days else None,
            "risk_label": self.risk_label,
            "summary": self.summary,
            "key_metrics": self.key_metrics,
            "simulation_notice": SIMULATION_NOTICE,
        }


# ---------------------------------------------------------------------------
# Finance Agent
# ---------------------------------------------------------------------------

# Seeded business financial profiles for the demo
_BUSINESS_FINANCIALS: Dict[str, Dict[str, Any]] = {
    "home_tiffin": {
        "display_name": "Priya's Home Tiffin",
        "cash_balance": 8500.0,
        "selling_price": 120.0,
        "supplier_unit_cost": 45.0,
        "variable_cost_per_unit": 8.0,
        "delivery_cost_per_unit": 12.0,
        "platform_commission_rate": 0.10,
        "daily_fixed_cost": 300.0,
        "daily_capacity": 50.0,
        "base_daily_demand": 35.0,
        "receivables_outstanding": 0.0,
        "cash_reserve_target": 2000.0,
    },
    "street_cart": {
        "display_name": "Raj's Street Cart",
        "cash_balance": 4200.0,
        "selling_price": 60.0,
        "supplier_unit_cost": 20.0,
        "variable_cost_per_unit": 5.0,
        "delivery_cost_per_unit": 0.0,
        "platform_commission_rate": 0.05,
        "daily_fixed_cost": 150.0,
        "daily_capacity": 80.0,
        "base_daily_demand": 55.0,
        "receivables_outstanding": 0.0,
        "cash_reserve_target": 1000.0,
    },
    "small_restaurant": {
        "display_name": "Sharma Family Restaurant",
        "cash_balance": 22000.0,
        "selling_price": 250.0,
        "supplier_unit_cost": 90.0,
        "variable_cost_per_unit": 20.0,
        "delivery_cost_per_unit": 15.0,
        "platform_commission_rate": 0.12,
        "daily_fixed_cost": 800.0,
        "daily_capacity": 120.0,
        "base_daily_demand": 80.0,
        "receivables_outstanding": 1500.0,
        "cash_reserve_target": 5000.0,
    },
}


class FinanceAgent:
    """
    Analyzes cash, profitability, and financial feasibility.

    Provides five high-level financial intelligence tools for business
    owners and the Alexa autopilot system to make informed decisions.
    Seeded with deterministic demo data; cash_balance can be overridden
    at construction time for dynamic use.
    """

    def __init__(
        self,
        business_type: str = "home_tiffin",
        cash_balance_override: Optional[float] = None,
    ):
        """
        Args:
            business_type:          One of the seeded business types.
            cash_balance_override:  Live cash balance from DB if available.
        """
        profile = _BUSINESS_FINANCIALS.get(
            business_type, _BUSINESS_FINANCIALS["home_tiffin"]
        )
        self._biz: Dict[str, Any] = dict(profile)
        self._biz["business_type"] = business_type
        if cash_balance_override is not None:
            self._biz["cash_balance"] = cash_balance_override

    # ------------------------------------------------------------------
    # Tool 1: get_financial_position
    # ------------------------------------------------------------------
    def get_financial_position(self) -> Dict[str, Any]:
        """
        Returns the current financial snapshot: cash, today's P&L,
        receivables, cash runway, and a health label.

        Returns:
            FinancialPosition dict with all accounting and cash metrics.
        """
        b = self._biz
        demand = b["base_daily_demand"]

        revenue = demand * b["selling_price"]
        cogs = demand * b["supplier_unit_cost"]
        gross_profit = revenue - cogs
        gross_margin_pct = (gross_profit / revenue * 100) if revenue else 0.0

        commission = revenue * b["platform_commission_rate"]
        variable_ops = demand * b["variable_cost_per_unit"]
        delivery = demand * b["delivery_cost_per_unit"]
        opex = commission + variable_ops + delivery + b["daily_fixed_cost"]

        net_profit = gross_profit - opex
        net_margin_pct = (net_profit / revenue * 100) if revenue else 0.0

        cash_runway = (
            b["cash_balance"] / b["daily_fixed_cost"]
            if b["daily_fixed_cost"] > 0
            else 999.0
        )

        if b["cash_balance"] >= b["cash_reserve_target"] * 2 and net_profit > 0:
            health = "healthy"
        elif b["cash_balance"] >= b["cash_reserve_target"] and net_profit >= 0:
            health = "caution"
        else:
            health = "critical"

        return FinancialPosition(
            business_type=b["business_type"],
            display_name=b["display_name"],
            cash_balance=b["cash_balance"],
            total_revenue_today=revenue,
            total_cogs_today=cogs,
            gross_profit_today=gross_profit,
            gross_margin_pct=gross_margin_pct,
            operating_expenses_today=opex,
            net_profit_today=net_profit,
            net_margin_pct=net_margin_pct,
            receivables_outstanding=b["receivables_outstanding"],
            cash_runway_days=cash_runway,
            health_label=health,
        ).to_dict()

    # ------------------------------------------------------------------
    # Tool 2: forecast_cash_flow
    # ------------------------------------------------------------------
    def forecast_cash_flow(
        self,
        days: int = 7,
        planned_procurement_cost: float = 0.0,
        planned_procurement_day: int = 1,
    ) -> Dict[str, Any]:
        """
        Projects cash flow over the next N days based on current demand
        and cost structure. Optionally includes a planned procurement outflow.

        Args:
            days:                      Forecast horizon (1–30 days).
            planned_procurement_cost:  One-time procurement outflow (Rs).
            planned_procurement_day:   Day (1-indexed) of the procurement.

        Returns:
            CashFlowForecast dict with daily breakdown and summary stats.
        """
        days = max(1, min(30, days))
        b = self._biz
        demand = b["base_daily_demand"]

        daily_inflow = demand * b["selling_price"] * (1.0 - b["platform_commission_rate"])
        daily_outflow = (
            demand * b["supplier_unit_cost"]
            + demand * b["variable_cost_per_unit"]
            + demand * b["delivery_cost_per_unit"]
            + b["daily_fixed_cost"]
        )
        daily_net = daily_inflow - daily_outflow

        cash = b["cash_balance"]
        daily_breakdown: List[Dict[str, Any]] = []
        lowest_cash = cash
        lowest_day = 0
        days_below_reserve = 0

        for day in range(1, days + 1):
            inflow = daily_inflow
            outflow = daily_outflow

            # Add procurement hit on the planned day
            if day == planned_procurement_day and planned_procurement_cost > 0:
                outflow += planned_procurement_cost

            cash = cash + inflow - outflow

            if cash < lowest_cash:
                lowest_cash = cash
                lowest_day = day

            if cash < b["cash_reserve_target"]:
                days_below_reserve += 1

            daily_breakdown.append({
                "day": day,
                "inflow_rs": round(inflow, 2),
                "outflow_rs": round(outflow, 2),
                "net_rs": round(inflow - outflow, 2),
                "ending_cash_rs": round(cash, 2),
                "below_reserve": cash < b["cash_reserve_target"],
            })

        return CashFlowForecast(
            business_type=b["business_type"],
            forecast_days=days,
            starting_cash=b["cash_balance"],
            projected_daily_inflow=daily_inflow,
            projected_daily_outflow=daily_outflow,
            projected_daily_net=daily_net,
            end_cash_balance=cash,
            lowest_cash_day=lowest_day,
            lowest_cash_amount=lowest_cash,
            days_below_reserve=days_below_reserve,
            cash_reserve_target=b["cash_reserve_target"],
            daily_breakdown=daily_breakdown,
        ).to_dict()

    # ------------------------------------------------------------------
    # Tool 3: analyze_profitability
    # ------------------------------------------------------------------
    def analyze_profitability(self) -> Dict[str, Any]:
        """
        Computes contribution margin, break-even volume, and profit at
        current demand vs full capacity. Provides actionable insights.

        Returns:
            ProfitabilityAnalysis dict with margin metrics and insights.
        """
        b = self._biz
        sp = b["selling_price"]
        commission = sp * b["platform_commission_rate"]
        variable_total = (
            b["supplier_unit_cost"]
            + b["variable_cost_per_unit"]
            + b["delivery_cost_per_unit"]
            + commission
        )
        contribution_margin = sp - variable_total
        contribution_margin_pct = (contribution_margin / sp * 100) if sp > 0 else 0.0

        break_even = (
            b["daily_fixed_cost"] / contribution_margin
            if contribution_margin > 0
            else float("inf")
        )
        cap_util_at_be = (break_even / b["daily_capacity"] * 100) if b["daily_capacity"] > 0 else 0.0

        profit_at_capacity = (contribution_margin * b["daily_capacity"]) - b["daily_fixed_cost"]
        profit_at_current = (contribution_margin * b["base_daily_demand"]) - b["daily_fixed_cost"]

        if contribution_margin_pct >= 40:
            margin_label = "high"
        elif contribution_margin_pct >= 25:
            margin_label = "medium"
        elif contribution_margin_pct >= 10:
            margin_label = "low"
        else:
            margin_label = "loss"

        insights: List[str] = []
        if break_even > b["daily_capacity"]:
            insights.append("Break-even volume exceeds capacity — business is structurally loss-making at current prices.")
        elif break_even > b["base_daily_demand"]:
            insights.append(f"Current demand ({b['base_daily_demand']:.0f} units) is below break-even ({break_even:.1f}). Increase demand or reduce costs.")
        else:
            insights.append(f"Operating above break-even by {b['base_daily_demand'] - break_even:.1f} units/day.")

        if b["platform_commission_rate"] > 0.10:
            insights.append(f"Platform commission ({b['platform_commission_rate']*100:.0f}%) is high — negotiate lower rates or shift to direct sales.")

        if cap_util_at_be > 70:
            insights.append("High break-even utilisation — limited buffer if demand drops.")
        else:
            insights.append(f"Break-even is reached at only {cap_util_at_be:.0f}% capacity — good operational leverage.")

        if profit_at_current > 0:
            insights.append(f"At current demand: net daily profit ≈ Rs {profit_at_current:.0f}.")
        else:
            insights.append(f"At current demand: daily loss of Rs {abs(profit_at_current):.0f}. Urgent action required.")

        return ProfitabilityAnalysis(
            business_type=b["business_type"],
            selling_price=sp,
            unit_material_cost=b["supplier_unit_cost"],
            variable_cost_per_unit=b["variable_cost_per_unit"],
            delivery_cost_per_unit=b["delivery_cost_per_unit"],
            platform_commission_rate=b["platform_commission_rate"],
            daily_fixed_cost=b["daily_fixed_cost"],
            contribution_margin_per_unit=contribution_margin,
            contribution_margin_pct=contribution_margin_pct,
            break_even_units_per_day=break_even,
            daily_capacity=b["daily_capacity"],
            capacity_utilisation_at_breakeven=cap_util_at_be,
            current_units_per_day=b["base_daily_demand"],
            profit_at_capacity=profit_at_capacity,
            profit_at_current=profit_at_current,
            margin_label=margin_label,
            insights=insights,
        ).to_dict()

    # ------------------------------------------------------------------
    # Tool 4: analyze_purchase_affordability
    # ------------------------------------------------------------------
    def analyze_purchase_affordability(
        self,
        purchase_amount: float,
        cash_reserve_target: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Checks whether the business can afford a proposed purchase without
        breaching its cash safety reserve.

        Args:
            purchase_amount:      Total cost of the proposed purchase (Rs).
            cash_reserve_target:  Override for cash reserve floor (Rs).
                                  Defaults to the profile's cash_reserve_target.

        Returns:
            AffordabilityAssessment dict with feasibility, risk label,
            recommendation, and alternative strategies.
        """
        b = self._biz
        reserve = cash_reserve_target if cash_reserve_target is not None else b["cash_reserve_target"]
        usable_cash = max(0.0, b["cash_balance"] - reserve)
        cash_after = b["cash_balance"] - purchase_amount

        is_affordable = purchase_amount <= usable_cash
        ratio = purchase_amount / usable_cash if usable_cash > 0 else float("inf")

        if ratio <= 0.5:
            risk_label = "safe"
            recommendation = "Purchase is well within cash comfort zone. Proceed."
        elif ratio <= 0.8:
            risk_label = "moderate"
            recommendation = "Purchase is affordable but will use most of your usable cash. Confirm demand before proceeding."
        elif ratio <= 1.0:
            risk_label = "high"
            recommendation = "Purchase will nearly exhaust usable cash. Only proceed if demand is certain."
        else:
            risk_label = "infeasible"
            recommendation = (
                f"Purchase of Rs {purchase_amount:.0f} exceeds usable cash of Rs {usable_cash:.0f}. "
                "Consider alternatives below."
            )

        alternatives: List[str] = []
        if not is_affordable:
            shortfall = purchase_amount - usable_cash
            alternatives.append(f"Reduce order size by Rs {shortfall:.0f} to stay within usable cash.")
            alternatives.append("Split the purchase across two delivery dates to spread cash outflow.")
            days_to_save = shortfall / max(b["base_daily_demand"] * (b["selling_price"] - b["supplier_unit_cost"]), 1)
            alternatives.append(f"Wait ~{days_to_save:.0f} day(s) to accumulate sufficient cash from sales.")
        else:
            alternatives.append("No immediate alternatives needed — purchase is financially viable.")

        return AffordabilityAssessment(
            business_type=b["business_type"],
            purchase_amount=purchase_amount,
            current_cash=b["cash_balance"],
            cash_reserve_target=reserve,
            usable_cash=usable_cash,
            cash_after_purchase=cash_after,
            is_affordable=is_affordable,
            affordability_ratio=min(ratio, 99.0),
            risk_label=risk_label,
            recommendation=recommendation,
            alternatives=alternatives,
        ).to_dict()

    # ------------------------------------------------------------------
    # Tool 5: simulate_financial_impact
    # ------------------------------------------------------------------
    def simulate_financial_impact(
        self,
        scenario_name: str,
        procurement_cost: float = 0.0,
        demand_change_units: float = 0.0,
        price_change_rs: float = 0.0,
        fixed_cost_change_rs: float = 0.0,
        forecast_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Runs a what-if financial scenario to evaluate the impact of a
        proposed business action on cash and profitability.

        Common scenarios:
          - "Bulk procurement": set procurement_cost to the bulk order total.
          - "Demand surge":     set demand_change_units = +10.
          - "Price increase":   set price_change_rs = +10.
          - "Hire helper":      set fixed_cost_change_rs = +200.

        Args:
            scenario_name:          Human-readable scenario label.
            procurement_cost:       One-time cash outflow (Rs) on day 1.
            demand_change_units:    Daily demand delta (units/day).
            price_change_rs:        Selling price delta (Rs/unit).
            fixed_cost_change_rs:   Daily fixed cost delta (Rs/day).
            forecast_days:          Projection horizon (1–30 days).

        Returns:
            FinancialImpactSimulation dict with baseline vs simulated metrics.
        """
        b = self._biz
        forecast_days = max(1, min(30, forecast_days))

        # --- Baseline ---
        sp_base = b["selling_price"]
        demand_base = b["base_daily_demand"]
        commission_base = sp_base * b["platform_commission_rate"]
        var_total_base = (
            b["supplier_unit_cost"]
            + b["variable_cost_per_unit"]
            + b["delivery_cost_per_unit"]
            + commission_base
        )
        contribution_base = sp_base - var_total_base
        profit_base = contribution_base * demand_base - b["daily_fixed_cost"]
        cash_base = b["cash_balance"]

        # --- Simulated ---
        sp_sim = sp_base + price_change_rs
        demand_sim = demand_base + demand_change_units
        commission_sim = sp_sim * b["platform_commission_rate"]
        var_total_sim = (
            b["supplier_unit_cost"]
            + b["variable_cost_per_unit"]
            + b["delivery_cost_per_unit"]
            + commission_sim
        )
        contribution_sim = sp_sim - var_total_sim
        fixed_sim = b["daily_fixed_cost"] + fixed_cost_change_rs
        profit_sim = contribution_sim * demand_sim - fixed_sim
        cash_sim = cash_base - procurement_cost + (profit_sim - profit_base) * forecast_days

        cash_delta = cash_sim - cash_base
        profit_delta = profit_sim - profit_base

        # Payback: how many days of extra daily profit to recover procurement cost
        if procurement_cost > 0 and profit_delta > 0:
            payback_days: Optional[float] = procurement_cost / profit_delta
        else:
            payback_days = None

        # Risk assessment
        if cash_sim < b["cash_reserve_target"]:
            risk_label = "high"
        elif cash_sim < b["cash_reserve_target"] * 1.5:
            risk_label = "moderate"
        else:
            risk_label = "low"

        summary_parts = []
        if procurement_cost > 0:
            summary_parts.append(f"Procurement of Rs {procurement_cost:.0f} lowers cash immediately.")
        if profit_delta > 0:
            summary_parts.append(f"Daily profit improves by Rs {profit_delta:.0f}/day.")
            if payback_days:
                summary_parts.append(f"Cash recovered in ~{payback_days:.1f} days.")
        elif profit_delta < 0:
            summary_parts.append(f"Daily profit drops by Rs {abs(profit_delta):.0f}/day.")
        if not summary_parts:
            summary_parts.append("No significant financial change from this scenario.")

        return FinancialImpactSimulation(
            scenario_name=scenario_name,
            business_type=b["business_type"],
            baseline_cash=cash_base,
            baseline_daily_profit=profit_base,
            simulated_cash=cash_sim,
            simulated_daily_profit=profit_sim,
            cash_delta=cash_delta,
            profit_delta=profit_delta,
            payback_days=payback_days,
            risk_label=risk_label,
            summary=" ".join(summary_parts),
            key_metrics={
                "baseline_daily_profit_rs": round(profit_base, 2),
                "simulated_daily_profit_rs": round(profit_sim, 2),
                "baseline_cash_rs": round(cash_base, 2),
                "simulated_end_cash_rs": round(cash_sim, 2),
                "procurement_cost_rs": round(procurement_cost, 2),
                "demand_change_units": demand_change_units,
                "price_change_rs": price_change_rs,
                "fixed_cost_change_rs": fixed_cost_change_rs,
                "forecast_days": forecast_days,
            },
        ).to_dict()
