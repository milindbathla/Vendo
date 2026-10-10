"""
Procurement Engine
Models inventory reordering, lead times, MOQ, bulk discounts, and working capital constraints.
"""
from typing import Tuple, Optional
from src.models.inventory import InventoryState, PendingDelivery

class ProcurementEngine:
    def __init__(self, force_bulk: Optional[bool] = None):
        """
        force_bulk: If True, always orders at least the bulk_threshold quantity when reordering.
                    If False, orders normal target quantity.
        """
        self.force_bulk = force_bulk

    def evaluate_procurement(
        self,
        inventory: InventoryState,
        available_cash: float,
        cash_reserve_target: float = 2000.0,
    ) -> Tuple[float, float, bool]:
        """
        Evaluates whether to place an order today.
        Returns (units_ordered, cash_committed, is_bulk).
        """
        # Check reorder point against inventory position (on-hand + on-order)
        if inventory.inventory_position >= inventory.reorder_point:
            return 0.0, 0.0, False

        # Desired order quantity to reach target inventory
        needed_units = inventory.target_inventory - inventory.inventory_position
        order_quantity = max(needed_units, inventory.min_order_quantity)

        # Apply forced bulk strategy if requested by scenario
        if self.force_bulk is True or (order_quantity >= inventory.bulk_threshold):
            order_quantity = max(order_quantity, inventory.bulk_threshold)

        # Determine pricing (bulk discount)
        is_bulk = order_quantity >= inventory.bulk_threshold
        unit_price = inventory.base_unit_cost
        if is_bulk:
            unit_price = unit_price * (1.0 - inventory.bulk_discount)

        total_procurement_cost = order_quantity * unit_price

        # Working Capital Constraint Check:
        # Business cannot spend cash below minimum liquid reserve
        usable_cash = max(0.0, available_cash - cash_reserve_target)

        if total_procurement_cost > usable_cash:
            # Cash constrained! Can we afford at least MOQ?
            max_affordable_units = usable_cash / unit_price
            if max_affordable_units < inventory.min_order_quantity:
                # Cannot even afford minimum order quantity: Order fails!
                # This causes an inventory stockout down the line due to cash crunch.
                return 0.0, 0.0, False
            else:
                # Shrink order to affordable limit
                order_quantity = max_affordable_units
                is_bulk = order_quantity >= inventory.bulk_threshold
                if not is_bulk:
                    # Recalculate price without bulk discount
                    unit_price = inventory.base_unit_cost
                    order_quantity = usable_cash / unit_price
                    is_bulk = False
                total_procurement_cost = order_quantity * unit_price

        # Place the order into the pipeline with lead time
        delivery = PendingDelivery(
            quantity=order_quantity,
            unit_cost=unit_price,
            total_cost=total_procurement_cost,
            days_remaining=inventory.lead_time_days,
            is_bulk=is_bulk,
        )
        inventory.pipeline.append(delivery)

        return order_quantity, total_procurement_cost, is_bulk
