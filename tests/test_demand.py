"""
Unit tests for Demand Engine
"""
import random
import unittest
from src.engine.demand import DemandEngine

class TestDemandEngine(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(42)
        self.engine = DemandEngine(self.rng)

    def test_day_of_week_seasonality(self):
        # Home tiffin weekday > weekend
        tiffin_weekday = self.engine.get_day_of_week_factor(day=2, business_type="home_tiffin") # Tuesday
        tiffin_weekend = self.engine.get_day_of_week_factor(day=7, business_type="home_tiffin") # Sunday
        self.assertGreater(tiffin_weekday, tiffin_weekend)

        # Home bakery weekend > weekday
        bakery_weekday = self.engine.get_day_of_week_factor(day=3, business_type="home_bakery")
        bakery_weekend = self.engine.get_day_of_week_factor(day=6, business_type="home_bakery")
        self.assertGreater(bakery_weekend, bakery_weekday)

    def test_price_elasticity(self):
        # Higher price reduces demand factor
        factor_discount = self.engine.calculate_price_elasticity_factor(90.0, 100.0)
        factor_expensive = self.engine.calculate_price_elasticity_factor(120.0, 100.0)
        self.assertGreater(factor_discount, 1.0)
        self.assertLess(factor_expensive, 1.0)

    def test_reproducibility(self):
        engine1 = DemandEngine(random.Random(123))
        orders1 = engine1.generate_orders(
            day=1, business_type="home_bakery", base_demand=20.0,
            demand_variability=0.15, current_price=250.0, baseline_price=250.0,
            new_customer_orders=2, repeat_customer_orders=3,
        )

        engine2 = DemandEngine(random.Random(123))
        orders2 = engine2.generate_orders(
            day=1, business_type="home_bakery", base_demand=20.0,
            demand_variability=0.15, current_price=250.0, baseline_price=250.0,
            new_customer_orders=2, repeat_customer_orders=3,
        )
        self.assertEqual(orders1, orders2)

if __name__ == "__main__":
    unittest.main()
