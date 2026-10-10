"""
End-to-End Simulation Tests
Validates full 90-day simulation runs and strict seed reproducibility.
"""
import unittest
from src.simulator import BusinessSimulator, load_business_profiles

class TestFullSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_business_profiles()

    def test_complete_90_day_home_bakery(self):
        profile = self.profiles["home_bakery"]
        sim = BusinessSimulator(profile=profile, days=90, seed=42)
        res = sim.run()

        self.assertEqual(len(res.daily_records), 90)
        self.assertEqual(res.simulation_days, 90)
        self.assertGreater(res.total_revenue, 0.0)
        self.assertGreater(res.total_cost, 0.0)
        self.assertGreater(res.total_fulfilled_orders, 0)
        self.assertGreaterEqual(res.fulfillment_rate, 0.0)
        self.assertLessEqual(res.fulfillment_rate, 1.0)
        self.assertGreater(res.total_customers_acquired, 0)
        self.assertGreater(res.ending_active_customers, 0)

    def test_strict_seed_reproducibility(self):
        profile = self.profiles["home_tiffin"]
        sim1 = BusinessSimulator(profile=profile, days=60, seed=101)
        res1 = sim1.run()

        sim2 = BusinessSimulator(profile=profile, days=60, seed=101)
        res2 = sim2.run()

        # Both runs must produce identical results down to exact floating point values
        self.assertEqual(res1.total_revenue, res2.total_revenue)
        self.assertEqual(res1.net_profit, res2.net_profit)
        self.assertEqual(res1.ending_cash, res2.ending_cash)
        self.assertEqual(res1.total_fulfilled_orders, res2.total_fulfilled_orders)
        self.assertEqual(res1.total_stockout_days, res2.total_stockout_days)

    def test_different_seeds_vary(self):
        profile = self.profiles["home_tiffin"]
        sim_a = BusinessSimulator(profile=profile, days=60, seed=101)
        res_a = sim_a.run()

        sim_b = BusinessSimulator(profile=profile, days=60, seed=999)
        res_b = sim_b.run()

        # Different random seeds should produce slightly different stochastic trajectories
        self.assertNotEqual(res_a.total_revenue, res_b.total_revenue)

    def test_all_10_business_profiles_run(self):
        for b_type, prof in self.profiles.items():
            sim = BusinessSimulator(profile=prof, days=30, seed=42)
            res = sim.run()
            self.assertEqual(len(res.daily_records), 30)
            self.assertGreater(res.total_revenue, 0.0)

if __name__ == "__main__":
    unittest.main()
