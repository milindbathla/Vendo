"""Data models and exceptions for Demand & Capacity specialist agent."""

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
class DemandDriverInfo:
    date: str
    weekday: str
    is_holiday: int
    festival: Optional[str]
    weather: Optional[str]
    local_event: Optional[str]
    subscription_pauses: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastDayResult:
    date: str
    status: str  # "available" | "unavailable"
    forecast_units: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    confidence: Optional[float] = None
    method: Optional[str] = None
    demand_driver: Optional[DemandDriverInfo] = None
    confirmed_orders_count: int = 0
    confirmed_units: int = 0
    tentative_units: int = 0
    historical_status: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.demand_driver:
            d["demand_driver"] = self.demand_driver.to_dict()
        return d


@dataclass
class DemandForecastResponse:
    planning_date: str
    start_date: str
    end_date: str
    scenario: Optional[str]
    days: List[ForecastDayResult]
    total_forecast_units: float
    total_confirmed_units: int
    total_tentative_units: int
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "scenario": self.scenario,
            "days": [day.to_dict() for day in self.days],
            "total_forecast_units": round(self.total_forecast_units, 2),
            "total_confirmed_units": self.total_confirmed_units,
            "total_tentative_units": self.total_tentative_units,
            "notes": self.notes,
        }


@dataclass
class DemandPatternAnalysis:
    sample_size: int
    date_range: Dict[str, str]
    weekday_distribution: Dict[str, Dict[str, Any]]
    order_type_distribution: Dict[str, Dict[str, Any]]
    order_status_distribution: Dict[str, int]
    recurring_customer_snapshot: Dict[str, Any]
    trend_observations: List[str]
    uncertainty_limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeliverySlotStatus:
    slot_id: str
    date: str
    slot_label: str
    start_time: str
    end_time: str
    capacity_units: int
    booked_units: int
    free_units: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapacityStatusResponse:
    date: str
    max_production_meals: int
    cook_hours: float
    committed_units: int
    remaining_production_capacity: int
    production_utilization_pct: float
    delivery_slots: List[DeliverySlotStatus]
    total_slot_capacity: int
    total_slot_booked: int
    total_slot_free: int
    declared_capacity: Optional[Dict[str, Any]]
    tightest_constraint: str
    capacity_shortfall: int
    bottlenecks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["delivery_slots"] = [s.to_dict() for s in self.delivery_slots]
        return d


@dataclass
class ItemRequirementSim:
    item_id: str
    name: str
    unit: str
    bom_qty: float
    required_qty: float
    current_stock: float
    shortfall_qty: float
    is_shortfall: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AdditionalDemandSimulationResponse:
    feasible: bool
    binding_constraint: Optional[str]
    date: str
    additional_units: int
    baseline_demand: Dict[str, Any]
    production_capacity_impact: Dict[str, Any]
    delivery_slot_impact: Dict[str, Any]
    item_requirements: List[ItemRequirementSim]
    stock_shortfalls: List[ItemRequirementSim]
    restock_implications: List[str]
    financial_constraint_summary: Dict[str, Any]
    blockers: List[str]
    warnings: List[str]
    assumptions: List[str]
    recommended_next_action: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["item_requirements"] = [item.to_dict() for item in self.item_requirements]
        d["stock_shortfalls"] = [item.to_dict() for item in self.stock_shortfalls]
        return d

