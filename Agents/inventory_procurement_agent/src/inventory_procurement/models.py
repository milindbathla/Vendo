"""Data models and exceptions for Inventory & Procurement specialist agent."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class BusinessMCPError(Exception):
    """Base exception for Business MCP components."""
    pass


class ValidationError(BusinessMCPError):
    """Raised when input validation fails."""
    pass


class ResourceNotFoundError(BusinessMCPError):
    """Raised when a requested resource is not found in the database."""
    pass


class ConstraintViolationError(BusinessMCPError):
    """Raised when a business constraint or policy is violated."""
    pass


@dataclass
class MetaInfo:
    """System metadata and planning dates."""
    as_of: str
    frozen_date: str
    tomorrow_date: str
    business_name: str
    currency: str = "INR"
    single_menu_item: Optional[str] = None
    menu_price_one_off: Optional[float] = None
    menu_price_subscription: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BusinessPolicy:
    """Configured business policies and thresholds."""
    policy_id: int
    min_cash_buffer: float
    safety_stock_pct: float
    regular_order_cutoff: str
    cooking_start: str
    packing_start: str
    max_meals_per_day: int
    fast_delivery_fee: float
    stockout_cost_per_meal: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ItemInventoryStatus:
    item_id: str
    item_name: str
    unit: str
    procure_mode: str
    reorder_point: float
    par_level: float
    bom_qty: float
    effective_requirement: float
    current_stock: float
    projected_stock: float
    shortfall_qty: float
    is_shortfall: bool
    below_reorder_point: bool
    below_par_level: bool
    last_restocked_date: Optional[str] = None
    last_restocked_qty: Optional[float] = None
    refresh_forecast_date: Optional[str] = None
    refresh_forecast_qty: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InventoryAnalysisResponse:
    planning_date: str
    forecast_units: float
    effective_units: float
    safety_stock_pct: float
    items: List[ItemInventoryStatus]
    shortfall_items_count: int
    below_reorder_items_count: int
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date,
            "forecast_units": self.forecast_units,
            "effective_units": self.effective_units,
            "safety_stock_pct": self.safety_stock_pct,
            "items": [item.to_dict() for item in self.items],
            "shortfall_items_count": self.shortfall_items_count,
            "below_reorder_items_count": self.below_reorder_items_count,
            "summary": self.summary,
        }


@dataclass
class RestockItemNeed:
    item_id: str
    item_name: str
    unit: str
    urgency: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    needed_qty: float
    needed_by: str
    reason: str
    current_stock: float
    reorder_point: float
    par_level: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RestockNeedAssessmentResponse:
    planning_date: str
    critical_shortfalls: List[RestockItemNeed]
    reorder_point_triggers: List[RestockItemNeed]
    par_level_targets: List[RestockItemNeed]
    urgency_ranking: List[RestockItemNeed]
    recommended_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date,
            "critical_shortfalls": [i.to_dict() for i in self.critical_shortfalls],
            "reorder_point_triggers": [i.to_dict() for i in self.reorder_point_triggers],
            "par_level_targets": [i.to_dict() for i in self.par_level_targets],
            "urgency_ranking": [i.to_dict() for i in self.urgency_ranking],
            "recommended_actions": self.recommended_actions,
        }


@dataclass
class ProcurementOption:
    item_id: str
    item_name: str
    supplier_id: str
    supplier_name: str
    pack_label: str
    pack_qty: float
    price_per_pack: float
    price_per_unit: float
    packs_needed: int
    total_units_provided: float
    subtotal: float
    delivery_fee: float
    free_delivery_threshold: Optional[float]
    total_cost: float
    cutoff_time: str
    delivery_window: str
    eta_minutes: int
    earliest_arrival: str
    deadline: str
    in_stock: bool
    reliability: float
    is_simulated: bool
    is_feasible: bool
    feasibility_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcurementOptionsResponse:
    planning_date: str
    target_items: List[Dict[str, Any]]
    options: List[ProcurementOption]
    filtered_out_options: List[Dict[str, Any]]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date,
            "target_items": self.target_items,
            "options": [opt.to_dict() for opt in self.options],
            "filtered_out_options": self.filtered_out_options,
            "summary": self.summary,
        }


@dataclass
class PlanLineDetail:
    item_id: str
    item_name: str
    supplier_id: str
    supplier_name: str
    pack_qty: int
    unit_qty_equivalent: float
    price_per_pack: float
    line_subtotal: float
    earliest_arrival: str
    is_simulated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizedPlan:
    plan_name: str
    strategy: str
    lines: List[PlanLineDetail]
    items_subtotal: float
    total_delivery_fees: float
    total_cost: float
    supplier_breakdown: List[Dict[str, Any]]
    buffer_compliant: bool
    post_plan_min_balance: float
    min_cash_buffer: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lines"] = [line.to_dict() for line in self.lines]
        return d


@dataclass
class OptimizeProcurementPlanResponse:
    planning_date: str
    is_fully_feasible: bool
    recommended_plan: Optional[OptimizedPlan]
    candidate_alternatives: List[Dict[str, Any]]
    financial_impact: Dict[str, Any]
    risks_and_considerations: List[str]
    unmet_requirements: List[str]
    decision_rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date,
            "is_fully_feasible": self.is_fully_feasible,
            "recommended_plan": self.recommended_plan.to_dict() if self.recommended_plan else None,
            "candidate_alternatives": self.candidate_alternatives,
            "financial_impact": self.financial_impact,
            "risks_and_considerations": self.risks_and_considerations,
            "unmet_requirements": self.unmet_requirements,
            "decision_rationale": self.decision_rationale,
        }


@dataclass
class CreatePurchasePlanResponse:
    plan_id: str
    status: str
    total_cost: float
    created_at: str
    lines_count: int
    approval_token: str
    approval_expires_at: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutePurchaseResponse:
    success: bool
    plan_id: str
    status: str
    simulated_orders: List[Dict[str, Any]]
    executed_at: str
    audit_log_id: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

