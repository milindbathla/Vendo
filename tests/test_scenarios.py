"""
Scenario Engine and What-If Tests
"""
import unittest
from src.simulator import load_business_profiles
from src.scenarios.scenario_engine import ScenarioEngine, ScenarioConfig

class TestScenarioEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_business_profiles()

    def test_scenario_comparison(self):
        profile = self.profiles["home_bakery"]
        engine = ScenarioEngine(profile)
        scenarios = engine.get_default_scenarios()

        results = engine.run_all(scenarios=scenarios, days=60, seed=42)

        self.assertEqual(len(results), len(scenarios))
        self.assertIn("scenario_a_baseline", results)
        self.assertIn("scenario_c_bulk_procurement", results)
        self.assertIn("scenario_d_supplier_shock", results)

        base_res = results["scenario_a_baseline"]
        shock_res = results["scenario_d_supplier_shock"]

        # 15% supplier cost inflation should strictly reduce net profit
        self.assertLess(shock_res.net_profit, base_res.net_profit)

        # Formatted comparison table should generate properly
        table = engine.format_comparison_table(scenarios, results)
        self.assertIn("A: Baseline Strategy", table)
        self.assertIn("D: Supplier Price Shock", table)

if __name__ == "__main__":
    unittest.main()
