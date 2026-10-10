"""
Inventory and Procurement Order Models
"""
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class PendingDelivery:
    quantity: float
    unit_cost: float
    total_cost: float
    days_remaining: int
    is_bulk: bool

@dataclass
class InventoryLot:
    quantity: float
    unit_cost: float

@dataclass
class InventoryState:
    on_hand: float
    reorder_point: float
    target_inventory: float
    min_order_quantity: float
    bulk_threshold: float
    bulk_discount: float
    base_unit_cost: float
    lead_time_days: int
    wastage_rate: float
    pipeline: List[PendingDelivery] = field(default_factory=list)
    lots: List[InventoryLot] = field(default_factory=list)

    def __post_init__(self):
        if not self.lots and self.on_hand > 0:
            self.lots.append(InventoryLot(quantity=self.on_hand, unit_cost=self.base_unit_cost))

    @property
    def on_order(self) -> float:
        return sum(order.quantity for order in self.pipeline)

    @property
    def inventory_position(self) -> float:
        """Position = On-Hand + On-Order"""
        return self.on_hand + self.on_order

    @property
    def current_unit_cost(self) -> float:
        if self.lots and self.on_hand > 0:
            total_val = sum(l.quantity * l.unit_cost for l in self.lots)
            total_qty = sum(l.quantity for l in self.lots)
            return (total_val / total_qty) if total_qty > 0 else self.base_unit_cost
        return self.base_unit_cost

    def advance_day(self) -> float:
        """
        Advance pending deliveries by 1 day.
        Returns total units delivered today and adds them to inventory lots.
        """
        delivered_units = 0.0
        remaining_pipeline = []
        for order in self.pipeline:
            order.days_remaining -= 1
            if order.days_remaining <= 0:
                delivered_units += order.quantity
                self.on_hand += order.quantity
                self.lots.append(InventoryLot(quantity=order.quantity, unit_cost=order.unit_cost))
            else:
                remaining_pipeline.append(order)
        self.pipeline = remaining_pipeline
        return delivered_units

    def consume_with_cost(self, amount: float) -> Tuple[float, float]:
        """
        Consume inventory using FIFO.
        Returns (actual_units_consumed, total_cost_of_consumed_units).
        """
        if not self.lots and self.on_hand > 0:
            self.lots.append(InventoryLot(quantity=self.on_hand, unit_cost=self.base_unit_cost))

        remaining_to_consume = min(self.on_hand, amount)
        actual_consumed = remaining_to_consume
        total_cost = 0.0

        while self.lots and remaining_to_consume > 0:
            lot = self.lots[0]
            if lot.quantity <= remaining_to_consume:
                total_cost += lot.quantity * lot.unit_cost
                remaining_to_consume -= lot.quantity
                self.lots.pop(0)
            else:
                total_cost += remaining_to_consume * lot.unit_cost
                lot.quantity -= remaining_to_consume
                remaining_to_consume = 0.0

        self.on_hand = max(0.0, self.on_hand - actual_consumed)
        if self.on_hand == 0.0:
            self.lots.clear()

        return actual_consumed, total_cost

    def consume(self, amount: float) -> float:
        """Consume inventory for production/fulfillment. Returns actual consumed."""
        actual, _ = self.consume_with_cost(amount)
        return actual

    def apply_wastage(self) -> float:
        """Apply daily spoilage/wastage to on-hand inventory."""
        wasted = self.on_hand * self.wastage_rate
        actual_wasted, _ = self.consume_with_cost(wasted)
        return actual_wasted
