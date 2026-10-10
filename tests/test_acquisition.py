"""
Unit tests for Customer Acquisition Engine
"""
import random
import unittest
from src.engine.acquisition import AcquisitionEngine

class TestAcquisitionEngine(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(42)
        self.engine = AcquisitionEngine(self.rng)

    def test_zero_spend(self):
        new_cust, cac = self.engine.calculate_new_customers(
            marketing_spend=0.0,
            base_cac=100.0,
            conversion_rate=0.2,
        )
        self.assertEqual(new_cust, 0)
        self.assertEqual(cac, 0.0)

    def test_positive_acquisition(self):
        new_cust, cac = self.engine.calculate_new_customers(
            marketing_spend=500.0,
            base_cac=100.0,
            conversion_rate=0.4,
        )
        self.assertGreater(new_cust, 0)
        self.assertGreater(cac, 0.0)

    def test_diminishing_returns(self):
        engine1 = AcquisitionEngine(random.Random(10))
        new_cust_low, _ = engine1.calculate_new_customers(
            marketing_spend=500.0,
            base_cac=100.0,
            conversion_rate=0.2,
        )

        engine2 = AcquisitionEngine(random.Random(10))
        new_cust_high, _ = engine2.calculate_new_customers(
            marketing_spend=5000.0,
            base_cac=100.0,
            conversion_rate=0.2,
        )
        # Even with 10x spend, diminishing returns ensures less than 10x linear customers
        self.assertLess(new_cust_high, new_cust_low * 10)

if __name__ == "__main__":
    unittest.main()
