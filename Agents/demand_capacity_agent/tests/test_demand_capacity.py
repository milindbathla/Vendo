"""Unit and integration tests for Demand & Capacity specialist agent."""

import os
import shutil
import sys
import tempfile
import unittest

# Ensure src is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from demand_capacity.agent import DemandCapacityAgent
from demand_capacity.config import resolve_db_path
from demand_capacity.models import ValidationError


class TestDemandCapacityAgent(unittest.TestCase):
    """Test suite verifying demand forecasting, historical patterns, and capacity simulation."""

    @classmethod
    def setUpClass(cls):
        cls.source_db = resolve_db_path()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = os.path.join(cls.temp_dir, "test_demo.db")
        shutil.copy2(cls.source_db, cls.test_db)
        cls.agent = DemandCapacityAgent.from_db_path(cls.test_db)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_forecast_demand_default_tomorrow(self):
        """Verify normal forecast retrieval for dynamically read tomorrow date."""
        res = self.agent.forecast_demand()
        self.assertEqual(res.planning_date, "2026-10-11")
        self.assertEqual(len(res.days), 1)

        day = res.days[0]
        self.assertEqual(day.date, "2026-10-11")
        self.assertEqual(day.status, "available")
        self.assertEqual(day.forecast_units, 23.0)
        self.assertEqual(day.lower_bound, 20.0)
        self.assertEqual(day.upper_bound, 26.0)
        self.assertEqual(day.confidence, 0.82)
        self.assertEqual(day.confirmed_units, 20)
        self.assertIsNotNone(day.demand_driver)
        self.assertEqual(day.demand_driver.weekday, "Sunday")

    def test_forecast_demand_missing_date(self):
        """Verify that dates without a database forecast return explicit 'unavailable' status."""
        res = self.agent.forecast_demand(start_date="2026-12-31")
        self.assertEqual(len(res.days), 1)
        day = res.days[0]
        self.assertEqual(day.date, "2026-12-31")
        self.assertEqual(day.status, "unavailable")
        self.assertIsNone(day.forecast_units)
        self.assertIn("No forecast record exists", day.note)

    def test_forecast_demand_invalid_range(self):
        """Verify ValidationError when start_date is after end_date."""
        with self.assertRaises(ValidationError):
            self.agent.forecast_demand(start_date="2026-10-15", end_date="2026-10-10")

    def test_analyze_demand_patterns(self):
        """Verify historical demand analysis returns structured distributions without causal claims."""
        res = self.agent.analyze_demand_patterns()
        self.assertGreater(res.sample_size, 1000)
        self.assertIn("Sunday", res.weekday_distribution)
        self.assertIn("subscription", res.order_type_distribution)
        self.assertIn("delivered", res.order_status_distribution)
        self.assertGreater(res.recurring_customer_snapshot.get("recurring_pct", 0), 50.0)
        self.assertTrue(any("Subscription orders account for" in t for t in res.trend_observations))
        self.assertTrue(any("synthetic" in u.lower() for u in res.uncertainty_limitations))

    def test_get_capacity_status(self):
        """Verify production capacity and delivery slot breakdown for tomorrow."""
        res = self.agent.get_capacity_status()
        self.assertEqual(res.date, "2026-10-11")
        self.assertEqual(res.max_production_meals, 40)
        self.assertEqual(res.committed_units, 20)
        self.assertEqual(res.remaining_production_capacity, 20)
        self.assertEqual(res.production_utilization_pct, 50.0)

        # Four delivery slots with free units
        self.assertEqual(len(res.delivery_slots), 4)
        total_free = sum(s.free_units for s in res.delivery_slots)
        self.assertEqual(total_free, 20)
        self.assertEqual(res.total_slot_free, 20)
        self.assertEqual(res.capacity_shortfall, 0)

    def test_simulate_additional_demand_small_feasible(self):
        """Verify a request within remaining capacity, slots, and stock checks stock."""
        res = self.agent.simulate_additional_demand(additional_units=5)
        self.assertEqual(res.additional_units, 5)
        self.assertEqual(res.production_capacity_impact["simulated_total_committed"], 25)
        self.assertFalse(res.production_capacity_impact["is_exceeded"])
        self.assertFalse(res.feasible)
        self.assertEqual(res.binding_constraint, "inventory_stockout")
        self.assertTrue(any("Sunflower oil" in b or "container" in b for b in res.blockers))

    def test_simulate_additional_demand_production_blocker(self):
        """Verify that requesting units exceeding production capacity flags production blocker."""
        res = self.agent.simulate_additional_demand(additional_units=25)
        self.assertFalse(res.feasible)
        self.assertEqual(res.binding_constraint, "production_capacity")
        self.assertTrue(res.production_capacity_impact["is_exceeded"])
        self.assertEqual(res.production_capacity_impact["shortfall"], 5)
        self.assertTrue(any("Production limit exceeded" in b for b in res.blockers))

    def test_simulate_additional_demand_delivery_slot_blocker(self):
        """Verify that requesting units exceeding a specific delivery slot flags slot blocker."""
        res = self.agent.simulate_additional_demand(
            additional_units=5, delivery_slot_id="SLOT-20261011-2"
        )
        self.assertFalse(res.feasible)
        self.assertTrue(res.delivery_slot_impact["is_exceeded"])
        self.assertTrue(any("SLOT-20261011-2 only has 2 free units" in b for b in res.blockers))

    def test_simulate_additional_demand_invalid_input(self):
        """Verify ValidationError when additional_units <= 0."""
        with self.assertRaises(ValidationError):
            self.agent.simulate_additional_demand(additional_units=0)
        with self.assertRaises(ValidationError):
            self.agent.simulate_additional_demand(additional_units=-10)


if __name__ == "__main__":
    unittest.main()

