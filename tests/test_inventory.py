"""
Unit tests for Inventory State and Flow
"""
import unittest
from src.models.inventory import InventoryState, PendingDelivery

class TestInventoryState(unittest.TestCase):
    def setUp(self):
        self.inv = InventoryState(
            on_hand=50.0,
            reorder_point=30.0,
            target_inventory=80.0,
            min_order_quantity=20.0,
            bulk_threshold=60.0,
            bulk_discount=0.10,
            base_unit_cost=100.0,
            lead_time_days=2,
            wastage_rate=0.05,
        )

    def test_consumption(self):
        consumed = self.inv.consume(20.0)
        self.assertEqual(consumed, 20.0)
        self.assertEqual(self.inv.on_hand, 30.0)

        # Exceeding on-hand returns only available
        consumed2 = self.inv.consume(50.0)
        self.assertEqual(consumed2, 30.0)
        self.assertEqual(self.inv.on_hand, 0.0)

    def test_pipeline_and_lead_time(self):
        order = PendingDelivery(
            quantity=40.0,
            unit_cost=100.0,
            total_cost=4000.0,
            days_remaining=2,
            is_bulk=False,
        )
        self.inv.pipeline.append(order)
        self.assertEqual(self.inv.on_order, 40.0)
        self.assertEqual(self.inv.inventory_position, 90.0)

        # Day 1: Order does not arrive yet
        delivered_day1 = self.inv.advance_day()
        self.assertEqual(delivered_day1, 0.0)
        self.assertEqual(self.inv.on_hand, 50.0)

        # Day 2: Order arrives
        delivered_day2 = self.inv.advance_day()
        self.assertEqual(delivered_day2, 40.0)
        self.assertEqual(self.inv.on_hand, 90.0)
        self.assertEqual(len(self.inv.pipeline), 0)

    def test_wastage(self):
        wasted = self.inv.apply_wastage()
        self.assertEqual(wasted, 2.5)  # 5% of 50.0
        self.assertEqual(self.inv.on_hand, 47.5)

if __name__ == "__main__":
    unittest.main()
