"""
Operations and Fulfillment Engine
Handles production capacity, inventory consumption, wastage, fulfillment, and operations costs.
"""
from typing import Tuple
from src.models.inventory import InventoryState

class OperationsEngine:
    def __init__(self, daily_capacity: float):
        self.daily_capacity = daily_capacity

    def execute_fulfillment(
        self,
        orders_demanded: int,
        inventory: InventoryState,
        variable_cost_per_unit: float,
        delivery_cost_per_unit: float,
    ) -> Tuple[int, int, float, float, float, float, float]:
        """
        Executes daily operations and fulfillment.
        Constraints:
          Fulfilled <= Demand
          Fulfilled <= Available Inventory on hand
          Fulfilled <= Daily Capacity ceiling
        Returns:
          (fulfilled_orders, stockout_units, capacity_utilization, wastage_units,
           variable_operating_cost, delivery_cost, material_cogs)
        """
        # Constraint 1: Inventory bottleneck
        inventory_available = inventory.on_hand

        # Constraint 2: Production/Service capacity bottleneck
        capacity_available = self.daily_capacity

        # Maximum possible fulfilled
        possible_by_inventory = min(float(orders_demanded), inventory_available)
        fulfilled_float = min(possible_by_inventory, capacity_available)
        fulfilled_orders = int(fulfilled_float)

        stockout_units = max(0, orders_demanded - fulfilled_orders)

        # Consume from inventory with actual lot cost
        _, material_cogs = inventory.consume_with_cost(fulfilled_orders)

        # Apply daily wastage / spoilage to remaining inventory
        wastage_units = inventory.apply_wastage()

        # Capacity utilization
        capacity_utilization = (fulfilled_orders / self.daily_capacity) if self.daily_capacity > 0 else 0.0

        # Costs
        variable_operating_cost = fulfilled_orders * variable_cost_per_unit
        delivery_cost = fulfilled_orders * delivery_cost_per_unit

        return (
            fulfilled_orders,
            stockout_units,
            capacity_utilization,
            wastage_units,
            variable_operating_cost,
            delivery_cost,
            material_cogs,
        )
