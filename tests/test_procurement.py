"""
Unit tests for Procurement Engine
"""
import unittest
from src.models.inventory import InventoryState
from src.engine.procurement import ProcurementEngine

class TestProcurementEngine(unittest.TestCase):
    def setUp(self):
        self.inv = InventoryState(
            on_hand=20.0,
            reorder_point=30.0,
            target_inventory=80.0,
            min_order_quantity=25.0,
            bulk_threshold=60.0,
            bulk_discount=0.10,
            base_unit_cost=100.0,
            lead_time_days=2,
            wastage_rate=0.02,
        )
        self.engine = ProcurementEngine()

    def test_reorder_trigger(self):
        # On-hand = 20 < Reorder Point = 30 -> Trigger order
        # Needed: 80 - 20 = 60 units (which meets bulk_threshold 60!)
        # Bulk discount 10% on 100 -> unit cost 90
        qty, spend, is_bulk = self.engine.evaluate_procurement(self.inv, available_cash=10000.0)
        self.assertEqual(qty, 60.0)
        self.assertTrue(is_bulk)
        self.assertEqual(spend, 60.0 * 90.0)
        self.assertEqual(len(self.inv.pipeline), 1)

    def test_cash_constraint(self):
        # Only Rs. 1500 usable cash (above 2000 reserve = total cash 3500)
        # 60 units costs 5400, but only 1500 usable
        # 1500 / 100 = 15 units, but MOQ is 25 units!
        # Order should fail due to cash crunch!
        qty, spend, is_bulk = self.engine.evaluate_procurement(self.inv, available_cash=3500.0)
        self.assertEqual(qty, 0.0)
        self.assertEqual(spend, 0.0)
        self.assertEqual(len(self.inv.pipeline), 0)

    def test_forced_bulk(self):
        forced_engine = ProcurementEngine(force_bulk=True)
        # Small deficit: on-hand 25, target 40 -> needed 15, but forced bulk threshold is 60
        self.inv.target_inventory = 40.0
        qty, spend, is_bulk = forced_engine.evaluate_procurement(self.inv, available_cash=10000.0)
        self.assertEqual(qty, 60.0)
        self.assertTrue(is_bulk)

if __name__ == "__main__":
    unittest.main()
