"""
Simulation Results and Daily Step Metrics
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class DailyMetric:
    day: int
    gross_demand: float
    orders_placed: int
    orders_fulfilled: int
    orders_stockout: int
    production_capacity: float
    capacity_utilization: float
    starting_inventory: float
    ending_inventory: float
    procurement_units_ordered: float
    procurement_units_delivered: float
    procurement_spend: float
    wastage_units: float
    revenue: float
    cogs: float
    variable_operating_cost: float
    delivery_cost: float
    platform_commission: float
    marketing_spend: float
    fixed_overhead: float
    total_cost: float
    daily_profit: float
    starting_cash: float
    ending_cash: float
    cash_inflow: float
    cash_outflow: float
    new_customers_acquired: int
    active_customers: int
    repeat_orders: int
    stockout_occurred: bool
    initial_customers: int = 0

@dataclass
class SimulationResult:
    business_type: str
    display_name: str
    simulation_days: int
    seed: int
    daily_records: List[DailyMetric] = field(default_factory=list)

    # Aggregated Summary KPI Properties
    @property
    def total_revenue(self) -> float:
        return sum(d.revenue for d in self.daily_records)

    @property
    def total_cost(self) -> float:
        return sum(d.total_cost for d in self.daily_records)

    @property
    def net_profit(self) -> float:
        return self.total_revenue - self.total_cost

    @property
    def starting_cash(self) -> float:
        return self.daily_records[0].starting_cash if self.daily_records else 0.0

    @property
    def ending_cash(self) -> float:
        return self.daily_records[-1].ending_cash if self.daily_records else 0.0

    @property
    def min_cash_balance(self) -> float:
        return min((d.ending_cash for d in self.daily_records), default=0.0)

    @property
    def total_cash_inflow(self) -> float:
        return sum(d.cash_inflow for d in self.daily_records)

    @property
    def total_cash_outflow(self) -> float:
        return sum(d.cash_outflow for d in self.daily_records)

    @property
    def operating_cash_flow(self) -> float:
        return self.total_cash_inflow - self.total_cash_outflow

    @property
    def net_cash_flow(self) -> float:
        return self.ending_cash - self.starting_cash

    @property
    def total_demand(self) -> int:
        return sum(d.orders_placed for d in self.daily_records)

    @property
    def total_fulfilled_orders(self) -> int:
        return sum(d.orders_fulfilled for d in self.daily_records)

    @property
    def fulfillment_rate(self) -> float:
        return (self.total_fulfilled_orders / self.total_demand) if self.total_demand > 0 else 1.0

    @property
    def total_stockout_days(self) -> int:
        return sum(1 for d in self.daily_records if d.stockout_occurred)

    @property
    def total_wastage_units(self) -> float:
        return sum(d.wastage_units for d in self.daily_records)

    @property
    def initial_customers(self) -> int:
        return self.daily_records[0].initial_customers if self.daily_records else 0

    @property
    def total_customers_acquired(self) -> int:
        return sum(d.new_customers_acquired for d in self.daily_records)

    @property
    def total_customer_base(self) -> int:
        return self.initial_customers + self.total_customers_acquired

    @property
    def ending_active_customers(self) -> int:
        return self.daily_records[-1].active_customers if self.daily_records else 0

    @property
    def total_marketing_spend(self) -> float:
        return sum(d.marketing_spend for d in self.daily_records)

    @property
    def customer_acquisition_cost(self) -> float:
        if self.total_customers_acquired > 0:
            return self.total_marketing_spend / self.total_customers_acquired
        return 0.0

    @property
    def total_repeat_orders(self) -> int:
        return sum(d.repeat_orders for d in self.daily_records)

    @property
    def average_capacity_utilization(self) -> float:
        if not self.daily_records:
            return 0.0
        return sum(d.capacity_utilization for d in self.daily_records) / len(self.daily_records)

    @property
    def average_inventory(self) -> float:
        if not self.daily_records:
            return 0.0
        return sum(d.ending_inventory for d in self.daily_records) / len(self.daily_records)

    @property
    def max_inventory(self) -> float:
        return max((d.ending_inventory for d in self.daily_records), default=0.0)

    @property
    def marketing_roi(self) -> float:
        if self.total_marketing_spend > 0:
            return (self.net_profit / self.total_marketing_spend)
        return 0.0

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "display_name": self.display_name,
            "simulation_days": self.simulation_days,
            "seed": self.seed,
            "total_revenue": round(self.total_revenue, 2),
            "total_cost": round(self.total_cost, 2),
            "net_profit": round(self.net_profit, 2),
            "starting_cash": round(self.starting_cash, 2),
            "ending_cash": round(self.ending_cash, 2),
            "min_cash_balance": round(self.min_cash_balance, 2),
            "operating_cash_flow": round(self.operating_cash_flow, 2),
            "total_cash_inflow": round(self.total_cash_inflow, 2),
            "total_cash_outflow": round(self.total_cash_outflow, 2),
            "total_demand_orders": self.total_demand,
            "total_fulfilled_orders": self.total_fulfilled_orders,
            "fulfillment_rate_pct": round(self.fulfillment_rate * 100, 2),
            "total_stockout_days": self.total_stockout_days,
            "total_wastage_units": round(self.total_wastage_units, 2),
            "initial_customers": self.initial_customers,
            "total_customers_acquired": self.total_customers_acquired,
            "total_customer_base": self.total_customer_base,
            "ending_active_customers": self.ending_active_customers,
            "total_marketing_spend": round(self.total_marketing_spend, 2),
            "customer_acquisition_cost": round(self.customer_acquisition_cost, 2),
            "total_repeat_orders": self.total_repeat_orders,
            "average_capacity_utilization_pct": round(self.average_capacity_utilization * 100, 2),
            "average_inventory": round(self.average_inventory, 2),
            "max_inventory": round(self.max_inventory, 2),
            "marketing_roi": round(self.marketing_roi, 2),
        }
