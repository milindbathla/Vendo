"""
Business Profile and Configuration Models
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class BusinessProfile:
    business_type: str
    display_name: str
    description: str
    starting_capital: float
    starting_inventory: float
    daily_capacity: float
    supplier_unit_cost: float
    bulk_order_threshold: float
    bulk_discount: float
    procurement_lead_time_days: int
    min_order_quantity: float
    selling_price: float
    daily_fixed_cost: float
    variable_cost_per_unit: float
    delivery_cost_per_unit: float
    platform_commission_rate: float
    base_daily_demand: float
    demand_variability: float
    daily_marketing_spend: float
    acquisition_cost_per_customer: float
    customer_conversion_rate: float
    customer_retention_rate: float
    daily_repeat_order_probability: float
    daily_wastage_rate: float
    reorder_point: float
    target_inventory: float
    receivables_delay_days: int = 0
    initial_customers: Optional[int] = None

    @property
    def estimated_initial_customers(self) -> int:
        if self.initial_customers is not None:
            return self.initial_customers
        if self.daily_repeat_order_probability > 0:
            return max(1, int(round(self.base_daily_demand / self.daily_repeat_order_probability)))
        return max(1, int(round(self.base_daily_demand)))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusinessProfile":
        return cls(
            business_type=data["business_type"],
            display_name=data.get("display_name", data["business_type"]),
            description=data.get("description", ""),
            starting_capital=float(data["starting_capital"]),
            starting_inventory=float(data["starting_inventory"]),
            daily_capacity=float(data["daily_capacity"]),
            supplier_unit_cost=float(data["supplier_unit_cost"]),
            bulk_order_threshold=float(data["bulk_order_threshold"]),
            bulk_discount=float(data["bulk_discount"]),
            procurement_lead_time_days=int(data["procurement_lead_time_days"]),
            min_order_quantity=float(data["min_order_quantity"]),
            selling_price=float(data["selling_price"]),
            daily_fixed_cost=float(data["daily_fixed_cost"]),
            variable_cost_per_unit=float(data["variable_cost_per_unit"]),
            delivery_cost_per_unit=float(data.get("delivery_cost_per_unit", 0.0)),
            platform_commission_rate=float(data.get("platform_commission_rate", 0.0)),
            base_daily_demand=float(data["base_daily_demand"]),
            demand_variability=float(data.get("demand_variability", 0.15)),
            daily_marketing_spend=float(data["daily_marketing_spend"]),
            acquisition_cost_per_customer=float(data["acquisition_cost_per_customer"]),
            customer_conversion_rate=float(data["customer_conversion_rate"]),
            customer_retention_rate=float(data["customer_retention_rate"]),
            daily_repeat_order_probability=float(data.get("daily_repeat_order_probability", 0.20)),
            daily_wastage_rate=float(data.get("daily_wastage_rate", 0.02)),
            reorder_point=float(data.get("reorder_point", 30.0)),
            target_inventory=float(data.get("target_inventory", 80.0)),
            receivables_delay_days=int(data.get("receivables_delay_days", 0)),
            initial_customers=int(data["initial_customers"]) if data.get("initial_customers") is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_type": self.business_type,
            "display_name": self.display_name,
            "description": self.description,
            "starting_capital": self.starting_capital,
            "starting_inventory": self.starting_inventory,
            "daily_capacity": self.daily_capacity,
            "supplier_unit_cost": self.supplier_unit_cost,
            "bulk_order_threshold": self.bulk_order_threshold,
            "bulk_discount": self.bulk_discount,
            "procurement_lead_time_days": self.procurement_lead_time_days,
            "min_order_quantity": self.min_order_quantity,
            "selling_price": self.selling_price,
            "daily_fixed_cost": self.daily_fixed_cost,
            "variable_cost_per_unit": self.variable_cost_per_unit,
            "delivery_cost_per_unit": self.delivery_cost_per_unit,
            "platform_commission_rate": self.platform_commission_rate,
            "base_daily_demand": self.base_daily_demand,
            "demand_variability": self.demand_variability,
            "daily_marketing_spend": self.daily_marketing_spend,
            "acquisition_cost_per_customer": self.acquisition_cost_per_customer,
            "customer_conversion_rate": self.customer_conversion_rate,
            "customer_retention_rate": self.customer_retention_rate,
            "daily_repeat_order_probability": self.daily_repeat_order_probability,
            "daily_wastage_rate": self.daily_wastage_rate,
            "reorder_point": self.reorder_point,
            "target_inventory": self.target_inventory,
            "receivables_delay_days": self.receivables_delay_days,
            "initial_customers": self.initial_customers,
        }
