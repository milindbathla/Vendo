"""
Customer Pool and Acquisition Models
"""
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class ChannelConfig:
    name: str
    share_of_spend: float  # e.g., 0.50 for 50% of budget
    base_cac: float        # cost to acquire 1 prospect
    conversion_rate: float # probability prospect converts to paying customer

@dataclass
class CustomerState:
    initial_customers: int = 0
    total_customers_acquired: int = 0
    active_customer_pool: float = 0.0
    churned_customers: int = 0
    repeat_orders_generated: int = 0
    new_orders_generated: int = 0

    def __post_init__(self):
        if self.initial_customers > 0 and self.active_customer_pool == 0.0:
            self.active_customer_pool = float(self.initial_customers)

    @property
    def total_customers(self) -> int:
        return self.initial_customers + self.total_customers_acquired

    def record_day(
        self,
        new_customers: float,
        churn_rate: float,
        repeat_prob: float,
        service_quality_factor: float = 1.0,
    ) -> (int, int):
        """
        Updates customer pool and returns (new_orders, repeat_orders).
        Distinguishes newly acquired customers from initial/retained active customers.
        service_quality_factor drops if there were stockouts on prior days.
        """
        # Effective retention adjusted for satisfaction
        effective_retention = max(0.1, (1.0 - churn_rate) * service_quality_factor)
        retained = self.active_customer_pool * effective_retention
        churned = self.active_customer_pool - retained
        self.churned_customers += int(churned)
        
        # New customer additions (from acquisition spend)
        self.active_customer_pool = retained + new_customers
        self.total_customers_acquired += int(new_customers)

        # Generate orders:
        # Each newly acquired customer places an initial order
        new_orders = int(round(new_customers))
        # Retained customer pool places repeat orders based on repeat propensity and service quality
        repeat_orders = int(round(retained * repeat_prob * service_quality_factor))

        self.new_orders_generated += new_orders
        self.repeat_orders_generated += repeat_orders

        return new_orders, repeat_orders
